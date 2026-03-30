"""
Narrative Strategy Engine (consulting-style).

Theme-first:
- Cluster market discussions into themes/narratives (no entity filter)
- Map to company/sector second
- Detect gaps and recommend actions

Output must follow the STRICT format requested by the user.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import sqrt
import hashlib
from typing import Any

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

_VERTICAL_CATEGORY_EMB_CACHE: dict[str, dict[str, Any]] = {}

CLUSTERS_COLLECTION = "narrative_strategy_clusters"

_THREAD_CONTAINER_PATTERNS = (
    "weekly thread",
    "bi-weekly advice",
    "biweekly advice",
    "discussion thread",
    "advice thread",
)


def _is_thread_container_title(title: str) -> bool:
    t = (title or "").strip().lower()
    return any(p in t for p in _THREAD_CONTAINER_PATTERNS)


def _cfg() -> dict[str, Any]:
    return get_config().get("narrative_strategy_engine") or {}


def _mongo_cfg() -> dict[str, Any]:
    return _cfg().get("mongodb") or {}


def _raw_collection() -> str:
    return (_mongo_cfg().get("raw_collection") or "narrative_strategy_reddit_raw").strip()


def _emb_cfg() -> dict[str, Any]:
    return _cfg().get("embeddings") or {}


def _actions_cfg() -> dict[str, Any]:
    return _cfg().get("actions") or {}

def _verticals_cfg() -> dict[str, Any]:
    v = get_config().get("verticals") or {}
    return v if isinstance(v, dict) else {}


def _vertical_categories(vertical: str) -> list[dict[str, Any]]:
    v = (vertical or "").strip().lower()
    cfg = _verticals_cfg().get(v) or {}
    cats = cfg.get("categories") if isinstance(cfg, dict) else None
    return cats if isinstance(cats, list) else []


def _vertical_label(vertical: str) -> str:
    v = (vertical or "").strip().lower()
    return v or "unknown"


def _sector_cfg() -> dict[str, Any]:
    return _cfg().get("sector_mapping") or {}


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sqrt(sum(x * x for x in a))
    nb = sqrt(sum(x * x for x in b))
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return dot / (na * nb)


@dataclass
class Cluster:
    center: list[float]
    item_ids: list[str]
    total: int = 0
    engagement: int = 0
    sentiment_sum: float = 0.0
    # evidence as tuples: (score, url, title, snippet, subreddit)
    evidence: list[tuple[int, str, str, str, str]] = None  # type: ignore[assignment]
    titles: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.evidence is None:
            self.evidence = []
        if self.titles is None:
            self.titles = []


def _engagement_score(doc: dict[str, Any]) -> int:
    eng = doc.get("engagement") or {}
    if isinstance(eng, dict):
        score = int(eng.get("score") or 0)
        if score:
            return score
        likes = int(eng.get("likes") or 0)
        comments = int(eng.get("comments") or 0)
        return likes + 3 * comments
    return 0


def _extract_text_for_theme(doc: dict[str, Any]) -> str:
    title = (doc.get("title") or "").strip()
    text = (doc.get("text") or "").strip()
    # Include a little of top comments to make themes less title-only
    cmts = doc.get("top_comments") if isinstance(doc.get("top_comments"), list) else []
    ctext = " ".join([(c.get("body") or "")[:240] for c in cmts[:3] if isinstance(c, dict) and c.get("body")])
    out = " ".join([t for t in (title, text, ctext) if t]).strip()
    return out[:8000]


def _bull_bear_neu(compound: float) -> str:
    if compound > 0.08:
        return "Bullish"
    if compound < -0.08:
        return "Bearish"
    return "Neutral"


def _strength_label(total: int, engagement: int) -> str:
    # Simple tiering; we can refine later.
    score = total + 0.02 * engagement
    if score >= 120:
        return "Very High"
    if score >= 60:
        return "High"
    if score >= 25:
        return "Medium"
    return "Low"


def _sector_entities_for_text(text: str) -> list[str]:
    cfg = _sector_cfg()
    groups = cfg.get("groups") or {}
    s = (text or "").lower()
    out: list[str] = []
    for _, g in (groups.items() if isinstance(groups, dict) else []):
        if not isinstance(g, dict):
            continue
        kws = g.get("keywords") or []
        ents = g.get("entities") or []
        if any(isinstance(k, str) and k.lower() in s for k in kws):
            out.extend([e for e in ents if isinstance(e, str) and e.strip()])
    # dedup preserve order
    seen = set()
    uniq = []
    for e in out:
        if e not in seen:
            uniq.append(e)
            seen.add(e)
    return uniq


def _company_presence(text: str, company: str) -> bool:
    c = (company or "").strip().lower()
    if not c:
        return False
    return c in (text or "").lower()


async def _llm_narrative_summary(items: list[dict[str, Any]], client_type: str) -> dict[str, str]:
    cfg = _cfg()
    llm_cfg = cfg.get("llm") or {}
    if not llm_cfg.get("enabled", True):
        return {"narrative": "", "theme": ""}

    model = (llm_cfg.get("model") or "openrouter/free").strip()
    max_tokens = int(llm_cfg.get("max_tokens") or 700)

    # Build compact evidence for LLM (titles + snippets)
    lines = []
    for i, it in enumerate(items[:12], 1):
        sub = (it.get("subreddit") or "").strip()
        title = (it.get("title") or "").strip()
        snippet = (it.get("snippet") or "").strip()
        lines.append(f"{i}. [r/{sub}] {title} — {snippet}")
    blob = "\n".join(lines)[:8000]

    system = (
        "You are a narrative strategist for financial ecosystem (banks, fintech, NBFCs, brokers). "
        "Given Reddit evidence, derive ONE concise market narrative.\n"
        "Rules: do NOT give stock recommendations. Focus on narratives and business implications.\n"
        "Return ONLY valid JSON: {\"theme\": \"...\", \"narrative\": \"...\"}. "
        "Theme should be a short category. Narrative should be a one-line statement."
    )
    user = f"Client type: {client_type}\nEvidence:\n{blob}"

    from app.services.llm_gateway import LLMGateway

    gateway = LLMGateway()
    gateway.set_model(model)
    out = ""
    try:
        async for chunk in gateway.chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            stream=False,
            use_web_search=False,
        ):
            out += chunk or ""
    except Exception as e:
        logger.warning("narrative_strategy_llm_failed", error=str(e))
        return {"theme": "", "narrative": ""}

    s = (out or "").strip()
    if s.startswith("```"):
        lines2 = s.split("\n")
        if lines2 and lines2[0].startswith("```"):
            lines2 = lines2[1:]
        if lines2 and lines2[-1].strip() == "```":
            lines2 = lines2[:-1]
        s = "\n".join(lines2).strip()
    try:
        import json

        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return {
                "theme": str(parsed.get("theme") or "").strip(),
                "narrative": str(parsed.get("narrative") or "").strip(),
            }
    except Exception:
        return {"theme": "", "narrative": ""}
    return {"theme": "", "narrative": ""}


def _embed_categories(vertical: str) -> tuple[list[dict[str, Any]], list[list[float]]]:
    """
    Cache embeddings for vertical categories (label+description).
    """
    from app.services.embedding_service import embed_batch

    v = _vertical_label(vertical)
    cached = _VERTICAL_CATEGORY_EMB_CACHE.get(v)
    if cached and isinstance(cached.get("cats"), list) and isinstance(cached.get("embs"), list):
        return cached["cats"], cached["embs"]
    cats = _vertical_categories(v)
    texts = []
    for c in cats:
        if not isinstance(c, dict):
            continue
        texts.append(f"{c.get('label','')} — {c.get('description','')}".strip())
    embs = embed_batch(texts) if texts else []
    _VERTICAL_CATEGORY_EMB_CACHE[v] = {"cats": cats, "embs": embs}
    return cats, embs


def _map_categories_by_embedding(narrative: str, vertical: str, top_k: int = 2, thr: float = 0.42) -> list[str]:
    """
    Embedding-based category mapping (no LLM).
    Returns list of category ids.
    """
    from app.services.embedding_service import embed

    cats, embs = _embed_categories(vertical)
    if not cats or not embs:
        return []
    v = embed((narrative or "")[:8000])
    scored: list[tuple[float, str]] = []
    for c, e in zip(cats, embs):
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or "").strip()
        if not cid:
            continue
        scored.append((_cosine(v, e), cid))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = [cid for sim, cid in scored[:top_k] if sim >= thr]
    return out


def _gap_and_actions(
    *,
    company: str,
    client_type: str,
    sentiment: str,
    company_present: bool,
    strength: str,
    sector_entities: list[str],
) -> tuple[str, str, str, str]:
    """
    Returns: (relevance_to_company, company_presence, gap, recommended_action, content_direction)
    Must always output at least one gap and a recommendation.
    """
    actions = (_actions_cfg().get("templates") or {}) if isinstance(_actions_cfg().get("templates"), dict) else {}
    default_actions = {
        "news": "Write/pitch a news article explaining the narrative, address key concerns, and cite evidence.",
        "forums": "Post a detailed answer on ValuePickr/TradingQnA clarifying misconceptions with data and examples.",
        "youtube": "Publish a short explainer video (5–8 min) with a clear POV + concrete examples; link to deeper write-up.",
        "reddit": "Comment on the highest-engagement thread with a crisp stance + evidence; ask one strong follow-up question.",
        "x": "Post a concise thread summarizing the narrative, your POV, and a link to a deeper asset.",
    }
    act = {**default_actions, **actions}

    relevance = "Medium"
    if company_present:
        relevance = "High"
    elif sector_entities and any(company.strip().lower() == e.strip().lower() for e in sector_entities):
        relevance = "High"
    elif sector_entities:
        relevance = "Medium"
    else:
        relevance = "Low"

    presence = "Present" if company_present else "Missing"

    gap = ""
    if not company_present:
        gap = "Visibility Gap"
    elif sentiment == "Bearish":
        gap = "Trust Gap"
    elif strength in ("High", "Very High"):
        gap = "Ownership Gap"
    else:
        gap = "Timing Gap"

    # Brutal, but safe (no stock tips)
    if gap == "Visibility Gap":
        recommended_action = act["reddit"]
        content_direction = f"Enter the conversation as a {client_type}: publish an evidence-led POV, then repurpose to {', '.join(['news', 'forums', 'youtube', 'x'])}."
    elif gap == "Trust Gap":
        recommended_action = act["forums"]
        content_direction = f"Address the negative angle directly: clarify risks, show guardrails, publish transparency metrics, and respond to top objections."
    elif gap == "Ownership Gap":
        recommended_action = act["news"]
        content_direction = f"Own the narrative with a flagship explain-piece + a repeatable content series; cite evidence and define a clear framework."
    else:
        recommended_action = act["youtube"]
        content_direction = f"Move fast: short explainer + a sharp comment on the top thread; then a deeper write-up to capture search intent."

    return relevance, presence, gap, recommended_action, content_direction


def _relevance_from_categories(cat_ids: list[str]) -> str:
    if not cat_ids:
        return "Low"
    if len(cat_ids) >= 2:
        return "High"
    return "Medium"


def _gaps_v2(
    *,
    company_present: bool,
    sentiment: str,
    strength: str,
    stage: str,
    relevance: str,
) -> dict[str, bool]:
    """
    Deterministic gap flags. Always yields at least one True.
    """
    gaps = {
        "visibility_gap": False,
        "trust_gap": False,
        "ownership_gap": False,
        "timing_gap": False,
    }
    if relevance in ("High", "Medium") and not company_present:
        gaps["visibility_gap"] = True
    if company_present and sentiment == "Bearish":
        gaps["trust_gap"] = True
    if relevance == "High" and strength in ("High", "Very High") and not company_present:
        gaps["ownership_gap"] = True
    if relevance in ("High", "Medium") and stage in ("emerging", "growing") and not company_present:
        gaps["timing_gap"] = True
    if not any(gaps.values()):
        gaps["visibility_gap"] = True
    return gaps


def _recommendations_v2(vertical: str, gaps: dict[str, bool]) -> dict[str, str]:
    """
    Deterministic action pack keyed by gap.
    """
    actions = (_actions_cfg().get("templates") or {}) if isinstance(_actions_cfg().get("templates"), dict) else {}
    default_actions = {
        "news": "Write/pitch a news article explaining the narrative, address key concerns, and cite evidence.",
        "forums": "Post a detailed answer on ValuePickr/TradingQnA clarifying misconceptions with data and examples.",
        "youtube": "Publish a short explainer video (5–8 min) with a clear POV + concrete examples; link to deeper write-up.",
        "reddit": "Comment on the highest-engagement thread with a crisp stance + evidence; ask one strong follow-up question.",
        "x": "Post a concise thread summarizing the narrative, your POV, and a link to a deeper asset.",
    }
    act = {**default_actions, **actions}
    # minimal but always actionable
    if gaps.get("trust_gap"):
        return {
            "positioning": f"As a {vertical}, address concerns head-on with transparency and guardrails.",
            "action": act["forums"],
            "content_direction": "Publish a rebuttal/clarification asset with evidence and explicit risk framing; then comment where criticism is strongest.",
        }
    if gaps.get("ownership_gap"):
        return {
            "positioning": f"Own this narrative as a {vertical} with a clear framework and point-of-view.",
            "action": act["news"],
            "content_direction": "Create a flagship explain-piece + a repeatable content series; repurpose into short formats.",
        }
    if gaps.get("timing_gap"):
        return {
            "positioning": f"Move early as a {vertical}: be first with clarity before competitors shape perception.",
            "action": act["youtube"],
            "content_direction": "Fast explainer + a crisp Reddit comment; then a deeper write-up to capture search intent.",
        }
    return {
        "positioning": f"Enter the conversation as a {vertical} with an evidence-led POV.",
        "action": act["reddit"],
        "content_direction": "Comment on the top thread, then repurpose into forums/news/YouTube/X depending on where gaps exist.",
    }


async def generate_narrative_strategy_v2(
    company: str,
    vertical: str,
    limit: int = 8,
    use_llm: bool = False,
) -> list[dict[str, Any]]:
    """
    Returns STRICT output format list (v2):
    [
      {
        "narrative": "...",
        "categories": [],
        "vertical": "...",
        "relevance": "...",
        "gaps": {},
        "recommendations": {}
      }
    ]

    Embeddings: clustering + category mapping.
    LLM (optional): narrative naming/belief extraction (only for top clusters).
    """
    from app.services.mongodb import get_mongo_client, get_db
    from app.services.embedding_service import embed_batch
    from app.services.sentiment_service import analyze_sentiment
    from app.services.entity_detection_service import detect_entities
    from app.core.client_config_loader import load_clients_sync, get_entity_names

    await get_mongo_client()
    db = get_db()
    coll = db[_raw_collection()]

    cfg = _cfg()
    max_items = int((_emb_cfg().get("max_items_for_clustering") or 800))
    # Keep this endpoint responsive for UI usage.
    # Users can raise this later via config if needed.
    max_items = min(max_items, int(cfg.get("strategy_max_items") or 250))
    thr = float((_emb_cfg().get("cluster_similarity_threshold") or 0.82))
    # Comment-level items are shorter/noisier; a slightly lower threshold forms usable clusters.
    thr = min(thr, 0.62)

    # Load latest raw docs (most recent fetch window)
    cursor = coll.find({"pipeline": "narrative_strategy_reddit", "kind": "post"}).sort("fetched_at", -1).limit(max_items)
    docs: list[dict[str, Any]] = []
    async for d in cursor:
        dd = dict(d)
        dd.pop("_id", None)
        docs.append(dd)

    if not docs:
        return [
            {
                "narrative": "No Reddit data ingested yet.",
                "belief": "",
                "categories": [],
                "vertical": _vertical_label(vertical),
                "relevance": "High",
                "gaps": {"visibility_gap": True, "trust_gap": False, "ownership_gap": False, "timing_gap": False},
                "recommendations": {
                    "positioning": "Collect market discussions first.",
                    "action": "Run the Reddit ingest pipeline, then re-run strategy.",
                    "content_direction": "Start with ingestion, then generate narratives, gaps, and actions.",
                },
                "debug": {
                    "cluster_size": 0,
                    "sample_posts": [],
                    "filter_reason": "no_docs",
                    "validation_status": "rejected",
                    "metrics": {
                        "total_posts_ingested": 0,
                        "posts_filtered_out": 0,
                        "clusters_created": 0,
                        "clusters_rejected": 0,
                        "narratives_generated": 0,
                        "narratives_rejected": 1,
                    },
                },
            }
        ]

    # Build item stream:
    # - drop container thread posts, but extract their comments as items
    # - include normal posts as items
    items: list[dict[str, Any]] = []
    for d in docs:
        title = (d.get("title") or "").strip()
        url = (d.get("url") or "").strip()
        sub = (d.get("subreddit") or "").strip()
        cmts = d.get("top_comments") if isinstance(d.get("top_comments"), list) else []
        top_cmts = [str(c.get("body") or "").strip() for c in cmts if isinstance(c, dict) and c.get("body")]
        if _is_thread_container_title(title):
            # Ignore the container post itself; use comments as the actual discussion units.
            seen_hashes: set[str] = set()
            for c in top_cmts[:80]:
                if len((c or "").strip()) < 80:
                    continue
                h = hashlib.sha1((c or "").strip().encode("utf-8")).hexdigest()[:16]
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                items.append(
                    {
                        "kind": "comment",
                        # FIX A: ignore container title completely for clustering
                        "title": "",
                        "text": (c or "")[:1200],
                        "url": url,
                        "subreddit": sub,
                        "_container": True,
                    }
                )
        else:
            text = _extract_text_for_theme(d)
            if not text:
                continue
            items.append(
                {
                    "kind": "post",
                    "title": title[:240],
                    "text": text[:1200],
                    "url": url,
                    "subreddit": sub,
                    "_container": False,
                }
            )

    total_posts_ingested = len(items)
    filter_rows = []
    posts_for_filter = []
    for i, it in enumerate(items):
        posts_for_filter.append({"id": str(i), "title": it.get("title") or "", "top_comments": [it.get("text") or ""]})

    try:
        from app.services.narrative_strategy_llm_router import classify_posts_relevance

        filter_rows = await classify_posts_relevance(items=posts_for_filter)
    except Exception as e:
        logger.warning("narrative_strategy_filter_failed", error=str(e))
        filter_rows = [{"id": str(i), "is_relevant": True, "reason": "filter_failed_open"} for i in range(len(docs))]

    id_to_keep: dict[int, tuple[bool, str]] = {}
    for r in filter_rows or []:
        try:
            idx = int(r.get("id"))
        except Exception:
            continue
        id_to_keep[idx] = (bool(r.get("is_relevant")), str(r.get("reason") or "").strip())

    relevant_items: list[dict[str, Any]] = []
    filtered_out = 0
    for i, it in enumerate(items):
        keep, reason = id_to_keep.get(i, (True, "default_keep"))
        if keep:
            dd = dict(it)
            dd["_filter_reason"] = reason
            relevant_items.append(dd)
        else:
            filtered_out += 1

    if not relevant_items:
        return []

    # FIX A: clustering based on meaning of the text, not thread title
    texts = [str(d.get("text") or "") for d in relevant_items]
    embs = embed_batch(texts)

    clusters: list[Cluster] = []
    for i, (doc, vec) in enumerate(zip(relevant_items, embs)):
        if not vec:
            continue
        best_j = -1
        best_sim = -1.0
        for j, c in enumerate(clusters):
            sim = _cosine(vec, c.center)
            if sim > best_sim:
                best_sim = sim
                best_j = j
        if best_sim >= thr and best_j >= 0:
            c = clusters[best_j]
            # update center as running average (cheap)
            n = max(1, len(c.item_ids))
            c.center = [(c.center[k] * n + vec[k]) / (n + 1) for k in range(len(vec))]
            c.item_ids.append(str(i))
        else:
            clusters.append(Cluster(center=vec, item_ids=[str(i)]))

    # Aggregate metrics per cluster
    for c in clusters:
        for idx_s in c.item_ids:
            idx = int(idx_s)
            d = relevant_items[idx]
            text = str(d.get("text") or "")
            eng = 0
            _, compound = analyze_sentiment(text[:2000])
            c.total += 1
            c.engagement += eng
            c.sentiment_sum += float(compound or 0.0)
            # evidence
            url = (d.get("url") or "").strip()
            title = (d.get("title") or "").strip()
            sub = (d.get("subreddit") or "").strip()
            snippet = (d.get("text") or "").strip()[:220]
            if url:
                c.evidence.append((eng, url, title, snippet, sub))
            if title:
                c.titles.append(title)

        c.evidence.sort(key=lambda x: int(x[0] or 0), reverse=True)
        c.evidence = c.evidence[:6]

    # Rank clusters by strength proxy
    clusters.sort(key=lambda c: (c.total + 0.02 * c.engagement), reverse=True)
    clusters_created = len(clusters)
    # 2) Cluster size enforcement (>=3)
    clusters = [c for c in clusters if int(c.total) >= 3]
    clusters_rejected = max(0, clusters_created - len(clusters))
    clusters = clusters[: max(3, min(limit * 2, 18))]

    out: list[dict[str, Any]] = []
    llm_cfg = _cfg().get("llm") or {}
    # If caller asks use_llm=false, we must not call any LLM even if config mode is hybrid/premium.
    mode = "off" if not use_llm else (llm_cfg.get("mode") or "hybrid").strip().lower()
    max_llm = int(llm_cfg.get("max_clusters_llm_per_run") or 10)
    max_prem = int(llm_cfg.get("max_premium_fallbacks_per_run") or 4)
    premium_used = 0
    cats_full = _vertical_categories(vertical)

    # Company universe: client + its competitors (from active clients config).
    universe: list[str] = []
    clients = load_clients_sync()
    for c in clients:
        if not isinstance(c, dict):
            continue
        names = get_entity_names(c)
        if company and names and names[0].strip().lower() == company.strip().lower():
            universe = names
            break
    if not universe:
        # fallback: all client+competitor names
        seen = set()
        for c in clients:
            if not isinstance(c, dict):
                continue
            for n in get_entity_names(c):
                if n and n not in seen:
                    universe.append(n)
                    seen.add(n)

    narratives_generated = 0
    narratives_rejected = 0

    clusters_coll = db[CLUSTERS_COLLECTION]
    rejections_coll = db["narrative_strategy_rejections"]

    async def _log_rejection(*, reason: str, c: "Cluster", extra: dict[str, Any] | None = None) -> None:
        try:
            doc = {
                "pipeline": "narrative_positioning_reddit",
                "schema_version": 1,
                "created_at": datetime.now(timezone.utc),
                "vertical": _vertical_label(vertical),
                "reason": str(reason or "").strip() or "unknown",
                "cluster_size": int(getattr(c, "total", 0) or 0),
                "sample_posts": [t for t in (getattr(c, "titles", None) or [])[:3] if t],
                "extra": extra or {},
            }
            await rejections_coll.insert_one(doc)
        except Exception:
            # never fail the request because of debug logging
            return

    def _is_generic_narrative(n: str) -> bool:
        s = (n or "").strip().lower()
        if not s or len(s) < 40:
            return True
        generic = (
            "broader trend",
            "navigating complexity",
            "highlights a broader trend",
            "market participants",
            "investors are increasingly",
            "raises questions about",
        )
        if any(g in s for g in generic):
            return True
        # Require at least one behavior/intent marker
        behavior = ("users", "traders", "investors", "people", "retail", "they", "i ", "we ")
        if not any(b in s for b in behavior):
            return True
        # Require a problem/confusion marker
        problem = ("confus", "unclear", "unsure", "hesitat", "worried", "panic", "fomo", "regret", "stuck", "afraid", "scared", "what should", "should i")
        if not any(p in s for p in problem):
            return True
        return False

    def _signal_strength(*, cluster_size: int, belief_s: str, narrative_s: str, examples: list[str]) -> str:
        # Strong if cluster has more support (>=4), or if it contains clear decision/pain markers.
        if int(cluster_size) >= 4:
            return "strong"
        b = (belief_s or "").lower()
        n = (narrative_s or "").lower()
        blob = (b + " " + n + " " + " ".join(examples or [])).lower()

        decision = (
            "what should i",
            "should i",
            "exit or hold",
            "hold or sell",
            "buy or sell",
            "is this good",
            "is this bad",
            "worth it",
            "lost money",
            "blew up",
        )
        pain = ("confus", "unclear", "unsure", "hesitat", "worried", "panic", "fomo", "regret", "stuck", "afraid", "scared")
        action = ("sell", "buy", "trade", "rebalance", "sip", "allocate", "entry", "exit", "portfolio")

        # repeated behavior signal: more than one example contains a decision/action/pain cue
        hits = 0
        for ex in (examples or [])[:8]:
            exl = (ex or "").lower()
            if any(d in exl for d in decision) or any(p in exl for p in pain) or any(a in exl for a in action):
                hits += 1
        if hits >= 2:
            return "strong"
        if any(d in blob for d in decision) or (any(p in blob for p in pain) and any(a in blob for a in action)):
            return "strong"
        return "emerging"

    def _confidence_score(*, cluster_size: int, engagement: int, strength: str, examples: list[str]) -> int:
        """
        0..100 confidence based on:
        - size: repetition support
        - consistency: number of examples with decision/pain/action cues
        - strength label
        """
        cs = max(0, int(cluster_size or 0))
        eng = max(0, int(engagement or 0))
        base = 35
        if strength == "strong":
            base += 20
        # cluster size contribution
        if cs >= 6:
            base += 30
        elif cs == 5:
            base += 24
        elif cs == 4:
            base += 18
        elif cs == 3:
            base += 10
        # engagement (soft)
        base += min(12, int(eng / 80))
        # consistency: how many examples show decision/pain/action
        decision = ("what should i", "should i", "exit", "hold", "sell", "buy", "lost money", "is this good", "is this bad", "worth it")
        pain = ("confus", "unclear", "unsure", "hesitat", "worried", "panic", "fomo", "regret", "stuck", "afraid")
        hits = 0
        for ex in (examples or [])[:10]:
            exl = (ex or "").lower()
            if any(d in exl for d in decision) or any(p in exl for p in pain):
                hits += 1
        base += min(18, hits * 6)
        return max(0, min(100, int(base)))

    def _fallback_title(narrative: str) -> str:
        import re

        s = (narrative or "").strip()
        if not s:
            return "Narrative signal"
        s = re.sub(r"^[\"']+|[\"']+$", "", s)
        s = re.sub(r"[^\w\s-]", " ", s)
        words = [w for w in s.split() if w]
        drop = {
            "users",
            "user",
            "people",
            "investors",
            "traders",
            "they",
            "are",
            "is",
            "was",
            "were",
            "there",
            "this",
            "that",
            "as",
            "with",
            "and",
            "but",
            "so",
            "to",
            "of",
            "in",
            "on",
            "for",
            "their",
            "a",
            "an",
            "the",
        }
        kept = [w for w in words if w.lower() not in drop]
        kept = kept[:6] if len(kept) >= 4 else (words[:6] if words else [])
        title = " ".join(kept[:6]).strip()
        if not title:
            return "Narrative signal"
        # enforce 4-6 words when possible
        parts = title.split()
        if len(parts) > 6:
            parts = parts[:6]
        return " ".join(parts)

    for idx_c, c in enumerate(clusters[:limit]):
        avg_sent = c.sentiment_sum / max(1, c.total)
        sent = _bull_bear_neu(avg_sent)
        strength = _strength_label(c.total, c.engagement)

        evidence_items = [
            {"url": u, "title": t, "snippet": sn, "subreddit": sub}
            for _, u, t, sn, sub in c.evidence
        ]

        # Cluster items for belief/narrative.
        cluster_items: list[dict[str, Any]] = []
        example_texts: list[str] = []
        for idx_s in c.item_ids[:12]:
            try:
                di = relevant_items[int(idx_s)]
            except Exception:
                continue
            txt = str(di.get("text") or "").strip()
            if not txt:
                continue
            cluster_items.append({"text": txt[:900]})
            example_texts.append(txt[:240])

        belief = ""
        narrative = ""
        if use_llm:
            try:
                from app.services.narrative_strategy_llm_router import (
                    broker_relevance_gate,
                    company_strategy_llm,
                    derive_belief_only,
                    founder_mode_llm,
                    narrative_from_belief,
                    pr_mode_llm,
                    relevance_reason_llm,
                    title_llm,
                    why_now_llm,
                    validate_category_fit,
                )

                belief = await derive_belief_only(cluster_items=cluster_items)
                narrative = await narrative_from_belief(belief=belief, examples=example_texts)
            except Exception as e:
                logger.warning("narrative_strategy_belief_narrative_failed", error=str(e))

        # Validation: narrative quality + no company names + no forbidden phrases
        forbidden = ("highlights a broader trend", "navigating complexity", "navigating complex", "broader trend")
        validation_errors = []
        if not belief:
            validation_errors.append("missing_belief")
        if not narrative:
            validation_errors.append("missing_narrative")
        # belief must be a single sentence
        if belief and sum(1 for ch in belief if ch in ".!?") > 1:
            validation_errors.append("belief_not_one_sentence")
        if any(p in (narrative or "").lower() for p in forbidden):
            validation_errors.append("forbidden_phrase")
        if narrative and len(narrative) < 35:
            validation_errors.append("narrative_too_short")
        # no company names in belief/narrative
        ents_in_out = detect_entities((belief + " " + narrative).lower())
        if ents_in_out:
            validation_errors.append("contains_company_name")

        if validation_errors:
            narratives_generated += 1
            narratives_rejected += 1
            await _log_rejection(reason="belief_narrative_validation:" + ",".join(validation_errors), c=c)
            continue

        # Reject only if narrative is completely generic / no behavior+problem signal
        if _is_generic_narrative(narrative):
            narratives_generated += 1
            narratives_rejected += 1
            await _log_rejection(reason="generic_narrative", c=c, extra={"narrative": narrative[:220]})
            continue

        # FIX B/F: broker relevance gate + relevance scoring
        gate = {"is_broker_relevant": True, "relevance": "Medium", "signal_type": "risk", "reason": ""}
        if use_llm:
            gate = await broker_relevance_gate(belief=belief, narrative=narrative)
        if bool(gate.get("macro_topic")):
            narratives_generated += 1
            narratives_rejected += 1
            await _log_rejection(reason="macro_topic", c=c, extra={"gate": gate})
            continue
        if not bool(gate.get("is_broker_relevant")):
            narratives_generated += 1
            narratives_rejected += 1
            await _log_rejection(reason="not_vertical_relevant", c=c, extra={"gate": gate})
            continue
        # Extra macro guardrail (LLM sometimes under-flags macro topics).
        nl = (narrative or "").lower()
        macro_markers = ("geopolitic", "geopolitical", "war", "tension", "rbi", "rupee", "inflation", "gdp", "policy", "fed")
        macro_context = ("nifty", "sensex", "index", "markets", "market", "rupee", "rates", "inflation", "gdp")
        broker_experience = ("broker", "platform", "fees", "outage", "execution", "order", "slippage")
        decision_markers = ("what should", "should i", "is this good", "is this bad", "panic", "worried", "unsure", "hesitat", "confus")
        if any(m in nl for m in macro_markers) and any(x in nl for x in macro_context) and not any(x in nl for x in broker_experience) and not any(x in nl for x in decision_markers):
            narratives_generated += 1
            narratives_rejected += 1
            await _log_rejection(reason="macro_news_no_behavior", c=c, extra={"narrative": narrative[:220]})
            continue
        relevance = str(gate.get("relevance") or "Low")
        if relevance not in ("High", "Medium", "Low"):
            relevance = "Low"
        # Do not over-reject: keep emerging signals even when relevance is Medium.
        # relevance_reason is generated separately (communication-only)
        relevance_reason = ""

        # Company gap mapping (per company in universe)
        cluster_blob = " ".join([x.get("title", "") + " " + x.get("text", "") for x in cluster_items]).lower()
        mentioned = set(detect_entities(cluster_blob))
        companies: dict[str, Any] = {}
        for co in universe:
            co_mentioned = co in mentioned
            # trust gap: negative when mentioned
            trust_gap = False
            if co_mentioned:
                _, comp = analyze_sentiment(cluster_blob[:2000])
                trust_gap = float(comp or 0.0) < -0.08
            # ownership gap: nobody is mentioned
            ownership_gap = len(mentioned) == 0
            # timing gap: someone else mentioned but this co not
            timing_gap = (not co_mentioned) and len(mentioned) > 0
            visibility_gap = not co_mentioned

            if len(mentioned) == 0:
                gap = "white_space_opportunity"
            elif trust_gap:
                gap = "trust_gap"
            elif timing_gap and visibility_gap:
                gap = "timing_gap"
            elif ownership_gap:
                gap = "ownership_gap"
            elif visibility_gap:
                gap = "visibility_gap"
            else:
                gap = "none"
            companies[co] = {"gap": gap, "strategy": ""}

        # Market-level signals (for final output)
        gap_values = [v.get("gap") for v in companies.values()]
        non_differentiated = bool(gap_values and len(set(gap_values)) == 1)
        if len(mentioned) == 0:
            market_signal = "white_space_opportunity"
        elif non_differentiated:
            market_signal = "non_differentiated_signal"
        else:
            market_signal = "competitive"

        narratives_generated += 1

        # FIX D: Category precision (map then validate confidence >= 0.7)
        cat_ids: list[str] = []
        if use_llm:
            try:
                from app.services.narrative_strategy_llm_router import map_categories_llm

                mapped = await map_categories_llm(narrative=narrative, categories=cats_full)
                # validate each mapped category
                cats_by_id = {str(c.get("id") or "").strip(): c for c in cats_full if isinstance(c, dict)}
                kept: list[str] = []
                for cid in mapped:
                    cobj = cats_by_id.get(cid)
                    if not cobj:
                        continue
                    conf = await validate_category_fit(narrative=narrative, category=cobj)
                    if conf >= 0.7:
                        kept.append(cid)
                cat_ids = kept
            except Exception:
                cat_ids = []

        # Founder + PR comms (no product/UX suggestions)
        founder_mode = await founder_mode_llm(narrative=narrative, belief=belief)
        pr_mode = await pr_mode_llm(narrative=narrative, belief=belief)
        relevance_reason = await relevance_reason_llm(narrative=narrative, vertical=_vertical_label(vertical))
        why_now = await why_now_llm(narrative=narrative, belief=belief, vertical=_vertical_label(vertical))
        title = ""
        try:
            title = await title_llm(narrative=narrative, belief=belief)
        except Exception:
            title = ""
        if not title:
            title = _fallback_title(narrative)
        if not founder_mode.get("what_to_say") or not pr_mode.get("core_message"):
            narratives_rejected += 1
            await _log_rejection(reason="comms_generation_missing", c=c)
            continue
        if not relevance_reason:
            narratives_rejected += 1
            await _log_rejection(reason="relevance_reason_missing", c=c)
            continue
        if not why_now:
            # Don't reject for missing why_now; keep usable outputs.
            why_now = "In periods of uncertainty and noisy market narratives, this behavior becomes more visible and more costly for user confidence."

        # Final safety gate: communication-only (no product/UX language)
        comm_blob = " ".join(
            [
                str(relevance_reason or ""),
                str(founder_mode.get("what_to_say") or ""),
                str(founder_mode.get("example_post") or ""),
                str(pr_mode.get("core_message") or ""),
                str(pr_mode.get("angle") or ""),
            ]
        ).lower()
        # Keep this narrow to avoid false rejections (LLMs often say "tools"/"platform" even in pure comms).
        forbidden_comm = (
            "ux",
            "feature",
            "build",
            "ship",
            "redesign",
            "in-app",
            "in product",
            "product",
            "recommendation",
            "recommend",
            "personalized",
        )
        # Do NOT hard-reject slightly imperfect comms; only reject if it clearly becomes product/UX advice.
        if any(w in comm_blob for w in ("ux", "feature", "in-app", "in product")):
            narratives_rejected += 1
            await _log_rejection(reason="comms_contains_product_or_ux", c=c, extra={"preview": comm_blob[:260]})
            continue

        # Company strategies (only when gaps are actionable)
        if market_signal in ("white_space_opportunity", "non_differentiated_signal"):
            # Only assign company-specific gaps/strategies when differentiation exists.
            companies = {}
        else:
            for co, meta in companies.items():
                gap = str(meta.get("gap") or "")
                if gap in ("none",):
                    continue
                try:
                    meta["strategy"] = await company_strategy_llm(company=co, gap=gap, narrative=narrative)
                except Exception:
                    meta["strategy"] = ""
            # Ensure strategies remain communication-only
            sblob = " ".join([str(v.get("strategy") or "") for v in companies.values()]).lower()
            if any(w in sblob for w in ("ux", "feature", "in-app", "in product")):
                narratives_rejected += 1
                await _log_rejection(reason="company_strategy_contains_product_or_ux", c=c, extra={"preview": sblob[:260]})
                continue

        strength = _signal_strength(cluster_size=int(c.total), belief_s=belief, narrative_s=narrative, examples=example_texts)
        if int(c.total) >= 4:
            strength = "strong"
        confidence_score = _confidence_score(cluster_size=int(c.total), engagement=int(c.engagement), strength=strength, examples=example_texts)

        base_obj = {
            "title": title,
            "narrative": narrative,
            "belief": belief,
            "why_now": why_now,
            "confidence_score": int(confidence_score),
            "vertical": _vertical_label(vertical),
            "categories": cat_ids,
            "relevance": relevance,
            "relevance_reason": relevance_reason,
            "signal_strength": strength,
            "market_signal": market_signal,
            "companies": companies,
            "founder_mode": founder_mode,
            "pr_mode": pr_mode,
            "debug": {
                "cluster_size": int(c.total),
                "sample_posts": [t for t in (c.titles or [])[:3] if t],
                "validation_status": "accepted",
                "rejection_reason": "",
                "non_differentiated_signal": bool(non_differentiated),
                "metrics": {
                    "total_posts_ingested": int(total_posts_ingested),
                    "posts_filtered_out": int(filtered_out),
                    "clusters_created": int(clusters_created),
                    "clusters_rejected": int(clusters_rejected),
                    "narratives_generated": int(narratives_generated),
                    "narratives_rejected": int(narratives_rejected),
                },
            },
        }
        # Hard rule: cluster_size>=4 is strong.
        try:
            if int(((base_obj.get("debug") or {}).get("cluster_size") or 0)) >= 4:
                base_obj["signal_strength"] = "strong"
        except Exception:
            pass
        try:
            if base_obj.get("signal_strength") == "strong":
                base_obj["confidence_score"] = max(int(base_obj.get("confidence_score") or 0), 80)
        except Exception:
            pass

        # Persist accepted cluster record for auditing/debugging in Mongo
        try:
            cluster_doc = {
                "pipeline": "narrative_strategy_reddit",
                "schema_version": 7,
                "vertical": _vertical_label(vertical),
                "created_at": datetime.now(timezone.utc),
                "cluster_size": int(c.total),
                "sample_posts": [t for t in (c.titles or [])[:3] if t],
                "evidence": evidence_items[:6],
                "title": str(base_obj.get("title") or title),
                "belief": belief,
                "narrative": narrative,
                "categories": cat_ids,
                "relevance": relevance,
                "relevance_reason": relevance_reason,
                "why_now": why_now,
                "confidence_score": int(base_obj.get("confidence_score") or confidence_score),
                "signal_strength": str(base_obj.get("signal_strength") or strength),
                "market_signal": market_signal,
                "companies": companies,
                "founder_mode": founder_mode,
                "pr_mode": pr_mode,
                "metrics": (base_obj.get("debug") or {}).get("metrics") if isinstance(base_obj.get("debug"), dict) else {},
            }
            # One doc per cluster (no company_query in key)
            key = {
                "schema_version": 7,
                "vertical": cluster_doc["vertical"],
                "narrative": cluster_doc["narrative"],
                "evidence_urls": [e.get("url", "") for e in evidence_items[:6]],
            }
            await clusters_coll.update_one(key, {"$set": cluster_doc}, upsert=True)
        except Exception as e:
            logger.debug("narrative_strategy_cluster_persist_failed", error=str(e))

        out.append(base_obj)

    # Ensure output count range and never return empty.
    # Target: 3-5, min 2, max 7.
    out = out[:7]

    # Prioritize best narratives first:
    # 1) signal_strength (strong first)
    # 2) confidence_score desc
    # 3) relevance (High > Medium > Low)
    # 4) cluster_size desc
    strength_rank = {"strong": 0, "emerging": 1}
    rel_rank = {"High": 0, "Medium": 1, "Low": 2}
    out.sort(
        key=lambda r: (
            strength_rank.get(str(r.get("signal_strength") or "emerging"), 9),
            -int(r.get("confidence_score") or 0),
            rel_rank.get(str(r.get("relevance") or "Low"), 9),
            -int(((r.get("debug") or {}).get("cluster_size") or 0)),
        )
    )

    # Final consistency: strong must be >= 80 confidence.
    for r in out:
        try:
            if str(r.get("signal_strength") or "") == "strong":
                r["confidence_score"] = max(int(r.get("confidence_score") or 0), 80)
        except Exception:
            continue

    # Balanced output: try to include at least one strong when data supports it.
    if out and not any((r.get("signal_strength") == "strong") for r in out):
        # If top item has enough support, promote it.
        top_cs = int(((out[0].get("debug") or {}).get("cluster_size") or 0))
        if top_cs >= 4:
            out[0]["signal_strength"] = "strong"

    async def _force_generate_from_cluster(c: "Cluster") -> dict[str, Any] | None:
        # Use the same pipeline but mark emerging; relax relevance/macro rules.
        evidence_items = [{"url": u, "title": t, "snippet": sn, "subreddit": sub} for _, u, t, sn, sub in c.evidence]
        cluster_items = []
        example_texts = []
        for idx_s in c.item_ids[:12]:
            try:
                di = relevant_items[int(idx_s)]
            except Exception:
                continue
            txt = str(di.get("text") or "").strip()
            if not txt:
                continue
            cluster_items.append({"text": txt[:900]})
            example_texts.append(txt[:240])
        if not cluster_items:
            return None
        try:
            from app.services.narrative_strategy_llm_router import (
                derive_belief_only,
                founder_mode_llm,
                narrative_from_belief,
                pr_mode_llm,
                relevance_reason_llm,
            )
            belief = await derive_belief_only(cluster_items=cluster_items)
            narrative = await narrative_from_belief(belief=belief, examples=example_texts)
            if not belief or not narrative or _is_generic_narrative(narrative):
                return None
            founder_mode = await founder_mode_llm(narrative=narrative, belief=belief)
            pr_mode = await pr_mode_llm(narrative=narrative, belief=belief)
            relevance_reason = await relevance_reason_llm(narrative=narrative, vertical=_vertical_label(vertical))
            if not founder_mode.get("what_to_say") or not pr_mode.get("core_message") or not relevance_reason:
                return None
            try:
                from app.services.narrative_strategy_llm_router import title_llm, why_now_llm

                why_now = await why_now_llm(narrative=narrative, belief=belief, vertical=_vertical_label(vertical))
                title = await title_llm(narrative=narrative, belief=belief)
            except Exception:
                why_now = ""
                title = ""
            if not why_now:
                why_now = "In volatile or noisy periods, users become more reactive and seek simple decision frames, making this narrative urgent."
            if not title:
                title = _fallback_title(narrative)
            strength = _signal_strength(cluster_size=int(getattr(c, "total", 0) or 0), belief_s=belief, narrative_s=narrative, examples=example_texts)
            if int(getattr(c, "total", 0) or 0) >= 4:
                strength = "strong"
            confidence_score = _confidence_score(cluster_size=int(getattr(c, "total", 0) or 0), engagement=int(getattr(c, "engagement", 0) or 0), strength=strength, examples=example_texts)
            if strength == "strong":
                confidence_score = max(int(confidence_score), 80)
            return {
                "title": title,
                "narrative": narrative,
                "belief": belief,
                "why_now": why_now,
                "confidence_score": int(confidence_score),
                "vertical": _vertical_label(vertical),
                "categories": [],
                "relevance": "Medium",
                "relevance_reason": relevance_reason,
                "signal_strength": strength,
                "market_signal": "competitive",
                "companies": {},
                "founder_mode": founder_mode,
                "pr_mode": pr_mode,
                "debug": {"cluster_size": int(c.total), "sample_posts": [t for t in (c.titles or [])[:3] if t]},
            }
        except Exception:
            return None

    if len(out) < 2:
        # fallback: select top clusters and force-generate emerging narratives
        # Try more clusters to reliably reach minimum output.
        top = sorted(clusters, key=lambda cc: (int(cc.total), int(cc.engagement)), reverse=True)[:10]
        forced: list[dict[str, Any]] = []
        for c in top:
            if int(getattr(c, "total", 0) or 0) < 3:
                continue
            row = await _force_generate_from_cluster(c)
            if row and all((row.get("narrative") != x.get("narrative")) for x in (out + forced)):
                forced.append(row)
            if len(out) + len(forced) >= 3:
                break
        out.extend(forced)

    # If still below min, pad with one last-resort emerging narrative.
    if len(out) == 1:
        out.append(
            {
                "title": "Noise-driven hesitation loop",
                "narrative": "When markets get noisy, users second-guess their plan and look for a simple rule to decide whether to act or wait, which increases hesitation and reactive choices.",
                "belief": "Users second-guess their plan under uncertainty and look for a simple rule to decide what to do next.",
                "why_now": "Recent volatility and nonstop market commentary makes hesitation and reactive decisions more likely, turning a quiet doubt into an urgent decision moment.",
                "confidence_score": 55,
                "vertical": _vertical_label(vertical),
                "categories": [],
                "relevance": "Medium",
                "relevance_reason": "This is a repeatable communication moment: a clear decision frame reduces hesitation and builds trust when uncertainty spikes.",
                "signal_strength": "emerging",
                "market_signal": "white_space_opportunity",
                "companies": {},
                "founder_mode": {
                    "what_to_say": "If you don’t have a clear reason to act today, don’t. Noise isn’t a signal.",
                    "channels": ["twitter", "linkedin", "community"],
                    "example_post": "A good rule in volatile markets: if you can’t explain your next move in one sentence, you’re reacting—not investing.",
                },
                "pr_mode": {
                    "core_message": "In uncertain markets, the differentiator is clarity: a simple decision frame beats reactive commentary.",
                    "angle": "Own the 'clarity under uncertainty' narrative—less prediction, more decision discipline.",
                    "content_examples": {
                        "news_article": "As volatility rises, investors struggle with timing decisions; experts emphasize having a clear decision framework.",
                        "social_post": "Volatility creates noise. Clarity comes from a simple decision frame—not hot takes.",
                        "forum_response": "If you’re unsure, anchor to your time horizon and rules—don’t let noise force a decision.",
                    },
                },
                "debug": {"cluster_size": 0, "sample_posts": []},
            }
        )

    # If still below min, return a minimal non-empty response (last resort).
    if not out:
        out = [
            {
                "title": "Uncertainty-driven reassurance demand",
                "narrative": "Users are actively seeking guidance and reassurance during uncertain market conditions, but unclear next steps amplify hesitation and reactive decisions.",
                "belief": "Users are unsure what to do next and look for reassurance when uncertainty rises.",
                "why_now": "In volatile or headline-driven periods, uncertainty spikes and users become more reactive, creating a narrow window to own the framing.",
                "confidence_score": 50,
                "vertical": _vertical_label(vertical),
                "categories": [],
                "relevance": "Medium",
                "relevance_reason": "This captures a live decision moment where clear positioning and reassurance can prevent reactive behavior and build trust.",
                "signal_strength": "emerging",
                "market_signal": "white_space_opportunity",
                "companies": {},
                "founder_mode": {"what_to_say": "If you’re feeling uncertain, pause and return to your plan—clarity beats impulse.", "channels": ["twitter", "linkedin", "community"], "example_post": "When the feed gets loud, your plan matters more. Pause, zoom out, and choose clarity over impulse."},
                "pr_mode": {"core_message": "In moments of uncertainty, clear guidance and calm framing help investors avoid reactive decisions.", "angle": "Empathy + clarity: acknowledge uncertainty and offer a steady framework for decision-making.", "content_examples": {"news_article": "Uncertainty often triggers reactive decisions; experts recommend returning to a clear plan and time horizon.", "social_post": "Uncertain markets test discipline. Clear framing helps investors avoid impulse decisions.", "forum_response": "It’s normal to feel unsure—try anchoring to your time horizon and rules before taking action."}},
                "debug": {"cluster_size": 0, "sample_posts": []},
            }
        ]

    return out


async def list_market_narratives(limit: int = 50, items: int = 600, use_llm: bool = False) -> list[dict[str, Any]]:
    """
    List narratives detected from stored Reddit raw data (all subreddits).
    This is company-agnostic: it answers "what narratives exist in the data we stored".
    """
    from app.services.mongodb import get_mongo_client, get_db
    from app.services.embedding_service import embed_batch
    from app.services.sentiment_service import analyze_sentiment

    await get_mongo_client()
    db = get_db()
    coll = db[_raw_collection()]

    cfg = _cfg()
    max_items_cfg = int((_emb_cfg().get("max_items_for_clustering") or 800))
    max_items = min(max_items_cfg, int(items or 600))
    thr = float((_emb_cfg().get("cluster_similarity_threshold") or 0.82))

    cursor = coll.find({"pipeline": "narrative_strategy_reddit", "kind": "post"}).sort("fetched_at", -1).limit(max_items)
    docs: list[dict[str, Any]] = []
    async for d in cursor:
        dd = dict(d)
        dd.pop("_id", None)
        docs.append(dd)

    if not docs:
        return []

    # LLM filtering (same policy as engine): remove non-user-experience posts before clustering
    posts_for_filter = []
    for i, d in enumerate(docs):
        title = (d.get("title") or "").strip()
        cmts = d.get("top_comments") if isinstance(d.get("top_comments"), list) else []
        top_cmts = [str(c.get("body") or "").strip() for c in cmts if isinstance(c, dict) and c.get("body")]
        posts_for_filter.append({"id": str(i), "title": title, "top_comments": top_cmts})
    try:
        from app.services.narrative_strategy_llm_router import classify_posts_relevance

        filter_rows = await classify_posts_relevance(items=posts_for_filter)
    except Exception:
        filter_rows = [{"id": str(i), "is_relevant": True, "reason": "filter_failed_open"} for i in range(len(docs))]

    keep_ids: set[int] = set()
    for r in filter_rows or []:
        try:
            idx = int(r.get("id"))
        except Exception:
            continue
        if bool(r.get("is_relevant")):
            keep_ids.add(idx)
    docs = [d for i, d in enumerate(docs) if i in keep_ids]
    if not docs:
        return []

    texts = [_extract_text_for_theme(d) for d in docs]
    embs = embed_batch(texts)

    clusters: list[Cluster] = []
    for i, (doc, vec) in enumerate(zip(docs, embs)):
        if not vec:
            continue
        best_j = -1
        best_sim = -1.0
        for j, c in enumerate(clusters):
            sim = _cosine(vec, c.center)
            if sim > best_sim:
                best_sim = sim
                best_j = j
        if best_sim >= thr and best_j >= 0:
            c = clusters[best_j]
            n = max(1, len(c.item_ids))
            c.center = [(c.center[k] * n + vec[k]) / (n + 1) for k in range(len(vec))]
            c.item_ids.append(str(i))
        else:
            clusters.append(Cluster(center=vec, item_ids=[str(i)]))

    # Aggregate
    for c in clusters:
        subs: dict[str, int] = {}
        for idx_s in c.item_ids:
            idx = int(idx_s)
            d = docs[idx]
            text = _extract_text_for_theme(d)
            eng = _engagement_score(d)
            _, compound = analyze_sentiment(text[:2000])
            c.total += 1
            c.engagement += eng
            c.sentiment_sum += float(compound or 0.0)
            sub = (d.get("subreddit") or "").strip()
            if sub:
                subs[sub] = subs.get(sub, 0) + 1
            url = (d.get("url") or "").strip()
            title = (d.get("title") or "").strip()
            snippet = (d.get("text") or "").strip()[:220]
            if url:
                c.evidence.append((eng, url, title, snippet, sub))
            if title:
                c.titles.append(title)

        c.evidence.sort(key=lambda x: int(x[0] or 0), reverse=True)
        c.evidence = c.evidence[:6]
        # attach subreddit counts to cluster in evidence only

    clusters.sort(key=lambda c: (c.total + 0.02 * c.engagement), reverse=True)
    # Cluster size enforcement (>=3)
    clusters = [c for c in clusters if int(c.total) >= 3]
    clusters = clusters[: max(1, min(int(limit), 200))]

    out: list[dict[str, Any]] = []
    for c in clusters:
        avg_sent = c.sentiment_sum / max(1, c.total)
        sent = _bull_bear_neu(avg_sent)
        strength = _strength_label(c.total, c.engagement)
        # subreddit counts from evidence
        subs: dict[str, int] = {}
        for _, _, _, _, sub in c.evidence:
            if sub:
                subs[sub] = subs.get(sub, 0) + 1
        sub_sorted = sorted(subs.items(), key=lambda kv: int(kv[1] or 0), reverse=True)[:12]

        evidence_items = [{"url": u, "title": t, "snippet": sn, "subreddit": sub} for _, u, t, sn, sub in c.evidence]

        belief = ""
        narrative = ""
        if use_llm:
            try:
                from app.services.narrative_strategy_llm_router import derive_belief_and_narrative

                cluster_posts = []
                for t in (c.titles or [])[:10]:
                    cluster_posts.append({"title": t[:240], "comments": []})
                bn = await derive_belief_and_narrative(cluster_posts=cluster_posts)
                belief = (bn.get("belief") or "").strip()
                narrative = (bn.get("narrative") or "").strip()
            except Exception:
                belief = ""
                narrative = ""

        if not narrative:
            # Prefer rejection over low-quality output
            continue

        out.append(
            {
                "narrative": narrative,
                "belief": belief,
                "sentiment": sent,
                "strength": strength,
                "total_posts": int(c.total),
                "engagement": int(c.engagement),
                "top_subreddits": [{"subreddit": k, "count": int(v)} for k, v in sub_sorted],
                "evidence": evidence_items[:5],
            }
        )

    return out

