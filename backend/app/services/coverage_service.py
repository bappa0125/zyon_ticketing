"""Competitor coverage analytics — compare media mentions from article_documents + entity_mentions."""
from typing import Any

from app.core.client_config_loader import get_entity_names, get_competitor_names, load_clients
from app.services.mongodb import get_mongo_client

ENTITY_MENTIONS_COLLECTION = "entity_mentions"
ARTICLE_DOCUMENTS_COLLECTION = "article_documents"


async def get_article_counts(client: str) -> dict[str, Any]:
    """
    Return counts for article_documents: total, with client in entities, competitor-only.
    Explains why competitor-only might be lower than expected.
    """
    clients = await load_clients()
    client_obj = next((c for c in clients if (c.get("name") or "").strip().lower() == client.strip().lower()), None)
    if not client_obj:
        return {}

    client_name = (client_obj.get("name") or "").strip()
    competitors = get_competitor_names(client_obj)
    if not client_name:
        return {}

    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    art_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    total = await art_coll.count_documents({})
    with_client = await art_coll.count_documents({"entities": client_name})
    competitor_only_query = {
        "$and": [
            {"entities": {"$in": competitors}},
            {"entities": {"$nin": [client_name]}},
        ]
    }
    competitor_only = await art_coll.count_documents(competitor_only_query)
    with_entities_populated = await art_coll.count_documents({"entities": {"$exists": True, "$ne": []}})

    return {
        "total_articles": total,
        "articles_with_client_mentioned": with_client,
        "competitor_only_articles": competitor_only,
        "articles_with_entities_populated": with_entities_populated,
        "pipeline_note": (
            "entities is set only when the article is first inserted by the article_fetcher "
            "(RSS → fetch → detect_entities on title+text/summary). Old docs or failed detection may have empty entities."
        ),
    }


async def get_competitor_only_articles(client: str, limit: int = 50) -> dict[str, Any]:
    """
    Articles where entity detection found only competitors (no client).
    article_documents: entities has at least one competitor, client not in entities.
    Returns { has_competitor_only_articles: bool, count: int, articles: [...] }.
    """
    clients = await load_clients()
    client_obj = next((c for c in clients if (c.get("name") or "").strip().lower() == client.strip().lower()), None)
    if not client_obj:
        return {"has_competitor_only_articles": False, "count": 0, "articles": []}

    client_name = (client_obj.get("name") or "").strip()
    competitors = get_competitor_names(client_obj)
    if not client_name or not competitors:
        return {"has_competitor_only_articles": False, "count": 0, "articles": []}

    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    art_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    # At least one competitor in entities, client not in entities
    query = {
        "$and": [
            {"entities": {"$in": competitors}},
            {"entities": {"$nin": [client_name]}},
        ]
    }

    total = await art_coll.count_documents(query)
    cursor = art_coll.find(query).sort("published_at", -1).limit(limit)
    articles: list[dict[str, Any]] = []
    async for doc in cursor:
        pub = doc.get("published_at")
        pub_str = pub.isoformat() if hasattr(pub, "isoformat") else str(pub or "")
        articles.append({
            "url": (doc.get("url") or "")[:500],
            "title": (doc.get("title") or "")[:500],
            "summary": (doc.get("summary") or "")[:400],
            "source_domain": (doc.get("source_domain") or "")[:200],
            "published_at": pub_str,
            "entities": list(doc.get("entities") or []),
            "author": (doc.get("author") or "")[:200] or None,
            "ai_summary": doc.get("ai_summary"),
        })

    return {
        "has_competitor_only_articles": total > 0,
        "count": total,
        "articles": articles,
    }


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


async def get_mentions_client_and_competitors(client: str, limit: int = 50) -> dict[str, Any]:
    """
    Mentions (entity_mentions rows) where entity is client or any competitor.
    Returns list of { url, title, summary, source_domain, published_at, entity, author } for the second table.
    """
    clients = await load_clients()
    client_obj = next((c for c in clients if (c.get("name") or "").strip().lower() == client.strip().lower()), None)
    if not client_obj:
        return {"mentions": [], "count": 0}

    client_name = (client_obj.get("name") or "").strip()
    competitors = get_competitor_names(client_obj)
    entities = [client_name] + (competitors or [])
    if not entities:
        return {"mentions": [], "count": 0}

    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]

    query = {"entity": {"$in": entities}}
    total = await em_coll.count_documents(query)
    cursor = em_coll.find(query).sort("published_at", -1).limit(limit)
    mentions: list[dict[str, Any]] = []
    async for doc in cursor:
        pub = doc.get("published_at")
        pub_str = pub.isoformat() if hasattr(pub, "isoformat") else str(pub or "")
        mentions.append({
            "url": (doc.get("url") or "")[:500],
            "title": (doc.get("title") or "")[:500],
            "summary": (doc.get("summary") or "")[:400],
            "source_domain": (doc.get("source_domain") or "")[:200],
            "published_at": pub_str,
            "entity": (doc.get("entity") or "")[:200],
            "author": (doc.get("author") or "")[:200] or None,
        })

    return {"mentions": mentions, "count": total}
