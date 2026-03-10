"""One-off backfill to fix old Google News redirect URLs.

Option 1: targeted backfill (no schema changes, no pipeline redesign).

Fixes two places:
1. article_documents: url/source_domain containing news.google.com
2. entity_mentions: url containing news.google.com (what the UI shows for "Where was X mentioned?")

For each such document we resolve the redirect and update url (and for article_documents
also url_resolved, source_domain, hashes). Safe to run multiple times.
"""

import asyncio
from typing import Any

import httpx

from app.config import get_config
from app.core.logging import get_logger
from app.services.monitoring_ingestion.article_fetcher import (
    _content_hash,
    _normalize_url,
    _source_domain_from_url,
    _url_hash,
)

logger = get_logger(__name__)


async def _get_db():
    """Return Motor database handle using same config as ingestion workers."""
    from motor.motor_asyncio import AsyncIOMotorClient

    config = get_config()
    url = config["settings"].mongodb_url
    db_name = config["mongodb"].get("database", "chat")
    client = AsyncIOMotorClient(url)
    return client[db_name]


def _resolve_url(url: str, timeout: float = 10.0) -> str | None:
    """Follow redirects and return final URL, or None on failure."""
    if not url:
        return None
    try:
        url_original = url.strip()
        if not url_original:
            return None
        headers = {"User-Agent": "ZyonRedirectFixer/1.0"}
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(url_original)
            resp.raise_for_status()
            final = str(resp.url).strip()
            return final or None
    except Exception as e:
        logger.warning("redirect_fix_http_failed", url=url[:100], error=str(e))
        return None


async def fix_redirected_entity_mentions(limit: int | None = None) -> dict[str, Any]:
    """
    Fix entity_mentions whose url still contains news.google.com.
    These are what the UI shows for "Where was X mentioned?" when results come from DB.
    """
    db = await _get_db()
    mentions_coll = db["entity_mentions"]
    query = {"url": {"$regex": "news\\.google\\.com"}}
    cursor = mentions_coll.find(query).sort("_id", 1)
    if limit is not None and limit > 0:
        cursor = cursor.limit(limit)

    processed = 0
    updated = 0
    skipped_resolve_failed = 0
    skipped_no_change = 0

    async for doc in cursor:
        processed += 1
        old_url = (doc.get("url") or "").strip()
        if not old_url:
            skipped_no_change += 1
            continue
        resolved = _resolve_url(old_url)
        if not resolved:
            skipped_resolve_failed += 1
            continue
        if "news.google.com" in resolved or resolved == old_url:
            skipped_no_change += 1
            continue
        try:
            await mentions_coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {"url": resolved[:2000]}},
            )
            updated += 1
            logger.info(
                "redirect_fix_updated_mention",
                entity=doc.get("entity"),
                old_url=old_url[:80],
                new_url=resolved[:80],
            )
        except Exception as e:
            logger.warning("redirect_fix_mention_failed", _id=str(doc["_id"]), error=str(e))

    summary = {
        "processed": processed,
        "updated": updated,
        "skipped_no_change": skipped_no_change,
        "skipped_resolve_failed": skipped_resolve_failed,
    }
    logger.info("redirect_fix_entity_mentions_complete", **summary)
    return summary


async def fix_redirected_articles(limit: int | None = None) -> dict[str, Any]:
    """
    Fix article_documents + entity_mentions that still reference news.google.com.

    - Only touches documents whose url/source_domain contain 'news.google.com'
    - Skips rows where the resolved URL is still a Google News URL
    - Skips rows where the new url_hash already exists on a different document
    """
    db = await _get_db()
    article_coll = db["article_documents"]
    mentions_coll = db["entity_mentions"]

    query = {
        "$or": [
            {"url": {"$regex": "news\\.google\\.com"}},
            {"source_domain": "news.google.com"},
        ]
    }

    cursor = article_coll.find(query).sort("_id", 1)
    if limit is not None and limit > 0:
        cursor = cursor.limit(limit)

    processed = 0
    updated = 0
    skipped_no_change = 0
    skipped_conflict = 0
    skipped_resolve_failed = 0

    async for doc in cursor:
        processed += 1
        _id = doc["_id"]
        old_url = (doc.get("url") or doc.get("url_resolved") or doc.get("url_original") or "").strip()
        if not old_url:
            skipped_no_change += 1
            continue

        resolved = _resolve_url(old_url)
        if not resolved:
            skipped_resolve_failed += 1
            continue
        if "news.google.com" in resolved:
            # Still a Google News URL, nothing to fix
            skipped_no_change += 1
            continue
        if resolved == old_url:
            skipped_no_change += 1
            continue

        # Compute new hashes based on resolved URL
        new_url_hash = _url_hash(resolved)
        new_normalized = _normalize_url(resolved)[:2000]
        title = (doc.get("title") or "")[:1000]
        new_content_hash = _content_hash(title, resolved)

        # Check for url_hash collision with a different document
        existing = await article_coll.find_one({"url_hash": new_url_hash, "_id": {"$ne": _id}})
        if existing is not None:
            skipped_conflict += 1
            continue

        url_original = (doc.get("url_original") or old_url)[:2000]
        url_resolved = resolved[:2000]
        source_domain = _source_domain_from_url(url_resolved) or (doc.get("source_domain") or "")

        update_doc = {
            "url": url_resolved,
            "url_original": url_original,
            "url_resolved": url_resolved,
            "normalized_url": new_normalized,
            "url_hash": new_url_hash,
            "content_hash": new_content_hash,
            "source_domain": source_domain[:200],
        }

        try:
            await article_coll.update_one({"_id": _id}, {"$set": update_doc})
            # Update any entity_mentions that still reference the old URL
            await mentions_coll.update_many({"url": old_url}, {"$set": {"url": url_resolved}})
            updated += 1
            logger.info(
                "redirect_fix_updated_article",
                article_id=str(_id),
                old_url=old_url[:200],
                new_url=url_resolved[:200],
                source_domain=source_domain[:100],
            )
        except Exception as e:
            logger.warning("redirect_fix_update_failed", article_id=str(_id), error=str(e))

    summary = {
        "processed": processed,
        "updated": updated,
        "skipped_no_change": skipped_no_change,
        "skipped_conflict": skipped_conflict,
        "skipped_resolve_failed": skipped_resolve_failed,
    }
    logger.info("redirect_fix_complete", **summary)
    print("article_documents:", summary)
    return summary


async def run_fix_all(limit: int | None = None) -> dict[str, Any]:
    """Fix both article_documents and entity_mentions. Returns combined summary."""
    articles_summary = await fix_redirected_articles(limit=limit)
    mentions_summary = await fix_redirected_entity_mentions(limit=limit)
    print("entity_mentions:", mentions_summary)
    return {
        "article_documents": articles_summary,
        "entity_mentions": mentions_summary,
    }


if __name__ == "__main__":
    result = asyncio.run(run_fix_all())
    art = result["article_documents"]
    ment = result["entity_mentions"]
    if art["processed"] == 0 and ment["processed"] == 0:
        print("\nNo stored documents had news.google.com URLs. If you still see Google News links for Sahi, those results are from live search (Google News RSS), not from the database.")

