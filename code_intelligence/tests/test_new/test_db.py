import unittest
import os
from code_intelligence.db import Database, CodeNode
from code_intelligence.search import SearchEngine
from code_intelligence.agents import SemanticSearchAgent

class TestDB(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_graph.db"
        self.db = Database(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_add_and_get_node(self):
        node = CodeNode(
            id="test:1", type="function", name="test_func",
            filepath="test.py", start_line=1, end_line=10,
            content="def test_func(): pass", properties={}
        )
        self.db.add_node(node)
        retrieved = self.db.get_node("test:1")
        self.assertEqual(retrieved.name, "test_func")

    def test_search_engine(self):
        node1 = CodeNode("1", "func", "foo", "f.py", 1, 2, "def foo(): print('hello world')", {})
        node2 = CodeNode("2", "func", "bar", "f.py", 3, 4, "def bar(): print('goodbye universe')", {})
        node3 = CodeNode("3", "func", "baz", "f.py", 5, 6, "def baz(): print('extra padding for bm25')", {})
        self.db.add_node(node1)
        self.db.add_node(node2)
        self.db.add_node(node3)
        
        search = SearchEngine(self.db)
        results = search.search("universe", limit=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "bar")

if __name__ == '__main__':
    unittest.main()
