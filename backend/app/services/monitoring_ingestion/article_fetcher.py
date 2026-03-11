"""Article Fetcher — fetch article pages and extract readable text. STEP 5.
No entity detection. Updates rss_items status; stores in article_documents."""
import hashlib
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
import trafilatura

from app.core.logging import get_logger

logger = get_logger(__name__)

RSS_ITEMS_COLLECTION = "rss_items"
ARTICLE_DOCUMENTS_COLLECTION = "article_documents"
STATUS_NEW = "new"
STATUS_PROCESSED = "processed"
STATUS_FAILED = "failed"
MAX_BATCH = 20
HTTP_TIMEOUT = 15
USER_AGENT = "ZyonArticleFetcher/1.0"


def _normalize_url(url: str) -> str:
    """Normalize URL for deduplication: lowercase, strip fragment."""
    if not url or not isinstance(url, str):
        return ""
    u = url.strip().lower()
    if u.startswith("http"):
        parsed = urlparse(u)
        path = parsed.path.rstrip("/") or "/"
        normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
        if parsed.query:
            normalized += "?" + parsed.query
        return normalized
    return u


def _url_hash(url: str) -> str:
    """Stable hash of normalized URL for deduplication."""
    norm = _normalize_url(url)
    return hashlib.md5(norm.encode("utf-8")).hexdigest()


def _content_hash(normalized_title: str, resolved_url: str) -> str:
    """Hash for strong dedup: normalized_title + resolved_url (prevents duplicate articles from RSS/aggregators)."""
    title = (normalized_title or "").strip().lower()[:2000]
    url = (resolved_url or "").strip().lower()[:2000]
    return hashlib.md5((title + url).encode("utf-8")).hexdigest()


def _source_domain_from_url(url: str) -> str:
    """Extract source_domain from URL. Never return news.google.com."""
    if not url or not isinstance(url, str):
        return ""
    parsed = urlparse((url or "").strip())
    netloc = (parsed.netloc or "").split(":")[0].lower()
    if not netloc or netloc == "news.google.com":
        return ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc[:200]


def _fetch_and_extract(url: str) -> tuple[str | None, int, str, str]:
    """Fetch URL (follow redirects), extract article text. Returns (text, length, url_original, url_resolved)."""
    url_original = (url or "").strip()[:2000]
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(url_original)
            resp.raise_for_status()
            html = resp.text
            url_resolved = str(resp.url)[:2000]
    except Exception as e:
        logger.warning("article_fetcher_http_failed", url=url_original[:100], error=str(e))
        return None, 0, url_original, url_original
    text = trafilatura.extract(html, include_comments=False, include_tables=False)
    if not text or not text.strip():
        return None, 0, url_original, url_resolved
    return text.strip(), len(text), url_original, url_resolved


async def run_article_fetcher(max_items: int = MAX_BATCH) -> dict[str, Any]:
    """
    Run one article fetch cycle: read rss_items with status=new, fetch each page,
    extract text with trafilatura, store in article_documents (dedup by url_hash),
    update rss_items status to processed or failed. Returns metrics.
    Uses a local Motor client so this works when run after other asyncio.run() calls
    (avoids "Event loop is closed" from the global mongodb client).
    """
    from motor.motor_asyncio import AsyncIOMotorClient

    from app.config import get_config

    config = get_config()
    url = config["settings"].mongodb_url
    db_name = config["mongodb"].get("database", "chat")
    client = AsyncIOMotorClient(url)
    db = client[db_name]
    rss_coll = db[RSS_ITEMS_COLLECTION]
    article_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    try:
        await article_coll.create_index("url_hash", unique=True)
        await article_coll.create_index("content_hash", unique=True)
    except Exception:
        pass

    cursor = rss_coll.find({"status": STATUS_NEW}).limit(max_items)
    items = await cursor.to_list(length=max_items)
    if not items:
        logger.info("article_fetcher_no_new_items")
        return {"articles_fetched": 0, "failures": 0, "duplicates_skipped": 0, "avg_article_length": 0}

    fetched = 0
    failures = 0
    duplicates_skipped = 0
    total_length = 0

    for item in items:
        url = (item.get("url") or "").strip()
        if not url:
            await rss_coll.update_one({"_id": item["_id"]}, {"$set": {"status": STATUS_FAILED}})
            failures += 1
            continue
        article_text, article_length, url_original, url_resolved = _fetch_and_extract(url)
        if article_text is None:
            # Workaround: store metadata-only article so we don't lose the article; entity_mentions_worker will create snippet mentions
            url_for_hash = url_resolved or url_original
            url_hash = _url_hash(url_for_hash)
            content_hash = _content_hash((item.get("title") or ""), url_for_hash)
            existing = await article_coll.find_one({"url_hash": url_hash})
            if not existing:
                existing = await article_coll.find_one({"content_hash": content_hash})
            if existing:
                await rss_coll.update_one({"_id": item["_id"]}, {"$set": {"status": STATUS_PROCESSED}})
                duplicates_skipped += 1
            else:
                source_domain = _source_domain_from_url(url_resolved or url_original) or (item.get("source_domain") or "")[:200]
                summary = (item.get("summary") or "").strip()[:5000]
                title_raw = (item.get("title") or "")[:1000]
                entities: list[str] = []
                try:
                    from app.services.entity_detection_service import detect_entities
                    entities = detect_entities(f"{title_raw} {summary}"[:8000])
                except Exception:
                    pass
                doc = {
                    "url": (url_resolved or url_original)[:2000],
                    "url_original": url_original[:2000],
                    "url_resolved": (url_resolved or url_original)[:2000],
                    "normalized_url": _normalize_url(url_for_hash)[:2000],
                    "url_hash": url_hash,
                    "content_hash": content_hash,
                    "source_domain": source_domain[:200] if source_domain else "",
                    "title": title_raw,
                    "published_at": item.get("published_at"),
                    "article_text": "",
                    "article_length": 0,
                    "fetched_at": datetime.now(timezone.utc),
                    "entities": entities,
                    "summary": summary,
                }
                try:
                    await article_coll.insert_one(doc)
                    await rss_coll.update_one({"_id": item["_id"]}, {"$set": {"status": STATUS_PROCESSED}})
                    fetched += 1
                    logger.info("article_fetcher_stored_metadata_only", url=url_original[:80])
                except Exception as e:
                    err_str = str(e).lower()
                    if "duplicate" in err_str or "e11000" in err_str:
                        await rss_coll.update_one({"_id": item["_id"]}, {"$set": {"status": STATUS_PROCESSED}})
                        duplicates_skipped += 1
                    else:
                        logger.warning("article_fetcher_insert_failed", url=url[:100], error=str(e))
                        await rss_coll.update_one({"_id": item["_id"]}, {"$set": {"status": STATUS_FAILED}})
                        failures += 1
            continue
        # Deduplication and storage use resolved URL (real article URL, not Google News redirect)
        url_hash = _url_hash(url_resolved)
        normalized_url = _normalize_url(url_resolved)[:2000]
        content_hash = _content_hash((item.get("title") or ""), url_resolved)
        existing = await article_coll.find_one({"url_hash": url_hash})
        if existing:
            await rss_coll.update_one({"_id": item["_id"]}, {"$set": {"status": STATUS_PROCESSED}})
            duplicates_skipped += 1
            continue
        existing_by_content = await article_coll.find_one({"content_hash": content_hash})
        if existing_by_content:
            await rss_coll.update_one({"_id": item["_id"]}, {"$set": {"status": STATUS_PROCESSED}})
            duplicates_skipped += 1
            continue
        fetched_at = datetime.now(timezone.utc)
        title_raw = (item.get("title") or "")[:1000]
        entities: list[str] = []
        try:
            from app.services.entity_detection_service import detect_entities
            entities = detect_entities(f"{title_raw} {article_text[:8000]}")
        except Exception:
            pass
        source_domain = _source_domain_from_url(url_resolved) or (item.get("source_domain") or "")[:200]
        doc = {
            "url": url_resolved[:2000],
            "url_original": url_original[:2000],
            "url_resolved": url_resolved[:2000],
            "normalized_url": normalized_url,
            "url_hash": url_hash,
            "content_hash": content_hash,
            "source_domain": source_domain[:200] if source_domain else "",
            "title": title_raw,
            "published_at": item.get("published_at"),
            "article_text": article_text[:500000],
            "article_length": article_length,
            "fetched_at": fetched_at,
            "entities": entities,
            "summary": (item.get("summary") or "").strip()[:5000],
        }
        try:
            await article_coll.insert_one(doc)
        except Exception as e:
            err_str = str(e).lower()
            if "duplicate" in err_str or "e11000" in err_str:
                await rss_coll.update_one({"_id": item["_id"]}, {"$set": {"status": STATUS_PROCESSED}})
                duplicates_skipped += 1
            else:
                logger.warning("article_fetcher_insert_failed", url=url[:100], error=str(e))
                await rss_coll.update_one({"_id": item["_id"]}, {"$set": {"status": STATUS_FAILED}})
                failures += 1
            continue
        await rss_coll.update_one({"_id": item["_id"]}, {"$set": {"status": STATUS_PROCESSED}})
        fetched += 1
        total_length += article_length

    avg_length = round(total_length / fetched, 1) if fetched else 0
    logger.info(
        "article_fetcher_run_complete",
        articles_fetched=fetched,
        failures=failures,
        duplicates_skipped=duplicates_skipped,
        avg_article_length=avg_length,
    )
    return {
        "articles_fetched": fetched,
        "failures": failures,
        "duplicates_skipped": duplicates_skipped,
        "avg_article_length": avg_length,
    }
