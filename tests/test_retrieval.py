import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from code_intelligence.db import Database, CodeNode
from code_intelligence.retrieval import RetrievalEngine, SearchResult

class TestRetrieval(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock(spec=Database)
        self.retrieval = RetrievalEngine(self.db)
        # Mock embeddings to avoid API calls
        self.retrieval.embeddings = MagicMock()
        self.retrieval.embeddings.client = True # pretend it's connected
        self.retrieval.embeddings.embed.return_value = [[0.1, 0.2, 0.3]]
        # Mock ANN
        self.retrieval.ann_index = MagicMock()
        self.retrieval.ann_index.available = False

    def test_retrieve_sparse_only(self):
        # Setup DB mocks
        node = CodeNode("1", "func", "test", "test.py", 1, 5, "def test(): pass", {})
        self.db.search_nodes.return_value = [node]
        self.retrieval.embeddings.client = None # Disable dense

        results = self.retrieval.retrieve("test", k=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].node.id, "1")
        # Reason might be sparse or llm-rerank depending on rerank
        self.assertIn(results[0].reason, ["sparse", "llm-rerank"])

    def test_retrieve_dense_mock(self):
        # Mock _dense_search
        node = CodeNode("1", "func", "test", "test.py", 1, 5, "def test(): pass", {})
        with patch.object(self.retrieval, '_dense_search', return_value=[(node, 0.9)]):
            self.db.search_nodes.return_value = []

            results = self.retrieval.retrieve("test", k=1)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].node.id, "1")
            self.assertIn(results[0].reason, ["dense", "llm-rerank"])

    def test_hybrid_fusion(self):
        node = CodeNode("1", "func", "test", "test.py", 1, 5, "def test(): pass", {})

        # Returns same node from both
        self.db.search_nodes.return_value = [node]
        with patch.object(self.retrieval, '_dense_search', return_value=[(node, 0.9)]):
            results = self.retrieval.retrieve("test", k=1)

            self.assertEqual(len(results), 1)
            # Score should be > 0.9 because of fusion (if not reranked) OR high if reranked (50.0)
            self.assertTrue(results[0].score > 0.9)

if __name__ == "__main__":
    unittest.main()
