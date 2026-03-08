"""Search provider - Tavily primary, DuckDuckGo fallback."""
from typing import Optional

from app.config import get_config
from app.core.logging import get_logger
from app.services.url_discovery.url_result_parser import parse_tavily_result, parse_duckduckgo_result

logger = get_logger(__name__)

MAX_RESULTS = 10


def _search_tavily(query: str, max_results: int = MAX_RESULTS) -> Optional[list[dict]]:
    """Tavily API search. Returns None if no key or import fails."""
    cfg = get_config()
    api_key = cfg["settings"].tavily_api_key or cfg.get("url_discovery", {}).get("tavily_api_key") or ""
    if not api_key:
        return None
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        resp = client.search(
            query=query,
            max_results=min(max_results, 10),
            search_depth="basic",
            include_answer=False,
        )
        results = resp.get("results", [])
        return [parse_tavily_result(r) for r in results if r.get("url")]
    except Exception as e:
        logger.warning("tavily_search_failed", error=str(e))
        return None


def _search_duckduckgo(query: str, max_results: int = MAX_RESULTS) -> list[dict]:
    """DuckDuckGo search fallback - no API key."""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                parsed = parse_duckduckgo_result(r)
                if parsed.get("link"):
                    results.append(parsed)
        return results
    except ImportError:
        return _search_duckduckgo_html(query, max_results)
    except Exception as e:
        logger.warning("duckduckgo_search_failed", error=str(e))
        return _search_duckduckgo_html(query, max_results)


def _search_duckduckgo_html(query: str, max_results: int) -> list[dict]:
    """Fallback: scrape DuckDuckGo HTML when duckduckgo-search not installed."""
    import httpx
    from bs4 import BeautifulSoup

    results = []
    try:
        url = "https://html.duckduckgo.com/html/"
        params = {"q": query}
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ZyonBot/1.0)"}
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            resp = client.post(url, data=params, headers=headers)
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for div in soup.select(".result")[:max_results]:
            a = div.select_one(".result__a")
            snippet_el = div.select_one(".result__snippet")
            if a and a.get("href"):
                href = a.get("href", "")
                if "duckduckgo.com" in href:
                    continue
                title = a.get_text(strip=True)
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                domain = href.split("://", 1)[1].split("/")[0] if "://" in href else href[:50]
                results.append({
                    "title": title[:200],
                    "source": domain[:100],
                    "link": href,
                    "snippet": snippet[:300],
                })
    except Exception as e:
        logger.warning("duckduckgo_html_fallback_failed", error=str(e))
    return results


def search(query: str, max_results: int = MAX_RESULTS) -> list[dict]:
    """
    Search: Tavily first, DuckDuckGo fallback.
    Max 1 API call per request.
    """
    parsed = _search_tavily(query, max_results)
    if parsed:
        return parsed[:max_results]
    return _search_duckduckgo(query, max_results)[:max_results]
