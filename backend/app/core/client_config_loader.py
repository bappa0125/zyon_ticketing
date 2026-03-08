"""Client configuration loader. Reads config/clients.yaml, caches in Redis (TTL 300s)."""
import json
from pathlib import Path
from typing import Any

import yaml

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

CLIENTS_CONFIG_KEY = "clients_config"
CACHE_TTL = 300


def _load_clients_from_file() -> list[dict[str, Any]]:
    """Read and parse config/clients.yaml. Called only when cache miss."""
    # Try project_root/config (local) then /app/config (Docker)
    project_root = Path(__file__).resolve().parent.parent.parent
    config_dir = project_root / "config"
    if not config_dir.exists():
        config_dir = Path("/app/config")
    path = config_dir / "clients.yaml"
    if not path.exists():
        logger.warning("clients_config_file_not_found", path=str(path))
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    clients = data.get("clients", [])
    return clients


async def load_clients() -> list[dict[str, Any]]:
    """
    Load monitored clients. Cache in Redis (key: clients_config, TTL: 300s).
    Load file only on cache miss.
    """
    try:
        from app.services.redis_client import get_redis

        r = await get_redis()
        cached = await r.get(CLIENTS_CONFIG_KEY)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.warning("clients_config_redis_miss", error=str(e))

    clients = _load_clients_from_file()
    try:
        from app.services.redis_client import get_redis

        r = await get_redis()
        await r.setex(CLIENTS_CONFIG_KEY, CACHE_TTL, json.dumps(clients))
    except Exception as e:
        logger.warning("clients_config_redis_set_failed", error=str(e))

    return clients
