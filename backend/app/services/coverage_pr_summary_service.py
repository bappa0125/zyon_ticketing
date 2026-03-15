"""
Coverage PR Summary — 1 LLM call per client per day.

Summarizes competitor coverage page results: Sahi (client) coverage, competitor coverage,
and actionable intel for the PR team (what to target). Stored in coverage_pr_summary.
Runs once per day (scheduler + master backfill).
"""

from datetime import datetime, timezone
from typing import Any

from app.core.client_config_loader import load_clients
from app.core.logging import get_logger
from app.services.coverage_service import (
    compute_coverage,
    get_article_counts,
    get_competitor_only_articles,
    get_mentions_client_and_competitors,
)

logger = get_logger(__name__)

COLLECTION = "coverage_pr_summary"


async def _llm_coverage_summary(
    client_name: str,
    coverage: list[dict],
    counts: dict[str, Any],
    competitor_sample: list[dict],
    mentions_sample: list[dict],
) -> str:
    """One LLM call: actionable PR summary from coverage stats and sample articles."""
    from app.services.llm_gateway import LLMGateway

    coverage_txt = "\n".join(
        f"- {r.get('entity', '')}: {r.get('mentions', 0)} mentions"
        for r in (coverage or [])
    )
    counts_txt = (
        f"Total articles: {counts.get('total_articles', 0)}. "
        f"Articles with {client_name}: {counts.get('articles_with_client_mentioned', 0)}. "
        f"Competitor-only: {counts.get('competitor_only_articles', 0)}."
    )
    comp_sample_txt = "\n".join(
        f"- {a.get('title', '')[:80]} | {a.get('source_domain', '')} | entities: {', '.join(a.get('entities') or [])}"
        for a in (competitor_sample or [])[:5]
    )
    mentions_txt = "\n".join(
        f"- {m.get('entity', '')}: {m.get('title', '')[:80]} | {m.get('source_domain', '')}"
        for m in (mentions_sample or [])[:5]
    )

    system = (
        "You are a PR analyst. Given coverage metrics and sample headlines for a client and their competitors, "
        "write a short actionable summary for the PR team. Include: (1) Client coverage snapshot, "
        "(2) Competitor coverage and gaps, (3) 2–4 concrete actions to target (outreach, topics, or sources). "
        "Keep it under 250 words. Use clear headings and bullet points. Return plain text or markdown, no JSON."
    )
    user = (
        f"Client: {client_name}\n\n"
        f"Coverage (mention counts):\n{coverage_txt or 'None'}\n\n"
        f"Article counts: {counts_txt}\n\n"
        f"Sample competitor-only headlines:\n{comp_sample_txt or 'None'}\n\n"
        f"Sample mentions (client + competitors):\n{mentions_txt or 'None'}"
    )[:5000]

    from app.config import get_config
    config = get_config()
    cfg = config.get("coverage_pr_summary") or config.get("narrative_intelligence_daily") or {}
    model = (cfg.get("llm") or {}).get("model") if isinstance(cfg.get("llm"), dict) else None
    if not model:
        settings = config.get("settings")
        model = getattr(settings, "openrouter_model", None) or "openai/gpt-4o-mini"

    gw = LLMGateway()
    gw.set_model(model)
    out = ""
    try:
        async for ch in gw.chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            stream=False,
            use_web_search=False,
        ):
            out += ch or ""
    except Exception as e:
        logger.warning("coverage_pr_summary_llm_failed", client=client_name, error=str(e))
        return (
            f"## Coverage snapshot\n"
            f"Client {client_name}: {next((c.get('mentions', 0) for c in coverage if (c.get('entity') or '').lower() == client_name.lower()), 0)} mentions. "
            f"Competitor-only articles: {counts.get('competitor_only_articles', 0)}. "
            f"Summary generation failed ({e}). Run again later."
        )

    return (out or "").strip()[:4000]


async def run_coverage_pr_summary_batch() -> dict[str, Any]:
    """For each client: compute coverage + counts + samples, one LLM call, store by date."""
    from app.services.mongodb import get_db
    from app.services.mongodb import get_mongo_client

    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION]

    clients = await load_clients()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    computed_at = datetime.now(timezone.utc)
    results: list[str] = []

    for c in clients:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        try:
            coverage = await compute_coverage(name)
            counts = await get_article_counts(name)
            comp_sample = (await get_competitor_only_articles(name, limit=5)).get("articles") or []
            mentions_data = await get_mentions_client_and_competitors(name, limit=5)
            mentions_sample = mentions_data.get("mentions") or []

            summary = await _llm_coverage_summary(
                client_name=name,
                coverage=coverage,
                counts=counts,
                competitor_sample=comp_sample,
                mentions_sample=mentions_sample,
            )

            await coll.update_one(
                {"client": name, "date": today},
                {
                    "$set": {
                        "client": name,
                        "date": today,
                        "summary": summary,
                        "computed_at": computed_at,
                    }
                },
                upsert=True,
            )
            results.append(name)
            logger.info("coverage_pr_summary_stored", client=name, date=today)
        except Exception as e:
            logger.warning("coverage_pr_summary_client_failed", client=name, error=str(e))

    return {"clients_updated": results}


async def get_latest_summary(client: str) -> dict[str, Any]:
    """Return the most recent coverage PR summary for the client, or empty."""
    from app.services.mongodb import get_db
    from app.services.mongodb import get_mongo_client

    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION]

    doc = await coll.find_one(
        {"client": client.strip()},
        sort=[("computed_at", -1)],
        projection={"summary": 1, "date": 1, "computed_at": 1},
    )
    if not doc:
        return {"summary": None, "date": None, "computed_at": None}

    computed = doc.get("computed_at")
    return {
        "summary": doc.get("summary") or "",
        "date": doc.get("date"),
        "computed_at": computed.isoformat() if hasattr(computed, "isoformat") else str(computed),
    }
