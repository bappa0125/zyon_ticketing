"""Redis cache for URL search results."""
import hashlib
import json
from typing import Optional

from redis import Redis

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

CACHE_TTL = 6 * 60 * 60  # 6 hours
PREFIX = "url_discovery:"


def _cache_key(query: str) -> str:
    return PREFIX + hashlib.sha256(query.strip().lower().encode()).hexdigest()


def get_cached(redis: Redis, query: str) -> Optional[list[dict]]:
    """Return cached results if exists."""
    key = _cache_key(query)
    data = redis.get(key)
    if data:
        try:
            return json.loads(data)
        except Exception:
            return None
    return None


def set_cached(redis: Redis, query: str, results: list[dict]) -> None:
    """Store results with 6h TTL."""
    key = _cache_key(query)
    try:
        redis.setex(key, CACHE_TTL, json.dumps(results))
    except Exception as e:
        logger.warning("url_cache_set_failed", error=str(e))


def get_redis() -> Redis:
    url = get_config()["settings"].redis_url
    return Redis.from_url(url, decode_responses=True)
