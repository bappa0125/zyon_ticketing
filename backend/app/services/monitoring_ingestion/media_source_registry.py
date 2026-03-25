"""Media Source Registry — load and expose config/media_sources.yaml.
No crawling, no network, no database. Configuration only."""
from typing import Any, Optional, Tuple

import yaml

from app.core.client_config_loader import _get_config_dir
from app.core.vertical_config_bundle import resolve_bundled_config_file
from app.core.logging import get_logger

logger = get_logger(__name__)

# (path_str, mtime, sources) — reload when file changes (same pattern as load_clients_sync)
_SOURCES_CACHE: Tuple[Optional[str], Optional[float], Optional[list[dict[str, Any]]]] = (None, None, None)


def _is_rss_source(source: dict[str, Any]) -> bool:
    """True if source is RSS-based (has usable rss_feed or crawl_method is rss)."""
    rss = source.get("rss_feed")
    if rss and isinstance(rss, str) and rss.strip():
        return True
    method = (source.get("crawl_method") or "").strip().lower()
    return method == "rss"


def _is_html_source(source: dict[str, Any]) -> bool:
    """True if source is HTML entry-page based (entry_url or crawl_method html)."""
    if source.get("entry_url") and isinstance(source.get("entry_url"), str):
        return True
    method = (source.get("crawl_method") or "").strip().lower()
    return method == "html"


def _validate_and_normalize_source(entry: Any, index: int) -> dict[str, Any] | None:
    """
    Validate minimal structure (domain, crawl_frequency). Log warning if missing.
    Return normalized dict with all keys preserved; None if entry is not a dict.
    """
    if not isinstance(entry, dict):
        logger.warning("media_source_registry_skip_invalid", index=index, reason="not_a_dict")
        return None

    source = dict(entry)
    domain = source.get("domain")
    crawl_frequency = source.get("crawl_frequency")

    if not domain or (isinstance(domain, str) and not domain.strip()):
        logger.warning(
            "media_source_registry_missing_domain",
            index=index,
            domain=domain,
        )
    if crawl_frequency is None:
        logger.warning(
            "media_source_registry_missing_crawl_frequency",
            index=index,
            domain=source.get("domain"),
        )

    return source


def clear_media_sources_cache() -> None:
    """Clear in-process cache (tests, or tooling)."""
    global _SOURCES_CACHE
    _SOURCES_CACHE = (None, None, None)


def load_media_sources() -> list[dict[str, Any]]:
    """
    Read config/media_sources.yaml, parse the list under "sources",
    validate minimal structure (domain, crawl_frequency), and return the list.
    Missing required fields log a warning but do not crash.
    Optional fields (priority, weight, category, name, region, crawl_method, entry_url, rss_feed)
    are preserved as-is. Reloads when media_sources.yaml mtime changes.
    """
    global _SOURCES_CACHE
    path = resolve_bundled_config_file("media_sources.yaml")
    path_key = str(path.resolve())
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = -1.0

    cached_path, cached_mtime, cached_list = _SOURCES_CACHE
    if cached_list is not None and cached_path == path_key and cached_mtime == mtime:
        return cached_list

    if not path.exists():
        logger.warning("media_source_registry_file_not_found", path=str(path))
        _SOURCES_CACHE = (path_key, mtime, [])
        return []

    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error("media_source_registry_load_failed", path=str(path), error=str(e))
        _SOURCES_CACHE = (path_key, mtime, [])
        return []

    raw = data.get("sources")
    if not isinstance(raw, list):
        logger.warning("media_source_registry_no_sources_list", path=str(path))
        _SOURCES_CACHE = (path_key, mtime, [])
        return []

    sources: list[dict[str, Any]] = []
    for i, entry in enumerate(raw):
        normalized = _validate_and_normalize_source(entry, i)
        if normalized is not None:
            sources.append(normalized)

    rss_count = sum(1 for s in sources if _is_rss_source(s))
    html_count = sum(1 for s in sources if _is_html_source(s))

    logger.info(
        "media_source_registry_loaded",
        path=str(path),
        total=len(sources),
        rss_sources=rss_count,
        html_sources=html_count,
    )
    _SOURCES_CACHE = (path_key, mtime, sources)
    return sources


def get_sources_by_priority() -> dict[int, list[dict[str, Any]]]:
    """
    Group loaded sources by priority for future crawl scheduling.
    Keys are priority values (int); default priority is 0 if missing.
    """
    sources = load_media_sources()
    by_priority: dict[int, list[dict[str, Any]]] = {}
    for s in sources:
        p = s.get("priority")
        if p is None:
            p = 0
        else:
            try:
                p = int(p)
            except (TypeError, ValueError):
                p = 0
        if p not in by_priority:
            by_priority[p] = []
        by_priority[p].append(s)
    return by_priority


def get_rss_sources() -> list[dict[str, Any]]:
    """Return only sources that are RSS-based."""
    return [s for s in load_media_sources() if _is_rss_source(s)]


def get_html_sources() -> list[dict[str, Any]]:
    """Return only sources that are HTML entry-page based."""
    return [s for s in load_media_sources() if _is_html_source(s)]
