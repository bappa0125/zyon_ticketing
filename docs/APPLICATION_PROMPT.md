# Zyon AI Chatbot — Complete Application Description

Use this document as a prompt to fully understand the application. It describes the tech stack, architecture, intent, and implementation details.

---

## Intent & Purpose

**Zyon AI Chatbot** is a ChatGPT-style conversational AI application designed to:

1. **Provide AI-powered chat** — Users interact with an LLM (via OpenRouter) through a streaming chat interface.
2. **Maintain conversation memory** — Store and retrieve chat history per conversation in MongoDB.
3. **Use semantic context** — Use vector embeddings (Qdrant) to find relevant past messages and inject them into the LLM prompt for better coherence.
4. **Run fully locally or in the cloud** — Docker-based stack that runs on a developer’s machine or a production server with one command.
5. **Support multiple LLM models** — OpenRouter allows switching between GPT, Claude, and other models without code changes.

**Target users:** Developers, internal teams, or anyone needing a private, self-hosted AI chat with memory and semantic retrieval.

---

## Tech Stack

| Layer | Technology | Version / Notes |
|-------|------------|------------------|
| **Reverse proxy** | Nginx | Alpine, port 80 |
| **Frontend** | Next.js | 14.x, React 18, TypeScript |
| **Styling** | Tailwind CSS | v3 |
| **Backend** | FastAPI | Python 3.11 |
| **Chat history** | MongoDB | 7, Motor (async driver) |
| **Vector DB** | Qdrant | Latest |
| **Cache** | Redis | 7 Alpine |
| **LLM provider** | OpenRouter | GPT-3.5-turbo (default), model switchable |
| **Embeddings** | sentence-transformers | all-MiniLM-L6-v2 (384 dims) |
| **Deployment** | Docker Compose | All services containerized |

---

## Architecture

```
                         NGINX (Port 80)
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    FRONTEND             BACKEND
    Next.js              FastAPI
    Port 3000            Port 8000
          │                   │
          └───────────────────┘
                    │
    ┌───────────────┼───────────────┬───────────────┐
    ▼               ▼               ▼               ▼
  MongoDB         Qdrant          Redis       OpenRouter
  (history)     (embeddings)     (cache)        (LLM API)
```

**Flow:** User → Frontend → Nginx → Backend → MongoDB + Qdrant + OpenRouter → Streamed response.

---

## Component Roles

| Component | Responsibility |
|-----------|----------------|
| **Nginx** | Routes `/` to frontend, `/api/*` to backend, `/health`, `/metrics` to backend |
| **Frontend** | Chat UI, sidebar, markdown rendering, streaming, calls `/api/chat`, `/api/new-chat`, `/api/history/{id}` |
| **Backend** | Orchestrates chat: store/retrieve messages, query Qdrant, build prompt, call OpenRouter, stream response |
| **MongoDB** | Stores `conversations` and `messages` (conversation_id, role, content, timestamp) |
| **Qdrant** | Stores embeddings of messages; semantic search returns relevant past context |
| **Redis** | Caching (conversation summaries, optional) |
| **OpenRouter** | LLM API; supports streaming and model switching |

---

## Prompt Pipeline

When the user sends a message, the backend builds the LLM prompt as:

1. **System prompt** — Fixed instructions for the assistant
2. **Conversation summary** — Optional, from Redis
3. **Vector context** — Relevant past messages from Qdrant (semantic search)
4. **Last N messages** — Recent turn-by-turn context from MongoDB
5. **User message** — Current input

---

## API Contract

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Send message, stream response (text/plain) |
| GET | `/api/history/{conversation_id}` | Get all messages for a conversation |
| POST | `/api/new-chat` | Create new conversation, return `conversation_id` |
| GET | `/health` | Liveness |
| GET | `/health/ready` | Readiness (MongoDB, Redis, Qdrant) |
| GET | `/metrics` | Prometheus metrics |

---

## Data Schemas

**MongoDB**
- `conversations`: `_id`, `title`, `created_at`, `updated_at`
- `messages`: `_id`, `conversation_id`, `role`, `content`, `timestamp`

**Qdrant**
- Collection: `chat_embeddings`
- Payload: `conversation_id`, `message_id`, `role`, `content`
- Vector size: 384 (all-MiniLM-L6-v2)

---

## Configuration

- **config/dev.yaml** — Local development (MongoDB, Redis, Qdrant URLs for Docker)
- **config/prod.yaml** — Production (env vars: MONGODB_URL, REDIS_URL, QDRANT_URL, OPENROUTER_API_KEY)
- **Env vars:** `OPENROUTER_API_KEY` (required), `OPENROUTER_MODEL` (default: openai/gpt-3.5-turbo)

---

## Project Structure

```
zyon_ai_ticketing/
├── config/           # dev.yaml, prod.yaml
├── docker/           # nginx.conf
├── frontend/         # Next.js app, src/app, src/components
├── backend/          # FastAPI app, api/, services/, core/
├── docs/             # ARCHITECTURE, DEPLOY, this prompt
├── docker-compose.yml
└── .github/workflows/
```

---

## Observability

- **Logging:** Structured JSON (structlog)
- **Request IDs:** Propagated in middleware
- **Health:** `/health`, `/health/ready`
- **Metrics:** Prometheus `/metrics`

---

## Deployment

- **Local:** `docker compose up --build`
- **Production:** `docker-compose.deploy.yml` uses pre-built images from GHCR; GitHub Actions SSH deploys to a server on push to `develop`.

---

## Summary

Zyon AI Chatbot is a self-hosted, ChatGPT-like app that combines:
- **Next.js** for the UI
- **FastAPI** for the API
- **MongoDB** for conversation history
- **Qdrant** for semantic memory
- **OpenRouter** for LLM access

It aims to provide a private, controllable AI assistant with streaming responses, persistent context, and semantic retrieval over past conversations.
