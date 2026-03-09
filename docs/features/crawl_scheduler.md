# Crawl Scheduler

## Purpose

The Crawl Scheduler (STEP 2 of the Monitoring Ingestion Layer) decides **which** media sources are ready to be crawled. It does **not** perform crawling, start workers, or make network calls. It consumes the source list from the Media Source Registry, tracks last-crawled state in memory, and outputs a list of sources ready for crawl. Future crawler workers will consume this list.

## How `crawl_frequency` Works

Each source in `config/media_sources.yaml` has a **`crawl_frequency`** value (in **minutes**). It defines the minimum time between two crawls of the same source.

- Example: `crawl_frequency: 240` → the source may be crawled again only after 240 minutes (4 hours) have passed since the last crawl.
- If `crawl_frequency` is missing or invalid, a default (60 minutes) is used.

## When a Source Becomes Ready

A source is **ready for crawling** when either:

1. **Never crawled** — it has no `last_crawled_at` record → ready immediately.
2. **Enough time has passed** — `current_time - last_crawled_at >= crawl_frequency` (in minutes).

The scheduler uses in-memory state: for each source (by `domain`), it stores `last_crawled_at` (timestamp). When a crawler completes a source (in a future step), it will call `mark_crawled(domain)` so the next scheduler run will respect `crawl_frequency`.

## Priority and Future Crawling

Sources have an optional **`priority`** in the configuration (e.g. 1 = high, 2 = normal). The scheduler exposes:

- **`get_ready_sources(sources)`** — flat list of all ready sources.
- **`get_ready_sources_by_priority(sources)`** — same ready sources grouped by priority (e.g. `{1: [...], 2: [...]}`).

**Lower priority number = higher priority.** Crawler workers implemented later can process priority 1 first, then priority 2, and so on. This step only builds the grouped list; it does not run any crawler.

## State Tracking

- **Storage:** In memory only (module-level dict: `domain` → `last_crawled_at`).
- **Scope:** State is per process; it is lost on restart. A future step may persist state (e.g. Redis or DB) if required.
- **API:** `mark_crawled(domain)` records that a source was crawled; `get_last_crawled(domain)` returns its last crawl time or `None`.

## API (Python)

| Function | Description |
|----------|-------------|
| `get_ready_sources(sources)` | Returns list of sources ready to be crawled. Logs ready count, skipped count, and distribution by priority. |
| `get_ready_sources_by_priority(sources)` | Returns `dict[priority, list[sources]]` of ready sources, sorted by priority. |
| `is_ready(source)` | Returns whether a single source is ready. |
| `mark_crawled(domain)` | Records that the source was crawled (for future crawler integration). |
| `get_last_crawled(domain)` | Returns last crawl timestamp or `None`. |

**Module:** `app.services.monitoring_ingestion.crawl_scheduler`

**Typical use (no crawler yet):**

```python
from app.services.monitoring_ingestion import load_media_sources, get_ready_sources, get_ready_sources_by_priority

sources = load_media_sources()
ready = get_ready_sources(sources)
ready_by_priority = get_ready_sources_by_priority(sources)
# Later: crawler would iterate ready_by_priority (e.g. priority 1 first) and call mark_crawled(domain) after each crawl.
```

## Logging

The scheduler logs:

- **ready_count** — number of sources ready for crawl.
- **skipped_count** — number of sources not ready (within `crawl_frequency`).
- **by_priority** — count of ready sources per priority (e.g. `{1: 5, 2: 10}`).

## Constraints

- No background workers or loops.
- No network calls or RSS fetching.
- No changes to existing monitoring ingestion modules (only new `crawl_scheduler` module and package exports).
- Scheduling logic only; crawler implementation is a later step.
