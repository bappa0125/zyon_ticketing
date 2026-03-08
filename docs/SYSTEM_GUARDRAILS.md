# Zyon AI System Guardrails

These rules must always be respected.

## Architecture rules

1. Do not modify the existing folder structure.
2. Do not refactor working modules.
3. Only add new modules.
4. Keep code modular.
5. Avoid breaking changes.

## Architecture stack

| Layer      | Technology   |
|-----------|--------------|
| Frontend  | Next.js      |
| Backend   | FastAPI      |
| Databases | MongoDB, Qdrant, Redis |
| LLM       | OpenRouter   |
| Deployment| Docker Compose |

## Performance constraints

**Development machine:** Mac Mini M1, 16GB RAM

Therefore:

- avoid heavy background workers
- avoid infinite loops
- limit concurrency
- prefer scheduled jobs
- use Redis caching
