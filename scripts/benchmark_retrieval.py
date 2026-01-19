import time
import sys
import os
import argparse
import numpy as np
from code_intelligence.db import Database
from code_intelligence.retrieval import RetrievalEngine
from code_intelligence.config import settings

def benchmark(query: str, k: int):
    print(f"Initializing DB from {settings.db_path}...")
    db = Database(settings.db_path)
    engine = RetrievalEngine(db)

    start = time.time()
    results = engine.retrieve(query, k=k)
    duration = time.time() - start

    print(f"Query: '{query}'")
    print(f"Time: {duration:.4f}s")
    print(f"Found {len(results)} results:")
    for i, res in enumerate(results):
        print(f"[{i}] {res.score:.2f} ({res.reason}) {res.node.filepath}:{res.node.start_line} - {res.node.name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("query", type=str)
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()

    benchmark(args.query, args.k)
