from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from api.server import app, lifespan
import unittest
import logging

# Suppress log noise
logging.getLogger("api.server").setLevel(logging.CRITICAL)

class TestAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.json())

    @patch("api.server.indexer")
    def test_index_endpoint(self, mock_indexer):
        mock_indexer.index_workspace.return_value = {"indexed": 1}
        # Create a temp dir to satisfy validation
        import tempfile, os, shutil
        tmp = tempfile.mkdtemp()
        try:
            with TestClient(app) as client: # Context manager to trigger lifespan
                response = client.post("/index", json={"path": tmp})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "indexing_started")
        finally:
            shutil.rmtree(tmp)

    @patch("api.server.retriever")
    @patch("api.server.answer_engine")
    def test_query_endpoint(self, mock_answer, mock_retriever):
        mock_retriever.retrieve.return_value = []
        # The endpoint calls answer_engine.answer
        mock_answer.answer.return_value = {"answer": "42", "citations": []}

        # NOTE: lifespan context manager creates NEW instances of engines.
        # We need to ensure the mocked engines are used by the app.
        # In `lifespan` function in `api.server`, global variables are assigned.
        # We can mock `lifespan` or patch `api.server.retriever` AFTER lifespan execution.

        # Better approach: Patch the globals in `api.server` directly.
        # But lifespan overwrites them.

        # Let's mock the classes instantiated inside lifespan.
        with patch("api.server.Database"), \
             patch("api.server.FileIndexer"), \
             patch("api.server.RetrievalEngine") as MockRetriever, \
             patch("api.server.AnswerEngine") as MockAnswerEngine:

            mock_ret_instance = MockRetriever.return_value
            mock_ret_instance.retrieve.return_value = []

            mock_ans_instance = MockAnswerEngine.return_value
            mock_ans_instance.answer.return_value = {"answer": "42", "citations": []}

            with TestClient(app) as client:
                response = client.post("/query", json={"query": "meaning of life"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["answer"], "42")

    @patch("api.server.retriever")
    def test_mcp_search(self, mock_retriever):
        # Similar issue with lifespan. Use the same patching strategy.
        with patch("api.server.Database"), \
             patch("api.server.FileIndexer"), \
             patch("api.server.RetrievalEngine") as MockRetriever, \
             patch("api.server.AnswerEngine"):

            mock_ret_instance = MockRetriever.return_value
            mock_ret_instance.retrieve.return_value = []

            with TestClient(app) as client:
                response = client.post("/mcp", json={
                    "jsonrpc": "2.0",
                    "method": "rag.search",
                    "params": {"query": "test"},
                    "id": 1
                })
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertIn("result", data)
                self.assertEqual(data["id"], 1)

if __name__ == "__main__":
    unittest.main()
