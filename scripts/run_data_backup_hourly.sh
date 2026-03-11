#!/usr/bin/env bash
# Run data backup every hour. Use for cron or long-running process.
# Usage: ./scripts/run_data_backup_hourly.sh
# Cron (run at minute 0 every hour): 0 * * * * /path/to/zyon_ai_ticketing/scripts/run_data_backup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/run_data_backup.sh"
INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-3600}"

while true; do
  echo "=== Hourly backup at $(date -Iseconds) ==="
  "$BACKUP_SCRIPT" || true
  echo "Next backup in ${INTERVAL_SECONDS}s"
  sleep "$INTERVAL_SECONDS"
done
