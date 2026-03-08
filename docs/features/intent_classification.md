# Intent Classification Layer

## Purpose

Gate external search pipelines (Google News RSS, DuckDuckGo, Tavily, Apify) from normal conversational messages. The classifier determines whether the user wants a **chat** response or a **search** (article/mention) response. It prevents triggering expensive search operations for greetings, small talk, and irrelevant questions.

## Data Flow

```
User message
      │
      ▼
┌─────────────────────┐
│  Intent Classifier  │  (rule-based + embedding, no LLM)
└─────────────────────┘
      │
      ├── intent=chat  ──► LLM response (no search)
      │
      └── intent=search + entity ──► Mention search pipeline
                                      (RSS, Reddit, YouTube, Tavily, etc.)
```

## Architecture

### 1. Intent Detection Pipeline

1. **Rules first** — Fast regex and phrase checks
   - Greeting/casual → `chat` immediately
   - Entity + trigger patterns (e.g. "articles about X", "mentions of X") → `search`

2. **Embedding fallback** — For borderline cases
   - Cosine similarity to search-intent example sentences
   - Uses the **existing** `embedding_service` (all-MiniLM-L6-v2)
   - Search intent only when entity is present; otherwise default to `chat`

3. **Default** — Unclear or no entity → `chat`

### 2. Rule + Embedding Hybrid Design

| Step | Logic | Result |
|------|-------|--------|
| 1 | `is_greeting_or_casual(message)` | → `chat` |
| 2 | `extract_company_or_topic(message)` | → `search` with entity |
| 3 | Embedding similarity to search examples | Used only when rules don't decide; entity still required for search |
| 4 | Fallback | → `chat` |

**Behavior rules:**

- Greetings or conversational messages → always `chat`
- Search intent only when message clearly refers to monitored entities or coverage queries
- Messages without entity references → default `chat`

### 3. Search Gating

The chat request handler calls the intent classifier **before** any external search. Gated pipelines include:

- Google News RSS
- DuckDuckGo search
- Tavily search
- Apify (Reddit, YouTube, Twitter)

Search runs only when:

- `intent == "search"` and an entity was extracted, **or**
- `intent == "chat"` but it is a follow-up request (e.g. "go ahead") and the entity comes from the previous message.

## Intents

| Intent | Description | Action |
|--------|-------------|--------|
| `chat` | Greeting, small talk, general question, out-of-scope | LLM response only; no external search |
| `search` | Explicit request for articles/mentions about an entity | Run mention search pipeline |
| `analytics` | (Future) Analytics or reporting request | Reserved for future use |

## Files

| File | Role |
|------|------|
| `backend/app/services/intent_classifier.py` | Hybrid classifier; `classify_intent(message) -> (intent, entity)` |
| `backend/app/services/url_discovery/intent_detector.py` | Rule-based helpers: greetings, entity extraction, trigger patterns |
| `backend/app/services/embedding_service.py` | Existing embedding model (all-MiniLM-L6-v2) |
| `backend/app/api/chat.py` | Calls classifier first; gates search on intent |

## Performance Constraints

- **No LLM calls** — Classifier uses only rules and embeddings
- **Lightweight** — Runs on Mac Mini M1, 16GB RAM, Docker
- **Low latency** — Rules first; embedding used only when necessary
- Embeddings are lazy-loaded and reused for search examples
