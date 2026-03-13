"""
YouTube narrative pipeline — trading/finance/commodity narrative from video metadata.

- Uses YouTube Data API v3 (no Apify, no comments).
- One LLM call per day: themes + narrative summary + sentiment.
- Popularity from views/likes/comment_count; sentiment from title + description.
- Daily snapshots in MongoDB for per-day tracking.
- Respects YouTube API quota (~400 units/day) and LLM limits.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

# --- Config -------------------------------------------------------------------

def _cfg() -> dict[str, Any]:
    return get_config().get("youtube_trending") or {}


def _api_key() -> str:
    settings = get_config().get("settings")
    key = getattr(settings, "youtube_api_key", "") if settings else ""
    if not key:
        key = _cfg().get("api_key", "")
    return (key or "").strip()


def _summaries_collection() -> str:
    return (_cfg().get("mongodb") or {}).get("summaries_collection") or "youtube_narrative_summaries"


def _videos_collection() -> str:
    return (_cfg().get("mongodb") or {}).get("videos_collection") or "youtube_narrative_videos"


# --- YouTube Data API v3 ------------------------------------------------------

def _search_videos(query: str, api_key: str, max_results: int = 15) -> list[str]:
    """search.list: returns video IDs. 100 units per call."""
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": min(max_results, 50),
        "order": "viewCount",
        "relevanceLanguage": "en",
        "key": api_key,
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("youtube_search_failed", query=query, error=str(e))
        return []
    items = data.get("items", [])
    return [i["id"]["videoId"] for i in items if i.get("id", {}).get("kind") == "youtube#video" and i.get("id", {}).get("videoId")]


def _fetch_video_details(video_ids: list[str], api_key: str) -> list[dict]:
    """videos.list: 1 unit per call, up to 50 ids. Returns snippet + statistics."""
    if not video_ids:
        return []
    url = "https://www.googleapis.com/youtube/v3/videos"
    ids = list(set(video_ids))[:50]
    params = {
        "part": "snippet,statistics",
        "id": ",".join(ids),
        "key": api_key,
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("youtube_videos_list_failed", error=str(e))
        return []
    items = data.get("items", [])
    out = []
    for i in items:
        try:
            vid = i.get("id", "")
            sn = i.get("snippet", {})
            stat = i.get("statistics", {})
            title = (sn.get("title") or "").strip()
            desc = (sn.get("description") or "")[:1500]
            channel = (sn.get("channelTitle") or "").strip()
            published = sn.get("publishedAt") or ""
            views = int(stat.get("viewCount") or 0)
            likes = int(stat.get("likeCount") or 0)
            comment_count = int(stat.get("commentCount") or 0)
            out.append({
                "video_id": vid,
                "title": title[:500],
                "description": desc,
                "channel_title": channel[:200],
                "published_at": published,
                "views": views,
                "likes": likes,
                "comment_count": comment_count,
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
        except Exception as e:
            logger.debug("youtube_video_skip", error=str(e))
            continue
    return out


# --- Fetch pipeline -----------------------------------------------------------

async def fetch_youtube_trending_videos() -> list[dict[str, Any]]:
    """
    Fetch trading/finance YouTube videos via search (no comments).
    Respects quota: ~3 searches (300 units) + 1 videos.list (1 unit) ≈ 301 units/run.
    """
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return []
    api_key = _api_key()
    if not api_key:
        logger.warning("youtube_trending_api_key_missing")
        return []

    search_queries = cfg.get("search_queries") or [
        "stock market trading",
        "options trading",
        "commodity market",
        "finance news India",
    ]
    max_per_query = min(int(cfg.get("max_videos_per_query") or 12), 25)
    delay = max(0.5, float(cfg.get("delay_seconds_between_searches") or 1.0))

    all_ids: list[str] = []
    seen: set[str] = set()
    for q in search_queries[:5]:
        ids = await asyncio.to_thread(_search_videos, q, api_key, max_results=max_per_query)
        for v in ids:
            if v not in seen:
                seen.add(v)
                all_ids.append(v)
        await asyncio.sleep(delay)

    videos = await asyncio.to_thread(_fetch_video_details, all_ids[:50], api_key)
    videos.sort(key=lambda v: (v.get("views") or 0, v.get("likes") or 0), reverse=True)
    return videos


# --- MongoDB ------------------------------------------------------------------

async def _get_db():
    from app.services.mongodb import get_mongo_client, get_db
    await get_mongo_client()
    return get_db()


async def save_videos_to_mongo(videos: list[dict[str, Any]], date_str: str) -> int:
    """Store raw videos for the given date (for heuristics / debugging)."""
    if not videos:
        return 0
    db = await _get_db()
    coll = db[_videos_collection()]
    docs = [{**v, "date": date_str, "pipeline": "youtube_narrative", "fetched_at": datetime.now(timezone.utc).isoformat()} for v in videos]
    try:
        await coll.delete_many({"date": date_str, "pipeline": "youtube_narrative"})
        if docs:
            await coll.insert_many(docs)
        return len(docs)
    except Exception as e:
        logger.warning("youtube_narrative_videos_save_failed", error=str(e))
        return 0


async def save_daily_summary_to_mongo(
    date_str: str,
    narrative: str,
    themes: list[dict],
    top_channels: list[str],
    sentiment_summary: str,
    popularity_score: float,
) -> None:
    """One doc per day. Upsert by date."""
    db = await _get_db()
    coll = db[_summaries_collection()]
    doc = {
        "date": date_str,
        "narrative": narrative,
        "themes": themes,
        "top_channels": top_channels[:20],
        "sentiment_summary": sentiment_summary,
        "popularity_score": popularity_score,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": "youtube_narrative",
    }
    try:
        await coll.replace_one({"date": date_str, "pipeline": "youtube_narrative"}, doc, upsert=True)
    except Exception as e:
        logger.warning("youtube_narrative_summary_save_failed", error=str(e))


async def load_daily_summaries(limit: int = 30) -> list[dict[str, Any]]:
    """Load per-day summaries, newest first."""
    db = await _get_db()
    coll = db[_summaries_collection()]
    cursor = coll.find({"pipeline": "youtube_narrative"}).sort("date", -1).limit(limit)
    out = []
    async for doc in cursor:
        d = dict(doc)
        d.pop("_id", None)
        for k in ("generated_at",):
            v = d.get(k)
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        out.append(d)
    return out


# --- LLM: 1 call for themes + narrative + sentiment ---------------------------

async def _llm_single_call(model: str, max_tokens: int, system: str, user: str) -> str:
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
        logger.warning("youtube_narrative_llm_failed", error=str(e))
        return ""
    s = (out or "").strip()
    if s.startswith("```"):
        lines = s.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines)
    return s


async def generate_narrative_from_videos(videos: list[dict[str, Any]]) -> dict[str, Any]:
    """
    One LLM call: themes + narrative summary + sentiment.
    Input: titles, descriptions, popularity (views/likes). No comments.
    """
    cfg = _cfg()
    llm_cfg = cfg.get("llm") or {}
    model = (llm_cfg.get("model") or "openrouter/free").strip()
    max_tokens = int(llm_cfg.get("max_tokens") or 800)

    lines = []
    for i, v in enumerate((videos or [])[:40], 1):
        title = (v.get("title") or "").strip()
        desc = (v.get("description") or "")[:200]
        ch = v.get("channel_title") or ""
        views = v.get("views") or 0
        likes = v.get("likes") or 0
        lines.append(f"{i}. [{ch}] {title} | views={views} likes={likes} | {desc}")

    text = "\n".join(lines) or "No videos."
    system = (
        "You are an analyst. Given YouTube video titles and descriptions from trading, finance, stock market, and commodity content, "
        "return a JSON object with exactly these keys: "
        '"themes" (array of {label, description}, 4-6 items), '
        '"narrative" (2-4 sentence summary of the dominant narrative), '
        '"sentiment_summary" (1-2 sentences: bullish/bearish/neutral tone), '
        '"top_channels" (array of 5-10 channel names that stand out). '
        "Return ONLY valid JSON, no markdown."
    )
    user = f"Analyze these YouTube videos:\n\n{text[:9000]}"
    raw = await _llm_single_call(model=model, max_tokens=max_tokens, system=system, user=user)
    if not raw:
        return {"themes": [], "narrative": "", "sentiment_summary": "", "top_channels": []}

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            themes = [{"label": x.get("label", ""), "description": x.get("description", "")} for x in (parsed.get("themes") or []) if isinstance(x, dict)]
            top_channels = [str(c) for c in (parsed.get("top_channels") or [])[:15] if c]
            return {
                "themes": themes,
                "narrative": (parsed.get("narrative") or "").strip(),
                "sentiment_summary": (parsed.get("sentiment_summary") or "").strip(),
                "top_channels": top_channels,
            }
    except json.JSONDecodeError:
        pass
    return {"themes": [], "narrative": "", "sentiment_summary": "", "top_channels": []}


def _popularity_score(videos: list[dict]) -> float:
    """Aggregate popularity: weighted views + likes + comment_count."""
    if not videos:
        return 0.0
    total = 0
    for v in videos[:30]:
        views = v.get("views") or 0
        likes = v.get("likes") or 0
        comments = v.get("comment_count") or 0
        total += views + (likes * 100) + (comments * 50)
    return total / 1_000_000  # scale for readability


# --- Full pipeline ------------------------------------------------------------

async def run_youtube_narrative_pipeline() -> dict[str, Any]:
    """
    Run: fetch YouTube videos → save to Mongo → 1 LLM call → save daily summary.
    One run per day; use date as partition.
    """
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return {"ok": False, "reason": "youtube_trending disabled"}
    if not _api_key():
        return {"ok": False, "reason": "YOUTUBE_API_KEY not set"}

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result: dict[str, Any] = {
        "ok": True,
        "date": date_str,
        "videos_fetched": 0,
        "videos_saved": 0,
        "narrative": "",
        "themes_count": 0,
        "popularity_score": 0.0,
    }

    videos = await fetch_youtube_trending_videos()
    result["videos_fetched"] = len(videos)
    if not videos:
        return result

    result["videos_saved"] = await save_videos_to_mongo(videos, date_str)
    result["popularity_score"] = _popularity_score(videos)

    llm_result = await generate_narrative_from_videos(videos)
    themes = llm_result.get("themes") or []
    narrative = llm_result.get("narrative") or ""
    sentiment = llm_result.get("sentiment_summary") or ""
    top_channels = llm_result.get("top_channels") or []

    result["narrative"] = narrative
    result["themes_count"] = len(themes)

    await save_daily_summary_to_mongo(
        date_str=date_str,
        narrative=narrative,
        themes=themes,
        top_channels=top_channels,
        sentiment_summary=sentiment,
        popularity_score=result["popularity_score"],
    )
    return result
