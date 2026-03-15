"""Social API — latest social mentions from social_posts; Reddit trending (separate pipeline)."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.services.mongodb import get_mongo_client

router = APIRouter(tags=["social"])

COLLECTION_NAME = "social_posts"
DEFAULT_LIMIT = 50


@router.get("/social/latest")
async def get_social_latest(entity: Optional[str] = None, limit: int = DEFAULT_LIMIT):
    """
    Return latest social mentions (Apify/social_posts pipeline).
    Optional ?entity=Sahi to filter by entity.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    coll = db[COLLECTION_NAME]

    query = {}
    if entity:
        query["entity"] = entity

    cursor = coll.find(query).sort("timestamp", -1).limit(min(limit, 100))

    posts = []
    async for doc in cursor:
        ts = doc.get("timestamp")
        if isinstance(ts, datetime):
            ts = ts.isoformat()
        engagement = doc.get("engagement") or {}
        posts.append({
            "platform": doc.get("platform", ""),
            "entity": doc.get("entity", ""),
            "text": doc.get("text", ""),
            "url": doc.get("url", ""),
            "engagement": engagement,
            "date": ts,
        })

    return {"posts": posts}


# --- Reddit trending (separate pipeline: own DB collections + Redis keys) -------

@router.get("/social/reddit-trending")
async def get_reddit_trending(limit: int = 80):
    """
    Return Reddit trending data: posts, themes, Sahi suggestions.
    Reads from Redis first, then MongoDB fallback so the UI always gets data after a refresh.
    """
    from app.services.reddit_trending_service import (
        load_posts_from_redis,
        load_posts_from_mongo,
        load_themes_from_redis,
        load_sahi_from_redis,
        load_latest_summary_from_mongo,
    )
    await get_mongo_client()
    posts = await load_posts_from_redis()
    if posts is None:
        posts = await load_posts_from_mongo(limit=limit)
    else:
        posts = posts[:limit]
    themes = await load_themes_from_redis()
    sahi = await load_sahi_from_redis()
    if not themes or not sahi:
        mongo_themes, mongo_sahi = await load_latest_summary_from_mongo()
        if not themes:
            themes = mongo_themes
        if not sahi:
            sahi = mongo_sahi
    return {
        "posts": posts or [],
        "themes": themes or [],
        "sahi_suggestions": sahi or [],
        "pipeline": "reddit_trending",
    }


@router.post("/social/reddit-trending/refresh")
async def refresh_reddit_trending():
    """Run the full Reddit trending pipeline (fetch → Mongo + Redis → LLM themes + Sahi → cache)."""
    from app.services.reddit_trending_service import run_reddit_trending_pipeline
    from app.config import get_config
    if not get_config().get("reddit_trending", {}).get("enabled", True):
        raise HTTPException(status_code=403, detail="reddit_trending disabled")
    result = await run_reddit_trending_pipeline()
    return result


# --- YouTube narrative (daily snapshots from DB) ---

@router.get("/social/youtube-narrative")
async def get_youtube_narrative(limit: int = 30):
    """
    Return YouTube narrative daily summaries from MongoDB.
    Per-day tracking: date, narrative, themes, sentiment, top channels, popularity.
    """
    from app.services.youtube_trending_service import load_daily_summaries
    await get_mongo_client()
    summaries = await load_daily_summaries(limit=limit)
    return {"summaries": summaries, "pipeline": "youtube_narrative"}


@router.get("/social/narrative-shift")
async def get_narrative_shift():
    """Return latest narrative shift run from DB."""
    from app.services.narrative_shift_service import load_latest_run
    await get_mongo_client()
    run = await load_latest_run()
    if not run:
        return {"generated_at": None, "narratives": [], "platform_totals": {}, "items_total": 0}
    return run


@router.get("/social/narrative-intelligence-daily")
async def get_narrative_intelligence_daily(days: int = 7):
    """Return last N days of narrative intelligence daily reports from DB."""
    from app.services.narrative_intelligence_daily_service import load_last_n_days
    await get_mongo_client()
    reports = await load_last_n_days(days=min(days, 30))
    return {"reports": reports}


@router.get("/social/narrative-positioning")
async def get_narrative_positioning(client: str, days: int = 7):
    """Return narrative positioning (PR-focused) for a client from DB."""
    if not client or not client.strip():
        return {"reports": []}
    from app.services.narrative_positioning_service import load_positioning
    await get_mongo_client()
    reports = await load_positioning(client=client.strip(), days=min(days, 30))
    return {"reports": reports}


@router.post("/social/narrative-positioning/run-batch")
async def run_narrative_positioning_batch():
    """Run narrative positioning batch for all clients."""
    from app.services.narrative_positioning_service import run_positioning_for_all_clients
    result = await run_positioning_for_all_clients()
    return result


@router.post("/social/youtube-narrative/refresh")
async def refresh_youtube_narrative():
    """Run the YouTube narrative pipeline (YouTube API + 1 LLM call → save daily summary)."""
    from app.services.youtube_trending_service import run_youtube_narrative_pipeline
    from app.config import get_config
    yt_cfg = get_config().get("youtube_trending")
    if not isinstance(yt_cfg, dict) or not yt_cfg.get("enabled", True):
        raise HTTPException(status_code=403, detail="youtube_trending disabled")
    result = await run_youtube_narrative_pipeline()
    return result


# --- AI Search Narrative (Perplexity answers for fixed queries → Narrative Analytics) ---

@router.get("/social/ai-search-answers")
async def get_ai_search_answers(days: int = 7, query: Optional[str] = None):
    """
    Return stored AI search answers (e.g. Perplexity) for the last N days.
    Optional ?query= substring to filter by search query text.
    """
    from app.services.ai_search_narrative_service import load_ai_search_answers
    await get_mongo_client()
    answers = await load_ai_search_answers(days=min(days, 90), query_filter=query)
    return {"answers": answers, "pipeline": "ai_search_narrative"}


@router.post("/social/ai-search-narrative/refresh")
async def refresh_ai_search_narrative():
    """Run the AI search narrative pipeline (fixed queries via Perplexity → store answers)."""
    from app.services.ai_search_narrative_service import run_ai_search_narrative_pipeline
    from app.config import get_config
    asc_cfg = get_config().get("ai_search_narrative")
    if not isinstance(asc_cfg, dict) or not asc_cfg.get("enabled", False):
        raise HTTPException(status_code=403, detail="ai_search_narrative disabled")
    result = await run_ai_search_narrative_pipeline()
    return result


# --- AI Search Visibility Monitoring (Phase 1) — CXO dashboard ---

@router.get("/social/ai-search-visibility/dashboard")
async def get_ai_search_visibility_dashboard(client: str, weeks: int = 8):
    """
    Return dashboard data for one client: latest snapshot, trend (last N weeks), recommendations.
    """
    if not client or not client.strip():
        raise HTTPException(status_code=400, detail="client required")
    from app.services.ai_search_visibility_service import load_dashboard
    await get_mongo_client()
    data = await load_dashboard(client=client.strip(), weeks=min(weeks, 52))
    return data


@router.post("/social/ai-search-visibility/refresh")
async def refresh_ai_search_visibility():
    """Run the AI Search Visibility pipeline (weekly prompts via Perplexity, entity detection, snapshots)."""
    from app.services.ai_search_visibility_service import run_visibility_pipeline
    from app.config import get_config
    vis_cfg = get_config().get("ai_search_visibility")
    if not isinstance(vis_cfg, dict) or not vis_cfg.get("enabled", False):
        raise HTTPException(status_code=403, detail="ai_search_visibility disabled")
    result = await run_visibility_pipeline()
    return result


# --- Sahi strategic brief (1–2 suggestions from themes, mentions, topics, competitors) ---

@router.get("/social/forum-mentions")
async def get_forum_mentions(
    entity: Optional[str] = None,
    limit: int = 50,
    range_days: int = 14,
):
    """
    Return entity_mentions where type=forum (traderji, tradingqna, valuepickr, etc.).
    Optional ?entity= to filter by brand/competitor name.
    """
    from datetime import datetime, timedelta, timezone

    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    coll = db["entity_mentions"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=min(range_days, 90))
    query: dict = {
        "type": "forum",
        "$or": [
            {"published_at": {"$gte": cutoff}},
            {"timestamp": {"$gte": cutoff}},
        ],
    }
    if entity and entity.strip():
        query["entity"] = entity.strip()
    cursor = coll.find(query).sort("published_at", -1).limit(min(limit, 200))
    mentions = []
    async for doc in cursor:
        pub = doc.get("published_at") or doc.get("timestamp")
        pub_str = pub.isoformat() if hasattr(pub, "isoformat") else str(pub or "")
        mentions.append({
            "entity": doc.get("entity", ""),
            "title": (doc.get("title") or "")[:500],
            "summary": (doc.get("summary") or doc.get("snippet") or "")[:400],
            "source_domain": doc.get("source_domain", ""),
            "url": doc.get("url", ""),
            "published_at": pub_str,
            "sentiment": doc.get("sentiment"),
        })
    return {"mentions": mentions, "count": len(mentions)}


@router.get("/social/forum-mentions/topics")
async def get_forum_topics_traction(
    client: Optional[str] = None,
    range_days: int = 14,
    top_n: int = 15,
):
    """
    Return topics with highest traction in forum mentions (type=forum).
    Optional ?client= to filter by brand; topics are joined from article_documents.
    """
    from app.services.forum_traction_service import get_forum_topics_traction as _get
    await get_mongo_client()
    return await _get(client=client or None, range_days=min(range_days, 90), top_n=min(top_n, 50))


@router.get("/social/sahi-strategic-brief")
async def get_sahi_strategic_brief(use_cache: bool = True):
    """
    Return 1–2 strategic suggestions for Sahi from Reddit themes, Sahi mentions,
    trending topics, and competitor context. Cached in Redis 1h.
    """
    await get_mongo_client()
    from app.services.sahi_strategic_brief_service import get_sahi_strategic_brief
    return await get_sahi_strategic_brief(use_cache=use_cache)
