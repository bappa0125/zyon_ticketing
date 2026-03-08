# Project Structure

```
zyon_ai_ticketing/
├── config/
│   ├── dev.yaml          # Development config
│   ├── prod.yaml         # Production config
│   └── clients.yaml      # Monitored clients and competitors (governance-driven)
├── docker/
│   └── nginx.conf        # Nginx reverse proxy config
├── docs/
│   ├── ARCHITECTURE.md
│   ├── PROJECT_STRUCTURE.md
│   ├── FEATURE_REGISTRY.md    # Feature registry — read before new features
│   ├── SYSTEM_GUARDRAILS.md   # Architecture and performance rules
│   ├── SYSTEM_SPEC.md         # Subsystems and monitoring spec
│   ├── CODE_OWNERSHIP_MAP.md  # Module ownership
│   ├── api/
│   ├── architecture/
│   └── features/
├── .cursor/
│   └── system_prompt.md   # Cursor instructions (read before implementing)
├── frontend/             # Next.js chat UI
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   └── lib/
│   ├── package.json
│   └── Dockerfile
├── backend/              # FastAPI
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   └── services/
│   ├── requirements.txt
│   └── Dockerfile
├── .github/
│   └── workflows/
│       └── ci-cd.yml
├── docker-compose.yml
└── README.md
```

## config/clients.yaml

External configuration for monitored clients and their competitors. Add or edit clients here without code changes. Used by the Client Monitoring feature and future monitoring modules (media, social, competitor intelligence, PR strategy).

## Governance documents

- **FEATURE_REGISTRY.md** — Tracks every implemented feature and owning files. Cursor must read before adding features.
- **SYSTEM_GUARDRAILS.md** — Architecture rules and performance constraints (e.g. Mac Mini M1, 16GB RAM).
- **SYSTEM_SPEC.md** — Conversational AI vs Monitoring Intelligence layers; config-driven monitoring.
- **CODE_OWNERSHIP_MAP.md** — Which paths own UI, APIs, core, services, models.

## Future monitoring modules

Planned modules that will consume `config/clients.yaml` and extend the Monitoring Intelligence Layer:

- Media monitoring
- Social monitoring
- Sentiment analysis
- PR strategy advisor
- Competitor intelligence

All must follow SYSTEM_GUARDRAILS and be registered in FEATURE_REGISTRY.md.
