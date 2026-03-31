from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.config import get_config

router = APIRouter(tags=["narrative-strategy"])


@router.get("/narrative-strategy/reddit")
async def narrative_strategy_reddit(
    company: str = Query(..., description="Company name (e.g., SBI, Paytm, Bajaj Finance)"),
    client_type: str = Query(..., description="Bank | NBFC | Fintech | Broker"),
    limit: int = Query(8, ge=1, le=20),
):
    """
    Narrative Strategy Engine (Reddit):
    Returns STRICT list output (see user spec).

    Note: This endpoint relies on prior ingestion into Mongo collection
    configured at config.dev.yaml -> narrative_strategy_engine.mongodb.raw_collection.
    """
    from app.services.narrative_strategy_engine import generate_narrative_strategy

    return await generate_narrative_strategy(company=company, client_type=client_type, limit=limit)


@router.get("/narrative-strategy/reddit/engine")
async def narrative_strategy_engine_reddit(
    company: str = Query(..., description="Company name (e.g., SBI, Paytm, Bajaj Finance)"),
    vertical: str = Query(..., description="broker | fintech | nbfc | bank"),
    limit: int = Query(8, ge=1, le=20),
    use_llm: bool = Query(False, description="If true, use LLM to name narratives (slower/costly)"),
):
    """
    Strict consulting-style output:
    [
      {
        "narrative": "...",
        "categories": [],
        "vertical": "...",
        "relevance": "...",
        "gaps": {},
        "recommendations": {}
      }
    ]
    """
    from app.services.narrative_strategy_engine import generate_narrative_strategy_v2

    return await generate_narrative_strategy_v2(company=company, vertical=vertical, limit=limit, use_llm=use_llm)


@router.get("/narrative-strategy/reddit/narratives")
async def narrative_strategy_reddit_narratives(
    limit: int = Query(50, ge=1, le=200, description="Max narratives to return"),
    items: int = Query(120, ge=80, le=1500, description="Max stored posts to cluster (speed vs quality)"),
    use_llm: bool = Query(False, description="If true, use LLM to name narratives (slower/costly)"),
):
    """
    List ALL narratives detected from stored Reddit raw data across configured subreddits.
    """
    from app.services.narrative_strategy_engine import list_market_narratives

    return await list_market_narratives(limit=limit, items=items, use_llm=use_llm)


def _normalize_narratives_vertical(raw: str) -> str:
    """
    UI sends bundle vertical (e.g. trading) via withClientQuery; Mongo stores industry vertical (broker).
    """
    v = (raw or "").strip().lower()
    if v in ("trading", "trading_vertical"):
        return "broker"
    if v in ("broker", "fintech", "nbfc", "bank"):
        return v
    # political / unknown → default to broker so trading clients still see data
    return "broker"


def _vertical_taxonomy_category_ids(vertical_key: str) -> list[str]:
    v = get_config().get("verticals") or {}
    if not isinstance(v, dict):
        return []
    block = v.get(vertical_key)
    if not isinstance(block, dict):
        return []
    cats = block.get("categories")
    if not isinstance(cats, list):
        return []
    out: list[str] = []
    for c in cats:
        if isinstance(c, dict) and str(c.get("id") or "").strip():
            out.append(str(c.get("id")).strip())
    return out


@router.get("/narratives")
async def narratives_dashboard(
    vertical: str = Query("broker", description="broker | fintech | nbfc | bank | trading (bundle alias)"),
    limit: int = Query(7, ge=1, le=50, description="Max narratives to return"),
):
    """
    UI-ready Narrative Positioning feed.
    Reads the latest stored positioning cluster docs (schema_version 7 or 8).

    Response shape: ``{ "narratives": [...], "meta": { fallback_mode, fallback_triggered, ... } }``.
    """
    from app.services.mongodb import get_mongo_client, get_db
    from app.services.narrative_strategy_engine import build_dashboard_min_narratives

    await get_mongo_client()
    db = get_db()
    coll = db["narrative_strategy_clusters"]
    vertical_key = _normalize_narratives_vertical(vertical)

    def _title_fallback_from_narrative(n: str) -> str:
        import re

        s = str(n or "").strip()
        if not s:
            return "Narrative signal"
        s = re.sub(r"[^\w\s-]", " ", s)
        words = [w for w in s.split() if w]
        drop = {
            "users",
            "user",
            "people",
            "investors",
            "traders",
            "they",
            "are",
            "is",
            "was",
            "were",
            "there",
            "this",
            "that",
            "as",
            "with",
            "and",
            "but",
            "so",
            "to",
            "of",
            "in",
            "on",
            "for",
            "their",
            "a",
            "an",
            "the",
        }
        kept = [w for w in words if w.lower() not in drop]
        head = kept[:6] if len(kept) >= 4 else words[:6]
        return " ".join(head[:6]).strip() or "Narrative signal"

    def _pack_row(dd: dict) -> dict:
        if isinstance(dd.get("evidence"), list):
            evidence = [
                {
                    "url": str(e.get("url") or ""),
                    "title": str(e.get("title") or ""),
                    "snippet": str(e.get("snippet") or ""),
                    "subreddit": str(e.get("subreddit") or ""),
                }
                for e in dd["evidence"]
                if isinstance(e, dict) and (e.get("url") or "")
            ]
        else:
            evidence = []
        fm = dd.get("founder_mode") if isinstance(dd.get("founder_mode"), dict) else {}
        wts = str(dd.get("what_to_say") or "").strip()
        if not wts:
            wts = str(fm.get("what_to_say") or "").strip().split("\n")[0].strip()
        dbg = dd.get("debug") if isinstance(dd.get("debug"), dict) else {}
        cs = int(dd.get("cluster_size") or dbg.get("cluster_size") or 0)
        posts = dd.get("sample_posts") if isinstance(dd.get("sample_posts"), list) else dbg.get("sample_posts") or []
        nar = str(dd.get("narrative") or "").strip()
        wim = str(dd.get("why_it_matters") or "").strip()
        if nar and not wim:
            # UI contract: always return a usable why_it_matters line.
            wim = "If this behavior persists, decisions stay reactive and strategy never stabilizes."
        bi = str(dd.get("business_impact") or "").strip()
        if nar and not bi:
            bi = "Higher activity without clarity raises support load and churn risk when outcomes disappoint."
        wts = str(dd.get("what_to_say") or "").strip()
        if not wts:
            wts = str(fm.get("what_to_say") or "").strip().split("\n")[0].strip()
        if not wts:
            wts = "Own a clear decision rule—noise is not a signal."
        src = str(dd.get("source") or "stored")
        source_type = "fallback_generated" if src in ("fallback_generated", "ui_fallback") else "cluster_based"
        return {
            "title": str(dd.get("title") or "") or _title_fallback_from_narrative(dd.get("narrative") or ""),
            "narrative": nar,
            "belief": str(dd.get("belief") or ""),
            "why_now": str(dd.get("why_now") or ""),
            "why_it_matters": wim,
            "business_impact": bi,
            "what_to_say": wts,
            "source": src,
            "source_type": source_type,
            "confidence_score": int(dd.get("confidence_score") or 0),
            "signal_strength": str(dd.get("signal_strength") or "emerging"),
            "signal_reason": str(dd.get("signal_reason") or "").strip(),
            "vertical": str(dd.get("vertical") or vertical_key),
            # Backward compat: keep categories but UI should prefer domain_tags.
            "categories": dd.get("categories") if isinstance(dd.get("categories"), list) else [],
            "behavior_tag": str(dd.get("behavior_tag") or "unclassified_behavior").strip() or "unclassified_behavior",
            "domain_tags": dd.get("domain_tags") if isinstance(dd.get("domain_tags"), list) else [],
            "relevance": str(dd.get("relevance") or ""),
            "relevance_reason": str(dd.get("relevance_reason") or ""),
            "market_signal": str(dd.get("market_signal") or ""),
            "opportunity_line": str(dd.get("opportunity_line") or "").strip(),
            "closest_competitor": dd.get("closest_competitor") if isinstance(dd.get("closest_competitor"), dict) else {"name": "", "reason": ""},
            "distribution_strategy": dd.get("distribution_strategy") if isinstance(dd.get("distribution_strategy"), list) else [],
            "companies": dd.get("companies") if isinstance(dd.get("companies"), dict) else {},
            "founder_mode": fm,
            "pr_mode": dd.get("pr_mode") if isinstance(dd.get("pr_mode"), dict) else {},
            "evidence": evidence,
            "debug": {
                "cluster_size": cs,
                "sample_posts": posts,
                "fallback_low_signal": bool(dbg.get("fallback_low_signal")),
            },
        }

    q = {"schema_version": {"$in": [7, 8]}, "vertical": vertical_key}
    cur = coll.find(q).sort("created_at", -1).limit(int(limit or 7))

    out: list[dict] = []
    async for d in cur:
        dd = dict(d)
        dd.pop("_id", None)
        out.append(_pack_row(dd))
    stored_rows_read = len(out)

    strong_c = sum(1 for r in out if str(r.get("signal_strength")) == "strong")
    emerg_c = sum(1 for r in out if str(r.get("signal_strength")) == "emerging")
    fallback_triggered = False
    reason_summary: list[str] = []

    if strong_c == 0 and emerg_c < 2:
        fallback_triggered = True
        reason_summary.append("dashboard_need_two_emerging_without_strong")
        existing = {str(r.get("narrative") or "") for r in out}
        for pad in build_dashboard_min_narratives(vertical_key):
            if emerg_c >= 2:
                break
            nk = str(pad.get("narrative") or "")
            if nk in existing:
                continue
            out.append(_pack_row(pad))
            emerg_c += 1
            existing.add(nk)
    elif len(out) < 2:
        fallback_triggered = True
        reason_summary.append("dashboard_below_two_total")
        existing = {str(r.get("narrative") or "") for r in out}
        for pad in build_dashboard_min_narratives(vertical_key):
            if len(out) >= 2:
                break
            nk = str(pad.get("narrative") or "")
            if nk in existing:
                continue
            out.append(_pack_row(pad))
            existing.add(nk)

    if not out:
        fallback_triggered = True
        reason_summary.append("dashboard_empty_mongo")
        out = [_pack_row(p) for p in build_dashboard_min_narratives(vertical_key)]

    # Invariant: narratives_returned > 0 only if we had stored rows OR we triggered fallback.
    # If this ever breaks, force fallback and record the correction (never ship "fake narratives").
    if stored_rows_read == 0 and not fallback_triggered and len(out) > 0:
        fallback_triggered = True
        reason_summary.append("invariant_violation_corrected:rows_without_data_or_fallback")
        out = [_pack_row(p) for p in build_dashboard_min_narratives(vertical_key)]

    meta = {
        "fallback_triggered": fallback_triggered,
        "fallback_mode": fallback_triggered,
        # For dashboard feed, treat stored rows as "clusters" for metrics purposes.
        "total_clusters": int(stored_rows_read),
        "clusters_after_filter": int(stored_rows_read),
        "clusters_rejected": 0,
        "reason_summary": reason_summary,
    }
    try:
        await db["narrative_strategy_run_log"].insert_one(
            {
                "pipeline": "narratives_dashboard",
                "created_at": datetime.now(timezone.utc),
                "vertical": vertical_key,
                "fallback_triggered": fallback_triggered,
                "total_clusters": int(stored_rows_read),
                "clusters_after_filter": int(stored_rows_read),
                "clusters_rejected": 0,
                "reason_summary": reason_summary,
                "rejection_reasons": [],
                "narratives_returned": len(out),
            }
        )
    except Exception:
        pass

    return {"narratives": out, "meta": meta}


@router.get("/narratives/by-category")
async def narratives_by_category(
    category: str = Query(..., description="Domain category id (domain_tag)"),
    company: str = Query(..., description="Company name (heatmap column)"),
    vertical: str = Query("broker", description="broker | fintech | nbfc | bank | trading (bundle alias)"),
    limit: int = Query(50, ge=1, le=200, description="Max narratives to return"),
):
    """
    Drilldown feed for heatmap cells.

    Returns narratives filtered by domain tag `category`, sorted by:
      signal_strength DESC (strong first), confidence_score DESC.

    Note: `company` is accepted to match the heatmap click contract; ownership is returned
    in the `companies` map so the UI can render the row for all companies.
    """
    from app.services.mongodb import get_mongo_client, get_db

    await get_mongo_client()
    db = get_db()
    coll = db["narrative_strategy_clusters"]
    vertical_key = _normalize_narratives_vertical(vertical)
    cat = str(category or "").strip()
    _ = str(company or "").strip()  # used by UI for context; keep param required by spec

    if not cat:
        return []

    def _strength_rank(s: str) -> int:
        return 1 if str(s or "").strip().lower() == "strong" else 0

    def _pick_fields(dd: dict) -> dict:
        fm = dd.get("founder_mode") if isinstance(dd.get("founder_mode"), dict) else {}
        wts = str(dd.get("what_to_say") or "").strip()
        if not wts:
            wts = str(fm.get("what_to_say") or "").strip().split("\n")[0].strip()
        return {
            "title": str(dd.get("title") or ""),
            "narrative": str(dd.get("narrative") or ""),
            "belief": str(dd.get("belief") or ""),
            "why_now": str(dd.get("why_now") or ""),
            "signal_strength": str(dd.get("signal_strength") or "emerging"),
            "signal_reason": str(dd.get("signal_reason") or "").strip(),
            "confidence_score": int(dd.get("confidence_score") or 0),
            "companies": dd.get("companies") if isinstance(dd.get("companies"), dict) else {},
            "what_to_say": wts,
            "opportunity_line": str(dd.get("opportunity_line") or "").strip(),
            "closest_competitor": dd.get("closest_competitor") if isinstance(dd.get("closest_competitor"), dict) else {"name": "", "reason": ""},
            "distribution_strategy": dd.get("distribution_strategy") if isinstance(dd.get("distribution_strategy"), list) else [],
        }

    q = {
        "schema_version": {"$in": [7, 8]},
        "vertical": vertical_key,
        "domain_tags": cat,
    }
    cur = coll.find(q).sort("created_at", -1).limit(int(limit or 50))

    rows: list[dict] = []
    async for d in cur:
        dd = dict(d)
        dd.pop("_id", None)
        rows.append(_pick_fields(dd))

    rows.sort(
        key=lambda r: (
            -_strength_rank(r.get("signal_strength")),
            -(int(r.get("confidence_score") or 0)),
        )
    )
    return rows

