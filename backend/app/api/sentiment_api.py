"""Sentiment Summary API — aggregate sentiment counts and article mentions for media coverage.

Supports entity_mentions (main pipeline: RSS → article_documents → entity_mentions)
and media_articles. Default source=entity_mentions so Sentiment page reflects
current monitoring pipeline.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Query

from app.services.mongodb import get_mongo_client
from app.services.media_intelligence_service import get_dashboard

router = APIRouter(tags=["sentiment"])

MEDIA_ARTICLES = "media_articles"
ENTITY_MENTIONS = "entity_mentions"
SOCIAL_POSTS = "social_posts"

# Sentiment sources for Sentiment UI (Pulse)
SOURCE_ALL = "all"
SOURCE_NEWS = "news"
SOURCE_FORUMS = "forums"
SOURCE_REDDIT = "reddit"
SOURCE_YOUTUBE = "youtube"


def _norm_source(raw: Optional[str]) -> str:
    s = (raw or SOURCE_ALL).strip().lower()
    if s in (SOURCE_ALL, SOURCE_NEWS, SOURCE_FORUMS, SOURCE_REDDIT, SOURCE_YOUTUBE):
        return s
    return SOURCE_ALL


async def _resolve_entities_for_client(client: str) -> list[str]:
    if not client or not client.strip():
        return []
    from app.core.client_config_loader import get_entity_names, load_clients

    clients = await load_clients()
    client_obj = next(
        (c for c in clients if (c.get("name") or "").strip().lower() == client.strip().lower()),
        None,
    )
    if not client_obj:
        return []
    return get_entity_names(client_obj) or []


def _source_match_filter(source: str) -> tuple[str, dict[str, Any]]:
    """
    Return (collection_name, mongo_match_fragment) for a given source.
    - news/forums: entity_mentions.type = article/forum
    - reddit/youtube: social_posts.platform = reddit/youtube
    """
    if source == SOURCE_NEWS:
        return ENTITY_MENTIONS, {"type": {"$in": ["article", "news"]}}
    if source == SOURCE_FORUMS:
        return ENTITY_MENTIONS, {"type": "forum"}
    if source == SOURCE_REDDIT:
        return SOCIAL_POSTS, {"platform": "reddit"}
    if source == SOURCE_YOUTUBE:
        return SOCIAL_POSTS, {"platform": "youtube"}
    return ENTITY_MENTIONS, {}  # all defaults to entity_mentions (legacy behavior)


def _sentiment_pipeline(match: dict) -> list:
    # Case-insensitive sentiment bucketization (handles "Positive"/"NEGATIVE", etc.).
    sent_norm = {"$toLower": {"$ifNull": ["$sentiment", ""]}}
    sent_bucket = {
        "$cond": [
            {"$in": [sent_norm, ["positive", "neutral", "negative"]]},
            sent_norm,
            "neutral",  # treat unknown labels as neutral so bars always split
        ]
    }
    return [
        {"$match": match},
        {"$match": {"sentiment": {"$exists": True, "$ne": None, "$ne": ""}}},
        {
            "$group": {
                "_id": "$entity",
                "positive": {"$sum": {"$cond": [{"$eq": [sent_bucket, "positive"]}, 1, 0]}},
                "neutral": {"$sum": {"$cond": [{"$eq": [sent_bucket, "neutral"]}, 1, 0]}},
                "negative": {"$sum": {"$cond": [{"$eq": [sent_bucket, "negative"]}, 1, 0]}},
            }
        },
        {"$project": {"entity": "$_id", "positive": 1, "neutral": 1, "negative": 1, "_id": 0}},
        {"$sort": {"entity": 1}},
    ]


def _narrative_sentiment_pipeline(match: dict) -> list:
    """
    Aggregate sentiment counts by (narrative_primary, entity).
    Requires fields: entity, sentiment, narrative_primary.
    """
    sent_norm = {"$toLower": {"$ifNull": ["$sentiment", ""]}}
    sent_bucket = {
        "$cond": [
            {"$in": [sent_norm, ["positive", "neutral", "negative"]]},
            sent_norm,
            "neutral",
        ]
    }
    return [
        {"$match": match},
        {"$match": {"sentiment": {"$exists": True, "$ne": None, "$ne": ""}}},
        {"$match": {"narrative_primary": {"$exists": True, "$ne": None, "$ne": ""}}},
        {
            "$group": {
                "_id": {"narrative": "$narrative_primary", "entity": "$entity"},
                "positive": {"$sum": {"$cond": [{"$eq": [sent_bucket, "positive"]}, 1, 0]}},
                "neutral": {"$sum": {"$cond": [{"$eq": [sent_bucket, "neutral"]}, 1, 0]}},
                "negative": {"$sum": {"$cond": [{"$eq": [sent_bucket, "negative"]}, 1, 0]}},
                "total": {"$sum": 1},
            }
        },
        {
            "$project": {
                "_id": 0,
                "narrative": "$_id.narrative",
                "entity": "$_id.entity",
                "positive": 1,
                "neutral": 1,
                "negative": 1,
                "total": 1,
            }
        },
        {"$sort": {"narrative": 1, "entity": 1}},
    ]


@router.get("/sentiment/narrative-sentiment")
async def get_narrative_sentiment(
    client: str = Query(..., description="Client name (to resolve client + competitors)"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
    surface: Optional[str] = Query(None, description="all|news|forums|reddit|youtube"),
    entity: Optional[str] = Query(None, description="Filter by entity name"),
    sentiment: Optional[str] = Query(None, description="Filter: positive | neutral | negative"),
):
    """
    Return stacked-bar friendly rows for taxonomy narrative sentiment:
    X-axis narratives (taxonomy tag ids), grouped by entity, stacked by sentiment.

    - News/Forums: from entity_mentions (requires narrative_primary already computed by pipeline).
    - Reddit/YouTube: from social_posts (computes narrative_primary + sentiment when missing, persists).
    """
    from app.services.narrative_tagging_service import get_narrative_tag_meta, tag_text_for_narratives
    from app.services.sentiment_service import analyze_sentiment

    await get_mongo_client()
    from app.services.mongodb import get_db

    surf = _norm_source(surface)
    coll_name, frag = _source_match_filter(surf)
    db = get_db()
    coll = db[coll_name]

    cutoff = datetime.now(timezone.utc) - _parse_range(range_param)

    entities = await _resolve_entities_for_client(client)
    q: dict[str, Any] = dict(frag)
    q["$or"] = [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}]
    if entities:
        q["entity"] = {"$in": entities}
    if entity and entity.strip():
        q["entity"] = entity.strip()
    sv = (sentiment or "").strip().lower()
    if sv in ("positive", "neutral", "negative"):
        sent_norm = {"$toLower": {"$ifNull": ["$sentiment", ""]}}
        sent_bucket = {
            "$cond": [
                {"$in": [sent_norm, ["positive", "neutral", "negative"]]},
                sent_norm,
                "neutral",
            ]
        }
        q["$expr"] = {"$eq": [sent_bucket, sv]}

    # For social_posts: ensure narrative_primary + sentiment exist (cheap, cached back to Mongo).
    if coll_name == SOCIAL_POSTS:
        cursor = coll.find(q).sort([("published_at", -1), ("timestamp", -1)]).limit(400)
        async for doc in cursor:
            needs_update = False
            s = (doc.get("sentiment") or "").strip().lower()
            if s not in ("positive", "neutral", "negative"):
                label, score = analyze_sentiment((doc.get("text") or "")[:2000])
                doc["sentiment"] = label
                doc["sentiment_score"] = score
                needs_update = True
            np = (doc.get("narrative_primary") or "").strip()
            if not np:
                text = (doc.get("text") or "").strip()
                tags, primary = tag_text_for_narratives(text)
                if primary:
                    doc["narrative_tags"] = tags
                    doc["narrative_primary"] = primary
                    needs_update = True
            if needs_update:
                try:
                    await coll.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {k: v for k, v in doc.items() if k in ("sentiment", "sentiment_score", "narrative_tags", "narrative_primary")}},
                    )
                except Exception:
                    pass

    # For entity_mentions: some pipelines may not have filled narrative_primary yet.
    # Without it, rows won't appear in the Narrative-per-company matrix.
    if coll_name == ENTITY_MENTIONS:
        q_backfill = dict(q)
        # If caller requested sentiment filter, q contains $expr; keep it for aggregation,
        # but remove it for the backfill scan since older rows can have non-normalized labels.
        q_backfill.pop("$expr", None)
        cursor = coll.find(q_backfill).sort([("published_at", -1), ("timestamp", -1)]).limit(400)
        async for doc in cursor:
            np = (doc.get("narrative_primary") or "").strip()
            if np:
                continue
            title = (doc.get("title") or "").strip()
            summary = (doc.get("summary") or "").strip()
            snippet = (doc.get("snippet") or "").strip()
            text = " ".join([t for t in (title, summary, snippet) if t]).strip()
            if not text:
                continue
            tags, primary = tag_text_for_narratives(text)
            if not primary:
                continue
            try:
                await coll.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"narrative_tags": tags, "narrative_primary": primary}},
                )
            except Exception:
                pass

    # Aggregate
    rows: list[dict[str, Any]] = []
    async for doc in coll.aggregate(_narrative_sentiment_pipeline(q)):
        rows.append(doc)

    return {
        "ok": True,
        "client": client.strip(),
        "surface": surf,
        "range": range_param,
        "cutoff": cutoff.isoformat(),
        "narrative_meta": get_narrative_tag_meta(),
        "chart_rows": rows,
        "entities": entities,
    }

@router.get("/sentiment/summary")
async def get_sentiment_summary(
    client: Optional[str] = None,
    entity: Optional[str] = Query(None, description="Filter to single entity (client or competitor name)"),
    source: Optional[str] = None,
    surface: Optional[str] = Query(
        None,
        description="Source surface filter for entity_mentions/social_posts: all|news|forums|reddit|youtube",
    ),
    sentiment: Optional[str] = Query(None, description="Filter: positive | neutral | negative"),
    range_param: Optional[str] = Query(None, alias="range", description="24h | 7d | 30d (optional; default = no time filter)"),
):
    """
    Return sentiment summary (positive/neutral/negative counts per entity).

    - source=entity_mentions (default): aggregate from entity_mentions (main pipeline).
    - source=media_articles: aggregate from media_articles (legacy).
    - client: when source=entity_mentions, filter to this client's entities (client + competitors from config).
    - entity: when provided, filter to that entity only (client or competitor).
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    # Backwards compatible:
    # - `source` keeps legacy meaning: entity_mentions (default) vs media_articles
    # - `surface` optionally filters to a specific surface (news/forums/reddit/youtube)
    use_entity_mentions = (source or "entity_mentions").strip().lower() != "media_articles"
    surf = _norm_source(surface)
    cutoff = None
    if range_param and str(range_param).strip():
        try:
            cutoff = datetime.now(timezone.utc) - _parse_range(range_param)
        except Exception:
            cutoff = None

    if use_entity_mentions:
        coll_name, frag = _source_match_filter(surf)
        coll = db[coll_name]
        match: dict = dict(frag)
        if cutoff is not None:
            match["$or"] = [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}]
        entities = await _resolve_entities_for_client(client) if client and client.strip() else []
        if entities:
            if entity and entity.strip():
                if entity.strip() in entities:
                    match["entity"] = entity.strip()
                else:
                    match["entity"] = {"$in": entities}
            else:
                match["entity"] = {"$in": entities}
        elif entity and entity.strip():
            match["entity"] = entity.strip()
        sv = (sentiment or "").strip().lower()
        if sv in ("positive", "neutral", "negative"):
            sent_norm = {"$toLower": {"$ifNull": ["$sentiment", ""]}}
            sent_bucket = {
                "$cond": [
                    {"$in": [sent_norm, ["positive", "neutral", "negative"]]},
                    sent_norm,
                    "neutral",
                ]
            }
            match["$expr"] = {"$eq": [sent_bucket, sv]}
        pipeline = _sentiment_pipeline(match)
        summaries = []
        async for doc in coll.aggregate(pipeline):
            summaries.append({
                "entity": doc.get("entity", ""),
                "positive": doc.get("positive", 0),
                "neutral": doc.get("neutral", 0),
                "negative": doc.get("negative", 0),
            })
        return {"summaries": summaries, "source": coll_name, "surface": surf}

    coll = db[MEDIA_ARTICLES]
    match = {}
    if client:
        match["client"] = client
    if cutoff is not None:
        match["$or"] = [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}]
    pipeline = _sentiment_pipeline(match)
    summaries = []
    async for doc in coll.aggregate(pipeline):
        summaries.append({
            "entity": doc.get("entity", ""),
            "positive": doc.get("positive", 0),
            "neutral": doc.get("neutral", 0),
            "negative": doc.get("negative", 0),
        })
    return {"summaries": summaries, "source": "media_articles"}


MENTIONS_LIMIT = 150


@router.get("/sentiment/mentions")
async def get_sentiment_mentions(
    client: str = Query(..., description="Client name, e.g. Sahi"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
    sentiment: Optional[str] = Query(None, description="Filter: positive | neutral | negative"),
    entity: Optional[str] = Query(None, description="Filter by entity name"),
    surface: Optional[str] = Query(
        None,
        description="Source surface filter: all|news|forums|reddit|youtube. all = existing dashboard feed.",
    ),
):
    """
    Return article mentions that have sentiment (for Sentiment page feed).
    Same structure as Media Intelligence feed items; filtered to items with sentiment.
    """
    await get_mongo_client()
    surf = _norm_source(surface)

    # Legacy/default: Source=all should show *everything* in one table:
    # - entity_mentions (news + forums) from dashboard feed
    # - social_posts (reddit + youtube) merged in
    if surf == SOURCE_ALL:
        data = await get_dashboard(client=client, range_param=range_param)
        feed = data.get("feed", [])
        mentions = [m for m in feed if m.get("sentiment")]
        if sentiment and sentiment.strip().lower() in ("positive", "neutral", "negative"):
            sv = sentiment.strip().lower()
            mentions = [m for m in mentions if (m.get("sentiment") or "").strip().lower() == sv]
        if entity and entity.strip():
            ev = entity.strip()
            mentions = [m for m in mentions if (m.get("entity") or "").strip() == ev]
        # Merge in social_posts (reddit + youtube) for the same time window
        from app.services.mongodb import get_db
        from app.services.sentiment_service import analyze_sentiment

        db = get_db()
        sp = db[SOCIAL_POSTS]
        cutoff = datetime.now(timezone.utc) - _parse_range(range_param)

        entities = await _resolve_entities_for_client(client)
        sp_q: dict[str, Any] = {
            "platform": {"$in": ["reddit", "youtube"]},
            "$or": [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}],
        }
        if entities:
            sp_q["entity"] = {"$in": entities}
        if entity and entity.strip():
            sp_q["entity"] = entity.strip()
        # Don't filter by raw stored sentiment here; normalize after compute (handles capitalized labels).

        cursor = sp.find(sp_q).sort([("published_at", -1), ("timestamp", -1)]).limit(MENTIONS_LIMIT)
        async for doc in cursor:
            s = (doc.get("sentiment") or "").strip().lower()
            if s not in ("positive", "neutral", "negative"):
                label, score = analyze_sentiment((doc.get("text") or "")[:2000])
                s = label
                try:
                    await sp.update_one({"_id": doc["_id"]}, {"$set": {"sentiment": label, "sentiment_score": score}})
                except Exception:
                    pass
            if sentiment and sentiment.strip().lower() in ("positive", "neutral", "negative"):
                if s != sentiment.strip().lower():
                    continue
            pub = doc.get("published_at") or doc.get("timestamp")
            pub_str = pub.isoformat() if hasattr(pub, "isoformat") else str(pub or "")
            text = (doc.get("text") or "").strip()
            headline = text[:100] + ("…" if len(text) > 100 else "") if text else "Social post"
            mentions.append({
                "headline": headline,
                "snippet": text[:220],
                "publisher": (doc.get("platform") or "").title() or "Social",
                "publish_time": pub_str,
                "link": doc.get("url") or "",
                "entity": doc.get("entity") or "",
                "sentiment": s,
            })

        # Sort merged list by publish_time desc (best-effort ISO strings)
        def _ts(m: dict[str, Any]) -> str:
            return str(m.get("publish_time") or "")

        mentions.sort(key=_ts, reverse=True)
        mentions = mentions[:MENTIONS_LIMIT]
        return {
            "mentions": mentions,
            "client": data.get("client", client),
            "competitors": data.get("competitors", []),
            "range": range_param,
            "surface": surf,
        }

    # Surface-specific: query collections directly so UI can show Reddit/YouTube too.
    from app.services.mongodb import get_db

    db = get_db()
    coll_name, frag = _source_match_filter(surf)
    coll = db[coll_name]
    cutoff = datetime.now(timezone.utc) - _parse_range(range_param)

    q: dict[str, Any] = dict(frag)
    if coll_name == ENTITY_MENTIONS:
        q["$or"] = [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}]
    else:
        q["$or"] = [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}]

    entities = await _resolve_entities_for_client(client)
    if entities:
        q["entity"] = {"$in": entities}
    if entity and entity.strip():
        q["entity"] = entity.strip()
    # Don't filter by raw stored sentiment here; normalize in loops below.

    # Ensure sentiment exists for social_posts (compute cheaply via VADER, cached back to Mongo)
    if coll_name == SOCIAL_POSTS:
        from app.services.sentiment_service import analyze_sentiment

        cursor = coll.find(q).sort([("published_at", -1), ("timestamp", -1)]).limit(MENTIONS_LIMIT)
        out: list[dict[str, Any]] = []
        async for doc in cursor:
            s = (doc.get("sentiment") or "").strip().lower()
            if s not in ("positive", "neutral", "negative"):
                label, score = analyze_sentiment((doc.get("text") or "")[:2000])
                s = label
                try:
                    await coll.update_one({"_id": doc["_id"]}, {"$set": {"sentiment": label, "sentiment_score": score}})
                except Exception:
                    pass
            if sentiment and sentiment.strip().lower() in ("positive", "neutral", "negative"):
                if s != sentiment.strip().lower():
                    continue
            # Map to the UI mention format used by SentimentMentionCard (headline/snippet/publisher/link/publish_time).
            pub = doc.get("published_at") or doc.get("timestamp")
            pub_str = pub.isoformat() if hasattr(pub, "isoformat") else str(pub or "")
            platform = (doc.get("platform") or "").strip().lower()
            text = (doc.get("text") or "").strip()
            if platform == "reddit":
                title = (doc.get("title") or "").strip()
                subreddit = (doc.get("subreddit") or "").strip()
                headline = title or (text[:100] + ("…" if len(text) > 100 else "")) or "Reddit thread"
                snippet = ((doc.get("body") or "").strip() or text)[:260]
                publisher = f"Reddit{(' • r/' + subreddit) if subreddit else ''}"
            elif platform == "youtube":
                vt = (doc.get("video_title") or "").strip()
                ch = (doc.get("channel") or "").strip()
                headline = vt or (text[:100] + ("…" if len(text) > 100 else "")) or "YouTube video"
                snippet = ((doc.get("video_description") or "").strip() or text)[:260]
                publisher = f"YouTube{(' • ' + ch) if ch else ''}"
            else:
                headline = text[:100] + ("…" if len(text) > 100 else "") if text else "Social post"
                snippet = text[:220]
                publisher = (doc.get("platform") or "").title() or "Social"
            out.append({
                "headline": headline,
                "snippet": snippet,
                "publisher": publisher,
                "publish_time": pub_str,
                "link": doc.get("url") or "",
                "entity": doc.get("entity") or "",
                "sentiment": s,
            })
        return {"mentions": out, "client": client, "range": range_param, "surface": surf}

    # entity_mentions: already has sentiment computed by worker
    cursor = coll.find(q).sort([("published_at", -1), ("timestamp", -1)]).limit(MENTIONS_LIMIT)
    out: list[dict[str, Any]] = []
    async for doc in cursor:
        pub = doc.get("published_at") or doc.get("timestamp")
        pub_str = pub.isoformat() if hasattr(pub, "isoformat") else str(pub or "")
        if sentiment and sentiment.strip().lower() in ("positive", "neutral", "negative"):
            sraw = (doc.get("sentiment") or "").strip().lower()
            if sraw != sentiment.strip().lower():
                continue
        out.append({
            "headline": (doc.get("title") or "")[:200],
            "snippet": ((doc.get("summary") or doc.get("snippet") or "")[:260]).strip(),
            "publisher": doc.get("source_domain") or doc.get("feed_domain") or ("Forum" if doc.get("type") == "forum" else "News"),
            "publish_time": pub_str,
            "link": doc.get("url") or "",
            "entity": doc.get("entity") or "",
            "sentiment": (doc.get("sentiment") or "neutral"),
        })
    return {"mentions": out, "client": client, "range": range_param, "surface": surf}


# ---------------------------------------------------------------------------
# Twitter (Apify) → taxonomy narratives → VADER sentiment (Pulse: Sentiment page)
# ---------------------------------------------------------------------------

TWITTER_NARRATIVE_POSTS = "twitter_narrative_posts"


def _parse_range(range_param: str) -> timedelta:
    rp = (range_param or "7d").strip()
    if rp == "24h":
        return timedelta(hours=24)
    if rp == "7d":
        return timedelta(days=7)
    if rp == "30d":
        return timedelta(days=30)
    return timedelta(days=7)


def _iso(dt: Any) -> str | None:
    if isinstance(dt, datetime):
        return dt.isoformat()
    if isinstance(dt, str):
        return dt
    return None


@router.post("/sentiment/twitter-narratives/refresh")
async def refresh_twitter_narratives(
    client: str = Query(..., description="Client name, e.g. Sahi"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
    max_items: int = Query(60, description="Max tweets to fetch from Apify (cap 200)"),
):
    """
    Fetch tweets via Apify for this client + competitors, tag narrative taxonomy IDs, run VADER sentiment,
    and persist to MongoDB (twitter_narrative_posts).
    """
    from app.core.client_config_loader import get_entity_names, load_clients
    from app.core.vertical_config_bundle import get_effective_config_bundle
    from app.services.apify_service import run_actor
    from app.services.apify_twitter_actor import build_twitter_actor_input
    from app.services.narrative_tagging_service import tag_text_for_narratives
    from app.services.sentiment_service import analyze_sentiment

    if not client or not client.strip():
        return {"ok": False, "detail": "client required"}

    await get_mongo_client()
    from app.services.mongodb import get_db

    clients_list = await load_clients()
    client_obj = next(
        (c for c in clients_list if (c.get("name") or "").strip().lower() == client.strip().lower()),
        None,
    )
    if not client_obj:
        return {"ok": False, "detail": f"client not found: {client.strip()!r}"}

    entities = get_entity_names(client_obj)
    entities = list(dict.fromkeys(e for e in entities if isinstance(e, str) and e.strip()))
    if not entities:
        return {"ok": False, "detail": "no entities for client"}

    # Build canonical entity -> matching terms (names + aliases)
    # Prefer client.yaml aliases; also include monitoring.entity_detection.entity_aliases.
    def _terms_for_entity(canonical: str, aliases: Any) -> list[str]:
        out = [canonical]
        if isinstance(aliases, list):
            out.extend([str(a).strip() for a in aliases if str(a).strip()])
        return list(dict.fromkeys([t for t in out if isinstance(t, str) and t.strip()]))

    canonical_to_terms: dict[str, list[str]] = {}
    # client aliases
    canonical_to_terms[entities[0]] = _terms_for_entity(entities[0], client_obj.get("aliases"))
    # competitor aliases (if structured)
    comps = client_obj.get("competitors") if isinstance(client_obj.get("competitors"), list) else []
    for c in comps:
        if isinstance(c, dict):
            nm = (c.get("name") or "").strip()
            if nm:
                canonical_to_terms[nm] = _terms_for_entity(nm, c.get("aliases"))
        elif isinstance(c, str) and c.strip():
            canonical_to_terms.setdefault(c.strip(), [c.strip()])

    # monitoring aliases (optional)
    try:
        mon_ed = (get_config().get("monitoring", {}) or {}).get("entity_detection", {})  # type: ignore[union-attr]
        ed_aliases = mon_ed.get("entity_aliases") if isinstance(mon_ed, dict) else None
        if isinstance(ed_aliases, dict):
            for canon, als in ed_aliases.items():
                canon_s = str(canon).strip()
                if not canon_s:
                    continue
                canonical_to_terms.setdefault(canon_s, [canon_s])
                if isinstance(als, list):
                    canonical_to_terms[canon_s].extend([str(a).strip() for a in als if str(a).strip()])
                    canonical_to_terms[canon_s] = list(dict.fromkeys([t for t in canonical_to_terms[canon_s] if t]))
    except Exception:
        pass

    def _detect_canonical_entity(text: str) -> str | None:
        tl = (text or "").lower()
        if not tl:
            return None
        # Prefer canonical names first (stable ordering: client then competitors)
        ordered_canon = entities[:]
        for canon in canonical_to_terms.keys():
            if canon not in ordered_canon:
                ordered_canon.append(canon)
        for canon in ordered_canon:
            for term in canonical_to_terms.get(canon, [canon]):
                t = term.lower()
                if t and t in tl:
                    return canon
        return None

    def _extract_tweet_fields(item: dict[str, Any]) -> tuple[str, str, dict[str, int], datetime]:
        """
        Best-effort extraction across Apify actor shapes.
        Returns (text, url, engagement, timestamp).
        """
        from app.services.apify_twitter_actor import _parse_tweet_timestamp as _pt  # type: ignore
        from app.services.apify_twitter_actor import _intish as _ii  # type: ignore

        nested = item.get("tweet")
        base = nested if isinstance(nested, dict) else item
        legacy = base.get("legacy") if isinstance(base.get("legacy"), dict) else None
        if legacy:
            text = legacy.get("full_text") or legacy.get("text") or ""
        else:
            text = (
                base.get("text")
                or base.get("full_text")
                or base.get("content")
                or base.get("fullText")
                or item.get("text")
                or item.get("full_text")
                or item.get("content")
                or ""
            )
        text = str(text or "")[:500]

        src = legacy or base
        likes = src.get("likeCount") or src.get("favorite_count") or src.get("favorites") or src.get("likes") or 0
        retweets = src.get("retweetCount") or src.get("retweet_count") or src.get("retweets") or 0
        replies = src.get("replyCount") or src.get("reply_count") or src.get("comments") or 0

        url = (
            base.get("url")
            or base.get("twitterUrl")
            or base.get("permanentUrl")
            or item.get("url")
            or item.get("twitterUrl")
            or item.get("permanentUrl")
            or item.get("tweet_url")
            or ""
        )
        tid = (
            base.get("id")
            or base.get("tweetId")
            or base.get("tweet_id")
            or base.get("statusId")
            or item.get("id")
            or item.get("tweetId")
            or item.get("tweet_id")
            or item.get("statusId")
        )
        if not url and tid:
            url = f"https://x.com/i/status/{tid}"
        url = str(url or "")[:500]

        created = (
            src.get("createdAt")
            or src.get("created_at")
            or (legacy.get("created_at") if legacy else None)
            or item.get("createdAt")
            or item.get("created_at")
            or item.get("date")
            or item.get("timestamp")
        )
        ts = _pt(created)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        return (
            text,
            url,
            {"likes": _ii(likes), "retweets": _ii(retweets), "comments": _ii(replies)},
            ts,
        )

    # Apify settings reuse monitoring config (defaults match existing social monitor).
    from app.config import get_config

    cfg = get_config()
    mon = cfg.get("monitoring", {}) if isinstance(cfg.get("monitoring", {}), dict) else {}
    apify_cfg = mon.get("apify", {}) if isinstance(mon.get("apify", {}), dict) else {}
    preferred_actor_id = str(apify_cfg.get("twitter_actor") or "").strip()
    preferred_style = str(apify_cfg.get("twitter_input_style") or "").strip()

    # For this feature we want a resilient default even if monitoring.yaml is tuned for another vertical.
    # Prefer configured actor if present; otherwise default to Tweet Scraper V2.
    actor_id = preferred_actor_id or "apidojo/tweet-scraper"
    input_style = preferred_style or "tweet_scraper_v2"

    cap = max(1, min(int(max_items), 200))
    # IMPORTANT: for this endpoint we always search by the active client+competitors
    # (including aliases), not by monitoring.yaml's global twitter_search_terms.
    def _quote_term(t: str) -> str:
        s = (t or "").strip()
        if not s:
            return ""
        # Quote multi-word terms; keep single tokens unquoted.
        return f"\"{s}\"" if (" " in s or "." in s) else s

    # Build search terms from canonical names + aliases (cap to avoid overly long queries).
    flat_terms: list[str] = []
    # Stable ordering: client first, then competitors
    for canon in entities:
        for term in canonical_to_terms.get(canon, [canon]):
            term_s = str(term).strip()
            if term_s and term_s.lower() not in {x.lower() for x in flat_terms}:
                flat_terms.append(term_s)
    # Include any remaining alias groups (monitoring aliases etc.)
    for canon, terms in canonical_to_terms.items():
        if canon in entities:
            continue
        for term in terms:
            term_s = str(term).strip()
            if term_s and term_s.lower() not in {x.lower() for x in flat_terms}:
                flat_terms.append(term_s)

    # Keep the query reasonably sized for actor inputs.
    MAX_QUERY_TERMS = 20
    flat_terms = flat_terms[:MAX_QUERY_TERMS]

    combined_query = " OR ".join([_quote_term(t) for t in flat_terms if t.strip()])
    apify_cfg_effective = dict(apify_cfg)
    apify_cfg_effective["twitter_search_terms"] = [combined_query] if combined_query.strip() else []
    def _build(style: str, actor_cfg: dict[str, Any]) -> dict[str, Any]:
        return build_twitter_actor_input(
            style=input_style,
            combined_query=combined_query,
            max_items=cap,
            apify_cfg=actor_cfg,
        )
    try:
        run_input = build_twitter_actor_input(
            style=input_style,
            combined_query=combined_query,
            max_items=cap,
            apify_cfg=apify_cfg_effective,
        )
    except ValueError:
        input_style = "tweet_scraper_v2"
        actor_id = "apidojo/tweet-scraper"
        run_input = build_twitter_actor_input(
            style=input_style,
            combined_query=combined_query,
            max_items=cap,
            apify_cfg=apify_cfg_effective,
        )

    def _looks_like_no_results(rows: list[Any]) -> bool:
        """
        Some Apify actors return dataset rows like {"noResults": true} instead of [].
        Treat that as empty so we can fall back to another actor.
        """
        if not rows:
            return True
        if all(isinstance(r, dict) and ("noResults" in r or "no_results" in r) for r in rows):
            return True
        # If none of the rows contain any obvious tweet text fields, also treat as empty.
        has_any_text = False
        for r in rows:
            if not isinstance(r, dict):
                continue
            if any(k in r for k in ("text", "full_text", "content", "tweet", "legacy", "fullText")):
                has_any_text = True
                break
        return not has_any_text

    def _try(actor: str, style: str, query: str, actor_cfg: dict[str, Any], note: str) -> tuple[list[dict[str, Any]], str, str, dict[str, Any]]:
        """Run one attempt; returns (items, actor_id, style, run_input)."""
        ri = build_twitter_actor_input(
            style=style,
            combined_query=query,
            max_items=cap,
            apify_cfg=actor_cfg,
        )
        out = run_actor(actor, ri)
        if _looks_like_no_results(out):
            out = []
        attempt_notes.append(note + f" -> {len(out)} items")
        return out, actor, style, ri

    attempt_notes: list[str] = []
    items: list[dict[str, Any]] = []

    # Attempt 1: configured actor/style with alias-rich OR query
    try:
        items, actor_id, input_style, run_input = _try(
            actor_id,
            input_style,
            combined_query,
            apify_cfg_effective,
            note=f"primary actor={actor_id!r} style={input_style!r} aliases_or_query",
        )
    except Exception as e:
        attempt_notes.append(f"primary error: {str(e)[:200]}")
        items = []

    # Attempt 2: shorter canonical-only query (less brittle)
    if not items:
        short_terms = [entities[0]] + [e for e in entities[1:4]]  # cap competitors
        q2 = " OR ".join([_quote_term(t) for t in short_terms if t.strip()])
        try:
            items, actor_id, input_style, run_input = _try(
                preferred_actor_id or actor_id,
                preferred_style or input_style,
                q2,
                dict(apify_cfg_effective, twitter_search_terms=[q2] if q2 else []),
                note="primary canonical_or_query",
            )
        except Exception as e:
            attempt_notes.append(f"canonical_or_query error: {str(e)[:200]}")

    # Attempt 3: handles-only (Apify official supports twitterHandles)
    if not items and input_style.strip().lower().replace("-", "_") == "apify_official":
        try:
            handles = apify_cfg_effective.get("twitter_handles")
            handles_list = [str(h).strip().lstrip("@") for h in handles] if isinstance(handles, list) else []
            # If no handles configured, skip.
            if handles_list:
                cfg3 = dict(apify_cfg_effective)
                cfg3["twitter_search_terms"] = []
                cfg3["twitter_handles"] = handles_list
                items, actor_id, input_style, run_input = _try(
                    preferred_actor_id or actor_id,
                    "apify_official",
                    "",  # query unused when handles provided; builder will set searchTerms=[]
                    cfg3,
                    note="primary handles_only",
                )
        except Exception as e:
            attempt_notes.append(f"handles_only error: {str(e)[:200]}")

    # Attempt 4: fallback tweet_scraper_v2 with simplified (unquoted) query
    if not items:
        fallback_actor_id = "apidojo/tweet-scraper"
        fallback_style = "tweet_scraper_v2"
        q4 = " OR ".join([t for t in flat_terms[:10] if t.strip()])  # no quotes, fewer terms
        try:
            items, actor_id, input_style, run_input = _try(
                fallback_actor_id,
                fallback_style,
                q4 or combined_query,
                {"twitter_sort": apify_cfg_effective.get("twitter_sort") or "Latest"},
                note="fallback tweet_scraper_v2 simplified_query",
            )
        except Exception as e:
            attempt_notes.append(f"fallback error: {str(e)[:200]}")
    db = get_db()
    coll = db[TWITTER_NARRATIVE_POSTS]

    bundle = get_effective_config_bundle()
    bundle_key = (bundle or "legacy").strip() or "legacy"
    now = datetime.now(timezone.utc)

    inserted = 0
    updated = 0
    skipped = 0
    tagged = 0
    no_entity = 0
    skipped_missing_text = 0
    skipped_missing_url = 0
    skipped_bad_shape = 0
    first_item_preview: dict[str, Any] | None = None

    for raw in items:
        if first_item_preview is None:
            if isinstance(raw, dict):
                # Small, safe preview for debugging actor schema in UI
                first_item_preview = {
                    "keys": sorted(list(raw.keys()))[:60],
                    "type": str(raw.get("type") or raw.get("__typename") or raw.get("itemType") or "")[:80],
                    "id": str(raw.get("id") or raw.get("tweetId") or raw.get("tweet_id") or "")[:80],
                }
            else:
                first_item_preview = {"non_dict_type": str(type(raw))}

        if not isinstance(raw, dict):
            skipped += 1
            skipped_bad_shape += 1
            continue

        text, url, engagement, ts = _extract_tweet_fields(raw)
        text = (text or "").strip()
        if not text:
            skipped += 1
            skipped_missing_text += 1
            continue

        canonical_entity = _detect_canonical_entity(text)
        if not canonical_entity:
            no_entity += 1
            # Keep the row anyway (so table isn't empty); chart will ignore until entity is known.
            canonical_entity = ""

        narrative_tags, narrative_primary = tag_text_for_narratives(text)
        if narrative_primary:
            tagged += 1

        sentiment_label, compound = analyze_sentiment(text)

        url = (url or "").strip()
        if not url:
            skipped += 1
            skipped_missing_url += 1
            continue

        doc = {
            "client": client_obj.get("name") or client.strip(),
            "bundle": bundle_key,
            "platform": "twitter",
            "entity": canonical_entity,
            "text": text,
            "url": url,
            "engagement": engagement or {},
            "timestamp": ts or now,
            "narrative_tags": narrative_tags,
            "narrative_primary": narrative_primary,
            "sentiment": sentiment_label,
            "sentiment_compound": compound,
            "raw": raw,
            "updated_at": now,
        }

        res = await coll.update_one(
            {"client": doc["client"], "bundle": bundle_key, "platform": "twitter", "url": url},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        if res.upserted_id is not None:
            inserted += 1
        elif res.modified_count:
            updated += 1

    return {
        "ok": True,
        "client": client_obj.get("name") or client.strip(),
        "bundle": bundle_key,
        "actor_id": actor_id,
        "input_style": input_style,
        "attempts": attempt_notes,
        "query_terms": entities,
        "run_input": run_input,
        "range": range_param,
        "counts": {
            "fetched": len(items),
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "no_entity_detected": no_entity,
            "tagged_with_narrative": tagged,
            "skipped_missing_text": skipped_missing_text,
            "skipped_missing_url": skipped_missing_url,
            "skipped_bad_shape": skipped_bad_shape,
        },
        "first_item_preview": first_item_preview,
    }


@router.get("/sentiment/twitter-narratives")
async def get_twitter_narratives(
    client: str = Query(..., description="Client name, e.g. Sahi"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
    entity: Optional[str] = Query(None, description="Filter by entity name"),
    narrative: Optional[str] = Query(None, description="Filter by narrative id (taxonomy tag id)"),
    sentiment: Optional[str] = Query(None, description="positive | neutral | negative"),
    limit: int = Query(50, description="Rows for posts table (cap 200)"),
    offset: int = Query(0, description="Pagination offset"),
):
    """
    Return:
    - narrative_meta: tag id -> {label, description}
    - chart: per narrative id, per entity sentiment counts
    - posts: tweet rows for the table (most recent first)
    """
    from app.core.vertical_config_bundle import get_effective_config_bundle
    from app.services.narrative_tagging_service import get_narrative_tag_meta

    await get_mongo_client()
    from app.services.mongodb import get_db

    bundle = get_effective_config_bundle()
    bundle_key = (bundle or "legacy").strip() or "legacy"

    cutoff = datetime.now(timezone.utc) - _parse_range(range_param)
    db = get_db()
    coll = db[TWITTER_NARRATIVE_POSTS]

    q: dict[str, Any] = {
        "client": client.strip(),
        "bundle": bundle_key,
        "$or": [{"timestamp": {"$gte": cutoff}}, {"created_at": {"$gte": cutoff}}],
    }
    if entity and entity.strip():
        q["entity"] = entity.strip()
    if narrative and narrative.strip():
        q["narrative_primary"] = narrative.strip()
    if sentiment and sentiment.strip().lower() in ("positive", "neutral", "negative"):
        q["sentiment"] = sentiment.strip().lower()

    # Load posts (table)
    cap = max(1, min(int(limit), 200))
    off = max(0, int(offset))

    cursor = coll.find(q).sort([("timestamp", -1), ("created_at", -1)]).skip(off).limit(cap)
    posts: list[dict[str, Any]] = []
    async for doc in cursor:
        posts.append(
            {
                "entity": doc.get("entity") or "",
                "url": doc.get("url") or "",
                "text": doc.get("text") or "",
                "timestamp": _iso(doc.get("timestamp") or doc.get("created_at")),
                "engagement": doc.get("engagement") or {},
                "narrative_primary": doc.get("narrative_primary"),
                "narrative_tags": doc.get("narrative_tags") or [],
                "sentiment": doc.get("sentiment") or "neutral",
                "sentiment_compound": doc.get("sentiment_compound"),
            }
        )

    # Aggregate chart data (narrative_primary + entity)
    pipeline = [
        {"$match": q},
        {"$match": {"narrative_primary": {"$exists": True, "$ne": None, "$ne": ""}}},
        {
            "$group": {
                "_id": {"narrative": "$narrative_primary", "entity": "$entity"},
                "positive": {"$sum": {"$cond": [{"$eq": ["$sentiment", "positive"]}, 1, 0]}},
                "neutral": {"$sum": {"$cond": [{"$eq": ["$sentiment", "neutral"]}, 1, 0]}},
                "negative": {"$sum": {"$cond": [{"$eq": ["$sentiment", "negative"]}, 1, 0]}},
                "total": {"$sum": 1},
            }
        },
        {
            "$project": {
                "_id": 0,
                "narrative": "$_id.narrative",
                "entity": "$_id.entity",
                "positive": 1,
                "neutral": 1,
                "negative": 1,
                "total": 1,
            }
        },
        {"$sort": {"narrative": 1, "entity": 1}},
    ]
    rows: list[dict[str, Any]] = []
    async for doc in coll.aggregate(pipeline):
        rows.append(doc)

    meta = get_narrative_tag_meta()
    return {
        "ok": True,
        "client": client.strip(),
        "bundle": bundle_key,
        "range": range_param,
        "cutoff": cutoff.isoformat(),
        "narrative_meta": meta,
        "chart_rows": rows,
        "posts": posts,
        "page": {"limit": cap, "offset": off, "returned": len(posts)},
    }
