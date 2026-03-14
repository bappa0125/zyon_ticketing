"""PR Report batch service — outreach targets, benchmarks, sentiment alerts.
Deterministic, no LLM. Reads from entity_mentions + article_documents. Writes to pr_daily_snapshots.
No changes to ingestion pipeline or entity detection."""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.core.client_config_loader import get_entity_names, get_competitor_names, load_clients
from app.services.mongodb import get_mongo_client

ENTITY_MENTIONS_COLLECTION = "entity_mentions"
ARTICLE_DOCUMENTS_COLLECTION = "article_documents"
PR_DAILY_SNAPSHOTS_COLLECTION = "pr_daily_snapshots"
PR_PRESS_RELEASES_COLLECTION = "pr_press_releases"
PR_PRESS_RELEASE_PICKUPS_COLLECTION = "pr_press_release_pickups"

# Crisis threshold: >30% negative in a day with 5+ total
SENTIMENT_ALERT_NEG_PCT = 30
SENTIMENT_ALERT_MIN_MENTIONS = 5


def _sentiment_score(s: Any) -> float:
    """Map sentiment to numeric: positive=1, negative=-1, neutral=0."""
    v = (str(s) if s else "neutral").strip().lower()
    if v in ("positive", "pos"):
        return 1.0
    if v in ("negative", "neg"):
        return -1.0
    return 0.0


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
    competitor_names = get_competitor_names(client_obj)
    return client_name, entities, competitor_names


async def _load_unified_for_date(
    client: str, date_str: str
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]], list[dict[str, Any]]]:
    """Load unified-style data for a single day. Returns (unified, domain_entity_count, by_domain)."""
    await get_mongo_client()
    from app.services.mongodb import get_db
    from app.services.monitoring_ingestion.media_source_registry import load_media_sources

    client_name, entities, _ = await _get_client_entities(client)
    if not client_name or not entities:
        return [], {}, []

    start = datetime.fromisoformat(date_str + "T00:00:00+00:00")
    end = start + timedelta(days=1)

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]
    art_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    raw: list[dict] = []
    match_em = {
        "entity": {"$in": entities},
        "$or": [
            {"published_at": {"$gte": start, "$lt": end}},
            {"timestamp": {"$gte": start, "$lt": end}},
        ],
    }
    async for doc in em_coll.find(match_em):
        raw.append({
            "url": (doc.get("url") or "").strip(),
            "source": doc.get("source") or doc.get("source_domain") or "",
            "source_domain": doc.get("source_domain") or "",
            "entity": (doc.get("entity") or "").strip(),
            "sentiment": doc.get("sentiment"),
            "title": doc.get("title") or "Untitled",
        })

    match_art = {
        "entities": {"$in": entities},
        "$or": [
            {"published_at": {"$gte": start, "$lt": end}},
            {"fetched_at": {"$gte": start, "$lt": end}},
        ],
    }
    async for doc in art_coll.find(match_art):
        for e in (doc.get("entities") or []):
            if e in entities:
                raw.append({
                    "url": (doc.get("url") or doc.get("url_resolved") or "").strip(),
                    "source": doc.get("source_domain") or doc.get("source") or "",
                    "source_domain": (doc.get("source_domain") or "")[:200],
                    "entity": str(e),
                    "sentiment": doc.get("sentiment"),
                    "title": doc.get("title") or "Untitled",
                })
                break

    # Dedupe by url|entity
    seen: set[str] = set()
    unified: list[dict] = []
    for r in raw:
        k = f"{(r.get('url') or '').lower()}|{r.get('entity') or ''}"
        if k in seen:
            continue
        seen.add(k)
        unified.append(r)

    # Build domain counts (simplified - use source_domain as domain key)
    domain_counts: dict[str, dict[str, int]] = {}
    config_sources = load_media_sources()
    domain_to_name: dict[str, str] = {}
    for s in config_sources:
        d = (s.get("domain") or "").strip().lower()
        if d:
            domain_to_name[d] = (s.get("name") or d)[:100]

    def _norm_domain(sd: str) -> str:
        if not sd:
            return ""
        d = sd.strip().lower()
        if d.startswith("www."):
            d = d[4:]
        if d in domain_to_name:
            return d
        for cfg in domain_to_name:
            if d == cfg or d.endswith("." + cfg):
                return cfg
        return d

    for r in unified:
        sd = _norm_domain(r.get("source_domain") or r.get("source") or "")
        if not sd:
            continue
        if sd not in domain_to_name and sd not in domain_counts:
            domain_to_name[sd] = sd
        if sd not in domain_counts:
            domain_counts[sd] = {e: 0 for e in entities}
        ent = (r.get("entity") or "").strip()
        if ent in domain_counts[sd]:
            domain_counts[sd][ent] += 1

    by_domain = [
        {"domain": d, "name": domain_to_name.get(d, d), "total": sum(domain_counts[d].values()), "entities": domain_counts[d]}
        for d in domain_to_name
        if d in domain_counts
    ]
    by_domain.sort(key=lambda x: -x["total"])

    return unified, domain_counts, by_domain


async def _load_unified_for_range(
    client: str, from_date: str, to_date: str
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]], list[dict[str, Any]]]:
    """Load unified data for date range; aggregate by_domain over the range."""
    await get_mongo_client()
    from app.services.mongodb import get_db
    from app.services.monitoring_ingestion.media_source_registry import load_media_sources

    client_name, entities, _ = await _get_client_entities(client)
    if not client_name or not entities:
        return [], {}, []

    start = datetime.fromisoformat(from_date + "T00:00:00+00:00")
    end = datetime.fromisoformat(to_date + "T23:59:59+00:00") + timedelta(seconds=1)

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]
    art_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    raw: list[dict] = []
    match_em = {
        "entity": {"$in": entities},
        "$or": [
            {"published_at": {"$gte": start, "$lt": end}},
            {"timestamp": {"$gte": start, "$lt": end}},
        ],
    }
    async for doc in em_coll.find(match_em):
        raw.append({
            "url": (doc.get("url") or "").strip(),
            "source": doc.get("source") or doc.get("source_domain") or "",
            "source_domain": doc.get("source_domain") or "",
            "entity": (doc.get("entity") or "").strip(),
            "sentiment": doc.get("sentiment"),
            "title": doc.get("title") or "Untitled",
        })

    match_art = {
        "entities": {"$in": entities},
        "$or": [
            {"published_at": {"$gte": start, "$lt": end}},
            {"fetched_at": {"$gte": start, "$lt": end}},
        ],
    }
    async for doc in art_coll.find(match_art):
        for e in (doc.get("entities") or []):
            if e in entities:
                raw.append({
                    "url": (doc.get("url") or doc.get("url_resolved") or "").strip(),
                    "source": doc.get("source_domain") or doc.get("source") or "",
                    "source_domain": (doc.get("source_domain") or "")[:200],
                    "entity": str(e),
                    "sentiment": doc.get("sentiment"),
                    "title": doc.get("title") or "Untitled",
                })
                break

    seen: set[str] = set()
    unified: list[dict] = []
    for r in raw:
        k = f"{(r.get('url') or '').lower()}|{r.get('entity') or ''}"
        if k in seen:
            continue
        seen.add(k)
        unified.append(r)

    config_sources = load_media_sources()
    domain_to_name: dict[str, str] = {}
    for s in config_sources:
        d = (s.get("domain") or "").strip().lower()
        if d:
            domain_to_name[d] = (s.get("name") or d)[:100]

    def _norm_domain(sd: str) -> str:
        if not sd:
            return ""
        d = sd.strip().lower()
        if d.startswith("www."):
            d = d[4:]
        if d in domain_to_name:
            return d
        for cfg in domain_to_name:
            if d == cfg or d.endswith("." + cfg):
                return cfg
        return d

    domain_counts: dict[str, dict[str, int]] = {}
    for r in unified:
        sd = _norm_domain(r.get("source_domain") or r.get("source") or "")
        if not sd:
            continue
        if sd not in domain_to_name and sd not in domain_counts:
            domain_to_name[sd] = sd
        if sd not in domain_counts:
            domain_counts[sd] = {e: 0 for e in entities}
        ent = (r.get("entity") or "").strip()
        if ent in domain_counts[sd]:
            domain_counts[sd][ent] += 1

    by_domain = [
        {"domain": d, "name": domain_to_name.get(d, d), "total": sum(domain_counts[d].values()), "entities": domain_counts[d]}
        for d in domain_to_name
        if d in domain_counts
    ]
    by_domain.sort(key=lambda x: -x["total"])
    return unified, domain_counts, by_domain


OUTREACH_DAYS_BACK = 7


async def compute_outreach_targets(client: str, date_str: str, days_back: int = 1) -> list[dict[str, Any]]:
    """Outlets where client=0 and competitors>0. Use days_back>1 for multi-day aggregation."""
    if days_back > 1:
        end_dt = datetime.fromisoformat(date_str + "T00:00:00+00:00")
        start_dt = end_dt - timedelta(days=days_back - 1)
        from_str = start_dt.strftime("%Y-%m-%d")
        _, _, by_domain = await _load_unified_for_range(client, from_str, date_str)
    else:
        _, _, by_domain = await _load_unified_for_date(client, date_str)
    client_name, _, _ = await _get_client_entities(client)
    if not client_name:
        return []

    targets = []
    for row in by_domain:
        ents = row.get("entities") or {}
        client_count = ents.get(client_name, 0)
        if client_count > 0:
            continue
        total = row.get("total", 0)
        if total < 1:
            continue
        comp_total = total - client_count
        targets.append({
            "outlet": row.get("name") or row.get("domain", ""),
            "domain": row.get("domain", ""),
            "client_mentions": 0,
            "competitor_mentions": comp_total,
            "total": total,
        })
    targets.sort(key=lambda x: -x["total"])
    return targets[:20]


async def compute_benchmarks(client: str, date_str: str) -> list[dict[str, Any]]:
    """Mentions, sentiment avg, share of voice per entity. Deterministic."""
    unified, _, _ = await _load_unified_for_date(client, date_str)
    _, entities, _ = await _get_client_entities(client)
    if not entities:
        return []

    total_mentions = len(unified)
    counts: dict[str, int] = {e: 0 for e in entities}
    sentiment_sum: dict[str, float] = {e: 0.0 for e in entities}
    for r in unified:
        e = (r.get("entity") or "").strip()
        if e in counts:
            counts[e] += 1
            sentiment_sum[e] += _sentiment_score(r.get("sentiment"))

    benchmarks = []
    for e in entities:
        c = counts.get(e, 0)
        savg = (sentiment_sum.get(e, 0) / c) if c > 0 else 0.0
        sov = (100.0 * c / total_mentions) if total_mentions > 0 else 0.0
        benchmarks.append({
            "entity": e,
            "mentions": c,
            "sentiment_avg": round(savg, 2),
            "share_of_voice_pct": round(sov, 1),
        })
    benchmarks.sort(key=lambda x: -x["mentions"])
    return benchmarks


async def compute_sentiment_alerts(client: str, date_str: str) -> list[dict[str, Any]]:
    """Detect negative spike. Deterministic."""
    unified, _, _ = await _load_unified_for_date(client, date_str)
    client_name, _, _ = await _get_client_entities(client)
    if not client_name:
        return []

    client_mentions = [r for r in unified if (r.get("entity") or "").strip() == client_name]
    if len(client_mentions) < SENTIMENT_ALERT_MIN_MENTIONS:
        return []

    pos = sum(1 for r in client_mentions if _sentiment_score(r.get("sentiment")) > 0)
    neg = sum(1 for r in client_mentions if _sentiment_score(r.get("sentiment")) < 0)
    neu = len(client_mentions) - pos - neg
    neg_pct = (100.0 * neg / len(client_mentions)) if client_mentions else 0

    alerts = []
    if neg_pct >= SENTIMENT_ALERT_NEG_PCT:
        alerts.append({
            "alert_type": "negative_spike",
            "severity": "high" if neg_pct >= 50 else "medium",
            "negative_pct": round(neg_pct, 1),
            "negative_count": neg,
            "total_mentions": len(client_mentions),
        })
    return alerts


async def run_daily_snapshot(client: str, date_str: str) -> dict[str, Any]:
    """Compute and store daily snapshot. No LLM."""
    await get_mongo_client()
    from app.services.mongodb import get_db

    client_name, _, _ = await _get_client_entities(client)
    if not client_name:
        return {"client": client, "date": date_str, "stored": False, "reason": "client_not_found"}

    outreach = await compute_outreach_targets(client, date_str, days_back=OUTREACH_DAYS_BACK)
    benchmarks = await compute_benchmarks(client, date_str)
    alerts = await compute_sentiment_alerts(client, date_str)

    snapshot = {
        "client": client_name,
        "date": date_str,
        "computed_at": datetime.now(timezone.utc),
        "outreach_targets": outreach,
        "benchmarks": benchmarks,
        "sentiment_alerts": alerts,
    }

    db = get_db()
    coll = db[PR_DAILY_SNAPSHOTS_COLLECTION]
    await coll.update_one(
        {"client": client_name, "date": date_str},
        {"$set": snapshot},
        upsert=True,
    )
    return {"client": client_name, "date": date_str, "stored": True}


async def run_daily_snapshot_all_clients(date_str: Optional[str] = None) -> dict[str, Any]:
    """Run snapshot for all clients. Batch job."""
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    clients_list = await load_clients()
    results = []
    for c in clients_list:
        name = (c.get("name") or "").strip()
        if name:
            r = await run_daily_snapshot(name, date_str)
            results.append(r)
    return {"date": date_str, "clients_processed": len(results), "results": results}


async def get_snapshots(
    client: str, from_date: str, to_date: str
) -> list[dict[str, Any]]:
    """Fetch stored snapshots for date range. Read-only."""
    await get_mongo_client()
    from app.services.mongodb import get_db

    client_name, _, _ = await _get_client_entities(client)
    if not client_name:
        return []

    db = get_db()
    coll = db[PR_DAILY_SNAPSHOTS_COLLECTION]
    cursor = coll.find(
        {"client": client_name, "date": {"$gte": from_date, "$lte": to_date}}
    ).sort("date", -1)
    return [doc async for doc in cursor]


# ----- Press release pickup (P2) -----


async def add_press_release(client: str, url: str, title: str, published_at: str) -> dict[str, Any]:
    """Add a press release. No schema change to existing collections."""
    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    coll = db[PR_PRESS_RELEASES_COLLECTION]
    doc = {
        "client": client,
        "url": (url or "").strip()[:2000],
        "title": (title or "").strip()[:500],
        "published_at": published_at[:10] if published_at else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "created_at": datetime.now(timezone.utc),
    }
    res = await coll.insert_one(doc)
    return {"id": str(res.inserted_id), "client": client}


async def list_press_releases(client: str, limit: int = 50) -> list[dict[str, Any]]:
    """List press releases for client."""
    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    coll = db[PR_PRESS_RELEASES_COLLECTION]
    cursor = coll.find({"client": client}).sort("published_at", -1).limit(limit)
    return [
        {"id": str(d["_id"]), "url": d.get("url"), "title": d.get("title"), "published_at": d.get("published_at")}
        async for d in cursor
    ]


async def compute_press_release_pickups(client: str, date_str: Optional[str] = None) -> dict[str, Any]:
    """Find articles published after each PR (same client). Deterministic batch."""
    await get_mongo_client()
    from app.services.mongodb import get_db

    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    db = get_db()
    pr_coll = db[PR_PRESS_RELEASES_COLLECTION]
    pickup_coll = db[PR_PRESS_RELEASE_PICKUPS_COLLECTION]
    em_coll = db[ENTITY_MENTIONS_COLLECTION]

    client_name, entities, _ = await _get_client_entities(client)
    if not client_name:
        return {"client": client, "date": date_str, "pickups_found": 0}

    pr_date = datetime.fromisoformat(date_str + "T00:00:00+00:00")
    cursor = pr_coll.find({"client": client_name, "published_at": {"$lte": date_str}})
    pickups_total = 0

    async for pr in cursor:
        pr_id = str(pr["_id"])
        pr_pub = pr.get("published_at") or ""
        if not pr_pub or len(pr_pub) < 10:
            continue
        try:
            pr_dt = datetime.fromisoformat(pr_pub[:10] + "T00:00:00+00:00")
        except Exception:
            continue

        # Articles with client mention, published after PR (within date range)
        end_range = pr_date + timedelta(days=1)
        match = {
            "entity": client_name,
            "published_at": {"$gt": pr_dt, "$lte": end_range},
        }

        async for em in em_coll.find(match).limit(50):
            url = (em.get("url") or "").strip()
            if not url:
                continue
            existing = await pickup_coll.find_one({"press_release_id": pr_id, "article_url": url})
            if existing:
                continue
            await pickup_coll.insert_one({
                "press_release_id": pr_id,
                "client": client_name,
                "article_url": url,
                "article_title": (em.get("title") or "")[:500],
                "published_at": em.get("published_at"),
                "matched_at": datetime.now(timezone.utc),
            })
            pickups_total += 1

    return {"client": client_name, "date": date_str, "pickups_found": pickups_total}


async def get_press_release_pickups(client: str, limit: int = 100) -> list[dict[str, Any]]:
    """Fetch pickups for client's press releases."""
    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    pr_coll = db[PR_PRESS_RELEASES_COLLECTION]
    pickup_coll = db[PR_PRESS_RELEASE_PICKUPS_COLLECTION]

    pr_ids = [d["_id"] async for d in pr_coll.find({"client": client}).distinct("_id")]
    if not pr_ids:
        return []

    cursor = pickup_coll.find(
        {"client": client, "press_release_id": {"$in": [str(pid) for pid in pr_ids]}}
    ).sort("published_at", -1).limit(limit)
    return [
        {
            "press_release_id": d.get("press_release_id"),
            "article_url": d.get("article_url"),
            "article_title": d.get("article_title"),
            "published_at": str(d.get("published_at", ""))[:19] if d.get("published_at") else "",
        }
        async for d in cursor
    ]
