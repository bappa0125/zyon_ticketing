#!/usr/bin/env bash
# Backfill author on existing article_documents by re-fetching and extracting.
# Run from project root. Requires: docker compose, backend + mongodb up.
#
# Usage:
#   ./backend/scripts/backfill_author.sh [--limit 200] [--delay 2]
#
# Options (passed to Python):
#   --limit N   Max articles to process (default 500)
#   --delay N   Seconds between fetches (default 1.5) — increase if hitting rate limits

set -euo pipefail

echo "=== Backfill author on article_documents ==="
docker compose exec backend python scripts/backfill_author.py "$@"
echo "=== Done ==="
