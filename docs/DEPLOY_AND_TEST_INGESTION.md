# Deploy and test ingestion (all 4 changes)

## Changes implemented

1. **RSS every 1h** – `config/dev.yaml`: `rss_interval_hours: 1`, `rss_max_feeds_per_run: 35`
2. **Lower crawl_frequency** – `config/media_sources.yaml`: 240→120 min, 360→180 min so feeds are “ready” more often
3. **Article fetcher newest first** – `backend/app/services/monitoring_ingestion/article_fetcher.py`: sort by `published_at` desc, then `discovered_at` desc
4. **On-demand trigger** – `POST /system/trigger-rss` runs one RSS cycle. **`POST /system/trigger-pipeline`** runs RSS + article fetcher + entity mentions so the **UI updates** (dashboard shows new data after you refresh).

## Deploy

```bash
cd /path/to/zyon_ai_ticketing
docker compose build backend --no-cache
docker compose up -d
```

If you use nginx on port 80, the API is at `http://localhost/system/...`. If you hit the backend directly, use `http://localhost:8000/system/...`.

## Test: DB count before and after one RSS run

### Option A – Manual

1. **Count before**
   ```bash
   docker compose exec backend python -m scripts.count_ingestion_db
   ```
   Note `rss_items` total and `new`.

2. **Trigger full pipeline** (RSS → articles → entity mentions) so the **UI gets new data**:
   ```bash
   curl -X POST "http://localhost/system/trigger-pipeline"
   ```
   Or with backend on 8000: `curl -X POST "http://localhost:8000/system/trigger-pipeline"`  
   Then **refresh the dashboard** in the browser; counts will update if new articles mention your client.

   To only run RSS (no UI update until scheduled jobs run): `curl -X POST "http://localhost/system/trigger-rss?force=true"`

3. **Count after**
   ```bash
   docker compose exec backend python -m scripts.count_ingestion_db
   ```
   Compare: `rss_items` total and `new` should increase if the run inserted new items.

### Option B – Script (from project root)

```bash
# If API is on port 80 (nginx)
./backend/scripts/test_rss_before_after.sh

# If backend is on port 8000
API_BASE=http://localhost:8000 ./backend/scripts/test_rss_before_after.sh
```

Make the script executable first: `chmod +x backend/scripts/test_rss_before_after.sh`

## Verify pipeline

- **Ingestion status**
  ```bash
  curl -s http://localhost/system/ingestion-status | python3 -m json.tool
  ```
  Check `rss_items.new`, `article_documents.fetched_last_24h`, `entity_mentions.last_24h`.

- **Backend logs**
  ```bash
  docker compose logs backend --tail 100
  ```
  Look for `scheduler_job_complete`, `rss_ingestion_run_complete`, `fresh_items_inserted`.

## Expected behaviour

- After deploy, ~30s after backend start one RSS run executes (startup job).
- Every 1h the scheduler runs RSS again (up to 35 feeds per run).
- Feeds are “ready” every 2h (120 min) or 3h (180 min) instead of 4h/6h.
- `POST /system/trigger-rss` always runs one cycle on demand; compare DB counts before/after to confirm new feeds are ingested.
