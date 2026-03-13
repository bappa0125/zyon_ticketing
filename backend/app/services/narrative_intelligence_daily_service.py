"""
Narrative Intelligence Daily — 1 LLM call per day, synthesis over narrative shift + Reddit + YouTube.

- Input: latest narrative_shift run, Reddit themes, YouTube summaries.
- Output: executive_summary, top_narratives, pr_actions, influencers, sentiment.
- Stores in narrative_intelligence_daily (one doc per date).
- Quota: 1 call/day.
"""

import json
from datetime import datetime, timezone
from typing import Any

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

COLLECTION = "narrative_intelligence_daily"


def _cfg() -> dict[str, Any]:
    cfg = get_config().get("narrative_intelligence_daily")
    if isinstance(cfg, dict):
        return cfg
    return get_config().get("narrative_shift") or {}


async def _llm_daily_synthesis(
    narratives: list[dict],
    reddit_themes: list[dict],
    reddit_sahi: list[dict],
    youtube_summaries: list[dict],
) -> dict[str, Any]:
    """One LLM call: executive summary, top narratives, PR actions, influencers, sentiment."""
    from app.services.llm_gateway import LLMGateway

    narratives_txt = "\n".join(
        f"- {n.get('topic', '')} | platform: {n.get('dominant_platform', '')} | influencers: {', '.join(n.get('influencers', [])[:3])} | pain: {n.get('pain_points', '')[:100]} | msg: {n.get('messaging', '')[:100]}"
        for n in (narratives or [])[:8]
    )
    themes_txt = "\n".join(
        f"- {t.get('label', '')}: {t.get('description', '')[:80]}"
        for t in (reddit_themes or [])[:6]
    )
    sahi_txt = "\n".join(
        f"- {s.get('title', '')}: {s.get('rationale', '')[:80]}"
        for s in (reddit_sahi or [])[:4]
    )
    yt_txt = "\n".join(
        f"- {y.get('date', '')}: {y.get('narrative', '')[:100]}"
        for y in (youtube_summaries or [])[:5]
    )

    system = (
        "You are a PR analyst. Given narrative clusters, Reddit themes, Sahi suggestions, and YouTube summaries "
        "from trading/finance content, produce a daily intelligence report. Return ONLY valid JSON with exactly: "
        '"executive_summary" (1-2 sentences), '
        '"top_narratives" (array of {rank, topic, rationale}, 3 items), '
        '"pr_actions" (array of {action, priority: "high"|"medium"|"low"}, 3 items for Sahi app), '
        '"influencers" (array of 3-5 names/channels), '
        '"sentiment" (one of: bullish, bearish, mixed).'
    )
    user = (
        "Narratives:\n" + (narratives_txt or "None") + "\n\n"
        "Reddit themes:\n" + (themes_txt or "None") + "\n\n"
        "Sahi topics:\n" + (sahi_txt or "None") + "\n\n"
        "YouTube summaries:\n" + (yt_txt or "None")
    )[:6000]

    cfg = _cfg()
    model = (cfg.get("llm") or {}).get("model") or "openrouter/free"
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
        logger.warning("narrative_intelligence_daily_llm_failed", error=str(e))
        return _empty_report()

    s = (out or "").strip()
    if s.startswith("```"):
        lines = s.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines)
    try:
        parsed = json.loads(s)
        return {
            "executive_summary": str(parsed.get("executive_summary", ""))[:500],
            "top_narratives": [
                {
                    "rank": i + 1,
                    "topic": str(x.get("topic", ""))[:150],
                    "rationale": str(x.get("rationale", ""))[:200],
                }
                for i, x in enumerate((parsed.get("top_narratives") or [])[:3])
                if isinstance(x, dict)
            ],
            "pr_actions": [
                {
                    "action": str(x.get("action", ""))[:200],
                    "priority": str(x.get("priority", "medium"))[:10],
                }
                for x in (parsed.get("pr_actions") or [])[:3]
                if isinstance(x, dict)
            ],
            "influencers": [str(x) for x in (parsed.get("influencers") or [])[:5]],
            "sentiment": str(parsed.get("sentiment", "mixed"))[:20],
        }
    except json.JSONDecodeError:
        return _empty_report()


def _empty_report() -> dict[str, Any]:
    return {
        "executive_summary": "",
        "top_narratives": [],
        "pr_actions": [],
        "influencers": [],
        "sentiment": "mixed",
    }


async def run_daily_synthesis() -> dict[str, Any]:
    """
    Load narrative_shift + Reddit + YouTube data, run 1 LLM synthesis, store by date.
    """
    from app.services.mongodb import get_mongo_client, get_db
    from app.services.narrative_shift_service import load_latest_run
    from app.services.reddit_trending_service import load_latest_summary_from_mongo
    from app.services.youtube_trending_service import load_daily_summaries

    await get_mongo_client()
    db = get_db()

    narratives: list[dict] = []
    reddit_themes: list[dict] = []
    reddit_sahi: list[dict] = []
    youtube_summaries: list[dict] = []

    ns_run = await load_latest_run()
    if ns_run and ns_run.get("narratives"):
        narratives = ns_run.get("narratives") or []

    themes, sahi = await load_latest_summary_from_mongo()
    reddit_themes = themes or []
    reddit_sahi = sahi or []

    yt = await load_daily_summaries(limit=5)
    youtube_summaries = yt or []

    report = await _llm_daily_synthesis(
        narratives=narratives,
        reddit_themes=reddit_themes,
        reddit_sahi=reddit_sahi,
        youtube_summaries=youtube_summaries,
    )

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = {
        "date": date_str,
        "executive_summary": report["executive_summary"],
        "top_narratives": report["top_narratives"],
        "pr_actions": report["pr_actions"],
        "influencers": report["influencers"],
        "sentiment": report["sentiment"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "narratives_count": len(narratives),
            "reddit_themes": len(reddit_themes),
            "youtube_days": len(youtube_summaries),
        },
    }
    coll = db[COLLECTION]
    await coll.replace_one({"date": date_str}, doc, upsert=True)

    return {"ok": True, "date": date_str, "report": report}


async def load_last_n_days(days: int = 7) -> list[dict[str, Any]]:
    """Load narrative intelligence daily docs, newest first."""
    from app.services.mongodb import get_mongo_client, get_db

    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION]
    cursor = coll.find({}).sort("date", -1).limit(days)
    out = []
    async for doc in cursor:
        d = dict(doc)
        d.pop("_id", None)
        for k in ("generated_at",):
            v = d.get(k)
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        out.append(d)
    return out
