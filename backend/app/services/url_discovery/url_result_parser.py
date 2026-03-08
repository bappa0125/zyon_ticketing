"""Parse search results into structured format (title, source, link, snippet)."""
from typing import Any


def parse_tavily_result(item: dict) -> dict[str, str]:
    """Parse Tavily API result item."""
    return {
        "title": (item.get("title") or "")[:200],
        "source": (item.get("source", "") or item.get("url", ""))[:100],
        "link": item.get("url") or "",
        "snippet": (item.get("content") or item.get("snippet") or "")[:300],
    }


def parse_duckduckgo_result(item: Any) -> dict[str, str]:
    """Parse DuckDuckGo result (dict or object with title, href, body)."""
    if isinstance(item, dict):
        title = item.get("title", "")
        href = item.get("href", "") or item.get("url", "") or item.get("link", "")
        body = item.get("body", "") or item.get("snippet", "") or item.get("content", "")
    else:
        title = getattr(item, "title", "") or ""
        href = getattr(item, "href", "") or getattr(item, "url", "") or ""
        body = getattr(item, "body", "") or getattr(item, "snippet", "") or ""
    return {
        "title": str(title)[:200],
        "source": _extract_domain(href)[:100],
        "link": str(href),
        "snippet": str(body)[:300],
    }


def _extract_domain(url: str) -> str:
    """Extract domain from URL for source field."""
    if not url:
        return ""
    url = str(url).strip()
    if "://" in url:
        url = url.split("://", 1)[1]
    return url.split("/")[0] if "/" in url else url
