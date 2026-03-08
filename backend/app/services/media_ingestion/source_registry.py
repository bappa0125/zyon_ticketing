"""Source registry - load media sources from config/media_sources.yaml."""
from pathlib import Path
from typing import Any

import yaml

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

_SOURCES: list[dict] | None = None


def _load_sources() -> list[dict]:
    global _SOURCES
    if _SOURCES is not None:
        return _SOURCES
    config = get_config()
    media_cfg = config.get("media_ingestion", config.get("media_index", {}))
    sources = media_cfg.get("sources")
    if sources:
        _SOURCES = sources
        return _SOURCES
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    config_dir = project_root / "config"
    if not config_dir.exists():
        config_dir = Path("/app/config")
    path = config_dir / "media_sources.yaml"
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
            _SOURCES = data.get("sources", [])
    else:
        _SOURCES = []
    logger.info("loaded_media_sources", count=len(_SOURCES or []))
    return _SOURCES or []


def get_sources(limit: int = 5) -> list[dict]:
    """Get sources for this crawl cycle. Max 5 per cycle."""
    return _load_sources()[:limit]


def get_all_sources() -> list[dict]:
    """Get all configured sources (for initial ingestion)."""
    return _load_sources()
