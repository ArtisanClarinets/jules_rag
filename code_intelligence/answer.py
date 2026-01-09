import logging
import json
from typing import List, Dict, Any, Optional

from .provider import LLMInterface
from .retrieval import SearchResult, CodeNode
from .config import settings

logger = logging.getLogger(__name__)

class AnswerEngine:
    def __init__(self, llm: LLMInterface = None):
        self.llm = llm or LLMInterface()

    def answer(self, query: str, context: List[SearchResult]) -> Dict[str, Any]:
        """
        Generate an answer based on query and retrieved context.
        Includes verification step (optional).
        """

        # 1. Prepare Context
        prompt_context = self._pack_context(context)

        # 2. Draft Answer
        system_prompt = (
            "You are a senior software engineer helping a user in VS Code. "
            "Use the provided context to answer the user's question. "
            "Cite your sources using [file:start_line-end_line] format. "
            "If the context is insufficient, say so. "
            "Be concise and code-focused."
        )

        full_prompt = f"Question: {query}\n\nContext:\n{prompt_context}\n\nAnswer:"

        response = self.llm.generate_response(full_prompt, system_prompt=system_prompt)

        # 3. Verify (Lightweight "Council of Judges")
        # In a real "Fortune 500" system, we might have a separate LLM call here
        # to grade the answer's groundedness.
        # For this implementation, we'll do a simple self-reflection check if configured.

        # For now, just return the response.
        return {
            "answer": response,
            "citations": [self._format_citation(r.node) for r in context]
        }

    def _pack_context(self, results: List[SearchResult]) -> str:
        """Fit results into token budget."""
        packed = []
        current_tokens = 0
        max_tokens = settings.rag_max_tokens_context

        for res in results:
            # Rough token estimation: 4 chars / token
            content = res.node.content
            estimated = len(content) / 4

            if current_tokens + estimated > max_tokens:
                break

            header = f"File: {res.node.filepath} ({res.node.start_line}-{res.node.end_line})"
            packed.append(f"--- {header} ---\n{content}\n")
            current_tokens += estimated + 20 # Header overhead

        return "\n".join(packed)

    def _format_citation(self, node: CodeNode) -> Dict[str, Any]:
        return {
            "filepath": node.filepath,
            "start_line": node.start_line,
            "end_line": node.end_line,
            "id": node.id
        }
