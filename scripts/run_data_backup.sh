#!/usr/bin/env bash
# Backup MongoDB, Redis, and Qdrant (vector DB) into project data_backup directory.
# Usage: from project root, ./scripts/run_data_backup.sh
# Requires: docker compose, curl. Optional: jq (for Qdrant snapshot name parsing).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_ROOT="${PROJECT_ROOT}/data_backup"
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${BACKUP_ROOT}/${TS}"
QDRANT_HOST="${QDRANT_BACKUP_HOST:-http://localhost:6333}"
COMPOSE_CMD="docker compose"
if ! docker compose version &>/dev/null; then
  COMPOSE_CMD="docker-compose"
fi

cd "$PROJECT_ROOT"
mkdir -p "$BACKUP_DIR"/{mongodb,redis,qdrant}

echo "[backup] Started at $(date -Iseconds) → ${BACKUP_DIR}"

# --- MongoDB (database: chat) ---
echo "[backup] MongoDB (chat)..."
if $COMPOSE_CMD exec -T mongodb mongodump --db=chat --archive &>"${BACKUP_DIR}/mongodb/chat.archive"; then
  echo "[backup] MongoDB OK → mongodb/chat.archive"
else
  echo "[backup] MongoDB failed (container may be down)" >&2
  rm -f "${BACKUP_DIR}/mongodb/chat.archive"
fi

# --- Redis ---
echo "[backup] Redis..."
if $COMPOSE_CMD exec -T redis redis-cli SAVE 2>/dev/null; then
  $COMPOSE_CMD cp redis:/data/dump.rdb "${BACKUP_DIR}/redis/dump.rdb" 2>/dev/null && echo "[backup] Redis OK → redis/dump.rdb" || echo "[backup] Redis copy failed" >&2
else
  echo "[backup] Redis SAVE failed (container may be down)" >&2
fi

# --- Qdrant (vector DB) ---
echo "[backup] Qdrant..."
QDRANT_SNAPSHOT_NAME=""
if command -v jq &>/dev/null; then
  QDRANT_SNAPSHOT_NAME=$(curl -s -X POST "${QDRANT_HOST}/snapshots?wait=true" | jq -r '.result.name // empty')
else
  QDRANT_SNAPSHOT_NAME=$(curl -s -X POST "${QDRANT_HOST}/snapshots?wait=true" | grep -o '"name":"[^"]*"' | head -1 | sed 's/"name":"//;s/"//')
fi
if [ -n "$QDRANT_SNAPSHOT_NAME" ]; then
  if curl -s "${QDRANT_HOST}/snapshots/${QDRANT_SNAPSHOT_NAME}" -o "${BACKUP_DIR}/qdrant/full.snapshot"; then
    echo "[backup] Qdrant OK → qdrant/full.snapshot"
  else
    echo "[backup] Qdrant download failed" >&2
  fi
else
  echo "[backup] Qdrant snapshot creation failed (Qdrant may be down or no data)" >&2
fi

echo "[backup] Done at $(date -Iseconds). Backup in: ${BACKUP_DIR}"
echo "${BACKUP_DIR}"
