# Code Intelligence System - Security Checklist (OWASP ASVS Baseline)

## Architecture & Design
- [x] **Local-First Default**: System defaults to `localhost` binding.
- [x] **Secure Configuration**: Secrets loaded from environment, not hardcoded.
- [x] **Least Privilege**: File access limited to workspace root.

## Authentication & Access Control
- [ ] **API Authentication**: Currently reliance on local network trust. *Future: Add simple token auth for remote usage.*
- [x] **Secret Management**: API keys managed via `SecretStr` to prevent accidental logging.

## Input Validation
- [x] **Strong Typing**: Pydantic models validate all JSON payloads.
- [x] **Path Traversal Prevention**: Indexing restricted to sub-paths of workspace root.
- [x] **Query Sanitization**: FTS5 queries sanitized to prevent SQLite errors.

## Data Protection
- [x] **Privacy Controls**: Respects `.gitignore`. Supports `RAG_DENY_GLOBS`.
- [x] **Encryption at Rest**: Relies on filesystem permissions. *Future: SQLCipher support.*
- [x] **Encryption in Transit**: Recommended to use behind reverse proxy (Nginx/Traefik) with TLS if exposed remotely.

## Logging & Monitoring
- [x] **No Secrets in Logs**: Logging configured to avoid sensitive data.
- [x] **Structured Logging**: JSON-friendly logs (via libraries).
- [x] **Metrics**: Evaluation harness provides latency and quality metrics.
