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
   ```
3. Access the UI at `https://localhost` (accept self-signed cert).

## Quickstart: Production

1. Run prerequisites script on Ubuntu:
   ```bash
   sudo make install-prereqs
   ```
2. Configure `.env` with secure passwords and domain.
3. Start the stack:
   ```bash
   make prod
   ```

## Architecture

See [docs/architecture.md](docs/architecture.md) for details.
