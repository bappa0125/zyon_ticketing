"""RSS crawler - fetch article entries from RSS feeds. Max 3 concurrent, 5 sources, 20 articles/cycle."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from app.config import get_config
from app.core.logging import get_logger
from app.services.media_ingestion.source_registry import get_sources, get_all_sources

logger = get_logger(__name__)

MAX_SOURCES_PER_CYCLE = 5
MAX_ARTICLES_PER_CYCLE = 20
MAX_ARTICLES_PER_SOURCE_INITIAL = 200
MAX_CONCURRENT_FETCHES = 3
USER_AGENT = "ZyonMediaIngestion/1.0 (compatible; +https://zyon.ai)"


def _parse_rss_feed(feed_url: str, source_domain: str, max_entries: int = 200) -> list[dict]:
    """Parse RSS feed. Returns list of {url, title, pub_date, source_domain}."""
    entries = []
    try:
        import feedparser
        feed = feedparser.parse(
            feed_url,
            agent=USER_AGENT,
            request_headers={"User-Agent": USER_AGENT},
        )
        for e in feed.entries[:max_entries]:
            link = e.get("link") or e.get("id")
            if not link or "javascript:" in str(link):
                continue
            entries.append({
                "url": str(link).strip(),
                "title": (e.get("title") or "")[:500],
                "pub_date": e.get("published"),
                "source_domain": source_domain,
            })
    except ImportError:
        logger.warning("feedparser_not_installed")
    except Exception as e:
        logger.warning("rss_parse_failed", feed=feed_url, error=str(e))
    return entries


def crawl_rss_sources(
    initial_mode: bool = False,
    max_articles_per_cycle: int = 20,
) -> list[dict]:
    """
    Crawl RSS feeds. Initial mode: all sources, 200 articles/source.
    Incremental: 5 sources, 20 articles total.
    """
    cfg = get_config().get("media_ingestion", {})
    max_sources = cfg.get("max_sources_per_cycle", MAX_SOURCES_PER_CYCLE)
    max_per_cycle = cfg.get("max_articles_per_cycle", max_articles_per_cycle)
    max_per_source = cfg.get("max_articles_per_source_initial", MAX_ARTICLES_PER_SOURCE_INITIAL)

    if initial_mode:
        sources = get_all_sources()
        max_per_source_actual = max_per_source
    else:
        sources = get_sources(limit=max_sources)
        max_per_source_actual = max_per_cycle

    all_entries = []
    for src in sources:
        domain = src.get("domain", "")
        rss = src.get("rss_feed")
        if not rss:
            continue
        entries = _parse_rss_feed(rss, domain, max_entries=max_per_source_actual)
        all_entries.extend(entries)
        if not initial_mode and len(all_entries) >= max_per_cycle:
            break

    return all_entries[:max_per_cycle] if not initial_mode else all_entries[:len(all_entries)]
