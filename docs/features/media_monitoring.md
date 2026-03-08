# Media Monitoring Engine

## System Purpose

Collect news mentions of monitored clients and their competitors. Configuration-driven via `config/clients.yaml`. Lightweight: uses Google News RSS and DuckDuckGo, no heavy crawling or headless browsers.

## Data Flow

```
config/clients.yaml
        │
        ▼
media_monitor_worker.run_media_monitor()
        │
        ├── load_clients()
        ├── For each client + competitor:
        │       search_entity() → Google News RSS, DuckDuckGo
        │       deduplicate by URL
        │       validate entity in title/snippet (no page fetch)
        │
        ▼
MongoDB media_articles
        │
        ▼
GET /api/media/latest?client=Sahi
        │
        ▼
Frontend /media page → MediaTable
```

## Sources Used

| Source       | Type    | Limit per entity |
|-------------|---------|-------------------|
| Google News | RSS     | 10 articles       |
| DuckDuckGo  | Search  | 10 articles       |

## Performance Constraints

- Run monitoring every 15 minutes (invoke `run_media_monitor()` via scheduler)
- 10 articles per source per entity
- Max 2 concurrent sources
- Entity validation via title/snippet only (no page fetch)
- Deduplicate by URL before insert
