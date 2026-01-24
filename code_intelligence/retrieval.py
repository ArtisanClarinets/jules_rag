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

    def retrieve(self, query: str, k: int = 10) -> List[SearchResult]:
        k = k or settings.retrieval_k

        # 1. Sparse Search (FTS)
        all_results: Dict[str, SearchResult] = {}

        try:
            sparse_nodes = self.db.search_nodes(query, limit=k*2)
            for i, node in enumerate(sparse_nodes):
                score = 1.0 / (i + 1)
                all_results[node.id] = SearchResult(node, score, "sparse")
        except Exception as e:
            logger.error(f"Sparse search error: {e}")

        # 2. Dense Search (ANN / Brute)
        if self.embeddings.client:
            try:
                q_vec = self.embeddings.embed([query])[0]
                dense_hits = self._dense_search(q_vec, k=k*2)

                for node, score in dense_hits:
                    # Fusion (Simple CombSUM)
                    if node.id in all_results:
                        all_results[node.id].score += score
                        all_results[node.id].reason = "hybrid"
                    else:
                        all_results[node.id] = SearchResult(node, score, "dense")
            except Exception as e:
                logger.warning(f"Dense search failed: {e}")

        candidates = list(all_results.values())
        candidates.sort(key=lambda x: x.score, reverse=True)
        candidates = candidates[:50]

        # 3. Graph Expansion
        expanded = self._expand_graph(candidates, limit=5)
        existing_ids = {c.node.id for c in candidates}
        for ex in expanded:
            if ex.node.id not in existing_ids:
                candidates.append(ex)

        # Centrality Boosting
        self._boost_centrality(candidates)

        candidates.sort(key=lambda x: x.score, reverse=True)

        # 4. Rerank (LLM)
        reranked = self._rerank(query, candidates[:20])

        # 5. MMR Selection
        final_results = self._mmr(self.embeddings.embed([query])[0] if self.embeddings.client else None, reranked, k)

        return final_results

    def _dense_search(self, vector: List[float], k: int) -> List[Tuple[CodeNode, float]]:
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
                        results.append((node, score))
                return results

        return self._brute_force_search(vec_np, k)

    def _brute_force_search(self, vector: np.ndarray, k: int) -> List[Tuple[CodeNode, float]]:
        self._refresh_cache_if_needed()
        if self._embeddings_cache_matrix is None:
            return []

        # Ensure vector is normalized (OpenAI usually is)
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
                results.append((node, float(scores[idx])))
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
        """
        Deep Graph Traversal:
        1. Fetch definitions of types used in the function (uses_type).
        2. Fetch callers of the function (calls).
        """
        expanded = []
        seen = {c.node.id for c in candidates}
        seeds = candidates[:3]

        conn = self.db._get_conn()
        cursor = conn.cursor()

        try:
            for cand in seeds:
                # Hop 1: Definitions of types used (outgoing edges)
                cursor.execute("SELECT target_id FROM edges WHERE source_id = ? AND relationship = 'uses_type'", (cand.node.id,))
                type_targets = [row[0] for row in cursor.fetchall()]

                for target_id in type_targets:
                    if target_id.startswith("symbol:"):
                        type_name = target_id.split(":", 1)[1]
                        # Find node defining this type
                        cursor.execute("SELECT id FROM nodes WHERE name = ? LIMIT 1", (type_name,))
                        row = cursor.fetchone()
                        if row:
                            nid = row[0]
                            if nid not in seen:
                                node = self.db.get_node(nid)
                                if node:
                                    expanded.append(SearchResult(node, cand.score * 0.4, f"defines-type:{type_name}"))
                                    seen.add(nid)

                # Hop 2: Callers (incoming edges)
                # target_id = symbol:<name>
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

    def _boost_centrality(self, candidates: List[SearchResult]):
        """Boost score of nodes that are highly referenced (central)."""
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            for cand in candidates:
                symbol_id = f"symbol:{cand.node.name}"
                cursor.execute("SELECT COUNT(*) FROM edges WHERE target_id = ? AND relationship = 'calls'", (symbol_id,))
                count = cursor.fetchone()[0]
                if count > 0:
                    # Logarithmic boost
                    boost = 1.0 + (0.1 * np.log(1 + count))
                    cand.score *= boost
                    cand.reason += f" +centrality({count})"
        except Exception:
            pass
        finally:
            conn.close()

    def _mmr(self, query_vec: Optional[np.ndarray], candidates: List[SearchResult], k: int) -> List[SearchResult]:
        if query_vec is None or not candidates:
            return candidates[:k]

        lambda_param = settings.retrieval_mmr_lambda
        selected = []

        # Prepare vectors for candidates
        cand_vecs = []
        cand_map = {}

        if self._embeddings_cache_ids:
             id_to_idx = {nid: i for i, nid in enumerate(self._embeddings_cache_ids)}
             for c in candidates:
                 if c.node.id in id_to_idx:
                     cand_vecs.append(self._embeddings_cache_matrix[id_to_idx[c.node.id]])
                     cand_map[len(cand_vecs)-1] = c

        if not cand_vecs:
            return candidates[:k]

        cand_vecs = np.array(cand_vecs)

        # Ensure normalization
        norms = np.linalg.norm(cand_vecs, axis=1, keepdims=True)
        cand_vecs = cand_vecs / (norms + 1e-9)

        query_vec = query_vec / (np.linalg.norm(query_vec) + 1e-9)

        remaining_indices = list(range(len(cand_vecs)))

        while len(selected) < k and remaining_indices:
            best_score = -np.inf
            best_idx = -1

            for idx in remaining_indices:
                sim_q = np.dot(cand_vecs[idx], query_vec)

                if not selected:
                    max_sim_s = 0
                else:
                    sims_s = [np.dot(cand_vecs[idx], cand_vecs[s_idx]) for s_idx in selected]
                    max_sim_s = max(sims_s) if sims_s else 0

                mmr_score = lambda_param * sim_q - (1 - lambda_param) * max_sim_s

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = idx

            if best_idx != -1:
                selected.append(best_idx)
                remaining_indices.remove(best_idx)

        return [cand_map[i] for i in selected]

    def _rerank(self, query: str, candidates: List[SearchResult]) -> List[SearchResult]:
        # 1. Heuristic
        query_terms = set(query.lower().split())
        for cand in candidates:
            name_lower = cand.node.name.lower() if cand.node.name else ""
            if any(term in name_lower for term in query_terms):
                cand.score *= 1.2
            if query in cand.node.content:
                cand.score *= 1.5

        candidates.sort(key=lambda x: x.score, reverse=True)

        # 2. LLM Rerank
        top_candidates = candidates[:10]
        if not top_candidates:
            return candidates

        try:
            reranked = self._llm_rerank(query, top_candidates)
            return reranked + candidates[10:]
        except Exception as e:
            logger.warning(f"LLM Rerank failed: {e}")
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
        seen_indices = set()

        for idx in indices:
            if isinstance(idx, int) and 0 <= idx < len(candidates):
                c = candidates[idx]
                c.score = 50.0 - (len(ranked_results) * 1.0)
                c.reason = "llm-rerank"
                ranked_results.append(c)
                seen_indices.add(idx)

        for i, c in enumerate(candidates):
            if i not in seen_indices:
                ranked_results.append(c)

        return ranked_results
