"""
Official YouTube Data API v3 ingest for brand / narrative intelligence.

- Uses only documented REST endpoints + API key (or OAuth if you extend auth).
- No HTML scraping — avoids ToS blocks and bot detection.
- Quota-aware: logs estimated units per run; caps searches, channels, comment fetches.

Typical quota costs (YouTube Data API v3):
  search.list          100 units / call
  videos.list            1 unit / call (up to 50 ids)
  channels.list          1 unit / call
  playlistItems.list     1 unit / call (page)
  commentThreads.list    1 unit / call (per video)

Default project quota is 10,000 units/day — tune yaml to stay well under budget.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


def _cfg() -> dict[str, Any]:
    return get_config().get("youtube_official") or {}


def _api_key() -> str:
    settings = get_config().get("settings")
    key = getattr(settings, "youtube_api_key", "") if settings else ""
    if not key:
        key = (_cfg().get("api_key") or "").strip()
    if not key:
        key = (get_config().get("youtube_trending") or {}).get("api_key") or ""
    return (key or "").strip()


def _mongo_collection_name() -> str:
    m = _cfg().get("mongodb") or {}
    return m.get("collection") or "youtube_intel_videos"


def _mongo_db_name() -> str:
    m = _cfg().get("mongodb") or {}
    return m.get("database") or (get_config().get("mongodb") or {}).get("database") or "chat"


class _QuotaTracker:
    """In-process estimate for observability (Google bills actual server-side)."""

    def __init__(self) -> None:
        self.units = 0
        self.calls: list[tuple[str, int]] = []

    def add(self, name: str, units: int) -> None:
        self.units += units
        self.calls.append((name, units))


def _get_json(url: str, params: dict[str, Any], tracker: _QuotaTracker, op: str, cost: int) -> dict[str, Any]:
    with httpx.Client(timeout=25.0) as client:
        resp = client.get(url, params=params)
        tracker.add(op, cost)
        if resp.status_code == 403:
            try:
                err = resp.json()
            except Exception:
                err = {}
            reason = (err.get("error") or {}).get("errors") or []
            logger.warning("youtube_api_forbidden", op=op, detail=reason)
        resp.raise_for_status()
        return resp.json()


def _channels_uploads_playlist_id(channel_id: str, api_key: str, tracker: _QuotaTracker) -> str | None:
    data = _get_json(
        f"{YOUTUBE_API_BASE}/channels",
        {"part": "contentDetails", "id": channel_id, "key": api_key},
        tracker,
        "channels.list",
        1,
    )
    items = data.get("items") or []
    if not items:
        return None
    return (items[0].get("contentDetails") or {}).get("relatedPlaylists", {}).get("uploads")


def _playlist_video_ids(
    uploads_playlist_id: str,
    api_key: str,
    tracker: _QuotaTracker,
    max_items: int,
) -> list[str]:
    out: list[str] = []
    page_token: str | None = None
    while len(out) < max_items:
        params: dict[str, Any] = {
            "part": "contentDetails,snippet",
            "playlistId": uploads_playlist_id,
            "maxResults": min(50, max_items - len(out)),
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        data = _get_json(f"{YOUTUBE_API_BASE}/playlistItems", params, tracker, "playlistItems.list", 1)
        for it in data.get("items") or []:
            vid = (it.get("contentDetails") or {}).get("videoId")
            if vid:
                out.append(vid)
            if len(out) >= max_items:
                break
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return out


def _search_video_ids(
    query: str,
    api_key: str,
    tracker: _QuotaTracker,
    max_results: int,
    order: str = "date",
) -> list[str]:
    data = _get_json(
        f"{YOUTUBE_API_BASE}/search",
        {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": min(max_results, 50),
            "order": order,
            "relevanceLanguage": "en",
            "key": api_key,
        },
        tracker,
        "search.list",
        100,
    )
    ids: list[str] = []
    for i in data.get("items") or []:
        if i.get("id", {}).get("kind") == "youtube#video":
            vid = i.get("id", {}).get("videoId")
            if vid:
                ids.append(vid)
    return ids


def _videos_list_details(video_ids: list[str], api_key: str, tracker: _QuotaTracker) -> list[dict[str, Any]]:
    if not video_ids:
        return []
    url = f"{YOUTUBE_API_BASE}/videos"
    out: list[dict[str, Any]] = []
    # Batch up to 50 per request, 1 unit each
    for i in range(0, len(video_ids), 50):
        batch = list(dict.fromkeys(video_ids[i : i + 50]))
        data = _get_json(
            url,
            {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch),
                "key": api_key,
            },
            tracker,
            "videos.list",
            1,
        )
        for item in data.get("items") or []:
            out.append(_normalize_video_item(item))
    return out


def _normalize_video_item(item: dict[str, Any]) -> dict[str, Any]:
    vid = item.get("id") or ""
    sn = item.get("snippet") or {}
    st = item.get("statistics") or {}
    cd = item.get("contentDetails") or {}
    thumbs = sn.get("thumbnails") or {}
    default_thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url") or ""
    tags = sn.get("tags") if isinstance(sn.get("tags"), list) else []
    return {
        "video_id": vid,
        "channel_id": (sn.get("channelId") or "").strip(),
        "channel_title": (sn.get("channelTitle") or "").strip()[:300],
        "title": (sn.get("title") or "").strip()[:500],
        "description": (sn.get("description") or "")[:4000],
        "published_at": sn.get("publishedAt") or "",
        "tags": [str(t)[:100] for t in tags[:30]],
        "category_id": str(sn.get("categoryId") or ""),
        "default_language": (sn.get("defaultLanguage") or sn.get("defaultAudioLanguage") or "")[:16],
        "duration_iso": (cd.get("duration") or "")[:32],
        "views": int(st.get("viewCount") or 0),
        "likes": int(st.get("likeCount") or 0) if st.get("likeCount") is not None else 0,
        "comment_count": int(st.get("commentCount") or 0) if st.get("commentCount") is not None else 0,
        "thumbnail_url": (default_thumb or "")[:500],
        "url": f"https://www.youtube.com/watch?v={vid}",
    }


def _comment_threads_for_video(
    video_id: str,
    api_key: str,
    tracker: _QuotaTracker,
    max_threads: int,
) -> list[dict[str, Any]]:
    data = _get_json(
        f"{YOUTUBE_API_BASE}/commentThreads",
        {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": min(max_threads, 100),
            "order": "relevance",
            "textFormat": "plainText",
            "key": api_key,
        },
        tracker,
        "commentThreads.list",
        1,
    )
    comments: list[dict[str, Any]] = []
    for it in data.get("items") or []:
        top = (it.get("snippet") or {}).get("topLevelComment", {}).get("snippet") or {}
        text = (top.get("textDisplay") or top.get("textOriginal") or "").strip()
        if not text:
            continue
        comments.append(
            {
                "text": text[:2000],
                "author": (top.get("authorDisplayName") or "")[:200],
                "like_count": int(top.get("likeCount") or 0),
                "published_at": top.get("publishedAt") or "",
            }
        )
    return comments


async def _get_db():
    from app.services.mongodb import get_mongo_client, get_db

    await get_mongo_client()
    return get_db()


async def _save_videos(videos: list[dict[str, Any]], run_id: str) -> int:
    if not videos:
        return 0
    db = await _get_db()
    coll = db[_mongo_collection_name()]
    now = datetime.now(timezone.utc).isoformat()
    n = 0
    for v in videos:
        vid = v.get("video_id")
        if not vid:
            continue
        doc = {
            **v,
            "pipeline": "youtube_official",
            "ingest_run_id": run_id,
            "fetched_at": now,
        }
        await coll.update_one({"video_id": vid, "pipeline": "youtube_official"}, {"$set": doc}, upsert=True)
        n += 1
    return n


def collect_video_ids_official(cfg: dict[str, Any], api_key: str, tracker: _QuotaTracker) -> list[str]:
    """Gather video IDs from monitored channels + limited search (all official API)."""
    max_total = max(1, int(cfg.get("max_total_videos_per_run") or 40))
    max_ch = max(0, int(cfg.get("max_channels_per_run") or 5))
    per_ch = max(1, int(cfg.get("max_playlist_items_per_channel") or 12))
    max_searches = max(0, int(cfg.get("max_searches_per_run") or 2))
    per_search = max(1, int(cfg.get("max_results_per_search") or 15))
    search_order = (cfg.get("search_order") or "date").strip()  # date | viewCount

    seen: set[str] = set()
    ordered: list[str] = []

    channel_ids = cfg.get("monitor_channel_ids") or []
    if isinstance(channel_ids, str):
        channel_ids = [channel_ids]
    channel_ids = [str(c).strip() for c in channel_ids if str(c).strip()][:max_ch]

    for ch in channel_ids:
        if len(ordered) >= max_total:
            break
        uploads = _channels_uploads_playlist_id(ch, api_key, tracker)
        if not uploads:
            logger.warning("youtube_official_channel_no_uploads_playlist", channel_id=ch)
            continue
        remaining = max_total - len(ordered)
        ids = _playlist_video_ids(uploads, api_key, tracker, min(per_ch, remaining))
        for vid in ids:
            if vid not in seen:
                seen.add(vid)
                ordered.append(vid)

    queries = cfg.get("discovery_search_queries") or []
    if isinstance(queries, str):
        queries = [queries]
    queries = [str(q).strip() for q in queries if str(q).strip()]
    delay = max(0.0, float(cfg.get("delay_seconds_between_api_calls") or 0.4))

    for q in queries[:max_searches]:
        if len(ordered) >= max_total:
            break
        ids = _search_video_ids(q, api_key, tracker, min(per_search, max_total - len(ordered) + 10), order=search_order)
        for vid in ids:
            if vid not in seen:
                seen.add(vid)
                ordered.append(vid)
        if delay:
            time.sleep(delay)

    return ordered[:max_total]


def enrich_with_comments(
    videos: list[dict[str, Any]],
    api_key: str,
    tracker: _QuotaTracker,
    max_videos: int,
    max_threads: int,
    delay_s: float,
) -> None:
    if max_videos <= 0:
        return
    # Prefer high-engagement videos for comment sampling
    ranked = sorted(videos, key=lambda v: (v.get("views") or 0, v.get("comment_count") or 0), reverse=True)

    for v in ranked[:max_videos]:
        vid = v.get("video_id")
        if not vid:
            continue
        try:
            v["top_comments"] = _comment_threads_for_video(vid, api_key, tracker, max_threads)
        except Exception as e:
            logger.debug("youtube_official_comments_skip", video_id=vid, error=str(e))
            v["top_comments"] = []
        if delay_s:
            time.sleep(delay_s)


async def run_youtube_official_ingest() -> dict[str, Any]:
    """
    Main entry: collect IDs → videos.list → optional comments → upsert Mongo.

    Returns stats for scheduler / diagnostics.
    """
    cfg = _cfg()
    if not cfg.get("enabled", False):
        return {"ok": False, "reason": "youtube_official disabled", "saved": 0}

    api_key = _api_key()
    if not api_key:
        logger.warning("youtube_official_api_key_missing")
        return {"ok": False, "reason": "YOUTUBE_API_KEY missing", "saved": 0}

    run_id = str(uuid.uuid4())
    tracker = _QuotaTracker()

    def _sync_pipeline() -> tuple[list[dict[str, Any]], int, list[tuple[str, int]]]:
        ids = collect_video_ids_official(cfg, api_key, tracker)
        videos = _videos_list_details(ids, api_key, tracker)
        max_comment_videos = max(0, int(cfg.get("max_videos_for_comment_fetch") or 0))
        max_threads = max(1, int(cfg.get("max_comment_threads_per_video") or 10))
        delay = max(0.0, float(cfg.get("delay_seconds_between_api_calls") or 0.4))
        enrich_with_comments(videos, api_key, tracker, max_comment_videos, max_threads, delay)
        return videos, tracker.units, list(tracker.calls)

    videos, units, quota_ops = await asyncio.to_thread(_sync_pipeline)
    saved = await _save_videos(videos, run_id)

    logger.info(
        "youtube_official_ingest_complete",
        run_id=run_id,
        videos_fetched=len(videos),
        saved=saved,
        estimated_quota_units=units,
        quota_ops=quota_ops,
    )
    return {
        "ok": True,
        "run_id": run_id,
        "videos_fetched": len(videos),
        "saved": saved,
        "estimated_quota_units": units,
    }
