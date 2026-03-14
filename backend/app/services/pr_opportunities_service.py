"""PR Opportunities batch service — Quote alerts, Outreach drafts, Competitor response angles.
LLM used in batch only; results stored in pr_opportunities. Reads from entity_mentions, article_documents."""
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.core.client_config_loader import get_entity_names, get_competitor_names, load_clients
from app.services.mongodb import get_mongo_client

ENTITY_MENTIONS_COLLECTION = "entity_mentions"
ARTICLE_DOCUMENTS_COLLECTION = "article_documents"
PR_OPPORTUNITIES_COLLECTION = "pr_opportunities"
PR_DAILY_SNAPSHOTS_COLLECTION = "pr_daily_snapshots"

# Limits to stay under LLM free tier
QUOTE_ALERT_LLM_BATCH = 5
OUTREACH_DRAFT_LLM_BATCH = 5
COMPETITOR_RESPONSE_LLM_BATCH = 5

# Regex patterns for quote opportunity (pre-filter, no LLM)
QUOTE_PATTERNS = re.compile(
    r"\b(declined to comment|did not (respond|return)|no comment|not available for comment|"
    r"could not be reached|refused to comment|declined comment|we reached out|"
    r"contacted for comment|requests? for comment)\b",
    re.I,
)

MAX_INPUT_CHARS = 800


async def _get_client_entities(client: str) -> tuple[Optional[str], list[str], list[str]]:
    clients_list = await load_clients()
    client_obj = next(
        (c for c in clients_list if (c.get("name") or "").strip().lower() == client.strip().lower()),
        None,
    )
    if not client_obj:
        return None, [], []
    client_name = (client_obj.get("name") or "").strip()
    entities = get_entity_names(client_obj)
    competitors = get_competitor_names(client_obj)
    return client_name, entities, competitors


async def _llm_call(prompt: str, max_tokens: int = 120) -> Optional[str]:
    """Single LLM call. Returns None on error or missing key."""
    try:
        from app.services.llm_gateway import LLMGateway
        gw = LLMGateway()
        if not gw.api_key:
            return None
        text = prompt.strip()[:3000]
        chunks: list[str] = []
        async for ch in gw.chat_completion([{"role": "user", "content": text}], stream=False):
            if ch and not (isinstance(ch, str) and ch.strip().startswith("{")):
                chunks.append(ch if isinstance(ch, str) else str(ch))
        out = "".join(chunks).strip()
        return out[:500] if out else None
    except Exception:
        return None


# --- 1. Quote opportunity alerts ---


async def _find_quote_alert_candidates(client: str, limit: int = 20) -> list[dict[str, Any]]:
    """Find articles (entity_mentions + article_documents) with quote-seeking phrases."""
    await get_mongo_client()
    from app.services.mongodb import get_db

    _, entities, _ = await _get_client_entities(client)
    if not entities:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]
    art_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    # article_documents have article_text (full content for regex)
    async for doc in art_coll.find({
        "entities": {"$in": entities},
        "$or": [{"published_at": {"$gte": cutoff}}, {"fetched_at": {"$gte": cutoff}}],
    }).limit(limit * 5):
        url = (doc.get("url") or doc.get("url_resolved") or "").strip().lower()
        if not url or url in seen_urls:
            continue
        text = (doc.get("article_text") or doc.get("summary") or doc.get("title") or "")[:2000]
        if not text:
            continue
        m = QUOTE_PATTERNS.search(text)
        if not m:
            continue
        seen_urls.add(url)
        candidates.append({
            "url": doc.get("url") or doc.get("url_resolved"),
            "title": (doc.get("title") or "")[:300],
            "snippet": text[:500],
            "phrase": m.group(0),
        })
        if len(candidates) >= limit:
            break

    return candidates


async def compute_quote_opportunities(client: str) -> int:
    """Batch: find quote-alert candidates, LLM suggests action, store. Returns count stored."""
    candidates = await _find_quote_alert_candidates(client, limit=QUOTE_ALERT_LLM_BATCH)
    if not candidates:
        return 0

    await get_mongo_client()
    from app.services.mongodb import get_db
    db = get_db()
    coll = db[PR_OPPORTUNITIES_COLLECTION]
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stored = 0

    for c in candidates[:QUOTE_ALERT_LLM_BATCH]:
        prompt = f"""Article excerpt (seeking comment):
"{c['snippet'][:MAX_INPUT_CHARS]}"

Detected phrase: "{c['phrase']}"

In one short sentence (max 20 words), suggest what the PR team should do. Output only the action, no quotes."""
        action = await _llm_call(prompt)
        if not action:
            action = "Reach out to journalist and offer expert quote."

        doc = {
            "type": "quote_alert",
            "client": client,
            "date": date_str,
            "article_url": c["url"],
            "article_title": c["title"],
            "detected_phrase": c["phrase"],
            "suggested_action": action,
            "computed_at": datetime.now(timezone.utc),
        }
        await coll.update_one(
            {"type": "quote_alert", "client": client, "date": date_str, "article_url": c["url"]},
            {"$set": doc},
            upsert=True,
        )
        stored += 1

    return stored


# --- 2. Outreach email drafts ---


OUTREACH_DAYS_BACK = 7


async def _get_outreach_targets(client: str) -> list[dict[str, Any]]:
    """Get outreach targets. Uses 7-day window; falls back to pr_daily_snapshots if present."""
    await get_mongo_client()
    from app.services.mongodb import get_db
    from app.services.pr_report_service import compute_outreach_targets

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    db = get_db()
    snap = await db[PR_DAILY_SNAPSHOTS_COLLECTION].find_one({"client": client, "date": date_str})
    if snap and (snap.get("outreach_targets") or []):
        return (snap.get("outreach_targets") or [])[:OUTREACH_DRAFT_LLM_BATCH]
    targets = await compute_outreach_targets(client, date_str, days_back=OUTREACH_DAYS_BACK)
    return targets[:OUTREACH_DRAFT_LLM_BATCH]


async def compute_outreach_drafts(client: str) -> int:
    """Batch: get outreach targets, LLM generates 1-2 line pitch, store."""
    targets = await _get_outreach_targets(client)
    if not targets:
        return 0

    await get_mongo_client()
    from app.services.mongodb import get_db
    db = get_db()
    coll = db[PR_OPPORTUNITIES_COLLECTION]
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stored = 0

    for t in targets[:OUTREACH_DRAFT_LLM_BATCH]:
        outlet = t.get("outlet") or t.get("domain", "")
        comp_mentions = t.get("competitor_mentions", 0)
        prompt = f"""PR outreach: Client "{client}" has zero coverage at outlet "{outlet}" while competitors have {comp_mentions} mentions.

Write ONE short opening line (max 25 words) for a cold pitch email. Be specific, professional, no hype. Output only the line."""
        draft = await _llm_call(prompt)
        if not draft:
            draft = f"Given {outlet}'s recent coverage of our space, we thought you might be interested in {client}'s perspective."

        doc = {
            "type": "outreach_draft",
            "client": client,
            "date": date_str,
            "outlet": outlet,
            "domain": t.get("domain", ""),
            "competitor_mentions": comp_mentions,
            "draft_line": draft,
            "computed_at": datetime.now(timezone.utc),
        }
        await coll.update_one(
            {"type": "outreach_draft", "client": client, "date": date_str, "outlet": outlet},
            {"$set": doc},
            upsert=True,
        )
        stored += 1

    return stored


# --- 3. Competitor story follow-ups ---


async def _get_competitor_articles(client: str, limit: int = 10) -> list[dict[str, Any]]:
    """Get recent articles where competitors (not client) are mentioned."""
    await get_mongo_client()
    from app.services.mongodb import get_db

    client_name, _, competitors = await _get_client_entities(client)
    if not competitors:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]
    seen: set[str] = set()
    results: list[dict] = []

    async for doc in em_coll.find({
        "entity": {"$in": competitors},
        "$or": [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}],
    }).sort("published_at", -1).limit(limit * 2):
        url = (doc.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        results.append({
            "url": url,
            "title": (doc.get("title") or "")[:300],
            "competitor": doc.get("entity"),
        })
        if len(results) >= limit:
            break

    return results


async def compute_competitor_responses(client: str) -> int:
    """Batch: get competitor articles, LLM suggests response angle for client."""
    articles = await _get_competitor_articles(client, limit=COMPETITOR_RESPONSE_LLM_BATCH)
    if not articles:
        return 0

    await get_mongo_client()
    from app.services.mongodb import get_db
    db = get_db()
    coll = db[PR_OPPORTUNITIES_COLLECTION]
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stored = 0

    for a in articles[:COMPETITOR_RESPONSE_LLM_BATCH]:
        prompt = f"""Competitor "{a['competitor']}" was featured in: "{a['title']}"

Client "{client}" wants to respond with a PR angle. Suggest ONE concrete story angle (max 25 words) the client could pitch. Output only the angle, no quotes."""
        angle = await _llm_call(prompt)
        if not angle:
            angle = f"Position {client} as a key player in this space with unique perspective."

        doc = {
            "type": "competitor_response",
            "client": client,
            "date": date_str,
            "article_url": a["url"],
            "article_title": a["title"],
            "competitor": a["competitor"],
            "suggested_angle": angle,
            "computed_at": datetime.now(timezone.utc),
        }
        await coll.update_one(
            {"type": "competitor_response", "client": client, "date": date_str, "article_url": a["url"]},
            {"$set": doc},
            upsert=True,
        )
        stored += 1

    return stored


# --- Run all for a client ---


async def run_pr_opportunities_batch(client: str) -> dict[str, Any]:
    """Run all 3 opportunity batches for client. Returns counts."""
    q = await compute_quote_opportunities(client)
    o = await compute_outreach_drafts(client)
    c = await compute_competitor_responses(client)
    return {"quote_alerts": q, "outreach_drafts": o, "competitor_responses": c}


async def run_pr_opportunities_all_clients() -> dict[str, Any]:
    """Run for all configured clients."""
    clients_list = await load_clients()
    results = []
    for c in clients_list:
        name = (c.get("name") or "").strip()
        if name:
            r = await run_pr_opportunities_batch(name)
            results.append({"client": name, **r})
    return {"results": results}


async def get_pr_opportunities(client: str, days: int = 7) -> dict[str, Any]:
    """Fetch stored opportunities for client. Read-only."""
    await get_mongo_client()
    from app.services.mongodb import get_db

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    db = get_db()
    coll = db[PR_OPPORTUNITIES_COLLECTION]
    cursor = coll.find({"client": client, "date": {"$gte": cutoff}}).sort("computed_at", -1)

    quote_alerts: list[dict] = []
    outreach_drafts: list[dict] = []
    competitor_responses: list[dict] = []
    last_computed_at: Optional[datetime] = None

    async for doc in cursor:
        d = {k: v for k, v in doc.items() if k != "_id"}
        if "computed_at" in d and hasattr(d.get("computed_at"), "isoformat"):
            d["computed_at"] = d["computed_at"].strftime("%Y-%m-%dT%H:%M:%SZ")
        t = doc.get("type", "")
        if t == "quote_alert":
            quote_alerts.append(d)
        elif t == "outreach_draft":
            outreach_drafts.append(d)
        elif t == "competitor_response":
            competitor_responses.append(d)
        ct = doc.get("computed_at")
        if isinstance(ct, datetime) and (last_computed_at is None or ct > last_computed_at):
            last_computed_at = ct

    out: dict[str, Any] = {
        "quote_alerts": quote_alerts,
        "outreach_drafts": outreach_drafts,
        "competitor_responses": competitor_responses,
    }
    if last_computed_at:
        out["last_computed_at"] = last_computed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return out
