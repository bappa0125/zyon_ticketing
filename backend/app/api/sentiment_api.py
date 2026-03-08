"""Sentiment Summary API — aggregate sentiment counts for media coverage."""
from typing import Optional

from fastapi import APIRouter

from app.services.mongodb import get_mongo_client

router = APIRouter(tags=["sentiment"])

COLLECTION_NAME = "media_articles"


@router.get("/sentiment/summary")
async def get_sentiment_summary(client: Optional[str] = None):
    """
    Return sentiment summary for media articles.
    Optional ?client=Sahi to filter by client.
    Aggregates positive, neutral, negative counts per entity.
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
        {"$match": {"sentiment": {"$exists": True, "$ne": None}}},
        {
            "$group": {
                "_id": "$entity",
                "positive": {"$sum": {"$cond": [{"$eq": ["$sentiment", "positive"]}, 1, 0]}},
                "neutral": {"$sum": {"$cond": [{"$eq": ["$sentiment", "neutral"]}, 1, 0]}},
                "negative": {"$sum": {"$cond": [{"$eq": ["$sentiment", "negative"]}, 1, 0]}},
            }
        },
        {"$project": {"entity": "$_id", "positive": 1, "neutral": 1, "negative": 1, "_id": 0}},
        {"$sort": {"entity": 1}},
    ]

    summaries = []
    async for doc in coll.aggregate(pipeline):
        summaries.append({
            "entity": doc.get("entity", ""),
            "positive": doc.get("positive", 0),
            "neutral": doc.get("neutral", 0),
            "negative": doc.get("negative", 0),
        })

    return {"summaries": summaries}
