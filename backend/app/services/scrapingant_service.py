from __future__ import annotations

import json
import re
import html
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_config
from app.core.logging import get_logger
from app.services.redis_client import get_redis

logger = get_logger(__name__)


SCRAPINGANT_ENDPOINT = "https://api.scrapingant.com/v2/general"


def _api_key() -> str:
    return (get_config()["settings"].scrapingant_api_key or "").strip()


def _daily_key(prefix: str = "scrapingant") -> str:
    d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{prefix}:calls:{d}"


async def can_spend_call(daily_cap: int) -> bool:
    if daily_cap <= 0:
        return False
    r = await get_redis()
    key = _daily_key()
    try:
        raw = await r.get(key)
        used = int(raw or 0)
    except Exception:
        used = 0
    return used < daily_cap


async def record_call() -> None:
    r = await get_redis()
    key = _daily_key()
    try:
        # keep 2 days for safety
        await r.incr(key)
        await r.expire(key, 172800)
    except Exception:
        pass


async def fetch_json_via_scrapingant(url: str, *, timeout_s: float = 45.0, daily_cap: int = 50) -> Any:
    """
    Fetch a URL through ScrapingAnt and parse JSON response.
    Counts against a daily cap (Redis).
    """
    key = _api_key()
    if not key:
        raise RuntimeError("SCRAPINGANT_API_KEY not set")
    if not await can_spend_call(daily_cap=daily_cap):
        raise RuntimeError("ScrapingAnt daily cap reached")

    params = {"url": url, "x-api-key": key}
    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
        resp = await client.get(SCRAPINGANT_ENDPOINT, params=params)
        if resp.status_code != 200:
            raise httpx.HTTPStatusError(f"ScrapingAnt HTTP {resp.status_code}", request=resp.request, response=resp)
        body = resp.text

    await record_call()

    def _try_parse_json(s: str) -> Any:
        return json.loads((s or "").strip())

    try:
        return _try_parse_json(body)
    except Exception:
        # ScrapingAnt sometimes wraps the upstream payload in HTML with a <pre> block.
        m = re.search(r"<pre[^>]*>([\s\S]*?)</pre>", body or "", re.IGNORECASE)
        if m:
            candidate = html.unescape((m.group(1) or "").strip())
            try:
                return _try_parse_json(candidate)
            except Exception as e2:
                logger.warning(
                    "scrapingant_non_json",
                    error=str(e2),
                    body_preview=(candidate or "")[:200],
                )
                raise

        logger.warning("scrapingant_non_json", error="no_json_found", body_preview=(body or "")[:200])
        raise

