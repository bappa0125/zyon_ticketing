# Narrative taxonomy & forum narrative layer

## Objective

Support **narrative positioning** work: **what** is being discussed (tags), **where** (forum site / domain), and **role** (forums as **amplifiers** of narratives that often start in publications or creator channels).

## Config

- **`config/narrative_taxonomy.yaml`** — tag `id`, `label`, `keywords` (rule-based scoring). Edit keywords; restart backend to clear the in-process cache (or call `clear_narrative_taxonomy_cache()` in dev).

## Pipeline

1. **`article_fetcher`** stores **`feed_domain`** from RSS registry (`rss_items.source_domain`) so Hacker News–syndicated URLs (external article host) still count as **forum** when `feed_domain=news.ycombinator.com`.
2. **`entity_mentions_worker`** (and **`backfill_entity_mentions_multi.py`**) set on each `entity_mentions` row:
   - `narrative_tags`, `narrative_primary` — from taxonomy keyword hits on validation text  
   - `type` — `forum` if page domain is TradingQnA / ValuePickr / Traderji **or** `feed_domain` is a forum feed (incl. HN)  
   - `forum_site` — `tradingqna` | `valuepickr` | `hackernews` | `traderji`  
   - `narrative_surface` — `forum` | `article`  
   - `narrative_role` — `amplifier` (forum) | `publication` (article)

## Media sources

- **TradingQnA**, **ValuePickr** — existing RSS forum entries.  
- **Hacker News** — `news.ycombinator.com` RSS in `config/media_sources.yaml`.

## APIs

- `GET /api/social/forum-mentions` — includes narrative fields per row.  
- `GET /api/social/forum-mentions/narrative-tags` — aggregates **tag × forum_site** counts + samples (traction / gaps).

## Backfill

Existing mentions lack narrative fields until reprocessed. Options:

- Let the worker process **new** docs only, or  
- Run **`python scripts/backfill_entity_mentions_multi.py --reprocess-days N`** (destructive for those URLs when reprocess mode deletes rows — see script help).
