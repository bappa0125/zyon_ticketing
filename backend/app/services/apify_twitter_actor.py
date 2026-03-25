"""
Apify Twitter/X actors — input builders and tweet normalization.

Supported styles (set monitoring.apify.twitter_input_style):
- apify_official: Apify Store Twitter (X) Scraper — actor id e.g. 61RPP7dywgiy0JPD0 / apify/twitter-scraper.
  Input: startUrls, searchTerms, twitterHandles, maxItems, sort, tweetLanguage (omit null keys).
- tweet_scraper_v2: apidojo/tweet-scraper (searchTerms, maxItems, sort).
- scraper_engine: scraper-engine/twitter-x-scraper (startUrls, maxTweets).

Optional YAML lists (apify_official):
- twitter_search_terms: if set, used as searchTerms; else one entry with combined OR query.
- twitter_start_urls, twitter_handles: optional lists of strings.

Actor fields change over time; verify input in Apify Console.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def _intish(x: Any) -> int:
    if x is None:
        return 0
    if isinstance(x, bool):
        return int(x)
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def _detect_entity(text: str, entities: list[str]) -> str | None:
    if not text:
        return None
    text_lower = text.lower()
    for e in entities:
        if e and e.lower() in text_lower:
            return e
    return None


def _parse_tweet_timestamp(raw: Any) -> datetime:
    if raw is None:
        return datetime.now(timezone.utc)
    if isinstance(raw, (int, float)):
        ts = float(raw)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    s = str(raw).strip()
    if not s:
        return datetime.now(timezone.utc)
    if "T" in s:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            pass
    for fmt in ("%a %b %d %H:%M:%S %z %Y",):
        try:
            return datetime.strptime(s, fmt).astimezone(timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("twitter_timestamp_parse_failed", raw=s[:80])
        return datetime.now(timezone.utc)


def _omit_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def build_twitter_actor_input(
    *,
    style: str,
    combined_query: str,
    max_items: int,
    apify_cfg: dict[str, Any],
) -> dict[str, Any]:
    """
    Build run_input for the configured Twitter Apify actor.

    combined_query: single string, typically "A OR B OR C" from entity names.
    """
    style_norm = (style or "tweet_scraper_v2").strip().lower().replace("-", "_")
    cap = max(1, min(int(max_items), 2000))

    if style_norm == "apify_official":
        raw_terms = apify_cfg.get("twitter_search_terms")
        if isinstance(raw_terms, list) and len(raw_terms) > 0:
            search_terms = [str(x).strip() for x in raw_terms if str(x).strip()]
        else:
            search_terms = [combined_query] if combined_query.strip() else []
        su = apify_cfg.get("twitter_start_urls")
        start_urls = [str(u).strip() for u in su] if isinstance(su, list) else []
        th = apify_cfg.get("twitter_handles")
        handles = [str(h).strip().lstrip("@") for h in th] if isinstance(th, list) else []
        sort = str(apify_cfg.get("twitter_sort") or "Latest").strip()
        out: dict[str, Any] = {
            "searchTerms": search_terms,
            "maxItems": cap,
            "sort": sort,
        }
        if start_urls:
            out["startUrls"] = start_urls
        if handles:
            out["twitterHandles"] = handles
        lang = apify_cfg.get("twitter_tweet_language")
        if isinstance(lang, str) and lang.strip():
            out["tweetLanguage"] = lang.strip()
        return _omit_none(out)

    if style_norm == "scraper_engine":
        return {
            "startUrls": [combined_query],
            "maxTweets": cap,
        }

    if style_norm == "tweet_scraper_v2":
        sort = str(apify_cfg.get("twitter_sort") or "Latest").strip()
        out: dict[str, Any] = {
            "searchTerms": [combined_query],
            "maxItems": cap,
            "sort": sort,
        }
        lang = apify_cfg.get("twitter_tweet_language")
        if isinstance(lang, str) and lang.strip():
            out["tweetLanguage"] = lang.strip()
        return out

    raise ValueError(f"Unknown twitter_input_style: {style!r}")


def normalize_tweet_for_social_posts(
    item: dict[str, Any],
    entities: list[str],
) -> dict[str, Any] | None:
    """
    Map Apify tweet dataset row → social_posts-style dict (platform twitter).
    Handles apidojo/tweet-scraper, Apify official Twitter scraper, and legacy shapes.
    """
    typ = str(item.get("type") or item.get("__typename") or "").lower()
    if typ in ("user", "profile", "consumer", "author"):
        return None

    nested = item.get("tweet")
    if isinstance(nested, dict):
        base = nested
    else:
        base = item

    legacy = base.get("legacy") if isinstance(base.get("legacy"), dict) else None
    if legacy:
        text = legacy.get("full_text") or legacy.get("text") or ""
    else:
        text = ""

    if not text:
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
    entity = _detect_entity(str(text), entities)
    if not entity:
        return None

    src = legacy or base
    likes = (
        src.get("likeCount")
        or src.get("favorite_count")
        or src.get("favorites")
        or src.get("likes")
        or item.get("likeCount")
        or item.get("favorite_count")
        or 0
    )
    retweets = (
        src.get("retweetCount")
        or src.get("retweet_count")
        or src.get("retweets")
        or item.get("retweetCount")
        or item.get("retweet_count")
        or 0
    )
    replies = (
        src.get("replyCount")
        or src.get("reply_count")
        or src.get("comments")
        or item.get("replyCount")
        or item.get("reply_count")
        or 0
    )

    url = (
        base.get("url")
        or base.get("twitterUrl")
        or item.get("url")
        or item.get("twitterUrl")
        or item.get("tweet_url")
        or ""
    )
    tid = base.get("id") or item.get("id")
    if not url and tid:
        url = f"https://x.com/i/status/{tid}"
    if url and not str(url).startswith("http"):
        url = f"https://x.com/i/status/{url}" if str(url).isdigit() else ""

    created = (
        src.get("createdAt")
        or src.get("created_at")
        or (legacy.get("created_at") if legacy else None)
        or item.get("createdAt")
        or item.get("created_at")
        or item.get("date")
        or item.get("timestamp")
    )
    ts = _parse_tweet_timestamp(created)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    return {
        "platform": "twitter",
        "entity": entity,
        "text": (text or "")[:500],
        "url": (str(url) or "")[:500],
        "engagement": {
            "likes": _intish(likes),
            "retweets": _intish(retweets),
            "comments": _intish(replies),
        },
        "timestamp": ts,
    }
