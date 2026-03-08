# Competitor Coverage Comparison

## Purpose

Compare media coverage between monitored clients and their competitors. Surfaces mention counts for the client and each competitor from `media_articles`, using `config/clients.yaml` for entity lists.

## Data Flow

```
config/clients.yaml (client + competitors)
        │
        ▼
coverage_service.compute_coverage(client)
        │
        ├── load_clients() → get client + competitors
        ├── entities = [client] + competitors
        │
        ▼
MongoDB media_articles aggregation
        │
        ├── $match: { entity: { $in: entities } }
        ├── $group: by entity, $sum: 1
        ├── $sort: mentions desc
        │
        ▼
GET /api/coverage/competitors?client=Sahi
        │
        ▼
Frontend /coverage page → CoverageChart
```

## Aggregation Logic

- Uses MongoDB aggregation pipeline; no large datasets loaded into memory.
- Matches documents where `entity` is in the configured entity list.
- Groups by `entity` and counts documents.
- Returns `[{ entity, mentions }, ...]` sorted by mentions descending.
- Entities with zero mentions are included in the response.

## Performance Constraints

- Mac Mini M1, 16GB RAM
- Aggregation performed in database
- Lightweight result set
