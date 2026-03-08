"""Redis client for caching."""
from typing import Optional

import redis.asyncio as redis

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

_redis: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        config = get_config()
        url = config["settings"].redis_url
        _redis = redis.from_url(url, decode_responses=True)
        logger.info("Redis connected")
    return _redis


async def get_cached_summary(conversation_id: str) -> Optional[str]:
    r = await get_redis()
    return await r.get(f"summary:{conversation_id}")


async def set_cached_summary(conversation_id: str, summary: str, ttl: int = 3600) -> None:
    r = await get_redis()
    await r.setex(f"summary:{conversation_id}", ttl, summary)
