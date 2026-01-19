#!/bin/bash
# scripts/restore.sh
if [ -z "$1" ]; then
  echo "Usage: ./restore.sh <backup_dir>"
  exit 1
fi

BACKUP_DIR=$1

echo "Restoring Postgres..."
cat $BACKUP_DIR/postgres.sql | docker exec -i vantus-postgres psql -U postgres

echo "Restore complete."
