"""
Actionable briefs for PR/campaigns — LLM synthesis from report and forum data.

- Forum PR brief: 3–5 actionable bullets for the PR team from forum perspective (topics, traction, samples).
- Campaign/content brief: per-brand brief (angles, suggested headlines, script prompt for video) for use with Pictory, Copy.ai, etc. Grounded in report data only.
"""

import json
from typing import Any

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)


async def get_forum_pr_brief(
    client_name: str,
    forum_traction: list[dict[str, Any]],
    sample_mentions: list[dict[str, Any]],
) -> str:
    """
    One LLM call: given forum topics traction and sample mentions, produce 3–5 actionable bullets for the PR team (forum perspective). Ground in data only.
    """
    from app.services.llm_gateway import LLMGateway

    topics_txt = "\n".join(
        f"- {t.get('topic', '')}: {t.get('mention_count', 0)} mentions; samples: {', '.join((t.get('sample_titles') or [])[:2])}"
        for t in forum_traction[:10]
    ) or "No topic data."
    mentions_txt = "\n".join(
        f"- [{m.get('source_domain', '')}] {m.get('title', '')[:80]}: {m.get('summary', '')[:120]}"
        for m in sample_mentions[:8]
    ) or "No sample mentions."

    system = (
        "You are a PR analyst. Given forum topic traction and sample forum mentions for a brand, "
        "produce 3–5 short, actionable bullets for the PR team (forum perspective only). "
        "Ground every point in the data. Do not prescribe campaigns; suggest angles to consider (e.g. 'Topic X is trending in forums; consider a response or content piece'). "
        "Return ONLY a JSON object with one key: \"bullets\" (array of 3–5 strings, each one bullet)."
    )
    user = (
        f"Brand: {client_name}\n\n"
        "Forum topics (traction):\n" + topics_txt + "\n\n"
        "Sample forum mentions:\n" + mentions_txt
    )[:4000]

    cfg = get_config().get("narrative_positioning") or {}
    llm_cfg = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    model = (llm_cfg.get("model") or get_config().get("openrouter", {}).get("model") or "openrouter/free")
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
        logger.warning("forum_pr_brief_llm_failed", client=client_name, error=str(e))
        return ""

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
        bullets = parsed.get("bullets") or []
        if isinstance(bullets, list):
            return "\n".join(f"• {b}" for b in bullets[:5] if b)
        return ""
    except json.JSONDecodeError:
        return s[:800] if s else ""


async def get_campaign_briefs_for_report(clients_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    One LLM call for all clients: given a compact summary per brand (narrative, positioning, opportunities, topics), 
    return a short campaign/content brief per brand (angles, suggested headlines, script prompt for video). 
    For use by PR/client with tools like Pictory, Copy.ai. Ground in data only; suggest, do not prescribe.
    Returns: [ { "brand": str, "brief": str }, ... ]
    """
    from app.services.llm_gateway import LLMGateway

    blocks = []
    for c in clients_data[:10]:
        name = (c.get("brand") or c.get("client_name") or "").strip()
        if not name:
            continue
        blocks.append(
            f"[{name}]\n"
            f"  PR/narrative brief: {(c.get('pr_brief') or '')[:200]}\n"
            f"  Positioning mix: {(c.get('positioning_mix_summary') or '')[:150]}\n"
            f"  Top topics: {(c.get('top_topics_display') or '')[:150]}\n"
            f"  Opportunities: {(c.get('top_opportunity') or '')[:150]}\n"
            f"  Reputation/SOV: {(c.get('reputation_note') or '')[:100]}"
        )
    data_txt = "\n\n".join(blocks) or "No client data."

    system = (
        "You are a PR/campaign strategist. Given competitor intelligence per brand (brief, positioning, topics, opportunities), "
        "produce a short campaign/content brief for each brand. Each brief: 2–3 suggested angles, one suggested headline, one short script prompt for video (1–2 sentences for Pictory-style tools). "
        "Ground in the data only. Frame as suggestions for the client/PR to consider, not prescriptions. "
        "Return ONLY valid JSON: { \"briefs\": [ { \"brand\": \"Name\", \"brief\": \"2–4 sentences plus headline and script prompt\" }, ... ] }."
    )
    user = "Client intelligence summary:\n\n" + data_txt
    user = user[:6000]

    cfg = get_config().get("narrative_positioning") or {}
    llm_cfg = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    model = (llm_cfg.get("model") or get_config().get("openrouter", {}).get("model") or "openrouter/free")
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
        logger.warning("campaign_brief_llm_failed", error=str(e))
        return [{"brand": d.get("brand") or d.get("client_name") or "", "brief": ""} for d in clients_data]

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
        briefs = parsed.get("briefs") or []
        if isinstance(briefs, list):
            return [{"brand": b.get("brand", ""), "brief": (b.get("brief") or "")[:1500]} for b in briefs]
        return []
    except json.JSONDecodeError:
        return []
