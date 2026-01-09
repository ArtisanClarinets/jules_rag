from typing import Dict, Any, List
import json
import os

class PerformanceAnalyzer:
    def __init__(self, log_path="performance.log"):
        self.log_path = log_path

    def log_session(self, query: str, validation_result: Dict, latency_ms: float):
        entry = {
            "query": query,
            "approved": validation_result.get("approved", False),
            "latency": latency_ms,
            "score": validation_result.get("relevance", {}).get("score", 0.0)
        }
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_average_score(self) -> float:
        total_score = 0.0
        count = 0
        if os.path.exists(self.log_path):
            with open(self.log_path, "r") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        total_score += data.get("score", 0)
                        count += 1
                    except:
                        pass
        return total_score / count if count > 0 else 0.0

class SelfImprovementEngine:
    def __init__(self):
        self.analyzer = PerformanceAnalyzer()

    def optimize(self) -> Dict[str, Any]:
        """
        Analyzes performance and returns configuration adjustments.
        In a full system, this would tune vector search weights or chunk sizes.
        """
        avg_score = self.analyzer.get_average_score()
        
        adjustments = {
            "vector_search_weight": 1.0,
            "keyword_search_weight": 1.0
        }
        
        # Simple feedback loop logic
        if avg_score < 0.7:
            # If relevance is low, boost keyword search (more exact)
            adjustments["keyword_search_weight"] = 1.2
            adjustments["vector_search_weight"] = 0.8
            status = "Adapting: Boosting keyword search due to low relevance."
        else:
            status = "System performing optimally."
            
        return {"adjustments": adjustments, "status": status}
