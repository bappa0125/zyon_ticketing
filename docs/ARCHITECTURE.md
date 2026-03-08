# AI Chatbot Platform — Architecture Design

## Overview

A ChatGPT-style application with streaming, vector memory, conversation history, and full observability. Deployable locally via Docker and to AWS via Terraform.

---

## High-Level Architecture

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                      NGINX (Reverse Proxy)               │
                    │                   Port 80 / 443                          │
                    └─────────────────────┬───────────────────────────────────┘
                                          │
              ┌───────────────────────────┼───────────────────────────┐
              │                           │                           │
              ▼                           ▼                           ▼
    ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
    │   FRONTEND      │         │    BACKEND      │         │  (Direct API)   │
    │   Next.js       │         │    FastAPI      │         │                 │
    │   Port 3000     │         │   Port 8000     │         │                 │
    └────────┬────────┘         └────────┬────────┘         └─────────────────┘
             │                           │
             │  /api/* proxied           │
             └───────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┬───────────────────┐
         │                   │                   │                   │
         ▼                   ▼                   ▼                   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  MongoDB    │    │   Qdrant    │    │   Redis     │    │ OpenRouter  │
│  :27017     │    │   :6333     │    │   :6379     │    │   (API)     │
│  History    │    │  Vectors    │    │   Cache     │    │   LLM       │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

---

## Component Responsibilities

| Component | Purpose |
|-----------|---------|
| **Nginx** | Reverse proxy, route `/api/*` → backend, static assets → frontend |
| **Frontend** | Next.js chat UI, streaming, markdown, conversation sidebar |
| **Backend** | FastAPI: chat, history, new-chat, orchestrate LLM + vectors + DB |
| **MongoDB** | `conversations`, `messages` — persistent chat history |
| **Qdrant** | Vector embeddings, semantic search for context retrieval |
| **Redis** | Cache for responses, session data, rate limiting |
| **OpenRouter** | LLM gateway — streaming, model switching |

---

## Data Flow: Chat Request

1. User sends message → Frontend POST `/api/chat`
2. Nginx proxies to Backend
3. Backend:
   - Stores user message in MongoDB
   - Queries Qdrant for relevant context (embeddings)
   - Optional: fetch conversation summary from Redis
   - Builds prompt: system + summary + last messages + vector context + user message
   - Calls OpenRouter (streaming)
   - Streams response to frontend
   - Stores assistant message in MongoDB
   - Updates Qdrant with new embeddings

---

## Prompt Pipeline

```
┌─────────────────┐
│ System Prompt   │  (fixed instructions, behavior)
├─────────────────┤
│ Conv Summary    │  (optional, from Redis/cache)
├─────────────────┤
│ Last N Messages │  (recent context from MongoDB)
├─────────────────┤
│ Vector Context  │  (relevant past messages from Qdrant)
├─────────────────┤
│ User Message    │  (current input)
└─────────────────┘
```

---

## API Contract

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Send message, receive streamed response |
| GET | `/api/history/{conversation_id}` | Get messages for a conversation |
| POST | `/api/new-chat` | Create new conversation, return ID |

---

## MongoDB Schema

**conversations**
- `_id`, `title`, `created_at`, `updated_at`, `user_id` (optional)

**messages**
- `_id`, `conversation_id`, `role` (user/assistant/system), `content`, `timestamp`

---

## Qdrant Schema

- Collection: `chat_embeddings`
- Vectors: lightweight model (e.g. `all-MiniLM-L6-v2` or OpenRouter embedding)
- Payload: `conversation_id`, `message_id`, `content`, `role`, `timestamp`

---

## Observability

- **Logging**: Structured JSON logs (request_id, level, message, duration)
- **Tracing**: Request IDs propagated across services
- **Health**: `/health` (liveness), `/health/ready` (MongoDB, Redis, Qdrant)
- **Metrics**: `/metrics` (Prometheus format — request counts, latencies)

---

## Deployment Targets

| Environment | Method |
|-------------|--------|
| Local | `docker compose up` |
| AWS | Terraform → EC2, same Docker images, CloudWatch, health checks |
