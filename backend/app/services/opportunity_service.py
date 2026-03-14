"""PR opportunity detection — topics competitors dominate but client has no mentions.
Uses article_documents (KeyBERT topics) when available; falls back to media_articles."""
from typing import Any

from app.core.client_config_loader import get_competitor_names, get_entity_names, load_clients
from app.services.mongodb import get_mongo_client

ARTICLE_DOCUMENTS_COLLECTION = "article_documents"
MEDIA_ARTICLES_COLLECTION = "media_articles"
TOP_LIMIT = 20


async def detect_pr_opportunities(client: str) -> list[dict[str, Any]]:
    """
    Find topics where competitors have mentions but client has none.
    Primary: article_documents (entities + topics from KeyBERT).
    Fallback: media_articles (entity + topics) if article_documents has no data.
    """
    clients = await load_clients()
    client_obj = next(
        (c for c in clients if (c.get("name") or "").strip().lower() == client.strip().lower()),
        None,
    )
    if not client_obj:
        return []

    client_name = (client_obj.get("name") or "").strip()
    competitor_list = get_competitor_names(client_obj)
    entities = get_entity_names(client_obj)

    if not competitor_list:
        return []

    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()

    # 1. Try article_documents first (main pipeline: RSS → article_fetcher → entity_mentions)
    result = await _detect_from_article_documents(db, client_name, competitor_list, entities)
    if result:
        return result

    # 2. Fallback to media_articles (legacy / alternate pipeline)
    return await _detect_from_media_articles(db, client_name, competitor_list)


async def _detect_from_article_documents(db, client_name: str, competitor_list: list[str], entities: list[str]) -> list[dict[str, Any]]:
    """Aggregate topic gaps from article_documents (entities array, topics array)."""
    coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    pipeline = [
        {
            "$match": {
                "entities": {"$in": entities},
                "topics": {"$exists": True, "$type": "array", "$ne": []},
            }
        },
        {
            "$addFields": {
                "is_client": {"$cond": [{"$in": [client_name, "$entities"]}, 1, 0]},
                "is_competitor": {
                    "$cond": [
                        {"$gt": [{"$size": {"$setIntersection": ["$entities", competitor_list]}}, 0]},
                        1,
                        0,
                    ]
                },
            }
        },
        {"$unwind": "$topics"},
        {"$match": {"topics": {"$exists": True, "$nin": [None, ""]}}},
        {
            "$group": {
                "_id": "$topics",
                "client_mentions": {"$sum": "$is_client"},
                "competitor_mentions": {"$sum": "$is_competitor"},
            }
        },
        {"$match": {"competitor_mentions": {"$gt": 0}, "client_mentions": 0}},
        {"$sort": {"competitor_mentions": -1}},
        {"$limit": TOP_LIMIT},
        {"$project": {"topic": "$_id", "client_mentions": 1, "competitor_mentions": 1, "_id": 0}},
    ]

    result = []
    async for doc in coll.aggregate(pipeline):
        result.append({
            "topic": doc.get("topic", ""),
            "competitor_mentions": doc.get("competitor_mentions", 0),
            "client_mentions": doc.get("client_mentions", 0),
        })
    return result


async def _detect_from_media_articles(db, client_name: str, competitor_list: list[str]) -> list[dict[str, Any]]:
    """Fallback: aggregate topic gaps from media_articles (entity field, topics array)."""
    coll = db[MEDIA_ARTICLES_COLLECTION]

    pipeline = [
        {
            "$match": {
                "entity": {"$in": [client_name] + competitor_list},
                "topics": {"$exists": True, "$type": "array", "$ne": []},
            }
        },
        {"$unwind": "$topics"},
        {"$match": {"topics": {"$exists": True, "$nin": [None, ""]}}},
        {
            "$group": {
                "_id": "$topics",
                "client_mentions": {"$sum": {"$cond": [{"$eq": ["$entity", client_name]}, 1, 0]}},
                "competitor_mentions": {"$sum": {"$cond": [{"$in": ["$entity", competitor_list]}, 1, 0]}},
            }
        },
        {"$match": {"competitor_mentions": {"$gt": 0}, "client_mentions": 0}},
        {"$sort": {"competitor_mentions": -1}},
        {"$limit": TOP_LIMIT},
        {"$project": {"topic": "$_id", "client_mentions": 1, "competitor_mentions": 1, "_id": 0}},
    ]

    result = []
    async for doc in coll.aggregate(pipeline):
        result.append({
            "topic": doc.get("topic", ""),
            "competitor_mentions": doc.get("competitor_mentions", 0),
            "client_mentions": doc.get("client_mentions", 0),
        })
    return result
