"""
Rule-based narrative tags from config/narrative_taxonomy.yaml.
Supports forum + article mentions; used for narrative source/amplifier/positioning analytics.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core.logging import get_logger

logger = get_logger(__name__)

_FORUM_PAGE_SUFFIXES = (
    "tradingqna.com",
    "valuepickr.com",
    "traderji.com",
)
_FORUM_FEED_DOMAINS = frozenset({
    "tradingqna.com",
    "valuepickr.com",
    "news.ycombinator.com",
})


def _config_dir() -> Path:
    project_root = Path(__file__).resolve().parent.parent.parent
    d = project_root / "config"
    if d.exists():
        return d
    return Path("/app/config")


@lru_cache(maxsize=1)
def _load_taxonomy_raw() -> dict[str, Any]:
    path = _config_dir() / "narrative_taxonomy.yaml"
    if not path.exists():
        logger.warning("narrative_taxonomy_missing", path=str(path))
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def clear_narrative_taxonomy_cache() -> None:
    _load_taxonomy_raw.cache_clear()


def get_forum_narrative_frame() -> dict[str, Any]:
    data = _load_taxonomy_raw()
    return dict(data.get("forum_narrative_frame") or {})


def tag_text_for_narratives(text: str, max_tags: int | None = None) -> tuple[list[str], str | None]:
    """
    Score tags by keyword hits in text (case-insensitive substring).
    Returns (ordered tag ids up to max_tags, primary tag id or None).
    """
    data = _load_taxonomy_raw()
    tags_cfg = data.get("tags") or []
    if max_tags is None:
        max_tags = int(data.get("max_tags_per_mention") or 2)
    max_tags = max(1, min(max_tags, 5))

    if not text or not isinstance(text, str):
        return [], None

    blob = text.lower()
    scores: dict[str, int] = {}

    for t in tags_cfg:
        if not isinstance(t, dict):
            continue
        tid = (t.get("id") or "").strip()
        if not tid:
            continue
        kws = t.get("keywords") or []
        if not isinstance(kws, list):
            continue
        s = 0
        for kw in kws:
            if not kw or not isinstance(kw, str):
                continue
            k = kw.strip().lower()
            if len(k) < 2:
                continue
            if k in blob:
                s += max(1, blob.count(k))
        if s > 0:
            scores[tid] = s

    if not scores:
        return [], None

    ordered = sorted(scores.keys(), key=lambda x: (-scores[x], x))
    picked = ordered[:max_tags]
    primary = picked[0] if picked else None
    return picked, primary


def score_all_narrative_themes(text: str) -> list[tuple[str, int]]:
    """
    Score every taxonomy tag against text (keyword hits). Used for forum theme digest
    (unbranded discourse) — not limited to top-2 tags like tag_text_for_narratives.
    Returns [(tag_id, score), ...] sorted by score descending, scores > 0 only.
    """
    data = _load_taxonomy_raw()
    tags_cfg = data.get("tags") or []
    if not text or not isinstance(text, str):
        return []
    blob = text.lower()
    scores: dict[str, int] = {}
    for t in tags_cfg:
        if not isinstance(t, dict):
            continue
        tid = (t.get("id") or "").strip()
        if not tid:
            continue
        kws = t.get("keywords") or []
        if not isinstance(kws, list):
            continue
        s = 0
        for kw in kws:
            if not kw or not isinstance(kw, str):
                continue
            k = kw.strip().lower()
            if len(k) < 2:
                continue
            if k in blob:
                s += max(1, blob.count(k))
        if s > 0:
            scores[tid] = s
    ordered = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    return ordered


def get_narrative_tag_meta() -> dict[str, dict[str, str]]:
    """Map tag id -> {label, description}."""
    data = _load_taxonomy_raw()
    tags_cfg = data.get("tags") or []
    out: dict[str, dict[str, str]] = {}
    for t in tags_cfg:
        if not isinstance(t, dict):
            continue
        tid = (t.get("id") or "").strip()
        if not tid:
            continue
        out[tid] = {
            "label": (t.get("label") or tid).strip(),
            "description": (t.get("description") or "").strip()[:500],
        }
    return out


def is_forum_document(source_domain: str, feed_domain: str) -> bool:
    """True if this article should be treated as forum-sourced for narrative (page or RSS registry)."""
    sd = (source_domain or "").strip().lower()
    fd = (feed_domain or "").strip().lower()
    if fd in _FORUM_FEED_DOMAINS:
        return True
    if not sd:
        return False
    if sd.startswith("www."):
        sd = sd[4:]
    for suf in _FORUM_PAGE_SUFFIXES:
        if sd == suf or sd.endswith("." + suf):
            return True
    if "forum." in sd and "valuepickr" in sd:
        return True
    return False


def forum_site_key(source_domain: str, feed_domain: str) -> str | None:
    """Stable site key for dashboards: tradingqna | valuepickr | hackernews | traderji."""
    sd = (source_domain or "").strip().lower()
    fd = (feed_domain or "").strip().lower()
    if fd.startswith("www."):
        fd = fd[4:]
    if sd.startswith("www."):
        sd = sd[4:]

    if fd == "news.ycombinator.com" or "ycombinator" in fd:
        return "hackernews"
    if "tradingqna" in sd or fd == "tradingqna.com":
        return "tradingqna"
    if "valuepickr" in sd or "valuepickr" in fd:
        return "valuepickr"
    if "traderji" in sd:
        return "traderji"
    return None
