"""PR opportunity detection — topics competitors dominate but client has no mentions."""
from typing import Any

from app.core.client_config_loader import load_clients
from app.services.mongodb import get_mongo_client


COLLECTION_NAME = "media_articles"
TOP_LIMIT = 20


async def detect_pr_opportunities(client: str) -> list[dict[str, Any]]:
    """
    Find topics where competitors have mentions but client has none.
    Uses MongoDB aggregation; no full dataset loaded into memory.
    """
    clients = await load_clients()
    client_obj = next(
        (c for c in clients if (c.get("name") or "").strip().lower() == client.strip().lower()),
        None,
    )
    if not client_obj:
        return []

    client_name = (client_obj.get("name") or "").strip()
    competitors = client_obj.get("competitors", [])
    if not isinstance(competitors, list):
        competitors = []
    competitor_list = [c.strip() for c in competitors if c and isinstance(c, str)]

    if not competitor_list:
        return []

    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    coll = db[COLLECTION_NAME]

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
                "client_mentions": {
                    "$sum": {"$cond": [{"$eq": ["$entity", client_name]}, 1, 0]}
                },
                "competitor_mentions": {
                    "$sum": {"$cond": [{"$in": ["$entity", competitor_list]}, 1, 0]}
                },
            }
        },
        {
            "$match": {
                "competitor_mentions": {"$gt": 0},
                "client_mentions": 0,
            }
        },
        {"$sort": {"competitor_mentions": -1}},
        {"$limit": TOP_LIMIT},
        {
            "$project": {
                "topic": "$_id",
                "client_mentions": 1,
                "competitor_mentions": 1,
                "_id": 0,
            }
        },
    ]

    result = []
    async for doc in coll.aggregate(pipeline):
        result.append({
            "topic": doc.get("topic", ""),
            "competitor_mentions": doc.get("competitor_mentions", 0),
            "client_mentions": doc.get("client_mentions", 0),
        })

    return result
