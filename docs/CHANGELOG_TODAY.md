# Features implemented today

## Reddit trending pipeline (separate from Apify)
- **Data source:** Reddit public JSON API (no API key). Fetches hot posts from configured subreddits (India + global trading/investing).
- **Separate DB/Redis:** Dedicated MongoDB collections `reddit_trending_posts`, `reddit_trending_summaries` and Redis key namespace `reddit_trending:*` (posts, themes, sahi).
- **LLM:** Batched calls for (1) themes from post titles/snippets, (2) Sahi content suggestions. Uses OpenRouter free tier.
- **API:** `GET /api/social/reddit-trending`, `POST /api/social/reddit-trending/refresh`. MongoDB fallback when Redis is empty.
- **Scheduler:** Job `reddit_trending` runs on configurable interval (e.g. 45 min).
- **Config:** `config/dev.yaml` and `config/prod.yaml` — `reddit_trending` section (subreddits, Redis/Mongo keys, LLM, TTLs).

## Sahi strategic brief (Option B)
- **Endpoint:** `GET /api/social/sahi-strategic-brief?use_cache=true`. Returns 1–2 strategic suggestions for Sahi.
- **Context:** Reddit themes, Sahi mentions (entity_mentions), trending topics (topics_service), competitors and mention counts.
- **Cache:** Redis key `sahi_strategic_brief`, TTL 1 hour.
- **Service:** `backend/app/services/sahi_strategic_brief_service.py`.

## Social page UI
- **Strategic suggestions:** Section at top showing 1–2 Sahi strategic suggestions (title, rationale, action_type) with “Refresh brief” button.
- **Reddit trending:** Themes, “Topics Sahi should talk about,” and recent posts table; “Refresh pipeline” button; error and status line.
- **Latest social mentions:** Existing entity filter and SocialTable (Apify/social_posts). All sections use app theme (--ai-*).

## Ingestion and reporting
- **AI brief:** JSON-safe payload serialization (datetime → ISO) to fix 500 on generate; try/except returns clear error message.
- **Ingestion status:** `live_search_ingested_last_24h` and `live_search_note` for live-search ingestion check.

## Page visibility and theme
- **globals.css:** Added `--background: var(--ai-bg)` so pages using it render correctly.
- **App pages:** Reputation, Targets, Alerts, Media Intelligence, Opportunities, Media, Topics, Clients, Coverage use `app-page` for consistent background and text color.
- **SocialTable:** Uses theme variables (--ai-*) for consistency.

## Navigation (menu)
- **Grouped menu:** Top-level items reduced to Home, Chat, Pulse ▾, Media ▾, Action ▾, Clients, Social. Pulse = Dashboard, Topics, Reputation, Alerts, Sentiment; Media = Media Intel, Coverage, Media; Action = Targets, Opportunities.
- **Dropdowns:** Click to open; click outside or on link to close. Overflow and z-index fixed so dropdowns are visible; click-outside uses capture phase.

## Docs
- `docs/features/reddit_trending_pipeline.md` — Reddit trending pipeline, MongoDB/Redis schema, config.
- `docs/DEPLOY_AND_TEST_INGESTION.md` — Deploy and test ingestion.
- `backend/scripts/test_rss_before_after.sh` — RSS before/after test script.
