"""Topics analytics — join entity_mentions with article_documents by url, aggregate by topic.
Returns volume, trend (WoW), sentiment, entity breakdown, sample headlines, action (talk/careful/avoid)."""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.core.client_config_loader import get_entity_names, get_competitor_names, load_clients
from app.services.mongodb import get_mongo_client

ENTITY_MENTIONS_COLLECTION = "entity_mentions"
ARTICLE_DOCUMENTS_COLLECTION = "article_documents"
TOPICS_LIMIT = 25
SAMPLE_HEADLINES = 5


def _parse_range(range_param: str) -> timedelta:
    if range_param == "24h":
        return timedelta(hours=24)
    if range_param == "7d":
        return timedelta(days=7)
    if range_param == "30d":
        return timedelta(days=30)
    return timedelta(days=7)


def _sentiment_label(s: Any) -> str:
    if s is None:
        return "neutral"
    v = str(s).lower().strip()
    if v in ("positive", "pos"):
        return "positive"
    if v in ("negative", "neg"):
        return "negative"
    return "neutral"


def _action_from_sentiment(positive: int, neutral: int, negative: int) -> str:
    total = positive + neutral + negative
    if total == 0:
        return "careful"
    pos_pct = positive / total
    neg_pct = negative / total
    if neg_pct >= 0.5:
        return "avoid"
    if pos_pct >= 0.5:
        return "talk"
    return "careful"


async def get_topics_analytics(
    client: Optional[str] = None,
    range_param: str = "7d",
) -> dict[str, Any]:
    """
    Return topic analytics from entity_mentions + article_documents.
    Joins by url, aggregates by topic: volume, trend_pct, sentiment, by_entity, sample_headlines, action.
    client: filter by client entities. If None, uses all entity_mentions with topics.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    entities: list[str] = []
    client_name: Optional[str] = None
    competitor_names: list[str] = []
    if client:
        clients_list = await load_clients()
        client_obj = next(
            (c for c in clients_list if (c.get("name") or "").strip().lower() == client.strip().lower()),
            None,
        )
        if not client_obj:
            return {"topics": [], "client": client, "competitors": [], "range": range_param}
        entities = get_entity_names(client_obj)
        client_name = (client_obj.get("name") or "").strip()
        competitor_names = get_competitor_names(client_obj)
        if not entities:
            return {"topics": [], "client": client, "competitors": competitor_names, "range": range_param}

    delta = _parse_range(range_param)
    now = datetime.now(timezone.utc)
    cutoff = now - delta
    prev_cutoff = cutoff - delta

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]
    art_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    match_em: dict[str, Any] = {
        "$or": [
            {"published_at": {"$gte": cutoff}},
            {"timestamp": {"$gte": cutoff}},
        ],
    }
    if entities:
        match_em["entity"] = {"$in": entities}

    pipeline_current = [
        {"$match": match_em},
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
                    {"$project": {"topics": 1}},
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
                "mentions": {"$sum": 1},
                "titles": {"$addToSet": {"$ifNull": ["$title", ""]}},
                "entities": {"$push": "$entity"},
                "sentiments": {"$push": {"$ifNull": ["$sentiment", "neutral"]}},
            }
        },
        {"$sort": {"mentions": -1}},
        {"$limit": TOPICS_LIMIT},
    ]

    current_raw: list[dict[str, Any]] = []
    async for doc in em_coll.aggregate(pipeline_current):
        current_raw.append(doc)

    # Previous period for trend
    match_prev = {
        "$or": [
            {"published_at": {"$gte": prev_cutoff, "$lt": cutoff}},
            {"timestamp": {"$gte": prev_cutoff, "$lt": cutoff}},
        ],
    }
    if entities:
        match_prev["entity"] = {"$in": entities}

    pipeline_prev = [
        {"$match": match_prev},
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
                    {"$project": {"topics": 1}},
                ],
                "as": "art",
            }
        },
        {"$match": {"art.0": {"$exists": True}}},
        {"$unwind": "$art"},
        {"$unwind": "$art.topics"},
        {"$group": {"_id": "$art.topics", "mentions": {"$sum": 1}}},
    ]

    prev_volumes: dict[str, int] = {}
    async for doc in em_coll.aggregate(pipeline_prev):
        prev_volumes[doc["_id"]] = doc.get("mentions", 0)

    topics_out: list[dict[str, Any]] = []
    for doc in current_raw:
        topic = doc.get("_id", "")
        if not topic:
            continue
        mentions = doc.get("mentions", 0)
        titles = [t for t in (doc.get("titles") or []) if t][:SAMPLE_HEADLINES]
        entities_list = doc.get("entities") or []
        sentiments_list = doc.get("sentiments") or []

        pos = sum(1 for s in sentiments_list if _sentiment_label(s) == "positive")
        neu = sum(1 for s in sentiments_list if _sentiment_label(s) == "neutral")
        neg = sum(1 for s in sentiments_list if _sentiment_label(s) == "negative")

        by_entity: dict[str, int] = {}
        for e in entities_list:
            e = (e or "").strip()
            if e:
                by_entity[e] = by_entity.get(e, 0) + 1

        prev = prev_volumes.get(topic, 0)
        trend_pct: Optional[float] = None
        if prev > 0:
            trend_pct = round((mentions - prev) / prev * 100, 1)
        elif mentions > 0:
            trend_pct = 100.0

        action = _action_from_sentiment(pos, neu, neg)

        client_mentions = by_entity.get(client_name, 0) if client_name else 0
        competitor_mentions = sum(by_entity.get(c, 0) for c in competitor_names) if competitor_names else 0

        topics_out.append({
            "topic": topic,
            "mentions": mentions,
            "client_mentions": client_mentions,
            "competitor_mentions": competitor_mentions,
            "trend_pct": trend_pct,
            "sentiment": {"positive": pos, "neutral": neu, "negative": neg},
            "sentiment_summary": "Pos" if pos > neg and pos > neu else ("Neg" if neg > pos and neg > neu else "Neutral"),
            "by_entity": by_entity,
            "sample_headlines": titles,
            "action": action,
        })

    return {
        "topics": topics_out,
        "client": client,
        "competitors": competitor_names,
        "range": range_param,
    }
