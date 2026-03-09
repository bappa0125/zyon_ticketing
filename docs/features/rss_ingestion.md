# RSS Metadata Ingestion

## Purpose

STEP 4 of the Monitoring Ingestion Layer: an **RSS ingestion worker** that fetches RSS feeds from configured sources, extracts **article metadata** (title, url, published date), and stores it in MongoDB. It does **not** crawl article pages, fetch full content, or run entity detection. A later stage will consume these records for processing.

## How It Works

1. **Sources** — The worker uses the Media Source Registry and Crawl Scheduler: gets RSS sources (`get_rss_sources()`), then ready sources (`get_ready_sources()`), then the ordered list from the Crawl Queue (`get_ordered_ready_sources()`).
2. **Batch** — Only a limited number of feeds are processed per run (e.g. 10). No parallel fetching; feeds are processed one after another.
3. **Fetch** — Each feed URL is fetched with `feedparser`. Only the RSS XML is read; no HTTP requests to article URLs.
4. **Extract** — For each `<item>` (or entry): `title`, `url` (link), `published_at` (parsed). Attached metadata: `source_domain`, `rss_feed`, `discovered_at`.
5. **Freshness filter** — Only items with `published_at` within the configured freshness window are considered for insert. Older items (or items with no `published_at`) are skipped and counted as stale; they are not written to `rss_items`. See [Freshness window](#freshness-window) below.
6. **Store** — Each entry that passes the freshness check is written to MongoDB collection `rss_items` with `status: "new"`, unless the URL already exists (deduplication).
7. **Deduplication** — Before insert, the worker checks if `url` is already in `rss_items`. If it exists, the item is skipped (no insert, no update).

## rss_items Schema

| Field           | Type     | Description |
|-----------------|----------|-------------|
| `title`         | string   | Article title from RSS (truncated if very long). |
| `url`           | string   | Article URL (link). Used for deduplication. |
| `source_domain` | string   | Domain of the source (e.g. from `media_sources.yaml`). |
| `published_at`  | datetime | Parsed publish/update date from RSS (or null). |
| `discovered_at` | datetime | When this run discovered the item (UTC). |
| `rss_feed`      | string   | RSS feed URL. |
| `status`        | string   | Default `"new"`. For use by the next processing stage. |

Collection: **`rss_items`**

## Freshness window

RSS feeds often include older articles. To keep the pipeline focused on **recent** mentions, the ingestion stage applies a **freshness filter**: only items whose `published_at` falls within a configurable time window are inserted into `rss_items`.

- **Rule:** An item is inserted only if `published_at >= current_time - freshness_window`. Items with no `published_at` are treated as stale and skipped.
- **Why skip stale items:** Reduces noise in downstream processing (e.g. Article Fetcher, entity detection) and keeps the monitoring pipeline aligned with recent coverage.
- **Configuration:** In `config/monitoring.yaml`, under `monitoring`, set:

  ```yaml
  rss_ingestion:
    freshness_window_hours: 72
  ```

  The default is **72 hours**. Change `freshness_window_hours` to adjust how far back items are accepted (e.g. `24` for one day, `168` for one week). The value is loaded through the existing app configuration; no code change is required to tune the window.

## Deduplication

- **Key:** `url`.
- **Rule:** Before inserting a document, the worker checks `rss_items` for an existing document with the same `url`. If found, the item is **skipped** (not inserted). No update of existing documents in this step.
- **Effect:** Each article URL is stored at most once. Re-runs of the worker add only new items.

## Next Stage

Downstream processing (not part of STEP 4) will:

- Read documents from `rss_items` (e.g. where `status == "new"`).
- Optionally fetch article content, run entity detection, or push to other collections.
- Update `status` (e.g. to `"processed"`) when done.

This step only populates `rss_items` with metadata; it does not implement that processing.

## Running the Worker

The worker is a **scheduled task**: it runs one cycle then exits. It does not run an infinite loop. Invoke it periodically (e.g. cron, or a scheduler that runs the script).

**One run from project root (Docker):**
```bash
docker compose run --rm backend python scripts/run_rss_ingestion.py
```

**One run (async) from code:**
```python
from app.services.monitoring_ingestion.rss_ingestion import run_rss_ingestion
import asyncio
stats = asyncio.run(run_rss_ingestion(max_feeds=10))
# stats: feeds_processed, articles_discovered, duplicates_skipped
```

**Worker module (one cycle):**
```python
from app.services.monitoring_ingestion_rss_worker import run_once
stats = run_once(max_feeds=10)
```

## Logging

After each feed the worker logs:

- **feed** — Source domain (e.g. `moneycontrol.com`).
- **fresh_items_inserted** — Number of items from that feed inserted into `rss_items`.
- **stale_items_skipped** — Number of items from that feed skipped because they were outside the freshness window (or had no `published_at`).

Example: `RSS feed processed: moneycontrol.com, Fresh items inserted: 12, Stale items skipped: 5` (log keys: `rss_ingestion_feed_processed`, `feed`, `fresh_items_inserted`, `stale_items_skipped`).

After each run the worker also logs:

- **feeds_processed** — Number of RSS feeds fetched.
- **articles_discovered** — Total number of entries extracted from those feeds.
- **duplicates_skipped** — Number of entries skipped because `url` already existed in `rss_items`.
- **fresh_items_inserted** — Total number of items inserted (within freshness window, not duplicates).
- **stale_items_skipped** — Total number of items skipped due to staleness.

## Performance

- **Batch size:** Configurable `max_feeds` per run (default 10).
- **Sequential:** Feeds are fetched one after another; no parallel RSS requests.
- **No article crawl:** Only RSS XML is fetched; no requests to article URLs.
- **No entity detection** in this step.
- Suitable for Mac Mini M1, 16GB RAM, as a scheduled job.

## Files

| File | Role |
|------|------|
| `backend/app/services/monitoring_ingestion/rss_ingestion.py` | Fetch RSS, extract metadata, dedup, insert into `rss_items`. |
| `backend/app/services/monitoring_ingestion_rss_worker.py` | Worker entrypoint: one cycle (async or sync). |
| `backend/scripts/run_rss_ingestion.py` | Script to run one cycle; for cron/scheduler. |

## Deploy and test

### Deploy

- **Config:** Ensure `config/monitoring.yaml` is present and contains `monitoring.rss_ingestion.freshness_window_hours` (default 72). The Docker image copies `config/` into the container, so no extra deploy step is needed for config.
- **One-off run (Docker):** From the **project root** (where `docker-compose.yml` lives), with stack up so MongoDB is available:
  ```bash
  docker compose up -d mongodb redis
  docker compose run --rm backend python scripts/run_rss_ingestion.py
  ```
- **Scheduled deploy:** Run the same command via cron or your scheduler (e.g. every 30–60 minutes). No code change is required; the worker runs one cycle then exits.

### Test

1. **Smoke test (Docker):** Run one cycle and check logs for the new metrics:
   ```bash
   docker compose run --rm backend python scripts/run_rss_ingestion.py
   ```
   Look for:
   - Per-feed: `rss_ingestion_feed_processed` with `feed`, `fresh_items_inserted`, `stale_items_skipped`.
   - Run summary: `rss_ingestion_run_complete` with `fresh_items_inserted`, `stale_items_skipped`.
2. **Verify freshness filter:** Set a short window in `config/monitoring.yaml` (e.g. `freshness_window_hours: 1`), run again. You should see more `stale_items_skipped` and fewer inserts. Restore to `72` (or your desired value) afterward.
3. **Check MongoDB:** Query `rss_items` and confirm recent documents have `published_at` within the last 72 hours (or your configured window):
   ```javascript
   db.rss_items.find().sort({ discovered_at: -1 }).limit(5)
   ```

### Local run (no Docker)

From the `backend/` directory, with `PYTHONPATH` and env (e.g. `MONGODB_URL`) set and `config/` available (e.g. symlink or copy from project root):

```bash
cd backend
export PYTHONPATH=/path/to/zyon_ai_ticketing/backend
export MONGODB_URL=mongodb://localhost:27017
python scripts/run_rss_ingestion.py
```

## Constraints

- No article page crawling.
- No entity detection in this step.
- No changes to chat modules.
- Worker runs as a scheduled task; no built-in infinite loop.
