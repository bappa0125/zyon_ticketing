# Client Monitoring Configuration

## Feature Purpose

Configuration-driven system for defining monitored clients and their competitors. This configuration will later be used by:

- Media monitoring
- Social monitoring
- Competitor intelligence
- PR strategy engine

## System Design

```
config/clients.yaml
        │
        ▼
client_config_loader.py
        │
        ├── Redis cache (clients_config, TTL 300s)
        │
        ▼
GET /api/clients
        │
        ▼
Frontend (clients/page.tsx)
        │
        ▼
ClientTable component
```

- **External config**: `config/clients.yaml` — add clients without code changes
- **Loader**: `backend/app/core/client_config_loader.py` — reads YAML, caches in Redis
- **API**: `GET /api/clients` — returns clients JSON
- **UI**: `/clients` page with table

## Configuration Example

```yaml
clients:
  - name: Sahi
    domain: sahi.com
    competitors:
      - Zerodha
      - Upstox
      - Groww
```

## Future Monitoring Use Cases

1. **Media monitoring** — use `competitors` for news/mention tracking
2. **Social monitoring** — track mentions of clients and competitors on social platforms
3. **Competitor intelligence** — compare coverage, sentiment, share of voice
4. **PR strategy engine** — recommend actions based on competitor activity
