"""
Context-aware entity validation — applied AFTER entity detection.
Discard mentions matching ignore_patterns; require context keyword for ambiguous entities.
Configuration: config/clients.yaml (context_keywords, ignore_patterns per client).
Does not modify the entity detection pipeline.
"""
import re
from pathlib import Path
from typing import Any

import yaml

from app.core.logging import get_logger

logger = get_logger(__name__)

_clients_cache: list[dict[str, Any]] | None = None


def _load_clients() -> list[dict[str, Any]]:
    """Load clients from config/clients.yaml (sync)."""
    global _clients_cache
    if _clients_cache is not None:
        return _clients_cache
    project_root = Path(__file__).resolve().parent.parent.parent
    config_dir = project_root / "config"
    if not config_dir.exists():
        config_dir = Path("/app/config")
    path = config_dir / "clients.yaml"
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    _clients_cache = data.get("clients", [])
    return _clients_cache


def _get_entity_config(entity: str) -> dict[str, Any] | None:
    """Return client config block for this entity (name or competitor)."""
    entity = (entity or "").strip()
    if not entity:
        return None
    entity_lower = entity.lower()
    for c in _load_clients():
        if (c.get("name") or "").strip().lower() == entity_lower:
            return c
        for comp in c.get("competitors") or []:
            if (comp or "").strip().lower() == entity_lower:
                return c
    return None


def get_context_keywords(entity: str) -> list[str]:
    """Return context_keywords for entity from clients.yaml, or empty list.
    Only applies to the primary client name (e.g. Sahi); for competitors (Zerodha, Groww)
    we return [] so we don't over-filter their mentions by the parent client's keywords.
    """
    entity = (entity or "").strip()
    if not entity:
        return []
    entity_lower = entity.lower()
    for c in _load_clients():
        name = (c.get("name") or "").strip().lower()
        if name and entity_lower == name:
            kw = c.get("context_keywords") or []
            return [k.strip() for k in kw if k and isinstance(k, str)] if isinstance(kw, list) else []
        for comp in c.get("competitors") or []:
            if (comp or "").strip().lower() == entity_lower:
                return []
    return []


def get_disambiguated_search_query(entity: str) -> str:
    """Return entity + first context_keyword when entity is ambiguous (e.g. Sahi -> Sahi trading)."""
    entity = (entity or "").strip()
    if not entity:
        return ""
    keywords = get_context_keywords(entity)
    if not keywords:
        return entity
    return f"{entity} {keywords[0]}"


def resolve_to_canonical_entity(query: str) -> str | None:
    """
    Map a search query to the canonical entity name from clients.yaml.
    Handles phrases like 'latest news on Sahi' -> 'Sahi', 'sahi trading app' -> 'Sahi'.
    Returns None if no client/alias/competitor matches.
    """
    q = (query or "").strip()
    if not q:
        return None
    q_lower = q.lower()
    # Build (pattern, canonical) — patterns from name, aliases, competitors; sort by length desc
    candidates: list[tuple[str, str]] = []
    for c in _load_clients():
        name = (c.get("name") or "").strip()
        if not name:
            continue
        canonical = name
        aliases = [a.strip().lower() for a in (c.get("aliases") or []) if a and isinstance(a, str)]
        for a in [name.lower()] + aliases:
            if a and len(a) >= 2:
                candidates.append((a, canonical))
        for comp in c.get("competitors") or []:
            comp = (comp or "").strip()
            if comp:
                candidates.append((comp.lower(), comp))
    candidates.sort(key=lambda x: -len(x[0]))
    for pattern, canonical in candidates:
        if pattern in q_lower:
            # Word boundary for short patterns to reduce false positives (e.g. 'sahi' in 'Angela Sahi')
            if len(pattern) >= 6 or re.search(r"\b" + re.escape(pattern) + r"\b", q_lower):
                return canonical
    return None


def validate_mention_context(entity: str, article_text: str) -> bool:
    """
    Validate entity mention after detection: discard if ignore_patterns match;
    for ambiguous entities (those with context_keywords), require at least one context keyword in text.
    Returns True if mention is valid, False if it should be discarded.
    """
    if not entity or not isinstance(article_text, str):
        return False
    text = article_text.strip().lower()
    if not text:
        return True
    cfg = _get_entity_config(entity)
    if not cfg:
        return True

    ignore_patterns = cfg.get("ignore_patterns") or []
    if isinstance(ignore_patterns, list):
        for pat in ignore_patterns:
            if pat and isinstance(pat, str):
                p = pat.strip().lower()
                if p and re.search(r"\b" + re.escape(p) + r"\b", text):
                    logger.debug("mention_context_rejected_ignore", entity=entity, pattern=p[:50])
                    return False

    context_keywords = cfg.get("context_keywords") or []
    if not isinstance(context_keywords, list) or len(context_keywords) == 0:
        return True
    for kw in context_keywords:
        if kw and isinstance(kw, str) and kw.strip().lower() in text:
            return True
    logger.debug("mention_context_rejected_no_keyword", entity=entity)
    return False
