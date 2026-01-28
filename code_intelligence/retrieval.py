import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass
import json
import time
import os

import numpy as np

from .db import Database, CodeNode
from .providers import EmbeddingsInterface, LLMInterface
from .config import settings
from .ann_index import ANNIndex

logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    node: CodeNode
    score: float
    reason: str = "similarity"

class RetrievalEngine:
    def __init__(self, db: Database):
        self.db = db
        self.embeddings = EmbeddingsInterface()
        self.llm = LLMInterface()

        # Cache for embeddings
        self._embeddings_cache_matrix: Optional[np.ndarray] = None
        self._embeddings_cache_ids: List[str] = []
        self._cache_timestamp: float = 0

        # ANN Index
        self.ann_index = ANNIndex(os.path.join(os.path.dirname(settings.db_path), "vectors.bin"))

    async def retrieve(self, query: str, k: int = 10) -> List[SearchResult]:
        k = k or settings.retrieval_k

        # 1. Query Expansion (Parallel)
        expansion_tasks = [
            self._decompose_query(query),
            self._generate_hyde_doc(query)
        ]
        sub_questions, hyde_doc = await asyncio.gather(*expansion_tasks)

        if sub_questions:
            logger.info(f"Decomposed query into: {sub_questions}")
        if hyde_doc:
            logger.info("Generated HyDE document.")

        queries_to_search = [query] + sub_questions

        # 2. Search Execution (Parallel)

        # Sparse Search
        sparse_tasks = []
        for q in queries_to_search:
            sparse_tasks.append(asyncio.to_thread(self._sparse_search, q, k*2))

        # Dense Search
        dense_tasks = []
        if self.embeddings.client:
            texts_to_embed = queries_to_search + ([hyde_doc] if hyde_doc else [])
            try:
                # Embeddings API is IO bound, run in thread to avoid blocking loop if sync client
                embeddings_list = await asyncio.to_thread(self.embeddings.embed, texts_to_embed)

                # Queries
                for i in range(len(queries_to_search)):
                    vec = embeddings_list[i]
                    dense_tasks.append(asyncio.to_thread(self._dense_search, vec, k*2))

                # HyDE
                if hyde_doc:
                    hyde_vec = embeddings_list[-1]
                    dense_tasks.append(asyncio.to_thread(self._dense_search, hyde_vec, k*2))

            except Exception as e:
                logger.error(f"Embedding failed: {e}")

        # Await all
        sparse_results_list = await asyncio.gather(*sparse_tasks)
        dense_results_list = await asyncio.gather(*dense_tasks)

        # 3. Graph Expansion
        # Seed graph with top results from original query
        seed_candidates = []
        if sparse_results_list:
            seed_candidates.extend(sparse_results_list[0][:5])
        if dense_results_list:
            seed_candidates.extend(dense_results_list[0][:5])

        graph_results = await asyncio.to_thread(self._expand_graph, seed_candidates, 5)

        # 4. RRF Fusion
        all_lists = sparse_results_list + dense_results_list + [graph_results]
        fused_results = self._rrf_fusion(all_lists, k=60)

        # 5. Rerank
        top_candidates = fused_results[:20]
        final_results = await self._rerank(query, top_candidates)

        return final_results[:k]

    async def _decompose_query(self, query: str) -> List[str]:
        prompt = f"Decompose this complex query into 2-3 atomic sub-questions:\nQuery: {query}\n\nReturn JSON: {{'questions': ['q1', 'q2']}}"
        try:
            resp = await asyncio.to_thread(
                self.llm.generate_response, prompt, system_prompt="You are a query assistant.", json_mode=True
            )
            data = json.loads(resp)
            return data.get("questions", [])
        except Exception:
            return []

    async def _generate_hyde_doc(self, query: str) -> str:
        prompt = f"Write a hypothetical code snippet or documentation that answers this query:\nQuery: {query}\n\nCode/Doc:"
        try:
             return await asyncio.to_thread(
                 self.llm.generate_response, prompt, temperature=0.0
             )
        except Exception:
             return ""

    def _sparse_search(self, query: str, limit: int) -> List[SearchResult]:
        try:
            nodes = self.db.search_nodes(query, limit=limit)
            results = []
            for i, node in enumerate(nodes):
                # Normalize BM25? FTS doesn't give score easily in sqlite FTS5 via library wrappers usually
                # standard rank
                score = 1.0 / (i + 1)
                results.append(SearchResult(node, score, "sparse"))
            return results
        except Exception as e:
            logger.error(f"Sparse search error: {e}")
            return []

    def _dense_search(self, vector: List[float], k: int) -> List[SearchResult]:
        vec_np = np.array(vector, dtype=np.float32)

        if settings.retrieval_enable_ann and self.ann_index.available:
            if not self.ann_index.index:
                 if not self.ann_index.load():
                     self._refresh_cache_if_needed()
                     if self._embeddings_cache_matrix is not None:
                         self.ann_index.build(self._embeddings_cache_matrix, self._embeddings_cache_ids)

            if self.ann_index.index:
                hits = self.ann_index.query(vec_np, k=k)
                results = []
                for nid, score in hits:
                    node = self.db.get_node(nid)
                    if node:
                        results.append(SearchResult(node, score, "dense"))
                return results

        return self._brute_force_search(vec_np, k)

    def _brute_force_search(self, vector: np.ndarray, k: int) -> List[SearchResult]:
        self._refresh_cache_if_needed()
        if self._embeddings_cache_matrix is None:
            return []

        norm_v = np.linalg.norm(vector)
        if norm_v > 0:
            vector = vector / norm_v

        scores = np.dot(self._embeddings_cache_matrix, vector)

        top_k = min(k, len(scores))
        if top_k == 0: return []

        top_indices = np.argpartition(scores, -top_k)[-top_k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        results = []
        for idx in top_indices:
            nid = self._embeddings_cache_ids[idx]
            node = self.db.get_node(nid)
            if node:
                results.append(SearchResult(node, float(scores[idx]), "dense"))
        return results

    def _refresh_cache_if_needed(self):
        if self._embeddings_cache_matrix is not None:
             if time.time() - self._cache_timestamp < 60:
                 return

        conn = self.db._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT node_id, vector FROM embeddings WHERE model = ?", (settings.embeddings_model,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            self._embeddings_cache_matrix = None
            self._embeddings_cache_ids = []
            self._cache_timestamp = time.time()
            return

        ids = []
        vecs = []
        for nid, blob in rows:
            ids.append(nid)
            vecs.append(np.frombuffer(blob, dtype=np.float32))

        self._embeddings_cache_ids = ids
        self._embeddings_cache_matrix = np.vstack(vecs)
        self._cache_timestamp = time.time()

    def _expand_graph(self, candidates: List[SearchResult], limit: int) -> List[SearchResult]:
        expanded = []
        seen = {c.node.id for c in candidates}
        seeds = candidates[:3]

        conn = self.db._get_conn()
        cursor = conn.cursor()

        try:
            for cand in seeds:
                cursor.execute("SELECT target_id FROM edges WHERE source_id = ? AND relationship = 'uses_type'", (cand.node.id,))
                type_targets = [row[0] for row in cursor.fetchall()]

                for target_id in type_targets:
                    if target_id.startswith("symbol:"):
                        type_name = target_id.split(":", 1)[1]
                        cursor.execute("SELECT id FROM nodes WHERE name = ? LIMIT 1", (type_name,))
                        row = cursor.fetchone()
                        if row:
                            nid = row[0]
                            if nid not in seen:
                                node = self.db.get_node(nid)
                                if node:
                                    expanded.append(SearchResult(node, cand.score * 0.4, f"defines-type:{type_name}"))
                                    seen.add(nid)

                symbol_id = f"symbol:{cand.node.name}"
                cursor.execute("SELECT source_id FROM edges WHERE target_id = ? AND relationship = 'calls' LIMIT ?", (symbol_id, limit))
                caller_ids = [row[0] for row in cursor.fetchall()]

                for cid in caller_ids:
                    if cid not in seen:
                        node = self.db.get_node(cid)
                        if node:
                            expanded.append(SearchResult(node, cand.score * 0.5, "caller"))
                            seen.add(cid)

        except Exception as e:
            logger.error(f"Graph traversal failed: {e}")
        finally:
            conn.close()

        return expanded

    def _rrf_fusion(self, results_lists: List[List[SearchResult]], k: int = 60) -> List[SearchResult]:
        scores = {}
        node_map = {}

        for r_list in results_lists:
            for rank, item in enumerate(r_list):
                nid = item.node.id
                if nid not in node_map:
                    node_map[nid] = item.node
                    scores[nid] = 0.0

                scores[nid] += 1.0 / (k + rank + 1)

        fused = []
        for nid, score in scores.items():
            fused.append(SearchResult(node_map[nid], score, "rrf-fusion"))

        fused.sort(key=lambda x: x.score, reverse=True)
        return fused

    async def _rerank(self, query: str, candidates: List[SearchResult]) -> List[SearchResult]:
        if not candidates:
            return []

        # Placeholder for CrossEncoder / TEI Reranker
        # For now, we use a simple Heuristic + LLM Rerank if enabled

        # 1. Heuristic Boost (Exact Match in path or content)
        for cand in candidates:
            if query.lower() in cand.node.name.lower():
                cand.score *= 1.2
            if query.lower() in cand.node.filepath.lower():
                cand.score *= 1.1

        # 2. LLM Rerank (Top 10)
        top_slice = candidates[:10]
        if not top_slice:
             return candidates

        try:
             reranked_slice = await asyncio.to_thread(self._llm_rerank, query, top_slice)
             # Combine
             seen = {c.node.id for c in reranked_slice}
             final = reranked_slice
             for c in candidates:
                 if c.node.id not in seen:
                     final.append(c)
             return final
        except Exception as e:
            logger.warning(f"Rerank failed: {e}")
            return candidates

    def _llm_rerank(self, query: str, candidates: List[SearchResult]) -> List[SearchResult]:
        items = []
        for i, c in enumerate(candidates):
            content_preview = c.node.content[:300].replace("\n", " ")
            items.append(f"[{i}] {c.node.filepath}: {content_preview}")

        prompt_items = "\n".join(items)

        system_prompt = (
            "You are a code retrieval expert. Rank the following code snippets based on their relevance to the user query.\n"
            "Return a JSON object with a list 'indices' containing the indices of the snippets in order of relevance.\n"
            "Example: {\"indices\": [2, 0, 1]}"
        )
        prompt = f"Query: {query}\n\nSnippets:\n{prompt_items}\n\nRank them."

        response = self.llm.generate_response(prompt, system_prompt=system_prompt, json_mode=True, temperature=0.0)

        try:
            data = json.loads(response)
            indices = data.get("indices", [])
        except json.JSONDecodeError:
            return candidates

        ranked_results = []

        for rank, idx in enumerate(indices):
            if isinstance(idx, int) and 0 <= idx < len(candidates):
                c = candidates[idx]
                # New score based on rank
                c.score = 100.0 - (rank * 5.0)
                c.reason = "llm-rerank"
                ranked_results.append(c)

        return ranked_results
