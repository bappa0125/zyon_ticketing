"""
Sahi strategic brief — 1–2 LLM suggestions from themes, mentions, topics, competitors.
Option B: dedicated logic; consumed by GET /api/social/sahi-strategic-brief.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import get_config
from app.core.client_config_loader import load_clients, get_competitor_names, get_entity_names
from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client, get_db
from app.services.topics_service import get_topics_analytics

logger = get_logger(__name__)

REDIS_KEY = "sahi_strategic_brief"
COLLECTION = "strategic_briefs"
CACHE_TTL = 3600  # 1 hour
RANGE_PARAM = "7d"
MAX_SUGGESTIONS = 2


async def _primary_client() -> str:
    """Primary client name (e.g. Sahi) from config; first client if no 'Sahi'."""
    clients_list = await load_clients()
    for c in clients_list:
        name = (c.get("name") or "").strip()
        if name and name.lower() == "sahi":
            return name
    if clients_list and (clients_list[0].get("name") or "").strip():
        return (clients_list[0].get("name") or "").strip()
    return "Sahi"


def _parse_range(range_param: str) -> timedelta:
    if range_param == "24h":
        return timedelta(hours=24)
    if range_param == "7d":
        return timedelta(days=7)
    if range_param == "30d":
        return timedelta(days=30)
    return timedelta(days=7)


async def _load_themes() -> list[dict[str, Any]]:
    """Themes from Reddit trending (Redis then Mongo)."""
    from app.services.reddit_trending_service import (
        load_themes_from_redis,
        load_latest_summary_from_mongo,
    )
    themes = await load_themes_from_redis()
    if not themes:
        themes, _ = await load_latest_summary_from_mongo()
    return themes or []


async def _load_sahi_mentions_summary(client_name: str) -> dict[str, Any]:
    """Client entity_mentions in last 7d: count and sample titles."""
    await get_mongo_client()
    db = get_db()
    em = db["entity_mentions"]
    delta = _parse_range(RANGE_PARAM)
    cutoff = datetime.now(timezone.utc) - delta
    match = {
        "entity": client_name,
        "$or": [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}],
    }
    count = await em.count_documents(match)
    cursor = em.find(match, {"title": 1}).sort("published_at", -1).limit(5)
    titles = []
    async for doc in cursor:
        t = (doc.get("title") or "").strip()
        if t and t not in titles:
            titles.append(t[:120])
    return {"count": count, "sample_titles": titles}


async def _load_entity_mentions_counts(primary_client: str) -> dict[str, int]:
    """Mention counts per entity (primary client + competitors) in last 7d."""
    clients_list = await load_clients()
    client_obj = next(
        (c for c in clients_list if (c.get("name") or "").strip().lower() == primary_client.lower()),
        None,
    )
    if not client_obj:
        return {}
    entities = get_entity_names(client_obj)
    if not entities:
        return {}
    await get_mongo_client()
    db = get_db()
    em = db["entity_mentions"]
    delta = _parse_range(RANGE_PARAM)
    cutoff = datetime.now(timezone.utc) - delta
    pipeline = [
        {
            "$match": {
                "entity": {"$in": entities},
                "$or": [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}],
            }
        },
        {"$group": {"_id": "$entity", "count": {"$sum": 1}}},
    ]
    out = {}
    async for doc in em.aggregate(pipeline):
        out[doc["_id"]] = doc.get("count", 0)
    return out


async def _load_topics(client: str) -> list[dict[str, Any]]:
    """Top topics for client from topics_service."""
    data = await get_topics_analytics(client=client, range_param=RANGE_PARAM)
    topics = (data.get("topics") or [])[:10]
    return [{"topic": t.get("topic"), "mentions": t.get("mentions"), "trend_pct": t.get("trend_pct")} for t in topics]


async def _load_competitors(primary_client: str) -> list[str]:
    """Competitor names for primary client."""
    clients_list = await load_clients()
    client_obj = next(
        (c for c in clients_list if (c.get("name") or "").strip().lower() == primary_client.lower()),
        None,
    )
    if not client_obj:
        return []
    return get_competitor_names(client_obj)


async def _llm_strategic_call(
    themes: list[dict],
    sahi_summary: dict,
    topics: list[dict],
    competitors: list[str],
    entity_counts: dict[str, int],
) -> list[dict[str, Any]]:
    """One LLM call: 1–2 strategic suggestions for Sahi."""
    from app.services.llm_gateway import LLMGateway
    cfg = get_config()
    model = (cfg.get("reddit_trending", {}).get("llm", {}).get("model") or cfg.get("llm", {}).get("model") or "openrouter/free").strip()
    max_tokens = 400
    themes_text = "\n".join(f"- {t.get('label', '')}: {t.get('description', '')}" for t in themes) if themes else "None yet."
    topics_text = "\n".join(f"- {t.get('topic', '')} (mentions: {t.get('mentions', 0)}, trend: {t.get('trend_pct')}%)" for t in topics if t.get("topic")) if topics else "None yet."
    counts_text = ", ".join(f"{e}: {c}" for e, c in sorted(entity_counts.items(), key=lambda x: -x[1])) if entity_counts else "No data."
    system = (
        "You are a PR/content strategist for Sahi (a trading and investing education app). "
        "Given Reddit themes, Sahi's mention volume, trending topics, and competitor mention counts, "
        "output exactly 1 or 2 concrete, actionable suggestions. Return ONLY valid JSON: "
        '{"suggestions": [{"title": "...", "rationale": "...", "action_type": "content"|"pr"|"social"}]}.'
    )
    user = (
        f"Current Reddit themes in trading/investing communities:\n{themes_text}\n\n"
        f"Sahi's mentions (last 7 days): {sahi_summary.get('count', 0)}. Sample headlines: {sahi_summary.get('sample_titles', [])}\n\n"
        f"Trending topics in our data:\n{topics_text}\n\n"
        f"Competitors: {', '.join(competitors) or 'None'}.\n"
        f"Mention counts (last 7d): {counts_text}\n\n"
        "Give 1–2 specific suggestions (e.g. which theme to create content on, or where Sahi is under-represented vs competitors)."
    )
    gateway = LLMGateway()
    gateway.set_model(model)
    out = ""
    try:
        async for chunk in gateway.chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            stream=False,
            use_web_search=False,
        ):
            out += chunk or ""
    except Exception as e:
        logger.warning("sahi_strategic_llm_failed", error=str(e))
        return []
    s = (out or "").strip()
    if s.startswith("```"):
        lines = s.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines)
    try:
        obj = json.loads(s)
        suggestions = obj.get("suggestions")
        if not isinstance(suggestions, list):
            return []
        result = []
        for x in suggestions[:MAX_SUGGESTIONS]:
            if isinstance(x, dict) and (x.get("title") or x.get("rationale")):
                result.append({
                    "title": (x.get("title") or "").strip() or "Suggestion",
                    "rationale": (x.get("rationale") or "").strip(),
                    "action_type": (x.get("action_type") or "content").strip().lower() or "content",
                })
        return result
    except Exception as e:
        logger.debug("sahi_strategic_parse_failed", error=str(e))
        return []


async def get_sahi_strategic_brief(use_cache: bool = True) -> dict[str, Any]:
    """
    Return latest strategic brief from MongoDB. If missing, generate via LLM and store.
    use_cache=True: read from DB; generate only if empty.
    use_cache=False: force regenerate via LLM and store.
    """
    primary_client = await _primary_client()
    if use_cache:
        await get_mongo_client()
        db = get_db()
        coll = db[COLLECTION]
        doc = await coll.find_one(
            {"client": primary_client},
            sort=[("generated_at", -1)],
            projection={"_id": 0},
        )
        if doc:
            gen = doc.get("generated_at")
            if hasattr(gen, "isoformat"):
                doc = dict(doc)
                doc["generated_at"] = gen.isoformat() if gen else None
            return doc

    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION]
    themes = await _load_themes()
    sahi_summary = await _load_sahi_mentions_summary(primary_client)
    topics = await _load_topics(primary_client)
    competitors = await _load_competitors(primary_client)
    entity_counts = await _load_entity_mentions_counts(primary_client)
    suggestions = await _llm_strategic_call(themes, sahi_summary, topics, competitors, entity_counts)
    result = {
        "client": primary_client,
        "range": RANGE_PARAM,
        "generated_at": datetime.now(timezone.utc),
        "suggestions": suggestions,
    }
    await coll.update_one(
        {"client": primary_client},
        {"$set": result},
        upsert=True,
    )
    return {**result, "generated_at": result["generated_at"].isoformat()}


async def run_sahi_strategic_brief_daily() -> dict[str, int]:
    """Generate and store strategic brief. Call from scheduler."""
    try:
        await get_sahi_strategic_brief(use_cache=False)
        return {"generated": 1, "errors": 0}
    except Exception as e:
        logger.warning("sahi_strategic_daily_failed", error=str(e))
        return {"generated": 0, "errors": 1}
