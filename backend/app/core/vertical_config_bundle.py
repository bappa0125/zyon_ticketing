"""
Optional per-vertical config bundles under config/verticals/{political|trading}/.

- If CONFIG_BUNDLE / app.config_bundle is unset and no request ?vertical= → **legacy**:
  only config/<filename> is used (backward compatible).
- If bundle is political|trading → use config/verticals/<bundle>/<filename> when that file
  exists, else fall back to config/<filename>.

Workers: set CONFIG_BUNDLE=trading (or political) in the environment; no request context.

HTTP API: pass ?vertical=political|trading (frontend adds from active client) so one deployment
can serve both bundles without restarting.
"""
from __future__ import annotations

import os
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

from app.config import _get_config_dir, get_config

ALLOWED_BUNDLES = frozenset({"political", "trading"})

request_config_bundle: ContextVar[Optional[str]] = ContextVar("request_config_bundle", default=None)


def normalize_bundle_name(raw: str | None) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if s in ALLOWED_BUNDLES:
        return s
    return None


def get_effective_config_bundle() -> str | None:
    """political | trading | None (legacy root-only)."""
    ctx = normalize_bundle_name(request_config_bundle.get())
    if ctx:
        return ctx
    env = normalize_bundle_name(os.environ.get("CONFIG_BUNDLE") or os.environ.get("CONFIG_VERTICAL"))
    if env:
        return env
    try:
        app_cfg = get_config().get("app") or {}
        if isinstance(app_cfg, dict):
            b = normalize_bundle_name(
                str(app_cfg.get("config_bundle") or app_cfg.get("config_vertical") or "")
            )
            if b:
                return b
    except Exception:
        pass
    return None


def resolve_bundled_config_file(filename: str) -> Path:
    """
    Resolve a file under config/. filename is a basename e.g. clients.yaml, media_sources.yaml.
    """
    base = _get_config_dir()
    bundle = get_effective_config_bundle()
    if not bundle:
        return base / filename
    cand = base / "verticals" / bundle / filename
    if cand.exists():
        return cand
    return base / filename


def resolve_verticals_config_path() -> Path:
    """
    Resolve config/verticals.yaml (per-bundle override supported).
    """
    return resolve_bundled_config_file("verticals.yaml")


def clients_redis_cache_key() -> str:
    """Redis key for async load_clients — include bundle to avoid cross-vertical pollution."""
    b = get_effective_config_bundle() or "default"
    return f"clients_config:{b}"
