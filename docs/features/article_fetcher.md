# Article Fetcher

## Purpose

STEP 5 of the Monitoring Ingestion Layer: fetch article pages discovered via RSS (in `rss_items`), extract readable article text with **trafilatura**, and store the result in **article_documents**. No entity detection, no chat changes. After processing, each `rss_items` row is updated to `processed` or `failed`.

## How Article Extraction Works

1. **Input** — Read from MongoDB `rss_items` where `status = "new"`, up to a batch size (e.g. 20).
2. **Fetch** — For each item, HTTP GET the article `url` with **httpx** (lightweight, no headless browser). Timeout and redirects are limited.
3. **Extract** — The response HTML is passed to **trafilatura**, which returns main article text and strips navigation, ads, and comments.
4. **Store** — A document is written to **article_documents** (see schema below) only if `url_hash` is not already present (deduplication).
5. **Status** — Update the corresponding `rss_items` document:
   - **Success** (extracted and stored, or duplicate skipped): `status = "processed"`.
   - **Failure** (no URL, fetch error, or no extractable text): `status = "failed"`.

No parallel fetches: items are processed one by one within the batch to limit concurrency.

## article_documents Schema

| Field           | Type     | Description |
|-----------------|----------|-------------|
| `url`           | string   | Original article URL. |
| `normalized_url`| string   | Normalized form (lowercase, no fragment) used for hashing. |
| `url_hash`      | string   | MD5 of normalized URL; used for deduplication. |
| `source_domain` | string   | From `rss_items.source_domain`. |
| `title`         | string   | From `rss_items.title`. |
| `published_at`  | datetime | From `rss_items.published_at` (or null). |
| `article_text`  | string   | Extracted main text from trafilatura. |
| `article_length`| int      | Character count of `article_text`. |
| `fetched_at`    | datetime | When the page was fetched (UTC). |

Collection: **`article_documents`**. An index on `url_hash` is used for dedup and uniqueness.

## rss_items Status Transitions

- **`new`** — Not yet processed by the article fetcher. The worker selects only these.
- **`processed`** — Fetcher ran for this item: either a document was stored in `article_documents` or it was skipped as duplicate. No further processing in this step.
- **`failed`** — Fetcher ran but failed (missing URL, HTTP error, or no extractable text). Can be retried or handled later.

Only `new` items are read; after each run the fetcher updates the item to `processed` or `failed`. No other status values are set by this step.

## Deduplication

- **Key** — `url_hash` (MD5 of normalized URL). Normalization: lowercase, strip fragment; path and query kept.
- **Rule** — Before inserting into `article_documents`, the worker checks for an existing document with the same `url_hash`. If one exists, no insert is made; the `rss_items` row is still set to `processed` so it is not picked again.
- **Effect** — Each distinct article URL is stored at most once in `article_documents`.

## Running the Worker

One cycle per invocation; no built-in loop. Run periodically via cron or a scheduler.

**Docker (from project root):**
```bash
docker compose run --rm backend python scripts/run_article_fetcher.py
```

**From code:**
```python
import asyncio
from app.services.monitoring_ingestion.article_fetcher import run_article_fetcher
stats = asyncio.run(run_article_fetcher(max_items=20))
# stats: articles_fetched, failures, duplicates_skipped, avg_article_length
```

## Logging

After each run the worker logs:

- **articles_fetched** — Number of new articles stored in `article_documents`.
- **failures** — Number of items set to `status = "failed"` (fetch or extraction error).
- **duplicates_skipped** — Number of items not inserted because `url_hash` already existed (still marked `processed`).
- **avg_article_length** — Average character count of extracted text for newly stored articles.

Example: `Articles fetched: 20, Failures: 3` (conceptually; actual keys as above).

## Performance

- **Batch size** — Configurable `max_items` per run (default 20).
- **Sequential** — One HTTP request at a time within a run; no parallel fetches.
- **Lightweight** — httpx + trafilatura only; no headless browser or Playwright.
- **Single run** — Worker runs one batch and exits; no infinite loop.

## Files

| File | Role |
|------|------|
| `backend/app/services/monitoring_ingestion/article_fetcher.py` | Fetch URL, extract with trafilatura, write to `article_documents`, update `rss_items`. |
| `backend/app/services/article_fetcher_worker.py` | Entrypoint for one cycle (async/sync). |
| `backend/scripts/run_article_fetcher.py` | Script for cron/scheduler. |

## Constraints

- No entity detection in this step.
- No changes to chat or existing monitoring architecture.
- No refactor of existing workers or modules.
- Article fetch and text extraction only.
