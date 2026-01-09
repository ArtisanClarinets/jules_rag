import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import json
import time

import numpy as np
from rank_bm25 import BM25Okapi

from .db import Database, CodeNode
from .provider import EmbeddingsInterface, LLMInterface
from .config import settings

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

    def retrieve(self, query: str, k: int = 10) -> List[SearchResult]:
        """
        Execute hybrid retrieval pipeline:
        1. Query Rewriting (optional but recommended)
        2. Sparse Search (FTS/BM25)
        3. Dense Search (Embeddings)
        4. Fusion (RRF)
        5. Reranking
        """

        # 1. Query Expansion (simplified for now)
        # We could ask LLM to generate synonyms or sub-queries.
        queries = [query]

        all_results: Dict[str, SearchResult] = {}

        for q in queries:
            # 2. Sparse Search (FTS)
            sparse_nodes = self.db.search_nodes(q, limit=k*2)
            for i, node in enumerate(sparse_nodes):
                # Normalize rank to score
                score = 1.0 / (i + 1)
                if node.id not in all_results:
                    all_results[node.id] = SearchResult(node, score, "sparse")
                else:
                    all_results[node.id].score += score

            # 3. Dense Search (Vector)
            if self.embeddings.client:
                try:
                    q_vec = self.embeddings.embed([q])[0]
                    dense_hits = self._vector_search(q_vec, k=k*2)
                    for i, (node, score) in enumerate(dense_hits):
                        # Fusion: Add scores (RRF-style simple addition here, or max)
                        # RRF is usually 1 / (k + rank), we can just sum normalized scores.
                        if node.id not in all_results:
                            all_results[node.id] = SearchResult(node, score, "dense")
                        else:
                            all_results[node.id].score += score
                except Exception as e:
                    logger.warning(f"Dense search failed: {e}")

        # 4. Convert to list and sort
        candidates = list(all_results.values())
        candidates.sort(key=lambda x: x.score, reverse=True)
        candidates = candidates[:50] # Take top 50 for reranking

        # 5. Rerank
        reranked = self._rerank(query, candidates)

        return reranked[:k]

    def _refresh_cache_if_needed(self):
        """Reload embeddings if cache is stale or empty."""
        # Simple policy: refresh if empty or every 5 minutes.
        # Ideally, we check DB last modified.
        # For this exercise, we'll reload if empty.
        # To support incremental updates, we'd need a more complex sync.

        if self._embeddings_cache_matrix is not None:
             # Basic TTL check (e.g., 60s)
             if time.time() - self._cache_timestamp < 60:
                 return

        logger.info("Refeshing embeddings cache...")
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

    def _vector_search(self, vector: List[float], k: int) -> List[Tuple[CodeNode, float]]:
        """
        Naive vector search using cached matrix.
        """
        self._refresh_cache_if_needed()

        if self._embeddings_cache_matrix is None:
            return []

        q_vec = np.array(vector, dtype=np.float32)

        # Cosine similarity
        # A . B / (|A| * |B|)

        # Norms
        # Precompute matrix norms could be further optimization
        norm_matrix = np.linalg.norm(self._embeddings_cache_matrix, axis=1)
        norm_q = np.linalg.norm(q_vec)

        scores = np.dot(self._embeddings_cache_matrix, q_vec) / (norm_matrix * norm_q + 1e-9)

        # Top K
        # If fewer items than K, take all
        top_k = min(k, len(scores))
        top_indices = np.argpartition(scores, -top_k)[-top_k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        results = []
        for idx in top_indices:
            nid = self._embeddings_cache_ids[idx]
            node = self.db.get_node(nid)
            if node:
                results.append((node, float(scores[idx])))

        return results

    def _rerank(self, query: str, candidates: List[SearchResult]) -> List[SearchResult]:
        """
        Rerank using LLM or heuristic.
        LLM reranking is expensive but accurate.
        We can do a cheap 'keyword density' rerank or similar here as baseline.
        Or use a cross-encoder if we had torch installed.
        """
        # For now, return as is or slight adjustment
        # Maybe boost exact matches of query words in code content

        query_terms = set(query.lower().split())

        for cand in candidates:
            # Boost score if name matches query terms
            name_lower = cand.node.name.lower()
            if any(term in name_lower for term in query_terms):
                cand.score *= 1.2

            # Boost if content contains exact phrase
            if query in cand.node.content:
                cand.score *= 1.5

        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates
