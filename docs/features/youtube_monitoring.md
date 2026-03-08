# YouTube Monitoring (Feature 7.3) — Apify

## Purpose

Collect YouTube mentions via configurable Apify actor. Combined query, entity detection in backend. Actor name is read from config; do not hardcode.

## Environment Variables

Set in `.env` (must remain in `.gitignore`):

- `APIFY_API_KEY` — required for Apify actors

## Configuration

**config/monitoring.yaml**:
```yaml
youtube:
  enabled: true
  actor: "streamers/youtube-scraper"
  max_items_per_run: 10
```

## Pipeline

1. Build query: `"Sahi OR Zerodha OR Upstox OR Groww"` (combined OR)
2. Run Apify actor via `apify_service.run_actor()`
3. Extract: video_title, video_description, comments, url, views
4. Run `entity_detection_service.detect_entity()` on text
5. Apply guardrails (engagement filter, dedup, daily limit)
6. Store in `social_posts`

## Apify Optimization

- **One job per platform** — single Apify run with combined query
- **No per-entity queries** — entity detected in backend from content
- **Store only essential fields** — no raw HTML or full actor response

## Run Worker

```bash
docker compose exec backend python -c "
import asyncio
from app.services.youtube_worker import run_youtube_monitor
print(asyncio.run(run_youtube_monitor()))
"
```
