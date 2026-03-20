# RSS feed discovery & finance sources

## What we did in-repo

- **Moneycontrol** (`moneycontrol.com`): four **official** feeds in `config/media_sources.yaml` — `business.xml`, `marketreports.xml`, `latestnews.xml`, `mostpopular.xml`. Same `domain` for all → **one row** in Media Intelligence “Coverage by source”; articles dedupe by **URL** in `rss_items` / `article_documents`.
- **RSS fetch headers** (`rss_ingestion.py`): browser-like `User-Agent` and `Accept` so feeds that sit behind Akamai are less likely to return login/consent HTML instead of XML.

**Avoid** (unstable in checks): `…/rss/indian_markets.xml`, `…/rss/markets.xml` — often **503** from CDN.

## Using tools like [RSS Finder](https://rssfinder.app)

1. Search by site or keyword (e.g. moneycontrol).
2. Prefer **HTTPS** URLs on the **publisher’s domain**.
3. **curl** or open in browser: `Content-Type` should be **XML**, not HTML.
4. Add to `media_sources.yaml`; run RSS ingestion; confirm `rss_items` then article fetcher.

**Caution:** Third-party “generate RSS from any page” services can be fragile or ToS-sensitive — use **official** feeds first.

## Scheduler note

Several YAML entries may share the same `domain` (e.g. multiple Moneycontrol feeds). The crawl scheduler uses a **per-feed key** (`domain` + hash of `rss_feed`) so each RSS URL has its own interval. Each run still processes up to `rss_max_feeds_per_run` feeds (see `config/dev.yaml` → `scheduler.rss_max_feeds_per_run`).

## If you see “no updated result” after editing YAML

1. **Config reload:** `load_media_sources()` reloads when `media_sources.yaml` **mtime** changes. **Rebuild/restart** the backend container if the image bakes in `config/` without a volume (see `backend/Dockerfile` `COPY config/`).
2. **Run RSS + article fetcher manually** after deploy:  
   `python scripts/run_rss_ingestion.py` then `python scripts/run_article_fetcher.py` (or trigger scheduler).
3. **Dashboard:** new `rss_items` dedupe by **URL**; “Coverage by source” still needs **entity_mentions** (run entity-mentions worker / backfill).
4. **Force a full RSS pass:** API `POST` system-metrics ingestion with `force=true` if your deployment exposes it, or temporarily raise `rss_max_feeds_per_run`.

See also: `docs/INGESTION_PIPELINES.md`.
