"""
Media Monitor Service — lightweight news monitoring for clients and competitors.
Uses Google News RSS and DuckDuckGo. No heavy crawling or headless browsers.
"""
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_ARTICLES_PER_SOURCE = 10
MAX_CONCURRENT = 2


def _normalize_entity(name: str) -> str:
    """Normalize entity for mention check."""
    return re.sub(r"\.(com|io|ai|co|org|net)$", "", name.lower().strip())


def _strip_html(text: str, max_len: int = 500) -> str:
    """Strip HTML so we never store raw <a href=...> as snippet."""
    if not text or not isinstance(text, str):
        return ""
    s = text.strip()
    if "<" not in s and ">" not in s:
        return s[:max_len]
    try:
        soup = BeautifulSoup(s, "html.parser")
        return soup.get_text(separator=" ", strip=True)[:max_len]
    except Exception:
        return s[:max_len]


def _resolve_google_news_url(url: str, timeout: float = 4.0) -> str:
    """Resolve Google News redirect to final article URL. Returns original on failure."""
    if not url or "news.google.com" not in url:
        return url or ""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "ZyonMediaMonitor/1.0"})
            final = str(resp.url)
            return final if final and "news.google.com" not in final else url
    except Exception as e:
        logger.debug("resolve_google_news_url_failed", url=url[:80], error=str(e))
        return url


def _entity_mentioned_in_text(entity: str, text: str) -> bool:
    """Check if entity is mentioned in title/snippet (no page fetch)."""
    if not text:
        return False
    text_lower = text.lower()
    normalized = _normalize_entity(entity)
    if not normalized:
        return True
    if normalized in text_lower:
        return True
    for part in normalized.split():
        if len(part) > 2 and part in text_lower:
            return True
    return False


def _search_google_news_rss(entity: str, max_results: int = MAX_ARTICLES_PER_SOURCE) -> list[dict]:
    """Fetch Google News RSS for entity. Lightweight, no page fetches."""
    results = []
    try:
        import feedparser

        query = entity.replace(" ", "+")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url, agent="ZyonMediaMonitor/1.0")
        for e in feed.entries[:max_results]:
            link = e.get("link") or e.get("id", "")
            if not link:
                continue
            if "news.google.com" in link:
                link = _resolve_google_news_url(link)
            title = (e.get("title") or "")[:500]
            raw_summary = (e.get("summary") or "") if hasattr(e, "summary") else ""
            snippet = _strip_html(raw_summary, 300)
            if not _entity_mentioned_in_text(entity, title + " " + snippet):
                continue
            pub = e.get("published_parsed") or e.get("updated_parsed")
            ts = datetime.utcnow()
            if pub:
                try:
                    ts = datetime(*pub[:6])
                except (TypeError, ValueError):
                    pass
            results.append({
                "entity": entity,
                "title": title,
                "url": link,
                "source": (e.get("source", {}) or {}).get("title", "") or urlparse(link).netloc,
                "timestamp": ts,
                "snippet": snippet,
            })
    except Exception as e:
        logger.warning("media_monitor_google_news_failed", entity=entity, error=str(e))
    return results


def _search_duckduckgo(entity: str, max_results: int = MAX_ARTICLES_PER_SOURCE) -> list[dict]:
    """Search DuckDuckGo for news. Lightweight."""
    results = []
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            for r in ddgs.text(f"{entity} news", max_results=max_results):
                link = r.get("href") or r.get("link", "")
                if not link:
                    continue
                title = (r.get("title") or "")[:500]
                snippet = (r.get("body") or "")[:300]
                if not _entity_mentioned_in_text(entity, title + " " + snippet):
                    continue
                results.append({
                    "entity": entity,
                    "title": title,
                    "url": link,
                    "source": urlparse(link).netloc or "",
                    "timestamp": datetime.utcnow(),
                    "snippet": snippet,
                })
    except Exception as e:
        logger.warning("media_monitor_duckduckgo_failed", entity=entity, error=str(e))
    return results


def search_entity(entity: str, client: str, sources: list[str] | None = None) -> list[dict[str, Any]]:
    """
    Search news for an entity. Returns list of articles with entity, client, title, url, source, timestamp, snippet.
    Limit 10 per source, title/snippet validation only (no page fetch).
    """
    if sources is None:
        sources = ["google_news", "duckduckgo"]
    all_results = []
    for src in sources[:2]:  # max 2 sources
        if src == "google_news":
            items = _search_google_news_rss(entity, MAX_ARTICLES_PER_SOURCE)
        elif src == "duckduckgo":
            items = _search_duckduckgo(entity, MAX_ARTICLES_PER_SOURCE)
        else:
            continue
        for item in items:
            item["client"] = client
            all_results.append(item)
    return all_results


def deduplicate_by_url(articles: list[dict]) -> list[dict]:
    """Deduplicate by URL."""
    seen = set()
    out = []
    for a in articles:
        url = (a.get("url") or "").strip().lower()
        if not url:
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(a)
    return out
