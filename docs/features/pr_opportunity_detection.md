# PR Opportunity Detection Engine

## Purpose

Detect topics where competitors receive media coverage but the client does not. Surfaces PR opportunities: areas where the client could gain visibility by engaging on topics competitors already dominate.

## Topic Comparison Logic

For each topic (from `media_articles.topics`):

- **client_mentions**: count of articles where `entity == client_name`
- **competitor_mentions**: count of articles where `entity in competitors`

**Opportunity** = topic where `competitor_mentions > 0` and `client_mentions == 0`.

Results sorted by `competitor_mentions` descending; top 20 returned.

## Data Pipeline

```
config/clients.yaml (client + competitors)
        │
        ▼
opportunity_service.detect_pr_opportunities(client)
        │
        ├── load_clients() → client_name, competitors
        ├── MongoDB aggregation:
        │       $match: entity in [client, ...competitors], topics exists
        │       $unwind: topics
        │       $group: by topic, client_mentions, competitor_mentions
        │       $match: competitor_mentions > 0, client_mentions == 0
        │       $sort, $limit: 20
        │
        ▼
GET /api/opportunities?client=Sahi
        │
        ▼
Frontend /opportunities page → OpportunityTable
```

## Performance Constraints

- Mac Mini M1, 16GB RAM
- MongoDB aggregation only; no full dataset in memory
- Top 20 opportunities returned
