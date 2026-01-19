# Benchmarking

To run benchmarks:

1. Ingest a sample dataset (Code or Docs).
2. Use the `eval/run_eval.py` script (if ported) or the UI Benchmark tab.

## Metrics
- **Hit Rate**: % of queries with relevant result in Top K.
- **MRR**: Mean Reciprocal Rank.
- **Latency**: P50, P95, P99 for Embedding, Search, Rerank.
