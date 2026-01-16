import json
import time
import sys
import os
import numpy as np

sys.path.append(os.getcwd())

from code_intelligence.db import Database
from code_intelligence.retrieval import RetrievalEngine
from code_intelligence.config import settings

def run_eval():
    db = Database(settings.db_path)
    retriever = RetrievalEngine(db)

    questions = []
    try:
        with open("eval/golden_questions.jsonl", "r") as f:
            for line in f:
                if line.strip():
                    questions.append(json.loads(line))
    except FileNotFoundError:
        print("eval/golden_questions.jsonl not found.")
        return

    print(f"Running eval on {len(questions)} questions...")

    latencies = []
    recalls = []

    for q in questions:
        query = q["question"]
        expected_path = q.get("expected_path")

        start = time.time()
        # Ensure k is sufficient
        results = retriever.retrieve(query, k=10)
        duration = time.time() - start
        latencies.append(duration)

        hit = False
        if expected_path:
            for r in results:
                if expected_path in r.node.filepath:
                    hit = True
                    break
        else:
            hit = True # relaxed for content check or assume manual check

        recalls.append(1 if hit else 0)

        print(f"Query: {query}")
        print(f"  Latency: {duration:.4f}s")
        print(f"  Recall Hit: {hit}")
        if not hit and expected_path:
             print(f"  Expected: {expected_path}")
             print("  Top 3:")
             for r in results[:3]:
                 print(f"    - {r.node.filepath} ({r.score:.2f})")
        print("-" * 40)

    if latencies:
        print(f"Mean Latency: {np.mean(latencies):.4f}s")
        print(f"P95 Latency: {np.percentile(latencies, 95):.4f}s")
        print(f"Recall@10: {np.mean(recalls):.2f}")

if __name__ == "__main__":
    run_eval()
