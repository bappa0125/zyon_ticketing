# Narrative Positioning — Deploy and Test

## Overview

Narrative Positioning is a PR-focused intelligence feature that produces per-client reports: narratives, positioning (headline, pitch angle, suggested outlets), threats, opportunities, and evidence refs. It uses 1 LLM call per client per day and stores results in the `narrative_positioning` collection.

## Deploy

### Docker Compose

```bash
cd /path/to/zyon_ai_ticketing
docker compose build backend frontend --no-cache
docker compose up -d
```

### What runs on startup

- Indexes for `narrative_positioning` are created via `ensure_ingestion_indexes()`
- Scheduler adds the `narrative_positioning` cron job (09:30 UTC daily) if `narrative_positioning.enabled` is true in config

### Config

In `config/dev.yaml` and `config/prod.yaml`:

```yaml
narrative_positioning:
  enabled: true
  llm:
    model: openrouter/free
```

## Test

### 1. Run pytest

```bash
# With Docker (mount backend to include tests)
docker compose run --rm -v "$(pwd)/backend:/app" -w /app backend python -m pytest tests/test_narrative_positioning.py -v --tb=short

# Or locally with venv
cd backend && pip install -r requirements.txt && python -m pytest tests/test_narrative_positioning.py -v --tb=short
```

### 2. Backfill (populate data)

```bash
# Option A: Inside container
docker compose exec backend python scripts/run_narrative_positioning_backfill.py

# Option B: If running locally
cd backend && python scripts/run_narrative_positioning_backfill.py
```

### 3. API

```bash
# Get reports for client (requires data from backfill)
curl -s "http://localhost:8000/api/social/narrative-positioning?client=Sahi&days=7" | python3 -m json.tool

# Run batch on demand
curl -X POST "http://localhost:8000/api/social/narrative-positioning/run-batch"
```

### 4. UI

1. Open `http://localhost:3000/social/narrative-intelligence`
2. Select client (e.g. Sahi)
3. Click **Refresh** to load from API
4. Click **Run batch** to trigger the batch job (requires OPENROUTER_API_KEY)

## Expected behaviour

- **API empty client**: `?client=` returns `{"reports": []}`
- **API with client**: Returns last N days of reports from `narrative_positioning`
- **Run batch**: Processes all clients, 1 LLM call each, upserts by (client, date)
- **Scheduler**: Runs at 09:30 UTC daily when enabled

## Dependencies

- Requires `narrative_intelligence_daily`, `narrative_shift`, Reddit/YouTube summaries, `entity_mentions`, `article_documents`, `social_posts` for best results (gathered automatically by the service)
- OPENROUTER_API_KEY must be set for the batch job to call the LLM
