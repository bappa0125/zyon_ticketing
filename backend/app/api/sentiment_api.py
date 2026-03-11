"""Sentiment Summary API — aggregate sentiment counts and article mentions for media coverage.

Supports entity_mentions (main pipeline: RSS → article_documents → entity_mentions)
and media_articles. Default source=entity_mentions so Sentiment page reflects
current monitoring pipeline.
"""
from typing import Optional

from fastapi import APIRouter, Query

from app.services.mongodb import get_mongo_client
from app.services.media_intelligence_service import get_dashboard

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
    entity: Optional[str] = Query(None, description="Filter to single entity (client or competitor name)"),
    source: Optional[str] = None,
):
    """
    Return sentiment summary (positive/neutral/negative counts per entity).

    - source=entity_mentions (default): aggregate from entity_mentions (main pipeline).
    - source=media_articles: aggregate from media_articles (legacy).
    - client: when source=entity_mentions, filter to this client's entities (client + competitors from config).
    - entity: when provided, filter to that entity only (client or competitor).
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
                    if entity and entity.strip():
                        if entity.strip() in entities:
                            match["entity"] = entity.strip()
                        else:
                            match["entity"] = {"$in": entities}
                    else:
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


MENTIONS_LIMIT = 150


@router.get("/sentiment/mentions")
async def get_sentiment_mentions(
    client: str = Query(..., description="Client name, e.g. Sahi"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
    sentiment: Optional[str] = Query(None, description="Filter: positive | neutral | negative"),
    entity: Optional[str] = Query(None, description="Filter by entity name"),
):
    """
    Return article mentions that have sentiment (for Sentiment page feed).
    Same structure as Media Intelligence feed items; filtered to items with sentiment.
    """
    await get_mongo_client()
    data = await get_dashboard(client=client, range_param=range_param)
    feed = data.get("feed", [])
    mentions = [m for m in feed if m.get("sentiment")]
    if sentiment and sentiment.strip().lower() in ("positive", "neutral", "negative"):
        sv = sentiment.strip().lower()
        mentions = [m for m in mentions if (m.get("sentiment") or "").strip().lower() == sv]
    if entity and entity.strip():
        ev = entity.strip()
        mentions = [m for m in mentions if (m.get("entity") or "").strip() == ev]
    mentions = mentions[:MENTIONS_LIMIT]
    return {
        "mentions": mentions,
        "client": data.get("client", client),
        "competitors": data.get("competitors", []),
        "range": range_param,
    }
