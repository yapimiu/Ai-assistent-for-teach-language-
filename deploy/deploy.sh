#!/usr/bin/env bash
# One-command update of the production stack on the VPS.
# Usage: ./deploy/deploy.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

COMPOSE_FILE="deploy/docker-compose.prod.yml"

echo "==> Updating repository"
# Optional: pull the latest code. Remove if you deploy from a manually synced checkout.
git pull --ff-only

echo "==> Backing up database (recommended before every update)"
# Aborts the deploy if the backup fails (set -e).
./deploy/backup.sh

echo "==> Building images"
# Services are built from the repository (build: ..). For prebuilt images use:
#   docker compose -f "$COMPOSE_FILE" pull
docker compose -f "$COMPOSE_FILE" build --no-cache

echo "==> Starting stack"
docker compose -f "$COMPOSE_FILE" up -d

echo "==> Cleaning dangling images"
docker system prune -f

echo "==> Status"
docker compose -f "$COMPOSE_FILE" ps

echo "Deploy finished."
