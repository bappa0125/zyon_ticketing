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


# Titles that look like keyword stacks / SEO / thread labels (reject or regenerate)
_TITLE_JUNK_RE = re.compile(
    r"\b(seek|seeking|identify|identifying|discuss|discussion|discussing|various|frequently|"
    r"empowering|topics?|portfolios?)\b",
    re.I,
)


_ABSTRACT_TITLE_RE = re.compile(
    r"\b(rewards?|celebrates?|embraces?|journey|path to|power of|wisdom|"
    r"conviction|faith|hope|matters most|beats|wins|triumph|glory)\b",
    re.I,
)


def is_abstract_title(title: str) -> bool:
    """Motivational / slogan titles without concrete behavior (e.g. 'Volatility Rewards Conviction')."""
    t = (title or "").strip()
    if len(t) < 8:
        return False
    if _ABSTRACT_TITLE_RE.search(t):
        return True
    # Verb pattern: abstract X for Y (no actor mistake)
    if re.search(r"\b(volatility|markets?|uncertainty)\s+\w+\s+(rewards?|punishes?|favors?)\b", t, re.I):
        return True
    return False


def is_low_quality_title(title: str) -> bool:
    """True if title should be dropped or rewritten (robotic / keyword-like). Max 6 words."""
    t = (title or "").strip()
    if len(t) < 6:
        return True
    words = re.sub(r"[/]", " ", t).split()
    wc = len([w for w in words if w.strip()])
    if wc < 3 or wc > 6:
        return True
    if _TITLE_JUNK_RE.search(t):
        return True
    tl = t.lower()
    if any(
        x in tl
        for x in (
            "discussion around",
            "discussion about",
            "users are",
            "people are",
            "informed decisions",
            "helping users",
        )
    ):
        return True
    # keyword stacking: mostly 1–2 char syllables without clear phrase
    short = sum(1 for w in words if len(re.sub(r"[^a-z0-9]", "", w.lower())) <= 2)
    if wc >= 5 and short / max(wc, 1) >= 0.55:
        return True
    return False


_GENERIC_LANGUAGE_RE = re.compile(
    r"\b(users are|people are|discussion about|discussions about|various topics?|empowering users|helping users)\b",
    re.I,
)

_WHY_IT_MATTERS_FLUFF_RE = re.compile(
    r"\b(important|critical(?:ly)?|critical for|helps?\s|helpful|it is important|essential to\b|valuable to\b|"
    r"clear insights|insights are)\b",
    re.I,
)

_BUSINESS_IMPACT_VAGUE_RE = re.compile(
    r"\b(impact|important|critical(?:ly)?|helps?\b|helpful|valuable|essential|insights?)\b",
    re.I,
)

_BUSINESS_METRIC_RE = re.compile(
    r"\b(churn|retention|retain|lifetime value|ltv|revenue|commissions?|aum|wallet share|"
    r"activation|conversion|arpu|cac|support load|ticket volume|sip cancellations?|cancellations?)\b",
    re.I,
)

_WHAT_TO_SAY_WEAK_RE = re.compile(
    r"^(need |want |get |try |contact |discover |learn more|find out|don't hesitate|feel free|please |"
    r"we invite|reach out)\b",
    re.I,
)


def contains_generic_language(text: str) -> bool:
    """Banned filler — triggers LLM rewrite."""
    s = (text or "").strip().lower()
    if not s:
        return False
    if re.search(r"\bvarious\b", s):
        return True
    return bool(_GENERIC_LANGUAGE_RE.search(s))


def is_low_quality_why_it_matters(text: str) -> bool:
    """Fluff advisory tone — rewrite or drop."""
    t = (text or "").strip()
    if len(t) < 28:
        return True
    if _WHY_IT_MATTERS_FLUFF_RE.search(t):
        return True
    if contains_generic_language(t):
        return True
    return False


def is_low_quality_what_to_say(text: str) -> bool:
    """Questions, polite CTAs, marketing — rewrite or drop."""
    t = (text or "").strip()
    if not t or len(t) < 14:
        return True
    if "?" in t:
        return True
    if _WHAT_TO_SAY_WEAK_RE.search(t):
        return True
    if contains_generic_language(t):
        return True
    return False


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


_OPPORTUNITY_GENERIC_RE = re.compile(
    r"\b(first mover advantage|open narrative|strategically open|white\s*space|no one owns|whoever owns this|"
    r"own this narrative|become the voice of|differentiation|differentiate|strategic(?:ally)?|advantage)\b",
    re.I,
)


async def generate_opportunity_line(*, narrative: str, companies: list[str]) -> str:
    """
    1 sharp sentence explaining WHY a narrative is open (white space) in a narrative-specific way.
    Must avoid generic consulting phrases like "first mover advantage".
    Returns empty string on failure or if output is generic.
    """
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": (narrative or "")[:900], "companies": [str(c) for c in (companies or []) if isinstance(c, str)][:20]}

    system = (
        "You are writing a positioning opportunity insight line for a Narrative Decision Engine.\n"
        "Task: explain why this narrative is strategically open in EXACTLY 1 sharp sentence.\n"
        "Hard rules:\n"
        "- DO NOT use generic phrases like: first mover advantage, open narrative, strategically open, white space, nobody owns, differentiate.\n"
        "- Be specific to the user behavior + market messaging gap.\n"
        "- No company names.\n"
        "- No product/UX/feature suggestions.\n"
        "Return ONLY JSON: {\"opportunity_line\":\"...\"}\n"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        obj = await _cached_json_call(
            namespace="opportunity_line:v1",
            payload=payload,
            value_key="obj",
            draft_model=draft_model,
            messages=messages,
        )
    except Exception:
        return ""
    if not isinstance(obj, dict):
        return ""
    line = str(obj.get("opportunity_line") or "").strip()
    # Basic hygiene: single sentence, non-generic.
    if not line or len(line) < 35:
        return ""
    if line.count("?") > 0:
        return ""
    if _OPPORTUNITY_GENERIC_RE.search(line):
        return ""
    if contains_generic_language(line):
        return ""
    # Trim to one sentence max if model over-produces.
    m = re.search(r"[.!?](\s|$)", line)
    if m and m.end() >= 20:
        line = line[: m.end()].strip()
    return line


async def closest_competitor_llm(*, narrative: str, competitors: list[str]) -> dict[str, str]:
    """
    Pick the competitor closest to owning the narrative (when heuristics are unclear).
    Returns: {"name": "...", "reason": "..."} or empty strings on failure.
    """
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    comps = [str(c).strip() for c in (competitors or []) if isinstance(c, str) and str(c).strip()]
    payload = {"narrative": (narrative or "")[:900], "competitors": comps[:20]}
    if not payload["narrative"] or len(comps) < 2:
        return {"name": "", "reason": ""}

    system = (
        "You are a competitive narrative analyst.\n"
        "Task: choose which competitor is closest to owning this narrative and why.\n"
        "Rules:\n"
        "- Output exactly 1 competitor from the provided list.\n"
        "- Reason must be 1 line, concrete (what they already signal), and must mention the gap (what they miss).\n"
        "- No generic phrases like: first mover advantage, white space, open narrative, strategically open.\n"
        "- No product/feature suggestions.\n"
        "Return ONLY JSON: {\"name\":\"<competitor>\",\"reason\":\"<one line>\"}\n"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        obj = await _cached_json_call(
            namespace="closest_competitor:v1",
            payload=payload,
            value_key="obj",
            draft_model=draft_model,
            messages=messages,
        )
    except Exception:
        return {"name": "", "reason": ""}
    if not isinstance(obj, dict):
        return {"name": "", "reason": ""}
    name = str(obj.get("name") or "").strip()
    reason = str(obj.get("reason") or "").strip()
    if not name or name not in comps:
        return {"name": "", "reason": ""}
    if not reason or len(reason) < 18:
        return {"name": name, "reason": ""}
    if _OPPORTUNITY_GENERIC_RE.search(reason) or contains_generic_language(reason):
        return {"name": name, "reason": ""}
    # keep reason to one sentence
    m = re.search(r"[.!?](\s|$)", reason)
    if m and m.end() >= 20:
        reason = reason[: m.end()].strip()
    return {"name": name, "reason": reason}


async def generate_distribution_strategy(*, narrative: str) -> list[str]:
    """
    Returns up to 3 concrete distribution bullets (platform + format).
    Output must be a JSON array of strings.
    """
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": (narrative or "")[:900]}
    if not payload["narrative"].strip():
        return []

    system = (
        "You are a comms operator.\n"
        "Task: Where should this narrative be pushed? Return 3 bullets max.\n"
        "Rules:\n"
        "- Output ONLY valid JSON array of strings.\n"
        "- Max 3 bullets.\n"
        "- Each bullet must include a platform and a format (e.g., Twitter thread, LinkedIn founder post, PR/earned media article, community AMA).\n"
        "- No generic bullets like \"social media\" or \"content marketing\".\n"
        "- No company names. No speculation. No fake data.\n"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        rows = await _cached_json_call(
            namespace="distribution_strategy:v1",
            payload=payload,
            value_key="rows",
            draft_model=draft_model,
            messages=messages,
        )
    except Exception:
        return []
    if not isinstance(rows, list):
        return []

    out: list[str] = []
    for x in rows:
        s = str(x or "").strip()
        if not s:
            continue
        if contains_generic_language(s):
            continue
        if re.search(r"\b(social media|content marketing|blog post|post on social|go viral)\b", s, re.I):
            continue
        # must mention at least one known platform-ish term
        if not re.search(r"\b(twitter|x\b|linkedin|pr\b|earned media|community|reddit|newsletter|webinar|podcast)\b", s, re.I):
            continue
        out.append(s)
        if len(out) >= 3:
            break
    # dedup keep order
    return _dedup_keep_order(out)[:3]


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
        "Extract ONE sentence: the non-obvious belief behind the discussion.\n"
        "Rules:\n"
        "- Must include tension, mistake, or what users are getting WRONG (not a neutral description).\n"
        "- Prefer: distrust of own judgment, hidden duplication, validation-seeking, fear-driven timing, confusion framed as a wrong assumption.\n"
        "- Be concrete; no abstract filler.\n"
        "- FORBIDDEN openings/phrases: \"users are discussing\", \"users are seeking\", \"users frequently\", \"people are\", \"there is a trend\".\n"
        "- Do NOT mention company names.\n"
        "- Ground in the snippets.\n"
        "Return ONLY JSON: {\"belief\":\"...\"}"
    )
    user = json.dumps(cluster_items[:12], ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="belief:v6", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
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
        "- Reveal a hidden pattern or consequence (not a recap of activity).\n"
        "- FORBIDDEN openings/phrases: \"users are discussing\", \"users frequently\", \"users discuss\", \"users are seeking\", \"people are\", \"discussion around\", \"discussion about\", \"various topics\", \"there is a trend\", \"highlights a broader trend\", \"navigating complexity\", \"navigating complex\", \"broader trend\".\n"
        "- Do NOT mention company names.\n"
        "- Avoid filler like: \"raises questions\", \"market participants\", \"increasingly\".\n"
        "Return ONLY valid JSON: {\"narrative\":\"...\"}"
    )
    user = json.dumps({"belief": belief, "examples": examples[:5]}, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="narrative:v7", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
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
    obj = await _cached_json_call(namespace="why_now:v2", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("why_now") or "").strip()


async def why_it_matters_llm(*, narrative: str, belief: str) -> str:
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": narrative, "belief": belief}
    system = (
        "Explain the risk or consequence of this behavior in one sharp sentence.\n"
        "Rules:\n"
        "- Name a concrete downside: false diversification, hidden exposure, churn, reactive decisions, no conviction.\n"
        "- No questions. No advisory fluff.\n"
        "- FORBIDDEN words/phrases: important, critical, helps, helpful, valuable insight, empowering, "
        "informed decisions, users are, people are, discussion about, various.\n"
        "- No company names.\n"
        "Return ONLY JSON: {\"why_it_matters\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="why_it_matters:v3", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("why_it_matters") or "").strip()


async def business_impact_llm(*, narrative: str, belief: str, vertical: str) -> str:
    """Broker-facing business consequence (one sentence, CFO-level)."""
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": narrative, "belief": belief, "vertical": vertical}
    system = (
        "Explain the direct business impact in terms of revenue, churn, or retention.\n"
        "Tone: measurable, CFO-level, concrete.\n"
        "Rules:\n"
        "- EXACTLY 1 sentence.\n"
        "- Must reference at least one metric concept (e.g., churn/retention/LTV/AUM/revenue/commissions/support load).\n"
        "- Do NOT use vague words: impact, important, helps, valuable, essential, insights.\n"
        "- No questions. No company names.\n"
        "Return ONLY JSON: {\"business_impact\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="business_impact:v1", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("business_impact") or "").strip()


def is_low_quality_business_impact(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 24:
        return True
    if "?" in t:
        return True
    if contains_generic_language(t):
        return True
    if _BUSINESS_IMPACT_VAGUE_RE.search(t):
        return True
    if not _BUSINESS_METRIC_RE.search(t):
        return True
    return False


async def rewrite_business_impact_llm(*, narrative: str, belief: str, vertical: str, bad_line: str) -> str:
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": narrative, "belief": belief, "vertical": vertical, "bad_line": bad_line}
    system = (
        "Rewrite the business impact into 1 CFO-level sentence.\n"
        "Rules:\n"
        "- Must reference revenue/churn/retention/LTV/AUM/commissions/support load.\n"
        "- Do NOT use vague words: impact, important, helps, valuable, essential, insights.\n"
        "- No questions. No company names.\n"
        "Return ONLY JSON: {\"business_impact\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(
        namespace="business_impact_rewrite:v1",
        payload=payload,
        value_key="obj",
        draft_model=draft_model,
        messages=messages,
    )
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("business_impact") or "").strip()


async def sharpen_title_concrete_llm(*, title: str, narrative: str, belief: str) -> str:
    """Final pass: replace abstract / slogan titles with concrete behavioral insight."""
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"title": title, "narrative": narrative, "belief": belief}
    system = (
        "Make this title more concrete and behavioral. Expose the mistake or wrong assumption.\n"
        "Replace the given title entirely.\n"
        "Rules:\n"
        "- EXACTLY 4 to 6 words. Title Case.\n"
        "- No slogans like 'Volatility Rewards Conviction' — name behavior or tension.\n"
        "- FORBIDDEN: seek, identify, discuss, various, rewards (as empty praise), journey, wisdom.\n"
        "- NO company names.\n"
        "Return ONLY JSON: {\"title\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="title_concrete:v1", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("title") or "").strip()


async def rewrite_why_it_matters_llm(*, narrative: str, belief: str, bad_line: str) -> str:
    """Replace fluffy why_it_matters with a sharp consequence sentence."""
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": narrative, "belief": belief, "bad_line": bad_line}
    system = (
        "Explain the risk or consequence of this behavior in one sharp sentence.\n"
        "Replace the bad line entirely.\n"
        "Rules:\n"
        "- Concrete downside only — no \"important\", \"critical\", \"helps\", marketing, or generic advisory tone.\n"
        "- No questions. No company names.\n"
        "Return ONLY JSON: {\"why_it_matters\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="why_it_matters_rewrite:v1", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("why_it_matters") or "").strip()


async def what_to_say_one_liner_llm(*, narrative: str, belief: str, founder_what_to_say: str) -> str:
    """Single sharp line for UI — derived from founder intent, instantly usable."""
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": narrative, "belief": belief, "founder_draft": founder_what_to_say}
    system = (
        "Write a bold one-line statement exposing the mistake or insight. Founder voice.\n"
        "Rules:\n"
        "- MUST NOT be a question (no question mark).\n"
        "- MUST NOT be polite CTA, soft ask, or marketing tone.\n"
        "- Name the wrong assumption or hidden mechanism — provocative but credible.\n"
        "- FORBIDDEN: need/want/get/try/contact/discover/learn more at start; "
        "\"empowering\", \"helping users\", \"informed decisions\", \"users are\", \"people are\", \"various\", "
        "\"discussion around\", \"discussion about\".\n"
        "- No company names.\n"
        "Return ONLY JSON: {\"what_to_say\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="what_to_say_line:v4", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("what_to_say") or "").strip()


async def rewrite_what_to_say_founder_llm(*, narrative: str, belief: str, bad_line: str) -> str:
    """Replace weak what_to_say (question/CTA) with founder punch."""
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": narrative, "belief": belief, "bad_line": bad_line}
    system = (
        "Write a bold one-line statement exposing the mistake or insight. No questions.\n"
        "Replace the bad line entirely. No polite CTA or marketing tone.\n"
        "No company names.\n"
        "Return ONLY JSON: {\"what_to_say\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="what_to_say_rewrite:v1", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("what_to_say") or "").strip()


async def title_llm(*, narrative: str, belief: str, emerging: bool = False) -> str:
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": narrative, "belief": belief, "emerging": emerging}
    emerging_hint = ""
    if emerging:
        emerging_hint = (
            "This is an EMERGING signal: title must feel like early insight (behavior forming), "
            "e.g. \"Early Signs of Validation Dependency\" or \"Struggle with Allocation Confidence\" — "
            "not noise, not keyword salad.\n"
        )
    system = (
        "Create a sharp 4–6 word investor insight title — behavior or tension. No generic filler.\n"
        + emerging_hint
        + "Rules:\n"
        "- EXACTLY 4 to 6 words. Never more than 6 words.\n"
        "- Clear human insight — NOT keyword stacking or SEO-style stacks.\n"
        "- Headline style; Title Case; punchy.\n"
        "- FORBIDDEN anywhere: seek, seeking, identify, discuss, discussion, various, frequently, topics, feedback (as filler).\n"
        "- Do NOT start with: Users, People, Investors, There, Discussion.\n"
        "- NO company names.\n"
        "Return ONLY JSON: {\"title\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="title:v4", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("title") or "").strip()


async def emerging_insight_title_llm(*, narrative: str, belief: str) -> str:
    """
    All emerging narratives: sharp 4–6 word insight title (behavior / tension), not noise.
    """
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"narrative": narrative, "belief": belief}
    system = (
        "Convert this into a sharp 4–6 word investor insight. No generic words. "
        "No verbs like 'seek', 'identify', or 'discuss'.\n"
        "Rules:\n"
        "- EXACTLY 4 to 6 words. Never more than 6.\n"
        "- Clear human insight — behavior or tension — not keyword stacking.\n"
        "- FORBIDDEN: seek, identify, discuss, various, frequently, users, people, discussion.\n"
        "- Title Case; NO company names.\n"
        "Return ONLY JSON: {\"title\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="emerging_title:v2", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("title") or "").strip()


async def rewrite_title_insight_llm(*, bad_title: str, narrative: str, belief: str, emerging: bool) -> str:
    """Fallback when primary title fails quality checks."""
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"bad_title": bad_title, "narrative": narrative, "belief": belief, "emerging": emerging}
    hint = "Emerging signal — " if emerging else ""
    system = (
        f"{hint}"
        "Convert this into a sharp 4–6 word investor insight. No generic words. "
        "No verbs like 'seek' or 'identify'. Replace the bad title completely — do not repeat its junk words.\n"
        "Rules:\n"
        "- EXACTLY 4 to 6 words. Never more than 6.\n"
        "- Clear human insight — not keyword stacking.\n"
        "- FORBIDDEN: seek, identify, discuss, various, frequently, users, people, discussion.\n"
        "- Title Case; NO company names.\n"
        "Return ONLY JSON: {\"title\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="title_rewrite:v2", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("title") or "").strip()


async def sanitize_belief_narrative_generic_llm(*, belief: str, narrative: str) -> dict[str, str]:
    """Remove forbidden generic phrasing; keep one sentence each."""
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {"belief": belief, "narrative": narrative}
    system = (
        "Rewrite belief and narrative to remove generic filler.\n"
        "FORBIDDEN phrases: \"users are\", \"people are\", \"discussion about\", \"various\", \"empowering users\", \"helping users\".\n"
        "Replace with direct behavioral statements and tension-driven insight.\n"
        "Rules:\n"
        "- belief: ONE sentence, concrete tension or mistake.\n"
        "- narrative: ONE sentence, behavior + implication.\n"
        "- No company names.\n"
        "Return ONLY JSON: {\"belief\":\"...\",\"narrative\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="sanitize_generic:v1", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
    if not isinstance(obj, dict):
        return {"belief": belief, "narrative": narrative}
    return {
        "belief": str(obj.get("belief") or "").strip() or belief,
        "narrative": str(obj.get("narrative") or "").strip() or narrative,
    }


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
        "You write Founder-mode comms: sharp, opinionated, slightly contrarian.\n"
        "Tone: real founder POV — punch through the pain, not a brochure.\n"
        "Rules:\n"
        "- what_to_say: 1-2 lines that NAME the mistake or tension + a concrete reframe.\n"
        "- MUST NOT be only a question; prefer declarative punches. No question marks in what_to_say.\n"
        "- Hit pain directly; no corporate tone.\n"
        "- example_post: conversational Twitter/LinkedIn voice; no jargon.\n"
        "- NO product/UX/feature suggestions.\n"
        "- No company names.\n"
        "- FORBIDDEN: empower, enabling, seamless, leverage, \"helping users\", \"informed decisions\", \"users are seeking\".\n"
        "Return ONLY JSON:\n"
        '{ "what_to_say": "1-2 lines", "channels": ["twitter","linkedin","community"], "example_post": "short natural post" }'
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="founder_mode:v5", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
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
        "You create PR-mode narrative ownership: clear stance vs the market.\n"
        "Rules:\n"
        "- core_message: a sharp claim to OWN (not a summary). Take a position.\n"
        "- angle: how this differs from generic fintech/PR noise (competitors stay vague; we name the mechanism).\n"
        "- content_examples: usable lines; sound human, not press-release.\n"
        "- NO product/UX suggestions.\n"
        "- No company names.\n"
        "- FORBIDDEN phrases: \"empowering users\", \"helping users\", \"informed decisions\", \"commitment to\", \"leading platform\".\n"
        "Return ONLY JSON:\n"
        '{ "core_message": "...", "angle": "...", "content_examples": { "news_article": "...", "social_post": "...", "forum_response": "..." } }'
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="pr_mode:v3", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
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
        "Write a short relevance_reason: why communicators should care (positioning stakes).\n"
        "- NO product/feature/UX/tool suggestions.\n"
        "- FORBIDDEN: \"empowering\", \"helping users\", \"informed decisions\".\n"
        "Return ONLY JSON: {\"relevance_reason\":\"...\"}"
    )
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(namespace="relevance_reason:v2", payload=payload, value_key="obj", draft_model=draft_model, messages=messages)
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


# ============================
# Narrative tag classification
# ============================


def _compact_tag_defs(tags: dict[str, Any], *, max_examples: int = 2) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tid, meta in (tags or {}).items():
        if not isinstance(tid, str) or not tid.strip():
            continue
        m = meta if isinstance(meta, dict) else {}
        ex = m.get("examples") if isinstance(m.get("examples"), list) else []
        out.append(
            {
                "id": tid.strip(),
                "definition": str(m.get("definition") or "").strip(),
                "include_when": [str(x) for x in (m.get("include_when") or []) if isinstance(x, str)][:6],
                "exclude_when": [str(x) for x in (m.get("exclude_when") or []) if isinstance(x, str)][:6],
                "examples": [str(x) for x in ex if isinstance(x, str)][:max_examples],
                "parents": [str(x) for x in (m.get("parents") or []) if isinstance(x, str)][:6],
            }
        )
    out.sort(key=lambda x: x["id"])
    return out


def _dedup_keep_order(xs: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in xs:
        s = str(x or "").strip()
        if not s or s in seen:
            continue
        out.append(s)
        seen.add(s)
    return out


def _get_all_parents(tag: str, parent_map: dict[str, list[str]]) -> set[str]:
    """
    Return transitive closure of parents for tag. Assumes parent_map already validated (acyclic, known parents).
    """
    start = (tag or "").strip()
    if not start:
        return set()
    out: set[str] = set()
    stack = list(parent_map.get(start, []))
    while stack:
        p = stack.pop()
        if p in out:
            continue
        out.add(p)
        stack.extend(parent_map.get(p, []))
    return out


def _resolve_overlap(tags: list[str], parent_map: dict[str, list[str]]) -> list[str]:
    """
    Remove any selected tag that is a (transitive) parent of another selected tag.
    Keeps the most specific tags only.
    """
    picked = _dedup_keep_order(tags)
    parent_sets: dict[str, set[str]] = {t: _get_all_parents(t, parent_map) for t in picked}
    to_drop: set[str] = set()
    for a in picked:
        for b in picked:
            if a == b:
                continue
            # drop a if it is a parent of b
            if a in parent_sets.get(b, set()):
                to_drop.add(a)
    return [t for t in picked if t not in to_drop]


async def validate_domain_tag_fit(*, vertical: str, domain_tag: dict[str, Any], narrative: str, belief: str) -> float:
    """
    Returns score 0..1: does this narrative strongly belong to this domain tag?
    """
    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()
    payload = {
        "vertical": str(vertical or "").strip().lower(),
        "domain_tag": domain_tag,
        "narrative": narrative,
        "belief": belief,
    }
    system = (
        "You are validating DOMAIN tag precision for a narrative decision engine.\n"
        "Return ONLY valid JSON: {\"score\": <number between 0 and 1>}.\n"
        "Score meaning:\n"
        "- 0.0 = clearly does NOT belong\n"
        "- 1.0 = clearly belongs\n"
        "Do not guess. If unclear, score <= 0.5.\n"
    )
    user = json.dumps(
        {
            "vertical": payload["vertical"],
            "domain_tag": domain_tag,
            "narrative": (narrative or "")[:600],
            "belief": (belief or "")[:400],
        },
        ensure_ascii=False,
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    obj = await _cached_json_call(
        namespace="narrative_domain_fit:v1",
        payload=payload,
        value_key="obj",
        draft_model=draft_model,
        messages=messages,
    )
    try:
        score = float(obj.get("score")) if isinstance(obj, dict) else 0.0
    except Exception:
        score = 0.0
    return max(0.0, min(1.0, score))


async def classify_narrative_tags(
    *,
    vertical: str,
    narrative: str,
    belief: str,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Config-driven dual-layer tagging:
    - behavior_tag (mandatory, single)
    - domain_tags (0-2), proposed by LLM then validated per-tag (>=0.6)
    - overlap resolution via domain_tag.parents (drop broader parents)
    """
    from app.core.narrative_tags_config import get_narrative_tags_config

    cfg = get_narrative_tags_config()
    v = (vertical or "").strip().lower() or "broker"
    behavior_cfg = cfg.behavior_tags(v)
    domain_cfg = cfg.domain_tags(v)
    valid_behavior = set(behavior_cfg.keys())
    valid_domain = set(domain_cfg.keys())
    fallback_behavior = "unclassified_behavior"

    llm_cfg = _cfg_llm()
    draft_model = (llm_cfg.get("draft_model") or "deepseek/deepseek-chat").strip()

    compact_behavior = _compact_tag_defs(behavior_cfg, max_examples=2)
    compact_domain = _compact_tag_defs(domain_cfg, max_examples=1)

    payload = {
        "vertical": v,
        "narrative": (narrative or "")[:800],
        "belief": (belief or "")[:600],
        "evidence_urls": [str(e.get("url") or "") for e in (evidence or [])[:6] if isinstance(e, dict) and e.get("url")],
    }

    system = (
        "You are tagging a narrative for a Narrative Decision Engine.\n"
        "You MUST choose tags only from the provided definitions.\n"
        "Return ONLY valid JSON.\n"
        "Rules:\n"
        "- Select EXACTLY 1 behavior_tag.\n"
        "- Propose 0–2 domain_tags (optional). If unclear, return [].\n"
        "- Do NOT invent new tags. Do NOT return free-text categories.\n"
        "- Behavior must reflect user psychology/action.\n"
        "- Domain must reflect product/system area; do NOT guess.\n"
    )
    user = json.dumps(
        {
            "vertical": v,
            "behavior_tag_definitions": compact_behavior,
            "domain_tag_definitions": compact_domain,
            "narrative": (narrative or "").strip(),
            "belief": (belief or "").strip(),
            "evidence": [{"title": str(e.get("title") or "")[:180], "snippet": str(e.get("snippet") or "")[:220]} for e in (evidence or [])[:4] if isinstance(e, dict)],
            "output_schema": {"behavior_tag": "<one id>", "domain_tags": ["<id>", "<id>"]},
        },
        ensure_ascii=False,
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    obj = await _cached_json_call(
        namespace="narrative_tags:v1",
        payload=payload,
        value_key="obj",
        draft_model=draft_model,
        messages=messages,
    )

    proposed_behavior = ""
    proposed_domains: list[str] = []
    if isinstance(obj, dict):
        proposed_behavior = str(obj.get("behavior_tag") or "").strip()
        dom = obj.get("domain_tags")
        if isinstance(dom, list):
            proposed_domains = [str(x or "").strip() for x in dom if str(x or "").strip()]
    proposed_domains = proposed_domains[:2]

    rejected: list[str] = []

    # Normalize behavior
    behavior_tag = proposed_behavior if proposed_behavior in valid_behavior else ""
    if not behavior_tag:
        if proposed_behavior:
            rejected.append(f"invalid_behavior:{proposed_behavior}")
        behavior_tag = fallback_behavior

    # Validate domains per-tag
    scored: list[tuple[float, str]] = []
    for d in proposed_domains:
        if d not in valid_domain:
            rejected.append(f"invalid_domain:{d}")
            continue
        score = await validate_domain_tag_fit(
            vertical=v,
            domain_tag={"id": d, **(domain_cfg.get(d) if isinstance(domain_cfg.get(d), dict) else {})},
            narrative=narrative,
            belief=belief,
        )
        if score >= 0.6:
            scored.append((score, d))
        else:
            rejected.append(f"domain_below_0_6:{d}:{score:.2f}")

    scored.sort(key=lambda x: x[0], reverse=True)
    kept = [d for _, d in scored][:2]

    # Overlap resolution using parents graph
    parent_map = {k: list((domain_cfg.get(k) or {}).get("parents") or []) for k in domain_cfg.keys() if isinstance(domain_cfg.get(k), dict)}
    kept2 = _resolve_overlap(kept, parent_map)
    if kept2 != kept:
        dropped = [x for x in kept if x not in kept2]
        rejected.extend([f"dropped_parent_overlap:{x}" for x in dropped])
    kept2 = kept2[:2]

    confidence_scores = {
        "domain": {d: float(s) for s, d in scored},
    }

    return {
        "behavior_tag": behavior_tag,
        "domain_tags": kept2,
        "debug": {
            "behavior_tag_selected": behavior_tag,
            "domain_tags_selected": kept2,
            "rejected_tags": rejected,
            "confidence_scores": confidence_scores,
        },
    }

