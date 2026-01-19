import asyncio
from typing import List, Dict, Any
from apps.api.services.embedding import get_embedding_provider, get_rerank_provider
from apps.api.services.vector_db import search_vectors
from apps.api.services.sparse_db import search_sparse

async def hybrid_search(
    collection_name: str,
    query: str,
    limit: int = 10,
    rerank: bool = True
) -> List[Dict[str, Any]]:

    # 1. Parallelize Embedding and Sparse Search
    embed_provider = get_embedding_provider()

    # Run embedding
    embedding_task = asyncio.create_task(embed_provider.embed([query]))
    sparse_task = asyncio.create_task(asyncio.to_thread(search_sparse, collection_name, query, limit=limit*2))

    embeddings = await embedding_task
    query_vector = embeddings[0]

    # Run dense search
    dense_results = await asyncio.to_thread(search_vectors, collection_name, query_vector, limit=limit*2)
    sparse_results = await sparse_task

    # 2. Normalize results for RRF
    # Dense results: list of ScoredPoint (id, score, payload)
    # Sparse results: list of dict (hits)

    results_dict = {"dense": [], "sparse": []}

    # Map all docs by ID to payload/content for final return
    doc_map = {}

    for i, res in enumerate(dense_results):
        doc_id = res.id
        results_dict["dense"].append((doc_id, res.score))
        if doc_id not in doc_map:
            doc_map[doc_id] = res.payload

    for i, res in enumerate(sparse_results):
        doc_id = res["_id"]
        results_dict["sparse"].append((doc_id, res["_score"]))
        if doc_id not in doc_map:
            doc_map[doc_id] = res["_source"]

    # 3. Fusion (RRF)
    k = 60
    fused_scores = {}
    for system, doc_list in results_dict.items():
        for rank, (doc_id, score) in enumerate(doc_list):
            if doc_id not in fused_scores:
                fused_scores[doc_id] = 0.0
            fused_scores[doc_id] += 1.0 / (k + rank + 1)

    sorted_docs = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
    top_docs = sorted_docs[:limit*2] # Oversample for rerank

    if not top_docs:
        return []

    # 4. Rerank
    if rerank:
        rerank_provider = get_rerank_provider()
        doc_ids = [d[0] for d in top_docs]
        texts = [doc_map[did].get("text", "") for did in doc_ids]

        reranked = await rerank_provider.rerank(query, texts)
        # reranked is list of {index, score}

        # Sort by rerank score
        reranked.sort(key=lambda x: x["score"], reverse=True)

        final_results = []
        for r in reranked:
            idx = r["index"]
            if idx < len(doc_ids):
                doc_id = doc_ids[idx]
                final_results.append({
                    "id": doc_id,
                    "score": r["score"],
                    "content": doc_map[doc_id]
                })
        return final_results[:limit]

    # No rerank, return RRF sorted
    final_results = []
    for doc_id, score in top_docs[:limit]:
        final_results.append({
            "id": doc_id,
            "score": score,
            "content": doc_map[doc_id]
        })

    return final_results
