# Monitoring Ingestion Pipeline

## Purpose

Unified pipeline for loading configuration and (in later steps) ingesting monitoring data from configured media sources and clients. Implemented in strict steps; only the current step is implemented.

## Pipeline Steps

| Step | Description | Status |
|------|-------------|--------|
| **STEP 1** | Pipeline configuration: load clients, monitoring config, media sources; expose `get_pipeline_config()` for downstream steps | Implemented |
| STEP 2 | _(Reserved; do not implement until instructed)_ | Pending |
| STEP 3+ | _(Reserved)_ | Pending |

## STEP 1 — Pipeline Configuration

### Scope

- **New modules only.** No changes to existing modules.
- **Read-only:** Load and expose configuration. No ingestion, no scheduling, no database writes.

### Files (new)

- `backend/app/services/monitoring_ingestion/__init__.py`
- `backend/app/services/monitoring_ingestion/pipeline_config.py`

### Behaviour

1. `get_pipeline_config()` returns a `PipelineConfig` with:
   - `monitored_entities`: names derived from `config/clients.yaml` (client names + competitors)
   - `clients`: raw list from `config/clients.yaml`
   - `media_sources`: list from `config/media_sources.yaml`
   - `ingestion_batch_size`: from `config/monitoring.yaml` → `monitoring.ingestion.batch_size` (default 20)
   - `enabled`: True

2. Config is loaded from files under `config/` (or `/app/config` in Docker). No Redis, no MongoDB.

3. Future steps will consume `get_pipeline_config()`; STEP 1 does not call any ingestion or existing media_ingestion modules.

### Usage

```python
from app.services.monitoring_ingestion import get_pipeline_config, PipelineConfig

cfg = get_pipeline_config()
# cfg.monitored_entities, cfg.clients, cfg.media_sources, cfg.ingestion_batch_size
```
