# Reddit Monitoring (Feature 7.1) — Apify

## Purpose

Collect Reddit mentions via configurable Apify actor. Single combined OR query, entity detection in backend. Actor name is read from config; do not hardcode.

## Environment Variables

Set in `.env` (must remain in `.gitignore`):

- `APIFY_API_KEY` — required for Apify actors

## Configuration

**config/monitoring.yaml**:
```yaml
reddit:
  enabled: true
  actor: "trudax/reddit-scraper"
  max_items_per_run: 20
```

## Pipeline

1. Build combined query: `"Sahi OR Zerodha OR Upstox OR Groww"`
2. Call Apify actor via `apify_service.run_actor()`
3. Limit results using `max_items_per_run`
4. Extract: title, text, url, score, comments
5. Run `entity_detection_service.detect_entity()` on text
6. Apply guardrails (engagement filter, dedup, daily limit)
7. Store in `social_posts`

## Apify Optimization

- **One job per platform** — single Apify run with combined query
- **No per-entity queries** — entity detected in backend from content
- **Store only essential fields** — no raw HTML or full actor response

## Run Worker

```bash
docker compose exec backend python -c "
import asyncio
from app.services.reddit_worker import run_reddit_monitor
print(asyncio.run(run_reddit_monitor()))
"
```
