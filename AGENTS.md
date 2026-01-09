# Code Intelligence Agent Guidelines

This repository contains the `advanced-code-intelligence` system, a local-first RAG solution for VS Code.

## Architecture

1.  **Backend (Python)**:
    *   `api/server.py`: FastAPI server exposing `/query`, `/index`, and `/mcp` endpoints.
    *   `code_intelligence/`: Core logic.
        *   `indexing.py`: AST-based chunking using `tree-sitter`.
        *   `db.py`: SQLite + FTS5 + Embeddings storage + Repo Map persistence.
        *   `retrieval.py`: Hybrid search (Sparse + Dense) with RRF fusion.
        *   `provider.py`: Unified LLM interface (OpenAI/OpenRouter).
        *   `config.py`: Configuration via `pydantic-settings`.

2.  **Extension (TypeScript)**:
    *   `vscode-extension/`: VS Code extension.
    *   Uses `onChatParticipant` to integrate with GitHub Copilot Chat.
    *   Provides commands to index the workspace.

## Configuration

The system is configured via environment variables (or `.env` file).

| Variable | Description | Default |
| :--- | :--- | :--- |
| `LLM_PROVIDER` | `openai`, `openrouter`, or `local` | `openai` |
| `LLM_API_KEY` | API Key for the provider | - |
| `LLM_MODEL` | Model name (e.g., `gpt-4o`, `anthropic/claude-3.5-sonnet`) | `gpt-4o-mini` |
| `DB_PATH` | Path to SQLite DB | `codegraph.db` |
| `RAG_MAX_FILE_MB` | Max file size to index (MB) | 2 |

## Security & Privacy (ASVS Baseline)

*   **Secrets**: Never commit `.env`. API keys are handled via `SecretStr` in Pydantic and not logged.
*   **Local-First**: By default, the server runs on `localhost`.
*   **Input Validation**: All API inputs are validated via Pydantic models.
*   **Sanitization**: FTS queries are sanitized to prevent injection/errors.
*   **Denylist**: `.gitignore` and `RAG_DENY_GLOBS` prevent sensitive files from being indexed.

## Development

1.  **Backend**:
    ```bash
    pip install -r requirements.txt
    python -m api.server
    ```

2.  **Extension**:
    Open `vscode-extension` folder in VS Code and press F5.

## Testing

Run unit tests:
```bash
python -m unittest discover tests
```

Run evaluation:
```bash
python -m eval.run --dataset eval/dataset.json
```

## MCP Support

The backend exposes a Model Context Protocol (MCP) compatible endpoint at `/mcp`. This allows external agents (like Claude Desktop or other MCP clients) to use the RAG system as a tool.

*   **Endpoint**: `POST /mcp`
*   **Protocol**: JSON-RPC 2.0 over HTTP (Simplified Transport)
*   **Tools**:
    *   `rag.search(query, k)`: Retrieve code chunks.
    *   `rag.explain(symbol)`: Generate explanations.

*Note: This is a "Tool Endpoint" implementation. Full MCP compliance usually requires SSE or Stdio transport.*
