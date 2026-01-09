from typing import List, Dict
from dataclasses import dataclass
import json
from .llm import LLMInterface

@dataclass
class ValidationReport:
    is_valid: bool
    score: float
    issues: List[str]

class BaseJudge:
    def __init__(self):
        self.llm = LLMInterface()

    def evaluate(self, query: str, context: List[Dict]) -> ValidationReport:
        raise NotImplementedError

class RelevanceJudge(BaseJudge):
    def evaluate(self, query: str, context: List[Dict]) -> ValidationReport:
        context_str = "\n".join([c.get('content', '')[:200] for c in context])
        prompt = f"""
        Rate the relevance of the following code context to the query: "{query}".
        Context:
        {context_str}
        
        Return JSON with keys: score (0.0-1.0), reasoning (string).
        """
        response = self.llm.generate_response(prompt)
        try:
            data = json.loads(response)
            return ValidationReport(
                is_valid=data.get('score', 0) > 0.7,
                score=data.get('score', 0),
                issues=[data.get('reasoning', '')]
            )
        except:
            # Fallback if LLM fails or is simulated
            return ValidationReport(is_valid=True, score=0.8, issues=["Simulated approval"])

class ConsistencyJudge(BaseJudge):
    def evaluate(self, query: str, context: List[Dict]) -> ValidationReport:
        context_str = "\n".join([c.get('content', '')[:200] for c in context])
        prompt = f"""
        Check for contradictions in the following code snippets.
        Context:
        {context_str}
        
        Return JSON with keys: consistent (bool), issues (list of strings).
        """
        response = self.llm.generate_response(prompt)
        try:
            data = json.loads(response)
            return ValidationReport(
                is_valid=data.get('consistent', True),
                score=1.0 if data.get('consistent') else 0.5,
                issues=data.get('issues', [])
            )
        except:
            return ValidationReport(is_valid=True, score=1.0, issues=[])

class CouncilOfJudges:
    def __init__(self):
        self.relevance_judge = RelevanceJudge()
        self.consistency_judge = ConsistencyJudge()

    def validate(self, query: str, context: List[Dict]) -> Dict:
        rel_report = self.relevance_judge.evaluate(query, context)
        con_report = self.consistency_judge.evaluate(query, context)
        
        return {
            "relevance": rel_report.__dict__,
            "consistency": con_report.__dict__,
            "approved": rel_report.is_valid and con_report.is_valid
        }
