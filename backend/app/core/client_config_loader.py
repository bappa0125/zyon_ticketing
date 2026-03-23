"""Client configuration loader. Reads clients.yaml (or executive_competitor_analysis*.yml when enabled), caches in Redis (TTL 300s).
Sync path: load_clients_sync() for workers (aliases, ignore_patterns, context_keywords same source as API).
Supports legacy (competitors as strings) and structured competitors {name, aliases, ignore_patterns, context_keywords?}."""
import json
from pathlib import Path
from typing import Any, Optional, Tuple

import yaml

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

CLIENTS_CONFIG_KEY = "clients_config"
CACHE_TTL = 300

# UI + ingestion routing: defaults keep legacy behaviour when YAML omits profile fields.
DEFAULT_VERTICAL = "corporate_pr"
ALLOWED_VERTICALS = frozenset({"corporate_pr", "trading", "political"})

DEFAULT_FEATURES: dict[str, Any] = {
    "forums": True,
    "youtube": True,
    "reddit": True,
    "twitter": True,
    "twitter_schema": "legacy",
}
ALLOWED_TWITTER_SCHEMAS = frozenset({"legacy", "political"})


def _competitor_name(comp: Any) -> str:
    """Return canonical competitor name; supports string or dict with 'name'."""
    if comp is None:
        return ""
    if isinstance(comp, dict):
        return (comp.get("name") or "").strip()
    return (comp or "").strip() if isinstance(comp, str) else ""


def get_entity_names(client_obj: dict[str, Any]) -> list[str]:
    """Return [client_name, ...competitor names] from a client block. Supports competitors as strings or dicts."""
    name = (client_obj.get("name") or "").strip()
    if not name:
        return []
    competitors = client_obj.get("competitors") or []
    if not isinstance(competitors, list):
        competitors = []
    names = [name]
    for c in competitors:
        n = _competitor_name(c)
        if n and n not in names:
            names.append(n)
    return names


def get_competitor_names(client_obj: dict[str, Any]) -> list[str]:
    """Return list of competitor names only. Supports competitors as strings or dicts."""
    competitors = client_obj.get("competitors") or []
    if not isinstance(competitors, list):
        return []
    return [n for c in competitors if (n := _competitor_name(c))]


def normalize_vertical(raw: Any) -> str:
    s = (raw or "").strip().lower() if isinstance(raw, str) else ""
    if s in ALLOWED_VERTICALS:
        return s
    return DEFAULT_VERTICAL


def normalize_features(raw: Any) -> dict[str, Any]:
    out = dict(DEFAULT_FEATURES)
    if not isinstance(raw, dict):
        return out
    for key in ("forums", "youtube", "reddit", "twitter"):
        if key in raw and isinstance(raw[key], bool):
            out[key] = raw[key]
    ts = raw.get("twitter_schema")
    if isinstance(ts, str) and ts.strip().lower() in ALLOWED_TWITTER_SCHEMAS:
        out["twitter_schema"] = ts.strip().lower()
    return out


def get_client_profile(client_obj: dict[str, Any]) -> dict[str, Any]:
    """Resolved vertical + feature flags for API and workers (YAML may omit keys)."""
    return {
        "vertical": normalize_vertical(client_obj.get("vertical")),
        "features": normalize_features(client_obj.get("features")),
    }


def _get_config_dir() -> Path:
    project_root = Path(__file__).resolve().parent.parent.parent
    config_dir = project_root / "config"
    if not config_dir.exists():
        config_dir = Path("/app/config")
    return config_dir


def _resolve_clients_config_path() -> Path:
    """Path to active clients file: executive_competitor_analysis*.yml when enabled, else clients.yaml."""
    config_dir = _get_config_dir()
    cfg = get_config()
    exec_cfg = cfg.get("executive_competitor_analysis") or {}
    if isinstance(exec_cfg, dict) and exec_cfg.get("use_this_file"):
        filename = (exec_cfg.get("clients_file") or "executive_competitor_analysis.yml").strip()
        return config_dir / filename
    return config_dir / "clients.yaml"


def _load_clients_from_file() -> list[dict[str, Any]]:
    """Read and parse clients from the resolved config path (no cache)."""
    path = _resolve_clients_config_path()
    if not path.exists():
        logger.warning("clients_config_file_not_found", path=str(path))
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    clients = data.get("clients", [])
    return clients


# (resolved_path_str, mtime, clients) — invalidated when file changes or path toggles (exec vs default)
_SYNC_CLIENTS_CACHE: Tuple[Optional[str], Optional[float], Optional[list[dict[str, Any]]]] = (
    None,
    None,
    None,
)


def load_clients_sync() -> list[dict[str, Any]]:
    """
    Load clients synchronously for workers and entity pipelines (no Redis).
    Same file as async load_clients(): clients.yaml or executive file when use_this_file is set.
    Cached in-process until the file’s mtime changes.
    """
    global _SYNC_CLIENTS_CACHE
    path = _resolve_clients_config_path()
    path_key = str(path.resolve())
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = -1.0
    cached_path, cached_mtime, cached_list = _SYNC_CLIENTS_CACHE
    if cached_list is not None and cached_path == path_key and cached_mtime == mtime:
        return cached_list
    clients = _load_clients_from_file()
    _SYNC_CLIENTS_CACHE = (path_key, mtime, clients)
    return clients


def clear_clients_sync_cache() -> None:
    """Clear in-process sync cache (tests or hot-reload tooling)."""
    global _SYNC_CLIENTS_CACHE
    _SYNC_CLIENTS_CACHE = (None, None, None)


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
