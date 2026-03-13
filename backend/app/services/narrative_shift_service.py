"""
Narrative Shift Intelligence — detect emerging narrative shifts across YouTube, Reddit, and news.

- Fetches via APIs: YouTube Data API v3, Reddit JSON API, news from article_documents.
- Uses sentence-transformers + KMeans for clustering.
- Stores results in MongoDB. Run backfill script to populate; UI reads from DB.
- Minimizes LLM (1 summarization call per run).
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

COLLECTION = "narrative_shift_runs"
WINDOW_HOURS = 72

# --- Config -------------------------------------------------------------------


def _cfg() -> dict[str, Any]:
    return get_config().get("narrative_shift") or {}


def _youtube_api_key() -> str:
    settings = get_config().get("settings")
    key = getattr(settings, "youtube_api_key", "") if settings else ""
    return (key or _cfg().get("youtube_api_key") or "").strip()


# --- Fetch YouTube (API) ------------------------------------------------------


def _youtube_search(query: str, api_key: str, max_results: int = 10) -> list[str]:
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": min(max_results, 25),
        "order": "viewCount",
        "relevanceLanguage": "en",
        "key": api_key,
    }
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            items = (r.json().get("items") or [])
            return [i["id"]["videoId"] for i in items if i.get("id", {}).get("kind") == "youtube#video" and i.get("id", {}).get("videoId")]
    except Exception as e:
        logger.warning("narrative_shift_youtube_search_failed", query=query, error=str(e))
        return []


def _youtube_video_details(video_ids: list[str], api_key: str) -> list[dict]:
    if not video_ids:
        return []
    url = "https://www.googleapis.com/youtube/v3/videos"
    ids = list(set(video_ids))[:50]
    params = {"part": "snippet,statistics", "id": ",".join(ids), "key": api_key}
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("narrative_shift_youtube_details_failed", error=str(e))
        return []
    out = []
    for i in (data.get("items") or []):
        sn = i.get("snippet", {})
        st = i.get("statistics", {})
        text = f"{sn.get('title', '')} {sn.get('description', '')}"[:1000]
        out.append({
            "platform": "youtube",
            "text": text,
            "source": sn.get("channelTitle", ""),
            "engagement": int(st.get("viewCount") or 0) + int(st.get("likeCount") or 0) * 100,
            "url": f"https://www.youtube.com/watch?v={i.get('id', '')}",
        })
    return out


# --- Fetch Reddit (API) -------------------------------------------------------


def _reddit_fetch(subreddit: str, limit: int = 25) -> list[dict]:
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={min(limit, 100)}"
    headers = {"User-Agent": "ZyonNarrativeShift/1.0"}
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as c:
            r = c.get(url, headers=headers)
            r.raise_for_status()
            children = (r.json().get("data") or {}).get("children") or []
    except Exception as e:
        logger.warning("narrative_shift_reddit_failed", sub=subreddit, error=str(e))
        return []
    out = []
    for c in children:
        d = c.get("data") or {}
        title = (d.get("title") or "").strip()
        body = (d.get("selftext") or "")[:500]
        text = f"{title} {body}".strip()
        if not text:
            continue
        score = int(d.get("score") or 0)
        num_comments = int(d.get("num_comments") or 0)
        out.append({
            "platform": "reddit",
            "text": text[:1500],
            "source": f"r/{subreddit}",
            "engagement": score + num_comments * 2,
            "url": f"https://reddit.com{d.get('permalink', '')}",
        })
    return out


# --- Fetch news from DB -------------------------------------------------------


async def _fetch_news_from_db(hours: int = WINDOW_HOURS) -> list[dict]:
    from app.services.mongodb import get_mongo_client, get_db
    await get_mongo_client()
    db = get_db()
    coll = db["article_documents"]
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    cursor = coll.find({"$or": [{"published_at": {"$gte": since}}, {"fetched_at": {"$gte": since}}]}).limit(150)
    out = []
    async for doc in cursor:
        title = (doc.get("title") or "")[:300]
        summary = (doc.get("summary") or doc.get("article_text") or "")[:500]
        text = f"{title} {summary}".strip()
        if not text:
            continue
        out.append({
            "platform": "news",
            "text": text[:1500],
            "source": (doc.get("source_domain") or "news")[:100],
            "engagement": 0,
            "url": doc.get("url") or "",
        })
    return out


# --- Cluster & summarize ------------------------------------------------------


def _cluster_texts(items: list[dict], n_clusters: int = 5) -> list[list[dict]]:
    """Cluster by embeddings (KMeans). Returns list of clusters (each cluster = list of items)."""
    try:
        from sklearn.cluster import KMeans
        from app.services.embedding_service import embed_batch
    except ImportError as e:
        logger.warning("narrative_shift_cluster_import_failed", error=str(e))
        return [items] if items else []
    texts = [x.get("text", "") or "" for x in items]
    if len(texts) < n_clusters:
        n_clusters = max(1, len(texts))
    try:
        embeds = embed_batch(texts)
    except Exception as e:
        logger.warning("narrative_shift_embed_failed", error=str(e))
        return [items] if items else []
    if len(embeds) != len(items):
        return [items] if items else []
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = km.fit_predict(embeds)
    clusters: list[list[dict]] = [[] for _ in range(n_clusters)]
    for i, lab in enumerate(labels):
        clusters[lab].append(items[i])
    return [c for c in clusters if c]


async def _llm_summarize_narrative(texts: list[str], max_tokens: int = 200) -> dict[str, str]:
    """One LLM call: topic, pain points, messaging."""
    from app.services.llm_gateway import LLMGateway
    sample = "\n".join((t[:200] for t in texts[:15]))
    system = (
        "Return JSON: {\"topic\": \"short narrative topic\", \"pain_points\": \"1-2 sentences\", \"messaging\": \"1-2 sentences for Sahi app\"}. "
        "Only valid JSON."
    )
    user = f"Summarize this cluster:\n{sample[:4000]}"
    cfg = _cfg()
    model = (cfg.get("llm") or {}).get("model") or "openrouter/free"
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
        logger.warning("narrative_shift_llm_failed", error=str(e))
        return {"topic": "Narrative", "pain_points": "", "messaging": ""}
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
        return {
            "topic": str(parsed.get("topic", "Narrative"))[:200],
            "pain_points": str(parsed.get("pain_points", ""))[:300],
            "messaging": str(parsed.get("messaging", ""))[:300],
        }
    except json.JSONDecodeError:
        return {"topic": "Narrative", "pain_points": "", "messaging": ""}


# --- Main pipeline ------------------------------------------------------------


async def run_narrative_shift_pipeline() -> dict[str, Any]:
    """
    Fetch from APIs + DB, cluster, summarize, store.
    Returns run summary for backfill script.
    """
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return {"ok": False, "reason": "narrative_shift disabled"}

    items: list[dict] = []

    # 1. YouTube (API)
    yt_key = _youtube_api_key()
    if yt_key:
        queries = (cfg.get("youtube_queries") or ["stock market", "options trading", "commodity"])[:3]
        for q in queries:
            ids = _youtube_search(q, yt_key, max_results=10)
            vids = _youtube_video_details(ids, yt_key)
            items.extend(vids)
            await asyncio.sleep(0.5)
    else:
        logger.info("narrative_shift_youtube_skipped", reason="no API key")

    # 2. Reddit (API)
    subs = (cfg.get("reddit_subreddits") or ["stocks", "investing", "IndianStreetBets"])[:5]
    for sub in subs:
        posts = _reddit_fetch(sub, limit=20)
        items.extend(posts)
        await asyncio.sleep(1.0)

    # 3. News (DB)
    news = await _fetch_news_from_db(hours=WINDOW_HOURS)
    items.extend(news)

    if len(items) < 3:
        return {"ok": True, "items": 0, "narratives": [], "reason": "insufficient data"}

    # 4. Cluster
    n_clusters = min(6, max(2, len(items) // 15))
    clusters = _cluster_texts(items, n_clusters=n_clusters)

    # 5. Build narratives
    narratives: list[dict] = []
    for clu in clusters:
        if not clu:
            continue
        texts = [x.get("text", "") for x in clu if x.get("text")]
        summ = await _llm_summarize_narrative(texts)
        platforms = {}
        sources = {}
        total_eng = 0
        for x in clu:
            p = x.get("platform", "unknown")
            platforms[p] = platforms.get(p, 0) + 1
            s = (x.get("source") or "").strip()
            if s:
                sources[s] = sources.get(s, 0) + 1
            total_eng += x.get("engagement") or 0
        top_sources = sorted(sources.items(), key=lambda t: -t[1])[:5]
        narratives.append({
            "topic": summ["topic"],
            "growth_pct": 0.0,
            "dominant_platform": max(platforms.items(), key=lambda t: t[1])[0] if platforms else "unknown",
            "platform_distribution": platforms,
            "influencers": [s[0] for s in top_sources],
            "pain_points": summ["pain_points"],
            "messaging": summ["messaging"],
            "item_count": len(clu),
            "total_engagement": total_eng,
        })

    narratives.sort(key=lambda n: -(n.get("total_engagement") or 0))

    # 6. Store
    from app.services.mongodb import get_mongo_client, get_db
    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION]
    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": WINDOW_HOURS,
        "items_total": len(items),
        "narratives": narratives,
        "platform_totals": {"youtube": sum(1 for i in items if i.get("platform") == "youtube"),
                           "reddit": sum(1 for i in items if i.get("platform") == "reddit"),
                           "news": sum(1 for i in items if i.get("platform") == "news")},
    }
    await coll.insert_one(doc)

    return {"ok": True, "items": len(items), "narratives": narratives, "run_id": str(doc.get("_id", ""))}


async def load_latest_run() -> dict[str, Any] | None:
    """Load most recent narrative shift run from DB."""
    from app.services.mongodb import get_mongo_client, get_db
    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION]
    doc = await coll.find_one(sort=[("generated_at", -1)])
    if not doc:
        return None
    d = dict(doc)
    d.pop("_id", None)
    return d
