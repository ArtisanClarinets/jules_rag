from rank_bm25 import BM25Okapi
from .db import Database, CodeNode
from typing import List

import numpy as np

from .embeddings import EmbeddingClient

class SearchEngine:
    """Hybrid search over the indexed code.

    Stage 1: lexical BM25 for fast candidate generation
    Stage 2 (optional): dense rerank using stored embeddings

    Note: This is intentionally lightweight. For very large repos, you will
    eventually want an ANN index (HNSW/FAISS/Qdrant) for dense retrieval.
    """

    def __init__(self, db: Database, embedder: EmbeddingClient | None = None):
        self.db = db
        self.embedder = embedder or EmbeddingClient()
        self.refresh()

    def refresh(self):
        """Reload nodes and rebuild the BM25 index."""

        self.nodes = self.db.get_all_nodes()
        self.tokenized_corpus = [self._tokenize(node.content) for node in self.nodes]
        self.bm25 = BM25Okapi(self.tokenized_corpus) if self.tokenized_corpus else None

    def _tokenize(self, text: str) -> List[str]:
        import re
        # Simple regex tokenizer to handle punctuation
        return re.findall(r'\w+', text.lower())

    def search(self, query: str, limit: int = 10) -> List[CodeNode]:
        if not self.bm25:
            return []

        tokenized_query = self._tokenize(query)
        bm25_scores = self.bm25.get_scores(tokenized_query)

        # Candidate set: widen to give dense reranker room.
        cand_k = min(len(self.nodes), max(limit * 12, 50))
        cand_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:cand_k]
        candidates = [self.nodes[i] for i in cand_indices]

        if not self.embedder.enabled:
            return candidates[:limit]

        # Dense rerank candidates using embeddings stored in SQLite.
        model = self.embedder.cfg.model
        node_ids = [n.id for n in candidates]
        vecs = self.db.get_embeddings_for_nodes(node_ids, model=model)

        # Compute on-demand for missing embeddings (keeps first run usable).
        missing = [n for n in candidates if n.id not in vecs]
        if missing:
            texts = [m.content[:8000] for m in missing]  # cap huge file nodes
            try:
                new_vecs = self.embedder.embed_texts(texts)
                for n, v in zip(missing, new_vecs):
                    self.db.upsert_embedding(n.id, model=model, vector=v)
                    vecs[n.id] = v
            except Exception:
                # If embeddings fail, fall back to BM25.
                return candidates[:limit]

        qv = self.embedder.embed_text(query)
        qv = qv / (np.linalg.norm(qv) + 1e-8)

        def cos(a: np.ndarray, b: np.ndarray) -> float:
            b = b / (np.linalg.norm(b) + 1e-8)
            return float(np.dot(a, b))

        scored = []
        for idx, node in enumerate(candidates):
            dv = vecs.get(node.id)
            if dv is None:
                continue
            dense = cos(qv, dv)
            lexical = float(bm25_scores[cand_indices[idx]])
            # Simple combination: normalize lexical roughly by rank and add.
            scored.append((node, dense, lexical))

        # Rank by dense primarily; break ties with lexical.
        scored.sort(key=lambda t: (t[1], t[2]), reverse=True)
        return [t[0] for t in scored[:limit]]
