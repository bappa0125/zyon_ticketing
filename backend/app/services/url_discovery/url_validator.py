"""Validate URLs by fetching first 1000 chars and verifying company/topic appears."""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

TIMEOUT = 5
MAX_CHARS = 1000
MAX_PAGES = 5
MAX_CONCURRENT = 2


def _extract_text(html: str) -> str:
    """Extract text from HTML, limit size."""
    soup = BeautifulSoup(html[:50000], "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)[:MAX_CHARS]


def _normalize_company(company: str) -> str:
    """Normalize company name for matching (remove TLD, lowercase)."""
    s = re.sub(r"\.(com|io|ai|co|org|net)$", "", company.lower())
    return s.strip()


def validate_url(
    url: str,
    company_or_topic: str,
) -> bool:
    """
    Fetch first 1000 chars, verify company/topic appears.
    Returns True if validated.
    """
    if not url or not company_or_topic:
        return False
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            text = _extract_text(resp.text)
    except Exception as e:
        logger.warning("url_validation_failed", url=url, error=str(e))
        return False

    normalized = _normalize_company(company_or_topic)
    if not normalized:
        return True
    text_lower = text.lower()
    if normalized in text_lower:
        return True
    parts = normalized.replace(".", " ").split()
    if any(p in text_lower for p in parts if len(p) > 2):
        return True
    return False


def validate_results(
    results: list[dict],
    company_or_topic: str,
    max_pages: int = MAX_PAGES,
) -> list[dict]:
    """
    Validate up to max_pages results. Uses max 2 concurrent fetches.
    Returns validated results only.
    """
    validated = []
    to_check = results[:max_pages]
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as ex:
        futures = {ex.submit(validate_url, r.get("link", ""), company_or_topic): r for r in to_check}
        for f in as_completed(futures):
            r = futures[f]
            try:
                if f.result():
                    validated.append(r)
            except Exception:
                pass
    return validated[:10]
