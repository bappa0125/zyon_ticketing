"""Competitor coverage analytics — compare media mentions from article_documents + entity_mentions."""
from typing import Any

from app.core.client_config_loader import get_entity_names, load_clients
from app.services.mongodb import get_mongo_client

ENTITY_MENTIONS_COLLECTION = "entity_mentions"
ARTICLE_DOCUMENTS_COLLECTION = "article_documents"


async def compute_coverage(client: str) -> list[dict[str, Any]]:
    """
    Load client and competitors from clients.yaml.
    Aggregate mention counts from entity_mentions and article_documents (single pipeline).
    """
    clients = await load_clients()
    client_obj = next((c for c in clients if (c.get("name") or "").strip().lower() == client.strip().lower()), None)
    if not client_obj:
        return []

    entities = get_entity_names(client_obj)
    if not entities:
        return []

    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]
    art_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    counts: dict[str, int] = {e: 0 for e in entities}

    async for doc in em_coll.find({"entity": {"$in": entities}}):
        e = doc.get("entity") or ""
        if e in counts:
            counts[e] += 1

    async for doc in art_coll.find({"entities": {"$in": entities}}):
        for e in doc.get("entities") or []:
            if e in counts:
                counts[e] += 1
                break

    result = [{"entity": e, "mentions": counts[e]} for e in entities]
    result.sort(key=lambda x: -x["mentions"])
    return result
