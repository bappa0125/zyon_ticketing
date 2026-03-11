# MVP Media Intelligence Section — Feasibility Evaluation

This document evaluates the proposed Media Intelligence features against the **current architecture** (news discovery, article metadata, snippets, optional article fetch) and outlines a minimal implementation plan.

---

## Current Data & Pipeline Summary

| Data source | Populated by | Key fields | Used by |
|-------------|--------------|------------|---------|
| **entity_mentions** | RSS → article_fetcher → entity_mentions_worker; also live-search storage | entity, title, source_domain, published_at, summary, sentiment, url, type | Chat/mention search, retrieval |
| **article_documents** | RSS pipeline + live-search storage | url, url_resolved, url_note, title, article_text, summary, source_domain, entities, published_at | entity_mentions_worker (read), retrieval, “verified” signal |
| **media_articles** | media_monitor_worker (Google News RSS + DuckDuckGo) | entity, title, url, source, published_at, snippet; + sentiment, topics (from workers) | GET /media/latest, coverage, sentiment, topics APIs |
| **rss_items** | RSS ingestion | url, title, summary, source, published_at | article_fetcher (downstream) |

**Mention confidence (verified vs unverified):**  
- **Verified:** article_documents with non-empty `article_text` (body was fetched) and no `url_note`, or entity_mentions with a resolvable url.  
- **Unverified:** article_documents with `url_note` (e.g. "Content fetch blocked...") or metadata-only records (no body); entity_mentions can carry `url_note` from retrieval.

---

## Feature-by-Feature Evaluation

### 1. Media Mentions Feed

**Proposed:** Real-time feed of articles mentioning a tracked company/topic. Each result: headline, publisher/source, publish time, snippet, link, mention confidence (verified vs unverified).

| Aspect | Feasibility | Data sources | Notes |
|--------|-------------|--------------|--------|
| **Headline** | ✅ Yes | entity_mentions.title, article_documents.title, media_articles.title | All stores have title. |
| **Publisher/source** | ✅ Yes | entity_mentions.source_domain, media_articles.source, article_documents.source_domain | Already available. |
| **Publish time** | ✅ Yes | entity_mentions.published_at, media_articles.published_at, article_documents.published_at/fetched_at | Normalize to one field for display. |
| **Snippet** | ✅ Yes | entity_mentions.summary, media_articles.snippet, article_documents.summary | Available everywhere. |
| **Link** | ✅ Yes | entity_mentions.url, article_documents.url/url_resolved, media_articles.url | Prefer resolved url; show url_note when empty. |
| **Mention confidence** | ✅ Yes | article_documents: presence of article_text + absence of url_note → verified; url_note or metadata-only → unverified. entity_mentions: can pass through url_note from retrieval. | No schema change; derive from existing fields. |

**Conclusion:** Fully feasible. Best served by a **unified feed API** that reads from **entity_mentions** and **article_documents** (and optionally **media_articles**) so the feed includes both RSS-derived and live-search–stored mentions, with a single “verified”/“unverified” flag derived as above.

---

### 2. AI Article Summary

**Proposed:** Short AI summary of what the article says about the tracked company/topic. If body cannot be fetched, use title + snippet.

| Aspect | Feasibility | Data sources | Notes |
|--------|-------------|--------------|--------|
| **When body exists** | ✅ Yes | article_documents.article_text (+ title, entity) | Run LLM (e.g. OpenRouter) on (title + snippet + first N chars of article_text) with prompt “Summarize in 1–2 sentences what this article says about [entity].” |
| **When body missing** | ✅ Yes | entity_mentions/article_documents: title + summary/snippet | Same LLM with “Summarize based on headline and snippet only.” |
| **Caching** | ✅ Recommended | Store summary in document (e.g. article_documents.ai_summary or a new collection keyed by url_hash) | Avoid re-calling LLM for same article; compute on first view or in a background job. |

**Conclusion:** Feasible. Uses existing title/snippet/article_text; add an optional **ai_summary** field (or small summary store) and one LLM call per article (with cache). No new ingestion required.

---

### 3. Mentions Trend

**Proposed:** Simple time-series of number of mentions per day (media attention increasing/decreasing).

| Aspect | Feasibility | Data sources | Notes |
|--------|-------------|--------------|--------|
| **Counts by day** | ✅ Yes | entity_mentions.published_at, media_articles.published_at, article_documents.published_at/fetched_at | Aggregate by date (e.g. $dateToString or day bucket). |
| **Existing API** | ✅ Exists | GET /api/coverage/timeline?company=Sahi (in coverage.py) | Returns mentions_by_day (date, count). Uses media_articles; can add same for entity_mentions for a unified trend. |

**Conclusion:** Feasible. Already partially implemented. Extend to **entity_mentions** (and optionally article_documents) for one unified “mentions per day” series, or keep media_articles-only and add a second series later.

---

### 4. Top Publications

**Proposed:** List of sources that mention the company most frequently (e.g. Economic Times, Mint, Moneycontrol).

| Aspect | Feasibility | Data sources | Notes |
|--------|-------------|--------------|--------|
| **Source field** | ✅ Yes | entity_mentions.source_domain, media_articles.source, article_documents.source_domain | Normalize (e.g. lowercase, strip www) for grouping. |
| **Aggregation** | ✅ Yes | $group by source_domain/source, $sum 1, sort by count desc | Standard MongoDB aggregation; no new pipeline. |

**Conclusion:** Feasible. One new (or extended) API: aggregate by source from entity_mentions and/or media_articles, return top N publications with counts.

---

### 5. Share of Voice (Competitor Comparison)

**Proposed:** Compare mention counts between tracked entities (Company A vs B vs C).

| Aspect | Feasibility | Data sources | Notes |
|--------|-------------|--------------|--------|
| **Entity counts** | ✅ Yes | media_articles (by entity), entity_mentions (by entity) | Already implemented: coverage_service + GET /api/coverage/competitors?client=Sahi returns client + competitors with mention counts. |
| **UI** | ✅ Exists | coverage page (CoverageChart) | Frontend already shows competitor comparison. |

**Conclusion:** Already implemented. Optionally extend to include entity_mentions in the count so “share of voice” reflects both media_articles and entity_mentions.

---

### 6. Topic / Keyword Extraction

**Proposed:** Extract key topics or keywords from articles mentioning the entity.

| Aspect | Feasibility | Data sources | Notes |
|--------|-------------|--------------|--------|
| **Existing** | ✅ Yes | media_articles.topics (KeyBERT), GET /api/topics?client=Sahi; coverage.py has GET /coverage/topics (word-frequency) | Topic worker runs KeyBERT on title+snippet and stores topics array; topics API aggregates. |
| **Entity_mentions / article_documents** | ✅ Optional | summary + title (or article_text when available) | Run KeyBERT (or same topic_worker logic) on entity_mentions/article_documents and store topics, or aggregate from existing media_articles only for MVP. |

**Conclusion:** Feasible and largely in place. For MVP, use existing **media_articles** topics and topics API; later add topic extraction for entity_mentions/article_documents if you want one unified “topics for this entity” view.

---

## Data Sources Summary (What Powers What)

| Feature | Primary data source(s) | Optional / extension |
|---------|------------------------|----------------------|
| Media Mentions Feed | entity_mentions, article_documents | media_articles |
| AI Article Summary | article_documents (article_text, title, summary), entity_mentions (title, summary) | — |
| Mentions Trend | media_articles (existing timeline API) | entity_mentions, article_documents |
| Top Publications | entity_mentions.source_domain, media_articles.source | article_documents.source_domain |
| Share of Voice | media_articles (coverage_service) | entity_mentions |
| Topic / Keyword | media_articles.topics (KeyBERT) | entity_mentions/article_documents |

---

## Minimal Implementation Plan

### Phase 1 — Unified Media Mentions Feed (MVP core)

1. **New API: GET /api/media-intelligence/feed** (or extend GET /api/media/latest)
   - **Input:** client or entity (e.g. `?entity=Sahi`), optional limit, optional source=entity_mentions|media_articles|all.
   - **Logic:** Query entity_mentions and article_documents by entity (and optionally media_articles). Merge, sort by published_at desc. For each item:
     - headline, source, publish time, snippet, link (resolved url or empty + url_note).
     - **mention_confidence:** `"verified"` if from article_documents with article_text and no url_note, else `"unverified"`.
   - **Output:** JSON list of feed items with the above fields. No new collections; use existing indexes (entity + published_at).

2. **Frontend: “Media mentions” / “Media intelligence” page**
   - Single feed list (cards or table): headline, source, date, snippet, link, badge “Verified”/“Unverified”.
   - Client/entity selector at top (reuse clients from config). Optional: date range filter.

### Phase 2 — Insights (reuse + small additions)

3. **Mentions trend**
   - Use existing **GET /api/coverage/timeline?company=Sahi** (media_articles). Optionally add a second endpoint that aggregates entity_mentions by day for the same entity so one chart can show “all mentions” or “media_articles only.”
   - Frontend: simple line or bar chart (date vs count). Reuse or mirror existing coverage/sentiment chart patterns.

4. **Top publications**
   - **New API: GET /api/media-intelligence/top-publications?entity=Sahi&limit=10**
   - Aggregate entity_mentions (and optionally media_articles) by source_domain/source, count, sort desc, return top N. No new pipeline.

5. **Share of voice**
   - Keep using **GET /api/coverage/competitors?client=Sahi** and existing coverage page. Optionally extend coverage_service to include entity_mentions in the counts so SOV reflects all stored mentions.

6. **Topics / keywords**
   - Keep using **GET /api/topics?client=Sahi** (media_articles.topics). Add a “Topics” block to the Media Intelligence page that calls this API. No backend change for MVP.

### Phase 3 — AI summary (optional for first demo)

7. **AI article summary**
   - When user expands a feed item or opens “detail,” call a small backend endpoint that:
     - Accepts article id or url (or entity + title).
     - Loads article_documents (or entity_mentions) for that item; gets title, snippet, and if available article_text.
     - If ai_summary already stored, return it.
     - Else call LLM with “Summarize in 1–2 sentences what this article says about [entity]” on (title + snippet + optional article_text excerpt), then store ai_summary and return.
   - Frontend: show “Summary” section with loading state, then the returned text.

---

## Summary Table

| Proposed feature | Feasible? | Data / API today | Minimal work |
|------------------|-----------|------------------|--------------|
| 1. Media Mentions Feed | ✅ Yes | entity_mentions, article_documents, media_articles | New unified feed API + “verified”/“unverified”; new/updated feed UI. |
| 2. AI Article Summary | ✅ Yes | title, snippet, article_text | LLM endpoint + optional ai_summary storage; wire into feed detail view. |
| 3. Mentions Trend | ✅ Yes | GET /coverage/timeline (media_articles) | Use existing API; add chart on Media Intelligence page; optionally add entity_mentions to timeline. |
| 4. Top Publications | ✅ Yes | source_domain / source in mentions | New aggregation API + small UI block. |
| 5. Share of Voice | ✅ Yes | GET /coverage/competitors, coverage_service | Use as-is; optionally include entity_mentions in counts. |
| 6. Topic / Keyword | ✅ Yes | media_articles.topics, GET /api/topics | Use as-is; add Topics section to Media Intelligence page. |

All six features are **practical** with the current pipeline. The main architectural choice is whether the “single source of truth” for the feed is **entity_mentions + article_documents** (RSS + live search, with verified/unverified) or **media_articles** (current media monitor). Recommending **entity_mentions + article_documents** for the feed gives you verified/unverified and aligns with chat/mention search; you can still surface media_articles in the same feed or in a separate “Media monitor” tab. Implementation stays simple: one new feed API, one new “top publications” API, reuse of timeline/topics/coverage, and an optional AI-summary endpoint with caching.
