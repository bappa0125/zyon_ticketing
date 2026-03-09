# Phase 1 — Ingestion Architecture Analysis

**Date:** 2025-03-08  
**Scope:** All services writing to MongoDB; collections; duplicate pipelines.

---

## Collection → Writers

| Collection | Writers | Notes |
|------------|---------|-------|
| **rss_items** | `monitoring_ingestion/rss_ingestion.py` | Single writer ✓ |
| **article_documents** | `monitoring_ingestion/article_fetcher.py` | Single writer ✓ |
| **media_articles** | `media_monitor_worker.py` + `media_ingestion/article_storage.py` + `media_index/article_indexer.py` | **3 writers — duplicate** |
| **social_posts** | `reddit_worker.py` + `youtube_worker.py` + `social_monitor_worker.py` | 3 writers (one per platform) ✓ |
| **mention_alerts** | `media_intelligence/alerts.py` (via `article_storage.store_article`) | Only when media_ingestion runs |
| **entity_mentions** | (none) | No writer yet |
| **web_snapshots** | `crawler/snapshot_store.py` | Crawler only |
| **competitors** | `crawler/snapshot_store.py` | Crawler only |
| **alerts** | `crawler/alert_store.py` | Crawler alerts (different from mention_alerts) |
| **conversations** | `mongodb.py` | Chat |
| **messages** | `mongodb.py` | Chat |

---

## Ingestion Pipelines Active

| Pipeline | Entry | Writes to | Status |
|----------|-------|-----------|--------|
| **RSS metadata** | `run_rss_ingestion.py` | rss_items | Keep |
| **Article fetcher** | `run_article_fetcher.py` | article_documents, rss_items (status) | Keep |
| **Media monitor (live search)** | `media_monitor_worker.run_media_monitor()` | media_articles | Keep |
| **Reddit** | `reddit_worker.run_reddit_monitor()` | social_posts | Keep |
| **YouTube** | `youtube_worker.run_youtube_monitor()` | social_posts | Keep |
| **Social (Apify)** | `social_monitor_worker.run_social_monitor()` | social_posts | Keep |
| **Media ingestion (RSS→media_articles)** | `media_index_scheduler.py` → `ingestion_scheduler.run_incremental_ingestion()` | media_articles, mention_alerts | **Remove (duplicate)** |
| **Media index (crawl→media_articles)** | `index_scheduler.run_index_cycle()` → `article_indexer.index_articles()` | media_articles | **Remove (duplicate)** |

---

## Pipelines Writing to Same Collection

**media_articles** has 3 writers:

1. `media_monitor_worker.py` — live search (Google News, DuckDuckGo) — **KEEP**
2. `media_ingestion/article_storage.py` — RSS → fetch → media_articles — **REMOVE** (duplicates rss_items → article_documents flow)
3. `media_index/article_indexer.py` — crawl → fetch → media_articles — **REMOVE** (duplicate)

**social_posts** has 3 writers (by design — Reddit, YouTube, Apify):

- All 3 kept ✓

---

## Recommendations (Phase 2)

1. **Remove** `backend/app/services/media_ingestion/` — duplicates monitoring_ingestion (rss_ingestion + article_fetcher)
2. **Remove** `backend/app/services/media_index/` — duplicates media_articles ingestion
3. **Remove** `backend/scripts/media_index_scheduler.py` — triggers media_ingestion
4. **Update** docker-compose to remove or repurpose `media_index_worker`
5. **Fix** any imports of media_ingestion or media_index (e.g. `media_search.py`, `config.py`, `source_registry.py`)
6. **Standardize** timestamp → published_at in media_articles, social_posts
7. **Add** entity_mentions pipeline (article_documents → entity_detection → entity_mentions)
