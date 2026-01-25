import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from code_intelligence.db import Database
from code_intelligence.indexing import FileIndexer
from code_intelligence.config import settings

class TestIndexingVerification(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test.db")
        self.db = Database(self.db_path)

        # Create dummy file
        self.src_dir = os.path.join(self.test_dir, "src")
        os.makedirs(self.src_dir)
        with open(os.path.join(self.src_dir, "main.py"), "w") as f:
            f.write("def hello():\n    print('world')\n")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("code_intelligence.indexing.EmbeddingsInterface")
    @patch("code_intelligence.indexing.LLMInterface")
    @patch("code_intelligence.ann_index.ANNIndex")
    def test_indexing_flow(self, MockANNIndex, MockLLM, MockEmbeddings):
        # Setup mocks
        mock_embed = MockEmbeddings.return_value
        def side_effect(texts):
            return [np.random.rand(1536).tolist() for _ in texts]
        mock_embed.embed.side_effect = side_effect
        mock_embed.client = True

        indexer = FileIndexer(self.db)

        # Run Indexing
        stats = indexer.index_workspace(self.test_dir, force=True)

        print(f"Stats: {stats}")
        self.assertGreater(stats["indexed"], 0)

        # Verify Nodes
        nodes = self.db.get_nodes_by_filepath("src/main.py")
        self.assertTrue(len(nodes) > 0)
        for node in nodes:
            self.assertEqual(node.filepath, "src/main.py")
            self.assertTrue(node.id.startswith("src/main.py:"))

        # Verify Embeddings
        # Use the actual model setting
        model = settings.embeddings_model
        chunks = self.db.get_chunks_without_embeddings(model)

        # Debug info if failure
        if len(chunks) > 0:
            print(f"Chunks without embeddings: {[n.id for n in chunks]}")
            # Check what models ARE in embeddings
            conn = self.db._get_conn()
            c = conn.cursor()
            c.execute("SELECT DISTINCT model FROM embeddings")
            print(f"Models in DB: {c.fetchall()}")
            conn.close()

        self.assertEqual(len(chunks), 0)

        self.assertTrue(mock_embed.embed.called)
        self.assertTrue(MockANNIndex.called)

if __name__ == "__main__":
    unittest.main()
