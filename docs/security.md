# Security Checklist

## Authentication
- [x] JWT for UI session management.
- [x] API Keys (hashed) for programmatic access.
- [x] Passwords hashed with Bcrypt.

## Network
- [x] NGINX handles TLS termination.
- [x] Internal services (DB, Qdrant) are on isolated docker network, not exposed publicly.
- [x] CORS configured.

## Input Validation
- [x] Pydantic models for all API inputs.
- [x] File upload size limits (in NGINX/FastAPI).
- [x] Repo URL sanitization.

## Secrets
- [x] Secrets loaded from `.env`.
- [x] No hardcoded keys in source.
