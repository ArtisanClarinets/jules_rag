import json
import logging
from typing import Dict, Any

from .provider import LLMInterface

logger = logging.getLogger(__name__)

class QueryClassifier:
    def __init__(self):
        self.llm = LLMInterface()

    def classify(self, query: str) -> Dict[str, Any]:
        system_prompt = (
            "You are a helpful assistant that classifies user queries related to software development.\n"
            "Categories:\n"
            "- PLAN: The user wants a feature implementation plan, architectural design, or step-by-step guide for a new feature.\n"
            "- DOCS: The user wants documentation (user guide, API docs, README) to be written, updated, or explained.\n"
            "- CODE: The user asks a specific coding question, debugging help, code explanation, or snippet generation.\n"
            "- GENERAL: Conversational, greetings, or out of scope.\n"
            "\n"
            "Return a JSON object with 'category' and 'reasoning'."
        )

        prompt = f"Query: {query}\n\nClassify this query."

        try:
            response = self.llm.generate_response(
                prompt=prompt,
                system_prompt=system_prompt,
                json_mode=True,
                temperature=0.1
            )
            return json.loads(response)
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return {"category": "CODE", "reasoning": "Fallback due to error."}
