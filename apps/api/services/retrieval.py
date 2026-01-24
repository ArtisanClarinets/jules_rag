import asyncio
import json
import re
from typing import List, Dict, Any
from apps.api.services.embedding import get_embedding_provider, get_rerank_provider
from apps.api.services.vector_db import search_vectors
from apps.api.services.sparse_db import search_sparse
from apps.api.services.llm import generate_text

async def decompose_query(query: str) -> List[str]:
    """Break complex query into sub-questions."""
    try:
        prompt = f"Decompose this complex query into 2-3 atomic sub-questions:\nQuery: {query}\n\nReturn JSON: {{'questions': ['q1', 'q2']}}"
        resp = await generate_text(prompt, system_prompt="You are a query assistant. Return JSON.", temperature=0.0)
        match = re.search(r"\{.*\}", resp, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            return data.get("questions", [])
    except Exception:
        pass
    return []

async def generate_hyde_doc(query: str) -> str:
    """Generate hypothetical answer."""
    try:
        prompt = f"Write a hypothetical code snippet or documentation that answers this query:\nQuery: {query}\n\nCode/Doc:"
        resp = await generate_text(prompt, temperature=0.0)
        return resp
    except Exception:
        return ""

async def hybrid_search(
    collection_name: str,
    query: str,
    limit: int = 10,
    rerank: bool = True
) -> List[Dict[str, Any]]:

    # 1. Query Hyper-Expansion (Parallel)
    expansion_tasks = [
        decompose_query(query),
        generate_hyde_doc(query)
    ]
    sub_questions, hyde_doc = await asyncio.gather(*expansion_tasks)

    # 2. Embeddings & Search Preparation
    embed_provider = get_embedding_provider()

    # Texts to embed: Original + Sub-questions + HyDE
    texts_to_embed = [query] + sub_questions
    if hyde_doc:
        texts_to_embed.append(hyde_doc)

    # Run embedding in parallel
    embedding_task = asyncio.create_task(embed_provider.embed(texts_to_embed))

    # Start Sparse Searches (Original + Sub-questions)
    # We do sparse search for original and sub-questions. HyDE is usually dense only.
    sparse_queries = [query] + sub_questions
    sparse_tasks = []
    for q in sparse_queries:
        sparse_tasks.append(asyncio.create_task(asyncio.to_thread(search_sparse, collection_name, q, limit=limit*2)))

    embeddings = await embedding_task

    # Unpack embeddings
    query_vector = embeddings[0]
    sub_vectors = embeddings[1:1+len(sub_questions)]
    hyde_vector = embeddings[1+len(sub_questions)] if hyde_doc else None

    # Start Dense Searches
    dense_tasks = []
    # Original
    dense_tasks.append(asyncio.create_task(asyncio.to_thread(search_vectors, collection_name, query_vector, limit=limit*2)))
    # Sub-questions
    for vec in sub_vectors:
        dense_tasks.append(asyncio.create_task(asyncio.to_thread(search_vectors, collection_name, vec, limit=limit*2)))
    # HyDE
    if hyde_vector:
        dense_tasks.append(asyncio.create_task(asyncio.to_thread(search_vectors, collection_name, hyde_vector, limit=limit*2)))

    # Await all searches
    all_sparse_results = await asyncio.gather(*sparse_tasks)
    all_dense_results = await asyncio.gather(*dense_tasks)

    # 3. Fusion (RRF)
    # Collect all results
    results_dict = {"combined": []} # Just use one list for RRF input, or separate? RRF takes multiple lists.

    rrf_lists = []

    doc_map = {}

    def process_dense(res_list):
        ranked = []
        for res in res_list:
            doc_id = res.id
            ranked.append(doc_id)
            if doc_id not in doc_map:
                doc_map[doc_id] = res.payload
        return ranked

    def process_sparse(res_list):
        ranked = []
        for res in res_list:
            doc_id = res["_id"]
            ranked.append(doc_id)
            if doc_id not in doc_map:
                doc_map[doc_id] = res["_source"]
        return ranked

    for res_list in all_dense_results:
        rrf_lists.append(process_dense(res_list))

    for res_list in all_sparse_results:
        rrf_lists.append(process_sparse(res_list))

    # Apply RRF
    k = 60
    fused_scores = {}

    for ranked_list in rrf_lists:
        for rank, doc_id in enumerate(ranked_list):
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
