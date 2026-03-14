"""
Narrative Positioning — PR-focused intelligence per client.

- Input: narrative_intelligence_daily, narrative_shift, Reddit/YouTube summaries, entity_mentions,
  article_documents, social_posts for the client entity.
- Output: narratives, positioning, threats, opportunities, evidence_refs.
- Stores in narrative_positioning (one doc per client per date).
- LLM: 1 call per client per day.
"""

import json
from datetime import datetime, timezone
from typing import Any

from app.config import get_config
from app.core.client_config_loader import get_entity_names, load_clients
from app.core.logging import get_logger

logger = get_logger(__name__)

COLLECTION = "narrative_positioning"
DAYS_WINDOW = 7


def _cfg() -> dict[str, Any]:
    cfg = get_config().get("narrative_positioning")
    if isinstance(cfg, dict):
        return cfg
    return get_config().get("narrative_intelligence_daily") or {}


async def _gather_inputs_for_client(client_name: str, entity: str) -> dict[str, Any]:
    """Gather narrative + evidence inputs for one client from existing collections."""
    from app.services.mongodb import get_mongo_client, get_db
    from app.services.narrative_intelligence_daily_service import load_last_n_days
    from app.services.narrative_shift_service import load_latest_run
    from app.services.reddit_trending_service import load_latest_summary_from_mongo
    from app.services.youtube_trending_service import load_daily_summaries

    await get_mongo_client()
    db = get_db()

    out: dict[str, Any] = {
        "narrative_daily": [],
        "narrative_shift": {},
        "reddit_themes": [],
        "reddit_sahi": [],
        "youtube_summaries": [],
        "entity_mentions": [],
        "article_snippets": [],
        "social_posts": [],
    }

    # Daily intelligence (last N days)
    daily = await load_last_n_days(days=DAYS_WINDOW)
    out["narrative_daily"] = daily or []

    # Latest narrative shift run
    ns = await load_latest_run()
    if ns:
        out["narrative_shift"] = ns

    # Reddit themes + Sahi suggestions
    themes, sahi = await load_latest_summary_from_mongo()
    out["reddit_themes"] = themes or []
    out["reddit_sahi"] = sahi or []

    # YouTube daily summaries
    yt = await load_daily_summaries(limit=7)
    out["youtube_summaries"] = yt or []

    # Client-specific: entity_mentions, article_documents (by entities), social_posts
    em_coll = db["entity_mentions"]
    async for doc in em_coll.find({"entity": entity}).sort("published_at", -1).limit(30):
        out["entity_mentions"].append({
            "title": (doc.get("title") or "")[:200],
            "source_domain": (doc.get("source_domain") or doc.get("source") or "")[:100],
            "summary": (doc.get("summary") or doc.get("snippet") or "")[:300],
            "url": (doc.get("url") or "")[:400],
            "type": (doc.get("type") or "article"),
        })

    ad_coll = db["article_documents"]
    async for doc in ad_coll.find({"entities": entity}).sort("published_at", -1).limit(25):
        summary = (doc.get("summary") or doc.get("article_text") or "")[:400]
        out["article_snippets"].append({
            "title": (doc.get("title") or "")[:200],
            "source": (doc.get("source_domain") or doc.get("source") or "")[:100],
            "summary": summary,
            "url": (doc.get("url") or doc.get("url_resolved") or "")[:400],
        })

    sp_coll = db["social_posts"]
    async for doc in sp_coll.find({"entity": entity}).sort("timestamp", -1).limit(20):
        text = (doc.get("text") or "")[:300]
        out["social_posts"].append({
            "platform": (doc.get("platform") or "social"),
            "text": text,
            "url": (doc.get("url") or "")[:400],
        })

    return out


async def _llm_positioning(client_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """One LLM call: narratives, positioning, threats, opportunities, evidence_refs."""
    from app.services.llm_gateway import LLMGateway

    daily_txt = ""
    for r in (inputs.get("narrative_daily") or [])[:3]:
        daily_txt += f"- {r.get('date','')}: {r.get('executive_summary','')[:120]}...\n"

    ns = inputs.get("narrative_shift") or {}
    ns_txt = "\n".join(
        f"- {n.get('topic','')}: pain={n.get('pain_points','')[:80]}; msg={n.get('messaging','')[:80]}"
        for n in (ns.get("narratives") or [])[:6]
    ) or "None"

    themes = inputs.get("reddit_themes") or []
    themes_txt = "\n".join(f"- {t.get('label','')}: {t.get('description','')[:80]}" for t in themes[:5]) or "None"
    sahi = inputs.get("reddit_sahi") or []
    sahi_txt = "\n".join(f"- {s.get('title','')}: {s.get('rationale','')[:80]}" for s in sahi[:4]) or "None"
    yt = inputs.get("youtube_summaries") or []
    yt_txt = "\n".join(f"- {y.get('date','')}: {y.get('narrative','')[:100]}" for y in yt[:5]) or "None"

    mentions = inputs.get("entity_mentions") or []
    ment_txt = "\n".join(
        f"- [{m.get('source_domain','')}] {m.get('title','')[:80]}: {m.get('summary','')[:100]}"
        for m in mentions[:12]
    ) or "None"

    arts = inputs.get("article_snippets") or []
    art_txt = "\n".join(
        f"- [{a.get('source','')}] {a.get('title','')[:80]}: {a.get('summary','')[:100]}"
        for a in arts[:10]
    ) or "None"

    social = inputs.get("social_posts") or []
    social_txt = "\n".join(
        f"- [{s.get('platform','')}] {s.get('text','')[:120]}"
        for s in social[:8]
    ) or "None"

    system = (
        "You are a PR analyst for a financial/trading app. Given narrative intelligence, Reddit themes, YouTube, "
        "mentions, and social posts, produce a PR-focused positioning brief. Return ONLY valid JSON with: "
        '"narratives" (array of {theme, sentiment, platforms, evidence_count, sample_quotes: []}, 3-5 items), '
        '"positioning" ({headline, pitch_angle, suggested_outlets: []}), '
        '"threats" (array of {narrative, severity, response_angle}, 1-4 items), '
        '"opportunities" (array of {angle, outlet_match}, 2-4 items), '
        '"evidence_refs" (array of {platform, url, title, snippet}, max 8).'
    )
    user = (
        f"Client: {client_name}\n\n"
        "Daily intelligence:\n" + (daily_txt or "None") + "\n\n"
        "Narrative shift topics:\n" + ns_txt + "\n\n"
        "Reddit themes:\n" + themes_txt + "\n\n"
        "Sahi suggestions:\n" + sahi_txt + "\n\n"
        "YouTube summaries:\n" + yt_txt + "\n\n"
        "Entity mentions:\n" + ment_txt + "\n\n"
        "Article snippets:\n" + art_txt + "\n\n"
        "Social posts:\n" + social_txt
    )[:8000]

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
        logger.warning("narrative_positioning_llm_failed", client=client_name, error=str(e))
        return _empty_output()

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
            "narratives": _normalize_narratives(parsed.get("narratives")),
            "positioning": _normalize_positioning(parsed.get("positioning")),
            "threats": _normalize_threats(parsed.get("threats")),
            "opportunities": _normalize_opportunities(parsed.get("opportunities")),
            "evidence_refs": _normalize_evidence_refs(parsed.get("evidence_refs")),
        }
    except json.JSONDecodeError:
        return _empty_output()


def _normalize_narratives(lst: Any) -> list[dict]:
    if not isinstance(lst, list):
        return []
    out = []
    for x in lst[:8]:
        if not isinstance(x, dict):
            continue
        out.append({
            "theme": str(x.get("theme", ""))[:200],
            "sentiment": str(x.get("sentiment", ""))[:30],
            "platforms": [str(p) for p in (x.get("platforms") or [])[:5]],
            "evidence_count": int(x.get("evidence_count", 0)) if isinstance(x.get("evidence_count"), (int, float)) else 0,
            "sample_quotes": [str(q) for q in (x.get("sample_quotes") or [])[:3]],
        })
    return out


def _normalize_positioning(obj: Any) -> dict:
    if not isinstance(obj, dict):
        return {"headline": "", "pitch_angle": "", "suggested_outlets": []}
    return {
        "headline": str(obj.get("headline", ""))[:300],
        "pitch_angle": str(obj.get("pitch_angle", ""))[:500],
        "suggested_outlets": [str(o) for o in (obj.get("suggested_outlets") or [])[:8]],
    }


def _normalize_threats(lst: Any) -> list[dict]:
    if not isinstance(lst, list):
        return []
    out = []
    for x in lst[:6]:
        if not isinstance(x, dict):
            continue
        out.append({
            "narrative": str(x.get("narrative", ""))[:300],
            "severity": str(x.get("severity", ""))[:30],
            "response_angle": str(x.get("response_angle", ""))[:300],
        })
    return out


def _normalize_opportunities(lst: Any) -> list[dict]:
    if not isinstance(lst, list):
        return []
    out = []
    for x in lst[:6]:
        if not isinstance(x, dict):
            continue
        out.append({
            "angle": str(x.get("angle", ""))[:300],
            "outlet_match": str(x.get("outlet_match", ""))[:200],
        })
    return out


def _normalize_evidence_refs(lst: Any) -> list[dict]:
    if not isinstance(lst, list):
        return []
    out = []
    for x in lst[:10]:
        if not isinstance(x, dict):
            continue
        out.append({
            "platform": str(x.get("platform", ""))[:50],
            "url": str(x.get("url", ""))[:500],
            "title": str(x.get("title", ""))[:300],
            "snippet": str(x.get("snippet", ""))[:300],
        })
    return out


def _empty_output() -> dict[str, Any]:
    return {
        "narratives": [],
        "positioning": {"headline": "", "pitch_angle": "", "suggested_outlets": []},
        "threats": [],
        "opportunities": [],
        "evidence_refs": [],
    }


async def run_positioning_for_all_clients() -> dict[str, Any]:
    """
    Run narrative positioning batch for all configured clients.
    One LLM call per client per date.
    """
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return {"ok": False, "reason": "narrative_positioning disabled"}

    clients_list = await load_clients()
    if not clients_list:
        return {"ok": True, "processed": 0, "reason": "no clients configured"}

    from app.services.mongodb import get_mongo_client, get_db

    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION]
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    processed = 0

    for client in clients_list:
        client_name = (client.get("name") or "").strip()
        if not client_name:
            continue
        entities = get_entity_names(client)
        entity = entities[0] if entities else client_name

        try:
            inputs = await _gather_inputs_for_client(client_name, entity)
            result = await _llm_positioning(client_name, inputs)

            doc = {
                "client": client_name,
                "date": date_str,
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "narratives": result["narratives"],
                "positioning": result["positioning"],
                "threats": result["threats"],
                "opportunities": result["opportunities"],
                "evidence_refs": result["evidence_refs"],
            }
            await coll.replace_one(
                {"client": client_name, "date": date_str},
                doc,
                upsert=True,
            )
            processed += 1
        except Exception as e:
            logger.warning("narrative_positioning_client_failed", client=client_name, error=str(e))

    return {"ok": True, "processed": processed, "date": date_str}


async def load_positioning(client: str, days: int = 7) -> list[dict[str, Any]]:
    """Load narrative positioning docs for a client, newest first."""
    from app.services.mongodb import get_mongo_client, get_db

    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION]
    cursor = coll.find({"client": client}).sort("date", -1).limit(min(days, 30))
    out = []
    async for doc in cursor:
        d = dict(doc)
        d.pop("_id", None)
        for k in ("computed_at",):
            v = d.get(k)
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        out.append(d)
    return out
