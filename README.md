# Vantus Vector Platform

Vantus is a production-ready, self-hosted retrieval platform.

## Quickstart: Dev

1. Copy `.env.example` to `.env`
   ```bash
   cp .env.example .env
   ```
2. Start the stack (CPU profile)
   ```bash
   make dev
# Advanced Code Intelligence RAG System (Next.js Edition)

## Overview
A production-grade RAG engine optimized for **Next.js App Router** repositories. It features symbol-centric indexing, hybrid retrieval (BM25 + ANN + Graph), and a secure streaming API.

## Features
- **Next.js Awareness**: Understands App Router structure (`page`, `layout`, `route`), `use client/server` directives, and exports.
- **Hybrid Retrieval**: FTS5 BM25 + Embeddings (HNSW/Brute) + Graph Expansion + MMR.
- **Strict Citations**: Citations include file path, line ranges, and Next.js route metadata.
- **Streaming**: NDJSON streaming endpoint for real-time answers.
- **Security**: Secret masking, API key auth, rate limiting.

## Setup
1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   # Optional: pip install hnswlib for faster ANN
   ```

2. Configure `rag_config.yaml` (optional, or use env vars):
   ```yaml
   RETRIEVAL_K: 10
   RAG_REDACT_SECRETS: true
   LLM_PROVIDER: openai
   ```

3. Index a Repo:
   ```bash
   python scripts/index_repo.py --root /path/to/nextjs-repo --mode incremental
   ```
3. Access the UI at `https://localhost` (accept self-signed cert).

## Quickstart: Production

1. Run prerequisites script on Ubuntu:
4. Run Server:
   ```bash
   sudo make install-prereqs
   ```
2. Configure `.env` with secure passwords and domain.
3. Start the stack:
   ```bash
   make prod
   ```
   This will start:
   - Vantus API (Vector DB Manager) on `/api`
   - Vantus Web (Admin UI) on `/`
   - Code Intelligence RAG Engine on `/rag`

## Architecture

See [docs/architecture.md](docs/architecture.md) for details.
## API Usage

### Streaming Query
`POST /query_stream`
Headers: `Authorization: Bearer <key>`
Body: `{"query": "..."}`

Response (NDJSON):
```json
{"type": "retrieval_start", "query": "..."}
{"type": "retrieval_result", "items": [{"path": "...", "route": "/dashboard", ...}]}
{"type": "generation_chunk", "text": "..."}
{"type": "done", "answer": "...", "citations": [...]}
```

## Next.js Integration
See `examples/nextjs/app/api/rag/route.ts` for a Next.js Route Handler example that proxies requests to this engine.

## Evaluation
Run the evaluation harness:
```bash
python scripts/run_eval.py
```
This runs a set of golden questions (in `eval/golden_questions.jsonl`) and reports latency and recall metrics.

## Configuration Options
| Env Var | YAML Key | Default | Description |
|---------|----------|---------|-------------|
| `LLM_PROVIDER` | `llm_provider` | `openai` | `openai`, `openrouter`, or `local` |
| `RAG_API_KEYS` | `rag_api_keys` | `[]` | List of allowed API keys |
| `RAG_REDACT_SECRETS` | `rag_redact_secrets` | `true` | Mask secrets in prompts |
| `RETRIEVAL_ENABLE_ANN` | `retrieval_enable_ann` | `true` | Use HNSW if available |
