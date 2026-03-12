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


# --- Sahi strategic brief (1–2 suggestions from themes, mentions, topics, competitors) ---

@router.get("/social/sahi-strategic-brief")
async def get_sahi_strategic_brief(use_cache: bool = True):
    """
    Return 1–2 strategic suggestions for Sahi from Reddit themes, Sahi mentions,
    trending topics, and competitor context. Cached in Redis 1h.
    """
    await get_mongo_client()
    from app.services.sahi_strategic_brief_service import get_sahi_strategic_brief
    return await get_sahi_strategic_brief(use_cache=use_cache)
