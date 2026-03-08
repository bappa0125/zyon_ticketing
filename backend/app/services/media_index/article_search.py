"""Article search - vector + keyword, cache in Redis, top 10."""
from typing import Optional

from app.config import get_config
from app.core.logging import get_logger
from app.services.embedding_service import embed

logger = get_logger(__name__)

CACHE_TTL = 3600
CACHE_PREFIX = "media_search:"


def _get_redis():
    from redis import Redis
    cfg = get_config()
    return Redis.from_url(cfg["settings"].redis_url, decode_responses=True)


def _get_qdrant():
    from qdrant_client import QdrantClient
    cfg = get_config()
    return QdrantClient(url=cfg["settings"].qdrant_url)


def _get_media_collection():
    from pymongo import MongoClient
    cfg = get_config()
    client = MongoClient(cfg["settings"].mongodb_url)
    db = client[cfg["mongodb"].get("database", "chat")]
    return db["media_articles"]


def search(query: str, limit: int = 10, use_cache: bool = True) -> list[dict]:
    """
    Search media index: vector search + keyword. Rank and return top 10.
    Cache in Redis, TTL 1 hour.
    """
    redis_client = _get_redis()
    cache_key = f"{CACHE_PREFIX}{hash(query) & 0x7FFFFFFFFFFFFFFF}"
    if use_cache:
        cached = redis_client.get(cache_key)
        if cached:
            import json
            try:
                return json.loads(cached)
            except Exception:
                pass
    qdrant = _get_qdrant()
    coll_name = "media_article_embeddings"
    query_vec = embed(query)
    vector_results = qdrant.search(
        collection_name=coll_name,
        query_vector=query_vec,
        limit=limit * 2,
    )
    seen_urls = set()
    scored = []
    for r in vector_results:
        url = r.payload.get("url")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        score = r.score or 0
        q_lower = query.lower()
        payload = r.payload
        text = f"{payload.get('title','')} {payload.get('content_preview','')}".lower()
        if q_lower in text:
            score += 0.2
        scored.append({
            "url": url,
            "title": payload.get("title", ""),
            "source": payload.get("source", ""),
            "publish_date": payload.get("publish_date"),
            "entities_detected": payload.get("entities_detected") or payload.get("entities", []),
            "content_preview": payload.get("content_preview", ""),
            "score": score,
        })
    # Keyword fallback in MongoDB
    import re as re_module
    safe_query = re_module.escape(query[:100]) if query else ""
    kw_cursor = []
    if safe_query:
        try:
            mongo = _get_media_collection()
            kw_cursor = mongo.find({
                "$or": [
                    {"title": {"$regex": safe_query, "$options": "i"}},
                    {"content": {"$regex": safe_query, "$options": "i"}},
                ]
            }).limit(limit)
        except Exception:
            kw_cursor = []
    try:
        for d in kw_cursor:
            url = d.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                scored.append({
                    "url": url,
                    "title": d.get("title", ""),
                    "source": d.get("source", ""),
                    "publish_date": str(d.get("publish_date")) if d.get("publish_date") else None,
                    "entities_detected": d.get("entities_detected", []),
                    "content_preview": (d.get("content", "") or "")[:300],
                    "score": 0.5,
                })
    except Exception:
        pass
    scored.sort(key=lambda x: x["score"], reverse=True)
    results = [{"title": x["title"], "link": x["url"], "source": x["source"], "snippet": x["content_preview"], "publish_date": x.get("publish_date")} for x in scored[:limit]]
    if use_cache:
        import json
        redis_client.setex(cache_key, CACHE_TTL, json.dumps(results))
    return results
