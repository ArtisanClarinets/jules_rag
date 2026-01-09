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

    def test_retrieve_sparse_only(self):
        # Setup DB mocks
        node = CodeNode("1", "func", "test", "test.py", 1, 5, "def test(): pass", {})
        self.db.search_nodes.return_value = [node]
        self.retrieval.embeddings.client = None # Disable dense

        results = self.retrieval.retrieve("test", k=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].node.id, "1")
        self.assertEqual(results[0].reason, "sparse")

    def test_retrieve_dense_mock(self):
        # Setup DB for vector search (which accesses sqlite directly in impl)
        # We need to mock _vector_search method instead of DB internals for easier unit testing

        node = CodeNode("1", "func", "test", "test.py", 1, 5, "def test(): pass", {})
        with patch.object(self.retrieval, '_vector_search', return_value=[(node, 0.9)]):
            self.db.search_nodes.return_value = []

            results = self.retrieval.retrieve("test", k=1)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].node.id, "1")
            self.assertEqual(results[0].reason, "dense")

    def test_hybrid_fusion(self):
        node = CodeNode("1", "func", "test", "test.py", 1, 5, "def test(): pass", {})

        # Returns same node from both
        self.db.search_nodes.return_value = [node]
        with patch.object(self.retrieval, '_vector_search', return_value=[(node, 0.9)]):
            results = self.retrieval.retrieve("test", k=1)

            self.assertEqual(len(results), 1)
            # Score should be > 0.9 because of fusion
            self.assertTrue(results[0].score > 0.9)

if __name__ == "__main__":
    unittest.main()
