# Monitoring Extension Architecture

## Overview

The Client Monitoring Configuration introduces a configuration layer that will extend the Zyon chatbot architecture for future monitoring phases.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         EXISTING CHAT SYSTEM                             │
├─────────────────────────────────────────────────────────────────────────┤
│  Nginx → Frontend (Next.js) → Backend (FastAPI) → OpenRouter/MongoDB/   │
│          Qdrant/Redis                                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ (unchanged)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    CLIENT CONFIGURATION LAYER                            │
├─────────────────────────────────────────────────────────────────────────┤
│  config/clients.yaml                                                     │
│       │                                                                  │
│       ▼                                                                  │
│  client_config_loader.py ──► Redis (clients_config, TTL 300s)           │
│       │                                                                  │
│       ▼                                                                  │
│  GET /api/clients                                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ feeds
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   FUTURE MONITORING WORKERS (Phase 2+)                    │
├─────────────────────────────────────────────────────────────────────────┤
│  • Media monitoring worker (reads clients + competitors)                 │
│  • Social monitoring worker                                              │
│  • Competitor intelligence engine                                        │
│  • PR strategy engine                                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

## Design Principles

- **No modification** to existing chat functionality
- **Configuration-first** — clients defined in YAML
- **Modular** — monitoring workers consume `/api/clients` or loader directly
- **Low footprint** — Redis cache, single file read, no heavy workers
