"""Media crawler - fetch articles from RSS or HTML. Max 5 sources per cycle."""
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.config import get_config
from app.core.logging import get_logger
from app.services.media_index.source_registry import get_sources
from app.services.media_index.article_parser import extract_article, fetch_and_parse

logger = get_logger(__name__)

USER_AGENT = "ZyonMediaIndex/1.0 (compatible; +https://zyon.ai)"
MAX_SOURCES_PER_CYCLE = 5
MAX_CONCURRENT_FETCHES = 3


def _parse_rss_feed(feed_url: str, source_domain: str) -> list[dict]:
    """Parse RSS feed and return list of {url, title, pub_date}."""
    entries = []
    try:
        import feedparser
        feed = feedparser.parse(
            feed_url,
            agent=USER_AGENT,
            request_headers={"User-Agent": USER_AGENT},
        )
        for e in feed.entries[:15]:
            link = e.get("link") or e.get("id")
            if not link or "javascript:" in link:
                continue
            entries.append({
                "url": link,
                "title": (e.get("title") or "")[:500],
                "pub_date": e.get("published"),
                "source_domain": source_domain,
            })
    except ImportError:
        logger.warning("feedparser_not_installed")
    except Exception as e:
        logger.warning("rss_parse_failed", feed=feed_url, error=str(e))
    return entries


def _discover_articles_html(domain: str, base_url: str) -> list[dict]:
    """Fallback: discover article links from HTML page."""
    entries = []
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(base_url, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text[:200_000], "html.parser")
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if not href or href.startswith("#") or "javascript:" in href:
                continue
            if not href.startswith("http"):
                href = f"https://{domain}{href}" if href.startswith("/") else f"https://{domain}/{href}"
            if domain not in href or href in seen:
                continue
            seen.add(href)
            title = a.get_text(strip=True)[:300] if a.get_text(strip=True) else ""
            if len(title) < 10:
                continue
            entries.append({
                "url": href,
                "title": title,
                "pub_date": None,
                "source_domain": domain,
            })
            if len(entries) >= 15:
                break
    except Exception as e:
        logger.warning("html_discover_failed", domain=domain, error=str(e))
    return entries


def crawl_sources(max_articles: int = 20) -> list[dict]:
    """
    Crawl up to 5 sources, return raw articles (url, title, etc).
    Max articles returned = 20.
    """
    sources = get_sources(limit=MAX_SOURCES_PER_CYCLE)
    all_entries = []
    for src in sources:
        domain = src.get("domain", "")
        rss = src.get("rss_feed")
        base_url = f"https://{domain}"
        if rss:
            entries = _parse_rss_feed(rss, domain)
        else:
            entries = _discover_articles_html(domain, base_url)
        for e in entries:
            e["source_domain"] = domain
        all_entries.extend(entries)
        if len(all_entries) >= max_articles * 2:
            break
    return all_entries[:max_articles * 2]
