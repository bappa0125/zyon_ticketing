"""Retrieve mentions from all monitoring sources (entity_mentions, media_articles, social_posts)."""
from datetime import datetime
from typing import Any

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

ENTITY_MENTIONS_COLLECTION = "entity_mentions"
ARTICLE_DOCUMENTS_COLLECTION = "article_documents"
MEDIA_COLLECTION = "media_articles"
SOCIAL_COLLECTION = "social_posts"
MIN_MENTIONS = 10
DB_FIRST_LIMIT = 10


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


def _published_at_for_sort(doc: dict) -> datetime:
    """Get sort key from doc: published_at or timestamp."""
    for key in ("published_at", "timestamp", "fetched_at"):
        v = doc.get(key)
        if v is not None:
            return _to_timestamp(v)
    return datetime.min


def retrieve_mentions_db_first(entity: str, limit: int = DB_FIRST_LIMIT) -> list[dict[str, Any]]:
    """
    DB-first retrieval: query entity_mentions, media_articles, social_posts.
    Returns list with title, source_domain, published_at, summary, sentiment, url, type.
    Sort by published_at descending. Used to avoid live search when MongoDB has results.
    """
    if not entity or not entity.strip():
        return []
    entity = entity.strip()
    results: list[dict[str, Any]] = []
    try:
        db = _get_db_sync()
    except Exception as e:
        logger.warning("mention_retrieval_db_failed", error=str(e))
        return []

    try:
        # 1. entity_mentions (if collection exists and has entity field)
        try:
            em_coll = db[ENTITY_MENTIONS_COLLECTION]
            for doc in em_coll.find({"entity": entity}).sort("published_at", -1).limit(limit):
                try:
                    pub = doc.get("published_at") or doc.get("timestamp")
                    results.append({
                        "title": str(doc.get("title") or "")[:500],
                        "source_domain": str(doc.get("source_domain") or doc.get("source") or "")[:200],
                        "published_at": _format_ts(pub),
                        "summary": str(doc.get("summary") or doc.get("snippet") or "")[:500],
                        "sentiment": doc.get("sentiment"),
                        "url": str(doc.get("url") or "")[:500],
                        "type": str(doc.get("type") or "article")[:50],
                        "_sort": _published_at_for_sort(doc),
                    })
                except Exception:
                    continue
        except Exception as e:
            logger.debug("entity_mentions_query_skip", error=str(e))

        # 2. article_documents (by entities list)
        try:
            art_coll = db[ARTICLE_DOCUMENTS_COLLECTION]
            for doc in art_coll.find({"entities": entity}).sort("published_at", -1).limit(limit):
                try:
                    pub = doc.get("published_at") or doc.get("fetched_at")
                    summary = (doc.get("summary") or doc.get("article_text") or "")[:500]
                    results.append({
                        "title": str(doc.get("title") or "")[:500],
                        "source_domain": str(doc.get("source_domain") or doc.get("source") or "")[:200],
                        "published_at": _format_ts(pub),
                        "summary": summary,
                        "sentiment": doc.get("sentiment"),
                        "url": str(doc.get("url") or doc.get("url_resolved") or "")[:500],
                        "type": "article",
                        "_sort": _published_at_for_sort(doc),
                    })
                except Exception:
                    continue
        except Exception as e:
            logger.debug("article_documents_query_skip", error=str(e))

        # 3. media_articles
        media_coll = db[MEDIA_COLLECTION]
        for doc in media_coll.find({"entity": entity}).sort("published_at", -1).limit(limit):
            try:
                ts = doc.get("published_at") or doc.get("timestamp")
                results.append({
                    "title": str(doc.get("title") or "")[:500],
                    "source_domain": str(doc.get("source") or "")[:200],
                    "published_at": _format_ts(ts),
                    "summary": str(doc.get("snippet") or "")[:500],
                    "sentiment": doc.get("sentiment"),
                    "url": str(doc.get("url") or "")[:500],
                    "type": "article",
                    "_sort": _published_at_for_sort(doc),
                })
            except Exception:
                continue

        # 4. social_posts
        social_coll = db[SOCIAL_COLLECTION]
        for doc in social_coll.find({"entity": entity}).sort("published_at", -1).limit(limit):
            try:
                platform = str(doc.get("platform") or "").lower() or "social"
                text = str(doc.get("text") or "")[:300]
                title = text[:80] + "..." if len(text) > 80 else text or f"{platform} post"
                ts = doc.get("published_at") or doc.get("timestamp")
                results.append({
                    "title": title,
                    "source_domain": platform[:200],
                    "published_at": _format_ts(ts),
                    "summary": text[:500],
                    "sentiment": doc.get("sentiment"),
                    "url": str(doc.get("url") or "")[:500],
                    "type": platform if platform in ("reddit", "youtube", "twitter") else "article",
                    "_sort": _published_at_for_sort(doc),
                })
            except Exception:
                continue

    except Exception as e:
        logger.warning("mention_retrieval_db_first_failed", entity=entity, error=str(e))
        return []

    # Dedupe by url, sort by published_at desc, limit
    seen_urls: set[str] = set()
    unique: list[dict] = []
    for r in sorted(results, key=lambda x: x.get("_sort", datetime.min), reverse=True):
        url = (r.get("url") or "").strip().lower()
        if url and url not in seen_urls:
            seen_urls.add(url)
            r2 = {k: v for k, v in r.items() if k != "_sort"}
            unique.append(r2)
            if len(unique) >= limit:
                break
    return unique


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
        media_cursor = media_coll.find({"entity": entity}).sort("published_at", -1).limit(20)
        for doc in media_cursor:
            try:
                ts = doc.get("published_at") or doc.get("timestamp")
                title = doc.get("title") or ""
                results.append({
                    "title": str(title)[:500],
                    "source": str(doc.get("source") or "")[:200],
                    "summary": str(doc.get("snippet") or "")[:300],
                    "url": str(doc.get("url") or "")[:500],
                    "timestamp": _format_ts(ts),
                    "published_at": _format_ts(ts),
                    "sentiment": doc.get("sentiment"),
                    "type": "article",
                })
            except Exception as e:
                logger.debug("mention_retrieval_media_skip", error=str(e))
                continue

        # Query social_posts for entity
        social_cursor = social_coll.find({"entity": entity}).sort("published_at", -1).limit(20)
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
                ts = doc.get("published_at") or doc.get("timestamp")
                results.append({
                    "title": title,
                    "source": platform or "social",
                    "summary": text,
                    "url": str(doc.get("url") or "")[:500],
                    "timestamp": _format_ts(ts),
                    "published_at": _format_ts(ts),
                    "sentiment": doc.get("sentiment"),
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
