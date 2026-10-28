#!/usr/bin/env bash
# Backup PostgreSQL database from the production compose stack.
# Output: ./backups/romana_YYYYMMDD_HHMMSS.sql.gz (relative to repo root).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BACKUP_DIR="./backups"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${BACKUP_DIR}/romana_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

docker compose -f deploy/docker-compose.prod.yml exec -T db pg_dump -U romana -d romana | gzip > "$OUT_FILE"

echo "Backup written: $OUT_FILE"
