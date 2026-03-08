"""Streaming crawler - Playwright resource control + extract key content only."""
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)


def _block_resources(route):
    """Block images, videos, fonts, tracking to reduce RAM."""
    cfg = get_config().get("crawler", {})
    req = route.request
    resource_type = req.resource_type
    url = (req.url or "").lower()

    if cfg.get("block_images", True) and resource_type == "image":
        return route.abort()
    if cfg.get("block_videos", True) and resource_type in ("media", "video"):
        return route.abort()
    if cfg.get("block_fonts", True) and resource_type == "font":
        return route.abort()
    if cfg.get("block_tracking", True):
        tracking = ("analytics", "gtm", "facebook", "doubleclick", "googlesyndication", "ads")
        if any(t in url for t in tracking):
            return route.abort()
    return route.continue_()


def _extract_key_content(html: str) -> dict:
    """Extract only: title, main content, pricing blocks, headers. Streaming parse."""
    soup = BeautifulSoup(html, "html.parser")
    out = {"title": "", "main_content": "", "pricing": "", "headers": "", "text_content": ""}

    # Remove script/style to reduce memory
    for tag in soup(["script", "style"]):
        tag.decompose()

    # Title
    t = soup.find("title")
    out["title"] = (t.get_text().strip() if t else "")[:500]

    # Headers (h1, h2)
    headers = []
    for h in soup.find_all(["h1", "h2"]):
        htxt = h.get_text(separator=" ", strip=True)
        if htxt:
            headers.append(htxt)
    out["headers"] = "\n".join(headers[:20])[:2000]

    # Main content: article, main, or body
    main = soup.find(["article", "main"]) or soup.find("body")
    if main:
        out["main_content"] = main.get_text(separator=" ", strip=True)[:15000]

    # Pricing blocks
    pricing_selectors = [
        '[class*="pric"]', '[id*="pric"]',
        '[class*="price"]', '[data-price]',
        '[class*="cost"]', '[class*="subscription"]',
    ]
    pricing_parts = []
    for sel in pricing_selectors:
        for el in soup.select(sel):
            txt = el.get_text(separator=" ", strip=True)
            if txt and len(txt) < 500:
                pricing_parts.append(txt)
    out["pricing"] = "\n".join(pricing_parts[:10])[:2000]

    # Combined text for change detection
    parts = [out["title"], out["headers"], out["main_content"], out["pricing"]]
    out["text_content"] = "\n\n".join(p for p in parts if p) or soup.get_text(separator="\n", strip=True)[:20000]

    return out


def fetch_page(url: str) -> tuple[str, dict]:
    """
    Fetch with Playwright: 1 browser, resource blocking.
    Returns (html_chunk, extracted_content).
    """
    cfg = get_config().get("crawler", {})
    timeout = cfg.get("page_timeout_ms", 15000)
    user_agent = cfg.get("user_agent", "ZyonCompetitorMonitor/1.0")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(
                user_agent=user_agent,
                java_script_enabled=True,
                ignore_https_errors=True,
            )
            page = ctx.new_page()
            if cfg.get("block_images", True) or cfg.get("block_tracking", True):
                page.route("**/*", _block_resources)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            html = page.content()
            page.close()
            ctx.close()
        finally:
            browser.close()

    extracted = _extract_key_content(html)
    return html, extracted


def extract_text(html: str) -> str:
    """Legacy: full text extraction (used by test endpoint)."""
    return _extract_key_content(html)["text_content"]


def normalize_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def fetch_page_simple(url: str) -> tuple[str, dict]:
    """Fallback: httpx (no JS). Returns (html, extracted)."""
    import httpx
    cfg = get_config().get("crawler", {})
    timeout = cfg.get("page_timeout_ms", 15000) / 1000.0
    user_agent = cfg.get("user_agent", "ZyonCompetitorMonitor/1.0")
    resp = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": user_agent})
    resp.raise_for_status()
    extracted = _extract_key_content(resp.text)
    return resp.text, extracted


def crawl_url(url: str, use_playwright: bool = True) -> tuple[str, str]:
    """
    Crawl URL. Returns (html, text_content) for backward compatibility.
    For worker, use crawl_and_extract() to get extracted dict.
    """
    url = normalize_url(url)
    logger.info("crawl_started", url=url)
    if use_playwright:
        try:
            html, extracted = fetch_page(url)
        except Exception as e:
            logger.warning("Playwright crawl failed, fallback to httpx", error=str(e))
            html, extracted = fetch_page_simple(url)
    else:
        html, extracted = fetch_page_simple(url)
    text = extracted["text_content"]
    logger.info("crawl_completed", url=url, text_length=len(text))
    return html, text


def crawl_and_extract(url: str, use_playwright: bool = True) -> dict:
    """
    Crawl and return extracted content only (title, main, pricing, headers).
    For streaming worker - no full HTML retained.
    """
    url = normalize_url(url)
    logger.info("crawl_started", url=url)
    if use_playwright:
        try:
            _, extracted = fetch_page(url)
        except Exception as e:
            logger.warning("Playwright failed, fallback to httpx", error=str(e))
            _, extracted = fetch_page_simple(url)
    else:
        _, extracted = fetch_page_simple(url)
    logger.info("crawl_completed", url=url, text_length=len(extracted.get("text_content", "")))
    return extracted
