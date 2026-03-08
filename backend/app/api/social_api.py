"""Social API — latest social mentions from social_posts."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter

from app.services.mongodb import get_mongo_client

router = APIRouter(tags=["social"])

COLLECTION_NAME = "social_posts"
DEFAULT_LIMIT = 50


@router.get("/social/latest")
async def get_social_latest(entity: Optional[str] = None, limit: int = DEFAULT_LIMIT):
    """
    Return latest social mentions.
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
