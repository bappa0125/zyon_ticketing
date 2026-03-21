"""
Unified forum theme digest — retail/trader discourse without requiring brand entities.

- Indian forums: ValuePickr, TradingQnA, Traderji via forum-sourced article_documents.
- Reddit: social_posts where platform=reddit (second read path, same taxonomy).
- PR pack: three structured deliverables for agency weekly Sahi-style retainers.

Hacker News removed from default forum list (non-Indian signal).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.config import get_config
from app.core.logging import get_logger
from app.services.narrative_tagging_service import (
    forum_site_key,
    get_narrative_tag_meta,
    is_forum_document,
    score_all_narrative_themes,
)

logger = get_logger(__name__)

COLLECTION = "forum_theme_digest"
ARTICLE_DOCUMENTS = "article_documents"
SOCIAL_POSTS = "social_posts"

# Indian forum surfaces only (article_documents path). Reddit uses forum_site key "reddit".
DEFAULT_FORUM_SITES = frozenset({"valuepickr", "tradingqna", "traderji"})

# PR deliverable 2 — risk, compliance, money topics suitable for FAQ / crisis prep
PR_RISK_THEME_IDS = frozenset({
    "trust_safety",
    "regulatory_compliance",
    "support_resolution",
    "pricing_charges",
    "platform_ux_stability",
})

# PR deliverable 3 — angles for content, commentary, education
PR_ANGLE_THEME_IDS = frozenset({
    "education_content",
    "ipo_primary",
    "mf_wealth",
    "value_investing_recommendations",
    "options_fno",
    "commodity_research",
    "brand_influencer",
    "ai_analytics",
    "ai_trigger_algo_strategy",
})


def _digest_cfg() -> dict[str, Any]:
    cfg = get_config().get("forum_theme_digest")
    return cfg if isinstance(cfg, dict) else {}


def _allowed_forum_sites() -> frozenset[str]:
    raw = _digest_cfg().get("forum_sites")
    if isinstance(raw, list) and raw:
        return frozenset(str(x).strip().lower() for x in raw if str(x).strip())
    return DEFAULT_FORUM_SITES


def _include_reddit() -> bool:
    return bool(_digest_cfg().get("include_reddit", True))


ThemeBucket = dict[str, dict[str, Any]]  # forum_site -> theme_id -> agg


def _empty_theme_data() -> ThemeBucket:
    return defaultdict(lambda: defaultdict(lambda: {"count": 0, "score_sum": 0, "threads": []}))


async def _scan_article_documents_for_themes(
    theme_data: ThemeBucket,
    *,
    allowed: frozenset[str],
    cutoff: datetime,
    max_documents: int,
    min_text_len: int,
) -> tuple[int, int]:
    """Fill theme_data from forum article_documents. Returns (scanned, used)."""
    from app.services.mongodb import get_db

    db = get_db()
    coll = db[ARTICLE_DOCUMENTS]
    query = {
        "$or": [
            {"published_at": {"$gte": cutoff}},
            {"fetched_at": {"$gte": cutoff}},
        ]
    }
    scanned = 0
    used = 0
    cursor = coll.find(query).sort([("fetched_at", -1)]).limit(max_documents)
    async for doc in cursor:
        scanned += 1
        sd = (doc.get("source_domain") or "") or ""
        fd = (doc.get("feed_domain") or "") or ""
        if not is_forum_document(sd, fd):
            continue
        fs = forum_site_key(sd, fd)
        if not fs or fs not in allowed:
            continue

        title = (doc.get("title") or "")[:500]
        summary = (doc.get("summary") or "")[:4000]
        body = (doc.get("article_text") or "")[:12000]
        blob = f"{title}\n{summary}\n{body}".strip()
        if len(blob) < min_text_len:
            continue

        themes = score_all_narrative_themes(blob)
        if not themes:
            continue

        used += 1
        url = (doc.get("url") or doc.get("url_resolved") or "")[:2000]
        pub = doc.get("published_at") or doc.get("fetched_at")
        pub_str = pub.isoformat() if hasattr(pub, "isoformat") else str(pub or "")

        for tid, strength in themes:
            bucket = theme_data[fs][tid]
            bucket["count"] += 1
            bucket["score_sum"] += int(strength)
            bucket["threads"].append({
                "title": title[:300] or "(no title)",
                "url": url,
                "strength": int(strength),
                "published_at": pub_str,
            })
    return scanned, used


async def _scan_reddit_social_posts_for_themes(
    theme_data: ThemeBucket,
    *,
    cutoff: datetime,
    max_posts: int,
    min_text_len: int,
) -> tuple[int, int]:
    """Merge Reddit text posts into theme_data under forum_site \"reddit\"."""
    from app.services.mongodb import get_db

    db = get_db()
    coll = db[SOCIAL_POSTS]
    query = {
        "platform": "reddit",
        "$or": [
            {"published_at": {"$gte": cutoff}},
            {"timestamp": {"$gte": cutoff}},
        ],
    }
    scanned = 0
    used = 0
    cursor = coll.find(query).sort([("published_at", -1)]).limit(max_posts)
    async for doc in cursor:
        scanned += 1
        text = (doc.get("text") or "")[:2000]
        title = (doc.get("title") or "")[:300]
        blob = f"{title}\n{text}".strip() if title else text
        if len(blob) < min_text_len:
            continue

        themes = score_all_narrative_themes(blob)
        if not themes:
            continue

        used += 1
        url = (doc.get("url") or "")[:500]
        pub = doc.get("published_at") or doc.get("timestamp")
        pub_str = pub.isoformat() if hasattr(pub, "isoformat") else str(pub or "")
        display_title = (title or text[:120] or "(reddit)").strip()

        fs = "reddit"
        for tid, strength in themes:
            bucket = theme_data[fs][tid]
            bucket["count"] += 1
            bucket["score_sum"] += int(strength)
            bucket["threads"].append({
                "title": display_title[:300],
                "url": url,
                "strength": int(strength),
                "published_at": pub_str,
            })
    return scanned, used


def _sections_from_theme_data(
    theme_data: ThemeBucket,
    tag_meta: dict[str, dict[str, str]],
    top_threads_per_theme: int,
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for fs in sorted(theme_data.keys()):
        themes_out: list[dict[str, Any]] = []
        for tid, agg in sorted(
            theme_data[fs].items(),
            key=lambda x: (-x[1]["score_sum"], -x[1]["count"], x[0]),
        ):
            meta = tag_meta.get(tid) or {"label": tid, "description": ""}
            threads = sorted(agg["threads"], key=lambda t: -t["strength"])[:top_threads_per_theme]
            themes_out.append({
                "theme_id": tid,
                "label": meta.get("label", tid),
                "description": meta.get("description", ""),
                "thread_count": agg["count"],
                "keyword_hit_score": agg["score_sum"],
                "sample_threads": threads,
            })
        if themes_out:
            sections.append({"forum_site": fs, "themes": themes_out})
    return sections


def _flatten_theme_totals(sections: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """theme_id -> merged stats + samples with forum_site."""
    by_theme: dict[str, dict[str, Any]] = {}
    for sec in sections:
        fs = sec.get("forum_site") or ""
        for th in sec.get("themes") or []:
            tid = th.get("theme_id") or ""
            if not tid:
                continue
            if tid not in by_theme:
                by_theme[tid] = {
                    "label": th.get("label", tid),
                    "description": th.get("description", ""),
                    "total_threads": 0,
                    "total_score": 0,
                    "samples": [],
                }
            by_theme[tid]["total_threads"] += int(th.get("thread_count") or 0)
            by_theme[tid]["total_score"] += int(th.get("keyword_hit_score") or 0)
            for st in th.get("sample_threads") or []:
                by_theme[tid]["samples"].append({**dict(st), "forum_site": fs})
    return by_theme


def build_pr_deliverables(sections: list[dict[str, Any]], range_days: int) -> dict[str, Any]:
    """
    Three agency-ready blocks: discourse map, risk/FAQ hooks, content/spokesperson angles.
    Deterministic text — no LLM; safe for disclaimers.
    """
    if not sections:
        return {
            "version": 1,
            "range_days": range_days,
            "cover_line": "Insufficient forum + Reddit volume in-window for a PR pack — widen ingestion or window.",
            "deliverables": [],
        }

    by_theme = _flatten_theme_totals(sections)
    ranked = sorted(by_theme.items(), key=lambda x: (-x[1]["total_score"], -x[1]["total_threads"], x[0]))

    # --- Deliverable 1: discourse map ---
    top_n = ranked[:8]
    themes_ranked = []
    bullets_d1 = []
    for tid, agg in top_n:
        samples = sorted(agg["samples"], key=lambda s: -int(s.get("strength") or 0))[:3]
        lead = samples[0] if samples else {}
        themes_ranked.append({
            "theme_id": tid,
            "label": agg["label"],
            "thread_count_total": agg["total_threads"],
            "keyword_score_total": agg["total_score"],
            "lead_example": {
                "title": lead.get("title", ""),
                "url": lead.get("url", ""),
                "forum_site": lead.get("forum_site", ""),
            },
        })
        bullets_d1.append(
            f"**{agg['label']}** — {agg['total_threads']} thread hits (score {agg['total_score']}) "
            f"across monitored surfaces."
        )

    top_labels = ", ".join(a["label"] for _, a in top_n[:5])
    exec_d1 = (
        f"Over the last **{range_days} days**, monitored **Indian forums and Reddit** cluster most on: {top_labels}. "
        "Use the table below for client briefings; every line traces to linked threads."
    )

    d1 = {
        "id": "discourse_map",
        "title": "Weekly retail / trader discourse map",
        "purpose": "Executive and client prep: what themes dominated community discussion.",
        "executive_summary": exec_d1,
        "bullets": bullets_d1,
        "themes_ranked": themes_ranked,
    }

    # --- Deliverable 2: risk & FAQ ---
    risk_items = [(tid, by_theme[tid]) for tid in PR_RISK_THEME_IDS if tid in by_theme]
    risk_items.sort(key=lambda x: (-x[1]["total_score"], x[0]))
    bullets_d2 = []
    risk_examples = []
    for tid, agg in risk_items[:10]:
        samples = sorted(agg["samples"], key=lambda s: -int(s.get("strength") or 0))[:2]
        bullets_d2.append(
            f"**{agg['label']}**: {agg['total_threads']} discussions — draft FAQs and holding lines; "
            "verify facts before external use."
        )
        for s in samples:
            risk_examples.append({
                "theme_id": tid,
                "theme_label": agg["label"],
                "title": s.get("title", ""),
                "url": s.get("url", ""),
                "forum_site": s.get("forum_site", ""),
            })
    exec_d2 = (
        "Themes tied to **trust, regulation, pricing, platform, and support** — prioritize for "
        "stakeholder Q&A and crisis watchlists (illustrative samples only)."
    )
    if not bullets_d2:
        bullets_d2 = ["No strong risk-cluster threads in-window — still scan brand-specific mentions separately."]
    d2 = {
        "id": "risk_faq_hooks",
        "title": "Risk radar & FAQ hooks",
        "purpose": "Prepare answers before scrutiny spikes; not legal or compliance advice.",
        "executive_summary": exec_d2,
        "bullets": bullets_d2,
        "example_threads": risk_examples[:12],
    }

    # --- Deliverable 3: content & spokesperson angles ---
    angle_items = [(tid, by_theme[tid]) for tid in PR_ANGLE_THEME_IDS if tid in by_theme]
    angle_items.sort(key=lambda x: (-x[1]["total_score"], x[0]))
    bullets_d3 = []
    angle_examples = []
    for tid, agg in angle_items[:12]:
        samples = sorted(agg["samples"], key=lambda s: -int(s.get("strength") or 0))[:1]
        bullets_d3.append(
            f"**{agg['label']}**: active retail interest ({agg['total_threads']} hits) — "
            "candidate for explainer content, spokesperson commentary, or owned education."
        )
        if samples:
            s = samples[0]
            angle_examples.append({
                "theme_id": tid,
                "theme_label": agg["label"],
                "title": s.get("title", ""),
                "url": s.get("url", ""),
                "forum_site": s.get("forum_site", ""),
            })
    exec_d3 = (
        "Where retail is **learning, listing, allocating, or trading** — use for **content calendar** "
        "and **thought leadership** hooks (always align with compliance)."
    )
    if not bullets_d3:
        bullets_d3 = ["No dominant education/IPO/MF/options clusters in-window."]
    d3 = {
        "id": "content_spokesperson_angles",
        "title": "Content & spokesperson angles",
        "purpose": "Pitch decks, bylines, and social themes grounded in observed discourse.",
        "executive_summary": exec_d3,
        "bullets": bullets_d3,
        "example_threads": angle_examples[:12],
    }

    cover = (
        f"PR intelligence pack — **{range_days}d** window — "
        f"{len(sections)} surfaces (Indian forums + Reddit). "
        "Illustrative; not statistically representative of all investors."
    )

    return {
        "version": 1,
        "range_days": range_days,
        "cover_line": cover,
        "deliverables": [d1, d2, d3],
    }


async def build_forum_theme_digest(
    range_days: int = 7,
    max_documents: int = 2500,
    top_threads_per_theme: int = 6,
    min_text_len: int = 40,
    max_reddit_posts: int = 2000,
) -> dict[str, Any]:
    """
    Aggregate theme traction from forum article_documents + optional Reddit social_posts.
    """
    from app.services.mongodb import get_mongo_client

    range_days = max(1, min(int(range_days), 90))
    max_documents = max(100, min(int(max_documents), 15000))
    max_reddit_posts = max(0, min(int(max_reddit_posts), 10000))
    top_threads_per_theme = max(2, min(int(top_threads_per_theme), 15))

    await get_mongo_client()

    allowed = _allowed_forum_sites()
    cutoff = datetime.now(timezone.utc) - timedelta(days=range_days)
    tag_meta = get_narrative_tag_meta()

    theme_data = _empty_theme_data()

    scanned_ad, used_ad = await _scan_article_documents_for_themes(
        theme_data,
        allowed=allowed,
        cutoff=cutoff,
        max_documents=max_documents,
        min_text_len=min_text_len,
    )

    scanned_rd, used_rd = 0, 0
    if _include_reddit() and max_reddit_posts > 0:
        scanned_rd, used_rd = await _scan_reddit_social_posts_for_themes(
            theme_data,
            cutoff=cutoff,
            max_posts=max_reddit_posts,
            min_text_len=min_text_len,
        )

    sections = _sections_from_theme_data(theme_data, tag_meta, top_threads_per_theme)

    digest_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    computed_at = datetime.now(timezone.utc).isoformat()

    sites_human = ", ".join(sorted(allowed)) + (" + reddit" if _include_reddit() else "")

    disclaimer = (
        f"Illustrative only: **{sites_human}** over the last **{range_days} days**. "
        "Keyword scoring uses narrative_taxonomy.yaml — not exhaustive. "
        "Indian forums listed in config; Reddit from social_posts (platform=reddit). "
        "Does not replace entity-specific brand monitoring or legal/compliance review."
    )

    pr_deliverables = build_pr_deliverables(sections, range_days)

    surfaces = sorted({s["forum_site"] for s in sections})
    out: dict[str, Any] = {
        "digest_date": digest_date,
        "range_days": range_days,
        "computed_at": computed_at,
        "disclaimer": disclaimer,
        "forum_sites_configured": sorted(allowed),
        "include_reddit": _include_reddit(),
        "surfaces_with_data": surfaces,
        "sections": sections,
        "pr_deliverables": pr_deliverables,
        "stats": {
            "article_documents_scanned": scanned_ad,
            "forum_documents_scored": used_ad,
            "reddit_posts_scanned": scanned_rd,
            "reddit_posts_scored": used_rd,
        },
    }
    return out


async def save_forum_theme_digest(doc: dict[str, Any]) -> None:
    """Upsert digest for digest_date + range_days."""
    from app.services.mongodb import get_db, get_mongo_client

    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION]
    dd = doc.get("digest_date") or ""
    rd = int(doc.get("range_days") or 7)
    await coll.replace_one(
        {"digest_date": dd, "range_days": rd},
        doc,
        upsert=True,
    )
    logger.info("forum_theme_digest_saved", digest_date=dd, range_days=rd)


async def load_latest_forum_theme_digest(
    range_days: int = 7,
) -> Optional[dict[str, Any]]:
    from app.services.mongodb import get_db, get_mongo_client

    range_days = max(1, min(int(range_days), 90))
    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION]
    doc = await coll.find_one(
        {"range_days": range_days},
        sort=[("computed_at", -1)],
    )
    if not doc:
        doc = await coll.find_one({}, sort=[("computed_at", -1)])
    if not doc:
        return None
    doc.pop("_id", None)
    return doc


async def run_forum_theme_digest_job() -> dict[str, Any]:
    """Scheduled / manual entry: build, save, return summary."""
    cfg = _digest_cfg()
    if not cfg.get("enabled", True):
        return {"ok": False, "reason": "forum_theme_digest disabled"}
    range_days = int(cfg.get("range_days", 7))
    max_documents = int(cfg.get("max_documents", 2500))
    max_reddit = int(cfg.get("max_reddit_posts", 2000))
    top_threads = int(cfg.get("top_threads_per_theme", 6))
    doc = await build_forum_theme_digest(
        range_days=range_days,
        max_documents=max_documents,
        top_threads_per_theme=top_threads,
        min_text_len=int(cfg.get("min_text_len", 40)),
        max_reddit_posts=max_reddit,
    )
    await save_forum_theme_digest(doc)
    st = doc.get("stats") or {}
    return {
        "ok": True,
        "digest_date": doc.get("digest_date"),
        "range_days": doc.get("range_days"),
        "sections": len(doc.get("sections") or []),
        "forum_documents_scored": st.get("forum_documents_scored", 0),
        "reddit_posts_scored": st.get("reddit_posts_scored", 0),
        "pr_deliverables_count": len((doc.get("pr_deliverables") or {}).get("deliverables") or []),
    }
