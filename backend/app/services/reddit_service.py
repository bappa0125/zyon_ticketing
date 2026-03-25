"""Reddit monitoring via Apify. Actor name from config.monitoring.reddit.actor."""
from datetime import datetime
from typing import Any

from app.config import get_config
from app.core.logging import get_logger
from app.services.apify_service import run_actor
from app.services.entity_detection_service import detect_entity, get_entities_and_aliases

logger = get_logger(__name__)


def fetch_reddit_mentions() -> list[dict[str, Any]]:
    """
    Build combined query "Sahi OR Zerodha OR Upstox", run Apify actor from config.
    Extract title, text, url, score, comments. Run entity_detection_service.
    Return normalized posts for guardrails pipeline.
    """
    config = get_config()
    mon = config.get("monitoring", {}).get("reddit", {})
    if not mon.get("enabled"):
        return []

    actor_id = (mon.get("actor") or "").strip()
    if not actor_id:
        logger.warning("reddit_actor_not_configured")
        return []

    max_items = mon.get("max_items_per_run", 20)

    entity_aliases = get_entities_and_aliases()
    entities = list(entity_aliases.keys())
    if not entities:
        return []

    query = " OR ".join(entities)

    # Support both searchTerms (spec) and searches (trudax/reddit-scraper)
    input_data: dict[str, Any] = {
        "searchTerms": [query],
        "searches": [query],
        "searchPosts": True,
        "maxItems": min(max_items, 50),
    }

    items = run_actor(actor_id, input_data)
    if not items:
        return []

    results: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    for item in items:
        if len(results) >= max_items:
            break
        try:
            title = item.get("title") or item.get("postTitle") or item.get("name") or ""
            body = (
                item.get("body")
                or item.get("selfText")
                or item.get("text")
                or item.get("content")
                or ""
            )
            text = f"{title} {body}".strip()
            if not text:
                continue

            entity = detect_entity(text)
            if not entity:
                continue

            url = item.get("url") or item.get("postUrl") or item.get("permalink") or ""
            if url and not url.startswith("http"):
                url = f"https://reddit.com{url}" if url.startswith("/") else ""

            subreddit = item.get("subreddit") or item.get("subredditName") or item.get("subreddit_name") or ""

            score = (
                item.get("score")
                or item.get("upVotes")
                or item.get("ups")
                or item.get("upvotes")
                or 0
            )
            raw_comments = (
                item.get("numberOfComments")
                or item.get("numComments")
                or item.get("commentCount")
            )
            if isinstance(raw_comments, (int, float)):
                num_comments = int(raw_comments)
            elif isinstance(raw_comments, str):
                try:
                    num_comments = int(raw_comments)
                except (ValueError, TypeError):
                    num_comments = 0
            elif isinstance(item.get("comments"), list):
                num_comments = len(item.get("comments"))
            else:
                num_comments = 0

            content_key = f"{entity}:{text[:200]}"
            if content_key in seen_hashes:
                continue
            seen_hashes.add(content_key)

            created = item.get("createdAt") or item.get("created") or item.get("timestamp")
            if isinstance(created, str):
                try:
                    ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    ts = datetime.utcnow()
            else:
                ts = datetime.utcnow()

            results.append({
                "platform": "reddit",
                "entity": entity,
                # Keep structured fields so UI can show "discussion thread" cleanly.
                "title": (title or "")[:300],
                "body": (body or "")[:700],
                "subreddit": (subreddit or "")[:80],
                "text": text[:500],
                "url": (url or "")[:500],
                "engagement": {"likes": int(score), "retweets": 0, "comments": int(num_comments)},
                "timestamp": ts,
            })
        except Exception as e:
            logger.debug("reddit_item_skip", error=str(e))
            continue

    return results[:max_items]
