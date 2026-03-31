from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.companies_config import require_company
from app.services.mongodb import get_db


def _sha(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def narrative_signature(base: dict[str, Any]) -> dict[str, Any]:
    """
    Stable signature for caching enrichment.
    Avoid volatile fields like created_at / evidence URLs.
    """
    return {
        "vertical": str(base.get("vertical") or "").strip().lower(),
        "title": str(base.get("title") or "").strip()[:120],
        "belief": str(base.get("belief") or "").strip()[:600],
        "narrative": str(base.get("narrative") or "").strip()[:900],
        "behavior_tag": str(base.get("behavior_tag") or "").strip(),
        "domain_tags": [str(x) for x in (base.get("domain_tags") or []) if isinstance(x, str)][:2],
        "signal_strength": str(base.get("signal_strength") or "").strip(),
        "confidence_score": int(base.get("confidence_score") or 0),
        "cluster_size": int(((base.get("debug") or {}).get("cluster_size") or 0)) if isinstance(base.get("debug"), dict) else 0,
    }


async def _ensure_indexes() -> None:
    db = get_db()
    coll = db["narrative_strategy_enrichment_cache"]
    try:
        await coll.create_index("cache_key", unique=True)
        # TTL index
        await coll.create_index("expires_at", expireAfterSeconds=0)
    except Exception:
        return


async def _get_cache(cache_key: str) -> dict[str, Any] | None:
    db = get_db()
    coll = db["narrative_strategy_enrichment_cache"]
    try:
        doc = await coll.find_one({"cache_key": cache_key})
        if not doc:
            return None
        val = doc.get("value")
        return val if isinstance(val, dict) else None
    except Exception:
        return None


async def _set_cache(cache_key: str, value: dict[str, Any], ttl_hours: int = 24) -> None:
    db = get_db()
    coll = db["narrative_strategy_enrichment_cache"]
    expires_at = datetime.now(timezone.utc) + timedelta(hours=int(ttl_hours))
    try:
        await coll.update_one(
            {"cache_key": cache_key},
            {"$set": {"cache_key": cache_key, "value": value, "expires_at": expires_at, "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    except Exception:
        return


async def enrich_narrative(*, base: dict[str, Any], client_slug: str) -> dict[str, Any]:
    """
    Compute-on-read enrichment. MUST NOT be stored back into cluster docs.
    Returns a dict with:
      - client_impact
      - opportunity_line
      - where_to_push (list[str])
      - closest_competitor {name, reason}
    Cached for 24h per (signature + client_slug).
    """
    client = require_company(client_slug)
    sig = narrative_signature(base)
    cache_key = _sha(json.dumps({"sig": sig, "client": client.slug}, sort_keys=True))

    await _ensure_indexes()
    cached = await _get_cache(cache_key)
    if cached:
        return cached

    from app.services.narrative_strategy_llm_router import (
        closest_competitor_llm,
        generate_distribution_strategy,
        generate_opportunity_line,
    )

    narrative = str(base.get("narrative") or "").strip()
    belief = str(base.get("belief") or "").strip()
    companies_map = base.get("companies") if isinstance(base.get("companies"), dict) else {}

    # closest competitor: prefer deterministic from companies map if present
    competitor_slugs = [k for k in companies_map.keys() if isinstance(k, str) and k.strip() and k.strip() != client.slug]
    # if map keys are names (legacy), we still pass them through LLM fallback below.

    closest = {"name": "", "reason": ""}
    if len(competitor_slugs) >= 2:
        try:
            pick = await closest_competitor_llm(narrative=narrative, competitors=competitor_slugs)
            closest = {"name": str(pick.get("name") or ""), "reason": str(pick.get("reason") or "")}
        except Exception:
            closest = {"name": "", "reason": ""}

    opp = ""
    try:
        opp = await generate_opportunity_line(narrative=narrative, companies=[client.name])
    except Exception:
        opp = ""

    where = []
    try:
        where = await generate_distribution_strategy(narrative=narrative)
    except Exception:
        where = []

    # client impact: simple deterministic fallback (no LLM yet) to avoid extra cost;
    # will be replaced by LLM call in the next patch step.
    client_impact = ""
    if belief and narrative:
        client_impact = f"For {client.name}, this behavior pattern can drive distrust and churn if not framed clearly."

    out = {
        "client_impact": client_impact,
        "opportunity_line": opp,
        "where_to_push": where[:3],
        "closest_competitor": closest,
    }
    await _set_cache(cache_key, out, ttl_hours=24)
    return out

