"""YouTube monitoring via Apify. Actor name from config.monitoring.youtube.actor."""
from datetime import datetime
from typing import Any

from app.config import get_config
from app.core.logging import get_logger
from app.services.apify_service import run_actor
from app.services.entity_detection_service import detect_entity, get_entities_and_aliases

logger = get_logger(__name__)


def fetch_youtube_mentions() -> list[dict[str, Any]]:
    """
    Build combined query from entity aliases, run Apify actor from config.
    Extract video_title, video_description, comments, url, views.
    Run entity_detection_service. Return normalized items for guardrails pipeline.
    """
    config = get_config()
    mon = config.get("monitoring", {}).get("youtube", {})
    if not mon.get("enabled"):
        return []

    actor_id = (mon.get("actor") or "").strip()
    if not actor_id:
        logger.warning("youtube_actor_not_configured")
        return []

    max_items = mon.get("max_items_per_run", 10)

    entity_aliases = get_entities_and_aliases()
    entities = list(entity_aliases.keys())
    if not entities:
        return []

    query = " OR ".join(entities)

    input_data: dict[str, Any] = {
        "searchKeywords": query,
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
            title = item.get("video_title") or item.get("title") or item.get("name") or ""
            desc = item.get("video_description") or item.get("description") or ""
            url = item.get("url") or item.get("videoUrl") or item.get("link") or ""
            channel = item.get("channelName") or item.get("channel") or item.get("author") or ""
            views = item.get("views") or item.get("viewCount") or 0
            likes = item.get("likes") or item.get("likeCount") or 0
            comments_raw = item.get("comments")
            if isinstance(comments_raw, (int, float)):
                comment_count = int(comments_raw)
            else:
                comment_count = item.get("commentCount") or 0

            text_candidates = [title, desc]
            comments = comments_raw if isinstance(comments_raw, list) else None
            if isinstance(comments, list):
                for c in comments[:5]:
                    if isinstance(c, dict):
                        t = c.get("text") or c.get("content") or c.get("comment") or ""
                        if t:
                            text_candidates.append(t)
                    elif isinstance(c, str):
                        text_candidates.append(c)
            elif isinstance(comments, str):
                text_candidates.append(comments)

            for text in text_candidates:
                if not text or not isinstance(text, str):
                    continue
                text = text.strip()[:500]
                if not text:
                    continue

                entity = detect_entity(text)
                if not entity:
                    continue

                content_key = f"{entity}:{text[:150]}"
                if content_key in seen_hashes:
                    continue
                seen_hashes.add(content_key)

                created = item.get("publishedAt") or item.get("uploadDate") or item.get("createdAt")
                if isinstance(created, str):
                    try:
                        ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        ts = datetime.utcnow()
                else:
                    ts = datetime.utcnow()

                results.append({
                    "platform": "youtube",
                    "entity": entity,
                    # Keep video fields so UI can show video link + description.
                    "video_title": (title or "")[:300],
                    "video_description": (desc or "")[:1200],
                    "channel": (channel or "")[:120],
                    "text": text,
                    "url": (url or "")[:500],
                    "engagement": {"likes": int(likes), "retweets": 0, "comments": int(comment_count)},
                    "timestamp": ts,
                })
                if len(results) >= max_items:
                    break
        except Exception as e:
            logger.debug("youtube_item_skip", error=str(e))
            continue

    return results[:max_items]
