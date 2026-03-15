"""
Executive Competitor Intelligence Report — aggregates data and optional LLM sections.

Builds report from: reputation, media dashboard, coverage, opportunities, PR intel,
narrative positioning, narrative shift, AI search visibility, positioning mix, narrative analytics.
Optional LLM: forum PR brief (per client), campaign/content brief (one call for all).
Stored in executive_competitor_reports; generated weekly by scheduler and at end of master backfill.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.client_config_loader import get_entity_names, load_clients
from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client
from app.services.positioning_mix_service import get_positioning_mix

logger = get_logger(__name__)

COLLECTION = "executive_competitor_reports"
ENTITY_MENTIONS_COLLECTION = "entity_mentions"


def _str(val: Any) -> str:
    """Safely coerce to string; avoid .strip() on dict/list."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, dict):
        for key in ("text", "summary", "value", "content"):
            v = val.get(key)
            if v is not None and isinstance(v, str):
                return v.strip()[:500]
        return str(val)[:500]
    return str(val)[:500]


def _parse_range(range_param: str) -> timedelta:
    if range_param == "24h":
        return timedelta(hours=24)
    if range_param == "7d":
        return timedelta(days=7)
    if range_param == "30d":
        return timedelta(days=30)
    return timedelta(days=7)


def _reputation_score(positive: int, neutral: int, negative: int) -> int:
    """Derive 0-100 score from sentiment counts (no LLM)."""
    total = positive + neutral + negative
    if total == 0:
        return 50
    # Weight: pos=1, neu=0.5, neg=0 -> scale to 0-100
    raw = (positive * 1.0 + neutral * 0.5) / total
    return min(100, max(0, int(round(raw * 100))))


async def _get_sentiment_rows(client_name: str, entities: list[str], range_param: str) -> list[dict[str, Any]]:
    """Aggregate sentiment per entity for client's entity set."""
    if not entities:
        return []
    delta = _parse_range(range_param)
    cutoff = datetime.now(timezone.utc) - delta
    from app.services.mongodb import get_db
    db = get_db()
    em = db[ENTITY_MENTIONS_COLLECTION]
    match = {
        "entity": {"$in": entities},
        "$or": [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}],
    }
    pipeline = [
        {"$match": match},
        {"$project": {"entity": 1, "sentiment": {"$ifNull": ["$sentiment", "neutral"]}}},
        {
            "$group": {
                "_id": "$entity",
                "positive": {"$sum": {"$cond": [{"$eq": ["$sentiment", "positive"]}, 1, 0]}},
                "neutral": {"$sum": {"$cond": [{"$eq": ["$sentiment", "neutral"]}, 1, 0]}},
                "negative": {"$sum": {"$cond": [{"$eq": ["$sentiment", "negative"]}, 1, 0]}},
                "total": {"$sum": 1},
            }
        },
        {"$project": {"entity": "$_id", "positive": 1, "neutral": 1, "negative": 1, "total": 1, "_id": 0}},
        {"$sort": {"total": -1}},
    ]
    rows: list[dict[str, Any]] = []
    async for doc in em.aggregate(pipeline):
        rows.append(doc)
    return rows


async def build_and_save_executive_report(range_param: str = "7d") -> dict[str, Any]:
    """
    Build the full executive competitor report from existing services (no LLM), save to MongoDB.
    Uses load_clients() so when executive_competitor_analysis.use_this_file is true, uses the 5-client set.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db
    from app.services.media_intelligence_service import get_dashboard
    from app.services.coverage_service import compute_coverage, get_article_counts
    from app.services.opportunity_service import detect_pr_opportunities
    from app.services.pr_opportunities_service import get_pr_opportunities
    from app.services.ai_brief_service import get_ai_brief_from_db
    from app.services.narrative_positioning_service import load_positioning
    from app.services.narrative_shift_service import load_latest_run
    from app.services.ai_search_visibility_service import load_dashboard as load_visibility_dashboard

    clients_list = await load_clients()
    if not clients_list:
        logger.warning("executive_report_no_clients")
        return {"ok": False, "reason": "no clients", "generated_at": None}

    now = datetime.now(timezone.utc)
    y, w, _ = now.isocalendar()
    week_label = f"{y}-W{w:02d}"

    # Global (once)
    narrative_shift = await load_latest_run()
    narrative_shift_themes = []
    if narrative_shift and isinstance(narrative_shift.get("narratives"), list):
        for n in narrative_shift.get("narratives", [])[:10]:
            if isinstance(n, dict) and n.get("theme") is not None:
                narrative_shift_themes.append(_str(n.get("theme")))
            elif isinstance(n, str) and n:
                narrative_shift_themes.append(n.strip())

    section1_rows: list[dict[str, Any]] = []
    section2_rows: list[dict[str, Any]] = []
    section3_rows: list[dict[str, Any]] = []
    section4_rows: list[dict[str, Any]] = []
    section5_rows: list[dict[str, Any]] = []
    section6_rows: list[dict[str, Any]] = []
    section7_rows: list[dict[str, Any]] = []
    section8_rows: list[dict[str, Any]] = []
    section9_narrative_analytics: dict[str, Any] = {}
    section_forum_traction_rows: list[dict[str, Any]] = []
    section_forum_pr_brief: list[dict[str, Any]] = []
    client_summaries_for_campaign: list[dict[str, Any]] = []

    total_articles = 0
    range_days = 7
    if range_param == "24h":
        range_days = 1
    elif range_param == "30d":
        range_days = 30
    elif range_param == "7d":
        range_days = 7
    total_sources = set()
    prompt_groups_used = 0

    for client_obj in clients_list:
        client_name = _str(client_obj.get("name"))
        if not client_name:
            continue
        entities = get_entity_names(client_obj)

        # 1. Reputation & Sentiment (one row per brand)
        sent_rows = await _get_sentiment_rows(client_name, entities, range_param)
        row_for_client = next((r for r in sent_rows if _str(r.get("entity")) == client_name), None)
        if row_for_client:
            pos = row_for_client.get("positive", 0) or 0
            neu = row_for_client.get("neutral", 0) or 0
            neg = row_for_client.get("negative", 0) or 0
            total = row_for_client.get("total", 0) or 0
            score = _reputation_score(pos, neu, neg)
            pct_pos = round(pos / total * 100, 0) if total else 0
            pct_neu = round(neu / total * 100, 0) if total else 0
            pct_neg = round(neg / total * 100, 0) if total else 0
            section1_rows.append({
                "brand": client_name,
                "reputation_score": score,
                "sentiment_pct": f"{pct_pos}% / {pct_neu}% / {pct_neg}%",
                "trend_vs_prev_7d": "—",
                "risk_note": "Elevated negative" if pct_neg >= 15 else ("Monitor" if pct_neg >= 12 else "—"),
            })
        else:
            section1_rows.append({
                "brand": client_name,
                "reputation_score": 50,
                "sentiment_pct": "—",
                "trend_vs_prev_7d": "—",
                "risk_note": "—",
            })

        # 2. Media Intelligence — dashboard for SOV and pr_summary
        try:
            dash = await get_dashboard(client=client_name, range_param=range_param)
        except Exception as e:
            logger.debug("executive_report_dashboard_failed", client=client_name, error=str(e))
            dash = {}
        coverage_list = dash.get("coverage") or []
        total_mentions = sum(c.get("mentions", 0) for c in coverage_list)
        by_domain = dash.get("by_domain") or []
        for d in by_domain:
            dom = _str(d.get("domain"))
            if dom:
                total_sources.add(dom)
        client_mentions = next((c.get("mentions", 0) for c in coverage_list if _str(c.get("entity")) == client_name), 0)
        sov_pct = round(client_mentions / total_mentions * 100, 0) if total_mentions else 0
        _pr_summary_raw = dash.get("pr_summary")
        pr_summary_line = _str(_pr_summary_raw).split("\n")[0][:200] if _pr_summary_raw is not None and _pr_summary_raw != "" else "—"
        section2_rows.append({
            "brand": client_name,
            "share_of_voice_pct": sov_pct,
            "news_pct": sov_pct,
            "social_pct": sov_pct,
            "pr_agency_summary": pr_summary_line or "—",
        })

        # 3. Coverage intel
        try:
            art_counts = await get_article_counts(client_name)
            cov = await compute_coverage(client_name)
        except Exception as e:
            logger.debug("executive_report_coverage_failed", client=client_name, error=str(e))
            art_counts = {}
            cov = []
        articles_7d = art_counts.get("articles_with_client_mentioned") or 0
        total_articles += articles_7d
        sources_count = len([d for d in (by_domain or []) if (d.get("entities") or {}).get(client_name, 0) > 0])
        top_pubs = [_str(d.get("name") or d.get("domain")) for d in (by_domain or [])[:5] if (d.get("entities") or {}).get(client_name, 0) > 0][:3]
        opportunities_sources = [_str(d.get("name") or d.get("domain")) for d in (by_domain or []) if (d.get("entities") or {}).get(client_name, 0) == 0 and d.get("total", 0) >= 2][:3]
        section3_rows.append({
            "brand": client_name,
            "articles_7d": articles_7d,
            "sources_with_coverage": sources_count,
            "top_publications": ", ".join(top_pubs) if top_pubs else "—",
            "gap_outlets": ", ".join(opportunities_sources) if opportunities_sources else "—",
        })

        # 4. PR opportunities
        try:
            opps = await detect_pr_opportunities(client_name)
            pr_intel = await get_pr_opportunities(client_name, days=7)
        except Exception as e:
            logger.debug("executive_report_opportunities_failed", client=client_name, error=str(e))
            opps = []
            pr_intel = {}
        quote_alerts = (pr_intel.get("quote_alerts") or [])
        pub_gaps = len(opps)
        top_opportunity = "—"
        if quote_alerts:
            top_opportunity = _str(quote_alerts[0].get("headline") or quote_alerts[0].get("summary") or "Quote alert")[:120]
        elif opps:
            top_opportunity = f"{pub_gaps} publication gap(s); prioritize outreach."
        section4_rows.append({
            "brand": client_name,
            "quote_alerts": len(quote_alerts),
            "pub_gaps": pub_gaps,
            "top_opportunity": top_opportunity,
        })

        # 5. PR Intelligence 7d synopsis — use AI brief or pr_summary (no LLM here)
        try:
            brief_doc = await get_ai_brief_from_db(client=client_name, range_param=range_param)
        except Exception:
            brief_doc = None
        synopsis = _str(brief_doc.get("brief"))[:500] if brief_doc else (pr_summary_line or "No synopsis for this period.")
        section5_rows.append({"brand": client_name, "synopsis_7d": synopsis or "—"})

        # 6. Narrative shift & PR brief
        try:
            positioning_reports = await load_positioning(client=client_name, days=7)
        except Exception as e:
            logger.debug("executive_report_positioning_failed", client=client_name, error=str(e))
            positioning_reports = []
        latest = positioning_reports[0] if positioning_reports else {}
        brief = _str(latest.get("brief_summary") or latest.get("positioning") or "")[:300] if latest else ""
        mix_summary = _str(latest.get("positioning_mix_summary") or "")[:200] if latest else ""
        brief_summary = (brief + ("\n" + mix_summary if mix_summary else "")).strip() or "—"
        narratives_headline = ", ".join(narrative_shift_themes[:5]) if narrative_shift_themes else "—"
        section6_rows.append({
            "brand": client_name,
            "narrative_shift_themes": narratives_headline,
            "pr_brief": brief_summary or "—",
        })

        # 7. AI Search Visibility
        try:
            vis = await load_visibility_dashboard(client=client_name, weeks=8)
        except Exception as e:
            logger.debug("executive_report_visibility_failed", client=client_name, error=str(e))
            vis = {}
        latest_snap = vis.get("latest") or {}
        overall = latest_snap.get("overall_index") or 0
        group_metrics = latest_snap.get("group_metrics") or []
        by_group: dict[str, float] = {_str(g.get("group_id")): g.get("score_pct", 0) for g in group_metrics}
        if group_metrics:
            prompt_groups_used = max(prompt_groups_used, len(group_metrics))
        section7_rows.append({
            "brand": client_name,
            "overall_index": overall,
            "broker_discovery": by_group.get("broker_discovery", 0),
            "zerodha_alt": by_group.get("zerodha_alternative", 0),
            "feature": by_group.get("feature_driven", 0),
            "problem": by_group.get("problem_driven", 0),
            "comparison": by_group.get("product_comparison", 0),
        })

        # 8. Positioning mix — forum vs news, YouTube, Reddit, topics, competitor-only (evidence + gaps)
        try:
            mix = await get_positioning_mix(client_name, range_param)
            section8_rows.append({
                "brand": mix.get("brand", client_name),
                "forum_pct": mix.get("forum_pct", 0),
                "news_pct": mix.get("news_pct", 0),
                "youtube_count": mix.get("youtube_count", 0),
                "reddit_count": mix.get("reddit_count", 0),
                "forum_count": mix.get("forum_count", 0),
                "total_mentions": mix.get("total_mentions", 0),
                "top_topics_display": mix.get("top_topics_display", "—"),
                "competitor_only_count": mix.get("competitor_only_count", 0),
                "top_opportunity": mix.get("top_opportunity", "—"),
            })
        except Exception as e:
            logger.debug("executive_report_positioning_mix_failed", client=client_name, error=str(e))
            section8_rows.append({
                "brand": client_name,
                "forum_pct": 0,
                "news_pct": 0,
                "youtube_count": 0,
                "reddit_count": 0,
                "forum_count": 0,
                "total_mentions": 0,
                "top_topics_display": "—",
                "competitor_only_count": 0,
                "top_opportunity": "—",
            })

        # Forum topics traction (detailed table) + sample mentions for LLM
        try:
            from app.services.forum_traction_service import get_forum_topics_traction as get_forum_traction
            traction_data = await get_forum_traction(client=client_name, range_days=range_days, top_n=15)
            topics_list = traction_data.get("topics") or []
            for t in topics_list:
                section_forum_traction_rows.append({
                    "brand": client_name,
                    "topic": _str(t.get("topic")),
                    "mention_count": t.get("mention_count", 0),
                    "sample_titles": ", ".join((t.get("sample_titles") or [])[:3]) or "—",
                })
            # Sample forum mentions for PR brief LLM
            from app.services.mongodb import get_db
            db = get_db()
            em_coll = db[ENTITY_MENTIONS_COLLECTION]
            delta = _parse_range(range_param)
            cutoff = datetime.now(timezone.utc) - delta
            sample_mentions: list[dict[str, Any]] = []
            async for doc in em_coll.find({
                "type": "forum",
                "entity": {"$in": entities},
                "$or": [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}],
            }).sort("published_at", -1).limit(10):
                sample_mentions.append({
                    "title": (doc.get("title") or "")[:300],
                    "summary": (doc.get("summary") or doc.get("snippet") or "")[:200],
                    "source_domain": doc.get("source_domain") or "",
                })
            from app.services.campaign_brief_service import get_forum_pr_brief
            forum_brief_text = await get_forum_pr_brief(client_name, topics_list, sample_mentions)
            section_forum_pr_brief.append({"brand": client_name, "brief": forum_brief_text or "—"})
        except Exception as e:
            logger.debug("executive_report_forum_traction_or_brief_failed", client=client_name, error=str(e))
            section_forum_pr_brief.append({"brand": client_name, "brief": "—"})

        # Collect client summary for campaign brief (one LLM call after loop)
        latest_pos = positioning_reports[0] if positioning_reports else {}
        pr_brief = _str(latest_pos.get("brief_summary") or "")[:300]
        mix_summary = _str(latest_pos.get("positioning_mix_summary") or "")[:200]
        client_summaries_for_campaign.append({
            "brand": client_name,
            "pr_brief": pr_brief,
            "positioning_mix_summary": mix_summary,
            "top_topics_display": section8_rows[-1].get("top_topics_display", "—") if section8_rows else "—",
            "top_opportunity": section8_rows[-1].get("top_opportunity", "—") if section8_rows else "—",
            "reputation_note": section1_rows[-1].get("risk_note", "—") if section1_rows else "—",
        })

    # Campaign/content brief (one LLM call for all clients)
    section_campaign_brief: list[dict[str, Any]] = []
    try:
        from app.services.campaign_brief_service import get_campaign_briefs_for_report
        section_campaign_brief = await get_campaign_briefs_for_report(client_summaries_for_campaign)
    except Exception as e:
        logger.debug("executive_report_campaign_brief_failed", error=str(e))
        section_campaign_brief = [{"brand": _str(c.get("brand")), "brief": "—"} for c in client_summaries_for_campaign]

    # 9. Narrative analytics (7d) — from narrative_intelligence_daily (global synthesis)
    try:
        from app.services.narrative_intelligence_daily_service import load_last_n_days
        daily_reports = await load_last_n_days(days=7)
        if daily_reports:
            latest = daily_reports[0]
            section9_narrative_analytics = {
                "executive_summary": _str(latest.get("executive_summary"))[:600],
                "top_narratives": [
                    {"rank": r.get("rank", i + 1), "topic": _str(r.get("topic"))[:150], "rationale": _str(r.get("rationale"))[:200]}
                    for i, r in enumerate((latest.get("top_narratives") or [])[:5])
                    if isinstance(r, dict)
                ],
                "pr_actions": [
                    {"action": _str(a.get("action"))[:200], "priority": _str(a.get("priority"))[:20]}
                    for a in (latest.get("pr_actions") or [])[:5]
                    if isinstance(a, dict)
                ],
                "influencers": [_str(x) for x in (latest.get("influencers") or [])[:8]],
                "sentiment": _str(latest.get("sentiment")) or "mixed",
                "date": latest.get("date"),
                "days_loaded": len(daily_reports),
            }
        else:
            section9_narrative_analytics = {"executive_summary": "", "top_narratives": [], "pr_actions": [], "influencers": [], "sentiment": "mixed", "days_loaded": 0}
    except Exception as e:
        logger.debug("executive_report_narrative_analytics_failed", error=str(e))
        section9_narrative_analytics = {"executive_summary": "", "top_narratives": [], "pr_actions": [], "influencers": [], "sentiment": "mixed", "days_loaded": 0}

    # Executive summary (template, no LLM)
    summary_text = (
        f"Unified view for {len(clients_list)} brands over the last {range_param}. "
        f"Total articles (with client mention): {total_articles}; sources: {len(total_sources)}. "
        "See sections below for reputation, share of voice, coverage, PR opportunities, narrative, AI search visibility, and positioning mix (forum vs news, topics, gaps)."
    )
    takeaways = [
        "Data aggregated from Pulse (reputation & sentiment), Media Intelligence, Coverage, Opportunities, Narrative Positioning, AI Search Visibility, and Positioning Mix (forum vs news, topic mix, competitor-only gaps).",
    ]
    missing_hint = (
        "Narrative shift (PR brief), PR Intelligence synopsis, and Quote alerts are filled by batch jobs per brand. "
        "If Zerodha, Dhan, Groww, Kotak show no data: run «Populate data for all brands» on this page (or run Narrative Positioning, AI Brief, and PR Opportunities batches with executive_competitor_analysis enabled), then regenerate the report."
    )
    payload = {
        "meta": {
            "period": f"Last {range_param}",
            "week": week_label,
            "data_coverage": f"{len(clients_list)} brands, {total_articles}+ articles, {len(total_sources)} sources",
            "last_updated": now.isoformat(),
        },
        "executive_summary": summary_text,
        "takeaways": takeaways,
        "section1_reputation": section1_rows,
        "section2_media_intel": section2_rows,
        "section3_coverage": section3_rows,
        "section4_opportunities": section4_rows,
        "section5_pr_intel_synopsis": section5_rows,
        "section6_narrative": section6_rows,
        "section7_ai_visibility": section7_rows,
        "section8_positioning_mix": section8_rows,
        "section9_narrative_analytics": section9_narrative_analytics,
        "section_forum_traction": section_forum_traction_rows,
        "section_forum_pr_brief": section_forum_pr_brief,
        "section_campaign_brief": section_campaign_brief,
        "data_quality_note": "Report built from pipelines; Forum PR brief and Campaign brief use LLM. Run weekly or via master backfill.",
        "missing_data_hint": missing_hint,
    }

    db = get_db()
    coll = db[COLLECTION]
    doc = {
        "range_param": range_param,
        "period_end": now.isoformat(),
        "generated_at": now,
        "payload": payload,
        "clients_count": len(clients_list),
    }
    await coll.insert_one(doc)
    logger.info("executive_report_generated", range_param=range_param, clients=len(clients_list))
    return {"ok": True, "generated_at": now.isoformat(), "clients_count": len(clients_list)}


async def get_latest_report() -> dict[str, Any] | None:
    """Return the latest stored report document (without _id), or None."""
    await get_mongo_client()
    from app.services.mongodb import get_db
    db = get_db()
    coll = db[COLLECTION]
    doc = await coll.find_one(sort=[("generated_at", -1)])
    if not doc:
        return None
    out = {
        "range_param": doc.get("range_param"),
        "period_end": doc.get("period_end"),
        "generated_at": doc.get("generated_at"),
        "payload": doc.get("payload"),
        "clients_count": doc.get("clients_count"),
    }
    if hasattr(out.get("generated_at"), "isoformat"):
        out["generated_at"] = out["generated_at"].isoformat()
    return out
