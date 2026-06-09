#!/usr/bin/env bash
# Deploy EmberHeart Reborn to funiserver.
#
# Pushes CODE ONLY and rebuilds the container. Three things are NEVER overwritten,
# so a deploy can't wipe your campaign or your art:
#   • data/                  — the live SQLite save (canonical on the server)
#   • frontend/gallery/*      — canon images you drop on the server (captions.json DOES sync)
#   • .env                    — the server's prod config
#
# Usage:  ./scripts/deploy.sh [--skip-tests]
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-funiserver}"
REMOTE_DIR="${REMOTE_DIR:-/mnt/user/appdata/emberheart-reborn}"
PORT="${REMOTE_PORT:-8000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "${1:-}" != "--skip-tests" ]]; then
  echo "→ running test suite (pass --skip-tests to bypass)"
  .venv/bin/python -m pytest -q
fi

echo "→ syncing source to ${REMOTE_HOST}:${REMOTE_DIR}  (save + gallery images protected)"
rsync -az --delete \
  --exclude 'data/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.DS_Store' \
  --include 'frontend/gallery/captions.json' \
  --include 'frontend/gallery/README.md' \
  --exclude 'frontend/gallery/*' \
  ./ "${REMOTE_HOST}:${REMOTE_DIR}/"

echo "→ building & restarting container"
ssh "${REMOTE_HOST}" "cd ${REMOTE_DIR} && docker compose up -d --build"

echo "→ waiting for health"
for _ in $(seq 1 20); do
  if ssh "${REMOTE_HOST}" "curl -fsS http://localhost:${PORT}/healthz >/dev/null 2>&1"; then
    echo "✓ deployed & healthy → http://${REMOTE_HOST}:${PORT}"
    exit 0
  fi
  sleep 2
done
echo "✗ health check timed out — ssh ${REMOTE_HOST} 'docker logs --tail 50 emberheart-reborn'" >&2
exit 1
