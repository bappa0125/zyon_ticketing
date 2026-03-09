# Crawl Queue

## Purpose

The Crawl Queue (STEP 3 of the Monitoring Ingestion Layer) takes the list of **sources ready for crawling** from the Crawl Scheduler and organizes them into **priority queues**. It does **not** perform crawling, start workers, or make network calls. Future crawler workers will consume these queues in order: high → medium → low.

## Flow: Scheduler → Queue

1. **Media Source Registry** supplies the full list of sources (`load_media_sources()`).
2. **Crawl Scheduler** determines which are ready (`get_ready_sources(sources)`).
3. **Crawl Queue** receives the ready list and distributes it into three queues by `priority` from `media_sources.yaml`.

```
Sources (Registry) → Scheduler (ready?) → Queue (high / medium / low) → [future] Crawler workers
```

## Priority Mapping

| Config `priority` | Queue   | Crawl order |
|-------------------|---------|-------------|
| 1                 | High    | First       |
| 2                 | Medium  | Second      |
| 3                 | Low     | Third       |
| Missing or other  | Low     | Last        |

Priority values come from `config/media_sources.yaml` (e.g. `priority: 1`). If a source has no `priority` or a value outside 1–3, it is placed in the **low** queue.

## Queue Structure

Three queues are exposed as a `CrawlQueues` object:

- **high** — list of sources with `priority: 1`
- **medium** — list of sources with `priority: 2`
- **low** — list of sources with `priority: 3` (or missing/other)

**Ordered list:** `to_ordered_list()` returns a single list: high sources first, then medium, then low. Crawler workers will later iterate this list to process higher-priority sources first.

## How Crawler Workers Will Consume the Queue

1. Call the scheduler to get ready sources: `get_ready_sources(load_media_sources())`.
2. Pass them to the queue: `build_crawl_queue(ready_sources)`.
3. Consume in order: `queues.to_ordered_list()` and process each source (crawl, then `mark_crawled(domain)`).

This step does **not** implement the crawler; it only builds the queue structure and ordered list.

## API (Python)

| Function / type      | Description |
|----------------------|-------------|
| `build_crawl_queue(ready_sources)` | Distribute ready sources into high/medium/low; log counts; return `CrawlQueues`. |
| `get_ordered_ready_sources(ready_sources)` | Build queues and return ordered list (high → medium → low). |
| `CrawlQueues`        | Dataclass with `.high`, `.medium`, `.low`, `.total`, `.to_ordered_list()`. |

**Module:** `app.services.monitoring_ingestion.crawl_queue`

**Example:**

```python
from app.services.monitoring_ingestion import (
    load_media_sources,
    get_ready_sources,
    build_crawl_queue,
    get_ordered_ready_sources,
)

sources = load_media_sources()
ready = get_ready_sources(sources)
queues = build_crawl_queue(ready)
# queues.high, queues.medium, queues.low, queues.total
ordered = queues.to_ordered_list()
# or: ordered = get_ordered_ready_sources(ready)
```

## Logging

The queue logs:

- **high_count** — number of sources in the high queue
- **medium_count** — number of sources in the medium queue
- **low_count** — number of sources in the low queue
- **total** — total ready sources

Example: `High priority sources: 7, Medium priority sources: 10, Low priority sources: 4` (via log fields).

## Constraints

- No crawler workers, no network, no RSS fetching.
- No changes to existing ingestion or chat modules; only the new queue component.
- Queue layer only; actual crawling is a later step.
