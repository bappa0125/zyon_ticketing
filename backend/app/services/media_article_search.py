"""Media article search — MongoDB-only search over media_articles. No Qdrant.
Used by /api/media/search when media_ingestion/media_index are removed."""
import re
from typing import Optional

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

CACHE_TTL = 3600
CACHE_PREFIX = "media_search:"


def _get_redis():
    from redis import Redis
    cfg = get_config()
    return Redis.from_url(cfg["settings"].redis_url, decode_responses=True)


def _get_media_collection():
    from pymongo import MongoClient
    cfg = get_config()
    client = MongoClient(cfg["settings"].mongodb_url)
    db = client[cfg["mongodb"].get("database", "chat")]
    return db["media_articles"]


def search(query: str, limit: int = 10, use_cache: bool = True) -> list[dict]:
    """
    Search media_articles via MongoDB (title, snippet). Returns top N articles.
    Cache in Redis, TTL 1 hour.
    """
    if use_cache:
        try:
            redis_client = _get_redis()
            cache_key = f"{CACHE_PREFIX}{hash(query) & 0x7FFFFFFFFFFFFFFF}"
            cached = redis_client.get(cache_key)
            if cached:
                import json
                try:
                    return json.loads(cached)
                except Exception:
                    pass
        except Exception:
            pass

    query = (query or "").strip()
    if not query:
        return []

    safe_query = re.escape(query[:100]) if query else ""
    results: list[dict] = []
    try:
        coll = _get_media_collection()
        cursor = coll.find({
            "$or": [
                {"title": {"$regex": safe_query, "$options": "i"}},
                {"snippet": {"$regex": safe_query, "$options": "i"}},
            ]
        }).sort("published_at", -1).limit(limit * 2)
        seen_urls: set[str] = set()
        for d in cursor:
            url = d.get("url") or d.get("source", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append({
                "title": d.get("title", ""),
                "link": url,
                "source": d.get("source", ""),
                "snippet": (d.get("snippet", "") or "")[:300],
                "publish_date": str(d.get("published_at", "")) if d.get("published_at") else None,
            })
            if len(results) >= limit:
                break
    except Exception as e:
        logger.warning("media_article_search_failed", query=query[:50], error=str(e))
        return []

    if use_cache:
        try:
            redis_client = _get_redis()
            cache_key = f"{CACHE_PREFIX}{hash(query) & 0x7FFFFFFFFFFFFFFF}"
            import json
            redis_client.setex(cache_key, CACHE_TTL, json.dumps(results))
        except Exception:
            pass
    return results
