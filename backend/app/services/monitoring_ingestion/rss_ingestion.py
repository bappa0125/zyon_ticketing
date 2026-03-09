"""RSS Metadata Ingestion — fetch RSS feeds, extract metadata, store in MongoDB.
STEP 4: RSS only. No article crawling, no entity detection. Freshness filter applied."""
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser

from app.core.logging import get_logger

logger = get_logger(__name__)

COLLECTION_NAME = "rss_items"
DEFAULT_STATUS = "new"
MAX_FEEDS_PER_RUN = 10
REQUEST_TIMEOUT = 15
DEFAULT_FRESHNESS_HOURS = 72


def _parse_published(entry: Any) -> datetime | None:
    """Parse published/updated date from feed entry to datetime."""
    for key in ("published_parsed", "updated_parsed"):
        val = getattr(entry, key, None)
        if val is None:
            continue
        if hasattr(val, "tm_year"):
            try:
                return datetime(
                    val.tm_year,
                    val.tm_mon,
                    val.tm_mday,
                    val.tm_hour,
                    val.tm_min,
                    min(val.tm_sec, 59),
                    tzinfo=timezone.utc,
                )
            except (TypeError, ValueError):
                pass
    return None


def _extract_entries(feed_url: str, source_domain: str, rss_feed: str) -> list[dict[str, Any]]:
    """Fetch RSS feed and extract article metadata. No article page fetch."""
    try:
        parsed = feedparser.parse(feed_url, request_headers={"User-Agent": "ZyonRSSIngestion/1.0"})
    except Exception as e:
        logger.warning("rss_ingestion_fetch_failed", feed=feed_url, error=str(e))
        return []

    discovered_at = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []

    for entry in getattr(parsed, "entries", []) or []:
        url = (getattr(entry, "link", None) or "").strip()
        if not url:
            continue
        title = (getattr(entry, "title", None) or "").strip() or "(No title)"
        published_at = _parse_published(entry)
        items.append({
            "title": title[:1000],
            "url": url[:2000],
            "source_domain": source_domain,
            "published_at": published_at,
            "discovered_at": discovered_at,
            "rss_feed": rss_feed[:500],
            "status": DEFAULT_STATUS,
        })
    return items


async def run_rss_ingestion(max_feeds: int = MAX_FEEDS_PER_RUN) -> dict[str, int]:
    """
    Run one RSS ingestion cycle: get RSS sources from registry + scheduler + queue,
    fetch up to max_feeds feeds sequentially, extract metadata, apply freshness filter,
    store in rss_items with deduplication by url. Returns feeds_processed, articles_discovered,
    duplicates_skipped, fresh_items_inserted, stale_items_skipped.
    """
    from motor.motor_asyncio import AsyncIOMotorClient

    from app.config import get_config
    from app.services.monitoring_ingestion import (
        get_ready_sources,
        get_ordered_ready_sources,
        mark_crawled,
    )
    from app.services.monitoring_ingestion.media_source_registry import get_rss_sources

    rss_sources = get_rss_sources()
    if not rss_sources:
        logger.info("rss_ingestion_no_rss_sources")
        return {
            "feeds_processed": 0,
            "articles_discovered": 0,
            "duplicates_skipped": 0,
            "fresh_items_inserted": 0,
            "stale_items_skipped": 0,
        }

    ready = get_ready_sources(rss_sources)
    ordered = get_ordered_ready_sources(ready)[:max_feeds]

    config = get_config()
    client = AsyncIOMotorClient(config["settings"].mongodb_url)
    db = client[config["mongodb"].get("database", "chat")]
    coll = db[COLLECTION_NAME]
    # Ensure index for dedup
    try:
        await coll.create_index("url", unique=False)
    except Exception:
        pass

    freshness_hours = (
        config.get("monitoring", {})
        .get("rss_ingestion", {})
        .get("freshness_window_hours", DEFAULT_FRESHNESS_HOURS)
    )
    try:
        freshness_hours = int(freshness_hours)
    except (TypeError, ValueError):
        freshness_hours = DEFAULT_FRESHNESS_HOURS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=freshness_hours)

    feeds_processed = 0
    articles_discovered = 0
    duplicates_skipped = 0
    fresh_inserted = 0
    stale_skipped = 0

    for source in ordered:
        rss_feed = (source.get("rss_feed") or "").strip()
        domain = (source.get("domain") or "").strip()
        if not rss_feed or not domain:
            continue
        entries = _extract_entries(rss_feed, domain, rss_feed)
        feeds_processed += 1
        mark_crawled(domain)
        feed_fresh = 0
        feed_stale = 0
        for item in entries:
            articles_discovered += 1
            published_at = item.get("published_at")
            if published_at is not None and published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
            if published_at is None or published_at < cutoff:
                feed_stale += 1
                stale_skipped += 1
                logger.debug("rss_ingestion_stale_skipped", url=item.get("url", "")[:80], published_at=str(published_at))
                continue
            url = item["url"]
            existing = await coll.find_one({"url": url})
            if existing:
                duplicates_skipped += 1
                continue
            try:
                await coll.insert_one(item)
                feed_fresh += 1
                fresh_inserted += 1
            except Exception as e:
                logger.warning("rss_ingestion_insert_failed", url=url[:100], error=str(e))
                duplicates_skipped += 1
        logger.info(
            "rss_ingestion_feed_processed",
            feed=domain,
            fresh_items_inserted=feed_fresh,
            stale_items_skipped=feed_stale,
        )

    logger.info(
        "rss_ingestion_run_complete",
        feeds_processed=feeds_processed,
        articles_discovered=articles_discovered,
        duplicates_skipped=duplicates_skipped,
        fresh_items_inserted=fresh_inserted,
        stale_items_skipped=stale_skipped,
    )
    return {
        "feeds_processed": feeds_processed,
        "articles_discovered": articles_discovered,
        "duplicates_skipped": duplicates_skipped,
        "fresh_items_inserted": fresh_inserted,
        "stale_items_skipped": stale_skipped,
    }
