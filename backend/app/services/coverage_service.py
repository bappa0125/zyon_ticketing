"""Competitor coverage analytics — compare media mentions using MongoDB aggregation."""
from typing import Any

from app.core.client_config_loader import load_clients
from app.services.mongodb import get_mongo_client


COLLECTION_NAME = "media_articles"


async def compute_coverage(client: str) -> list[dict[str, Any]]:
    """
    Load client and competitors from clients.yaml.
    Aggregate media_articles by entity; return mention counts.
    Uses MongoDB aggregation to avoid loading large datasets into memory.
    """
    clients = await load_clients()
    client_obj = next((c for c in clients if (c.get("name") or "").strip().lower() == client.strip().lower()), None)
    if not client_obj:
        return []

    client_name = (client_obj.get("name") or "").strip()
    competitors = client_obj.get("competitors", [])
    if not isinstance(competitors, list):
        competitors = []
    entities = [client_name] + [c.strip() for c in competitors if c and isinstance(c, str)]

    if not entities:
        return []

    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    coll = db[COLLECTION_NAME]

    pipeline = [
        {"$match": {"entity": {"$in": entities}}},
        {"$group": {"_id": "$entity", "mentions": {"$sum": 1}}},
        {"$project": {"entity": "$_id", "mentions": 1, "_id": 0}},
        {"$sort": {"mentions": -1}},
    ]

    result = []
    async for doc in coll.aggregate(pipeline):
        result.append({
            "entity": doc.get("entity", ""),
            "mentions": doc.get("mentions", 0),
        })

    # Include entities with zero mentions (not in aggregation result)
    seen = {r["entity"] for r in result}
    for e in entities:
        if e not in seen:
            result.append({"entity": e, "mentions": 0})
    result.sort(key=lambda x: -x["mentions"])

    return result
