# Ingestion Pipelines — Architecture

This document describes the ingestion pipelines, collections written, execution order, and pipeline ownership after stabilization.

---

## Final Architecture

```
RSS feeds (media_sources.yaml)
    → rss_ingestion
    → rss_items

rss_items (status=new)
    → article_fetcher
    → article_documents

article_documents
    → entity_mentions_worker (entity detection + context validation)
    → entity_mentions

Parallel:
Reddit / YouTube / Apify
    → social_posts (reddit_worker, youtube_worker, social_monitor_worker)

Fallback (live search when MongoDB has no results):
media_monitor_worker
    → media_articles
```

---

## Collections Written

| Collection | Single writer | Pipeline |
|------------|---------------|----------|
| **rss_items** | `rss_ingestion.py` | Pipeline A |
| **article_documents** | `article_fetcher.py` | Pipeline B |
| **entity_mentions** | `entity_mentions_worker.py` | Entity mentions pipeline |
| **social_posts** | `reddit_worker.py`, `youtube_worker.py`, `social_monitor_worker.py` | Pipeline C |
| **media_articles** | `media_monitor_worker.py` | Pipeline D |

Each collection has **exactly one** or **dedicated** writers (social_posts has three writers by design — one per platform).

---

## Execution Order

1. **RSS ingestion** — `run_rss_ingestion.py`  
   Fetches RSS feeds, applies freshness filter (72h), stores metadata in `rss_items`.

2. **Article fetcher** — `run_article_fetcher.py`  
   Reads `rss_items` (status=new), fetches URLs, extracts text, resolves redirects, dedupes by url_hash/content_hash, stores in `article_documents`.

3. **Entity mentions** — `run_entity_mentions.py`  
   Reads `article_documents`, runs entity detection, validates context, writes to `entity_mentions`.

4. **Social ingestion** — Reddit/YouTube/Apify workers (scheduled)  
   Fetches social posts, applies guardrails, stores in `social_posts`.

5. **Live search fallback** — `media_monitor_worker` (scheduled)  
   Google News RSS + DuckDuckGo, stores in `media_articles`. Used when DB-first retrieval finds no results.

---

## Pipeline Ownership

| Pipeline | Entry | Writes to | Trigger |
|----------|-------|-----------|---------|
| **A — RSS metadata** | `run_rss_ingestion.py` | rss_items | Script (cron/manual) |
| **B — Article fetch** | `run_article_fetcher.py` | article_documents, rss_items (status) | Script (cron/manual) |
| **C — Social ingestion** | `run_reddit_monitor()`, `run_youtube_monitor()`, `run_social_monitor()` | social_posts | Scheduled workers |
| **D — Live search** | `run_media_monitor()` | media_articles | Scheduled worker |
| **Entity mentions** | `run_entity_mentions.py` | entity_mentions | Script (cron/manual) |

---

## Document Schemas

### rss_items

- title, url, source_domain, published_at, discovered_at, rss_feed, status

### article_documents

- title, url, url_original, url_resolved, normalized_url, url_hash, content_hash, source_domain, published_at, article_text, article_length, fetched_at, entities (list)

### entity_mentions

- entity, title, source_domain, published_at, summary, sentiment, url, type (article|blog|forum)

### social_posts

- platform, entity, text, url, content_hash, engagement, published_at

### media_articles

- entity, title, url, source, published_at, snippet

---

## Indexes

- **entity_mentions:** entity + published_at
- **article_documents:** entities, url_hash
- **social_posts:** entity + published_at, TTL on published_at
- **rss_items:** url

---

## One-Time Reset (Development)

Use `backend/scripts/reset_ingestion_collections.py` to drop `media_articles`, `entity_mentions`, `rss_items` for a clean slate.

Does **not** drop: article_documents, social_posts, conversations, messages.
