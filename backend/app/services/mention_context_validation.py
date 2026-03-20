"""
Context-aware entity validation — applied AFTER entity detection.
Discard mentions matching ignore_patterns; require context keyword for ambiguous entities.
Configuration: same active clients file as entity detection (clients.yaml or executive file when enabled).
Does not modify the entity detection pipeline.
"""
import re
from typing import Any, Union

from app.core.client_config_loader import load_clients_sync
from app.core.logging import get_logger

logger = get_logger(__name__)


def _load_clients() -> list[dict[str, Any]]:
    """Load clients (sync, shared with entity_detection_service and Redis-backed API)."""
    return load_clients_sync()


def _competitor_name(comp: Union[dict, str, None]) -> str:
    """Canonical name for competitor (string or dict with 'name')."""
    if comp is None:
        return ""
    if isinstance(comp, dict):
        return (comp.get("name") or "").strip()
    return (comp or "").strip() if isinstance(comp, str) else ""


def _get_entity_config(entity: str) -> dict[str, Any] | None:
    """Return config block for this entity: client dict, or for competitor a dict with ignore_patterns + context_keywords from client."""
    entity = (entity or "").strip()
    if not entity:
        return None
    entity_lower = entity.lower()
    for c in _load_clients():
        if (c.get("name") or "").strip().lower() == entity_lower:
            return c
        for comp in c.get("competitors") or []:
            comp_name = _competitor_name(comp)
            if comp_name.lower() == entity_lower:
                if isinstance(comp, dict):
                    comp_ck = comp.get("context_keywords")
                    if isinstance(comp_ck, list) and len(comp_ck) > 0:
                        ck = comp_ck
                    else:
                        ck = c.get("context_keywords") or []
                    return {
                        "ignore_patterns": comp.get("ignore_patterns") or [],
                        "context_keywords": ck if isinstance(ck, list) else [],
                    }
                return c
    return None


def get_context_keywords(entity: str) -> list[str]:
    """Return context_keywords for entity (competitor may override; else inherits client list)."""
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
            if _competitor_name(comp).lower() == entity_lower:
                if isinstance(comp, dict):
                    comp_kw = comp.get("context_keywords")
                    if isinstance(comp_kw, list) and len(comp_kw) > 0:
                        kw = comp_kw
                    else:
                        kw = c.get("context_keywords") or []
                else:
                    kw = c.get("context_keywords") or []
                return [k.strip() for k in kw if k and isinstance(k, str)] if isinstance(kw, list) else []
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
    Map a search query to the canonical entity name from the active clients config.
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
            comp_name = _competitor_name(comp)
            if not comp_name:
                continue
            candidates.append((comp_name.lower(), comp_name))
            if isinstance(comp, dict):
                for a in (comp.get("aliases") or []):
                    if a and isinstance(a, str):
                        a = a.strip().lower()
                        if len(a) >= 2:
                            candidates.append((a, comp_name))
    candidates.sort(key=lambda x: -len(x[0]))
    for pattern, canonical in candidates:
        if pattern in q_lower:
            # Word boundary for short patterns to reduce false positives (e.g. 'sahi' in 'Angela Sahi')
            if len(pattern) >= 6 or re.search(r"\b" + re.escape(pattern) + r"\b", q_lower):
                return canonical
    return None


# Brutal option: these sources are often written without explicit “context keywords”
# (e.g. “trading”, “broker”), but we still want mentions. We skip the context-keyword
# requirement when the source_domain matches one of these.
_FINANCIAL_NEWS_DOMAINS = frozenset({
    "business-standard.com",
    "moneycontrol.com",
    "cnbctv18.com",
    "ndtvprofit.com",
    "economictimes.indiatimes.com",
    "livemint.com",
    "financialexpress.com",
    "thehindubusinessline.com",
    "businesstoday.in",
    "outlookbusiness.com",
    "fortuneindia.com",
    "reuters.com",
    "bloomberg.com",
    "marketwatch.com",
    "fintechfutures.com",
    "thepaypers.com",
    "pymnts.com",
    "entrackr.com",
    "upstox.com",
    "groww.in",
    "angelone.in",
    "dhan.co",
    "finshots.in",
    "freefincal.com",
    "valuepickr.com",
    "safalniveshak.com",
    "getmoneyrich.com",
    "subramoney.com",
})


def _normalize_domain(domain: str) -> str:
    if not domain or not isinstance(domain, str):
        return ""
    d = domain.strip().lower()
    if d.startswith("www."):
        d = d[4:]
    return d[:200]


def validate_mention_context(entity: str, article_text: str, source_domain: str | None = None) -> bool:
    """
    Validate entity mention after detection:
    - discard if ignore_patterns match
    - require context keyword for entities that have context_keywords

    Brutal ingest: if source_domain is a known financial-news domain, skip the
    context-keyword requirement (still respects ignore_patterns).
    """
    if not entity or not isinstance(article_text, str):
        return False
    text = article_text.strip().lower()
    if not text:
        return True

    # Finance/news sources: only ignore_patterns are applied.
    if source_domain:
        sd = _normalize_domain(source_domain)
        if sd and (sd in _FINANCIAL_NEWS_DOMAINS or any(sd.endswith("." + x) for x in _FINANCIAL_NEWS_DOMAINS)):
            cfg = _get_entity_config(entity)
            # If entity has no config, accept.
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
