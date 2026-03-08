# Zyon AI Ticketing — Features & Architectural Stack

A prompt summarizing the features developed to date and the full architectural stack for the Zyon AI chatbot platform.

---

## Architectural Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Reverse Proxy** | Nginx (Alpine) | Port 80, route `/api/*` → backend, streaming (`proxy_buffering off`), WebSocket upgrade |
| **Frontend** | Next.js (standalone) | Chat UI, streaming responses, markdown (ReactMarkdown), conversation sidebar, API proxy rewrite |
| **Backend** | FastAPI (Python 3.11) | REST API, chat streaming, LLM orchestration, media search, coverage APIs |
| **LLM** | OpenRouter | Multi-model gateway (GPT-3.5, Claude, Perplexity Sonar for web search) |
| **Embedding** | Sentence Transformers (all-MiniLM-L6-v2) | 384-dim vectors for semantic search, intent detection |
| **Vector DB** | Qdrant | `chat_embeddings` (conversations), `page_embeddings` (crawler), semantic retrieval |
| **Document DB** | MongoDB 7 | `conversations`, `messages`, `media_articles`, `mention_alerts` |
| **Cache** | Redis 7 | Rate limiting, session cache |
| **Search** | Google News RSS, Tavily, DuckDuckGo | Live web/news search, article discovery |
| **Workers** | media_index_worker, crawler_worker | Background jobs for media ingestion and page crawling |
| **Deployment** | Docker Compose | All services containerized, volumes for persistence |

---

## Developed Features

### 1. AI Chat with Streaming
- Streaming responses via SSE-style plain text
- OpenRouter LLM gateway (model switching, streaming)
- Perplexity Sonar fallback when live search returns no results
- Mock LLM mode (`MOCK_LLM=1`) for testing without API keys
- Chat input unfreezes on first chunk (`setLoading(false)`)
- Background MongoDB + Qdrant storage (non-blocking stream close)

### 2. Live Search First
- **Intent**: Embedding-based intent detection (cosine similarity to “article search” examples)
- **Flow**: Always run live search first for substantive messages; fall back to LLM when no results
- **Search query extraction**: Regex entity extraction (“articles about X”) + cleaned message fallback

### 3. Media Mention Search
- Internal media index (MongoDB/Qdrant)
- Google News RSS (no API key)
- Tavily (optional `TAVILY_API_KEY`)
- DuckDuckGo fallback (no API key)
- Deduplication, validation (fetch page, verify entity), quality scoring
- Optional LLM rerank
- Entity aliases (e.g. Shahrukh Khan → SRK, Shah Rukh)
- Broader search: news, articles, blogs

### 4. Guaranteed Article Links
- Backend formats search results directly (no LLM formatting)
- Markdown `[Title](URL)` for every article
- Source, date, snippet included

### 5. Coverage & Media Intelligence APIs
- `GET /api/alerts` — Mention alerts from `mention_alerts`
- `GET /api/coverage/timeline?company=X` — Coverage timeline
- `GET /api/coverage/compare?companies=X,Y,Z` — Competitor comparison
- `GET /api/coverage/topics?company=X` — Trending topics
- Sentiment analysis (rule-based: positive/negative/neutral)

### 6. Conversation & Memory
- MongoDB: conversations, messages
- Qdrant: vector embeddings for semantic context
- Recall-questions handling (“list my last questions”)
- Follow-up handling (“answer the last question”)
- Skip vector search for very short messages (<25 chars) to avoid embedding load

### 7. Debug & Observability
- `GET /api/stream-test` — Minimal streaming test (no deps)
- Startup log for `OPENROUTER_API_KEY` (set/not set)
- Structured logging (chat_stream_start, mention_search_used, etc.)
- Health: `/health`, `/health/ready`
- Metrics: `/metrics` (Prometheus)

### 8. Media Index & Crawler Workers
- media_index_worker: RSS/feed ingestion, article parsing, entity detection
- crawler_worker: Playwright page snapshots, change detection
- Monitored entities: Sahi, Zerodha, Upstox (configurable)

---

## Data Flow: Chat with Live Search

```
User: "give me latest articles on Shahrukh Khan"
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Intent: embedding similarity → article search            │
│ 2. Extract query: "Shahrukh Khan"                           │
│ 3. Live search: Google News + Tavily/DuckDuckGo             │
│ 4. Validation, dedup, score, rerank                         │
└─────────────────────────────────────────────────────────────┘
          │
    [url_results]
          │
    ┌─────┴─────┐
    │  Results  │  Format directly with [Title](URL), stream
    │  found    │  → No LLM call for article list
    └───────────┘
          │
    ┌─────┴─────┐
    │ No results│  Fall back to Perplexity (web search) or
    │           │  regular LLM
    └───────────┘
```

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `OPENROUTER_API_KEY` | Required for LLM |
| `HF_TOKEN` | Hugging Face (optional, embeddings rate limits) |
| `TAVILY_API_KEY` | Optional, Tavily search |
| `MOCK_LLM` | 1 = skip OpenRouter, return mock response |
| `APP_ENV` | dev / prod (loads config/dev.yaml or prod.yaml) |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Send message, stream response |
| POST | `/api/new-chat` | Create conversation |
| GET | `/api/history/{id}` | Get messages |
| GET | `/api/stream-test` | Streaming test |
| GET | `/api/alerts` | Mention alerts |
| GET | `/api/coverage/timeline` | Coverage timeline |
| GET | `/api/coverage/compare` | Competitor comparison |
| GET | `/api/coverage/topics` | Trending topics |
| GET | `/health` | Liveness |
| GET | `/health/ready` | Readiness |
| GET | `/metrics` | Prometheus metrics |
