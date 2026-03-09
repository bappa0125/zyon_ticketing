# Entity Detection Engine (multi-layer pipeline)

## Purpose

The Entity Detection Engine identifies mentions of monitored companies (clients and competitors) in text. It is used by social monitoring (Reddit, YouTube), URL discovery, and—when integrated—the article_documents → entity_mentions pipeline. To minimize cost and latency, detection is implemented as a **multi-layer pipeline** that runs deterministic layers first and uses the LLM only as a fallback.

## Pipeline order

1. **Ignore rules** — If the text matches a configured ignore pattern, entity detection is skipped (e.g. conversational Hindi like "sahi hai").
2. **Dictionary / alias matching** — Case-insensitive match of configured aliases against the text. Longest match wins.
3. **Regex pattern matching** — Lightweight regex over canonical entity names (word boundaries) to catch broker/trading/platform references.
4. **NER (Named Entity Recognition)** — spaCy (e.g. `en_core_web_sm`) detects ORG entities; any ORG that matches a monitored entity or its aliases is returned.
5. **Embedding fallback** — Only if no entity was detected in layers 1–4 **and** the text contains finance-related context keywords. Uses the **same embedding model as the rest of the app** (e.g. SentenceTransformers `all-MiniLM-L6-v2`): embed the text and "article about [Entity]" for each entity; return the entity with highest cosine similarity above a threshold. **No OpenRouter or LLM call** by default.
6. **Optional LLM fallback** — If `monitoring.entity_detection.use_llm_fallback` is `true` in config and embedding did not find an entity, OpenRouter LLM can be used with a strict classification prompt. Disabled by default.

Deterministic layers (1–4) run first; Layer 5 uses the existing embedding model so no extra API key is needed. LLM is optional and off by default.

## When embedding / LLM fallback is used

Layer 5 (embedding) runs only when:

- No entity was detected by ignore/alias/regex/NER, and  
- The text contains at least one **finance context keyword** (e.g. `trading`, `broker`, `demat`, `stock app`, `derivatives`, `investment platform`).

If the text has no finance context, the pipeline returns `None` without calling the embedding or LLM. The embedding model is the same one used for intent classification and chat (no OpenRouter). Optional LLM fallback requires `use_llm_fallback: true` in `monitoring.entity_detection` and `OPENROUTER_API_KEY`.

## Configuration

### clients.yaml

- **ignore_patterns** (per client): Phrases that cause detection to be skipped for that segment (e.g. "sahi hai", "bilkul sahi").
- **aliases** (per client): Phrases that map to the client or competitor name (e.g. "sahi trading", "sahi trading app").
- **competitors**: List of competitor names; their aliases can be defined in `monitoring.yaml` under `entity_detection.entity_aliases`.

### monitoring.yaml (entity_detection)

- **ignore_patterns**: Global ignore patterns (merged with per-client patterns from clients.yaml).
- **entity_aliases**: Map of entity name → list of aliases (e.g. Zerodha → ["zerodha", "zerodha kite", "kite app"]).
- **use_llm_fallback** (optional, default `false`): If `true`, when embedding layer finds no entity, call OpenRouter LLM for classification. Requires `OPENROUTER_API_KEY`.

Ignore rules and aliases are loaded from both `config/clients.yaml` and `config/monitoring.yaml` through the existing configuration system.

## Detection confidence and detection source tracking

When writing to **entity_mentions**, the service can provide two optional fields for reliability and observability:

- **confidence** — Score by detection layer (higher = more reliable):
  - Alias: `0.95`
  - Regex: `0.85`
  - NER: `0.75`
  - Embedding: `0.70`
  - LLM: `0.65`
- **detected_by** — Which layer identified the entity: `alias`, `regex`, `ner`, `embedding`, or `llm`.

Use **detect_entity(text, with_metadata=True)** or **detect_entity_async(text, with_metadata=True, article_url=...)** to get an **EntityDetectionResult(entity, confidence, detected_by)**. When storing a mention in `entity_mentions`, set:

- `confidence`: `result.confidence`
- `detected_by`: `result.detected_by`

Existing fields in `entity_mentions` are unchanged; these are additive. Queries that do not filter on `confidence` or `detected_by` continue to work.

## API

- **detect_entity(text, stats=None, with_metadata=False)** — Synchronous, layers 1–4. Returns entity or `None`; if `with_metadata=True` returns **EntityDetectionResult(entity, confidence, detected_by)**.
- **detect_entity_async(text, stats=None, with_metadata=False, article_url=None)** — Full pipeline. Optional **article_url** enables LLM result cache (Redis or in-memory) to avoid repeated LLM calls for the same article. With `with_metadata=True` returns **EntityDetectionResult**.
- **detect_entity_with_metadata(text, stats=None)** — Convenience: sync detection returning **EntityDetectionResult** for entity_mentions.
- **get_entities_and_aliases()** — Returns the entity → aliases map (unchanged).
- **ensure_initialized()** — Call once at service start to precompile alias dictionary and regex.
- **log_detection_run_stats(stats)** — Logs detection metrics and a batch summary (see Logging).

## Logging

- **Per detection (debug):** `entity_detection_stage` with `stage` (alias, regex, ner, embedding, llm) and `entity`.
- **Batch run:** Set **stats["articles_scanned"]** to the number of articles processed, then call **log_detection_run_stats(stats)**. Logged:
  - **entity_detection_run_stats**: `articles_scanned`, `alias_matches`, `regex_matches`, `ner_matches`, `llm_matches`, `by_embedding`.
  - **entity_detection_batch_summary**: human-readable line, e.g.  
    `Articles scanned: 100 | Alias matches: 74 | Regex matches: 8 | NER matches: 10 | LLM fallback matches: 3`

## Pipeline position

The pipeline remains:

- **article_documents** → entity_detection_service → **entity_mentions**

The schema of `entity_mentions` is unchanged. Only the detection logic inside `entity_detection_service` is refactored; ingestion, RSS, and article fetching are not modified.

## Performance and initialization

- **Precompiled alias dictionary:** At first use (or when **ensure_initialized()** is called), aliases from `clients.yaml` and `monitoring.yaml` are loaded, normalized to lowercase, and built into a single lookup list sorted by alias length (longest first) so that each article does not rebuild patterns.
- **Single compiled regex:** All monitored entity names are combined into one regex with word boundaries and case-insensitive matching (e.g. `\b(Zerodha|Upstox|Groww|Angel One)\b`), compiled once at initialization.
- **LLM result cache:** When **detect_entity_async(..., article_url=...)** is used, the LLM result for that article is cached by `article_url` hash. Redis is used if available (key `entity_detection_llm:{hash}`, TTL 24h); otherwise an in-memory cache with bounded size is used. This avoids duplicate LLM calls when the same article is reprocessed.

## Dependencies

- **Embedding (Layer 5):** Same as the rest of the app — SentenceTransformers (e.g. `all-MiniLM-L6-v2`). No OpenRouter. Optional `HF_TOKEN` for Hugging Face if needed.
- **spaCy:** A small model such as `en_core_web_sm` is used for NER. Install with `pip install spacy` and `python -m spacy download en_core_web_sm`. If the model is not available, the NER layer is skipped.
- **LLM:** OpenRouter is used only when `use_llm_fallback: true` in `monitoring.entity_detection` and embedding did not find an entity.

## Files

| File | Role |
|------|------|
| `backend/app/services/entity_detection_service.py` | Multi-layer detection (ignore, alias, regex, NER, LLM fallback). |
| `config/clients.yaml` | Per-client ignore_patterns and aliases. |
| `config/monitoring.yaml` | entity_detection.ignore_patterns and entity_aliases. |

## Deploy and test

### Where this lives in the project (Docker Compose)

- **Project root** = directory that contains `docker-compose.yml` (e.g. `zyon_ai_ticketing/`).
- **Entity detection** runs inside the **backend** service. Config is loaded from `config/` (mounted into the image at build time).

Relevant parts of the project:

| Path | Purpose |
|------|--------|
| `docker-compose.yml` | Defines `backend`, `mongodb`, `redis`, etc. Run all commands from this directory. |
| `config/clients.yaml` | Clients, `aliases`, `ignore_patterns` for entity detection. |
| `config/monitoring.yaml` | `monitoring.entity_detection` (ignore_patterns, entity_aliases, use_llm_fallback). |
| `backend/` | Backend app; `backend/app/services/entity_detection_service.py` is the detection engine. |
| `backend/Dockerfile` | Builds backend image; copies `config/` and `backend/app/` into the container. |

The **backend** service in `docker-compose.yml` gets `MONGODB_URL`, `REDIS_URL`, `OPENROUTER_API_KEY`, etc. from `.env`. Redis is used for the LLM result cache when available.

---

### Docker Compose: deploy

Run every command from the **project root** (same folder as `docker-compose.yml`).

**1. Config and env**

- Ensure `config/clients.yaml` and `config/monitoring.yaml` exist and at least one client has `aliases`.
- Optional: copy `.env.example` to `.env` and set `OPENROUTER_API_KEY` if you use LLM fallback (`use_llm_fallback: true` in `monitoring.entity_detection`).

**2. Build and start dependencies**

```bash
docker compose build backend
docker compose up -d mongodb redis
```

**3. (Optional) Run full stack**

```bash
docker compose up -d
```

---

### Docker Compose: test

From the **project root**:

**1. Smoke test (sync detection)**

```bash
docker compose run --rm backend python -c "
from app.services.entity_detection_service import detect_entity, get_entities_and_aliases
assert get_entities_and_aliases(), 'entities loaded'
assert detect_entity('Sahi trading app is great') == 'Sahi'
assert detect_entity('bilkul sahi hai') is None
assert detect_entity('Zerodha broker review') in ('Zerodha', None)
print('Entity detection OK')
"
```

**2. Test with metadata (confidence, detected_by)**

```bash
docker compose run --rm backend python -c "
from app.services.entity_detection_service import detect_entity_with_metadata
r = detect_entity_with_metadata('Sahi trading app is great')
print('entity:', r.entity, 'confidence:', r.confidence, 'detected_by:', r.detected_by)
assert r.entity == 'Sahi' and r.detected_by == 'alias' and r.confidence == 0.95
print('Metadata OK')
"
```

**3. Test async (embedding fallback; no OpenRouter needed)**

```bash
docker compose run --rm backend python -c "
import asyncio
from app.services.entity_detection_service import detect_entity_async
async def main():
    r = await detect_entity_async('This article discusses trading and brokers in India.')
    print('detect_entity_async:', r)
asyncio.run(main())
"
```

**4. Test batch stats and ensure_initialized**

```bash
docker compose run --rm backend python -c "
from app.services.entity_detection_service import ensure_initialized, detect_entity, log_detection_run_stats
ensure_initialized()
stats = {'articles_scanned': 3}
detect_entity('Sahi trading app', stats=stats)
detect_entity('Zerodha broker', stats=stats)
detect_entity('random text', stats=stats)
log_detection_run_stats(stats)
print('Batch stats OK')
"
```

**5. (Optional) NER in Docker**

In `backend/Dockerfile`, after the `pip install` line, add:

```dockerfile
RUN python -m spacy download en_core_web_sm
```

Then: `docker compose build backend`.

---

### Deployment (non-Docker)

1. **Config**
   - Ensure `config/clients.yaml` has at least one client with `aliases` and optional `ignore_patterns`.
   - Ensure `config/monitoring.yaml` has `monitoring.entity_detection` with optional `ignore_patterns` and `entity_aliases`. Layer 5 uses the app embedding model (no OpenRouter). For optional LLM fallback set `use_llm_fallback: true` and `OPENROUTER_API_KEY`.

2. **Dependencies**
   - `pip install -r backend/requirements.txt` (includes `spacy`).
   - **Optional (for NER):** Download the spaCy model so Layer 4 is active:
     ```bash
     python -m spacy download en_core_web_sm
     ```
     If the model is not installed, the NER layer is skipped and alias/regex still run.

3. **Docker**
   - From project root, build and run as usual. Config is copied into the image via `COPY config/ ./config/`.
   - To enable NER in Docker, add after `pip install` in `backend/Dockerfile`:
     ```dockerfile
     RUN python -m spacy download en_core_web_sm
     ```
     Then rebuild the backend image.

4. **Local (no Docker)**
   - From project root, set `PYTHONPATH` to the backend directory and ensure `config/` is on the config path (e.g. run from repo root or copy/symlink `config` into `backend`). No need to start MongoDB/Redis for testing `detect_entity()` alone.

### Testing

1. **Smoke test (sync, no LLM)**  
   Run in project root (with venv activated and `PYTHONPATH` set to backend, or from `backend` with `PYTHONPATH=.`):
   ```bash
   cd backend
   export PYTHONPATH=$PWD
   python -c "
   from app.services.entity_detection_service import detect_entity, get_entities_and_aliases
   assert get_entities_and_aliases(), 'entities loaded'
   assert detect_entity('Sahi trading app is great') == 'Sahi'
   assert detect_entity('bilkul sahi hai') is None
   assert detect_entity('Zerodha broker review') in ('Zerodha', None)
   print('OK')
   "
   ```

2. **Layer 1 (ignore)**  
   - `detect_entity('sahi hai')` → `None`.  
   - `detect_entity('bilkul sahi')` → `None` (if in ignore_patterns).

3. **Layer 2 (alias)**  
   - `detect_entity('sahi trading app looks good')` → `Sahi`.  
   - Use a phrase that is in `clients.yaml` aliases for a client or in `entity_aliases` for a competitor.

4. **Layer 3 (regex)**  
   - `detect_entity('Zerodha and Upstox are brokers')` → first matched entity (e.g. Zerodha or Upstox).  
   - Confirms canonical names are matched by word-boundary regex.

5. **Layer 4 (NER, optional)**  
   - Only runs if `en_core_web_sm` is installed.  
   - Use a sentence where the company appears as an ORG (e.g. “Apple and Zerodha announced a partnership”). If Zerodha is in the entity list and NER labels it as ORG, it should be detected.

6. **Batch stats**  
   - Pass a shared `stats={}` into multiple `detect_entity(..., stats=stats)` calls, then call `log_detection_run_stats(stats)` and check logs for `by_alias`, `by_regex`, `by_ner`.

7. **Async + LLM fallback (optional)**  
   - Requires `OPENROUTER_API_KEY` and finance context in the text. Example (run in async context):
     ```python
     import asyncio
     from app.services.entity_detection_service import detect_entity_async
     async def main():
         r = await detect_entity_async('Article about trading platforms and new brokers.')
         # May return an entity if LLM finds one; or None
     asyncio.run(main())
     ```
   - With no finance keywords, `detect_entity_async` should return `None` without calling the LLM.

8. **Integration**  
   - Run Reddit or YouTube worker (or any flow that uses `detect_entity(text)`). Confirm no regressions and that logs show `entity_detection_stage` when debug logging is enabled.

## Related

- **Feature 7.0 — Entity Alias Detection:** Original alias/ignore design; see `docs/features/entity_alias_detection.md`.
- **Reddit / YouTube monitoring:** Use `detect_entity(text)` (sync, no LLM).
