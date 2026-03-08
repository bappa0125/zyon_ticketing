# Topic Detection Engine

## Purpose

Detect key topics in media coverage for monitored companies. Uses KeyBERT for lightweight keyword extraction to surface narratives surrounding clients and competitors.

## Data Flow

```
MongoDB media_articles (title, snippet, entity, client, …)
        │
        ▼
topic_worker.run_topic_detection()
        │
        ├── filter: topics field does not exist
        ├── batch size: max 20 articles
        ├── topic_service.extract_topics(title + " — " + snippet)
        │       KeyBERT: top 3 topics per article
        │
        ▼
MongoDB update: topics
        │
        ▼
GET /api/topics?client=Sahi
        │
        ▼
Frontend /topics page → TopicTable
```

## Pipeline

1. **Media monitoring** collects articles into `media_articles` (title, snippet, entity, client).
2. **Topic worker** processes articles without `topics`; extracts top 3 topics via KeyBERT; updates MongoDB.
3. **Topics API** aggregates topic mentions; optional filter by client.

## Data Fields

| Field | Type | Description |
|-------|------|-------------|
| topics | array of string | Top 3 topic phrases per article |

## Performance Constraints

- Mac Mini M1, 16GB RAM
- KeyBERT with all-MiniLM-L6-v2: lightweight model
- Max batch size: 20 articles per run
- Process only articles without `topics` field
