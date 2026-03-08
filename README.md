# Zyon AI Chatbot Platform

A ChatGPT-style AI chatbot with streaming responses, vector memory (Qdrant), conversation history (MongoDB), and OpenRouter LLM. Built with Next.js, FastAPI, and Docker. Run locally with a single command.

## Architecture

```
                         NGINX (Port 80)
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    FRONTEND             BACKEND              /api/*, /health
    Next.js              FastAPI
    (Port 3000)          (Port 8000)
                              │
          ┌───────────────────┼───────────────────┬───────────────────┐
          ▼                   ▼                   ▼                   ▼
      MongoDB              Qdrant               Redis            OpenRouter
    (conversations)      (embeddings)          (cache)              (LLM)
```

| Component   | Purpose                      |
|-------------|------------------------------|
| **Nginx**   | Reverse proxy, route /api → backend |
| **Frontend**| Next.js chat UI, markdown, streaming |
| **Backend** | FastAPI: chat, history, LLM orchestration |
| **MongoDB** | `conversations`, `messages` storage |
| **Qdrant**  | Vector embeddings, semantic search |
| **Redis**   | Cache                        |
| **OpenRouter** | LLM provider (GPT-3.5, Claude, etc.) |

**Data flow:** User message → MongoDB → Qdrant (context) → Prompt pipeline → OpenRouter → Stream response → MongoDB + Qdrant.

> Full architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Deploy: [docs/DEPLOY.md](docs/DEPLOY.md)

## Quick Start (Local)

1. **Install Docker Desktop** (if you don't have it):
   - https://www.docker.com/products/docker-desktop/

2. **Set your OpenRouter API key**
   ```bash
   export OPENROUTER_API_KEY=your_key_here
   ```

3. **Start all services**
   ```bash
   docker compose up --build
   ```

4. **Open the app**
   - **http://localhost** — use this URL (Nginx proxies frontend + API)
   - Avoid http://localhost:3000 for chat — API lives on port 80

> First build may take 5–10 minutes (sentence-transformers downloads models). Subsequent starts are faster.

## Architecture

| Component   | Purpose                  |
|-------------|--------------------------|
| **Nginx**   | Reverse proxy (port 80)  |
| **Frontend**| Next.js chat UI (3000)   |
| **Backend** | FastAPI API (8000)       |
| **MongoDB** | Conversation history     |
| **Redis**   | Cache                    |
| **Qdrant**  | Vector memory/embeddings |
| **OpenRouter** | LLM provider         |

## API Endpoints

- `POST /api/chat` — Send message, stream response
- `GET /api/history/{conversation_id}` — Get messages
- `POST /api/new-chat` — Create new conversation
- `GET /health` — Liveness | `GET /health/ready` — Readiness
- `GET /metrics` — Prometheus metrics

## Configuration

- `config/dev.yaml` — Local development
- `OPENROUTER_API_KEY` — Required for LLM

## Project Structure

```
├── config/     # dev.yaml, prod.yaml
├── docker/     # nginx.conf
├── frontend/   # Next.js
├── backend/    # FastAPI
└── .github/    # CI (lint, test, build)
```
