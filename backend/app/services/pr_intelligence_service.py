"""PR Intelligence Layer — topic-article mapping, first mention, amplifier, journalist-outlet.
Read-only, no LLM. Uses article_documents + entity_mentions (KeyBERT topics)."""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.core.client_config_loader import get_entity_names, get_competitor_names, load_clients
from app.services.mongodb import get_mongo_client

ENTITY_MENTIONS_COLLECTION = "entity_mentions"
ARTICLE_DOCUMENTS_COLLECTION = "article_documents"
TOPIC_ARTICLES_LIMIT = 50
FIRST_MENTIONS_LIMIT = 100
AMPLIFIERS_LIMIT = 50
JOURNALIST_OUTLETS_LIMIT = 500


def _parse_range(range_param: str) -> timedelta:
    if range_param == "24h":
        return timedelta(hours=24)
    if range_param == "7d":
        return timedelta(days=7)
    if range_param == "30d":
        return timedelta(days=30)
    return timedelta(days=7)


def _to_dt(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return None


async def _get_client_entities(client: str) -> tuple[Optional[str], list[str], list[str]]:
    """Return (client_name, entities, competitor_names)."""
    clients_list = await load_clients()
    client_obj = next(
        (c for c in clients_list if (c.get("name") or "").strip().lower() == client.strip().lower()),
        None,
    )
    if not client_obj:
        return None, [], []
    client_name = (client_obj.get("name") or "").strip()
    entities = get_entity_names(client_obj)
    competitor_names = get_competitor_names(client_obj)
    return client_name, entities, competitor_names


async def get_topic_article_mapping(
    client: str,
    range_param: str = "7d",
    topic_filter: Optional[str] = None,
    limit_per_topic: int = 20,
) -> dict[str, Any]:
    """
    Map topics to articles. Uses article_documents.topics (KeyBERT) joined with entity_mentions.
    Returns topics with list of articles (url, title, published_at, entity, author).
    No LLM.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    client_name, entities, competitor_names = await _get_client_entities(client)
    if not client_name or not entities:
        return {
            "client": client,
            "competitors": competitor_names or [],
            "range": range_param,
            "topics": [],
        }

    delta = _parse_range(range_param)
    cutoff = datetime.now(timezone.utc) - delta

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]
    art_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    match_em: dict[str, Any] = {
        "entity": {"$in": entities},
        "$or": [
            {"published_at": {"$gte": cutoff}},
            {"timestamp": {"$gte": cutoff}},
        ],
    }

    pipeline = [
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
                    {"$project": {"topics": 1, "author": 1, "title": 1, "url": 1, "url_resolved": 1, "published_at": 1}},
                ],
                "as": "art",
            }
        },
        {"$match": {"art.0": {"$exists": True}}},
        {"$unwind": "$art"},
        {"$unwind": "$art.topics"},
        {"$match": {"art.topics": {"$exists": True, "$nin": [None, ""]}}},
        {"$limit": 2000},
        {
            "$group": {
                "_id": "$art.topics",
                "articles": {
                    "$push": {
                        "url": {"$ifNull": ["$url", "$art.url"]},
                        "title": {"$ifNull": ["$title", "$art.title"]},
                        "published_at": {"$ifNull": ["$published_at", "$timestamp"]},
                        "entity": "$entity",
                        "author": {"$ifNull": ["$author", "$art.author"]},
                        "source_domain": "$source_domain",
                    }
                },
            }
        },
    ]
    if topic_filter and topic_filter.strip():
        pipeline.insert(-1, {"$match": {"_id": {"$regex": topic_filter.strip(), "$options": "i"}}})

    topics_out: list[dict[str, Any]] = []
    async for doc in em_coll.aggregate(pipeline):
        topic = doc.get("_id", "")
        if not topic:
            continue
        articles_raw = doc.get("articles") or []
        seen_urls: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for a in articles_raw:
            url = (a.get("url") or "").strip().lower()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            pub = a.get("published_at")
            pub_iso = pub.isoformat() if isinstance(pub, datetime) else str(pub or "")[:50]
            deduped.append({
                "url": (a.get("url") or "").strip()[:2000],
                "title": (a.get("title") or "Untitled")[:500],
                "published_at": pub_iso,
                "entity": (a.get("entity") or "").strip(),
                "author": (a.get("author") or "").strip()[:300] if a.get("author") else None,
                "source_domain": (a.get("source_domain") or "").strip()[:200],
            })
        deduped.sort(key=lambda x: x.get("published_at") or "", reverse=True)
        topics_out.append({
            "topic": topic,
            "article_count": len(deduped),
            "articles": deduped[:limit_per_topic],
        })

    topics_out.sort(key=lambda x: -x["article_count"])

    return {
        "client": client_name,
        "competitors": competitor_names,
        "range": range_param,
        "topics": topics_out[:TOPIC_ARTICLES_LIMIT],
    }


async def get_first_mentions(
    client: str,
    range_param: str = "7d",
    topic_filter: Optional[str] = None,
    entity_filter: Optional[str] = None,
) -> dict[str, Any]:
    """
    For each (topic, entity), find the earliest article by published_at and its author.
    No LLM.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    client_name, entities, competitor_names = await _get_client_entities(client)
    if not client_name or not entities:
        return {
            "client": client,
            "competitors": competitor_names or [],
            "range": range_param,
            "first_mentions": [],
        }

    if entity_filter and entity_filter.strip():
        ef = entity_filter.strip()
        if ef in entities:
            entities = [ef]
        else:
            entities = [e for e in entities if ef.lower() in e.lower()] or entities

    delta = _parse_range(range_param)
    cutoff = datetime.now(timezone.utc) - delta

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]

    match_em: dict[str, Any] = {
        "entity": {"$in": entities},
        "$or": [
            {"published_at": {"$gte": cutoff}},
            {"timestamp": {"$gte": cutoff}},
        ],
    }

    pipeline = [
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
                    {"$project": {"topics": 1, "author": 1}},
                ],
                "as": "art",
            }
        },
        {"$match": {"art.0": {"$exists": True}}},
        {"$unwind": "$art"},
        {"$unwind": "$art.topics"},
        {"$match": {"art.topics": {"$exists": True, "$nin": [None, ""]}}},
    ]
    if topic_filter and topic_filter.strip():
        pipeline.append({"$match": {"art.topics": {"$regex": topic_filter.strip(), "$options": "i"}}})

    pipeline.extend([
        {"$sort": {"published_at": 1, "timestamp": 1}},
        {
            "$group": {
                "_id": {"topic": "$art.topics", "entity": "$entity"},
                "first_published_at": {"$first": {"$ifNull": ["$published_at", "$timestamp"]}},
                "first_title": {"$first": "$title"},
                "first_url": {"$first": "$url"},
                "first_author": {"$first": {"$ifNull": ["$author", "$art.author"]}},
                "first_source_domain": {"$first": "$source_domain"},
            }
        },
        {"$sort": {"first_published_at": 1}},
        {"$limit": FIRST_MENTIONS_LIMIT},
    ])

    first_mentions: list[dict[str, Any]] = []
    async for doc in em_coll.aggregate(pipeline):
        gid = doc.get("_id") or {}
        topic = (gid.get("topic") or "").strip()
        entity = (gid.get("entity") or "").strip()
        pub = doc.get("first_published_at")
        pub_iso = pub.isoformat() if isinstance(pub, datetime) else str(pub or "")[:50]
        first_mentions.append({
            "topic": topic,
            "entity": entity,
            "first_published_at": pub_iso,
            "first_title": (doc.get("first_title") or "Untitled")[:500],
            "first_url": (doc.get("first_url") or "").strip()[:2000],
            "first_author": (doc.get("first_author") or "").strip()[:300] if doc.get("first_author") else None,
            "first_source_domain": (doc.get("first_source_domain") or "").strip()[:200],
        })

    return {
        "client": client_name,
        "competitors": competitor_names,
        "range": range_param,
        "first_mentions": first_mentions,
    }


async def get_amplifiers(
    client: str,
    topic: str,
    range_param: str = "7d",
    entity_filter: Optional[str] = None,
) -> dict[str, Any]:
    """
    For a topic, find articles published after the first mention (amplifiers).
    Group by author/outlet. No LLM.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    client_name, entities, competitor_names = await _get_client_entities(client)
    if not client_name or not entities or not (topic or "").strip():
        return {
            "client": client,
            "competitors": competitor_names or [],
            "range": range_param,
            "topic": topic or "",
            "first_mention": None,
            "amplifiers_by_author": [],
            "amplifiers_by_outlet": [],
        }

    if entity_filter and entity_filter.strip():
        ef = entity_filter.strip()
        entities = [e for e in entities if ef.lower() in e.lower()] or entities

    topic_str = (topic or "").strip()
    delta = _parse_range(range_param)
    cutoff = datetime.now(timezone.utc) - delta

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]

    match_em = {
        "entity": {"$in": entities},
        "$or": [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}],
    }

    first_mention_doc = None
    first_pub_dt: Optional[datetime] = None

    pipeline_first = [
        {"$match": match_em},
        {
            "$lookup": {
                "from": ARTICLE_DOCUMENTS_COLLECTION,
                "let": {"em_url": "$url"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {"$or": [{"$eq": ["$url", "$$em_url"]}, {"$eq": ["$url_resolved", "$$em_url"]}]},
                            "topics": {"$in": [topic_str]},
                        }
                    },
                    {"$limit": 1},
                    {"$project": {"topics": 1, "author": 1}},
                ],
                "as": "art",
            }
        },
        {"$match": {"art.0": {"$exists": True}}},
        {"$sort": {"published_at": 1, "timestamp": 1}},
        {"$limit": 1},
    ]

    async for doc in em_coll.aggregate(pipeline_first):
        first_mention_doc = doc
        first_pub_dt = _to_dt(doc.get("published_at") or doc.get("timestamp"))
        break

    if not first_pub_dt:
        return {
            "client": client_name,
            "competitors": competitor_names,
            "range": range_param,
            "topic": topic_str,
            "first_mention": None,
            "amplifiers_by_author": [],
            "amplifiers_by_outlet": [],
        }

    first_mention_out = None
    if first_mention_doc:
        pub = first_mention_doc.get("published_at") or first_mention_doc.get("timestamp")
        first_mention_out = {
            "title": (first_mention_doc.get("title") or "Untitled")[:500],
            "url": (first_mention_doc.get("url") or "").strip()[:2000],
            "author": (first_mention_doc.get("author") or "").strip()[:300] or None,
            "source_domain": (first_mention_doc.get("source_domain") or "").strip()[:200],
            "published_at": pub.isoformat() if isinstance(pub, datetime) else str(pub or "")[:50],
        }

    pipeline_amp = [
        {"$match": match_em},
        {"$match": {"$or": [{"published_at": {"$gt": first_pub_dt}}, {"timestamp": {"$gt": first_pub_dt}}]}},
        {
            "$lookup": {
                "from": ARTICLE_DOCUMENTS_COLLECTION,
                "let": {"em_url": "$url"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {"$or": [{"$eq": ["$url", "$$em_url"]}, {"$eq": ["$url_resolved", "$$em_url"]}]},
                            "topics": {"$in": [topic_str]},
                        }
                    },
                    {"$limit": 1},
                    {"$project": {"topics": 1, "author": 1}},
                ],
                "as": "art",
            }
        },
        {"$match": {"art.0": {"$exists": True}}},
        {"$limit": 500},
        {
            "$group": {
                "_id": {"$ifNull": ["$author", {"$arrayElemAt": ["$art.author", 0]}]},
                "count": {"$sum": 1},
                "articles": {"$push": {"title": "$title", "url": "$url", "published_at": {"$ifNull": ["$published_at", "$timestamp"]}, "source_domain": "$source_domain"}},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": AMPLIFIERS_LIMIT},
    ]

    by_author: list[dict[str, Any]] = []
    async for doc in em_coll.aggregate(pipeline_amp):
        author = doc.get("_id")
        if author is None or (isinstance(author, str) and not author.strip()):
            author = "author unknown"
        else:
            author = str(author).strip()[:300]
        arts = doc.get("articles") or []
        by_author.append({
            "author": author,
            "count": doc.get("count", 0),
            "sample_articles": [
                {
                    "title": (a.get("title") or "Untitled")[:500],
                    "url": (a.get("url") or "").strip()[:2000],
                    "published_at": a.get("published_at").isoformat() if isinstance(a.get("published_at"), datetime) else str(a.get("published_at", ""))[:50],
                }
                for a in arts[:5]
            ],
        })

    pipeline_outlet = [
        {"$match": match_em},
        {"$match": {"$or": [{"published_at": {"$gt": first_pub_dt}}, {"timestamp": {"$gt": first_pub_dt}}]}},
        {
            "$lookup": {
                "from": ARTICLE_DOCUMENTS_COLLECTION,
                "let": {"em_url": "$url"},
                "pipeline": [
                    {"$match": {"$expr": {"$or": [{"$eq": ["$url", "$$em_url"]}, {"$eq": ["$url_resolved", "$$em_url"]}]}, "topics": {"$in": [topic_str]}}},
                    {"$limit": 1},
                    {"$project": {"topics": 1}},
                ],
                "as": "art",
            }
        },
        {"$match": {"art.0": {"$exists": True}}},
        {"$limit": 500},
        {"$group": {"_id": {"$ifNull": ["$source_domain", ""]}, "count": {"$sum": 1}}},
        {"$match": {"_id": {"$ne": "", "$exists": True}}},
        {"$sort": {"count": -1}},
        {"$limit": AMPLIFIERS_LIMIT},
    ]

    by_outlet: list[dict[str, Any]] = []
    async for doc in em_coll.aggregate(pipeline_outlet):
        outlet = (doc.get("_id") or "").strip()[:200] or "unknown"
        by_outlet.append({"outlet": outlet, "count": doc.get("count", 0)})

    return {
        "client": client_name,
        "competitors": competitor_names,
        "range": range_param,
        "topic": topic_str,
        "first_mention": first_mention_out,
        "amplifiers_by_author": by_author,
        "amplifiers_by_outlet": by_outlet,
    }


async def get_journalist_outlet_index(
    client: str,
    range_param: str = "30d",
) -> dict[str, Any]:
    """
    Build journalist -> outlets index from article_documents and entity_mentions where author exists.
    No LLM.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    client_name, entities, competitor_names = await _get_client_entities(client)
    if not client_name or not entities:
        return {
            "client": client,
            "competitors": competitor_names or [],
            "range": range_param,
            "journalists": [],
        }

    delta = _parse_range(range_param)
    cutoff = datetime.now(timezone.utc) - delta

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]
    art_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    match_em = {
        "entity": {"$in": entities},
        "$or": [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}],
    }

    pipeline = [
        {"$match": match_em},
        {"$match": {"author": {"$exists": True, "$nin": [None, ""]}}},
        {"$limit": 5000},
        {
            "$group": {
                "_id": {"$trim": {"input": {"$ifNull": ["$author", ""]}, "chars": " "}},
                "outlets": {"$addToSet": {"$cond": [{"$and": [{"$ne": ["$source_domain", None]}, {"$gt": [{"$strLenCP": {"$ifNull": ["$source_domain", ""]}}, 0]}]}, "$source_domain", None]}},
                "article_count": {"$sum": 1},
            }
        },
        {"$match": {"_id": {"$ne": "", "$exists": True}}},
        {"$project": {"author": "$_id", "outlets": {"$filter": {"input": "$outlets", "as": "o", "cond": {"$and": [{"$ne": ["$$o", None]}, {"$gt": [{"$strLenCP": {"$ifNull": ["$$o", ""]}}, 0]}]}}}, "article_count": 1, "_id": 0}},
        {"$match": {"$expr": {"$gt": [{"$size": "$outlets"}, 0]}}},
        {"$sort": {"article_count": -1}},
        {"$limit": JOURNALIST_OUTLETS_LIMIT},
    ]

    art_match = {
        "entities": {"$in": entities},
        "$or": [{"published_at": {"$gte": cutoff}}, {"fetched_at": {"$gte": cutoff}}],
        "author": {"$exists": True, "$ne": None, "$ne": ""},
        "source_domain": {"$exists": True, "$ne": None, "$ne": ""},
    }
    art_pipeline = [
        {"$match": art_match},
        {"$limit": 5000},
        {
            "$group": {
                "_id": {"$trim": {"input": {"$ifNull": ["$author", ""]}, "chars": " "}},
                "outlets": {"$addToSet": "$source_domain"},
                "article_count": {"$sum": 1},
            }
        },
        {"$match": {"_id": {"$ne": "", "$exists": True}}},
    ]

    combined: dict[str, dict[str, Any]] = {}
    async for doc in em_coll.aggregate(pipeline):
        author = (doc.get("author") or "").strip()[:300]
        if not author:
            continue
        outlets = set(o for o in (doc.get("outlets") or []) if o)
        if author not in combined:
            combined[author] = {"author": author, "outlets": list(outlets), "article_count": doc.get("article_count", 0)}
        else:
            combined[author]["outlets"] = list(set(combined[author]["outlets"]) | outlets)
            combined[author]["article_count"] += doc.get("article_count", 0)

    async for doc in art_coll.aggregate(art_pipeline):
        author = (doc.get("_id") or "").strip()[:300]
        if not author:
            continue
        outlets = set(o for o in (doc.get("outlets") or []) if o)
        if author not in combined:
            combined[author] = {"author": author, "outlets": list(outlets), "article_count": doc.get("article_count", 0)}
        else:
            combined[author]["outlets"] = list(set(combined[author]["outlets"]) | outlets)
            combined[author]["article_count"] += doc.get("article_count", 0)

    journalists = sorted(combined.values(), key=lambda x: -x["article_count"])[:JOURNALIST_OUTLETS_LIMIT]

    return {
        "client": client_name,
        "competitors": competitor_names,
        "range": range_param,
        "journalists": journalists,
    }
