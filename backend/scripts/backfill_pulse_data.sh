#!/usr/bin/env bash
# Backfill and refresh data used by the Pulse dashboard.
# Run from project root (where docker-compose.yml is).
# Requires: docker compose, backend + mongodb up.
#
# Usage:
#   ./backend/scripts/backfill_pulse_data.sh
#
# This will:
#   1) Run RSS ingestion
#   2) Run article fetcher
#   3) Run entity_mentions pipeline (and sentiment, if configured)
#   4) Print ingestion DB counts

set -euo pipefail

echo "=== Backfill Pulse data ==="

echo ""
echo "1) RSS ingestion (rss_items)…"
docker compose exec backend python scripts/run_rss_ingestion.py || {
  echo "RSS ingestion failed"; exit 1;
}

echo ""
echo "2) Article fetcher (article_documents)…"
docker compose exec backend python scripts/run_article_fetcher.py || {
  echo "Article fetcher failed"; exit 1;
}

echo ""
echo "3) Entity mentions (entity_mentions)…"
if docker compose exec backend python scripts/run_entity_mentions.py; then
  echo "Entity mentions run completed."
else
  echo "Entity mentions script failed (continuing, data may be partial)."
fi

echo ""
echo "4) Entity mentions sentiment (optional)…"
if docker compose exec backend python scripts/run_entity_mentions_sentiment.py; then
  echo "Entity mentions sentiment run completed."
else
  echo "Entity mentions sentiment script failed (continuing)."
fi

echo ""
echo "5) Ingestion DB summary after backfill:"
docker compose exec backend python scripts/count_ingestion_db.py || true

echo ""
echo "=== Backfill Pulse data done ==="

