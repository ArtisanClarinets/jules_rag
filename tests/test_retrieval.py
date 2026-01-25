import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import numpy as np
from code_intelligence.db import Database, CodeNode
from code_intelligence.retrieval import RetrievalEngine, SearchResult

class TestRetrieval(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = MagicMock(spec=Database)
        # Mock connection context for refresh_cache
        conn = MagicMock()
        conn.cursor.return_value.fetchall.return_value = []
        self.db._get_conn.return_value = conn

        self.retrieval = RetrievalEngine(self.db)
        # Mock embeddings to avoid API calls
        self.retrieval.embeddings = MagicMock()
        self.retrieval.embeddings.client = True
        # For async retrieve, embed is called in to_thread, so standard mock works if it returns list
        self.retrieval.embeddings.embed.return_value = [[0.1]*1536, [0.1]*1536, [0.1]*1536] # query, sub, hyde

        # Mock ANN
        self.retrieval.ann_index = MagicMock()
        self.retrieval.ann_index.available = False

        # Mock LLM
        self.retrieval.llm = MagicMock()
        self.retrieval.llm.generate_response.return_value = "{}" # empty JSON

    async def test_retrieve_sparse_only(self):
        # Setup DB mocks
        node = CodeNode(id="1", type="func", name="test", filepath="test.py", start_line=1, end_line=5, content="def test(): pass", properties={})
        self.db.search_nodes.return_value = [node]
        self.retrieval.embeddings.client = None # Disable dense

        results = await self.retrieval.retrieve("test", k=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].node.id, "1")
        self.assertIn(results[0].reason, ["sparse", "rrf-fusion", "llm-rerank"])

    async def test_retrieve_dense_mock(self):
        # Mock _dense_search
        node = CodeNode(id="1", type="func", name="test", filepath="test.py", start_line=1, end_line=5, content="def test(): pass", properties={})

        # _dense_search now returns List[SearchResult]
        dense_results = [SearchResult(node, 0.9, "dense")]

        # Since _dense_search is called via to_thread(self._dense_search, ...), patching it on instance works
        with patch.object(self.retrieval, '_dense_search', return_value=dense_results):
            self.db.search_nodes.return_value = []

            results = await self.retrieval.retrieve("test", k=1)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].node.id, "1")

    async def test_hybrid_fusion(self):
        node = CodeNode(id="1", type="func", name="test", filepath="test.py", start_line=1, end_line=5, content="def test(): pass", properties={})

        # Returns same node from both
        self.db.search_nodes.return_value = [node]
        dense_results = [SearchResult(node, 0.9, "dense")]

        with patch.object(self.retrieval, '_dense_search', return_value=dense_results):
            results = await self.retrieval.retrieve("test", k=1)

            self.assertEqual(len(results), 1)
            # RRF fusion
            self.assertTrue(results[0].score > 0.0)

if __name__ == "__main__":
    unittest.main()
