"""Sentiment Summary API — aggregate sentiment counts for media coverage.

Supports entity_mentions (main pipeline: RSS → article_documents → entity_mentions)
and media_articles. Default source=entity_mentions so Sentiment page reflects
current monitoring pipeline.
"""
from typing import Optional

from fastapi import APIRouter

from app.services.mongodb import get_mongo_client

router = APIRouter(tags=["sentiment"])

MEDIA_ARTICLES = "media_articles"
ENTITY_MENTIONS = "entity_mentions"


def _sentiment_pipeline(match: dict) -> list:
    return [
        {"$match": match},
        {"$match": {"sentiment": {"$exists": True, "$ne": None, "$ne": ""}}},
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


@router.get("/sentiment/summary")
async def get_sentiment_summary(
    client: Optional[str] = None,
    source: Optional[str] = None,
):
    """
    Return sentiment summary (positive/neutral/negative counts per entity).

    - source=entity_mentions (default): aggregate from entity_mentions (main pipeline).
    - source=media_articles: aggregate from media_articles (legacy).
    - client: when source=entity_mentions, filter to this client's entities (client + competitors from config).
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    use_entity_mentions = (source or "entity_mentions").strip().lower() != "media_articles"

    if use_entity_mentions:
        coll = db[ENTITY_MENTIONS]
        match: dict = {}
        if client and client.strip():
            from app.core.client_config_loader import get_entity_names, load_clients
            clients = await load_clients()
            client_obj = next(
                (c for c in clients if (c.get("name") or "").strip().lower() == client.strip().lower()),
                None,
            )
            if client_obj:
                entities = get_entity_names(client_obj)
                if entities:
                    match["entity"] = {"$in": entities}
        pipeline = _sentiment_pipeline(match)
        summaries = []
        async for doc in coll.aggregate(pipeline):
            summaries.append({
                "entity": doc.get("entity", ""),
                "positive": doc.get("positive", 0),
                "neutral": doc.get("neutral", 0),
                "negative": doc.get("negative", 0),
            })
        return {"summaries": summaries, "source": "entity_mentions"}

    coll = db[MEDIA_ARTICLES]
    match = {}
    if client:
        match["client"] = client
    pipeline = _sentiment_pipeline(match)
    summaries = []
    async for doc in coll.aggregate(pipeline):
        summaries.append({
            "entity": doc.get("entity", ""),
            "positive": doc.get("positive", 0),
            "neutral": doc.get("neutral", 0),
            "negative": doc.get("negative", 0),
        })
    return {"summaries": summaries, "source": "media_articles"}
