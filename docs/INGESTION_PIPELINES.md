# Ingestion Pipelines — Who Pushes Data into MongoDB

This document lists every pipeline that **writes** data into MongoDB: pipeline name, target collection(s), the files involved, each file’s role, and what (or who) triggers the pipeline.

---

## Summary Table

| Pipeline | MongoDB collection(s) | Main entry / trigger |
|----------|------------------------|----------------------|
| 1. RSS metadata ingestion | `rss_items` | Script: `run_rss_ingestion.py` |
| 2. Article fetcher (RSS → full text) | `article_documents`, updates `rss_items` | Script: `run_article_fetcher.py` |
| 3. Media monitor (live search) | `media_articles` | Worker: `media_monitor_worker.py` (scheduled/called externally) |
| 4. Reddit monitor | `social_posts` | Worker: `reddit_worker.py` (scheduled/called externally) |
| 5. YouTube monitor | `social_posts` | Worker: `youtube_worker.py` (scheduled/called externally) |
| 6. Social monitor (Apify) | `social_posts` | Worker: `social_monitor_worker.py` (scheduled/called externally) |
| 7. Media ingestion (RSS → media_articles) | `media_articles`, `mention_alerts` | Scheduler: `media_index_scheduler.py` → `ingestion_scheduler.py` |
| 8. Media index (crawl + index) | `media_articles`, Qdrant | `index_scheduler.run_index_cycle()` → `article_indexer.index_articles()` |
| 9. Crawler snapshots / competitors | `web_snapshots`, `competitors` | Crawler / competitor flows using `snapshot_store.py` |
| 10. Crawler alerts | `alerts` | Crawler using `crawler/alert_store.py` |
| 11. YouTube narrative | `youtube_narrative_videos`, `youtube_narrative_summaries` | Scheduler (daily 8:00 UTC) or `POST /api/social/youtube-narrative/refresh` |
| 12. AI search narrative | `ai_search_answers` | Scheduler (daily 10:30 UTC) or `POST /api/social/ai-search-narrative/refresh` |
| 13. AI Search Visibility (Phase 1) | `visibility_answers`, `visibility_runs`, `visibility_weekly_snapshots`, `visibility_recommendations` | Scheduler (weekly Sun 02:00 UTC) or `POST /api/social/ai-search-visibility/refresh` |

*Chat and app data (conversations, messages) are written by `app/services/mongodb.py` and are not ingestion pipelines.*

---

## 1. RSS metadata ingestion → `rss_items`

**What it does:** Fetches RSS feeds from `media_sources.yaml` / registry, applies a freshness window (e.g. 72h), and stores **metadata only** (title, url, source_domain, published_at) in `rss_items`. No article body is fetched here.

| File | Role |
|------|------|
| `backend/app/services/monitoring_ingestion/rss_ingestion.py` | Defines `run_rss_ingestion()`. Fetches feeds (feedparser), applies freshness filter, dedupes by url, **inserts into `rss_items`**. |
| `backend/scripts/run_rss_ingestion.py` | Entry script: sets up path and runs `run_rss_ingestion()`. |

**Trigger:** Run the script (e.g. cron or manually):  
`python backend/scripts/run_rss_ingestion.py`

**Responsible for:** Filling `rss_items` with new RSS entries. Downstream: article fetcher reads from `rss_items`.

---

## 2. Article fetcher (RSS → full text) → `article_documents` + `rss_items` status

**What it does:** Reads **new** items from `rss_items`, fetches each URL, extracts article text (trafilatura), resolves redirects (url_original / url_resolved), dedupes (url_hash, content_hash), and writes full documents to `article_documents`. Updates `rss_items.status` to processed/failed.

| File | Role |
|------|------|
| `backend/app/services/monitoring_ingestion/article_fetcher.py` | Defines `run_article_fetcher()`. Reads `rss_items` (status=new), fetches URL, extracts text, **inserts into `article_documents`**, updates `rss_items`. Creates url_hash + content_hash and unique indexes. |
| `backend/scripts/run_article_fetcher.py` | Entry script: runs `run_article_fetcher()`. |

**Trigger:** Run the script after RSS ingestion:  
`python backend/scripts/run_article_fetcher.py`

**Responsible for:** Turning RSS links into full-text articles in `article_documents`. Does **not** run entity detection or fill `entity_mentions`.

---

## 3. Media monitor (live search) → `media_articles`

**What it does:** For each client/competitor from `clients.yaml`, runs **live search** (Google News RSS + DuckDuckGo via `media_monitor_service`). Dedupes by URL and inserts into `media_articles` (entity, title, url, source, timestamp, snippet).

| File | Role |
|------|------|
| `backend/app/services/media_monitor_worker.py` | **Orchestrator.** Loads clients, loops over entities, calls `search_entity()`, dedupes, **inserts into `media_articles`**. |
| `backend/app/services/media_monitor_service.py` | **Fetcher.** Implements Google News RSS + DuckDuckGo search, returns list of articles. Does not write to DB. |

**Trigger:** Call `run_media_monitor()` on a schedule (cron, Celery, or internal scheduler). Not started by the three scripts in `backend/scripts/`.

**Responsible for:** Populating `media_articles` from live web search (not from RSS-only or article_documents).

---

## 4. Reddit monitor → `social_posts`

**What it does:** Fetches Reddit posts that mention monitored entities (via `reddit_service`), applies guardrails (engagement filter, dedup by content_hash, daily cap per entity), and inserts into `social_posts`.

| File | Role |
|------|------|
| `backend/app/services/reddit_worker.py` | **Orchestrator.** Loads config, calls `fetch_reddit_mentions()`, applies filters, **inserts into `social_posts`** (platform=reddit, entity, text, url, engagement, timestamp). |
| `backend/app/services/reddit_service.py` | **Fetcher.** Calls Reddit API / search, returns raw posts. Does not write to DB. |

**Trigger:** Call `run_reddit_monitor()` on a schedule.

**Responsible for:** Reddit mentions in `social_posts`.

---

## 5. YouTube monitor → `social_posts`

**What it does:** Fetches YouTube mentions for monitored entities (via `youtube_service`), applies same guardrails as Reddit, and inserts into `social_posts`.

| File | Role |
|------|------|
| `backend/app/services/youtube_worker.py` | **Orchestrator.** Loads config, calls `fetch_youtube_mentions()`, applies filters, **inserts into `social_posts`** (platform=youtube, entity, text, url, timestamp). |
| `backend/app/services/youtube_service.py` | **Fetcher.** Fetches YouTube data. Does not write to DB. |

**Trigger:** Call `run_youtube_monitor()` on a schedule.

**Responsible for:** YouTube mentions in `social_posts`.

---

## 5b. YouTube narrative (trading/finance daily) → `youtube_narrative_videos`, `youtube_narrative_summaries`

**What it does:** Uses YouTube Data API v3 (no Apify, no comments) to fetch trading/finance videos by search. One LLM call synthesizes themes, narrative summary, sentiment. Daily snapshots stored in MongoDB for per-day tracking. Popularity from views/likes; sentiment from title + description.

| File | Role |
|------|------|
| `backend/app/services/youtube_trending_service.py` | Fetch via search.list + videos.list; 1 LLM call; save to `youtube_narrative_videos` and `youtube_narrative_summaries`. |
| `backend/app/api/social_api.py` | `GET /social/youtube-narrative` (read), `POST /social/youtube-narrative/refresh` (run pipeline). |

**Config:** `youtube_trending` in config. Requires `YOUTUBE_API_KEY` (env or config). Quota: ~400 units/run (search + videos.list). LLM: 1 call/day (openrouter/free).

**Trigger:** Scheduler daily at 8:00 UTC, or `POST /api/social/youtube-narrative/refresh`.

**Collections:** `youtube_narrative_videos` (raw videos per date), `youtube_narrative_summaries` (one doc per date: narrative, themes, sentiment, top_channels, popularity_score).

---

## 5c. Narrative shift intelligence

**What it does:** Uses YouTube + Reddit APIs + news from DB, clusters content (KMeans + sentence-transformers), LLM summaries per cluster. Outputs narrative themes, platform distribution, influencers. No scheduled job—run manually via backfill script.

**Scripts:** `python scripts/run_narrative_shift_backfill.py` (inside backend container). API: `GET /api/social/narrative-shift`.

---

## 5d. Narrative intelligence daily → `narrative_intelligence_daily`

**What it does:** 1 LLM synthesis call/day over narrative shift + Reddit themes + YouTube summaries. Produces executive summary, top narratives, PR actions, influencers, sentiment. Stored in `narrative_intelligence_daily` (last 7 days in UI).

| File | Role |
|------|------|
| `backend/app/services/narrative_intelligence_daily_service.py` | `run_daily_synthesis()` reads narrative_shift, Reddit themes, YouTube summaries; 1 LLM call; saves to `narrative_intelligence_daily`. |
| `backend/app/api/social_api.py` | `GET /api/social/narrative-intelligence-daily?days=7` |
| `backend/scripts/run_narrative_intelligence_backfill.py` | Runs narrative shift backfill + daily synthesis (full flow). |

**Trigger:** Scheduler daily at 9:00 UTC, or `docker compose exec backend python scripts/run_narrative_intelligence_backfill.py`. **Generate Report** button on Narrative Shift page downloads a client-ready HTML report.

**Config:** `narrative_intelligence_daily.enabled`, `narrative_intelligence_daily.llm.model` (dev.yaml, prod.yaml).

---

## 5e. AI search narrative → `ai_search_answers`

**What it does:** Runs a small set of fixed search queries (e.g. category/client-relevant) through an AI search provider (Perplexity via OpenRouter). Stores answer text + metadata per query per date for Narrative Analytics and positioning. Rate-limited (max queries per run, delay between calls) for free tier.

| File | Role |
|------|------|
| `backend/app/services/ai_search_narrative_service.py` | Builds query list from config; calls Perplexity (LLMGateway with use_web_search); stores in `ai_search_answers`. |
| `backend/app/api/social_api.py` | `GET /api/social/ai-search-answers?days=7&query=`, `POST /api/social/ai-search-narrative/refresh`. |

**Config:** `ai_search_narrative` in config: `enabled`, `search_queries`, `max_queries_per_run`, `delay_seconds_between_calls`, `mongodb.answers_collection`. Requires `OPENROUTER_API_KEY`. Free tier: keep max_queries_per_run low (e.g. 6) and delay ≥ 4s.

**Trigger:** Scheduler daily at 10:30 UTC, or `POST /api/social/ai-search-narrative/refresh`, or master backfill (`--skip ai_search_narrative` to omit).

**Collections:** `ai_search_answers` (query, provider, answer, date, computed_at).

---

## 5f. AI Search Visibility (Phase 1) → `visibility_answers`, `visibility_runs`, `visibility_weekly_snapshots`, `visibility_recommendations`

**What it does:** Runs curated prompts (five groups, capped per run) via Perplexity once per (query, engine, week); stores answers in `visibility_answers`. For each client, runs existing entity detection on each answer and stores `visibility_runs` (entities_found). Computes weekly snapshots (AI Visibility Index, per-group scores) and rule-based recommendations when competitors appear but company does not.

| File | Role |
|------|------|
| `backend/app/services/ai_search_visibility_service.py` | Load prompt groups from `config/ai_visibility_prompts.yaml`; call Perplexity (cached by query/week); entity detection via `entity_detection_service.detect_entities()`; write runs, snapshots, recommendations. |
| `backend/app/api/social_api.py` | `GET /api/social/ai-search-visibility/dashboard?client=&weeks=`, `POST /api/social/ai-search-visibility/refresh`. |

**Config:** `ai_search_visibility` in config: `enabled`, `prompt_groups_file`, `max_prompts_per_run`, `max_per_group_per_run`, `delay_seconds_between_calls`, `enabled_engines: [perplexity]`, `mongodb.*`. Requires `OPENROUTER_API_KEY`. Weekly run only; cache avoids re-running same query in same week.

**Trigger:** Scheduler weekly Sunday 02:00 UTC, or `POST /api/social/ai-search-visibility/refresh`, or master backfill (`--skip ai_search_visibility` to omit).

**Collections:** `visibility_answers` (query, group_id, group_name, engine, week, answer_text); `visibility_runs` (client, query, engine, week, entities_found); `visibility_weekly_snapshots` (client, week, overall_index, group_metrics, engine_metrics); `visibility_recommendations` (client, week, query, competitors_found, recommendation_text).

---

## 6. Social monitor (Apify) → `social_posts`

**What it does:** Fetches social mentions (e.g. Twitter/other) via Apify (`social_monitor_service`), applies guardrails, and inserts into `social_posts`.

| File | Role |
|------|------|
| `backend/app/services/social_monitor_worker.py` | **Orchestrator.** Calls `fetch_social_mentions()`, filters, **inserts into `social_posts`** (platform, entity, text, url, etc.). |
| `backend/app/services/social_monitor_service.py` | **Fetcher.** Calls Apify, returns raw posts. Does not write to DB. |

**Trigger:** Call `run_social_monitor()` on a schedule.

**Responsible for:** Apify-sourced social mentions in `social_posts`.

---

## 7. Media ingestion (RSS → media_articles + alerts) → `media_articles`, `mention_alerts`

**What it does:** **Separate from pipeline 1–2.** Crawls RSS via `media_ingestion.rss_crawler`, fetches and parses articles (`article_parser`), detects entities (`entity_detector`), stores in **`media_articles`** and optionally creates **`mention_alerts`**. Also writes vectors to Qdrant. Runs incrementally (skips existing URLs).

| File | Role |
|------|------|
| `backend/scripts/media_index_scheduler.py` | **Entry.** Runs a loop calling `run_incremental_ingestion()` every N minutes. |
| `backend/app/services/media_ingestion/ingestion_scheduler.py` | **Orchestrator.** `run_incremental_ingestion()`: gets RSS entries from `rss_crawler`, parses with `article_parser`, detects entities with `entity_detector`, calls `store_article()`. |
| `backend/app/services/media_ingestion/article_storage.py` | **Writer.** `store_article()`: dedupes by URL, **inserts into `media_articles`**, sends content to Qdrant, calls `create_alert()**. |
| `backend/app/services/media_ingestion/rss_crawler.py` | **Fetcher.** Crawls RSS sources. Does not write to DB. |
| `backend/app/services/media_ingestion/entity_detector.py` | **Logic.** Detects entities in text. Does not write to DB. |
| `backend/app/services/media_intelligence/alerts.py` | **Writer.** `create_alert()`: **inserts into `mention_alerts`** (company, title, source, url, publish_date). |

**Trigger:** Run the scheduler (e.g. as in docker-compose `media_index_worker`):  
`python scripts/media_index_scheduler.py`  
→ calls `run_incremental_ingestion()` from `media_ingestion.ingestion_scheduler`.

**Responsible for:** Another path that fills `media_articles` (and Qdrant) from RSS + entity detection, and fills `mention_alerts`.

---

## 8. Media index (crawl + index) → `media_articles`, Qdrant

**What it does:** Uses `media_index` crawler and indexer: crawls sources, fetches articles, detects mentions, **inserts into `media_articles`** and indexes in Qdrant. This is a **different code path** from pipeline 7 (different crawler/sources).

| File | Role |
|------|------|
| `backend/app/services/media_index/article_indexer.py` | **Orchestrator + writer.** `index_articles()`: uses `media_crawler.crawl_sources()`, fetches/parses with `article_parser`, detects mentions, **inserts into `media_articles`**, creates alerts, writes to Qdrant. |
| `backend/app/services/media_index/media_crawler.py` | **Fetcher.** Crawls configured sources. Does not write to DB. |
| `backend/app/services/media_index/article_parser.py` | **Parser.** Fetches URL and extracts content. Does not write to DB. |
| `backend/app/services/media_index/index_scheduler.py` | **Entry.** `run_index_cycle()` calls `article_indexer.index_articles()`. |

**Trigger:** Something must call `index_scheduler.run_index_cycle()` (e.g. a separate cron or scheduler). The **docker-compose** `media_index_worker` runs `media_index_scheduler.py`, which uses **media_ingestion** (pipeline 7), not this index_scheduler.

**Responsible for:** Alternative path to `media_articles` + Qdrant from the media_index crawler.

---

## 9. Crawler snapshots / competitors → `web_snapshots`, `competitors`

**What it does:** Stores competitor metadata and web snapshots (HTML, text) for crawler/change detection.

| File | Role |
|------|------|
| `backend/app/services/crawler/snapshot_store.py` | **Writer.** `create_competitor()`: **inserts into `competitors`**. `store_snapshot()`: **inserts into `web_snapshots`** (competitor_id, url, html, text_content, content_hash). |

**Trigger:** Called by crawler or competitor onboarding logic.

**Responsible for:** `competitors` and `web_snapshots` only.

---

## 10. Crawler alerts → `alerts`

**What it does:** Stores crawler/competitor change alerts (not the same as mention_alerts).

| File | Role |
|------|------|
| `backend/app/services/crawler/alert_store.py` | **Writer.** `create_alert()`: **inserts into `alerts`** (competitor_id, change_summary, impact_score). |

**Trigger:** Called by crawler when it detects a meaningful change.

**Responsible for:** `alerts` (crawler alerts).

---

## Who is responsible for what (by collection)

| Collection | Written by (pipeline / file) |
|------------|-----------------------------|
| **rss_items** | RSS ingestion → `rss_ingestion.py` |
| **article_documents** | Article fetcher → `article_fetcher.py` |
| **media_articles** | Media monitor worker (`media_monitor_worker.py`), Media ingestion (`article_storage.py`), Media index (`article_indexer.py`) |
| **social_posts** | Reddit worker (`reddit_worker.py`), YouTube worker (`youtube_worker.py`), Social monitor worker (`social_monitor_worker.py`) |
| **mention_alerts** | Media ingestion path → `media_intelligence/alerts.py` (via `article_storage.store_article`) |
| **entity_mentions** | (No writer in codebase yet; intended for pipeline after entity detection + context validation.) |
| **web_snapshots** | Crawler → `crawler/snapshot_store.py` |
| **competitors** | Crawler → `crawler/snapshot_store.py` |
| **alerts** | Crawler → `crawler/alert_store.py` |
| **ai_search_answers** | AI search narrative → `ai_search_narrative_service.py` |
| **visibility_answers** | AI Search Visibility → `ai_search_visibility_service.py` |
| **visibility_runs** | AI Search Visibility → `ai_search_visibility_service.py` |
| **visibility_weekly_snapshots** | AI Search Visibility → `ai_search_visibility_service.py` |
| **visibility_recommendations** | AI Search Visibility → `ai_search_visibility_service.py` |

---

## In-process scheduler (Option A)

The backend runs an in-process ingestion scheduler when `scheduler.enabled: true` in config (dev.yaml, prod.yaml). Jobs run automatically:

| Job | Interval (config) | Collection(s) / effect |
|-----|-------------------|------------------------|
| RSS ingestion | `rss_interval_hours` (default 4) | `rss_items` |
| Article fetcher | `article_fetcher_interval_minutes` (default 10) | `article_documents`, `rss_items` (status) |
| Entity mentions | `entity_mentions_interval_minutes` (default 15) | `entity_mentions` |
| Reddit monitor | `reddit_interval_minutes` (default 120) | `social_posts` |
| YouTube monitor | `youtube_interval_minutes` (default 120) | `social_posts` |
| Crawler enqueue | `crawler_enqueue_interval_minutes` (default 30) | Enqueues `crawl_website` jobs to Redis |
| YouTube narrative (cron) | Daily 08:00 UTC | `youtube_narrative_videos`, `youtube_narrative_summaries` |
| Narrative intelligence daily (cron) | Daily 09:00 UTC | `narrative_intelligence_daily` |
| AI search narrative (cron) | Daily 10:30 UTC | `ai_search_answers` |
| AI Search Visibility (cron) | Weekly Sunday 02:00 UTC | `visibility_answers`, `visibility_runs`, `visibility_weekly_snapshots`, `visibility_recommendations` |

Config keys: `scheduler.enabled`, `scheduler.rss_interval_hours`, `scheduler.article_fetcher_interval_minutes`, `scheduler.entity_mentions_interval_minutes`, `scheduler.reddit_interval_minutes`, `scheduler.youtube_interval_minutes`, `scheduler.crawler_enqueue_interval_minutes`. Set `scheduler.enabled: false` to disable.

---

## Quick reference: scripts and workers

| Run this | What runs | Collection(s) written |
|----------|-----------|------------------------|
| `python backend/scripts/run_rss_ingestion.py` | RSS metadata ingestion | `rss_items` |
| `python backend/scripts/run_article_fetcher.py` | Article fetch from rss_items | `article_documents`, `rss_items` (status) |
| `python backend/scripts/media_index_scheduler.py` | Media ingestion loop (RSS → media_articles) | `media_articles`, `mention_alerts`, Qdrant |
| `run_media_monitor()` | Live search (Google News, DuckDuckGo) | `media_articles` |
| `run_reddit_monitor()` | Reddit mentions | `social_posts` |
| `run_youtube_monitor()` | YouTube mentions | `social_posts` |
| `run_social_monitor()` | Apify social mentions | `social_posts` |
| `run_index_cycle()` (media_index) | Crawl + index (media_index path) | `media_articles`, Qdrant |
| `docker compose exec backend python scripts/run_narrative_shift_backfill.py` | Narrative shift (YouTube+Reddit+news clustering) | (in-memory, served via API) |
| `docker compose exec backend python scripts/run_narrative_intelligence_backfill.py` | Narrative shift + daily synthesis | `narrative_intelligence_daily` |
| `POST /api/social/ai-search-narrative/refresh` | AI search narrative (Perplexity queries) | `ai_search_answers` |
| **`docker compose exec backend python scripts/run_master_backfill.py`** | **All ingestion jobs in dependency order** | All collections above |

### Master backfill (daily morning run)

Use `run_master_backfill.py` to run every scheduled ingestion job in one go. Recommended for a daily morning catch-up.

```bash
# From project root with Docker
docker compose exec backend python scripts/run_master_backfill.py
```

- **Dependencies:** Runs in correct order (RSS → article fetcher → entity mentions → sentiment/topics → AI summary, etc.).
- **Deduplication:** Each service handles its own (URL dedup, date-based upserts).
- **Continue on error:** By default, one failing job does not stop the rest. Use `--strict` to exit on first failure.
- **Skip phases:** `--skip narrative --skip youtube --skip ai_search_narrative` to omit narrative pipelines, YouTube narrative, or AI search narrative.
- **Dry run:** `--dry-run` shows what would run without executing.
- **Scheduler paused during backfill:** While the master backfill runs, it sets a Redis lock (`ingestion:backfill_running`). The in-process ingestion scheduler checks this before each job and skips the run if the lock is set, so scheduled jobs do not overlap with the backfill. The lock is cleared when the script exits (or after 2h TTL if the script crashes).

### Removing fake/placeholder mentions

If the chat shows fake results (e.g. `example.com`, sources "TechNews"/"FinanceDaily"), remove them with:

```bash
# With Docker (from repo root, backend + mongodb running):
docker compose exec backend python scripts/remove_fake_mentions.py

# Or from backend directory with app env (needs MongoDB URL in env or config):
cd backend && APP_ENV=dev python scripts/remove_fake_mentions.py

# Or with env-only (no app config): needs pymongo installed
MONGODB_URL=mongodb://localhost:27017 MONGODB_DATABASE=chat python scripts/remove_fake_mentions.py
```

The script deletes documents in `entity_mentions`, `media_articles`, `social_posts`, and `article_documents` where the URL contains `example.com` or the source is `TechNews`/`FinanceDaily`.
