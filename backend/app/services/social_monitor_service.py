"""Social monitor — fetch mentions via Apify using combined OR query."""
from datetime import datetime
from typing import Any

from app.core.client_config_loader import get_entity_names, load_clients
from app.core.logging import get_logger
from app.services.apify_service import run_actor
from app.services.apify_twitter_actor import build_twitter_actor_input, normalize_tweet_for_social_posts

logger = get_logger(__name__)


def _detect_entity(text: str, entities: list[str]) -> str | None:
    """Detect which entity is mentioned in text (case-insensitive)."""
    if not text:
        return None
    text_lower = text.lower()
    for e in entities:
        if e and e.lower() in text_lower:
            return e
    return None


def _normalize_youtube(item: dict[str, Any], entities: list[str]) -> dict[str, Any] | None:
    """Normalize YouTube comment scraper output."""
    text = item.get("text") or item.get("comment") or item.get("content") or ""
    entity = _detect_entity(text, entities)
    if not entity:
        return None
    likes = item.get("likeCount") or item.get("likes") or 0
    replies = item.get("replyCount") or item.get("replies") or 0
    url = item.get("url") or item.get("commentUrl") or ""
    created = item.get("publishedAt") or item.get("createdAt") or item.get("timestamp")
    if isinstance(created, str):
        try:
            ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            ts = datetime.utcnow()
    else:
        ts = datetime.utcnow()
    return {
        "platform": "youtube",
        "entity": entity,
        "text": (text or "")[:500],
        "url": (url or "")[:500],
        "engagement": {"likes": int(likes), "retweets": 0, "comments": int(replies)},
        "timestamp": ts,
    }


async def fetch_social_mentions() -> list[dict[str, Any]]:
    """
    Load entities from clients.yaml, build combined OR query.
    Run Apify actors (Twitter, YouTube), normalize and limit by max_items_per_run.
    """
    clients = await load_clients()
    entities: list[str] = []
    for c in clients:
        entities.extend(get_entity_names(c))
    entities = list(dict.fromkeys(e for e in entities if e))

    if not entities:
        return []

    from app.config import get_config
    config = get_config()
    mon = config.get("monitoring", {})
    sources = mon.get("social_sources", {})
    apify_cfg = mon.get("apify", {})
    max_items = apify_cfg.get("max_items_per_run", 20)

    query = " OR ".join(entities)
    results: list[dict[str, Any]] = []

    if sources.get("twitter"):
        actor_id = apify_cfg.get("twitter_actor", "apidojo/tweet-scraper")
        input_style = apify_cfg.get("twitter_input_style", "tweet_scraper_v2")
        try:
            input_data = build_twitter_actor_input(
                style=input_style,
                combined_query=query,
                max_items=max_items,
                apify_cfg=apify_cfg,
            )
        except ValueError as e:
            logger.warning("twitter_apify_input_style_invalid", error=str(e))
            input_data = build_twitter_actor_input(
                style="tweet_scraper_v2",
                combined_query=query,
                max_items=max_items,
                apify_cfg=apify_cfg,
            )
        items = run_actor(actor_id, input_data)
        for item in items:
            norm = normalize_tweet_for_social_posts(item, entities)
            if norm:
                results.append(norm)
        results = results[:max_items]

    if sources.get("youtube") and len(results) < max_items:
        actor_id = apify_cfg.get("youtube_actor", "streamers/youtube-scraper")
        # streamers/youtube-scraper: adjust input if schema differs (e.g. searchQuery, maxResults)
        input_data = {"searchKeywords": query, "maxItems": min(max_items - len(results), 20)}
        items = run_actor(actor_id, input_data)
        for item in items:
            norm = _normalize_youtube(item, entities)
            if norm:
                results.append(norm)
        results = results[:max_items]

    return results
