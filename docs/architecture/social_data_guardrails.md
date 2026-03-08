# Social Data Guardrails

## Purpose

Prepares the system to safely ingest high-volume social media data (Feature 7). Protects MongoDB from storage explosion, duplicate posts, and noisy low-engagement data.

## Configuration

**File:** `config/monitoring.yaml`

| Key | Description |
|-----|-------------|
| retention_days | TTL for documents (auto-delete after N days) |
| max_posts_per_entity_per_day | Cap posts per entity per calendar day |
| engagement_thresholds | likes, retweets, comments — post must meet one to be stored |
| deduplication.enabled | Skip insert if content_hash exists |
| ingestion.batch_size | Max posts per batch (20) |
| crawling.interval_minutes | Scrape interval (30) |

## Deduplication Logic

1. Generate `content_hash` via `hash_utils.generate_content_hash(text)` (MD5)
2. Before insert, query: `{"content_hash": hash}`
3. If document exists → skip insert
4. Index on `content_hash` for fast lookup

## Engagement Filtering

`social_filter_service.filter_low_engagement(posts)`:

- Post passes if: `likes >= threshold` OR `retweets >= threshold` OR `comments >= threshold`
- Thresholds from `config.monitoring.social_data.engagement_thresholds`

## Daily Sampling Limit

- Before insert: count documents where `entity = X` and `timestamp` date = today
- If count >= `max_posts_per_entity_per_day` → skip insert
- Prevents one entity from flooding storage

## TTL Retention

- Collection: `social_posts`
- Field: `timestamp` (must be BSON date for TTL to work)
- TTL: `retention_days * 86400` seconds
- MongoDB automatically deletes expired documents
- Index created at backend startup

## Database Indexes

| Index | Field | Purpose |
|-------|-------|---------|
| ttl_timestamp | timestamp | TTL expiration |
| ix_content_hash | content_hash | Dedup lookup |
| ix_entity | entity | Filter by entity |

## Apify Query Optimization

**Rule for Feature 7:** Do NOT run a scraper per entity.

- Build a single combined query: `"Sahi OR Zerodha OR Upstox OR Groww"`
- Detect entity in backend from post content
- Reduces scraping cost and avoids duplicate posts across entities

## Data Storage Rule

Store only essential fields. Do NOT store raw HTML or full scraper responses.

Example document:

```json
{
  "platform": "twitter",
  "entity": "Sahi",
  "text": "Sahi trading app is amazing",
  "url": "https://twitter.com/post",
  "content_hash": "abc123",
  "engagement": { "likes": 45, "retweets": 12 },
  "timestamp": "2026-03-10"
}
```
