# Social Media Monitoring (Apify Integration)

## Purpose

Collect social media mentions of monitored entities using Apify actors. Supports Twitter/X and YouTube comments. Respects Feature 6.5 guardrails.

## Apify Integration

**API Key:** Set `APIFY_API_KEY` in `.env`. Never commit API keys.

**Actors:**

| Platform | Config Key | Default Actor |
|----------|------------|---------------|
| Twitter | twitter_actor | `apidojo/tweet-scraper` (Tweet Scraper V2) |
| Twitter | twitter_input_style | `tweet_scraper_v2` (or `scraper_engine` for `scraper-engine/twitter-x-scraper`) |
| Twitter | twitter_sort | `Latest` (V2 only; actor also supports `Top`, etc.) |
| YouTube | youtube_actor | `streamers/youtube-scraper` (see `social_monitor_service`) |

**Config:** `config/monitoring.yaml`

```yaml
monitoring:
  social_sources:
    twitter: true
    youtube: true
  apify:
    twitter_actor: apidojo/tweet-scraper
    twitter_input_style: tweet_scraper_v2
    twitter_sort: Latest
    youtube_actor: streamers/youtube-scraper
    max_items_per_run: 20
```

Actor input/output fields are defined by each Apify actor; confirm the latest **Input** tab in the Apify Console. Tweet Scraper V2 documents `searchTerms`, `maxItems`, and `sort` on [apify.com/apidojo/tweet-scraper](https://apify.com/apidojo/tweet-scraper).

## Combined Search Query Strategy

**Rule:** Do NOT run one scrape per entity.

1. Load all entities from `clients.yaml` (clients + competitors).
2. Build single query: `"Sahi OR Zerodha OR Upstox OR Groww"`.
3. Run Apify actor once with combined query.
4. Detect entity in backend by scanning post text.

Reduces scraping cost and avoids duplicate posts across entity-specific runs.

## Data Flow

```
clients.yaml → entities
        │
        ▼
social_monitor_service.fetch_social_mentions()
        │
        ├── query = "Entity1 OR Entity2 OR ..."
        ├── run_actor(twitter_actor, { searchQueries: [query], maxItems })
        ├── run_actor(youtube_actor, { searchKeywords: query, maxItems })
        ├── normalize output → { platform, entity, text, url, engagement, timestamp }
        │
        ▼
social_monitor_worker.run_social_monitor()
        │
        ├── filter_low_engagement (guardrails)
        ├── generate_content_hash, check dedup
        ├── check daily limit per entity
        │
        ▼
MongoDB social_posts
        │
        ▼
GET /api/social/latest?entity=Sahi
```

## Environment Variable Usage

- Load via existing config: `get_config()["settings"].apify_api_key`
- Source: `.env` (in `.gitignore`)
- Docker: `APIFY_API_KEY` passed via `docker-compose` env

## Error Handling

- Apify API errors: log warning, return empty list
- Network failures: caught in `run_actor`, return []
- Rate limits: Apify client may raise; caught and logged
- Worker does not crash; returns `{inserted, skipped}`
