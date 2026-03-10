"""Forum ingestion worker — fetch HTML sources (traderji, tradingqna, etc.), extract text, store in article_documents.
Documents then flow through entity_mentions_worker. Does not modify existing pipelines or MongoDB schema."""
import hashlib
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
import trafilatura

from app.core.logging import get_logger

logger = get_logger(__name__)

ARTICLE_DOCUMENTS_COLLECTION = "article_documents"
HTTP_TIMEOUT = 20
USER_AGENT = "ZyonForumIngestion/1.0"


def _normalize_url(url: str) -> str:
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
    return hashlib.md5(_normalize_url(url).encode("utf-8")).hexdigest()


def _content_hash(normalized_title: str, resolved_url: str) -> str:
    title = (normalized_title or "").strip().lower()[:2000]
    url = (resolved_url or "").strip().lower()[:2000]
    return hashlib.md5((title + url).encode("utf-8")).hexdigest()


def _fetch_and_extract(url: str) -> tuple[str | None, str | None, int, str]:
    """Fetch URL, extract main text. Returns (text, title, length, url_resolved)."""
    url_strip = (url or "").strip()[:2000]
    if not url_strip:
        return None, None, 0, url_strip
    try:
        with httpx.Client(
            timeout=HTTP_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        ) as client:
            resp = client.get(url_strip)
            resp.raise_for_status()
            html = resp.text
            url_resolved = str(resp.url)[:2000]
    except Exception as e:
        logger.warning("forum_ingestion_http_failed", url=url_strip[:100], error=str(e))
        return None, None, 0, url_strip
    text = trafilatura.extract(html, include_comments=False, include_tables=False)
    meta = trafilatura.extract_metadata(html)
    title_str = (getattr(meta, "title", None) or "").strip() or urlparse(url_resolved).netloc or "Forum"
    if not text or not text.strip():
        return None, title_str, 0, url_resolved
    return text.strip(), title_str, len(text), url_resolved


async def run_forum_ingestion() -> dict[str, Any]:
    """
    Load HTML sources from media_sources.yaml, fetch entry_url pages, extract discussion text,
    store as article_documents. Same collection as RSS→article_fetcher; entity_mentions_worker will process them.
    Returns {fetched, skipped_duplicate, errors}.
    """
    from motor.motor_asyncio import AsyncIOMotorClient

    from app.config import get_config
    from app.services.monitoring_ingestion.media_source_registry import get_html_sources

    sources = get_html_sources()
    if not sources:
        logger.info("forum_ingestion_no_html_sources")
        return {"fetched": 0, "skipped_duplicate": 0, "errors": 0}

    config = get_config()
    client = AsyncIOMotorClient(config["settings"].mongodb_url)
    db = client[config["mongodb"].get("database", "chat")]
    article_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    try:
        await article_coll.create_index("url_hash", unique=True)
        await article_coll.create_index("content_hash", unique=True)
    except Exception:
        pass

    fetched = 0
    skipped_duplicate = 0
    errors = 0

    for source in sources:
        entry_url = (source.get("entry_url") or "").strip()
        domain = (source.get("domain") or "").strip() or (source.get("name") or "").strip()
        if not entry_url:
            continue
        article_text, title_str, article_length, url_resolved = _fetch_and_extract(entry_url)
        if article_text is None or not article_text.strip():
            errors += 1
            continue
        url_hash = _url_hash(url_resolved)
        existing = await article_coll.find_one({"url_hash": url_hash})
        if existing:
            skipped_duplicate += 1
            continue
        content_hash = _content_hash(title_str, url_resolved)
        existing_content = await article_coll.find_one({"content_hash": content_hash})
        if existing_content:
            skipped_duplicate += 1
            continue
        fetched_at = datetime.now(timezone.utc)
        doc = {
            "url": url_resolved[:2000],
            "url_original": url_resolved[:2000],
            "url_resolved": url_resolved[:2000],
            "normalized_url": _normalize_url(url_resolved)[:2000],
            "url_hash": url_hash,
            "content_hash": content_hash,
            "source_domain": domain[:200],
            "title": (title_str or domain or "Forum")[:1000],
            "published_at": fetched_at,
            "article_text": article_text[:500000],
            "article_length": article_length,
            "fetched_at": fetched_at,
            "entities": [],
        }
        try:
            await article_coll.insert_one(doc)
            fetched += 1
            logger.info("forum_ingestion_stored", source_domain=domain, url=url_resolved[:80])
        except Exception as e:
            err_str = str(e).lower()
            if "duplicate" in err_str or "e11000" in err_str:
                skipped_duplicate += 1
            else:
                errors += 1
                logger.warning("forum_ingestion_insert_failed", url=url_resolved[:100], error=str(e))

    logger.info(
        "forum_ingestion_run_complete",
        fetched=fetched,
        skipped_duplicate=skipped_duplicate,
        errors=errors,
    )
    return {"fetched": fetched, "skipped_duplicate": skipped_duplicate, "errors": errors}
