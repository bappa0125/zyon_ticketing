"""
Positioning mix — evidence and gaps for executive report (no LLM).

Aggregates: forum vs news split (entity_mentions by type), topic mix (from topics_service),
competitor-only articles (coverage_service). Used as section8 in executive report.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.client_config_loader import get_entity_names, load_clients
from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client

logger = get_logger(__name__)

ENTITY_MENTIONS_COLLECTION = "entity_mentions"
TOP_TOPICS_LIMIT = 5
COMPETITOR_ONLY_SAMPLE = 10


def _parse_range(range_param: str) -> timedelta:
    if range_param == "24h":
        return timedelta(hours=24)
    if range_param == "7d":
        return timedelta(days=7)
    if range_param == "30d":
        return timedelta(days=30)
    return timedelta(days=7)


def _str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    return str(val)[:500]


async def get_positioning_mix(client_name: str, range_param: str = "7d") -> dict[str, Any]:
    """
    Return positioning mix for one client: forum vs news %, top topics, competitor-only count + sample.
    Read-only; uses entity_mentions, topics_service, coverage_service.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db
    from app.services.topics_service import get_topics_analytics
    from app.services.coverage_service import get_competitor_only_articles

    clients_list = await load_clients()
    client_obj = next(
        (c for c in clients_list if _str(c.get("name")).lower() == client_name.strip().lower()),
        None,
    )
    if not client_obj:
        return _empty_row(client_name)

    entities = get_entity_names(client_obj)
    if not entities:
        return _empty_row(client_name)

    delta = _parse_range(range_param)
    cutoff = datetime.now(timezone.utc) - delta
    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]

    # 1. Forum vs news split: aggregate entity_mentions by type
    match = {
        "entity": {"$in": entities},
        "$or": [
            {"published_at": {"$gte": cutoff}},
            {"timestamp": {"$gte": cutoff}},
        ],
    }
    pipeline = [
        {"$match": match},
        {"$project": {"type": {"$ifNull": ["$type", "article"]}}},
        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
    ]
    by_type: dict[str, int] = {}
    async for doc in em_coll.aggregate(pipeline):
        t = (doc.get("_id") or "article")
        if isinstance(t, str):
            t = t.strip().lower()
            if t not in ("forum", "article"):
                t = "article"
        else:
            t = "article"
        by_type[t] = by_type.get(t, 0) + doc.get("count", 0)

    article_count = by_type.get("article", 0)
    forum_count = by_type.get("forum", 0)
    total_mentions = article_count + forum_count
    forum_pct = round(forum_count / total_mentions * 100, 0) if total_mentions else 0
    news_pct = round(article_count / total_mentions * 100, 0) if total_mentions else 0

    # 1b. YouTube and Reddit counts from social_posts (same entities, same range)
    sp_coll = db["social_posts"]
    sp_match = {
        "entity": {"$in": entities},
        "$or": [
            {"published_at": {"$gte": cutoff}},
            {"timestamp": {"$gte": cutoff}},
        ],
    }
    sp_pipeline = [
        {"$match": sp_match},
        {"$project": {"platform": {"$ifNull": ["$platform", ""]}}},
        {"$group": {"_id": {"$toLower": "$platform"}, "count": {"$sum": 1}}},
    ]
    youtube_count = 0
    reddit_count = 0
    async for doc in sp_coll.aggregate(sp_pipeline):
        plat = (doc.get("_id") or "").strip().lower()
        c = doc.get("count", 0)
        if "youtube" in plat:
            youtube_count += c
        elif "reddit" in plat:
            reddit_count += c

    # 2. Topic mix (top N topic names from topics_service)
    top_topics: list[str] = []
    try:
        topics_data = await get_topics_analytics(client=client_name, range_param=range_param)
        topics_list = topics_data.get("topics") or []
        for t in topics_list[:TOP_TOPICS_LIMIT]:
            name = (t.get("topic") or "").strip()
            if name:
                top_topics.append(name)
    except Exception as e:
        logger.debug("positioning_mix_topics_failed", client=client_name, error=str(e))

    # 3. Competitor-only articles (gaps)
    competitor_only_count = 0
    competitor_only_sample: list[dict[str, Any]] = []
    top_opportunity = "—"
    try:
        co = await get_competitor_only_articles(client_name, limit=COMPETITOR_ONLY_SAMPLE)
        competitor_only_count = co.get("count") or 0
        competitor_only_sample = co.get("articles") or []
        if competitor_only_sample:
            top_opportunity = _str(competitor_only_sample[0].get("title") or "Competitor-only article")[:120]
    except Exception as e:
        logger.debug("positioning_mix_competitor_only_failed", client=client_name, error=str(e))

    return {
        "brand": client_name,
        "forum_count": forum_count,
        "article_count": article_count,
        "youtube_count": youtube_count,
        "reddit_count": reddit_count,
        "total_mentions": total_mentions,
        "forum_pct": forum_pct,
        "news_pct": news_pct,
        "top_topics": top_topics,
        "top_topics_display": ", ".join(top_topics) if top_topics else "—",
        "competitor_only_count": competitor_only_count,
        "top_opportunity": top_opportunity,
    }


def _empty_row(client_name: str) -> dict[str, Any]:
    return {
        "brand": client_name,
        "forum_count": 0,
        "article_count": 0,
        "youtube_count": 0,
        "reddit_count": 0,
        "total_mentions": 0,
        "forum_pct": 0,
        "news_pct": 0,
        "top_topics": [],
        "top_topics_display": "—",
        "competitor_only_count": 0,
        "top_opportunity": "—",
    }
