"""Crawl Scheduler — determine which sources are ready to be crawled.
STEP 2: Scheduling logic only. No crawling, no network, no workers."""
import time
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# In-memory state: domain -> last_crawled_at (seconds since epoch)
_last_crawled: dict[str, float] = {}

# Default crawl_frequency (minutes) if missing on source
_DEFAULT_CRAWL_FREQUENCY_MINUTES = 60


def _source_key(source: dict[str, Any]) -> str:
    """Stable key for a source (domain)."""
    domain = source.get("domain")
    if domain and isinstance(domain, str):
        return domain.strip().lower()
    return ""


def _crawl_frequency_minutes(source: dict[str, Any]) -> float:
    """Crawl frequency in minutes. Uses default if missing or invalid."""
    freq = source.get("crawl_frequency")
    if freq is None:
        return float(_DEFAULT_CRAWL_FREQUENCY_MINUTES)
    try:
        return float(freq)
    except (TypeError, ValueError):
        return float(_DEFAULT_CRAWL_FREQUENCY_MINUTES)


def _priority(source: dict[str, Any]) -> int:
    """Priority value for grouping. Lower number = higher priority."""
    p = source.get("priority")
    if p is None:
        return 0
    try:
        return int(p)
    except (TypeError, ValueError):
        return 0


def is_ready(source: dict[str, Any], now_ts: float | None = None) -> bool:
    """
    True if source is ready to be crawled.
    Ready when: never crawled, or (now - last_crawled_at) >= crawl_frequency (minutes).
    """
    key = _source_key(source)
    if not key:
        return False
    now = now_ts if now_ts is not None else time.time()
    last = _last_crawled.get(key)
    if last is None:
        return True
    freq_minutes = _crawl_frequency_minutes(source)
    elapsed_minutes = (now - last) / 60.0
    return elapsed_minutes >= freq_minutes


def get_ready_sources(sources: list[dict[str, Any]], now_ts: float | None = None) -> list[dict[str, Any]]:
    """
    From the given list of sources (e.g. from Media Source Registry), return those
    that are ready to be crawled. Sources never crawled are ready immediately.
    """
    now = now_ts if now_ts is not None else time.time()
    ready: list[dict[str, Any]] = []
    skipped = 0
    by_priority: dict[int, int] = {}

    for s in sources:
        if not _source_key(s):
            continue
        if is_ready(s, now):
            ready.append(s)
            p = _priority(s)
            by_priority[p] = by_priority.get(p, 0) + 1
        else:
            skipped += 1

    logger.info(
        "crawl_scheduler_ready",
        ready_count=len(ready),
        skipped_count=skipped,
        by_priority=dict(sorted(by_priority.items())),
    )
    return ready


def get_ready_sources_by_priority(
    sources: list[dict[str, Any]], now_ts: float | None = None
) -> dict[int, list[dict[str, Any]]]:
    """
    Group ready sources by priority. Lower priority number = higher priority;
    crawler workers will later process higher-priority groups first.
    """
    ready = get_ready_sources(sources, now_ts)
    by_priority: dict[int, list[dict[str, Any]]] = {}
    for s in ready:
        p = _priority(s)
        if p not in by_priority:
            by_priority[p] = []
        by_priority[p].append(s)
    return dict(sorted(by_priority.items()))


def mark_crawled(domain: str) -> None:
    """
    Record that a source (by domain) was crawled at the current time.
    Call this when a crawler completes a source (future step).
    """
    if domain and isinstance(domain, str):
        key = domain.strip().lower()
        if key:
            _last_crawled[key] = time.time()
            logger.debug("crawl_scheduler_marked", domain=key)


def get_last_crawled(domain: str) -> float | None:
    """Return last_crawled_at (seconds since epoch) for a domain, or None if never crawled."""
    if not domain or not isinstance(domain, str):
        return None
    key = domain.strip().lower()
    return _last_crawled.get(key)
