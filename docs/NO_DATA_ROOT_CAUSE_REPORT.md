# No-Data Root Cause Report — Per Page / Route

This document maps each UI page (and its API) to the data it expects, the root causes when that data is missing, and how to fix it. **No implementation** — analysis only for your review.

---

## How to use this report

- **Page/Route:** Frontend path and main API(s) it calls.
- **Expected data:** What the page shows when things work.
- **Data source:** MongoDB collection(s) and/or external APIs.
- **Root cause (no data):** Why the UI might show empty/“No data”/placeholders.
- **How to solve:** Concrete steps (run pipeline, set config, run script).

---

## 1. Executive Report (`/reports/executive-report`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /reports/executive-competitor?range=7d`, `POST /reports/executive-competitor/populate` |
| **Expected data** | 12 sections: Reputation, Media intel, Coverage, Opportunities, PR synopsis, Narrative, AI visibility, Positioning mix (YouTube/Reddit/Forums), Narrative analytics 7d, Forum traction table, Forum PR brief, Campaign brief. One row per client (from `load_clients()` / executive_competitor_analysis). |
| **Data sources** | `entity_mentions`, `article_documents`, `media_articles`, `social_posts`, `narrative_positioning`, `narrative_intelligence_daily`, `visibility_weekly_snapshots`, `ai_brief` (or pr_summary), `executive_competitor_reports` (stored report). |

### Root cause analysis (section by section)

| Section | When it’s empty / “no data” | Root cause | How to solve |
|---------|-----------------------------|------------|--------------|
| **Report missing** | “No report available” | No document in `executive_competitor_reports` yet. | Click “Generate report” (calls build with `refresh=true`) or run master backfill including `executive_competitor_report`. |
| **Section 1 Reputation** | Scores 50, “—” | No (or no recent) rows in `entity_mentions` for client entities in range; or sentiment not computed. | Run entity_mentions pipeline (scheduler or backfill). Run entity_mentions_sentiment pipeline so `sentiment` is set. |
| **Section 2 Media intel** | SOV 0%, “—” | Dashboard reads `entity_mentions` + `article_documents`. Empty if no mentions in range for client entities. | Same as Section 1: ensure entity_mentions (and optionally article_documents) are populated for the period. |
| **Section 3 Coverage** | 0 articles, no top pubs | `article_documents` with `entities` containing client, or entity_mentions; coverage logic uses both. | Run RSS → article_fetcher → entity_mentions. Ensure `article_documents.entities` and/or entity_mentions exist for client. |
| **Section 4 Opportunities** | 0 quote alerts, 0 pub gaps | `detect_pr_opportunities` and `get_pr_opportunities` read entity_mentions, article_documents, and stored `pr_opportunities` / quote alerts. | Run PR opportunities batch (`POST .../populate` runs it for executive clients). Run entity_mentions so there is mention data to analyze. |
| **Section 5 PR synopsis** | “No synopsis” | AI brief or pr_summary: needs stored AI brief for client/range or dashboard pr_summary. | Run AI brief batch (populate or `POST /reports/ai-brief`). Narrative positioning also feeds pr_summary in dashboard. |
| **Section 6 Narrative** | “—” themes, “—” brief | `narrative_positioning` collection (per client per date) and narrative_shift. | Run “Populate data for all brands” (runs narrative positioning batch). Run narrative_shift backfill if you want narrative_shift themes. |
| **Section 7 AI visibility** | 0% indices | `visibility_weekly_snapshots` (and runs/answers) for client. | Run AI Search Visibility pipeline: scheduler (weekly Sun 02:00 UTC) or `POST /api/social/ai-search-visibility/refresh`. Requires config and OPENROUTER_API_KEY. |
| **Section 8 Positioning mix** | 0% forum/news, 0 YouTube/Reddit/Forums | `entity_mentions` (type forum/article), `social_posts` (platform), topics_service (article_documents.topics), coverage competitor-only. | Run entity_mentions + article_topics; run Reddit/YouTube monitors so social_posts has data; run forum_ingestion + entity_mentions for forum %. |
| **Section 9 Narrative analytics** | Section hidden or empty | `narrative_intelligence_daily` has no docs (or `days_loaded` 0). | Run narrative intelligence daily: scheduler (daily 09:00 UTC) or `run_narrative_intelligence_backfill.py`. Depends on narrative_shift + Reddit themes + YouTube summaries. |
| **Section 10 Forum traction** | No table | No `entity_mentions` with `type=forum` in range, or no join to `article_documents.topics`. | Run forum_ingestion → article_documents; run entity_mentions_worker (marks forum by source_domain); run article_topics_worker so forum docs have `topics`. |
| **Section 11 Forum PR brief** | “—” per client | LLM runs at report build time; if forum traction + sample mentions are empty, brief can be empty or “—”. | Ensure forum traction and forum mentions exist (see Section 10). If data exists but brief is “—”, check LLM config/rate limits (OPENROUTER_API_KEY, model). |
| **Section 12 Campaign brief** | “—” per client | Same as Section 11: LLM at report build; input is client summary (pr_brief, positioning_mix, etc.). If those are empty, brief is generic or “—”. | Populate narrative positioning and report data first (Sections 5–8). Check LLM config and rate limits. |

**Summary (Executive Report):** Most sections depend on **entity_mentions** and **article_documents** being filled (RSS → article_fetcher → entity_mentions, plus sentiment and topics). Narrative and AI sections depend on **narrative_positioning**, **narrative_intelligence_daily**, and **AI Search Visibility** pipelines. Forum sections need **forum_ingestion** and **entity_mentions** (forum type) and **article_topics**. **Fix:** Run master backfill, then “Populate data for all brands,” then “Refresh report.” Ensure `executive_competitor_analysis.use_this_file` and clients list match what you expect.

---

## 2. Forum mentions (`/social/forums`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /social/forum-mentions?entity=&limit=&range_days=`, `GET /social/forum-mentions/topics?client=&range_days=&top_n=` |
| **Expected data** | List of forum mentions (entity, title, summary, source_domain, url, date); “By source” counts; “Topics by traction” table (topic, mention_count, sample titles). |
| **Data sources** | `entity_mentions` (type=forum), `article_documents` (for topics join). |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **No mentions** | No documents in `entity_mentions` with `type=forum` in the last N days. | Forum content must first land in `article_documents` (forum_ingestion), then entity_mentions_worker must process those docs and set `type=forum` (based on source_domain in _FORUM_DOMAINS: tradingqna.com, traderji.com, valuepickr.com). Run `run_forum_ingestion.py` then run entity_mentions pipeline (scheduler or `run_master_backfill.py --only forum_ingestion` then `--only entity_mentions`). |
| **No “By source”** | Same as above: no forum entity_mentions, so no source breakdown. | Same as above. |
| **No topics by traction** | (1) No forum entity_mentions, or (2) forum docs in article_documents have no `topics` field (join returns nothing). | (1) As above. (2) Run article_topics_worker so that article_documents (including forum-ingested docs) get `topics` from KeyBERT. |

**Summary (Forum page):** End-to-end chain is **forum_ingestion** → **article_documents** → **entity_mentions_worker** (sets type=forum) → **article_topics_worker** (for topics). Any break in the chain (scheduler disabled, forum sources not in config, or topics not run) causes empty or partial data.

---

## 3. Social (`/social`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /social/reddit-trending`, `POST /social/reddit-trending/refresh`, `GET /social/youtube-narrative`, `POST /social/youtube-narrative/refresh`, `GET /social/sahi-strategic-brief`, `GET /social/latest` |
| **Expected data** | Reddit trending (posts, themes, Sahi suggestions), YouTube narrative (daily summaries), Strategic brief (1–2 suggestions), Latest social mentions table. |

### Root cause analysis

| Block | When empty | Root cause | How to solve |
|-------|------------|------------|--------------|
| **Reddit trending** | “No Reddit trending data” | Reddit trending pipeline writes to Redis + MongoDB (separate from social_posts). Not run or Redis/Mongo empty. | Run Reddit trending pipeline: `POST /social/reddit-trending/refresh`. Requires `reddit_trending.enabled` and config (subreddits, etc.). |
| **YouTube narrative** | “No data” / empty list | `youtube_narrative_summaries` (and videos) empty. | Run pipeline: scheduler (daily 08:00 UTC) or `POST /social/youtube-narrative/refresh`. Requires `youtube_trending.enabled` and `YOUTUBE_API_KEY`. |
| **Strategic brief** | No suggestions | Sahi brief built from Reddit themes + mentions + topics; if those are empty, brief is empty. | Run Reddit trending first so themes/cache exist. Ensure clients/entities and topic data exist for the brief logic. |
| **Latest social mentions** | “No social mentions” | `social_posts` empty for selected entity (or no entity filter). | Run Reddit monitor, YouTube monitor, and/or Social monitor (Apify) so `social_posts` is populated. Scheduler: reddit_interval_minutes, youtube_interval_minutes; Apify needs APIFY_API_KEY and run_social_monitor(). |

**Summary (Social):** Reddit/YouTube narrative and Sahi brief depend on **separate pipelines** (reddit_trending, youtube_trending). “Latest social mentions” depends on **social_posts** (reddit_worker, youtube_worker, social_monitor_worker). Enable and run the right pipelines and keys.

---

## 4. Narrative Shift (`/social/narrative-shift`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /social/narrative-shift`, `GET /social/narrative-intelligence-daily?days=7` |
| **Expected data** | Narratives (themes, platform distribution), Narrative intelligence daily (executive summary, top narratives, PR actions, etc.). |
| **Data sources** | Narrative shift: in-memory/Redis or MongoDB from **run_narrative_shift_backfill.py** (YouTube + Reddit APIs + article_documents). Narrative daily: `narrative_intelligence_daily` collection. |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **Narrative shift empty** | Backfill never run or failed (APIs, clustering, or LLM). | Run `docker compose exec backend python scripts/run_narrative_shift_backfill.py`. Ensure YouTube/Reddit API access and OPENROUTER for LLM if used. |
| **Narrative intelligence daily empty** | No docs in `narrative_intelligence_daily`. Synthesis needs narrative_shift + Reddit themes + YouTube summaries. | Run narrative intelligence backfill: `run_narrative_intelligence_backfill.py` (runs shift + daily synthesis). Or scheduler daily 09:00 UTC. |

**Summary (Narrative Shift):** No scheduled job for narrative shift itself — **manual backfill only**. Narrative daily is scheduler or same backfill script.

---

## 5. Narrative Positioning (`/social/narrative-intelligence`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /social/narrative-positioning?client=&days=`, `POST /social/narrative-positioning/run-batch` |
| **Expected data** | Per-client reports (narratives, positioning, threats, opportunities, brief_summary, positioning_mix_summary, content_suggestions). |
| **Data sources** | `narrative_positioning` collection (one doc per client per date). Filled by run-batch (reads narrative_intelligence_daily, narrative_shift, Reddit themes, YouTube summaries, entity_mentions, article_documents, social_posts). |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **No reports** | No docs in `narrative_positioning` for client/date. Batch not run or failed. | Run batch: “Run batch” on page or `POST /social/narrative-positioning/run-batch`. Requires LLM (OPENROUTER_API_KEY). |
| **Empty or thin content** | Upstream inputs empty: narrative_shift, Reddit themes, YouTube summaries, entity_mentions, articles, social_posts. | Run narrative shift backfill, Reddit trending, YouTube narrative, entity_mentions pipeline, and social monitors so the batch has inputs. |

**Summary (Narrative Positioning):** **Run-batch** must be executed; it does not run on a schedule by default. Upstream data (narrative daily, Reddit, YouTube, mentions, articles) improves quality.

---

## 6. AI Search Visibility (`/social/ai-search-narrative`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /social/ai-search-visibility/dashboard?client=&weeks=`, `POST /social/ai-search-visibility/refresh` |
| **Expected data** | Per-client dashboard: latest snapshot (overall index, group metrics), trend, recommendations. |
| **Data sources** | `visibility_weekly_snapshots`, `visibility_runs`, `visibility_answers`, `visibility_recommendations`. |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **No dashboard / no data** | Visibility pipeline never run or disabled. Weekly run (Sunday 02:00 UTC) or manual refresh. | Run `POST /api/social/ai-search-visibility/refresh`. Enable in config (`ai_search_visibility.enabled`), set `ai_visibility_prompts.yaml`, OPENROUTER_API_KEY. |
| **Empty snapshots for client** | No visibility_runs/snapshots for that client (prompts run but entity detection didn’t find client in answers, or run failed). | Re-run refresh; check prompt groups and entity names in config; ensure entity_detection runs on answers and client name/aliases match. |

**Summary (AI Search Visibility):** **Weekly or manual refresh** only. Config and API key must be set; prompts and entity alignment affect results.

---

## 7. Dashboard (`/dashboard`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /clients`, `GET /reports/pulse?…`, `GET /reports/pulse/articles?…`, `GET /reports/ai-brief?…` |
| **Expected data** | Client list, Pulse report (reputation, articles), AI brief. |
| **Data sources** | clients from config; Pulse from entity_mentions / sentiment / coverage; AI brief from stored ai_brief or similar. |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **No clients** | `load_clients()` returns empty (wrong config file or executive_competitor_analysis pointing to empty list). | Fix config: `clients.yaml` or `executive_competitor_analysis.yml` and `executive_competitor_analysis.use_this_file` so the app loads the intended client set. |
| **Pulse empty** | No entity_mentions / sentiment in range for selected client. | Run entity_mentions and entity_mentions_sentiment pipelines; ensure date range and client filter are correct. |
| **AI brief empty** | No stored AI brief for client/range. | Run AI brief generation (reports API or populate). |

**Summary (Dashboard):** Clients from **config**. Pulse and AI brief from **entity_mentions** and **stored briefs**; run ingestion and brief generation.

---

## 8. Topics (`/topics`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /clients`, `GET /topics?client=&range=` |
| **Expected data** | Topic analytics (volume, trend, sentiment, by entity, sample headlines, action). |
| **Data sources** | `entity_mentions` + `article_documents` (join by url); topics from `article_documents.topics`. |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **No topics** | (1) No entity_mentions in range for client. (2) article_documents have no `topics` (KeyBERT not run). (3) Join fails (url mismatch). | Run entity_mentions pipeline. Run **article_topics_worker** so article_documents have `topics`. Ensure URLs align between entity_mentions and article_documents. |

**Summary (Topics):** Depends on **entity_mentions** and **article_documents.topics**. Run article_fetcher → entity_mentions → **article_topics** pipeline.

---

## 9. Reputation (`/reputation`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /clients`, `GET /reports/reputation?…` |
| **Expected data** | Reputation report (scores, sentiment breakdown). |
| **Data sources** | `entity_mentions` (sentiment), report builder. |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **No / empty report** | No entity_mentions with sentiment in range for selected client. | Run entity_mentions pipeline then **entity_mentions_sentiment** (VADER on title/summary). |

**Summary (Reputation):** **entity_mentions** + **sentiment** field. Run entity_mentions and sentiment worker.

---

## 10. Coverage (`/coverage`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /coverage/competitors`, `GET /coverage/competitor-only-articles`, `GET /coverage/article-counts`, `GET /coverage/mentions`, `GET /coverage/pr-summary` |
| **Expected data** | Competitor list, competitor-only articles, article counts, mentions, PR summary. |
| **Data sources** | `article_documents` (entities), `entity_mentions`; PR summary may use LLM or stored summary. |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **No competitors** | Client not in config or competitors list empty. | Fix clients config (competitors for that client). |
| **0 article counts / no competitor-only** | article_documents have no `entities` or entities don’t include client/competitors. | Entity detection runs at article storage (media ingestion path) or via entity_mentions_worker on article_documents. Run the pipeline that sets `article_documents.entities` (or entity_mentions) for your clients. |
| **No mentions** | No entity_mentions in range. | Run entity_mentions pipeline. |
| **No PR summary** | Coverage PR summary needs data + optional LLM. | Ensure coverage data exists; run any batch that generates pr_summary (e.g. narrative positioning / dashboard). |

**Summary (Coverage):** **article_documents.entities** and **entity_mentions** are key. Populate via RSS → article_fetcher → entity_mentions (and any path that sets entities on articles).

---

## 11. Media Intelligence (`/media-intelligence`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /media-intelligence/dashboard?client=&range=` |
| **Expected data** | Coverage, feed, by_domain, topics, etc. from unified mentions. |
| **Data sources** | `entity_mentions` + `article_documents` (unified in media_intelligence_service). |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **Empty dashboard** | No entity_mentions or article_documents (with entities) in range for client. | Same as Dashboard/Topics: run RSS → article_fetcher → entity_mentions; ensure scheduler or backfill runs. |

**Summary (Media Intelligence):** Same dependency as other “mentions” pages: **entity_mentions** and **article_documents**.

---

## 12. Sentiment (`/sentiment`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /clients`, `GET /sentiment/summary?…`, `GET /sentiment/mentions?…` |
| **Expected data** | Sentiment summary and mention list. |
| **Data sources** | `entity_mentions` (sentiment field). |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **No summary / mentions** | No entity_mentions, or sentiment not set. | Run entity_mentions then **entity_mentions_sentiment** pipeline. |

**Summary (Sentiment):** **entity_mentions** + **sentiment**. Run both pipelines.

---

## 13. Alerts (`/alerts`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /clients`, `GET /reports/alerts?…` |
| **Expected data** | Alerts report (mention_alerts or crawler alerts). |
| **Data sources** | `mention_alerts` (media ingestion) and/or `alerts` (crawler). |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **No alerts** | No rows in mention_alerts or alerts. | mention_alerts: run media ingestion path (media_index_scheduler / article_storage). alerts: run crawler and alert_store. |

**Summary (Alerts):** Depends on which alert system: **media ingestion** (mention_alerts) or **crawler** (alerts).

---

## 14. Opportunities (`/opportunities`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /opportunities?client=`, `GET /opportunities/pr-intel?client=&days=`, `POST /opportunities/run-batch` |
| **Expected data** | PR opportunities (gaps, quote alerts, etc.), PR intel. |
| **Data sources** | opportunity_service (article_documents, entity_mentions), pr_opportunities_service, pr_opportunities collection. |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **No opportunities** | article_documents / entity_mentions empty or no “gaps” detected; or run-batch not run. | Run entity_mentions and article_topics; run opportunities batch: `POST /opportunities/run-batch?client=...`. |
| **No PR intel** | pr_opportunities or quote-alert logic has no data. | Run PR opportunities batch (populate or run-batch). |

**Summary (Opportunities):** **article_documents** + **entity_mentions** + **run-batch** for stored opportunities.

---

## 15. PR Intelligence (`/pr-intelligence`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /pr-intelligence/topic-articles`, `GET /pr-intelligence/first-mentions`, `GET /pr-intelligence/amplifiers`, `GET /pr-intelligence/journalist-outlets` |
| **Expected data** | Topic–article mapping, first mentions, amplifiers, journalist–outlets. |
| **Data sources** | `article_documents` (topics, entities), `entity_mentions` (author/source). |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **No topic articles** | article_documents have no `topics` or no `entities` for client. | Run article_topics_worker; run entity_mentions so entities are set. |
| **No first mentions / amplifiers / journalists** | Same: need article_documents and entity_mentions with author/source data. | Run pipelines that populate articles and mentions; ensure author/source are stored. |

**Summary (PR Intelligence):** **article_documents** (topics, entities) + **entity_mentions** (author). Run article_fetcher, entity_mentions, article_topics.

---

## 16. Chat (`/chat`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `POST /new-chat`, `GET /history/:id`, `POST /chat` |
| **Expected data** | Conversations, answers with cited mentions. |
| **Data sources** | Conversations/messages in MongoDB; mention search uses entity_mentions, article_documents, media_articles, social_posts. |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **“No mentions found”** | DB-first search returns nothing: entity_mentions, article_documents, media_articles, social_posts empty or no match for query/entity. | Populate entity_mentions, article_documents, media_articles, social_posts (ingestion + monitors). Ensure client/entity names match config. |
| **Empty or generic answers** | Same: no grounding data for the model. | Same as above. |

**Summary (Chat):** Relies on **all mention sources** (entity_mentions, article_documents, media_articles, social_posts). Full ingestion and monitors improve answers.

---

## 17. Clients (`/clients`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /clients` |
| **Expected data** | List of clients (and competitors) from config. |
| **Data sources** | Config: `clients.yaml` or `executive_competitor_analysis.yml` (when enabled). |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **No clients** | Config not loaded or file empty / wrong path. | Set `executive_competitor_analysis.use_this_file` and `clients_file` correctly; ensure the YAML exists and has client entries. |

**Summary (Clients):** Purely **config-driven**. No pipeline.

---

## 18. Media (`/media`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /media/latest?client=`, `GET /media-intelligence/dashboard?…` |
| **Expected data** | Latest media items, dashboard. |
| **Data sources** | media_api: likely media_articles or similar; dashboard: entity_mentions + article_documents. |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **No latest media** | media_articles empty or no client filter match. | Run media monitor worker or media ingestion so media_articles is populated. |
| **Dashboard empty** | Same as Media Intelligence: entity_mentions + article_documents. | Run entity_mentions pipeline. |

**Summary (Media):** **media_articles** for “latest”; **entity_mentions** + **article_documents** for dashboard.

---

## 19. Reports (P&R) (`/reports`)

| Aspect | Detail |
|--------|--------|
| **APIs** | `GET /pr-reports/clients`, `GET /pr-reports/snapshots`, `GET /media-intelligence/dashboard`, `GET /pr-reports/press-releases`, `GET /pr-reports/press-release-pickups` |
| **Expected data** | PR report snapshots, press releases, pickups. |
| **Data sources** | pr_daily_snapshots, pr_press_releases, pr_press_release_pickups, entity_mentions, article_documents. |

### Root cause analysis

| What’s missing | Root cause | How to solve |
|----------------|------------|--------------|
| **No snapshots** | pr_daily_snapshots empty (run-batch not run). | Run PR reports batch: `POST /pr-reports/run-batch` or equivalent. |
| **No press releases / pickups** | pr_press_releases or pr_press_release_pickups empty. | Ingest press releases and run pickup detection (configure and run the pipeline that fills these). |

**Summary (Reports):** Depends on **PR-specific collections** and **run-batch**; some data from entity_mentions/article_documents.

---

## Cross-cutting summary

| Dependency | Used by (examples) | How to get data |
|------------|--------------------|------------------|
| **entity_mentions** | Executive report (1–8, 10–11), Dashboard, Topics, Reputation, Coverage, Media intel, Sentiment, Opportunities, PR intel, Chat, Forum page | RSS → article_fetcher → **entity_mentions_worker**; forum_ingestion → article_documents → entity_mentions_worker. Scheduler or `run_master_backfill.py`. |
| **entity_mentions.sentiment** | Executive report 1, Reputation, Sentiment | **entity_mentions_sentiment** worker (VADER). |
| **article_documents** (with entities/topics) | Coverage, Topics, Media intel, PR intel, Opportunities, Forum topics | article_fetcher (from rss_items); **article_topics_worker** for topics; entity_mentions_worker or ingestion path for entities. |
| **social_posts** | Executive report 8, Social (latest), Chat | **reddit_worker**, **youtube_worker**, **social_monitor_worker** (Apify). |
| **narrative_positioning** | Executive report 5–6, 11–12 | **POST narrative-positioning/run-batch** or populate. |
| **narrative_intelligence_daily** | Executive report 9, Narrative Shift page | **run_narrative_intelligence_backfill.py** or scheduler (daily 09:00). |
| **visibility_* collections** | Executive report 7, AI Search Visibility page | **POST ai-search-visibility/refresh** or weekly scheduler. |
| **Reddit trending (Redis/Mongo)** | Social page (Reddit block) | **POST reddit-trending/refresh**. |
| **youtube_narrative_*** | Social page (YouTube block), Narrative | **POST youtube-narrative/refresh** or scheduler; YOUTUBE_API_KEY. |
| **Forum (entity_mentions type=forum)** | Executive report 8, 10–11, Forum page | **forum_ingestion** → article_documents → **entity_mentions_worker** (forum type); **article_topics_worker** for topic traction. |

---

## Recommended order to fix “no data” globally

1. **Config:** Ensure `clients.yaml` (or executive_competitor_analysis) has the right clients and competitors.
2. **Core ingestion:** Run `run_master_backfill.py` (or scheduler): RSS → article_fetcher → **entity_mentions** → entity_mentions_sentiment → **article_topics**.
3. **Forum:** Run `run_forum_ingestion.py` then entity_mentions (and article_topics) so forum traction and forum mentions exist.
4. **Social:** Run Reddit/YouTube monitors (and Apify if used) so **social_posts** is filled; run **reddit-trending** and **youtube-narrative** refresh for Social page blocks.
5. **Narrative:** Run narrative_shift backfill, then narrative_intelligence_backfill; run **narrative-positioning/run-batch** (or populate).
6. **AI visibility:** Run **ai-search-visibility/refresh** (and ensure config/keys).
7. **Executive report:** Run **Populate data for all brands** then **Refresh report**.

Use this report to trace any “no data” on a given page back to the pipeline(s) and config that feed it, then run the corresponding steps above.
