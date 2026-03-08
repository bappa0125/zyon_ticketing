"""Social monitor worker — fetch from Apify, apply guardrails, store in MongoDB."""
from datetime import datetime

from app.core.hash_utils import generate_content_hash
from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client
from app.services.social_filter_service import filter_low_engagement
from app.services.social_monitor_service import fetch_social_mentions

logger = get_logger(__name__)

COLLECTION_NAME = "social_posts"


async def run_social_monitor() -> dict[str, int]:
    """
    Fetch social mentions from Apify, apply guardrails (engagement filter,
    dedup, daily limit), store in social_posts.
    """
    from app.config import get_config
    from app.services.mongodb import get_db

    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION_NAME]

    config = get_config()
    mon = config.get("monitoring", {})
    social = mon.get("social_data", {})
    dedup_enabled = social.get("deduplication", {}).get("enabled", True)
    max_per_entity_per_day = social.get("max_posts_per_entity_per_day", 100)

    inserted = 0
    skipped = 0

    try:
        raw_posts = await fetch_social_mentions()
    except Exception as e:
        logger.warning("social_monitor_fetch_failed", error=str(e))
        return {"inserted": 0, "skipped": 0, "errors": 1}

    posts = filter_low_engagement(raw_posts)
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    for post in posts:
        try:
            text = post.get("text") or ""
            content_hash = generate_content_hash(text)
            entity = post.get("entity", "")
            ts = post.get("timestamp", datetime.utcnow())
            if isinstance(ts, datetime):
                ts_bson = ts
            else:
                ts_bson = datetime.utcnow()

            if dedup_enabled and content_hash:
                existing = await coll.find_one({"content_hash": content_hash})
                if existing:
                    skipped += 1
                    continue

            start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            count_today = await coll.count_documents({
                "entity": entity,
                "timestamp": {"$gte": start_of_day},
            })
            if count_today >= max_per_entity_per_day:
                skipped += 1
                continue

            doc = {
                "platform": post.get("platform", ""),
                "entity": entity,
                "text": (text or "")[:500],
                "url": (post.get("url") or "")[:500],
                "content_hash": content_hash,
                "engagement": post.get("engagement", {}),
                "timestamp": ts_bson,
            }
            await coll.insert_one(doc)
            inserted += 1

        except Exception as e:
            logger.warning("social_monitor_insert_failed", error=str(e))
            skipped += 1

    if inserted or skipped:
        logger.info("social_monitor_run_complete", inserted=inserted, skipped=skipped)

    return {"inserted": inserted, "skipped": skipped}
