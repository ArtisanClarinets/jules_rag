# Operations Runbook

## Deployment

### Prerequisites
- Ubuntu 22.04+
- Docker & Docker Compose
- `vm.max_map_count=262144` (for OpenSearch)

### Start Dev
```bash
make dev
```

### Start Prod
```bash
make prod
```

### GPU Support
To enable GPU embeddings:
1. Ensure NVIDIA drivers and container toolkit are installed.
2. Run:
   ```bash
   docker compose --profile gpu up -d
   ```

## Backups

Run `make backup` to dump Postgres and config.
Data volumes for Qdrant/MinIO should be backed up using volume snapshots or `rsync` if offline.

## Restore

Run `make restore <backup_dir>` to restore Postgres.

## Configuration

All configuration is managed via Environment Variables (`.env`) or the Admin UI.
UI settings take precedence for runtime parameters (like Model selection).
Infra settings (ports, volumes) are in `.env` and `docker-compose.yml`.
