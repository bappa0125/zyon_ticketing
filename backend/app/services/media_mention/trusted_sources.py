"""Load trusted source domains from config."""
from pathlib import Path
from typing import Any

import yaml

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

_TRUSTED: set[str] | None = None


def _load_trusted() -> set[str]:
    global _TRUSTED
    if _TRUSTED is not None:
        return _TRUSTED
    config = get_config()
    cfg = config.get("media_mention", {})
    domains = cfg.get("trusted_domains", [])
    if domains:
        _TRUSTED = {d.lower() for d in domains}
        return _TRUSTED
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    config_dir = project_root / "config"
    if not config_dir.exists():
        config_dir = Path("/app/config")
    path = config_dir / "trusted_sources.yaml"
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
            domains = data.get("trusted_domains", [])
            _TRUSTED = {str(d).lower() for d in domains}
    else:
        _TRUSTED = set()
    return _TRUSTED or set()


def is_trusted(source: str) -> bool:
    """Check if source domain is trusted."""
    if not source:
        return False
    s = source.lower().strip()
    if "://" in s:
        s = s.split("://", 1)[1]
    domain = s.split("/")[0]
    return domain in _load_trusted()
