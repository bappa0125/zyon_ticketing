"""Topic Analytics API — aggregate topic mentions from media coverage."""
from typing import Optional

from fastapi import APIRouter

from app.services.mongodb import get_mongo_client

router = APIRouter(tags=["topics"])

COLLECTION_NAME = "media_articles"


@router.get("/topics")
async def get_topics(client: Optional[str] = None):
    """
    Return topic analytics: topic phrases with mention counts.
    Optional ?client=Sahi to filter by client.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    coll = db[COLLECTION_NAME]

    match: dict = {}
    if client:
        match["client"] = client

    pipeline = [
        {"$match": match},
        {"$match": {"topics": {"$exists": True, "$ne": [], "$type": "array"}}},
        {"$unwind": "$topics"},
        {"$group": {"_id": "$topics", "mentions": {"$sum": 1}}},
        {"$project": {"topic": "$_id", "mentions": 1, "_id": 0}},
        {"$sort": {"mentions": -1}},
    ]

    topics = []
    async for doc in coll.aggregate(pipeline):
        topic_str = doc.get("topic", "")
        if topic_str:
            topics.append({
                "topic": topic_str,
                "mentions": doc.get("mentions", 0),
            })

    return {"topics": topics}
