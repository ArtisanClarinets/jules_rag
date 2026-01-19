import logging
import json
from typing import List, Dict, Any, Optional

from .providers import LLMInterface
from .retrieval import SearchResult, CodeNode
from .config import settings
from .safe_context import mask_secrets

logger = logging.getLogger(__name__)

class AnswerEngine:
    def __init__(self, llm: LLMInterface = None):
        self.llm = llm or LLMInterface()

    def answer(self, query: str, context: List[SearchResult]) -> Dict[str, Any]:
        """
        Generate an answer based on query and retrieved context.
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

        # Note: LLMInterface also applies masking, but we do it here for good measure
        # especially if logic changes later.
        response = self.llm.generate_response(full_prompt, system_prompt=system_prompt)

        return {
            "answer": response,
            "citations": [self._format_citation(r.node) for r in context]
        }

    def answer_stream(self, query: str, context: List[SearchResult]):
        prompt_context = self._pack_context(context)
        system_prompt = (
            "You are a senior software engineer helping a user in VS Code. "
            "Use the provided context to answer the user's question. "
            "Cite your sources using [file:start_line-end_line] format. "
            "If the context is insufficient, say so. "
            "Be concise and code-focused."
        )
        full_prompt = f"Question: {query}\n\nContext:\n{prompt_context}\n\nAnswer:"
        return self.llm.generate_stream(full_prompt, system_prompt=system_prompt)

    def _pack_context(self, results: List[SearchResult]) -> str:
        """Fit results into token budget."""
        packed = []
        current_tokens = 0
        max_tokens = settings.rag_max_tokens_context

        for res in results:
            content = res.node.content

            # Mask secrets in content before sending to LLM
            if settings.rag_redact_secrets:
                content = mask_secrets(content)

            # Rough token estimation: 4 chars / token
            estimated = len(content) / 4

            if current_tokens + estimated > max_tokens:
                break

            header = f"File: {res.node.filepath} ({res.node.start_line}-{res.node.end_line})"
            if res.node.next_route_path:
                header += f" [Route: {res.node.next_route_path}]"

            packed.append(f"--- {header} ---\n{content}\n")
            current_tokens += estimated + 20

        return "\n".join(packed)

    def _format_citation(self, node: CodeNode) -> Dict[str, Any]:
        return {
            "filepath": node.filepath,
            "start_line": node.start_line,
            "end_line": node.end_line,
            "id": node.id,
            "route": node.next_route_path,
            "segment": node.next_segment_type,
            "score": 0.0 # populated by caller usually if needed, but not available here directly
        }
