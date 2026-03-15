"""
Forum topics traction — which topics get high traction in forum mentions (entity_mentions type=forum).
Joins to article_documents for topics; returns per-topic counts and sample titles/urls.
Used for Forum mentions page and executive report.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.core.client_config_loader import get_entity_names, load_clients
from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client

logger = get_logger(__name__)

ENTITY_MENTIONS_COLLECTION = "entity_mentions"
ARTICLE_DOCUMENTS_COLLECTION = "article_documents"
TOP_TOPICS_DEFAULT = 15
SAMPLE_TITLES_PER_TOPIC = 3


def _str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    return str(val)[:500]


async def get_forum_topics_traction(
    client: Optional[str] = None,
    range_days: int = 14,
    top_n: int = TOP_TOPICS_DEFAULT,
) -> dict[str, Any]:
    """
    Return topics with highest traction in forum mentions (entity_mentions type=forum).
    Joins to article_documents to get topics. Optionally filter by client entities.
    Returns: { topics: [ { topic, mention_count, sample_titles, sample_urls } ], client?, range_days }
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]
    cutoff = datetime.now(timezone.utc) - timedelta(days=min(range_days, 90))

    entities_filter: Optional[list[str]] = None
    if client and client.strip():
        clients_list = await load_clients()
        client_obj = next(
            (c for c in clients_list if _str(c.get("name")).lower() == client.strip().lower()),
            None,
        )
        if client_obj:
            entities_filter = get_entity_names(client_obj)

    match: dict[str, Any] = {
        "type": "forum",
        "$or": [
            {"published_at": {"$gte": cutoff}},
            {"timestamp": {"$gte": cutoff}},
        ],
    }
    if entities_filter:
        match["entity"] = {"$in": entities_filter}

    # Aggregate: entity_mentions (forum) -> lookup article_documents by url -> unwind topics -> group by topic
    pipeline = [
        {"$match": match},
        {
            "$lookup": {
                "from": ARTICLE_DOCUMENTS_COLLECTION,
                "let": {"em_url": "$url"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {"$or": [{"$eq": ["$url", "$$em_url"]}, {"$eq": ["$url_resolved", "$$em_url"]}]},
                            "topics": {"$exists": True, "$type": "array", "$ne": []},
                        }
                    },
                    {"$limit": 1},
                    {"$project": {"topics": 1, "title": 1, "url": 1}},
                ],
                "as": "art",
            }
        },
        {"$match": {"art.0": {"$exists": True}}},
        {"$unwind": "$art"},
        {"$unwind": "$art.topics"},
        {"$match": {"art.topics": {"$exists": True, "$nin": [None, ""]}}},
        {
            "$group": {
                "_id": "$art.topics",
                "mention_count": {"$sum": 1},
                "titles": {"$addToSet": {"$ifNull": ["$art.title", "$title"]}},
                "urls": {"$addToSet": {"$ifNull": ["$art.url", "$url"]}},
            }
        },
        {"$sort": {"mention_count": -1}},
        {"$limit": top_n},
    ]

    topics_out: list[dict[str, Any]] = []
    async for doc in em_coll.aggregate(pipeline):
        topic = _str(doc.get("_id"))
        if not topic:
            continue
        count = doc.get("mention_count", 0)
        titles = [t for t in (doc.get("titles") or []) if _str(t)][:SAMPLE_TITLES_PER_TOPIC]
        urls = [u for u in (doc.get("urls") or []) if _str(u)][:SAMPLE_TITLES_PER_TOPIC]
        topics_out.append({
            "topic": topic,
            "mention_count": count,
            "sample_titles": titles,
            "sample_urls": urls,
        })

    return {
        "topics": topics_out,
        "client": client,
        "range_days": range_days,
    }
