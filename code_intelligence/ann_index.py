import os
import logging
import json
import numpy as np
from typing import List, Tuple, Dict, Optional

logger = logging.getLogger(__name__)

class ANNIndex:
    def __init__(self, index_path: str, dim: int = 1536):
        self.index_path = index_path
        self.dim = dim
        self.index = None
        self.id_map: Dict[int, str] = {}

        self.available = False
        try:
            import hnswlib
            self.hnswlib = hnswlib
            self.available = True
        except ImportError:
            logger.warning("hnswlib not installed. ANN indexing disabled.")

    def build(self, vectors: np.ndarray, ids: List[str]):
        """
        Build HNSW index from vectors.
        vectors: (N, dim) float32 array
        ids: list of string node IDs
        """
        if not self.available:
            return

        num_elements = len(ids)
        if num_elements == 0:
            return

        logger.info(f"Building ANN index for {num_elements} vectors...")

        # Initialize HNSW index
        # 'cosine' metric in hnswlib is usually 1 - cosine_similarity for normalized vectors
        p = self.hnswlib.Index(space='cosine', dim=self.dim)
        p.init_index(max_elements=num_elements, ef_construction=200, M=16)

        # Add items
        p.add_items(vectors, np.arange(num_elements))

        p.set_ef(50) # Query time accuracy
        self.index = p
        self.id_map = {i: nid for i, nid in enumerate(ids)}

        self.save()

    def query(self, vector: np.ndarray, k: int = 10) -> List[Tuple[str, float]]:
        if not self.available or self.index is None:
            return []

        # Reshape if 1D
        if vector.ndim == 1:
            vector = vector.reshape(1, -1)

        labels, distances = self.index.knn_query(vector, k=k)

        results = []
        for label, dist in zip(labels[0], distances[0]):
             nid = self.id_map.get(int(label))
             if nid:
                 # Convert distance to similarity score
                 # hnswlib cosine distance = 1 - dot(u, v) (if normalized)
                 score = 1.0 - float(dist)
                 results.append((nid, score))
        return results

    def save(self):
        if not self.index:
            return
        try:
            os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
            self.index.save_index(self.index_path)
            with open(self.index_path + ".map", "w", encoding="utf-8") as f:
                 # If self.id_map has non-string keys (such as int), convert them to strings for JSON compatibility
                 json.dump({str(k): v for k, v in self.id_map.items()}, f)
            logger.info("Saved ANN index.")
        except Exception as e:
            logger.error(f"Failed to save ANN index: {e}")

    def load(self) -> bool:
        if not self.available:
            return False

        if not os.path.exists(self.index_path) or not os.path.exists(self.index_path + ".map"):
            return False

        try:
            with open(self.index_path + ".map", "r", encoding="utf-8") as f:
                # Load id_map from JSON and convert string keys back to int
                self.id_map = {int(k): v for k, v in json.load(f).items()}

            p = self.hnswlib.Index(space='cosine', dim=self.dim)
            p.load_index(self.index_path, max_elements=len(self.id_map))
            p.set_ef(50)
            self.index = p
            logger.info(f"Loaded ANN index with {len(self.id_map)} elements.")
            return True
        except Exception as e:
            logger.error(f"Failed to load ANN index: {e}")
            return False
