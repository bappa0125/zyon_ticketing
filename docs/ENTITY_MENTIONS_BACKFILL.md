# Entity Mentions: Backfill and Worker (Enterprise-Grade)

## Summary

- **Worker** processes **unprocessed** `article_documents` first (oldest by `fetched_at`), marks each with `entity_mentions_processed_at` so the backlog drains without re-processing or blocking.
- **Backfill** runs once (or on a schedule) to process all unprocessed articles in batches with an optional delay to avoid DB/CPU spikes.
- **Batch size** is 150 by default (configurable via `scheduler.entity_mentions_batch_size` in config).

## Worker (scheduled)

- **Query:** `article_documents` where `entity_mentions_processed_at` is null or missing, sorted by `fetched_at` ascending, limit `batch_size`.
- **After each doc:** Set `entity_mentions_processed_at = now()` so it is never processed again.
- **Effect:** New articles (from RSS fetcher, live search) have no marker and are picked up; backlog is cleared oldest-first without blocking.

## Backfill (one-off or cron)

Run to process all unprocessed articles in batches with optional delay:

```bash
# Process all unprocessed, 100 per batch, 0.5s sleep between batches
docker compose exec backend python scripts/backfill_entity_mentions_multi.py

# Limit 500, batch 50, 1s delay (gentler)
docker compose exec backend python scripts/backfill_entity_mentions_multi.py --limit 500 --batch 50 --delay 1.0

# Re-process everything (including already processed)
docker compose exec backend python scripts/backfill_entity_mentions_multi.py --no-skip-processed --limit 1000
```

| Flag | Default | Description |
|------|---------|-------------|
| `--batch` | 100 | Batch size before optional sleep |
| `--limit` | None | Max article_documents to process (None = all unprocessed) |
| `--delay` | 0.5 | Seconds to sleep between batches (0 to disable) |
| `--no-skip-processed` | false | If set, process all docs including already marked |

## Config

- **dev.yaml** (or prod): `scheduler.entity_mentions_batch_size` (default 150).
- **Index:** `article_documents` has partial index `ix_unprocessed_fetched` on `fetched_at` for docs where `entity_mentions_processed_at` is null/missing for performant unprocessed-first query.

## Safeguards

- **No blocking:** Worker and backfill only read/write MongoDB and run in-process entity detection; no external API calls, so no rate-limit blocking from third parties.
- **Performant:** Partial index on unprocessed docs; batch size caps memory and CPU per run.
- **Enterprise-grade:** Every article is processed exactly once (marked after processing); backlog drains predictably; backfill is idempotent when run with default (skip already processed).
