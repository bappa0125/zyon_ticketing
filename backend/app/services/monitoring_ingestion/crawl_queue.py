"""Crawl Queue — organize ready sources by priority for future crawler workers.
STEP 3: Queue layer only. No crawling, no network, no workers."""
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# priority 1 → high, 2 → medium, 3 → low; missing or other → low
PRIORITY_HIGH = 1
PRIORITY_MEDIUM = 2
PRIORITY_LOW = 3


def _queue_priority(source: dict[str, Any]) -> int:
    """Priority from source config. Default to low (3) if missing or invalid."""
    p = source.get("priority")
    if p is None:
        return PRIORITY_LOW
    try:
        n = int(p)
        if n in (1, 2, 3):
            return n
        return PRIORITY_LOW
    except (TypeError, ValueError):
        return PRIORITY_LOW


def _source_weight(source: dict[str, Any]) -> int:
    """Weight from source config. Higher = preferred within same priority. Default 0."""
    w = source.get("weight")
    if w is None:
        return 0
    try:
        return int(w)
    except (TypeError, ValueError):
        return 0


@dataclass
class CrawlQueues:
    """Three priority queues: high (1), medium (2), low (3)."""

    high: list[dict[str, Any]] = field(default_factory=list)
    medium: list[dict[str, Any]] = field(default_factory=list)
    low: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.high) + len(self.medium) + len(self.low)

    def to_ordered_list(self) -> list[dict[str, Any]]:
        """Order for crawler: high first, then medium, then low. Within each group, by weight desc."""
        high_sorted = sorted(self.high, key=lambda s: -_source_weight(s))
        medium_sorted = sorted(self.medium, key=lambda s: -_source_weight(s))
        low_sorted = sorted(self.low, key=lambda s: -_source_weight(s))
        return high_sorted + medium_sorted + low_sorted


def build_crawl_queue(ready_sources: list[dict[str, Any]]) -> CrawlQueues:
    """
    Receive sources ready for crawling (from the scheduler), distribute them into
    high / medium / low queues by priority. Does not perform crawling or network.
    """
    high: list[dict[str, Any]] = []
    medium: list[dict[str, Any]] = []
    low: list[dict[str, Any]] = []

    for s in ready_sources:
        p = _queue_priority(s)
        if p == PRIORITY_HIGH:
            high.append(s)
        elif p == PRIORITY_MEDIUM:
            medium.append(s)
        else:
            low.append(s)

    queues = CrawlQueues(high=high, medium=medium, low=low)
    logger.info(
        "crawl_queue_built",
        high_count=len(high),
        medium_count=len(medium),
        low_count=len(low),
        total=queues.total,
    )
    return queues


def get_ordered_ready_sources(ready_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Convenience: build queues from ready sources and return the ordered list
    (high → medium → low) for future crawler workers to consume.
    """
    queues = build_crawl_queue(ready_sources)
    return queues.to_ordered_list()
