"""Article extraction - title, author, date, content. Max 2000 chars."""
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_CONTENT_CHARS = 2000
USER_AGENT = "ZyonMediaIndex/1.0 (compatible; +https://zyon.ai)"


def parse_date(raw: str | None) -> Optional[datetime]:
    """Parse common date formats."""
    if not raw or not raw.strip():
        return None
    raw = raw.strip()[:80]
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%d",
        "%d %b %Y",
    ):
        try:
            return datetime.strptime(re.sub(r"\.\d+Z?$", "", raw), fmt)
        except (ValueError, TypeError):
            continue
    return None


def extract_article(url: str, html: str, source_domain: str) -> Optional[dict]:
    """
    Extract title, author, date, content, url, source from HTML.
    Limits content to max 2000 chars.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        # Remove script/style
        for tag in soup(["script", "style"]):
            tag.decompose()
        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)[:500]
        # Common article selectors
        for sel in ["h1", "article h1", ".post-title", ".article-title", ".entry-title"]:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                title = el.get_text(strip=True)[:500]
                break
        if not title:
            title = url.split("/")[-1][:200] or "Untitled"
        # Author
        author = ""
        for sel in ["[rel=author]", ".author", ".byline", "meta[name=author]"]:
            el = soup.select_one(sel)
            if el:
                author = el.get("content", el.get_text(strip=True))[:200] if el.name == "meta" else el.get_text(strip=True)[:200]
                break
        # Date
        pub_date = None
        for sel in ["time[datetime]", "meta[property=article:published_time]", ".date", ".published"]:
            el = soup.select_one(sel)
            if el:
                pub_date = parse_date(el.get("datetime") or el.get("content") or el.get_text(strip=True))
                if pub_date:
                    break
        # Content
        content_parts = []
        for sel in ["article", ".post-content", ".article-body", ".entry-content", "main", ".content"]:
            container = soup.select_one(sel)
            if container:
                for p in container.find_all(["p", "h2", "h3"]):
                    text = p.get_text(strip=True)
                    if text:
                        content_parts.append(text)
                if content_parts:
                    break
        if not content_parts:
            for p in soup.find_all("p")[:20]:
                text = p.get_text(strip=True)
                if text and len(text) > 30:
                    content_parts.append(text)
        content = " ".join(content_parts)[:MAX_CONTENT_CHARS]
        return {
            "title": title,
            "author": author,
            "publish_date": pub_date,
            "content": content,
            "url": url,
            "source": source_domain,
        }
    except Exception as e:
        logger.warning("article_parse_failed", url=url, error=str(e))
        return None


def fetch_and_parse(url: str, source_domain: str) -> Optional[dict]:
    """Fetch URL and parse article. Uses httpx, limits response size."""
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            html = resp.text[:500_000]
        return extract_article(url, html, source_domain)
    except Exception as e:
        logger.warning("article_fetch_failed", url=url, error=str(e))
        return None
