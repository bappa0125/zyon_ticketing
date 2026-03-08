# Sentiment Analysis Engine

## Purpose

Analyze sentiment of media coverage for monitored companies. Extends the media monitoring pipeline by adding sentiment labels (positive, neutral, negative) to articles and providing aggregated summaries.

## Data Flow

```
MongoDB media_articles (title, snippet, entity, client, …)
        │
        ▼
sentiment_worker.run_sentiment_analysis()
        │
        ├── filter: sentiment field does not exist
        ├── batch size: max 20 articles
        ├── sentiment_service.analyze_sentiment(title + " — " + snippet)
        │       VADER: compound > 0.05 → positive, < -0.05 → negative, else neutral
        │
        ▼
MongoDB update: sentiment, sentiment_score
        │
        ▼
GET /api/sentiment/summary?client=Sahi
        │
        ▼
Frontend /sentiment page → SentimentChart
```

## Pipeline

1. **Media monitoring** collects articles into `media_articles` (title, snippet, entity, client).
2. **Sentiment worker** processes articles without `sentiment`; updates with `sentiment` and `sentiment_score`.
3. **Sentiment API** aggregates counts by entity; optional filter by client.

## Data Fields

| Field | Type | Description |
|-------|------|-------------|
| sentiment | string | "positive", "neutral", or "negative" |
| sentiment_score | float | VADER compound score (-1 to 1) |

## Performance Constraints

- Mac Mini M1, 16GB RAM
- VADER (vaderSentiment): lightweight, no transformers
- Max batch size: 20 articles per run
- Process only articles without `sentiment` field
