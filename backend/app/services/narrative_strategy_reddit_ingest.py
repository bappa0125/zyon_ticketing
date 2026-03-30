"""
Narrative Strategy Engine - Reddit ingestion.

Goal: collect high-signal market discussions (posts + top comments) WITHOUT filtering by company mentions.
This is intentionally separate from the existing reddit_monitor/reddit_trending pipelines so we don't break anything.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_config
from app.core.hash_utils import generate_content_hash
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class IngestStats:
    posts_fetched: int = 0
    comments_fetched: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0


def _cfg() -> dict[str, Any]:
    return get_config().get("narrative_strategy_engine") or {}


def _reddit_cfg() -> dict[str, Any]:
    return _cfg().get("reddit") or {}


def _mongo_cfg() -> dict[str, Any]:
    return _cfg().get("mongodb") or {}


def _raw_collection() -> str:
    return (_mongo_cfg().get("raw_collection") or "narrative_strategy_reddit_raw").strip()


def _user_agent() -> str:
    ua = (_reddit_cfg().get("user_agent") or "ZyonNarrativeStrategy/1.0").strip()
    return ua or "ZyonNarrativeStrategy/1.0"


def _listing_url(subreddit: str, sort: str, top_period: str, limit: int) -> str:
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
    if sort == "top":
        url += f"?t={top_period}"
    url += "&" if "?" in url else "?"
    url += f"limit={min(limit, 100)}"
    return url


def _comments_url(permalink: str, limit: int) -> str:
    # permalink is like /r/foo/comments/<id>/...
    p = (permalink or "").strip()
    if not p:
        return ""
    if not p.startswith("http"):
        p = f"https://www.reddit.com{p}" if p.startswith("/") else ""
    if not p:
        return ""
    # Use raw_json=1 to avoid HTML entities where possible
    sep = "&" if "?" in p else "?"
    return f"{p}.json{sep}limit={min(limit, 50)}&raw_json=1"


def _safe_dt_from_listing(raw: dict) -> datetime:
    created_utc = raw.get("created_utc")
    if isinstance(created_utc, (int, float)):
        return datetime.fromtimestamp(float(created_utc), tz=timezone.utc)
    return datetime.now(timezone.utc)


def _norm_post(raw: dict, subreddit: str) -> dict[str, Any] | None:
    try:
        title = (raw.get("title") or "").strip()
        selftext = (raw.get("selftext") or "").strip()
        if not title and not selftext:
            return None
        permalink = (raw.get("permalink") or "").strip()
        url = permalink
        if url and not url.startswith("http"):
            url = f"https://www.reddit.com{url}" if url.startswith("/") else ""
        post_id = (raw.get("id") or "").strip()
        score = int(raw.get("score") or 0)
        num_comments = int(raw.get("num_comments") or 0)
        created_at = _safe_dt_from_listing(raw)
        text = " ".join([t for t in (title, selftext) if t]).strip()
        if not text:
            return None
        return {
            "kind": "post",
            "platform": "reddit",
            "subreddit": subreddit,
            "reddit_id": post_id[:20],
            "url": url[:500],
            "title": title[:500],
            "body": selftext[:4000],
            "text": text[:8000],
            "engagement": {"score": score, "comments": num_comments},
            "published_at": created_at,
        }
    except Exception:
        return None


def _flatten_comments(node: Any, out: list[dict[str, Any]], limit: int) -> None:
    if len(out) >= limit:
        return
    if not isinstance(node, dict):
        return
    # Reddit comment listing nodes can be weird; we just walk 'data.children'
    data = node.get("data")
    if isinstance(data, dict) and isinstance(data.get("children"), list):
        for ch in data.get("children") or []:
            if len(out) >= limit:
                return
            if not isinstance(ch, dict):
                continue
            if ch.get("kind") != "t1":
                # not a comment
                continue
            cdata = ch.get("data") or {}
            body = (cdata.get("body") or "").strip()
            if body:
                out.append(
                    {
                        "reddit_comment_id": (cdata.get("id") or "")[:20],
                        "body": body[:3000],
                        "score": int(cdata.get("score") or 0),
                    }
                )
            # replies can be a dict listing
            replies = cdata.get("replies")
            if isinstance(replies, dict):
                _flatten_comments(replies, out, limit)


async def _fetch_json(url: str, headers: dict[str, str], *, purpose: str) -> Any:
    r_cfg = _reddit_cfg()
    sa = r_cfg.get("scrapingant") or {}
    sa_enabled = bool(sa.get("enabled", False))
    sa_daily_cap = int(sa.get("daily_cap_calls") or 50)
    fallback_statuses = sa.get("fallback_statuses") or [429, 403]
    fallback_statuses = [int(x) for x in fallback_statuses if isinstance(x, (int, float, str)) and str(x).isdigit()]
    use_for_listings = bool(sa.get("use_for_listings", True))
    use_for_comments = bool(sa.get("use_for_comments", False))
    allow_for_purpose = (purpose == "listing" and use_for_listings) or (purpose == "comments" and use_for_comments)

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            status = int(getattr(e.response, "status_code", 0) or 0)
            if sa_enabled and allow_for_purpose and status in fallback_statuses:
                try:
                    from app.services.scrapingant_service import fetch_json_via_scrapingant

                    return await fetch_json_via_scrapingant(url, daily_cap=sa_daily_cap)
                except RuntimeError as e2:
                    # If the daily cap is reached, do a best-effort direct retry with a short backoff
                    # rather than failing the whole ingest immediately.
                    msg = str(e2).lower()
                    if "daily cap" in msg:
                        await asyncio.sleep(2.5)
                        resp2 = await client.get(url, headers=headers)
                        resp2.raise_for_status()
                        return resp2.json()
                    raise
                except Exception:
                    raise
            raise


async def ingest_reddit_raw() -> dict[str, Any]:
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return {"ok": False, "reason": "narrative_strategy_engine disabled"}

    r_cfg = _reddit_cfg()
    subreddits = r_cfg.get("subreddits") or []
    if not subreddits:
        return {"ok": False, "reason": "no subreddits configured"}

    sort = (r_cfg.get("sort") or "hot").strip().lower() or "hot"
    top_period = (r_cfg.get("top_period") or "day").strip().lower() or "day"
    per_sub = min(int(r_cfg.get("posts_per_subreddit") or 25), 100)
    delay = max(0.5, float(r_cfg.get("delay_seconds_between_subreddits") or 1.5))

    fetch_comments = bool(r_cfg.get("fetch_top_comments", True))
    top_comments_per_post = min(int(r_cfg.get("top_comments_per_post") or 8), 20)
    max_posts_total = int(r_cfg.get("max_posts_total_per_run") or 500)
    max_comments_total = int(r_cfg.get("max_comments_total_per_run") or 2500)

    headers = {"User-Agent": _user_agent()}
    now = datetime.now(timezone.utc)
    stats = IngestStats()

    from app.services.mongodb import get_mongo_client, get_db

    await get_mongo_client()
    db = get_db()
    coll = db[_raw_collection()]

    async def _upsert(doc: dict[str, Any], key: dict[str, Any]) -> None:
        nonlocal stats
        try:
            doc["fetched_at"] = now
            doc["pipeline"] = "narrative_strategy_reddit"
            # stable hash for quick dedup
            doc["content_hash"] = generate_content_hash((doc.get("text") or "")[:8000])
            res = await coll.update_one(key, {"$set": doc}, upsert=True)
            if getattr(res, "upserted_id", None):
                stats.inserted += 1
            elif getattr(res, "modified_count", 0) > 0:
                stats.updated += 1
            else:
                stats.skipped += 1
        except Exception as e:
            stats.errors += 1
            logger.debug("narrative_strategy_reddit_upsert_failed", error=str(e))

    posts_seen = 0
    comments_seen = 0

    for sub in subreddits:
        if posts_seen >= max_posts_total:
            break
        if not isinstance(sub, str) or not sub.strip():
            continue
        sub = sub.strip()
        url = _listing_url(sub, sort=sort, top_period=top_period, limit=per_sub)
        try:
            data = await _fetch_json(url, headers=headers, purpose="listing")
        except Exception as e:
            stats.errors += 1
            logger.warning("narrative_strategy_reddit_fetch_failed", subreddit=sub, error=str(e))
            await asyncio.sleep(delay)
            continue

        children = (data.get("data") or {}).get("children") or []
        raw_posts = [c.get("data") for c in children if isinstance(c, dict) and isinstance(c.get("data"), dict)]

        for raw in raw_posts:
            if posts_seen >= max_posts_total:
                break
            post = _norm_post(raw, sub)
            if not post:
                continue
            stats.posts_fetched += 1
            posts_seen += 1

            # attach top comments
            permalink = (raw.get("permalink") or "").strip()
            if fetch_comments and permalink and comments_seen < max_comments_total:
                c_url = _comments_url(permalink, limit=top_comments_per_post)
                if c_url:
                    try:
                        cjson = await _fetch_json(c_url, headers=headers, purpose="comments")
                        # comments endpoint returns a list: [postListing, commentsListing]
                        comments_flat: list[dict[str, Any]] = []
                        if isinstance(cjson, list) and len(cjson) >= 2:
                            _flatten_comments(cjson[1], comments_flat, top_comments_per_post)
                        # Keep top by score
                        comments_flat.sort(key=lambda x: int(x.get("score") or 0), reverse=True)
                        comments_flat = comments_flat[:top_comments_per_post]
                        post["top_comments"] = comments_flat
                        comments_seen += len(comments_flat)
                        stats.comments_fetched += len(comments_flat)
                    except Exception as e:
                        stats.errors += 1
                        logger.debug("narrative_strategy_reddit_comments_failed", subreddit=sub, error=str(e))

            key = {"pipeline": "narrative_strategy_reddit", "platform": "reddit", "kind": "post", "reddit_id": post.get("reddit_id", ""), "subreddit": sub}
            await _upsert(post, key)

        await asyncio.sleep(delay)

    return {
        "ok": True,
        "collection": _raw_collection(),
        "posts_fetched": stats.posts_fetched,
        "comments_fetched": stats.comments_fetched,
        "inserted": stats.inserted,
        "updated": stats.updated,
        "skipped": stats.skipped,
        "errors": stats.errors,
    }

