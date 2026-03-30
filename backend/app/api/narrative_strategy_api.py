from __future__ import annotations

from fastapi import APIRouter, Query


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


@router.get("/narratives")
async def narratives_dashboard(
    vertical: str = Query("broker", description="broker | fintech | nbfc | bank | trading (bundle alias)"),
    limit: int = Query(7, ge=1, le=20, description="Max narratives to return"),
):
    """
    UI-ready Narrative Positioning feed.
    Reads the latest stored positioning cluster docs (schema_version=7).
    """
    from app.services.mongodb import get_mongo_client, get_db

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

    q = {"schema_version": 7, "vertical": vertical_key}
    cur = coll.find(q).sort("created_at", -1).limit(int(limit or 7))

    out = []
    async for d in cur:
        dd = dict(d)
        dd.pop("_id", None)
        # Ensure evidence exists for drawer UX
        if isinstance(dd.get("evidence"), list):
            dd["evidence"] = [
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
            dd["evidence"] = []
        # The engine already returns these; keep only the UI contract keys
        out.append(
            {
                "title": str(dd.get("title") or "") or _title_fallback_from_narrative(dd.get("narrative") or ""),
                "narrative": str(dd.get("narrative") or ""),
                "belief": str(dd.get("belief") or ""),
                "why_now": str(dd.get("why_now") or ""),
                "confidence_score": int(dd.get("confidence_score") or 0),
                "signal_strength": str(dd.get("signal_strength") or "emerging"),
                "vertical": str(dd.get("vertical") or ""),
                "categories": dd.get("categories") if isinstance(dd.get("categories"), list) else [],
                "relevance": str(dd.get("relevance") or ""),
                "relevance_reason": str(dd.get("relevance_reason") or ""),
                "market_signal": str(dd.get("market_signal") or ""),
                "companies": dd.get("companies") if isinstance(dd.get("companies"), dict) else {},
                "founder_mode": dd.get("founder_mode") if isinstance(dd.get("founder_mode"), dict) else {},
                "pr_mode": dd.get("pr_mode") if isinstance(dd.get("pr_mode"), dict) else {},
                "evidence": dd.get("evidence") if isinstance(dd.get("evidence"), list) else [],
                "debug": {"cluster_size": int(dd.get("cluster_size") or 0), "sample_posts": dd.get("sample_posts") or []},
            }
        )

    return out

