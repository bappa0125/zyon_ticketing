#!/usr/bin/env bash
# Run from project root (where docker-compose.yml is). Requires: backend + mongo up.
# Usage: ./backend/scripts/test_rss_before_after.sh
# Or:    API_BASE=http://localhost ./backend/scripts/test_rss_before_after.sh  (if nginx on 80)

set -e
API_BASE="${API_BASE:-http://localhost:8000}"
echo "=== Count BEFORE trigger-rss ==="
docker compose exec backend python -m scripts.count_ingestion_db
echo ""
echo "=== Triggering RSS run (POST $API_BASE/system/trigger-rss) ==="
curl -s -X POST "$API_BASE/system/trigger-rss" | python3 -m json.tool 2>/dev/null || curl -s -X POST "$API_BASE/system/trigger-rss"
echo ""
echo "=== Count AFTER trigger-rss ==="
docker compose exec backend python -m scripts.count_ingestion_db
