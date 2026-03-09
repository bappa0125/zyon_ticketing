# Media Source Registry

## Purpose

The Media Source Registry is the configuration-driven list of external media sources used by the monitoring system. It reads `config/media_sources.yaml`, validates minimal structure, and exposes the source list to other modules. This step does **not** perform crawling, RSS ingestion, entity detection, or database writes.

## Configuration File

**Path:** `config/media_sources.yaml`

The file has a single top-level key:

- **`sources`** — A list of source objects. Each object describes one media source.

## Source Entry Structure

### Required fields (minimal)

| Field              | Type   | Description |
|--------------------|--------|-------------|
| `domain`           | string | Canonical domain of the source (e.g. `moneycontrol.com`). |
| `crawl_frequency`  | number | How often to crawl (e.g. minutes between runs). |

If either is missing, the loader logs a warning but does not crash. The entry is still included so that configuration errors can be corrected without losing other sources.

### Optional fields

The loader accepts and preserves any additional fields. Unknown or future fields do not break loading.

| Field           | Type   | Description |
|-----------------|--------|-------------|
| `rss_feed`      | string \| null | RSS feed URL. If present and non-empty, source is treated as RSS-based. |
| `crawl_method`  | string | `"rss"` or `"html"`. Drives classification as RSS vs HTML source. |
| `entry_url`     | string | For HTML sources: URL of the entry page to crawl. |
| `name`          | string | Human-readable name (e.g. "Moneycontrol"). |
| `category`      | string | e.g. `financial_news`, `startup_media`, `broker_blog`, `forum`. |
| `region`        | string | e.g. `india`, `global`, `asia`. |
| `priority`      | number | Used to group sources for crawl scheduling (lower = higher priority). |
| `weight`        | number | Optional weight for scheduling or ranking. |

New metadata fields can be added in YAML later; the loader does not require a fixed schema beyond `domain` and `crawl_frequency`.

## Source Types

- **RSS-based:** Has `rss_feed` set to a non-empty string, or `crawl_method: rss`. The system can use these for RSS ingestion in a later step.
- **HTML entry-page:** Has `entry_url` or `crawl_method: html`. Used for sources that require scraping an HTML page instead of an RSS feed.

A source can have both `rss_feed` and `entry_url`; classification prefers RSS when `rss_feed` is present and non-empty.

## How to Add New Sources

1. Open `config/media_sources.yaml`.
2. Under `sources`, add a new list item (same indentation as existing entries).
3. Set at least:
   - `domain`: e.g. `example.com`
   - `crawl_frequency`: e.g. `240` (minutes)
4. Optionally set:
   - `rss_feed` and `crawl_method: rss` for RSS, or
   - `entry_url` and `crawl_method: html` for HTML.
5. Optionally set `name`, `category`, `region`, `priority`, `weight` for scheduling and filtering.

Example:

```yaml
sources:
  - domain: example.com
    name: Example News
    category: financial_news
    region: india
    crawl_method: rss
    rss_feed: https://example.com/feed.xml
    crawl_frequency: 60
    priority: 2
    weight: 5
```

## Priority and Categories (Future Use)

- **Priority** — The registry exposes `get_sources_by_priority()`, which groups sources by the `priority` field. Lower numeric priority can be used for higher importance (e.g. 1 = high, 2 = normal). Future crawl scheduling can pick sources by priority.
- **Category** — Stored on each source as optional metadata. Future steps can filter by `category` (e.g. only `financial_news`) or `region`.

No scheduling or crawling is implemented in this step; the registry only loads and exposes the data.

## API (Python)

| Function                  | Returns | Description |
|---------------------------|---------|-------------|
| `load_media_sources()`    | `list[dict]` | Full list of sources (validated, optional fields preserved). |
| `get_sources_by_priority()` | `dict[int, list[dict]]` | Sources grouped by `priority`. |
| `get_rss_sources()`       | `list[dict]` | Sources classified as RSS-based. |
| `get_html_sources()`      | `list[dict]` | Sources classified as HTML entry-page. |

**Module:** `app.services.monitoring_ingestion.media_source_registry`

**Package import:**

```python
from app.services.monitoring_ingestion import (
    load_media_sources,
    get_sources_by_priority,
    get_rss_sources,
    get_html_sources,
)
```

## Logging

On load, the registry logs:

- **total** — Number of sources loaded.
- **rss_sources** — Count of RSS-based sources.
- **html_sources** — Count of HTML-based sources.

If a source is missing `domain` or `crawl_frequency`, a warning is logged (index and field); the source is still included in the list.

## Constraints

- No network calls.
- No background workers or scheduling.
- No database writes.
- No crawling or ingestion logic.
- Configuration only; existing monitoring and chat modules are unchanged.
