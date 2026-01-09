import unittest
import os
import sqlite3
import tempfile
from code_intelligence.db import Database, CodeNode

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        self.db = Database(self.temp_db.name)

    def tearDown(self):
        os.unlink(self.temp_db.name)

    def test_add_and_get_node(self):
        node = CodeNode(
            id="test1",
            type="function",
            name="test_func",
            filepath="test.py",
            start_line=1,
            end_line=5,
            content="def test_func(): pass",
            properties={"lang": "python"}
        )
        self.db.add_node(node)
        retrieved = self.db.get_node("test1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "test_func")
        self.assertEqual(retrieved.properties["lang"], "python")

    def test_fts_search(self):
        node1 = CodeNode("1", "func", "alpha", "a.py", 1, 2, "function alpha does stuff", {})
        node2 = CodeNode("2", "func", "beta", "b.py", 1, 2, "function beta does other stuff", {})
        self.db.add_node(node1)
        self.db.add_node(node2)

        results = self.db.search_nodes("alpha")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "1")

        results = self.db.search_nodes("stuff")
        self.assertEqual(len(results), 2)

    def test_delete_nodes_by_filepath(self):
        node = CodeNode("1", "func", "alpha", "a.py", 1, 2, "content", {})
        self.db.add_node(node)
        self.db.set_file_hash("a.py", "hash123")

        self.assertIsNotNone(self.db.get_node("1"))
        self.assertEqual(self.db.get_file_hash("a.py"), "hash123")

        self.db.delete_nodes_by_filepath("a.py")
        self.assertIsNone(self.db.get_node("1"))
        # File hash should arguably remain if we want to track that it was deleted,
        # but current impl doesn't auto-delete hash.
        # Actually, if we delete nodes, we might want to re-index, so hash handling depends on logic.
        # But `delete_nodes_by_filepath` explicitly removes nodes, embeddings, edges, fts.

    def test_embeddings(self):
        import numpy as np
        vec = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        node = CodeNode("1", "func", "alpha", "a.py", 1, 2, "content", {})
        self.db.add_node(node)
        self.db.upsert_embedding("1", "model-x", vec)

        retrieved = self.db.get_embedding("1", "model-x")
        np.testing.assert_array_almost_equal(vec, retrieved)

if __name__ == "__main__":
    unittest.main()
