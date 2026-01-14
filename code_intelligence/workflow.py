import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .provider import LLMInterface
from .retrieval import RetrievalEngine, SearchResult

logger = logging.getLogger(__name__)

class BaseWorkflow:
    def __init__(self, retriever: RetrievalEngine):
        self.retriever = retriever
        self.llm = LLMInterface()

    def execute(self, query: str) -> Dict[str, Any]:
        raise NotImplementedError

class PlanWorkflow(BaseWorkflow):
    def execute(self, query: str) -> Dict[str, Any]:
        # 1. Broad Search
        # We assume the query describes the feature.
        logger.info(f"Executing Plan Workflow for: {query}")

        # Search with a higher K to get context
        results = self.retriever.retrieve(query, k=20)

        context_str = "\n\n".join([
            f"File: {r.node.filepath}\nContent:\n{r.node.content[:2000]}"
            for r in results
        ])

        # 2. Generate Plan
        system_prompt = (
            "You are a Senior Software Architect. Create a comprehensive, corporate-level feature implementation plan.\n"
            "The plan should include:\n"
            "1. Overview & Objectives\n"
            "2. Architectural Changes\n"
            "3. Step-by-Step Implementation Guide\n"
            "4. Testing Strategy\n"
            "5. Verification Steps\n"
            "\n"
            "Use the provided code context to make specific references to existing files and components."
        )

        prompt = (
            f"User Request: {query}\n\n"
            f"Codebase Context:\n{context_str}\n\n"
            "Generate the implementation plan in Markdown format."
        )

        plan_content = self.llm.generate_response(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=2000
        )

        return {
            "answer": plan_content,
            "citations": [
                {
                    "filepath": r.node.filepath,
                    "start_line": r.node.start_line,
                    "end_line": r.node.end_line
                } for r in results[:5]
            ]
        }

class DocsWorkflow(BaseWorkflow):
    def execute(self, query: str) -> Dict[str, Any]:
        logger.info(f"Executing Docs Workflow for: {query}")

        results = self.retriever.retrieve(query, k=15)

        context_str = "\n\n".join([
            f"File: {r.node.filepath}\nContent:\n{r.node.content[:3000]}"
            for r in results
        ])

        system_prompt = (
            "You are a Technical Writer. Write high-quality, user-friendly documentation based on the code provided.\n"
            "If the user asks for API docs, format it as such. If they ask for a User Guide, format accordingly.\n"
            "Ensure the documentation is accurate and reflects the actual code."
        )

        prompt = (
            f"User Request: {query}\n\n"
            f"Codebase Context:\n{context_str}\n\n"
            "Generate the documentation in Markdown format."
        )

        docs_content = self.llm.generate_response(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.2,
            max_tokens=2000
        )

        return {
            "answer": docs_content,
            "citations": [
                {
                    "filepath": r.node.filepath,
                    "start_line": r.node.start_line,
                    "end_line": r.node.end_line
                } for r in results[:5]
            ]
        }

class WorkflowEngine:
    def __init__(self, retriever: RetrievalEngine):
        self.retriever = retriever
        self.workflows = {
            "PLAN": PlanWorkflow(retriever),
            "DOCS": DocsWorkflow(retriever)
        }

    def run(self, workflow_type: str, query: str) -> Optional[Dict[str, Any]]:
        wf = self.workflows.get(workflow_type)
        if wf:
            return wf.execute(query)
        return None
