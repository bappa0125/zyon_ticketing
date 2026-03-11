# Live Search Job (Sahi, Dhan, Groww, Zerodha)

Scheduled job that runs **live search** for the client and selected competitors, then **stores results** in `article_documents` with deduplication. The **entity_mentions_worker** (run separately or on a schedule) turns new article_documents into entity_mentions, increasing **Media Intelligence** coverage.

## Entities

Fixed list: **Sahi**, **Dhan**, **Groww**, **Zerodha**.

## Safeguards (avoid blocks)

- **One entity at a time** – no parallel search.
- **Delay between entities** – default 45s (configurable 10–300s).
- **Back off on errors** – on 429, 5xx, connection/timeout, the run stops and sleeps 5 minutes before exit so the next cron run is not immediate.
- **Optional reduced load** – `--no-external` skips Tavily/DuckDuckGo; `--no-llm-rerank` skips LLM rerank.

## Usage

```bash
# Default (45s delay, external + LLM rerank)
docker compose exec backend python scripts/run_live_search_all_entities.py

# Longer delay (e.g. 60s)
docker compose exec backend python scripts/run_live_search_all_entities.py --delay 60

# Lighter load (no external search, no LLM rerank)
docker compose exec backend python scripts/run_live_search_all_entities.py --no-external --no-llm-rerank
```

## Scheduling

Run 1–2 times per day (e.g. 2 AM) so you don’t hammer providers:

```cron
# Daily at 2 AM
0 2 * * * cd /app && python scripts/run_live_search_all_entities.py
```

Or every 12 hours:

```cron
0 2,14 * * * cd /app && python scripts/run_live_search_all_entities.py --delay 60
```

After the job runs, run the **entity_mentions_worker** (or let your existing schedule do it) so new `article_documents` get turned into `entity_mentions` and appear in the Media Intelligence dashboard.
