"""Retrieve mentions from all monitoring sources (media_articles, social_posts)."""
from datetime import datetime
from typing import Any

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

MEDIA_COLLECTION = "media_articles"
SOCIAL_COLLECTION = "social_posts"
MIN_MENTIONS = 10


def _get_db_sync():
    """Get MongoDB database (sync) for retrieval."""
    from pymongo import MongoClient

    config = get_config()
    url = config["settings"].mongodb_url
    db_name = config["mongodb"].get("database", "chat")
    client = MongoClient(url)
    return client[db_name]


def _to_timestamp(obj: Any) -> datetime:
    """Convert various date formats to datetime for sorting."""
    if obj is None:
        return datetime.min
    if isinstance(obj, datetime):
        return obj
    if isinstance(obj, str):
        try:
            return datetime.fromisoformat(obj.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return datetime.min
    return datetime.min


def _format_ts(obj: Any) -> str:
    """Format timestamp as ISO string for output. Never raises."""
    try:
        if obj is None:
            return ""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, str):
            return obj[:50]
        return str(obj)[:50]
    except Exception:
        return ""


def retrieve_mentions(entity: str, min_count: int = MIN_MENTIONS) -> list[dict[str, Any]]:
    """
    Retrieve mentions from media_articles and social_posts for entity.
    Returns unified list: [{title, source, summary, url, timestamp, type}, ...]
    Sorted by timestamp descending. Returns at least min_count if available.
    """
    results: list[dict[str, Any]] = []
    try:
        db = _get_db_sync()
    except Exception as e:
        logger.warning("mention_retrieval_db_failed", error=str(e))
        return []

    try:
        media_coll = db[MEDIA_COLLECTION]
        social_coll = db[SOCIAL_COLLECTION]

        # Query media_articles for entity
        media_cursor = media_coll.find({"entity": entity}).sort("timestamp", -1).limit(20)
        for doc in media_cursor:
            try:
                ts = doc.get("timestamp")
                title = doc.get("title") or ""
                results.append({
                    "title": str(title)[:500],
                    "source": str(doc.get("source") or "")[:200],
                    "summary": str(doc.get("snippet") or "")[:300],
                    "url": str(doc.get("url") or "")[:500],
                    "timestamp": _format_ts(ts),
                    "type": "article",
                })
            except Exception as e:
                logger.debug("mention_retrieval_media_skip", error=str(e))
                continue

        # Query social_posts for entity
        social_cursor = social_coll.find({"entity": entity}).sort("timestamp", -1).limit(20)
        for doc in social_cursor:
            try:
                platform = str(doc.get("platform") or "").lower()
                if platform in ("reddit", "youtube", "twitter"):
                    t = platform
                else:
                    t = "article"
                text = str(doc.get("text") or "")[:300]
                title = text[:80] + "..." if len(text) > 80 else text
                if not title:
                    title = f"{platform} post"
                ts = doc.get("timestamp")
                results.append({
                    "title": title,
                    "source": platform or "social",
                    "summary": text,
                    "url": str(doc.get("url") or "")[:500],
                    "timestamp": _format_ts(ts),
                    "type": t,
                })
            except Exception as e:
                logger.debug("mention_retrieval_social_skip", error=str(e))
                continue

    except Exception as e:
        logger.warning("mention_retrieval_query_failed", entity=entity, error=str(e))
        return []

    # Sort combined by timestamp descending
    def sort_key(r: dict) -> datetime:
        s = r.get("timestamp") or ""
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return datetime.min

    results.sort(key=sort_key, reverse=True)

    return results[:max(min_count, 20)]
