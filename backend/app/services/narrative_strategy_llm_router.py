from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from openai import AsyncOpenAI

from app.config import get_config
from app.core.logging import get_logger
from app.services.llm_gateway import LLMGateway

logger = get_logger(__name__)


def _cfg_llm() -> dict[str, Any]:
    return (get_config().get("narrative_strategy_engine") or {}).get("llm") or {}


def _sha(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def _is_generic(text: str) -> bool:
    s = (text or "").strip().lower()
    if not s:
        return True
    bad = [
        "a market narrative is forming",
        "market narrative",
        "gaining attention",
        "discussion cluster",
        "users are talking",
    ]
    return any(b in s for b in bad) or len(s) < 40


def _validate_schema(obj: Any) -> tuple[bool, str]:
    if not isinstance(obj, dict):
        return False, "not_object"
    required = ["narrative", "categories", "vertical", "relevance", "gaps", "recommendations"]
    for k in required:
        if k not in obj:
            return False, f"missing_{k}"
    if not isinstance(obj.get("categories"), list):
        return False, "categories_not_list"
    if not isinstance(obj.get("gaps"), dict):
        return False, "gaps_not_object"
    if not isinstance(obj.get("recommendations"), dict):
        return False, "recommendations_not_object"
    # ensure at least one gap true
    gaps = obj.get("gaps") or {}
    if isinstance(gaps, dict):
        if not any(bool(v) for v in gaps.values()):
            return False, "no_gap_true"
    # ensure action fields present
    rec = obj.get("recommendations") or {}
    if isinstance(rec, dict):
        for k in ("positioning", "action", "content_direction"):
            if not str(rec.get(k) or "").strip():
                return False, f"recommendations_missing_{k}"
    if _is_generic(str(obj.get("narrative") or "")):
        return False, "generic_narrative"
    return True, "ok"


async def _call_openrouter(model: str, messages: list[dict[str, str]]) -> str:
    gw = LLMGateway()
    gw.set_model(model)
    out = ""
    async for chunk in gw.chat_completion(messages=messages, stream=False, use_web_search=False):
        out += chunk or ""
    return out.strip()


async def _call_openai(model: str, messages: list[dict[str, str]]) -> str:
    cfg = get_config()
    key = cfg["settings"].openai_api_key
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    client = AsyncOpenAI(api_key=key, timeout=60.0)
    resp = await client.chat.completions.create(model=model, messages=messages)  # type: ignore[arg-type]
    txt = ""
    if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
        txt = resp.choices[0].message.content
    return (txt or "").strip()


async def _get_cache(coll, cache_key: str) -> Optional[dict[str, Any]]:
    try:
        doc = await coll.find_one({"cache_key": cache_key})
        if not doc:
            return None
        d = dict(doc)
        d.pop("_id", None)
        return d.get("value") if isinstance(d.get("value"), dict) else None
    except Exception:
        return None


async def _set_cache(coll, cache_key: str, value: dict[str, Any]) -> None:
    try:
        await coll.update_one(
            {"cache_key": cache_key},
            {"$set": {"cache_key": cache_key, "value": value, "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    except Exception:
        pass


async def enrich_cluster_consulting_grade(
    *,
    company: str,
    vertical: str,
    categories: list[dict[str, Any]],
    evidence: list[dict[str, str]],
    base_obj: dict[str, Any],
    allow_premium_fallback: bool,
    cache_namespace: str,
) -> dict[str, Any]:
    """
    Returns a strict object. Uses:
    - draft model (OpenRouter)
    - fallback model (OpenAI) only when needed and allowed
    Includes Mongo caching keyed by cluster signature.
    """
    from app.services.mongodb import get_db

    db = get_db()
    cache_coll = db["narrative_strategy_llm_cache"]

    sig = {
        "company": company.strip(),
        "vertical": vertical.strip().lower(),
        "evidence_urls": [e.get("url", "") for e in (evidence or []) if e.get("url")],
        "namespace": cache_namespace,
    }
    cache_key = _sha(json.dumps(sig, sort_keys=True))

    cached = await _get_cache(cache_coll, cache_key)
    if cached:
        ok, _ = _validate_schema(cached)
        if ok:
            return cached

    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    fallback_model = (llm_cfg.get("fallback_model") or "gpt-4o-mini").strip()

    cat_lines = []
    for c in categories or []:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or "").strip()
        lab = str(c.get("label") or "").strip()
        desc = str(c.get("description") or "").strip()
        if cid and lab:
            cat_lines.append(f"- {cid}: {lab} — {desc}")

    ev_lines = []
    for i, e in enumerate((evidence or [])[:6], 1):
        ev_lines.append(f"{i}. {e.get('title','')}\nURL: {e.get('url','')}\nSnippet: {e.get('snippet','')}")

    system = (
        "You are a senior narrative strategist (consulting-grade) for financial institutions.\n"
        "Goal: turn Reddit evidence into one narrative + gaps + actions.\n"
        "Hard rules:\n"
        "- NO stock recommendations.\n"
        "- Output MUST be valid JSON object ONLY.\n"
        "- Must include at least one gap=true.\n"
        "- Must cite evidence implicitly (your narrative and actions should clearly match evidence).\n"
    )

    user = (
        f"Company: {company}\n"
        f"Vertical: {vertical}\n\n"
        f"Vertical categories:\n{chr(10).join(cat_lines) if cat_lines else '(none)'}\n\n"
        f"Evidence:\n{chr(10).join(ev_lines)}\n\n"
        "Return JSON with this schema:\n"
        "{\n"
        '  "narrative": "1 sentence with implication (risk/opportunity)",\n'
        '  "categories": ["<category_id>", "..."],\n'
        '  "vertical": "<vertical>",\n'
        '  "relevance": "High|Medium|Low",\n'
        '  "gaps": {"visibility_gap": bool, "trust_gap": bool, "ownership_gap": bool, "timing_gap": bool},\n'
        '  "recommendations": {"positioning": "...", "action": "...", "content_direction": "..."}\n'
        "}\n"
        "Constraints:\n"
        "- categories must be chosen from vertical categories.\n"
        "- If company is not mentioned but narrative is relevant, set visibility_gap=true.\n"
        "- If narrative is negative about the space, set trust_gap=true.\n"
    )

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    # Draft
    txt = await _call_openrouter(draft_model, messages)
    obj = None
    try:
        obj = json.loads(txt)
    except Exception:
        obj = None

    if obj is not None:
        ok, _ = _validate_schema(obj)
        if ok:
            await _set_cache(cache_coll, cache_key, obj)
            return obj

    # Premium fallback
    if allow_premium_fallback:
        try:
            txt2 = await _call_openai(fallback_model, messages)
            obj2 = json.loads(txt2)
            ok2, _ = _validate_schema(obj2)
            if ok2:
                await _set_cache(cache_coll, cache_key, obj2)
                return obj2
        except Exception as e:
            logger.warning("narrative_strategy_openai_fallback_failed", error=str(e))

    # Last resort: return deterministic base object
    await _set_cache(cache_coll, cache_key, base_obj)
    return base_obj


def _strip_code_fences(s: str) -> str:
    txt = (s or "").strip()
    if not txt.startswith("```"):
        return txt
    lines = txt.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _looks_like_json(s: str) -> bool:
    t = (s or "").strip()
    return (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]"))


async def _cached_json_call(*, namespace: str, payload: dict[str, Any], value_key: str, draft_model: str, messages: list[dict[str, str]]) -> Any:
    """
    Generic cached JSON call. Stores Mongo doc in narrative_strategy_llm_cache:
    { cache_key, updated_at, value: {<value_key>: <obj>} }
    """
    from app.services.mongodb import get_db

    db = get_db()
    cache_coll = db["narrative_strategy_llm_cache"]
    cache_key = _sha(json.dumps({"ns": namespace, "payload": payload}, sort_keys=True))

    cached = await _get_cache(cache_coll, cache_key)
    if cached and value_key in cached:
        return cached.get(value_key)

    txt = await _call_openrouter(draft_model, messages)
    txt = _strip_code_fences(txt)
    if not _looks_like_json(txt):
        raise ValueError("llm_non_json")
    obj = json.loads(txt)
    await _set_cache(cache_coll, cache_key, {value_key: obj})
    return obj


async def classify_posts_relevance(
    *,
    items: list[dict[str, Any]],
    daily_cap: int = 50,
) -> list[dict[str, Any]]:
    """
    LLM classifier to filter irrelevant Reddit posts before embeddings/clustering.

    Input item shape:
      { "id": "<string>", "title": "...", "top_comments": ["...","..."] }

    Output:
      [ { "id": "...", "is_relevant": bool, "reason": "..." }, ... ]
    """
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()

    # We cache by content, so repeated runs don't re-spend LLM calls.
    payload = {"items": [{"id": str(it.get("id") or ""), "title": it.get("title") or "", "top_comments": it.get("top_comments") or []} for it in items]}

    system = (
        "You are a strict classifier for a Narrative Intelligence system.\n"
        "Question: Does this Reddit item contain user experience, behavior, or opinion related to trading, investing, or brokers?\n"
        "KEEP only if the user expresses confusion, pain, decision-making, or behavior (losses, execution issues, charges, broker choice, FOMO/panic).\n"
        "REJECT if:\n"
        "- informational/macro/news without user reaction\n"
        "- memes/jokes/politics\n"
        "- THREAD CONTAINERS like weekly/bi-weekly advice threads, discussion threads (these are containers, not narratives)\n"
        "Return ONLY valid JSON array. Each element must match:\n"
        '{ \"id\": \"<id>\", \"is_relevant\": true/false, \"reason\": \"...\" }\n'
    )
    # keep compact to reduce cost; top 3 comments max, each trimmed
    compact = []
    for it in items[:120]:
        cid = str(it.get("id") or "")
        title = str(it.get("title") or "")[:220]
        cmts = it.get("top_comments") if isinstance(it.get("top_comments"), list) else []
        cmts2 = [str(c or "")[:240] for c in cmts[:3] if isinstance(c, str) and c.strip()]
        compact.append({"id": cid, "title": title, "top_comments": cmts2})

    user = json.dumps(compact, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return await _cached_json_call(namespace="filter:v1", payload=payload, value_key="rows", draft_model=draft_model, messages=messages)


async def derive_belief_only(*, cluster_items: list[dict[str, Any]]) -> str:
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"items": cluster_items}
    system = (
        "You are extracting a concrete user belief from multiple discussion snippets.\n"
        "Prompt: What are users collectively experiencing, doing, or struggling with?\n"
        "Rules:\n"
        "- Focus on behavior, pain, confusion, decision-making\n"
        "- Be concrete (what they do / avoid / ask / fear), not abstract\n"
        "- Avoid vague phrasing like: \"navigating complex markets\", \"seeking clarity\" (without saying about what)\n"
        "- Must be grounded in the provided text\n"
        "- Do NOT mention company names\n"
        "- Output MUST be exactly 1 sentence.\n"
        "Return ONLY valid JSON: {\"belief\":\"...\"}"
    )
    user = json.dumps(cluster_items[:12], ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="belief:v3", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("belief") or "").strip()


async def narrative_from_belief(*, belief: str, examples: list[str]) -> str:
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"belief": belief, "examples": examples[:5]}
    system = (
        "Convert a concrete user belief into ONE sharp, contrarian narrative INSIGHT sentence.\n"
        "Rules:\n"
        "- Must include: user behavior + specific problem + implication\n"
        "- Must be about user decision-making/pain (NOT just macro headlines).\n"
        "- Sound like an insight, not a recap.\n"
        "- Add contrarian edge: reveal a non-obvious behavior or hidden mechanism (challenge an assumption).\n"
        "  Examples:\n"
        "  - Not: \"Investors lack confidence\".\n"
        "  - Yes: \"Investors think they're diversified but are duplicating the same exposure across funds, so they keep seeking validation before acting\".\n"
        "- Do NOT use generic consulting language.\n"
        "- FORBIDDEN openings/phrases: \"users are discussing\", \"users discuss\", \"there is a trend\", \"highlights a broader trend\", \"navigating complexity\", \"navigating complex\", \"broader trend\".\n"
        "- Do NOT mention company names.\n"
        "- Avoid filler like: \"raises questions\", \"market participants\", \"increasingly\".\n"
        "Return ONLY valid JSON: {\"narrative\":\"...\"}"
    )
    user = json.dumps({"belief": belief, "examples": examples[:5]}, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="narrative:v4", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("narrative") or "").strip()


async def why_now_llm(*, narrative: str, belief: str, vertical: str) -> str:
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": narrative, "belief": belief, "vertical": vertical}
    system = (
        "You generate a timeliness/urgency line for a narrative positioning engine.\n"
        "Task: Explain why this narrative matters RIGHT NOW.\n"
        "Rules:\n"
        "- 1 sentence\n"
        "- Must connect to current conditions (volatility, participation shifts, recent events/coverage patterns) WITHOUT inventing specific facts.\n"
        "- If uncertain, speak in conditional/general terms (e.g., \"in periods of volatility\").\n"
        "- NO product/UX/feature ideas\n"
        "- No company names\n"
        "Return ONLY JSON: {\"why_now\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="why_now:v1", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("why_now") or "").strip()


async def title_llm(*, narrative: str, belief: str) -> str:
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": narrative, "belief": belief}
    system = (
        "Create a short UI title for a narrative card.\n"
        "Rules:\n"
        "- 4 to 6 words\n"
        "- Punchy, specific, headline-like (NOT a sentence)\n"
        "- NO generic phrasing\n"
        "- NO company names\n"
        "- Do NOT start with: \"users\", \"people\", \"investors\", \"there\"\n"
        "- Do NOT use verbs like: \"users are\", \"people are\", \"there is\"\n"
        "Return ONLY JSON: {\"title\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="title:v1", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("title") or "").strip()


async def broker_relevance_gate(*, belief: str, narrative: str) -> dict[str, Any]:
    """
    Decide if narrative is directly actionable for a broker platform.
    Reject macro/policy/news without trading/investing behavior.
    """
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"belief": belief, "narrative": narrative}
    system = (
        "You are the FINAL production relevance gate for a broker narrative POSITIONING system.\n"
        "Decide if this is DIRECTLY actionable for communication, positioning, and narrative ownership for the given vertical.\n"
        "\n"
        "Step 1) Set macro_topic=true if the core topic is macro/policy/geopolitics/currency/news commentary.\n"
        "Macro examples (MUST set macro_topic=true and is_broker_relevant=false):\n"
        "- INR/USD, rupee depreciation, RBI intervention debates\n"
        "- geopolitics/war impacting indices\n"
        "- GDP/inflation/policy headlines without a specific in-app trading/investing behavior\n"
        "\n"
        "Step 2) Only if macro_topic=false, decide vertical relevance.\n"
        "KEEP only if there is a clear user behavior / decision / pain that the company can address via messaging, education, trust-building, and narrative ownership.\n"
        "Examples:\n"
        "- placing trades, panic selling, FOMO, overtrading, hesitation\n"
        "- portfolio decisions with confusion or regret\n"
        "- trust concerns (fees, outages, execution quality) expressed as user experience\n"
        "Important constraints:\n"
        "- NO product, feature, UX, or tool suggestions\n"
        "- Do not mention recommendations, personalization, dashboards, or in-app changes\n"
        "- The reason must explain why the narrative matters for positioning/communication\n"
        "\n"
        "Return ONLY valid JSON:\n"
        '{ "is_broker_relevant": true/false, "macro_topic": true/false, "relevance": "High|Medium|Low", "signal_type": "white_space_opportunity|competitive|risk", "reason": "..." }'
    )
    user = json.dumps({"belief": belief, "narrative": narrative}, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="broker_gate:v4", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return {"is_broker_relevant": False, "macro_topic": False, "relevance": "Low", "signal_type": "risk", "reason": "gate_failed"}
    return {
        "is_broker_relevant": bool(obj.get("is_broker_relevant")),
        "macro_topic": bool(obj.get("macro_topic")),
        "relevance": str(obj.get("relevance") or "").strip() or "Low",
        "signal_type": str(obj.get("signal_type") or "").strip() or "risk",
        "reason": str(obj.get("reason") or "").strip(),
    }


async def validate_category_fit(*, narrative: str, category: dict[str, Any]) -> float:
    """
    Returns confidence 0..1 that narrative strongly belongs to category.
    """
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    cid = str(category.get("id") or "").strip()
    lab = str(category.get("label") or "").strip()
    desc = str(category.get("description") or "").strip()
    payload = {"narrative": narrative, "category": {"id": cid, "label": lab, "description": desc}}
    system = (
        "You are validating category precision.\n"
        "Prompt: Does this narrative strongly belong to this category?\n"
        "Return ONLY valid JSON: {\"confidence\": <number between 0 and 1>}."
    )
    user = json.dumps({"narrative": narrative, "category": payload["category"]}, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="cat_validate:v1", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    try:
        conf = float(obj.get("confidence")) if isinstance(obj, dict) else 0.0
    except Exception:
        conf = 0.0
    return max(0.0, min(1.0, conf))


async def company_strategy_llm(*, company: str, gap: str, narrative: str) -> str:
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"company": company, "gap": gap, "narrative": narrative}
    system = (
        "You are generating a company-specific communication strategy for narrative ownership.\n"
        "Given a gap type and a user-behavior narrative (narrative contains no company names), propose a 1-2 sentence COMMUNICATION strategy.\n"
        "Rules:\n"
        "- MUST be about positioning, messaging, and what to say\n"
        "- NO product/UX/feature suggestions\n"
        "- Avoid words like build, launch, feature, UX, flow, tool, dashboard, app redesign, add\n"
        "- NO generic PR fluff\n"
        "Return ONLY valid JSON: {\"strategy\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="company_strategy_comm:v1", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("strategy") or "").strip()


async def founder_mode_llm(*, narrative: str, belief: str) -> dict[str, Any]:
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": narrative, "belief": belief}
    system = (
        "You write Founder-mode comms: sharp, opinionated, and immediately usable.\n"
        "Tone: confident, specific, human (not corporate).\n"
        "Rules:\n"
        "- what_to_say must directly address the user's confusion/pain and name the tension\n"
        "- what_to_say must include one concrete framing or rule-of-thumb (no generic 'stay informed')\n"
        "- NO product/UX suggestions\n"
        "- Do not propose tools, features, or recommendations\n"
        "- No company names\n"
        "- Avoid corporate words: empower, enable, unlock, seamless, leverage\n"
        "Return ONLY JSON:\n"
        '{ "what_to_say": "1-2 lines", "channels": ["twitter","linkedin","community"], "example_post": "short natural post" }'
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="founder_mode:v2", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return {"what_to_say": "", "channels": [], "example_post": ""}
    channels = obj.get("channels") if isinstance(obj.get("channels"), list) else []
    return {
        "what_to_say": str(obj.get("what_to_say") or "").strip(),
        "channels": [str(c) for c in channels if isinstance(c, str)],
        "example_post": str(obj.get("example_post") or "").strip(),
    }


async def pr_mode_llm(*, narrative: str, belief: str) -> dict[str, Any]:
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": narrative, "belief": belief}
    system = (
        "You create PR-mode narrative ownership guidance.\n"
        "Rules:\n"
        "- Strategic but natural tone; no fluff\n"
        "- core_message must be the narrative the company wants to OWN (not a summary)\n"
        "- angle must differentiate (what we say that others aren't saying)\n"
        "- NO product/UX suggestions\n"
        "- Do not propose tools, features, or recommendations\n"
        "- No company names\n"
        "- Avoid vague PR filler: \"commitment\", \"leading platform\", \"customer-first\" unless tied to the belief\n"
        "Return ONLY JSON:\n"
        '{ "core_message": "...", "angle": "...", "content_examples": { "news_article": "...", "social_post": "...", "forum_response": "..." } }'
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="pr_mode:v2", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return {"core_message": "", "angle": "", "content_examples": {}}
    ce = obj.get("content_examples") if isinstance(obj.get("content_examples"), dict) else {}
    out_ce = {}
    for k in ("news_article", "social_post", "forum_response"):
        v = ce.get(k)
        if isinstance(v, str) and v.strip():
            out_ce[k] = v.strip()
    return {
        "core_message": str(obj.get("core_message") or "").strip(),
        "angle": str(obj.get("angle") or "").strip(),
        "content_examples": out_ce,
    }


async def relevance_reason_llm(*, narrative: str, vertical: str) -> str:
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": narrative, "vertical": vertical}
    system = (
        "Write a short relevance_reason for a narrative positioning engine.\n"
        "Rules:\n"
        "- Explain why this matters for the given vertical's communication/positioning\n"
        "- NO product/feature/UX/tool suggestions\n"
        "- Do not mention recommendations, personalization, dashboards, or in-app changes\n"
        "Return ONLY JSON: {\"relevance_reason\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="relevance_reason:v1", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("relevance_reason") or "").strip()

def validate_recommendation_obj(obj: dict[str, str]) -> tuple[bool, str]:
    action = (obj.get("action") or "").lower()
    content_direction = (obj.get("content_direction") or "").lower()
    bad = ["create content", "improve ux", "improve user experience", "increase awareness"]
    if any(b in action for b in bad) or any(b in content_direction for b in bad):
        return False, "generic_action"
    if any(x in content_direction for x in ("blog post", "blog posts", "youtube", "tweet", "thread", "videos")):
        return False, "marketing_content_direction"
    if len((obj.get("action") or "").strip()) < 25:
        return False, "action_too_short"
    return True, "ok"


def _contains_company_name(text: str, banned: list[str]) -> bool:
    s = (text or "").lower()
    for b in banned:
        bb = (b or "").strip().lower()
        if not bb:
            continue
        if re.search(r"\b" + re.escape(bb) + r"\b", s):
            return True
    return False


async def derive_belief_and_narrative(
    *,
    cluster_posts: list[dict[str, Any]],
) -> dict[str, str]:
    """
    LLM: belief + narrative grounded in cluster input. No company names.
    Input posts: [{"title": "...", "comments": ["...", ...]}, ...]
    Output: {"belief": "...", "narrative": "..."}
    """
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()

    payload = {"posts": cluster_posts}

    system = (
        "You are analyzing multiple user discussions.\n"
        "Task:\n"
        "1) Identify what users are collectively experiencing or doing\n"
        "2) Focus on behavior, pain, frustration\n"
        "3) Do NOT introduce new assumptions\n"
        "Rules:\n"
        "- Must be grounded in the input\n"
        "- No company names\n"
        "Return ONLY valid JSON:\n"
        '{ "belief": "1 sentence describing user behavior", "narrative": "1 sentence describing broader implication" }'
    )
    user = json.dumps(cluster_posts[:10], ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="belief_narrative:v1", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        raise ValueError("belief_narrative_not_object")
    return {"belief": str(obj.get("belief") or "").strip(), "narrative": str(obj.get("narrative") or "").strip()}


async def map_categories_llm(
    *,
    narrative: str,
    categories: list[dict[str, Any]],
) -> list[str]:
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()

    cat_lines = []
    valid_ids: set[str] = set()
    for c in categories or []:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or "").strip()
        lab = str(c.get("label") or "").strip()
        desc = str(c.get("description") or "").strip()
        if cid and lab:
            valid_ids.add(cid)
            cat_lines.append(f"- {cid}: {lab} — {desc}")

    payload = {"narrative": narrative, "cats": cat_lines}
    system = (
        "You are mapping a business narrative to a configured category taxonomy.\n"
        "Rules:\n"
        "- semantic matching only\n"
        "- allow multiple\n"
        "- if unclear return []\n"
        "Return ONLY valid JSON array of category ids."
    )
    user = f"Narrative:\n{narrative}\n\nCategories:\n" + ("\n".join(cat_lines) if cat_lines else "(none)")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="catmap:v1", payload=payload, value_key="ids", draft_model=draft_model, messages=messages)
    if not isinstance(obj, list):
        return []
    out = []
    for x in obj:
        s = str(x or "").strip()
        if s and s in valid_ids:
            out.append(s)
    # dedup preserve order
    seen = set()
    uniq = []
    for s in out:
        if s not in seen:
            uniq.append(s)
            seen.add(s)
    return uniq


async def recommend_actions_llm(
    *,
    narrative: str,
    gaps: dict[str, bool],
    vertical: str,
) -> dict[str, str]:
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": narrative, "gaps": gaps, "vertical": vertical}

    system = (
        "You are a senior strategist.\n"
        "Given a narrative (user behavior based) and detected gaps, produce specific actionable recommendations.\n"
        "Rules:\n"
        "- be specific, actionable, and aligned with the narrative\n"
        "- recommendations MUST be product/UX/feature/ops oriented (in-app changes, reliability, flows, decision support)\n"
        "- content_direction can mention in-product education (tooltips, explainers inside the app), not generic marketing.\n"
        "- FORBIDDEN: \"create content\", \"improve UX\", \"increase awareness\", generic blog/video plans.\n"
        "- no stock recommendations\n"
        "Return ONLY valid JSON:\n"
        '{ "positioning": "...", "action": "...", "content_direction": "..." }'
    )
    user = json.dumps({"vertical": vertical, "narrative": narrative, "gaps": gaps}, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="recs:v2", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return {"positioning": "", "action": "", "content_direction": ""}
    return {
        "positioning": str(obj.get("positioning") or "").strip(),
        "action": str(obj.get("action") or "").strip(),
        "content_direction": str(obj.get("content_direction") or "").strip(),
    }

