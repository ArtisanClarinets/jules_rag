import unittest
from unittest.mock import MagicMock
from code_intelligence.answer import AnswerEngine, SearchResult, CodeNode

class TestAnswer(unittest.TestCase):
    def test_pack_context(self):
        engine = AnswerEngine(llm=MagicMock())

        node1 = CodeNode("1", "func", "a", "a.py", 1, 10, "content_a", {})
        node2 = CodeNode("2", "func", "b", "b.py", 1, 10, "content_b", {})

        results = [
            SearchResult(node1, 0.9),
            SearchResult(node2, 0.8)
        ]

        packed = engine._pack_context(results)
        self.assertIn("File: a.py", packed)
        self.assertIn("content_a", packed)
        self.assertIn("File: b.py", packed)

    def test_answer_flow(self):
        mock_llm = MagicMock()
        mock_llm.generate_response.return_value = "This is the answer."

        engine = AnswerEngine(llm=mock_llm)

        node = CodeNode("1", "func", "a", "a.py", 1, 10, "content_a", {})
        results = [SearchResult(node, 0.9)]

        output = engine.answer("How to do X?", results)

        self.assertEqual(output["answer"], "This is the answer.")
        self.assertEqual(len(output["citations"]), 1)
        self.assertEqual(output["citations"][0]["filepath"], "a.py")

if __name__ == "__main__":
    unittest.main()
