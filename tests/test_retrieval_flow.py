import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import numpy as np
from code_intelligence.db import Database, CodeNode
from code_intelligence.retrieval import RetrievalEngine, SearchResult

class TestRetrievalVerification(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = MagicMock(spec=Database)
        # Mock search_nodes
        self.node1 = CodeNode(id="n1", type="func", name="foo", filepath="foo.py", start_line=1, end_line=10, content="def foo(): pass", properties={})
        self.node2 = CodeNode(id="n2", type="func", name="bar", filepath="bar.py", start_line=1, end_line=10, content="def bar(): pass", properties={})

        self.db.search_nodes.return_value = [self.node1]
        self.db.get_node.side_effect = lambda nid: self.node1 if nid == "n1" else (self.node2 if nid == "n2" else None)
        # Mock connection for refresh_cache
        conn = MagicMock()
        conn.cursor.return_value.fetchall.return_value = []
        self.db._get_conn.return_value = conn

    @patch("code_intelligence.retrieval.EmbeddingsInterface")
    @patch("code_intelligence.retrieval.LLMInterface")
    @patch("code_intelligence.retrieval.ANNIndex")
    async def test_retrieve_flow(self, MockANNIndex, MockLLM, MockEmbeddings):
        # Setup Embeddings Mock
        mock_embed = MockEmbeddings.return_value
        mock_embed.client = True
        # Return enough vectors for query + subquestions + hyde
        # retrieve calls embed with [query, subq..., hyde]
        # decomposition returns 1 subq, plus query, plus hyde = 3
        mock_embed.embed.return_value = [[0.1]*1536, [0.2]*1536, [0.3]*1536]

        # Setup LLM Mock
        mock_llm = MockLLM.return_value

        def llm_side_effect(prompt, **kwargs):
            if "Decompose" in prompt:
                return '{"questions": ["subq1"]}'
            if "hypothetical" in prompt:
                return "def hyde(): pass"
            if "Rank" in prompt:
                return '{"indices": [0, 1]}'
            return "{}"

        mock_llm.generate_response.side_effect = llm_side_effect

        retriever = RetrievalEngine(self.db)

        # Mock ANNIndex
        MockANNIndex.return_value.available = True
        MockANNIndex.return_value.index = MagicMock()
        # Dense search returns n2
        MockANNIndex.return_value.query.return_value = [("n2", 0.9)]

        # Run Retrieve
        results = await retriever.retrieve("test query")

        print(f"Results: {[r.node.id for r in results]}")
        self.assertTrue(len(results) >= 1)

        ids = [r.node.id for r in results]
        self.assertIn("n1", ids) # From sparse
        self.assertIn("n2", ids) # From dense

if __name__ == "__main__":
    unittest.main()
