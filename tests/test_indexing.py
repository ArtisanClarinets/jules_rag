import unittest
import os
import tempfile
import shutil
from code_intelligence.db import Database
from code_intelligence.indexing import FileIndexer

class TestIndexing(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_dir = tempfile.mkdtemp()
        self.db_file = os.path.join(self.db_dir, "test.db")
        self.db = Database(self.db_file)
        self.indexer = FileIndexer(self.db)

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        shutil.rmtree(self.db_dir)

    def test_index_python_file(self):
        filepath = os.path.join(self.test_dir, "hello.py")
        with open(filepath, "w") as f:
            f.write("def hello():\n    print('world')\n    return True\n")

        stats = self.indexer.index_workspace(self.test_dir)
        # Note: Stats counts files, not nodes. 1 file processed.
        # But wait, logic is: if res: stats["indexed"] += 1.
        # And _process_file returns (should_index, entries).
        # should_index is True for new file.
        self.assertEqual(stats["indexed"], 1)

        nodes = self.db.get_nodes_by_filepath(filepath)
        self.assertTrue(len(nodes) >= 1) # File node + func node

        # Verify function extraction
        func_node = next((n for n in nodes if n.type == "function_definition"), None)
        self.assertIsNotNone(func_node)
        self.assertEqual(func_node.name, "hello")

    def test_incremental_indexing(self):
        filepath = os.path.join(self.test_dir, "test.py")
        with open(filepath, "w") as f:
            f.write("x = 1")

        self.indexer.index_workspace(self.test_dir)
        hash1 = self.db.get_file_hash(filepath)

        # Run again, should skip indexing but return stats
        stats = self.indexer.index_workspace(self.test_dir)
        self.assertEqual(stats["indexed"], 0)
        self.assertEqual(stats["skipped"], 1)

        # Modify
        with open(filepath, "w") as f:
            f.write("x = 2")

        stats = self.indexer.index_workspace(self.test_dir)
        self.assertEqual(stats["indexed"], 1)
        hash2 = self.db.get_file_hash(filepath)
        self.assertNotEqual(hash1, hash2)

    def test_ignore_rules(self):
        os.makedirs(os.path.join(self.test_dir, "node_modules"))
        with open(os.path.join(self.test_dir, "node_modules", "ignore.js"), "w") as f:
            f.write("x")

        # Add .gitignore
        with open(os.path.join(self.test_dir, ".gitignore"), "w") as f:
            f.write("node_modules/\n")

        stats = self.indexer.index_workspace(self.test_dir)
        # Should exclude node_modules.
        # But .gitignore itself is indexed.
        self.assertEqual(stats["indexed"], 1)

        # Verify ignore.js is NOT indexed
        nodes = self.db.get_nodes_by_filepath(os.path.join(self.test_dir, "node_modules", "ignore.js"))
        self.assertEqual(len(nodes), 0)

if __name__ == "__main__":
    unittest.main()
