#!/usr/bin/env bash
# Restore MongoDB, Redis, and Qdrant from a backup produced by ./scripts/run_data_backup.sh
#
# Usage:
#   ./scripts/restore_data_backup.sh /absolute/or/relative/path/to/data_backup/<timestamp>
#
# Notes:
# - Mongo restore replaces data in the `chat` database via --drop.
# - Redis restore requires restarting the redis container so it loads dump.rdb.
# - Qdrant restore uses the snapshot recovery endpoint (requires Qdrant running).
#
# Requirements: docker compose, curl
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

COMPOSE_CMD="docker compose"
if ! docker compose version &>/dev/null; then
  COMPOSE_CMD="docker-compose"
fi

BACKUP_DIR="${1:-}"
if [ -z "$BACKUP_DIR" ]; then
  echo "Usage: $0 <backup_dir>" >&2
  exit 2
fi

if [ ! -d "$BACKUP_DIR" ]; then
  echo "[restore] Backup dir not found: $BACKUP_DIR" >&2
  exit 2
fi

BACKUP_DIR="$(cd "$BACKUP_DIR" && pwd)"
MONGO_ARCHIVE="${BACKUP_DIR}/mongodb/chat.archive"
REDIS_RDB="${BACKUP_DIR}/redis/dump.rdb"
QDRANT_SNAPSHOT="${BACKUP_DIR}/qdrant/full.snapshot"

QDRANT_HOST="${QDRANT_BACKUP_HOST:-http://localhost:6333}"

cd "$PROJECT_ROOT"

echo "[restore] Started at $(date -Iseconds) ← ${BACKUP_DIR}"

# --- MongoDB ---
if [ -f "$MONGO_ARCHIVE" ]; then
  echo "[restore] MongoDB (chat) from mongodb/chat.archive..."
  $COMPOSE_CMD exec -T mongodb mongorestore --drop --db=chat --archive <"$MONGO_ARCHIVE"
  echo "[restore] MongoDB OK"
else
  echo "[restore] MongoDB archive missing: $MONGO_ARCHIVE" >&2
fi

# --- Redis ---
if [ -f "$REDIS_RDB" ]; then
  echo "[restore] Redis from redis/dump.rdb..."
  # Copy RDB into container data dir and restart so Redis loads it.
  $COMPOSE_CMD cp "$REDIS_RDB" redis:/data/dump.rdb
  $COMPOSE_CMD restart redis >/dev/null
  echo "[restore] Redis OK (container restarted)"
else
  echo "[restore] Redis dump missing: $REDIS_RDB" >&2
fi

# --- Qdrant ---
if [ -f "$QDRANT_SNAPSHOT" ]; then
  echo "[restore] Qdrant from qdrant/full.snapshot..."
  # Qdrant snapshot restore is version-dependent and can be collection-scoped.
  # We keep this step best-effort and non-fatal so Mongo/Redis restores still succeed.
  echo "[restore] Qdrant restore is best-effort; attempting API-based recover..."
  if curl -fsS -X POST "${QDRANT_HOST}/snapshots/recover?wait=true" -H 'Content-Type: application/octet-stream' --data-binary @"$QDRANT_SNAPSHOT" >/dev/null; then
    echo "[restore] Qdrant OK"
  else
    echo "[restore] Qdrant restore skipped/failed (API/version may differ). You can restore manually via Qdrant UI/API." >&2
  fi
else
  echo "[restore] Qdrant snapshot missing: $QDRANT_SNAPSHOT" >&2
fi

echo "[restore] Done at $(date -Iseconds)"

