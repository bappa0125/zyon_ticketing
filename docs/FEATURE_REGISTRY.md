# Zyon AI — Feature Registry

This document tracks all implemented features.

Cursor must read this file before implementing new features.

Cursor must NOT modify existing features unless explicitly instructed.

---

## Feature 1 — Client Monitoring Configuration

**Status:** Implemented

**Purpose:**  
Define monitored clients and their competitors.

**Files involved:**

- `config/clients.yaml`
- `backend/app/core/client_config_loader.py`
- `backend/app/api/clients_api.py`
- `frontend/src/app/clients/page.tsx`
- `frontend/src/components/ClientTable.tsx`

**API:**

- `GET /api/clients`

**Description:**  
Configuration-driven client monitoring system. This will power:

- media monitoring
- social monitoring
- competitor intelligence
- PR strategy recommendations

---

## Feature 2 — Media Monitoring Engine

**Status:** Implemented

**Purpose:**  
Collect news mentions of monitored clients and their competitors.

**Files involved:**

- `backend/app/services/media_monitor_service.py`
- `backend/app/services/media_monitor_worker.py`
- `backend/app/api/media_api.py`
- `frontend/src/app/media/page.tsx`
- `frontend/src/components/MediaTable.tsx`

**API:**

- `GET /api/media/latest?client=Sahi`

**Description:**  
Lightweight news monitoring using Google News RSS and DuckDuckGo. Stores results in MongoDB `media_articles`. No heavy crawling or headless browsers.

---

## Feature 3 — Sentiment Analysis Engine

**Status:** Implemented

**Purpose:**  
Analyze sentiment of media coverage for monitored companies. Use VADER to label articles positive/neutral/negative and aggregate counts by entity.

**Files involved:**

- `backend/app/services/sentiment_service.py`
- `backend/app/services/sentiment_worker.py`
- `backend/app/api/sentiment_api.py`
- `frontend/src/app/sentiment/page.tsx`
- `frontend/src/components/SentimentChart.tsx`
- `docs/features/sentiment_analysis.md`

**API:**

- `GET /api/sentiment/summary?client=Sahi`

**Description:**  
Lightweight sentiment analysis using vaderSentiment. Worker processes articles without sentiment (batch 20), updates `media_articles` with `sentiment` and `sentiment_score`. API aggregates counts per entity.

---

## Feature 4 — Topic Detection Engine

**Status:** Implemented

**Purpose:**  
Detect key topics in media coverage for monitored companies. Use KeyBERT for lightweight keyword extraction; surface topic mentions and analytics.

**Files involved:**

- `backend/app/services/topic_service.py`
- `backend/app/services/topic_worker.py`
- `backend/app/api/topics_api.py`
- `frontend/src/app/topics/page.tsx`
- `frontend/src/components/TopicTable.tsx`
- `docs/features/topic_detection.md`

**API:**

- `GET /api/topics?client=Sahi`

**Description:**  
KeyBERT-based topic extraction. Worker processes articles without `topics` (batch 20), updates `media_articles` with top 3 topics per article. API aggregates topic mentions.

---

## Feature 5 — Competitor Coverage Comparison

**Status:** Implemented

**Purpose:**  
Compare media coverage between monitored clients and their competitors. Uses MongoDB aggregation; entities loaded from clients.yaml.

**Files involved:**

- `backend/app/services/coverage_service.py`
- `backend/app/api/coverage_api.py`
- `frontend/src/app/coverage/page.tsx`
- `frontend/src/components/CoverageChart.tsx`
- `docs/features/coverage_comparison.md`

**API:**

- `GET /api/coverage/competitors?client=Sahi`

**Description:**  
Configuration-driven. Loads client + competitors from clients.yaml; aggregates media_articles by entity; returns mention counts. Uses MongoDB aggregation pipeline for efficiency.

---

## Feature 6 — PR Opportunity Detection

**Status:** Implemented

**Purpose:**  
Detect topics where competitors have media coverage but the client does not. Surfaces PR opportunities for the client to engage.

**Files involved:**

- `backend/app/services/opportunity_service.py`
- `backend/app/api/opportunity_api.py`
- `frontend/src/app/opportunities/page.tsx`
- `frontend/src/components/OpportunityTable.tsx`
- `docs/features/pr_opportunity_detection.md`

**API:**

- `GET /api/opportunities?client=Sahi`

**Description:**  
MongoDB aggregation over media_articles by entity + topic. Returns topics where competitor_mentions > 0 and client_mentions == 0. Top 20 opportunities.

---

## Feature 6.5 — Social Data Guardrails

**Status:** Implemented

**Purpose:**  
Prepare the system for safe high-volume social media ingestion. Config-driven deduplication, engagement filtering, daily sampling limits, TTL retention, and Apify query optimization rules.

**Files involved:**

- `config/monitoring.yaml`
- `backend/app/core/hash_utils.py`
- `backend/app/core/social_posts_indexes.py`
- `backend/app/services/social_filter_service.py`
- `docs/architecture/social_data_guardrails.md`

**Description:**  
Config loader extended to load monitoring.yaml. Hash dedup (MD5), engagement filter, TTL index on social_posts, indexes on content_hash/entity. Apify single-query rule and storage schema documented.

---

## Feature 7 — Social Monitoring (Apify)

**Status:** Implemented

**Purpose:**  
Collect social media mentions (Twitter, YouTube) using Apify. Combined OR query, entity detection in backend. Respects Feature 6.5 guardrails.

**Files involved:**

- `backend/app/services/apify_service.py`
- `backend/app/services/social_monitor_service.py`
- `backend/app/services/social_monitor_worker.py`
- `backend/app/api/social_api.py`
- `frontend/src/app/social/page.tsx`
- `frontend/src/components/SocialTable.tsx`
- `docs/features/social_monitoring_apify.md`

**API:**

- `GET /api/social/latest?entity=Sahi`

**Description:**  
Apify integration. Load entities from clients.yaml; single combined query per platform; normalize and apply guardrails (engagement filter, dedup, daily limit); store in social_posts. APIFY_API_KEY in .env.

---

## Feature 7.2 — Intent Classification (Search Gate)

**Status:** Implemented

**Purpose:**  
Prevent search pipelines from triggering on conversational messages (greetings, small talk, irrelevant questions). Use a hybrid rule + embedding layer to classify intent (chat vs search) before any external search.

**Files involved:**

- `backend/app/services/intent_classifier.py`
- `backend/app/services/url_discovery/intent_detector.py` (reused)
- `backend/app/services/embedding_service.py` (reused)
- `backend/app/api/chat.py`
- `docs/features/intent_classification.md`

**Flow:**  
User message → Intent Classifier → Chat response OR Search pipeline (RSS, DuckDuckGo, Tavily, Apify). Search only when intent=search and entity is extracted.

---

## Feature 7.0 — Entity Alias Detection

**Status:** Implemented

**Purpose:**  
Improve entity detection accuracy, avoid Hindi false positives (e.g. "sahi hai").

**Files involved:**

- `backend/app/services/entity_detection_service.py`
- `config/clients.yaml` (aliases), `config/monitoring.yaml` (entity_detection)
- `docs/features/entity_alias_detection.md`

**Description:**  
Load aliases from clients.yaml and monitoring.entity_detection; ignore_patterns for conversational Hindi; detect_entity(text) returns canonical entity or None.

---

## Feature 7.1 — Reddit Monitoring (Apify)

**Status:** Implemented

**Purpose:**  
Collect Reddit mentions via Apify actor apify/reddit-scraper.

**Files involved:**

- `backend/app/services/reddit_service.py`
- `backend/app/services/reddit_worker.py`
- `config/monitoring.yaml` (reddit section)
- `docs/features/reddit_monitoring.md`

**Description:**  
Build combined OR query; call Apify reddit-scraper; entity_detection; guardrails pipeline; store in social_posts. APIFY_API_KEY.

---

## Feature 7.3 — YouTube Monitoring (Apify)

**Status:** Implemented

**Purpose:**  
Collect YouTube mentions via Apify actor apify/youtube-scraper.

**Files involved:**

- `backend/app/services/youtube_service.py`
- `backend/app/services/youtube_worker.py`
- `config/monitoring.yaml` (youtube section)
- `docs/features/youtube_monitoring.md`

**Description:**  
Build combined OR query; call Apify youtube-scraper; entity_detection; guardrails pipeline; store in social_posts. APIFY_API_KEY.

---

## Feature 7.4 — Entity Resolution for Search Queries

**Status:** Implemented

**Purpose:**  
Map natural-language queries (e.g. "latest news on Sahi") to canonical entity names before mention search, so disambiguation and context filtering work correctly.

**Files involved:**

- `backend/app/services/mention_context_validation.py` — `resolve_to_canonical_entity(query)`
- `backend/app/api/chat.py` — Resolve before `search_mentions`, pass canonical entity
- `docs/features/entity_resolution_search.md`

**Description:**  
Uses `clients.yaml` (name, aliases, competitors) to resolve queries to canonical entity. Enables correct disambiguation (e.g. "Sahi trading") and context filtering for ambiguous entities.

---

## Feature 7.5 — PR Intelligence Layer

**Status:** Implemented

**Purpose:**  
Topic-article mapping, first mention detection, amplifier detection, and journalist-outlet mapping. Read-only; no LLM; uses KeyBERT topics from article_documents.

**Files involved:**

- `backend/app/services/pr_intelligence_service.py` — core logic (topic-article, first mention, amplifier, journalist-outlet)
- `backend/app/api/pr_intelligence_api.py` — API routes

**API:**

- `GET /api/pr-intelligence/topic-articles?client=Sahi&range=7d` — Map topics to articles
- `GET /api/pr-intelligence/first-mentions?client=Sahi&range=7d` — Earliest article per (topic, entity)
- `GET /api/pr-intelligence/amplifiers?client=Sahi&topic=...&range=7d` — Articles after first mention, by author/outlet
- `GET /api/pr-intelligence/journalist-outlets?client=Sahi&range=30d` — Journalist → outlets index

**Description:**  
MongoDB aggregation over entity_mentions + article_documents. Topics from KeyBERT (article_topics_worker). No LLM calls; respects daily quota.
