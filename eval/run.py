import json
import time
import statistics
import logging
from dataclasses import dataclass
from typing import List, Dict, Any

from code_intelligence.db import Database
from code_intelligence.retrieval import RetrievalEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("eval")

@dataclass
class EvalResult:
    query: str
    mrr: float
    recall_at_k: float
    latency_ms: float

class Evaluator:
    def __init__(self, db_path: str = "codegraph.db"):
        self.db = Database(db_path)
        self.retriever = RetrievalEngine(self.db)

    def run(self, dataset_path: str) -> Dict[str, Any]:
        with open(dataset_path, "r") as f:
            data = json.load(f)

        results = []

        for item in data:
            query = item["query"]
            expected_files = set(item["expected_files"])

            start = time.time()
            hits = self.retriever.retrieve(query, k=10)
            latency = (time.time() - start) * 1000

            # Metrics
            # Recall@10
            retrieved_files = {h.node.filepath for h in hits}
            intersection = expected_files.intersection(retrieved_files)
            recall = len(intersection) / len(expected_files) if expected_files else 0

            # MRR
            rank = 0
            for i, hit in enumerate(hits):
                if hit.node.filepath in expected_files:
                    rank = i + 1
                    break
            mrr = 1.0 / rank if rank > 0 else 0.0

            results.append(EvalResult(query, mrr, recall, latency))
            logger.info(f"Query: '{query}' | MRR: {mrr:.2f} | Recall: {recall:.2f} | {latency:.0f}ms")

        # Aggregate
        avg_mrr = statistics.mean(r.mrr for r in results)
        avg_recall = statistics.mean(r.recall_at_k for r in results)
        avg_latency = statistics.mean(r.latency_ms for r in results)

        return {
            "mrr": avg_mrr,
            "recall@10": avg_recall,
            "avg_latency_ms": avg_latency,
            "queries": len(results)
        }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--db", default="codegraph.db")
    args = parser.parse_args()

    ev = Evaluator(args.db)
    stats = ev.run(args.dataset)
    print(json.dumps(stats, indent=2))
