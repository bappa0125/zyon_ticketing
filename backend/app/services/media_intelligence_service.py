"""Media Intelligence dashboard — coverage, feed, timeline, top publications, topics, by_domain.
Reads from article_documents + entity_mentions (single pipeline); no media_articles."""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.core.client_config_loader import get_entity_names, get_competitor_names, load_clients
from app.services.mongodb import get_mongo_client

ENTITY_MENTIONS_COLLECTION = "entity_mentions"
ARTICLE_DOCUMENTS_COLLECTION = "article_documents"
FEED_LIMIT = 100
TOP_PUBS_LIMIT = 15
TOPICS_LIMIT = 12


def _normalize_domain(source: str) -> str:
    """Normalize source to domain: lowercase, strip www."""
    if not source or not isinstance(source, str):
        return ""
    s = source.strip().lower()
    if s.startswith("www."):
        s = s[4:]
    # If it looks like a URL, take host only
    if "://" in s:
        s = s.split("://", 1)[1]
    if "/" in s:
        s = s.split("/", 1)[0]
    return s[:200]


def _parse_range(range_param: str) -> timedelta:
    if range_param == "24h":
        return timedelta(hours=24)
    if range_param == "7d":
        return timedelta(days=7)
    if range_param == "30d":
        return timedelta(days=30)
    return timedelta(days=7)


def _to_dt(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return None


def _date_str(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d")
    if isinstance(dt, str) and len(dt) >= 10:
        return dt[:10]
    return None


async def get_dashboard(
    client: str,
    range_param: str = "7d",
    domain_filter: Optional[str] = None,
) -> dict[str, Any]:
    """
    Return full dashboard from article_documents + entity_mentions.
    client: primary company name (from clients.yaml).
    range_param: 24h | 7d | 30d.
    domain_filter: optional domain (e.g. moneycontrol.com) to filter feed and coverage to that source.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    clients = await load_clients()
    client_obj = next(
        (c for c in clients if (c.get("name") or "").strip().lower() == client.strip().lower()),
        None,
    )
    if not client_obj:
        return {
            "coverage": [],
            "feed": [],
            "timeline": [],
            "top_publications": [],
            "topics": [],
            "by_domain": [],
            "client": client,
            "competitors": [],
        }

    client_name = (client_obj.get("name") or "").strip()
    entities = get_entity_names(client_obj)
    competitor_names = get_competitor_names(client_obj)
    delta = _parse_range(range_param)
    cutoff = datetime.now(timezone.utc) - delta

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]
    art_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    # Collect raw items from entity_mentions and article_documents (in range, for any of the entities)
    raw: list[dict[str, Any]] = []

    # 1. entity_mentions: entity (string) in entities
    try:
        cursor = em_coll.find(
            {
                "entity": {"$in": entities},
                "$or": [
                    {"published_at": {"$gte": cutoff}},
                    {"timestamp": {"$gte": cutoff}},
                ],
            }
        ).sort("published_at", -1).sort("timestamp", -1).limit(FEED_LIMIT * 2)
        async for doc in cursor:
            pub = doc.get("published_at") or doc.get("timestamp")
            raw.append({
                "_source": "entity_mentions",
                "title": doc.get("title") or "Untitled",
                "source": doc.get("source") or doc.get("source_domain") or "",
                "published_at": pub,
                "snippet": doc.get("summary") or doc.get("snippet") or "",
                "ai_summary": (doc.get("ai_summary") or "").strip() or None,
                "sentiment": doc.get("sentiment"),
                "url": (doc.get("url") or "").strip(),
                "url_note": (doc.get("url_note") or "").strip(),
                "entity": (doc.get("entity") or "").strip(),
                "id": str(doc.get("_id", "")),
            })
    except Exception:
        pass

    # 2. article_documents: entities (array) contains any of our entities
    try:
        cursor = art_coll.find(
            {
                "entities": {"$in": entities},
                "$or": [
                    {"published_at": {"$gte": cutoff}},
                    {"fetched_at": {"$gte": cutoff}},
                ],
            }
        ).sort("published_at", -1).sort("fetched_at", -1).limit(FEED_LIMIT * 2)
        async for doc in cursor:
            pub = doc.get("published_at") or doc.get("fetched_at")
            ents = doc.get("entities") or []
            entity_val = ents[0] if ents else ""
            for e in entities:
                if e in ents:
                    entity_val = e
                    break
            raw.append({
                "_source": "article_documents",
                "title": doc.get("title") or "Untitled",
                "source": doc.get("source_domain") or doc.get("source") or "",
                "published_at": pub,
                "snippet": (doc.get("summary") or (doc.get("article_text") or "")[:400]).strip(),
                "ai_summary": (doc.get("ai_summary") or "").strip() or None,
                "sentiment": doc.get("sentiment"),
                "url": (doc.get("url") or doc.get("url_resolved") or "").strip(),
                "url_note": (doc.get("url_note") or "").strip(),
                "entity": (entity_val or "").strip() if isinstance(entity_val, str) else "",
                "id": str(doc.get("_id", "")),
            })
    except Exception:
        pass

    # Dedupe by (url or title+source), sort by published_at desc; add normalized source_domain
    seen: set[str] = set()
    unified: list[dict[str, Any]] = []
    for r in sorted(raw, key=lambda x: _to_dt(x.get("published_at")) or datetime.min, reverse=True):
        url = (r.get("url") or "").strip().lower()
        key = url if url else ("meta:" + (r.get("title") or "") + "|" + (r.get("source") or ""))
        if key in seen:
            continue
        seen.add(key)
        r["source_domain"] = _normalize_domain(r.get("source") or "")
        unified.append(r)
        if len(unified) >= FEED_LIMIT:
            break

    # Build by_domain (coverage by source) from media_sources.yaml before applying domain filter
    try:
        from app.services.monitoring_ingestion.media_source_registry import load_media_sources
        config_sources = load_media_sources()
    except Exception:
        config_sources = []
    domain_to_name: dict[str, str] = {}
    for s in config_sources:
        d = _normalize_domain(s.get("domain") or "")
        if d:
            domain_to_name[d] = (s.get("name") or d)[:100]
    # Count per (domain, entity) from unified
    domain_entity_count: dict[str, dict[str, int]] = {}
    for r in unified:
        d = r.get("source_domain") or ""
        if not d:
            continue
        if d not in domain_entity_count:
            domain_entity_count[d] = {e: 0 for e in entities}
        e = r.get("entity") or ""
        if e in domain_entity_count[d]:
            domain_entity_count[d][e] += 1
    by_domain: list[dict[str, Any]] = []
    for d in domain_to_name:
        counts = domain_entity_count.get(d, {e: 0 for e in entities})
        total = sum(counts.values())
        by_domain.append({
            "domain": d,
            "name": domain_to_name[d],
            "total": total,
            "entities": counts,
        })
    by_domain.sort(key=lambda x: -x["total"])

    # Optional filter by domain for feed/coverage/timeline/top_pubs/topics
    if domain_filter:
        domain_norm = _normalize_domain(domain_filter)
        if domain_norm:
            unified = [r for r in unified if r.get("source_domain") == domain_norm]

    # Build coverage (count by entity)
    coverage_map: dict[str, int] = {e: 0 for e in entities}
    for r in unified:
        e = r.get("entity") or ""
        if e in coverage_map:
            coverage_map[e] += 1
    coverage = [{"entity": e, "mentions": coverage_map[e]} for e in entities]
    coverage.sort(key=lambda x: -x["mentions"])

    # Build feed items (include sentiment, summary = ai_summary or snippet, source_domain)
    feed: list[dict] = []
    for r in unified:
        pub = r.get("published_at")
        pub_iso = pub.isoformat() if isinstance(pub, datetime) else str(pub or "")[:50]
        entity_val = r.get("entity") or ""
        mention_type = "direct" if entity_val.strip().lower() == client_name.lower() else "competitor"
        url = (r.get("url") or "").strip()
        confidence = "verified" if url else "unverified"
        summary = (r.get("ai_summary") or "").strip() or (r.get("snippet") or "")[:400]
        feed.append({
            "id": r.get("id", ""),
            "publisher": (r.get("source") or "")[:200],
            "source_domain": r.get("source_domain") or "",
            "headline": (r.get("title") or "Untitled")[:500],
            "publish_time": pub_iso,
            "snippet": (r.get("snippet") or "")[:400],
            "summary": summary[:400],
            "sentiment": r.get("sentiment"),
            "mention_type": mention_type,
            "entity": entity_val,
            "confidence": confidence,
            "link": url,
            "url_note": r.get("url_note") or ("" if url else "Publisher link unavailable"),
        })

    # Timeline: by day per entity
    by_entity_date: dict[str, dict[str, int]] = {e: {} for e in entities}
    for r in unified:
        pub = r.get("published_at")
        d = _date_str(pub) if isinstance(pub, datetime) else (pub[:10] if isinstance(pub, str) and len(pub) >= 10 else None)
        e = r.get("entity") or ""
        if d and e in by_entity_date:
            by_entity_date[e][d] = by_entity_date[e].get(d, 0) + 1
    dates_in_range: list[str] = []
    d = (datetime.now(timezone.utc) - delta).date()
    end = datetime.now(timezone.utc).date()
    while d <= end:
        dates_in_range.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    timeline = []
    for date_str in dates_in_range:
        row: dict[str, Any] = {"date": date_str}
        for e in entities:
            row[e] = by_entity_date.get(e, {}).get(date_str, 0)
        timeline.append(row)

    # Top publications
    source_count: dict[str, int] = {}
    for r in unified:
        s = (r.get("source") or "Unknown").strip() or "Unknown"
        source_count[s] = source_count.get(s, 0) + 1
    top_publications = [
        {"source": s, "mentions": c}
        for s, c in sorted(source_count.items(), key=lambda x: -x[1])[:TOP_PUBS_LIMIT]
    ]

    # Topics (keyword extraction)
    import re
    stopwords = {
        "the", "and", "for", "with", "from", "that", "this", "has", "have", "are", "was", "were",
        "its", "said", "per", "will", "can", "not", "but", "they", "their", "about", "when", "which",
    }
    freq: dict[str, int] = {}
    for r in unified[:500]:
        text = f"{r.get('title', '')} {r.get('snippet', '')}".lower()
        words = re.findall(r"\b[a-z]{4,}\b", text)
        for w in words:
            if w not in stopwords and not w.isdigit():
                freq[w] = freq.get(w, 0) + 1
    topics = [{"topic": w, "mentions": c} for w, c in sorted(freq.items(), key=lambda x: -x[1])[:TOPICS_LIMIT]]

    return {
        "client": client_name,
        "competitors": competitor_names,
        "range": range_param,
        "coverage": coverage,
        "feed": feed,
        "timeline": timeline,
        "top_publications": top_publications,
        "topics": topics,
        "by_domain": by_domain,
    }
