"""
AI Search Narrative — track what AI search (e.g. Perplexity) returns for fixed queries.

- Runs a small set of configured queries daily via Perplexity (OpenRouter web_search_model).
- Stores answer + metadata in MongoDB for Narrative Analytics / positioning.
- Rate-limited and capped for free tier (max_queries_per_run, delay_seconds_between_calls).
- No changes to existing collections or APIs; additive only.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

COLLECTION_DEFAULT = "ai_search_answers"


def _cfg() -> dict[str, Any]:
    return get_config().get("ai_search_narrative") or {}


def _answers_collection_name() -> str:
    mongo = _cfg().get("mongodb") or {}
    return mongo.get("answers_collection") or COLLECTION_DEFAULT


def _get_queries() -> list[str]:
    """Return query list from config, already capped by max_queries_per_run."""
    cfg = _cfg()
    queries = cfg.get("search_queries") or []
    if not isinstance(queries, list):
        queries = []
    max_q = max(0, int(cfg.get("max_queries_per_run") or 6))
    return [str(q).strip() for q in queries if str(q).strip()][:max_q]


async def _call_perplexity_for_query(query: str) -> str:
    """Single non-streaming-style call: use web search, collect full response."""
    from app.services.llm_gateway import LLMGateway

    gateway = LLMGateway()
    # Use web search model (Perplexity Sonar) from config or default
    raw = (get_config().get("openrouter") or {}).get("web_search_model") or ""
    model = raw if raw and "perplexity" in raw.lower() else "perplexity/sonar"
    gateway.set_model(model)

    messages = [
        {"role": "user", "content": f"Answer in 2–4 short paragraphs: {query}"},
    ]
    out = ""
    try:
        async for chunk in gateway.chat_completion(
            messages=messages,
            stream=True,
            use_web_search=True,
        ):
            if chunk:
                out += chunk
    except Exception as e:
        logger.warning("ai_search_narrative_perplexity_failed", query=query[:80], error=str(e))
        return ""
    out = out.strip()
    if out.startswith('{"error"'):
        return ""
    return out[:8000] if out else ""


async def run_ai_search_narrative_pipeline() -> dict[str, Any]:
    """
    Run the AI search narrative pipeline: run configured queries via Perplexity,
    store answers in MongoDB. Respects rate limit and free tier (max queries, delay).
    """
    cfg = _cfg()
    if not cfg.get("enabled", False):
        return {"ok": False, "reason": "ai_search_narrative disabled"}

    if not get_config().get("settings").openrouter_api_key:
        logger.warning("ai_search_narrative_skipped", reason="OPENROUTER_API_KEY not set")
        return {"ok": False, "reason": "OPENROUTER_API_KEY not set"}

    queries = _get_queries()
    if not queries:
        return {"ok": True, "processed": 0, "reason": "no queries configured"}

    delay_sec = max(0, min(30, float(cfg.get("delay_seconds_between_calls") or 4)))
    provider = (cfg.get("provider") or "perplexity").strip().lower()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_at = datetime.now(timezone.utc)

    from app.services.mongodb import get_mongo_client, get_db

    await get_mongo_client()
    db = get_db()
    coll_name = _answers_collection_name()
    coll = db[coll_name]

    processed = 0
    for i, query in enumerate(queries):
        if i > 0:
            await asyncio.sleep(delay_sec)
        answer = await _call_perplexity_for_query(query)
        doc = {
            "query": query[:500],
            "provider": provider,
            "answer": answer,
            "date": date_str,
            "computed_at": run_at,
        }
        try:
            await coll.replace_one(
                {"query": query[:500], "date": date_str},
                doc,
                upsert=True,
            )
            processed += 1
        except Exception as e:
            logger.warning("ai_search_narrative_store_failed", query=query[:80], error=str(e))

    logger.info("ai_search_narrative_run_done", processed=processed, queries=len(queries), date=date_str)
    return {"ok": True, "processed": processed, "date": date_str, "queries_run": len(queries)}


async def load_ai_search_answers(days: int = 7, query_filter: str | None = None) -> list[dict[str, Any]]:
    """Load stored AI search answers for the last N days, optionally filtered by query substring."""
    from app.services.mongodb import get_mongo_client, get_db

    await get_mongo_client()
    db = get_db()
    coll = db[_answers_collection_name()]

    cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = cutoff - timedelta(days=max(0, min(days, 90)))
    date_cutoff = cutoff.strftime("%Y-%m-%d")

    q: dict[str, Any] = {"date": {"$gte": date_cutoff}}
    if query_filter and query_filter.strip():
        q["query"] = {"$regex": query_filter.strip(), "$options": "i"}

    cursor = coll.find(q).sort("date", -1).sort("computed_at", -1).limit(200)
    out = []
    async for doc in cursor:
        d = dict(doc)
        d.pop("_id", None)
        for k in ("computed_at",):
            v = d.get(k)
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        out.append(d)
    return out
