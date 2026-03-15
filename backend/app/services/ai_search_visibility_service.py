"""
AI Search Visibility Monitoring (Phase 1).

- Runs curated prompts per client via Perplexity; caches by (client, query, engine, week).
- Reuses entity_detection.detect_entities() on each answer to get entities_found.
- Writes visibility_runs, visibility_weekly_snapshots, visibility_recommendations.
- Rule-based recommendations when competitors appear but company does not.
- Weekly run only; caps to stay under LLM limits.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.config import get_config
from app.core.client_config_loader import get_entity_names, load_clients
from app.core.logging import get_logger

logger = get_logger(__name__)

ENGINE_PERPLEXITY = "perplexity"


def _get_config_dir() -> Path:
    from app.config import _get_config_dir as _dir
    return _dir()


def _cfg() -> dict[str, Any]:
    return get_config().get("ai_search_visibility") or {}


def _load_prompt_groups() -> list[dict[str, Any]]:
    """Load prompt groups from config/ai_visibility_prompts.yaml (or path in ai_search_visibility)."""
    cfg = _cfg()
    config_dir = _get_config_dir()
    filename = (cfg.get("prompt_groups_file") or "ai_visibility_prompts.yaml").strip()
    path = config_dir / filename
    if not path.exists():
        logger.warning("ai_search_visibility_prompts_file_not_found", path=str(path))
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    groups = data.get("prompt_groups") or []
    return groups if isinstance(groups, list) else []


def _build_prompt_list() -> list[tuple[str, str, str]]:
    """Return list of (group_id, group_name, query) capped by config."""
    groups = _load_prompt_groups()
    cfg = _cfg()
    max_per_run = max(0, int(cfg.get("max_prompts_per_run") or 30))
    max_per_group = max(0, int(cfg.get("max_per_group_per_run") or 6))
    out: list[tuple[str, str, str]] = []
    for g in groups:
        gid = (g.get("id") or "").strip()
        gname = (g.get("name") or gid).strip()
        prompts = g.get("prompts") or []
        if not isinstance(prompts, list):
            continue
        taken = 0
        for p in prompts:
            if len(out) >= max_per_run:
                return out
            if taken >= max_per_group:
                break
            q = (p or "").strip()
            if not q:
                continue
            out.append((gid, gname, q))
            taken += 1
    return out


def _week_string(dt: datetime | None = None) -> str:
    """ISO week e.g. 2025-W10."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


async def _call_perplexity(query: str) -> str:
    """Call Perplexity via OpenRouter; return answer text (no entity detection)."""
    from app.services.llm_gateway import LLMGateway

    gateway = LLMGateway()
    raw = (get_config().get("openrouter") or {}).get("web_search_model") or ""
    model = raw if raw and "perplexity" in raw.lower() else "perplexity/sonar"
    gateway.set_model(model)
    messages = [{"role": "user", "content": f"Answer in 2–4 short paragraphs: {query}"}]
    out = ""
    try:
        async for chunk in gateway.chat_completion(
            messages=messages,
            stream=True,
            use_web_search=True,
        ):
            if chunk:
                out += chunk
    except Exception as e:
        logger.warning("ai_visibility_perplexity_failed", query=query[:80], error=str(e))
        return ""
    out = out.strip()
    if out.startswith('{"error"'):
        return ""
    return out[:8000] if out else ""


def _entities_in_answer(answer_text: str) -> list[str]:
    """Reuse existing entity detection; returns list of entity names (company + competitors) found in text."""
    from app.services.entity_detection_service import detect_entities
    return detect_entities(answer_text or "")


def _collections(cfg: dict[str, Any]) -> tuple[str, str, str, str]:
    mongo = cfg.get("mongodb") or {}
    return (
        mongo.get("answers_collection") or "visibility_answers",
        mongo.get("runs_collection") or "visibility_runs",
        mongo.get("snapshots_collection") or "visibility_weekly_snapshots",
        mongo.get("recommendations_collection") or "visibility_recommendations",
    )


async def run_visibility_pipeline() -> dict[str, Any]:
    """
    Run Phase 1 visibility pipeline:
    - Fetch answers once per (query, engine, week) into visibility_answers (cache).
    - For each client, run entity detection on each answer, store visibility_runs; compute snapshots and recommendations.
    """
    cfg = _cfg()
    if not cfg.get("enabled", False):
        return {"ok": False, "reason": "ai_search_visibility disabled"}

    if not get_config().get("settings").openrouter_api_key:
        logger.warning("ai_search_visibility_skipped", reason="OPENROUTER_API_KEY not set")
        return {"ok": False, "reason": "OPENROUTER_API_KEY not set"}

    enabled = cfg.get("enabled_engines") or []
    if ENGINE_PERPLEXITY not in (e.strip().lower() for e in enabled if isinstance(e, str)):
        return {"ok": False, "reason": "no enabled_engines (perplexity)"}

    prompt_list = _build_prompt_list()
    if not prompt_list:
        return {"ok": True, "processed": 0, "reason": "no prompt groups or prompts"}

    week = _week_string()
    delay_sec = max(0, min(30, float(cfg.get("delay_seconds_between_calls") or 4)))
    answers_coll_name, runs_coll_name, snap_coll_name, rec_coll_name = _collections(cfg)

    from app.services.mongodb import get_mongo_client, get_db

    await get_mongo_client()
    db = get_db()
    answers_coll = db[answers_coll_name]
    runs_coll = db[runs_coll_name]
    snap_coll = db[snap_coll_name]
    rec_coll = db[rec_coll_name]

    # Step 1: Ensure each (query, engine, week) has an answer (one Perplexity call per query per week)
    total_new_answers = 0
    for i, (group_id, group_name, query) in enumerate(prompt_list):
        if i > 0:
            await asyncio.sleep(delay_sec)
        existing = await answers_coll.find_one({
            "query": query[:500],
            "engine": ENGINE_PERPLEXITY,
            "week": week,
        })
        if existing:
            continue
        answer_text = await _call_perplexity(query)
        doc = {
            "query": query[:500],
            "group_id": group_id,
            "group_name": group_name,
            "engine": ENGINE_PERPLEXITY,
            "week": week,
            "answer_text": answer_text,
            "computed_at": datetime.now(timezone.utc),
        }
        await answers_coll.replace_one(
            {"query": query[:500], "engine": ENGINE_PERPLEXITY, "week": week},
            doc,
            upsert=True,
        )
        total_new_answers += 1

    # Step 2: For each client, run entity detection on each answer and store visibility_runs
    clients_list = await load_clients()
    if not clients_list:
        logger.info("ai_search_visibility_no_clients")
        return {"ok": True, "processed": total_new_answers, "week": week, "clients": 0}

    # Delete old recommendations for this week so we recompute
    await rec_coll.delete_many({"week": week})

    total_new_runs = 0
    async for answer_doc in answers_coll.find({"week": week, "engine": ENGINE_PERPLEXITY}):
        query = answer_doc.get("query") or ""
        group_id = answer_doc.get("group_id") or "unknown"
        group_name = answer_doc.get("group_name") or group_id
        answer_text = answer_doc.get("answer_text") or ""

        for client_obj in clients_list:
            client_name = (client_obj.get("name") or "").strip()
            if not client_name:
                continue
            existing_run = await runs_coll.find_one({
                "client": client_name,
                "query": query[:500],
                "engine": ENGINE_PERPLEXITY,
                "week": week,
            })
            if existing_run:
                continue

            entities_found = _entities_in_answer(answer_text)
            entity_names = get_entity_names(client_obj)
            company_name = entity_names[0] if entity_names else client_name
            competitor_names = entity_names[1:] if len(entity_names) > 1 else []

            run_doc = {
                "client": client_name,
                "query": query[:500],
                "group_id": group_id,
                "group_name": group_name,
                "engine": ENGINE_PERPLEXITY,
                "week": week,
                "entities_found": entities_found,
                "computed_at": datetime.now(timezone.utc),
            }
            await runs_coll.replace_one(
                {"client": client_name, "query": query[:500], "engine": ENGINE_PERPLEXITY, "week": week},
                run_doc,
                upsert=True,
            )
            total_new_runs += 1

            competitors_in = [c for c in competitor_names if c in entities_found]
            company_in = company_name in entities_found
            if not company_in and competitors_in:
                rec_text = (
                    f"Query: {query[:200]}. {company_name} not visible. "
                    f"Competitors in answer: {', '.join(competitors_in)}. "
                    f"Recommendation: Publish content addressing this topic to improve AI visibility."
                )
                await rec_coll.insert_one({
                    "client": client_name,
                    "week": week,
                    "query": query[:500],
                    "engine": ENGINE_PERPLEXITY,
                    "competitors_found": competitors_in,
                    "recommendation_text": rec_text,
                })

        # Compute weekly snapshot per client (after processing all runs for this week)
        # We do this once per client after the inner loop - but the inner loop is per answer_doc. So we need to compute snapshots after all runs are done.
    for client_obj in clients_list:
        client_name = (client_obj.get("name") or "").strip()
        if not client_name:
            continue
        entity_names = get_entity_names(client_obj)
        company_name = entity_names[0] if entity_names else client_name

        cursor = runs_coll.find({"client": client_name, "week": week})
        runs_this_week: list[dict[str, Any]] = []
        async for d in cursor:
            runs_this_week.append(d)

        if not runs_this_week:
            continue

        total = len(runs_this_week)
        company_visible_count = sum(1 for r in runs_this_week if company_name in (r.get("entities_found") or []))
        overall_index = round((company_visible_count / total * 100), 1) if total else 0

        by_group: dict[str, dict[str, Any]] = {}
        for r in runs_this_week:
            gid = r.get("group_id") or "unknown"
            gname = r.get("group_name") or gid
            if gid not in by_group:
                by_group[gid] = {"group_id": gid, "name": gname, "prompts_run": 0, "company_visible_count": 0}
            by_group[gid]["prompts_run"] += 1
            if company_name in (r.get("entities_found") or []):
                by_group[gid]["company_visible_count"] += 1

        group_metrics = []
        for g in by_group.values():
            run_count = g["prompts_run"]
            vis = g["company_visible_count"]
            score_pct = round((vis / run_count * 100), 1) if run_count else 0
            group_metrics.append({
                "group_id": g["group_id"],
                "name": g["name"],
                "prompts_run": run_count,
                "company_visible_count": vis,
                "score_pct": score_pct,
            })

        engine_metrics = [{
            "engine": ENGINE_PERPLEXITY,
            "prompts_run": total,
            "company_visible_count": company_visible_count,
            "score_pct": overall_index,
        }]

        snapshot = {
            "client": client_name,
            "week": week,
            "overall_index": overall_index,
            "group_metrics": group_metrics,
            "engine_metrics": engine_metrics,
            "computed_at": datetime.now(timezone.utc),
        }
        await snap_coll.replace_one(
            {"client": client_name, "week": week},
            snapshot,
            upsert=True,
        )

    logger.info(
        "ai_search_visibility_run_done",
        total_new_answers=total_new_answers,
        total_new_runs=total_new_runs,
        week=week,
        clients=len(clients_list),
    )
    return {"ok": True, "processed": total_new_answers + total_new_runs, "week": week, "clients": len(clients_list)}


async def load_dashboard(client: str, weeks: int = 8, sample_limit: int = 6) -> dict[str, Any]:
    """Load dashboard data: current snapshot + trend (last N weeks) + sample prompts & results for one client."""
    cfg = _cfg()
    answers_coll_name, runs_coll_name, snap_coll_name, rec_coll_name = _collections(cfg)
    from app.services.mongodb import get_mongo_client, get_db

    await get_mongo_client()
    db = get_db()
    snap_coll = db[snap_coll_name]
    rec_coll = db[rec_coll_name]
    runs_coll = db[runs_coll_name]
    answers_coll = db[answers_coll_name]

    # Latest snapshot (current week or most recent)
    latest = await snap_coll.find_one({"client": client}, sort=[("week", -1)])
    week = latest.get("week") if latest else _week_string()

    # Trend: last N weeks
    cursor = snap_coll.find({"client": client}).sort("week", -1).limit(max(1, min(weeks, 52)))
    trend: list[dict[str, Any]] = []
    async for doc in cursor:
        d = dict(doc)
        d.pop("_id", None)
        for k in ("computed_at",):
            v = d.get(k)
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        trend.append(d)

    # Recommendations for latest week
    rec_cursor = rec_coll.find({"client": client, "week": week}).limit(50)
    recommendations: list[dict[str, Any]] = []
    async for doc in rec_cursor:
        d = dict(doc)
        d.pop("_id", None)
        recommendations.append(d)

    # Sample prompts & results: join runs with answers for this client + week
    samples: list[dict[str, Any]] = []
    runs_cursor = runs_coll.find({"client": client, "week": week}).limit(sample_limit)
    async for run_doc in runs_cursor:
        query = (run_doc.get("query") or "")[:500]
        group_name = run_doc.get("group_name") or run_doc.get("group_id") or ""
        entities_found = run_doc.get("entities_found") or []
        answer_doc = await answers_coll.find_one({
            "query": query,
            "engine": ENGINE_PERPLEXITY,
            "week": week,
        })
        answer_text = (answer_doc.get("answer_text") or "") if answer_doc else ""
        company_visible = client in entities_found
        samples.append({
            "query": query,
            "group_name": group_name,
            "answer_text": answer_text,
            "entities_found": entities_found,
            "company_visible": company_visible,
        })

    latest_serialized = None
    if latest:
        latest_serialized = dict(latest)
        latest_serialized.pop("_id", None)
        v = latest_serialized.get("computed_at")
        if hasattr(v, "isoformat"):
            latest_serialized["computed_at"] = v.isoformat()

    return {
        "client": client,
        "week": week,
        "latest": latest_serialized,
        "trend": trend,
        "recommendations": recommendations,
        "samples": samples,
    }
