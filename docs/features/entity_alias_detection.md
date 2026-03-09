# Entity Alias Detection (Feature 7.0)

## Purpose

Improve entity detection accuracy and avoid false positives (e.g. "Sahi" as Hindi word meaning "correct"). The detection logic has been extended to a **multi-layer pipeline** (ignore → alias → regex → NER → LLM fallback). See **docs/features/entity_detection.md** for the full pipeline, configuration, and when the LLM is used.

## Configuration

**clients.yaml** — optional `aliases` per client:
```yaml
clients:
  - name: Sahi
    aliases:
      - sahi trading
      - sahi trading app
      - sahi derivatives
```

**monitoring.yaml** — `entity_detection`:
```yaml
entity_detection:
  ignore_patterns:
    - sahi hai
    - bilkul sahi
    - sahi bola
  entity_aliases:
    Zerodha: [zerodha, zerodha kite, kite app]
```

## Pipeline

1. **normalize text** — strip, lower
2. **check ignore_patterns** — if text contains phrase, return None
3. **search aliases** — match entity aliases in text (longest match wins)
4. **return canonical entity** — or None

## Usage

```python
from app.services.entity_detection_service import detect_entity

entity = detect_entity("Sahi trading app looks promising")
# -> "Sahi"

entity = detect_entity("bilkul sahi hai")
# -> None (ignore_pattern)
```
