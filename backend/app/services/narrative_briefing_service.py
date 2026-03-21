"""
Single-pack narrative briefing for CXO UI: landscape, forums, YouTube, Reddit, positioning + memo.

- **Batch / ingestion:** `run_narrative_briefing_for_all_clients` builds packs, calls LLM when configured,
  upserts into `narrative_briefing_snapshots` (one document per client × range_days × UTC day).
- **API / UI:** read latest snapshot only — no user-triggered LLM.
"""

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.config import get_config
from app.core.client_config_loader import get_entity_names, load_clients
from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client

logger = get_logger(__name__)

ENTITY_MENTIONS = "entity_mentions"
SNAPSHOT_COLLECTION = "narrative_briefing_snapshots"
PIPELINE_ID = "narrative_briefing_daily"

_indexes_ensured = False


async def _ensure_briefing_indexes() -> None:
    global _indexes_ensured
    if _indexes_ensured:
        return
    from app.services.mongodb import get_db

    coll = get_db()[SNAPSHOT_COLLECTION]
    await coll.create_index([("client", 1), ("range_days", 1), ("snapshot_date", 1), ("pipeline", 1)], unique=True)
    await coll.create_index([("client", 1), ("range_days", 1), ("computed_at", -1)])
    _indexes_ensured = True


def _nb_cfg() -> dict[str, Any]:
    cfg = get_config().get("narrative_briefing")
    return cfg if isinstance(cfg, dict) else {}


def _str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v)[:500]


async def _surface_totals(entities: list[str], cutoff: datetime) -> dict[str, int]:
    from app.services.mongodb import get_db

    db = get_db()
    coll = db[ENTITY_MENTIONS]
    match: dict[str, Any] = {
        "entity": {"$in": entities},
        "$or": [
            {"published_at": {"$gte": cutoff}},
            {"timestamp": {"$gte": cutoff}},
        ],
    }
    pipeline = [
        {"$match": match},
        {"$group": {"_id": {"$ifNull": ["$type", "unknown"]}, "n": {"$sum": 1}}},
    ]
    out: dict[str, int] = {"article": 0, "forum": 0, "other": 0}
    async for row in coll.aggregate(pipeline):
        typ = _str(row.get("_id")) or "other"
        n = int(row.get("n") or 0)
        if typ in out:
            out[typ] = out.get(typ, 0) + n
        else:
            out["other"] = out.get("other", 0) + n
    return out


def _deterministic_memo(
    client_name: str,
    range_days: int,
    surface: dict[str, int],
    gaps: list[dict],
    forum_rows: list[dict],
    yt_line: str,
    reddit_themes: list[str],
    positioning_line: str,
) -> dict[str, Any]:
    bullets: list[str] = []
    total = sum(surface.values())
    bullets.append(
        f"**Monitoring window:** {range_days} days — **{total:,}** entity-tagged mentions across your universe "
        f"({_str(client_name)} + competitors): **{surface.get('article', 0)}** publication/article signals, "
        f"**{surface.get('forum', 0)}** forum echoes."
    )
    if gaps:
        bullets.append(f"**Narrative gap (priority):** {gaps[0].get('headline', '')}")
    elif forum_rows:
        bullets.append(
            f"**Forum traction:** strongest themes include *{_humanize_tag(str(forum_rows[0].get('narrative_tag', '')))}* "
            f"on {forum_rows[0].get('forum_site', 'forums')} — track for reputational risk and copycat claims."
        )
    else:
        bullets.append("**Forum traction:** limited tagged forum volume in-window — widen ingestion or backfill before exec readout.")

    if yt_line:
        bullets.append(f"**YouTube narrative (video ecosystem):** {yt_line}")
    else:
        bullets.append("**YouTube:** no daily narrative snapshot in DB — refresh YouTube pipeline for exhibit sync.")

    if reddit_themes:
        bullets.append(
            f"**Reddit velocity:** active themes include {', '.join(reddit_themes[:4])} — use as early warning, not legal fact."
        )
    else:
        bullets.append("**Reddit:** no cached themes — run Reddit trending pipeline or treat as TBD.")

    if positioning_line:
        bullets.append(f"**PR / positioning layer:** {positioning_line}")
    else:
        bullets.append(
            "**PR / positioning:** no stored narrative positioning report for this client in-window — run positioning batch for board-ready language."
        )

    bullets.append(
        "**Exhibits below** ground every line in source charts and links — use them when challenged in Q&A."
    )
    return {"bullets": bullets, "raw_markdown": "\n\n".join(bullets)}


def _humanize_tag(tag: str) -> str:
    return tag.replace("_", " ") if tag else tag


async def _llm_memo(facts: dict[str, Any]) -> Optional[str]:
    from app.config import get_config
    from app.services.llm_gateway import LLMGateway

    cfg = get_config()
    st = cfg.get("settings")
    api_key = (getattr(st, "openrouter_api_key", "") or "") if st else ""
    if not api_key:
        return None

    model = (
        (getattr(st, "openrouter_model", "") or "") if st else ""
    ) or (cfg.get("openrouter") or {}).get("model") or "openai/gpt-4o-mini"
    model = str(model).strip()
    payload = json.dumps(facts, default=str)[:6000]
    system = (
        "You are a chief-of-staff drafting a CXO narrative briefing. "
        "Use ONLY the JSON facts provided. Do not invent statistics or URLs. "
        "Output 6–8 markdown bullets: executive tone, crisp, no fluff. "
        "Start bullets with bold labels like **Gap:** **Forums:** **YouTube:** **Reddit:** **Positioning:** **Receipts:** "
        "The last bullet must say exhibits/charts below must be cited under scrutiny."
    )
    user = f"FACTS JSON:\n{payload}\n\nWrite the briefing."
    gateway = LLMGateway()
    gateway.set_model(model)
    out = ""
    try:
        async for chunk in gateway.chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            stream=False,
            use_web_search=False,
        ):
            if not chunk:
                continue
            if chunk.strip().startswith('{"error"'):
                break
            out += chunk
    except Exception as e:
        logger.warning("narrative_briefing_llm_failed", error=str(e))
        return None
    text = (out or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text or None


async def build_narrative_briefing_pack(
    client: Optional[str] = None,
    range_days: int = 30,
    use_llm_memo: bool = True,
    include_audit_facts: bool = False,
) -> dict[str, Any]:
    """
    Aggregate landscape, forum tags, surface totals, YouTube, Reddit, positioning; optional LLM memo.
    Used by ingestion jobs only — not exposed for arbitrary user-driven LLM calls.
    If include_audit_facts=True, response includes _audit_facts (stripped before persist).
    """
    await get_mongo_client()
    from app.services.mongodb import get_db
    from app.services.forum_traction_service import get_forum_narrative_tag_traction
    from app.services.narrative_landscape_service import get_narrative_landscape
    from app.services.narrative_positioning_service import load_positioning
    from app.services.reddit_trending_service import load_latest_summary_from_mongo, load_posts_from_mongo
    from app.services.youtube_trending_service import load_daily_summaries

    client_name = ""
    entities: list[str] = []
    if client and client.strip():
        clients_list = await load_clients()
        client_obj = next(
            (c for c in clients_list if _str(c.get("name")).lower() == client.strip().lower()),
            None,
        )
        if client_obj:
            client_name = _str(client_obj.get("name"))
            entities = get_entity_names(client_obj)

    cutoff = datetime.now(timezone.utc) - timedelta(days=min(range_days, 90))

    async def _empty_list() -> list:
        return []

    async def _empty_surface() -> dict[str, int]:
        return {"article": 0, "forum": 0, "other": 0}

    ckey = (client or "").strip()
    landscape_task = get_narrative_landscape(client=client, range_days=range_days, top_tags=12)
    forum_task = get_forum_narrative_tag_traction(client=client, range_days=range_days, top_n=24)
    positioning_task = load_positioning(client=ckey, days=7) if ckey else _empty_list()
    yt_task = load_daily_summaries(limit=5)
    reddit_posts_task = load_posts_from_mongo(limit=14)
    reddit_summary_task = load_latest_summary_from_mongo()
    surface_task = _surface_totals(entities, cutoff) if entities else _empty_surface()

    landscape, forum_pack, positioning, yt, reddit_posts, reddit_pair, surface = await asyncio.gather(
        landscape_task,
        forum_task,
        positioning_task,
        yt_task,
        reddit_posts_task,
        reddit_summary_task,
        surface_task,
    )

    themes, _sahi = reddit_pair if reddit_pair else ([], [])
    theme_labels = [_str(t.get("label") or t.get("theme")) for t in (themes or []) if _str(t.get("label") or t.get("theme"))][
        :8
    ]

    forum_rows = forum_pack.get("narrative_tags") or []
    gaps = landscape.get("executive_gaps") or []

    yt_line = ""
    if yt:
        latest = yt[0]
        yt_line = _str(latest.get("narrative") or latest.get("narrative_summary") or latest.get("summary"))[:400]
        if not yt_line and latest.get("themes"):
            yt_line = "Themes: " + ", ".join(_str(x) for x in (latest.get("themes") or [])[:5])

    pos_line = ""
    latest_pos = positioning[0] if positioning else None
    if latest_pos:
        pos_line = _str((latest_pos.get("positioning") or {}).get("headline") or latest_pos.get("brief_summary"))[:350]

    facts = {
        "client_name": client_name,
        "range_days": range_days,
        "surface_totals": surface,
        "executive_gaps": gaps[:5],
        "top_forum_narrative_tags": forum_rows[:8],
        "youtube_one_line": yt_line,
        "reddit_theme_labels": theme_labels,
        "positioning_headline": pos_line,
        "landscape_row_count": len(landscape.get("landscape") or []),
    }

    memo_source = "deterministic"
    memo: dict[str, Any]
    if use_llm_memo and entities:
        llm_text = await _llm_memo(facts)
        if llm_text:
            memo = {"bullets": [], "raw_markdown": llm_text}
            memo_source = "llm"
        else:
            memo = _deterministic_memo(
                client_name, range_days, surface, gaps, forum_rows, yt_line, theme_labels, pos_line
            )
    else:
        memo = _deterministic_memo(
            client_name, range_days, surface, gaps, forum_rows, yt_line, theme_labels, pos_line
        )

    exhibits: dict[str, Any] = {
        "A": {
            "label": "Exhibit A — Narrative landscape (publication vs forum)",
            "subtitle": "Per-theme volumes, gaps, and earliest receipts",
            "landscape": (landscape.get("landscape") or [])[:8],
            "frame": landscape.get("frame"),
        },
        "B": {
            "label": "Exhibit B — Forum narrative traction",
            "subtitle": "Tag × forum site (amplifiers)",
            "rows": forum_rows[:12],
        },
        "C": {
            "label": "Exhibit C — YouTube narrative snapshots",
            "subtitle": "Latest daily summaries in DB",
            "summaries": [
                {
                    "date": y.get("date"),
                    "narrative": _str(y.get("narrative") or y.get("narrative_summary") or "")[:500],
                    "themes": (y.get("themes") or [])[:6],
                    "sentiment_summary": _str(y.get("sentiment_summary", ""))[:200],
                }
                for y in (yt or [])[:5]
            ],
        },
        "D": {
            "label": "Exhibit D — Reddit velocity",
            "subtitle": "LLM themes + recent posts (sample)",
            "themes": themes[:8] if themes else [],
            "posts": [
                {
                    "title": _str(p.get("title"))[:200],
                    "url": _str(p.get("url"))[:500],
                    "subreddit": _str(p.get("subreddit")),
                    "score": p.get("score"),
                }
                for p in (reddit_posts or [])[:10]
            ],
        },
        "E": {
            "label": "Exhibit E — PR positioning (stored reports)",
            "subtitle": "Newest first",
            "reports": positioning[:3] if positioning else [],
        },
    }

    generated_at = datetime.now(timezone.utc).isoformat()

    out: dict[str, Any] = {
        "meta": {
            "client": client,
            "client_name": client_name,
            "range_days": range_days,
            "generated_at": generated_at,
            "memo_source": memo_source,
            "entities_count": len(entities),
        },
        "memo": memo,
        "surface_totals": surface,
        "executive_gaps": gaps,
        "deep_links": {
            "briefing_ui": "/reports/narrative-briefing",
            "pr_dashboard": "/reports/pr",
            "landscape": "/social/narrative-landscape",
            "forums": "/social/forums",
            "positioning": "/social/narrative-intelligence",
            "social_hub": "/social",
            "executive_report": "/reports/executive-report",
        },
        "exhibits": exhibits,
    }
    if include_audit_facts:
        out["_audit_facts"] = facts
    return out


async def save_briefing_snapshot(pack: dict[str, Any], audit_facts: Optional[dict[str, Any]] = None) -> None:
    """Upsert today's snapshot for client × range_days (UTC calendar day)."""
    await get_mongo_client()
    from app.services.mongodb import get_db

    meta = pack.get("meta") or {}
    client_name = _str(meta.get("client_name"))
    range_days = int(meta.get("range_days") or 30)
    if not client_name:
        logger.warning("narrative_briefing_snapshot_skip", reason="missing client_name")
        return

    computed_at = datetime.now(timezone.utc)
    snapshot_date = computed_at.strftime("%Y-%m-%d")
    pack = {**pack, "meta": {**meta, "snapshot_computed_at": computed_at.isoformat(), "snapshot_date": snapshot_date, "served_from": "mongodb_snapshot"}}

    await _ensure_briefing_indexes()
    db = get_db()
    coll = db[SNAPSHOT_COLLECTION]

    doc = {
        "pipeline": PIPELINE_ID,
        "client": client_name,
        "range_days": range_days,
        "snapshot_date": snapshot_date,
        "computed_at": computed_at,
        "memo_source": meta.get("memo_source"),
        "pack": pack,
        "audit_facts": audit_facts,
    }
    await coll.replace_one(
        {
            "client": client_name,
            "range_days": range_days,
            "snapshot_date": snapshot_date,
            "pipeline": PIPELINE_ID,
        },
        doc,
        upsert=True,
    )
    logger.info("narrative_briefing_snapshot_saved", client=client_name, range_days=range_days, date=snapshot_date)


async def load_latest_briefing_snapshot(client: Optional[str], range_days: int = 30) -> Optional[dict[str, Any]]:
    """Return stored pack for UI (latest computed_at)."""
    await get_mongo_client()
    from app.services.mongodb import get_db

    ckey = (client or "").strip()
    if not ckey:
        return None
    clients_list = await load_clients()
    client_obj = next(
        (c for c in clients_list if _str(c.get("name")).lower() == ckey.lower()),
        None,
    )
    if not client_obj:
        return None
    client_name = _str(client_obj.get("name"))
    db = get_db()
    coll = db[SNAPSHOT_COLLECTION]
    doc = await coll.find_one(
        {"client": client_name, "range_days": range_days, "pipeline": PIPELINE_ID},
        sort=[("computed_at", -1)],
    )
    if not doc:
        return None
    pack = doc.get("pack")
    if not isinstance(pack, dict):
        return None
    # Ensure meta reflects DB provenance
    meta = dict(pack.get("meta") or {})
    ca = doc.get("computed_at")
    meta["snapshot_computed_at"] = ca.isoformat() if hasattr(ca, "isoformat") else str(ca)
    meta["snapshot_date"] = doc.get("snapshot_date")
    meta["served_from"] = "mongodb_snapshot"
    return {**pack, "meta": meta}


async def run_narrative_briefing_for_all_clients(range_days: Optional[int] = None) -> dict[str, Any]:
    """
    Build and persist briefing for every client in clients.yaml (ingestion / master backfill).
    LLM memo when API key present; else deterministic. Continues per client on error.
    """
    await get_mongo_client()
    await _ensure_briefing_indexes()
    cfg_days = range_days if range_days is not None else int(_nb_cfg().get("range_days", 30))
    cfg_days = max(1, min(cfg_days, 90))

    clients_list = await load_clients()
    results: list[dict[str, Any]] = []
    for c in clients_list:
        name = _str(c.get("name"))
        if not name:
            continue
        try:
            pack = await build_narrative_briefing_pack(
                client=name,
                range_days=cfg_days,
                use_llm_memo=True,
                include_audit_facts=True,
            )
            audit = pack.pop("_audit_facts", None)
            await save_briefing_snapshot(pack, audit_facts=audit)
            results.append({"client": name, "ok": True})
        except Exception as e:
            logger.exception("narrative_briefing_client_failed", client=name, error=str(e))
            results.append({"client": name, "ok": False, "error": str(e)})

    ok_n = sum(1 for r in results if r.get("ok"))
    return {
        "pipeline": PIPELINE_ID,
        "range_days": cfg_days,
        "clients_total": len(results),
        "clients_ok": ok_n,
        "clients_failed": len(results) - ok_n,
        "results": results,
    }


_TZ_SAFE = re.compile(r"^[A-Za-z0-9_+\-/]+$")


def _validate_iana_tz(name: Optional[str]) -> Optional[str]:
    if not name or not isinstance(name, str):
        return None
    s = name.strip()
    if len(s) > 64 or not _TZ_SAFE.match(s):
        return None
    try:
        ZoneInfo(s)
        return s
    except Exception:
        return None


def _calendar_dates_last_n_days(now_utc: datetime, n: int, tz_name: str) -> list[str]:
    """N consecutive calendar dates (YYYY-MM-DD) ending today in `tz_name`."""
    tz = ZoneInfo(tz_name)
    local = now_utc.astimezone(tz)
    out: list[str] = []
    for i in range(n - 1, -1, -1):
        d = local.date() - timedelta(days=i)
        out.append(d.isoformat())
    return out


def _utc_calendar_dates_last_n_days(now_utc: datetime, n: int) -> list[str]:
    out: list[str] = []
    for i in range(n - 1, -1, -1):
        d = now_utc.date() - timedelta(days=i)
        out.append(d.isoformat())
    return out


def _mention_trend_pipeline(entities: list[str], cutoff: datetime, tz_mongo: Optional[str]) -> list[dict[str, Any]]:
    """tz_mongo: IANA zone for $dateToString, or None for implicit UTC."""
    if tz_mongo:
        day_expr: Any = {"$dateToString": {"format": "%Y-%m-%d", "date": "$_dt", "timezone": tz_mongo}}
    else:
        day_expr = {"$dateToString": {"format": "%Y-%m-%d", "date": "$_dt"}}
    return [
        {
            "$match": {
                "entity": {"$in": entities},
                "$or": [
                    {"published_at": {"$gte": cutoff}},
                    {"timestamp": {"$gte": cutoff}},
                ],
            }
        },
        {"$addFields": {"_dt": {"$ifNull": ["$published_at", "$timestamp"]}}},
        {"$match": {"_dt": {"$gte": cutoff, "$ne": None}}},
        {"$addFields": {"day": day_expr, "typ": {"$ifNull": ["$type", "other"]}}},
        {"$group": {"_id": {"d": "$day", "t": "$typ"}, "n": {"$sum": 1}}},
    ]


async def _aggregate_mention_trends_by_day(
    coll: Any, entities: list[str], cutoff: datetime, tz_mongo: Optional[str]
) -> dict[str, dict[str, int]]:
    raw: dict[str, dict[str, int]] = {}
    pipe = _mention_trend_pipeline(entities, cutoff, tz_mongo)
    async for row in coll.aggregate(pipe):
        idd = row.get("_id") or {}
        d = _str(idd.get("d"))
        t = _str(idd.get("t")) or "other"
        n = int(row.get("n") or 0)
        if not d:
            continue
        raw.setdefault(d, {})
        raw[d][t] = raw[d].get(t, 0) + n
    return raw


async def get_mention_trends_for_client(
    client: Optional[str],
    days: int = 7,
    timezone_override: Optional[str] = None,
) -> dict[str, Any]:
    """
    Daily mention counts (article vs forum vs other) for client + competitors.
    Buckets align to calendar days in `report_timezone` from clients.yaml (or `timezone_override`),
    default UTC. Extra match window (+1 day) avoids TZ edge drops. Mongo without IANA support falls back to UTC.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    ckey = (client or "").strip()
    days = max(1, min(int(days or 7), 30))
    if not ckey:
        return {
            "series": [],
            "client": client,
            "days": days,
            "client_name": "",
            "timezone_effective": "UTC",
            "timezone_source": "none",
        }

    clients_list = await load_clients()
    client_obj = next(
        (c for c in clients_list if _str(c.get("name")).lower() == ckey.lower()),
        None,
    )
    if not client_obj:
        return {
            "series": [],
            "client": client,
            "days": days,
            "error": "unknown_client",
            "timezone_effective": "UTC",
            "timezone_source": "none",
        }
    client_name = _str(client_obj.get("name"))
    entities = get_entity_names(client_obj)
    if not entities:
        return {
            "series": [],
            "client_name": client_name,
            "days": days,
            "timezone_effective": "UTC",
            "timezone_source": "none",
        }

    query_tz = _validate_iana_tz(timezone_override)
    cfg_tz = _validate_iana_tz(_str(client_obj.get("report_timezone")))
    requested = query_tz or cfg_tz or "UTC"
    if query_tz:
        tz_source = "query"
    elif cfg_tz:
        tz_source = "client_config"
    else:
        tz_source = "default_utc"

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days + 1)

    db = get_db()
    coll = db[ENTITY_MENTIONS]
    mongo_tz_failed = False
    effective_tz = requested

    if requested == "UTC":
        raw = await _aggregate_mention_trends_by_day(coll, entities, cutoff, None)
        date_list = _utc_calendar_dates_last_n_days(now, days)
    else:
        try:
            raw = await _aggregate_mention_trends_by_day(coll, entities, cutoff, requested)
            date_list = _calendar_dates_last_n_days(now, days, requested)
        except Exception as e:
            from pymongo.errors import OperationFailure

            if not isinstance(e, OperationFailure):
                raise
            logger.warning(
                "mention_trends_mongo_timezone_unsupported",
                timezone=requested,
                error=str(e),
            )
            mongo_tz_failed = True
            effective_tz = "UTC"
            raw = await _aggregate_mention_trends_by_day(coll, entities, cutoff, None)
            date_list = _utc_calendar_dates_last_n_days(now, days)

    series: list[dict[str, Any]] = []
    for day_dt in date_list:
        buckets = raw.get(day_dt, {})
        art = int(buckets.get("article", 0))
        frm = int(buckets.get("forum", 0))
        oth = sum(v for k, v in buckets.items() if k not in ("article", "forum"))
        series.append({
            "date": day_dt,
            "article": art,
            "forum": frm,
            "other": oth,
            "total": art + frm + oth,
        })

    return {
        "client_name": client_name,
        "days": days,
        "series": series,
        "timezone_effective": effective_tz,
        "timezone_requested": requested,
        "timezone_source": tz_source,
        "mongo_timezone_fallback_utc": mongo_tz_failed,
    }


async def get_narrative_briefing_pack_for_api(client: Optional[str], range_days: int = 30) -> dict[str, Any]:
    """
    Public API: latest Mongo snapshot only (no live LLM).
    """
    await get_mongo_client()
    snap = await load_latest_briefing_snapshot(client, range_days=range_days)
    if snap:
        return snap
    return {
        "meta": {
            "client": client,
            "client_name": "",
            "range_days": range_days,
            "no_snapshot": True,
            "message": "No briefing snapshot yet. Run master backfill or wait for the daily narrative_briefing job.",
            "served_from": "none",
        },
        "memo": {"bullets": [], "raw_markdown": ""},
        "surface_totals": {"article": 0, "forum": 0, "other": 0},
        "executive_gaps": [],
        "deep_links": {
            "briefing_ui": "/reports/narrative-briefing",
            "pr_dashboard": "/reports/pr",
            "landscape": "/social/narrative-landscape",
            "forums": "/social/forums",
            "positioning": "/social/narrative-intelligence",
            "social_hub": "/social",
            "executive_report": "/reports/executive-report",
        },
        "exhibits": {},
    }
