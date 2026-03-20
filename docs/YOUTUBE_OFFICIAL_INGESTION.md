# YouTube — official data & ingestion

## Why official API only

- **YouTube Data API v3** (Google Cloud project + API key or OAuth) is the supported way to read metadata, playlists, and (optionally) comments.
- **Scraping** the site or using unofficial endpoints risks IP blocks, CAPTCHAs, and ToS issues — not suitable for production brand intelligence.

## What data we store (brand / narrative use)

| Field | Source | Notes |
|--------|--------|--------|
| `video_id` | `videos.list` | Stable key |
| `channel_id`, `channel_title` | `snippet` | Who is publishing |
| `title`, `description` | `snippet` | Primary text for themes / entity detection |
| `published_at` | `snippet` | Time series |
| `tags`, `category_id`, `default_language` | `snippet` | Taxonomy / locale |
| `duration_iso` | `contentDetails` | ISO 8601 duration |
| `views`, `likes`, `comment_count` | `statistics` | Engagement / prioritization |
| `thumbnail_url` | `thumbnails` | UI |
| `url` | constructed | Canonical watch URL |
| `top_comments` (optional) | `commentThreads.list` | **1 quota unit per video** — off by default |

Pipeline marker: `pipeline: youtube_official`. Collection default: `youtube_intel_videos`.

## How we discover videos (limits-first)

1. **Monitored channels** (`monitor_channel_ids`): `channels.list` → uploads playlist → `playlistItems.list` (cheap vs search).
2. **Discovery search** (`discovery_search_queries`): `search.list` — **100 units per call**; cap with `max_searches_per_run`.
3. **Detail enrichment**: `videos.list` in batches of 50 — **1 unit per batch**.
4. **Comments** (optional): `commentThreads.list` — **1 unit per video**; set `max_videos_for_comment_fetch: 0` until budgeted.

## Quota (typical defaults)

- Default **10,000 units/day** per Google project (can request increase).
- Example conservative run: 2 searches (200) + 1 `videos.list` (1) + 3 channels + 3 playlist pages (~6) ≈ **207 units** (no comments).

Tune in `config/*.yaml` under `youtube_official:`.

## Config

- **`YOUTUBE_API_KEY`**: env var (shared with `youtube_trending` if desired).
- **`youtube_official.enabled`**: master switch.
- **`scheduler.youtube_official_interval_minutes`**: how often the job runs (min 30 enforced in code).

## Operational

- **Manual run**: `python backend/scripts/run_youtube_official_ingest.py` (from repo root, with `APP_ENV` and Mongo as for the app).
- **Scheduler**: job id `youtube_official_ingest` when `youtube_official.enabled` is true.
- **Coexistence**: `youtube_monitor` (Apify) and `youtube_official` are separate; disable Apify path when you fully migrate to official-only discovery.

## Future extensions (still official)

- **Captions**: `captions.list` + download often requires **OAuth** and owner/third-party permissions; not in v1.
- **Push**: YouTube **PubSubHubbub** for near-real-time uploads on subscribed channels (reduces polling).
- **Analytics**: YouTube Analytics API is separate OAuth + channel owner scope.
