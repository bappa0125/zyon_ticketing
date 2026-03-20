"""Media Intelligence dashboard — coverage, feed, timeline, top publications, topics, by_domain.
Reads from article_documents + entity_mentions (single pipeline); no media_articles."""
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from app.core.client_config_loader import get_entity_names, get_competitor_names, load_clients
from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client

logger = get_logger(__name__)

ENTITY_MENTIONS_COLLECTION = "entity_mentions"
ARTICLE_DOCUMENTS_COLLECTION = "article_documents"
FEED_LIMIT = 100
TOP_PUBS_LIMIT = 15
TOPICS_LIMIT = 12


def _strip_leading_www_variants(host: str) -> str:
    """
    Normalize hostname: www., www2., www360., etc.
    Many Indian publishers use www2.example.com which would not match config example.com otherwise.
    """
    h = (host or "").strip().lower()
    if not h:
        return ""
    changed = True
    while changed:
        changed = False
        if h.startswith("www."):
            h = h[4:]
            changed = True
        elif re.match(r"^www\d+\.", h):
            h = re.sub(r"^www\d+\.", "", h, count=1)
            changed = True
    return h[:200]


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
    if s.startswith("www."):
        s = s[4:]
    s = _strip_leading_www_variants(s)
    return s[:200]


def _domain_from_url(url: str) -> str:
    """Extract domain from URL for matching media_sources. Strips www. Never returns news.google.com."""
    if not url or not isinstance(url, str):
        return ""
    from urllib.parse import urlparse
    parsed = urlparse((url or "").strip())
    netloc = (parsed.netloc or "").split(":")[0].lower()
    if not netloc or netloc == "news.google.com":
        return ""
    netloc = _strip_leading_www_variants(netloc)
    return netloc[:200] if "." in netloc and " " not in netloc else ""


def _google_or_empty_url_host(url: str) -> bool:
    """True when stored URL is still an aggregator/redirect host — prefer source_domain from the row."""
    if not url or not isinstance(url, str):
        return True
    from urllib.parse import urlparse

    netloc = (urlparse(url.strip()).netloc or "").split(":")[0].lower()
    if not netloc:
        return True
    netloc = _strip_leading_www_variants(netloc)
    if netloc == "news.google.com":
        return True
    if netloc in ("google.com", "google.co.in", "google.co.uk"):
        return True
    if netloc.endswith(".cdn.ampproject.org") or netloc.endswith(".ampproject.org"):
        return True
    return False


def _effective_row_source_domain(r: dict[str, Any]) -> str:
    """
    Domain for Coverage-by-source mapping. Prefer real publisher host from URL; when URL is still
    Google News / google.com redirect, use normalized source field (entity_mentions.source_domain / article source_domain).
    """
    url_val = (r.get("url") or "").strip()
    src_norm = _normalize_domain(r.get("source") or "")
    url_dom = _domain_from_url(url_val) if url_val else ""
    if _google_or_empty_url_host(url_val) or not url_dom:
        return src_norm or url_dom
    return url_dom or src_norm


def _map_to_config_domain(domain: str, config_domains: set[str]) -> str | None:
    """
    Map a raw domain (from URL or DB) to the matching media_sources domain.
    Handles subdomains: m.economictimes.indiatimes.com -> economictimes.indiatimes.com.
    Handles www prefix: www.livemint.com -> livemint.com.
    Returns the config domain key to use, or None if no match.
    """
    if not domain or not isinstance(domain, str):
        return None
    d = domain.strip().lower()
    if not d or " " in d:
        return None
    d = _strip_leading_www_variants(d)
    if d in config_domains:
        return d
    for cfg in config_domains:
        if d == cfg or d.endswith("." + cfg):
            return cfg
    return None


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
        s = val.strip()
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
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


def _entity_lower_to_canonical(entities: Sequence[str]) -> dict[str, str]:
    """Map stripped lowercase entity -> canonical name from clients.yaml (for coverage keys)."""
    out: dict[str, str] = {}
    for e in entities:
        if not e or not isinstance(e, str):
            continue
        c = e.strip()
        if not c:
            continue
        out[c.lower()] = c
    return out


def _mongo_case_insensitive_entity_filter(field: str, entities: Sequence[str]) -> dict[str, Any]:
    """
    Build a Mongo filter fragment: match field (string or array of strings) to any entity, case-insensitive.
    Uses anchored regex per name so 'grow' does not match 'Groww' when names differ (still exact full-string match).
    """
    ors: list[dict[str, Any]] = []
    for e in entities:
        if not e or not isinstance(e, str):
            continue
        s = e.strip()
        if not s:
            continue
        # BSON Regex via re.compile — reliable for array fields (e.g. entities[]) across Mongo versions
        ors.append({field: re.compile(f"^{re.escape(s)}$", re.IGNORECASE)})
    if not ors:
        return {"_id": {"$exists": False}}
    return {"$or": ors} if len(ors) > 1 else ors[0]


async def _load_unified_mentions(
    *,
    em_coll,
    art_coll,
    entities: Sequence[str],
    cutoff: datetime,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Load and unify mentions from entity_mentions and article_documents.
    - One item per (url, entity) pair.
    - Sorted by published_at desc.
    - Optional limit on number of unified items returned.
    """
    raw: list[dict[str, Any]] = []
    elower = _entity_lower_to_canonical(entities)

    # 1. entity_mentions: entity matches any tracked name (case-insensitive); normalize to canonical for dashboard keys
    try:
        em_q = {
            "$and": [
                _mongo_case_insensitive_entity_filter("entity", entities),
                {
                    "$or": [
                        {"published_at": {"$gte": cutoff}},
                        {"timestamp": {"$gte": cutoff}},
                    ],
                },
            ]
        }
        cursor = em_coll.find(em_q).sort([("timestamp", -1), ("published_at", -1)])
        if limit is not None:
            cursor = cursor.limit(limit * 2)
        async for doc in cursor:
            raw_entity = (doc.get("entity") or "").strip()
            canonical = elower.get(raw_entity.lower())
            if not canonical:
                continue
            pub = doc.get("published_at") or doc.get("timestamp")
            raw.append(
                {
                    "_source": "entity_mentions",
                    "title": doc.get("title") or "Untitled",
                    "source": doc.get("source") or doc.get("source_domain") or "",
                    "published_at": pub,
                    "snippet": doc.get("summary") or doc.get("snippet") or "",
                    "ai_summary": (doc.get("ai_summary") or "").strip() or None,
                    "sentiment": doc.get("sentiment"),
                    "url": (doc.get("url") or "").strip(),
                    "url_original": (doc.get("url_original") or "").strip(),
                    "url_note": (doc.get("url_note") or "").strip(),
                    "entity": canonical,
                    "id": str(doc.get("_id", "")),
                    "content_quality": doc.get("content_quality") or "full_text",
                    "author": (doc.get("author") or "").strip()[:300] if doc.get("author") else None,
                }
            )
    except Exception as e:
        logger.warning("media_intelligence_entity_mentions_query_failed", error=str(e))

    # 2. article_documents: entities[] contains a tracked name (case-insensitive)
    try:
        art_q = {
            "$and": [
                _mongo_case_insensitive_entity_filter("entities", entities),
                {
                    "$or": [
                        {"published_at": {"$gte": cutoff}},
                        {"fetched_at": {"$gte": cutoff}},
                    ],
                },
            ]
        }
        cursor = art_coll.find(art_q).sort([("fetched_at", -1), ("published_at", -1)])
        if limit is not None:
            cursor = cursor.limit(limit * 2)
        async for doc in cursor:
            pub = doc.get("published_at") or doc.get("fetched_at")
            ents = doc.get("entities") or []
            article_text = (doc.get("article_text") or "").strip()
            content_quality = "snippet" if not article_text else "full_text"
            for entity_val in ents:
                if not isinstance(entity_val, str):
                    continue
                canonical = elower.get(entity_val.strip().lower())
                if not canonical:
                    continue
                raw.append(
                    {
                        "_source": "article_documents",
                        "title": doc.get("title") or "Untitled",
                        "source": doc.get("source_domain") or doc.get("source") or "",
                        "published_at": pub,
                        "snippet": (doc.get("summary") or (article_text[:400] if article_text else "")).strip(),
                        "ai_summary": (doc.get("ai_summary") or "").strip() or None,
                        "sentiment": doc.get("sentiment"),
                        "url": (doc.get("url") or doc.get("url_resolved") or "").strip(),
                        "url_original": (doc.get("url_original") or "").strip(),
                        "url_note": (doc.get("url_note") or "").strip(),
                        "entity": canonical,
                        "id": f"{doc.get('_id', '')}_{canonical}",
                        "content_quality": content_quality,
                        "author": (doc.get("author") or "").strip()[:300] if doc.get("author") else None,
                    }
                )
    except Exception as e:
        logger.warning("media_intelligence_article_documents_query_failed", error=str(e))

    # Dedupe by (url, entity). Prefer items WITH author (article_documents often have it; entity_mentions may not).
    def _sort_key(x: dict) -> tuple:
        has_author = 0 if (x.get("author") or "").strip() else 1
        pub = _to_dt(x.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc)
        return (has_author, -pub.timestamp())

    seen: set[str] = set()
    unified: list[dict[str, Any]] = []
    for r in sorted(raw, key=_sort_key):
        url = (r.get("url") or "").strip().lower()
        entity = (r.get("entity") or "").strip()
        key = (
            f"{url}|{entity}"
            if url and entity
            else (
                url
                or ("meta:" + (r.get("title") or "") + "|" + (r.get("source") or ""))
            )
        )
        if key in seen:
            continue
        seen.add(key)
        r["source_domain"] = _effective_row_source_domain(r)
        unified.append(r)
        if limit is not None and len(unified) >= limit:
            break

    return unified


async def get_mention_counts(
    client: str,
    range_param: str = "7d",
) -> dict[str, Any]:
    """
    Return true mention counts per entity (client + competitors) and total_mentions.
    Uses the same unified mention logic as the dashboard but without FEED_LIMIT.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db
    from app.core.client_config_loader import get_entity_names, get_competitor_names, load_clients

    clients = await load_clients()
    client_obj = next(
        (c for c in clients if (c.get("name") or "").strip().lower() == client.strip().lower()),
        None,
    )
    if not client_obj:
        return {"client": client, "competitors": [], "range": range_param, "entity_counts": {}, "total_mentions": 0}

    client_name = (client_obj.get("name") or "").strip()
    entities = get_entity_names(client_obj)
    competitor_names = get_competitor_names(client_obj)
    delta = _parse_range(range_param)
    cutoff = datetime.now(timezone.utc) - delta

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]
    art_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    unified = await _load_unified_mentions(
        em_coll=em_coll,
        art_coll=art_coll,
        entities=entities,
        cutoff=cutoff,
        limit=None,
    )

    counts: dict[str, int] = {e: 0 for e in entities}
    for r in unified:
        e = (r.get("entity") or "").strip()
        if e in counts:
            counts[e] += 1

    total = sum(counts.values())
    return {
        "client": client_name,
        "competitors": competitor_names,
        "range": range_param,
        "entity_counts": counts,
        "total_mentions": total,
    }


async def get_articles_for_entity(
    client: str,
    range_param: str,
    entity: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """
    Paginated list of articles/mentions for a specific entity (client or competitor)
    in the given range. Uses unified mentions; does not call any LLM.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db
    from app.core.client_config_loader import get_entity_names, get_competitor_names, load_clients

    clients = await load_clients()
    client_obj = next(
        (c for c in clients if (c.get("name") or "").strip().lower() == client.strip().lower()),
        None,
    )
    if not client_obj:
        return {
            "client": client,
            "entity": entity or client,
            "range": range_param,
            "total_articles": 0,
            "page": page,
            "page_size": page_size,
            "rows": [],
        }

    client_name = (client_obj.get("name") or "").strip()
    entities = get_entity_names(client_obj)
    competitor_names = get_competitor_names(client_obj)
    if not entities:
        return {
            "client": client_name,
            "entity": entity or client_name,
            "range": range_param,
            "total_articles": 0,
            "page": page,
            "page_size": page_size,
            "rows": [],
        }

    chosen_entity = (entity or client_name).strip()
    if chosen_entity not in entities:
        chosen_entity = client_name

    delta = _parse_range(range_param)
    cutoff = datetime.now(timezone.utc) - delta

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]
    art_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    unified = await _load_unified_mentions(
        em_coll=em_coll,
        art_coll=art_coll,
        entities=entities,
        cutoff=cutoff,
        limit=None,
    )

    # Filter to chosen entity
    filtered = [r for r in unified if (r.get("entity") or "").strip() == chosen_entity]
    total_articles = len(filtered)

    # Simple pagination in memory (safe for current data sizes)
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 25
    max_page_size = 100
    if page_size > max_page_size:
        page_size = max_page_size
    start = (page - 1) * page_size
    end = start + page_size
    page_items = filtered[start:end]

    rows: list[dict[str, Any]] = []
    for r in page_items:
        pub = r.get("published_at")
        pub_iso = pub.isoformat() if isinstance(pub, datetime) else str(pub or "")[:50]
        url = (r.get("url") or "").strip()
        summary = (r.get("ai_summary") or "").strip() or (r.get("snippet") or "")[:400]

        rows.append(
            {
                "id": r.get("id", ""),
                "entity": chosen_entity,
                "title": (r.get("title") or "Untitled")[:500],
                "summary": summary,
                "link": url,
                "source": (r.get("source") or "")[:200],
                "source_domain": r.get("source_domain") or "",
                "journalist": (r.get("author") or "").strip() if isinstance(r.get("author"), str) else None,
                "published_at": pub_iso,
                "sentiment": r.get("sentiment"),
            }
        )

    return {
        "client": client_name,
        "competitors": competitor_names,
        "entity": chosen_entity,
        "range": range_param,
        "total_articles": total_articles,
        "page": page,
        "page_size": page_size,
        "rows": rows,
    }


async def get_dashboard(
    client: str,
    range_param: str = "7d",
    domain_filter: Optional[str] = None,
    content_quality: Optional[str] = None,
) -> dict[str, Any]:
    """
    Return full dashboard from article_documents + entity_mentions.
    client: primary company name (from clients.yaml).
    range_param: 24h | 7d | 30d.
    domain_filter: optional domain (e.g. moneycontrol.com) to filter feed and coverage to that source.
    content_quality: optional filter for feed — "full_text" | "snippet" | None (all).
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
            "meta": {"unified_mentions_count": 0, "article_documents_in_window": 0, "media_sources_count": 0},
        }

    client_name = (client_obj.get("name") or "").strip()
    entities = get_entity_names(client_obj)
    competitor_names = get_competitor_names(client_obj)
    delta = _parse_range(range_param)
    cutoff = datetime.now(timezone.utc) - delta

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]
    art_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    # Load full unified for coverage/total/by_domain (no 100 cap). Feed limited to FEED_LIMIT for display.
    unified = await _load_unified_mentions(
        em_coll=em_coll,
        art_coll=art_coll,
        entities=entities,
        cutoff=cutoff,
        limit=None,
    )

    # Build by_domain (coverage by source) from media_sources.yaml before applying domain filter
    try:
        from app.services.monitoring_ingestion.media_source_registry import load_media_sources
        config_sources = load_media_sources()
    except Exception:
        config_sources = []
    domain_to_name: dict[str, str] = {}
    config_domain_set: set[str] = set()
    for s in config_sources:
        d = _normalize_domain(s.get("domain") or "")
        if d:
            domain_to_name[d] = (s.get("name") or d)[:100]
            config_domain_set.add(d)
    # Count per (domain, entity) from unified — map raw source_domain to config domain (handles subdomains)
    # Entity match is case-insensitive (entity_mentions may have "Zerodha" or "zerodha")
    entity_lower_to_canonical: dict[str, str] = {e.strip().lower(): e.strip() for e in entities if e and isinstance(e, str)}
    domain_entity_count: dict[str, dict[str, int]] = {}
    for r in unified:
        raw_d = r.get("source_domain") or ""
        if not raw_d:
            continue
        d = _map_to_config_domain(raw_d, config_domain_set)
        if d is None:
            continue
        if d not in domain_entity_count:
            domain_entity_count[d] = {e: 0 for e in entities}
        raw_entity = (r.get("entity") or "").strip()
        e_canonical = entity_lower_to_canonical.get(raw_entity.lower()) if raw_entity else None
        if e_canonical and e_canonical in domain_entity_count[d]:
            domain_entity_count[d][e_canonical] += 1
    by_domain: list[dict[str, Any]] = []
    # How many article_documents landed in this time window per config domain (any topic).
    # Helps tell "ingestion gap" (0 indexed) vs "no entity hits" (indexed > 0 but total 0).
    articles_indexed_by_domain: dict[str, int] = {d: 0 for d in domain_to_name}
    articles_indexed_scan_error: str | None = None
    try:
        acursor = art_coll.find(
            {
                "$or": [
                    {"published_at": {"$gte": cutoff}},
                    {"fetched_at": {"$gte": cutoff}},
                ],
            },
            projection={"url": 1, "url_resolved": 1, "source_domain": 1},
        )
        async for doc in acursor:
            u = (doc.get("url") or doc.get("url_resolved") or "").strip()
            raw = _domain_from_url(u) if u else ""
            if not raw:
                raw = _normalize_domain(doc.get("source_domain") or "")
            mapped = _map_to_config_domain(raw, config_domain_set)
            if mapped and mapped in articles_indexed_by_domain:
                articles_indexed_by_domain[mapped] += 1
    except Exception as e:
        articles_indexed_scan_error = str(e)
        logger.warning("media_intelligence_articles_indexed_scan_failed", error=str(e))

    for d in domain_to_name:
        counts = domain_entity_count.get(d, {e: 0 for e in entities})
        total = sum(counts.values())
        by_domain.append({
            "domain": d,
            "name": domain_to_name[d],
            "total": total,
            "entities": counts,
            "articles_indexed": articles_indexed_by_domain.get(d, 0),
        })
    by_domain.sort(key=lambda x: -x["total"])
    article_documents_in_window = sum(articles_indexed_by_domain.values())

    # Optional filter by domain for feed/coverage/timeline/top_pubs/topics
    if domain_filter:
        domain_norm = _normalize_domain(domain_filter)
        if domain_norm and domain_norm in config_domain_set:
            def _matches_domain(r: dict) -> bool:
                raw = r.get("source_domain") or ""
                mapped = _map_to_config_domain(raw, config_domain_set) if raw else None
                return mapped == domain_norm
            unified = [r for r in unified if _matches_domain(r)]

    # Optional filter by content_quality for feed (coverage/timeline stay full)
    if content_quality in ("full_text", "snippet"):
        unified_for_feed = [r for r in unified if (r.get("content_quality") or "full_text") == content_quality]
    else:
        unified_for_feed = unified

    # Build coverage (count by entity)
    coverage_map: dict[str, int] = {e: 0 for e in entities}
    for r in unified:
        e = r.get("entity") or ""
        if e in coverage_map:
            coverage_map[e] += 1
    coverage = [{"entity": e, "mentions": coverage_map[e]} for e in entities]
    coverage.sort(key=lambda x: -x["mentions"])

    # Per-URL set of entities (for also_mentions)
    url_entities: dict[str, set[str]] = {}
    for r in unified_for_feed:
        u = (r.get("url") or "").strip().lower()
        e = (r.get("entity") or "").strip()
        if u and e:
            url_entities.setdefault(u, set()).add(e)

    # Build feed items (include sentiment, summary, content_quality, also_mentions). Cap at FEED_LIMIT for display.
    feed: list[dict] = []
    for r in unified_for_feed[:FEED_LIMIT]:
        pub = r.get("published_at")
        pub_iso = pub.isoformat() if isinstance(pub, datetime) else str(pub or "")[:50]
        entity_val = r.get("entity") or ""
        mention_type = "direct" if entity_val.strip().lower() == client_name.lower() else "competitor"
        url = (r.get("url") or "").strip()
        url_lower = url.lower()
        confidence = "verified" if url else "unverified"
        summary = (r.get("ai_summary") or "").strip() or (r.get("snippet") or "")[:400]
        others = (url_entities.get(url_lower) or set()) - {entity_val}
        also_mentions = sorted(others) if others else []
        feed.append({
            "id": r.get("id", ""),
            "publisher": (r.get("source") or "")[:200],
            "source_domain": r.get("source_domain") or "",
            "headline": (r.get("title") or "Untitled")[:500],
            "publish_time": pub_iso,
            "snippet": (r.get("snippet") or "")[:400],
            "summary": summary[:400],
            "ai_summary": (r.get("ai_summary") or "").strip()[:400] or None,
            "sentiment": r.get("sentiment"),
            "mention_type": mention_type,
            "entity": entity_val,
            "confidence": confidence,
            "link": url,
            "url_original": (r.get("url_original") or "").strip(),
            "url_note": r.get("url_note") or ("" if url else "Publisher link unavailable"),
            "content_quality": r.get("content_quality") or "full_text",
            "also_mentions": also_mentions,
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

    # Deterministic PR summary from Coverage by Source (no LLM)
    pr_summary = _build_pr_summary(
        client_name=client_name,
        competitor_names=competitor_names,
        range_param=range_param,
        by_domain=by_domain,
        topics=topics,
        coverage=coverage,
    )

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
        "pr_summary": pr_summary,
        "meta": {
            "unified_mentions_count": len(unified),
            "article_documents_in_window": article_documents_in_window,
            "media_sources_count": len(domain_to_name),
            "articles_indexed_scan_error": articles_indexed_scan_error,
        },
    }


def _build_pr_summary(
    *,
    client_name: str,
    competitor_names: Sequence[str],
    range_param: str,
    by_domain: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
) -> str:
    """
    Build a deterministic PR agency summary from Coverage by Source data.
    No LLM - pure Python template from the table data.
    """
    period_label = {"24h": "last 24 hours", "7d": "last 7 days", "30d": "last 30 days"}.get(
        range_param, f"last {range_param}"
    )
    total_mentions = sum(c.get("mentions", 0) for c in coverage)
    sources_with_data = [r for r in by_domain if r.get("total", 0) > 0]
    top_sources = sorted(sources_with_data, key=lambda x: -x.get("total", 0))[:8]
    top_topics = [t.get("topic", "") for t in topics[:10] if t.get("topic")]

    # Opportunities: sources where client has 0 but competitors have mentions
    opportunities = [
        r.get("name") or r.get("domain", "")
        for r in sources_with_data
        if (r.get("entities", {}) or {}).get(client_name, 0) == 0 and r.get("total", 0) >= 2
    ][:6]

    lines: list[str] = []

    # Executive summary
    if total_mentions == 0:
        lines.append(f"## Executive summary\nNo mentions for {client_name} or competitors in the {period_label}.")
    else:
        lines.append(
            f"## Executive summary\n"
            f"In the {period_label}, {len(sources_with_data)} sources covered {client_name} and competitors "
            f"with {total_mentions} total mentions."
        )

    # Top sources
    if top_sources:
        lines.append("\n## Top sources by coverage")
        for r in top_sources[:6]:
            name = r.get("name") or r.get("domain", "")
            total = r.get("total", 0)
            client_count = (r.get("entities") or {}).get(client_name, 0)
            lines.append(f"- **{name}**: {total} mentions ({client_count} for {client_name})")

    # Opportunities
    if opportunities:
        lines.append("\n## High-priority outlets (opportunity)")
        lines.append(
            f"These outlets wrote about competitors but not {client_name}: "
            + ", ".join(opportunities)
            + ". Target for PR outreach."
        )

    # Trending topics
    if top_topics:
        lines.append("\n## Trending topics")
        lines.append("Top keywords in coverage: " + ", ".join(top_topics[:8]) + ".")

    # Recommendations
    lines.append("\n## Recommendations")
    if opportunities:
        lines.append(
            f"1. Prioritize outreach to {opportunities[0]}" + (f" and {opportunities[1]}" if len(opportunities) > 1 else "") + "."
        )
    if top_topics:
        lines.append(f"2. Pitch stories around: {top_topics[0]}, {top_topics[1]}" + (f", {top_topics[2]}" if len(top_topics) > 2 else "") + ".")
    lines.append("3. Monitor share of voice vs competitors in top sources.")
    lines.append("4. Run media monitoring regularly to track coverage changes.")

    return "\n".join(lines).strip()


