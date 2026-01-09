from typing import List, Optional
import hashlib
import numpy as np

from .embeddings import EmbeddingClient

class VectorStore:
    """
    Abstraction for Vector Storage.
    Defaults to in-memory cosine similarity using simple hashing if no embedding model is configured,
    or random vectors for testing.
    In production, this would connect to Qdrant/Pinecone.
    """
    def __init__(self, dimension: int = 384, embedder: Optional[EmbeddingClient] = None):
        self.embedder = embedder or EmbeddingClient()
        self.dimension = dimension
        self.vectors = {} # id -> np.array
        self.ids = []

    def add_vector(self, id: str, text: str):
        # Prefer real embeddings when configured.
        if self.embedder.enabled:
            try:
                vector = self.embedder.embed_text(text)
                self.dimension = int(vector.shape[0])
            except Exception:
                vector = self._mock_embedding(text)
        else:
            vector = self._mock_embedding(text)
        self.vectors[id] = vector
        if id not in self.ids:
            self.ids.append(id)

    def search(self, query: str, limit: int = 10) -> List[str]:
        if self.embedder.enabled:
            try:
                query_vector = self.embedder.embed_text(query)
            except Exception:
                query_vector = self._mock_embedding(query)
        else:
            query_vector = self._mock_embedding(query)
        
        scores = []
        for vid in self.ids:
            vec = self.vectors[vid]
            score = self._cosine_similarity(query_vector, vec)
            scores.append((vid, score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in scores[:limit]]

    def _mock_embedding(self, text: str) -> np.ndarray:
        # Implement Hashing Vectorizer (Feature Hashing)
        # This creates a deterministic, semantic-lite vector based on word counts.
        vector = np.zeros(self.dimension)
        words = text.lower().split()
        for word in words:
            # Python's built-in hash() is intentionally randomized between
            # processes. Use a stable hash so embeddings remain consistent
            # across runs.
            h = int.from_bytes(hashlib.md5(word.encode("utf-8")).digest()[:4], "little") % self.dimension
            # Increment that dimension (simple bag-of-words)
            vector[h] += 1.0
        
        # Normalize
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
            
        return vector

    def _cosine_similarity(self, v1: np.ndarray, v2: np.ndarray) -> float:
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return np.dot(v1, v2) / (norm1 * norm2)
