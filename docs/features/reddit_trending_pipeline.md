# Reddit Trending Pipeline

Separate pipeline for “trending on Reddit” (India + global trading/investing). **No Apify.** Uses Reddit’s public JSON API, dedicated MongoDB collections, and a dedicated Redis key namespace. LLM (OpenRouter free) generates themes and “Sahi should talk about” suggestions.

## Data flow

1. **Fetch** — HTTP GET to `https://www.reddit.com/r/<subreddit>/hot.json` (or `top.json?t=day`) with a custom User-Agent. One request per subreddit, with a delay between requests (configurable).
2. **Normalize** — Map to internal schema: `subreddit`, `title`, `body_snippet`, `url`, `score`, `num_comments`, `created_utc`, `reddit_id`.
3. **Store** — Write to **MongoDB** (`reddit_trending_posts`) and **Redis** (`reddit_trending:posts`).
4. **LLM** — Two batched calls (same model, free tier): (1) themes from post titles/snippets, (2) Sahi content suggestions. Results cached in Redis (`reddit_trending:themes`, `reddit_trending:sahi`) and appended to **MongoDB** (`reddit_trending_summaries`).
5. **API** — `GET /api/social/reddit-trending` reads Redis first, then MongoDB fallback. `POST /api/social/reddit-trending/refresh` runs the full pipeline.

## MongoDB schema (separate from `social_posts`)

- **Database:** Same as app (`chat` by default; overridable via `reddit_trending.mongodb.database`).
- **Collections:**
  - **`reddit_trending_posts`** — One document per post: `subreddit`, `title`, `body_snippet`, `url`, `score`, `num_comments`, `created_utc`, `reddit_id`, `fetched_at`, `pipeline: "reddit_trending"`. Replaced each run (delete + insert).
  - **`reddit_trending_summaries`** — One document per pipeline run: `generated_at`, `themes` (array of `{label, description}`), `sahi_suggestions` (array of `{title, rationale}`), `pipeline: "reddit_trending"`. Append-only.

## Redis schema (separate namespace)

- **Key prefix:** `reddit_trending` (configurable via `reddit_trending.redis.key_prefix`).
- **Keys:**
  - `reddit_trending:posts` — JSON array of normalized posts. TTL e.g. 30 min.
  - `reddit_trending:themes` — JSON array of `{label, description}`. TTL e.g. 1 h.
  - `reddit_trending:sahi` — JSON array of `{title, rationale}`. TTL e.g. 1 h.

No overlap with existing Redis keys (e.g. `ai_brief:...`, `summary:...`, or social_posts-related keys).

## Config

- **`config/dev.yaml`** / **`config/prod.yaml`** — Section `reddit_trending`:
  - `enabled`, `subreddits`, `sort`, `top_period`, `posts_per_subreddit`, `delay_seconds_between_subreddits`, `user_agent`
  - `mongodb.database`, `mongodb.posts_collection`, `mongodb.summaries_collection`
  - `redis.key_prefix`, `redis.posts_ttl_seconds`, `redis.themes_ttl_seconds`, `redis.sahi_suggestions_ttl_seconds`
  - `llm.model`, `llm.max_tokens_themes`, `llm.max_tokens_sahi`
  - `fetch_interval_minutes` — Scheduler interval for the pipeline.

## Scheduler

- Job id: `reddit_trending`. Runs only if `reddit_trending.enabled` is true.
- Interval: `reddit_trending.fetch_interval_minutes` (default 45).

## Frontend

- **Social page** (`/social`): Section “Trending on Reddit” shows themes, Sahi suggestions, and a table of posts. “Refresh” button calls `POST /api/social/reddit-trending/refresh`. Existing “Latest social mentions” (entity filter + `social_posts`) is unchanged.
