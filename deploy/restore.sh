#!/usr/bin/env bash
# Restore PostgreSQL database from a gzipped SQL backup.
# Usage: ./deploy/restore.sh backups/romana_YYYYMMDD_HHMMSS.sql.gz
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <backup_file.sql.gz>" >&2
  exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Error: backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

gunzip < "$BACKUP_FILE" | docker compose -f deploy/docker-compose.prod.yml exec -T db psql -U romana -d romana

echo "Restore finished from: $BACKUP_FILE"
