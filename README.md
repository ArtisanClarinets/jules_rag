# Advanced Code Intelligence RAG System (Prototype)

## Overview
This project serves as a foundational prototype for a multi-layered RAG architecture. It implements the core AST-aware indexing for Python and outlines the agentic architecture. 

**Note**: This is a foundational implementation. It uses SQLite for persistence and supports **OpenAI or OpenRouter** for chat + embeddings.

## Directory Structure
- `code_intelligence/`: Core Python engine for indexing, retrieval, and validation.
- `vscode-extension/`: VS Code extension integration.
- `api/`: Backend API (Placeholder).

## Setup
1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run CLI:
   ```bash
   # Index the codebase
   python -m code_intelligence.cli index /path/to/codebase
   
   # Query via CLI
   python -m code_intelligence.cli query "How does authentication work?"
   ```

3. Run API Server (for VS Code Extension):
   ```bash
   python api/server.py
   ```

## LLM + Embeddings configuration (OpenAI or OpenRouter)

This repo supports OpenAI-compatible APIs via environment variables.

### OpenAI

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=...
export LLM_MODEL=gpt-4o-mini
export EMBEDDINGS_MODEL=text-embedding-3-small
```

### OpenRouter

```bash
export LLM_PROVIDER=openrouter
export OPENROUTER_API_KEY=...
export LLM_MODEL=openai/gpt-4o-mini
export EMBEDDINGS_MODEL=openai/text-embedding-3-small

# Optional attribution headers (recommended by OpenRouter)
export OPENROUTER_HTTP_REFERER=https://your.site
export OPENROUTER_X_TITLE="My VS Code RAG"
```

## Architecture
1. **Indexing Layer**: AST parser (Python) builds a `CodeGraph`.
2. **Retrieval Layer**: Orchestrator with semantic and syntactic agents.
3. **Validation Layer**: Council of Judges validates results.

### Recent improvements
- Hybrid retrieval: BM25 candidate generation + optional dense rerank (when embeddings are configured)
- Stored embeddings in SQLite (reused across runs)
- Stable hashing fallback (no Python hash randomization)
- Optional `.gitignore`-aware indexing (via `pathspec`) and default ignores

## Security Note
API keys are read from environment variables. For VS Code usage, store keys in VS Code SecretStorage.
