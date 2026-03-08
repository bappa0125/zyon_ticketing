"""Media API — latest articles for monitored clients and competitors."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter

from app.services.mongodb import get_mongo_client

router = APIRouter(tags=["media"])

COLLECTION_NAME = "media_articles"
DEFAULT_LIMIT = 50


@router.get("/media/latest")
async def get_media_latest(client: Optional[str] = None, limit: int = DEFAULT_LIMIT):
    """
    Return latest media articles for monitored clients.
    Optional ?client=Sahi to filter by client.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    coll = db[COLLECTION_NAME]

    query = {}
    if client:
        query["client"] = client

    cursor = coll.find(query).sort("timestamp", -1).limit(min(limit, 100))

    articles = []
    async for doc in cursor:
        ts = doc.get("timestamp")
        if isinstance(ts, datetime):
            ts = ts.isoformat()
        articles.append({
            "title": doc.get("title", ""),
            "source": doc.get("source", ""),
            "url": doc.get("url", ""),
            "entity": doc.get("entity", ""),
            "client": doc.get("client", ""),
            "date": ts,
            "snippet": doc.get("snippet", ""),
        })

    return {"articles": articles}
