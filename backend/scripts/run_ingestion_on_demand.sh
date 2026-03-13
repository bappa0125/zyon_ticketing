#!/usr/bin/env bash
# Run both RSS and social (Reddit trending) ingestion pipelines on demand.
# Run from project root. Backend must be up.
#
# Usage:
#   ./backend/scripts/run_ingestion_on_demand.sh
#   API_BASE=http://localhost:8000 ./backend/scripts/run_ingestion_on_demand.sh

set -e
API_BASE="${API_BASE:-http://localhost:8000}"

echo "=== 1. RSS Pipeline (trigger-pipeline) ==="
echo "POST $API_BASE/system/trigger-pipeline"
curl -s -X POST "$API_BASE/system/trigger-pipeline" | python3 -m json.tool 2>/dev/null || curl -s -X POST "$API_BASE/system/trigger-pipeline"
echo ""
echo ""

echo "=== 2. Social Pipeline (Reddit trending) ==="
echo "POST $API_BASE/api/social/reddit-trending/refresh"
curl -s -X POST "$API_BASE/api/social/reddit-trending/refresh" | python3 -m json.tool 2>/dev/null || curl -s -X POST "$API_BASE/api/social/reddit-trending/refresh"
echo ""
echo ""

echo "=== Done ==="
