"""Ensure social_posts collection has TTL and indexes. Run at startup."""
from app.config import get_config
from app.core.logging import get_logger
from app.services.mongodb import get_db

logger = get_logger(__name__)

COLLECTION_NAME = "social_posts"


async def ensure_social_posts_indexes():
    """
    Create TTL index and lookup indexes for social_posts.
    TTL: retention_days from config; expires documents automatically.
    Indexes: content_hash, entity, timestamp.
    """
    try:
        db = get_db()
        coll = db[COLLECTION_NAME]

        config = get_config()
        social = config.get("monitoring", {}).get("social_data", {})
        retention_days = social.get("retention_days", 30)
        ttl_seconds = retention_days * 86400

        # TTL index on published_at — MongoDB deletes docs when published_at + TTL < current time
        try:
            await coll.create_index(
                [("published_at", 1)],
                expireAfterSeconds=ttl_seconds,
                name="ttl_published_at",
            )
        except Exception:
            try:
                await coll.create_index(
                    [("timestamp", 1)],
                    expireAfterSeconds=ttl_seconds,
                    name="ttl_timestamp",
                )
            except Exception:
                pass
        logger.info("social_posts_ttl_index_created", retention_days=retention_days)

        # Lookup indexes (content_hash for dedup, entity for filtering)
        await coll.create_index("content_hash", name="ix_content_hash")
        await coll.create_index("entity", name="ix_entity")

    except Exception as e:
        # Index may already exist (MongoDB returns error if index exists with same key)
        logger.warning("social_posts_index_setup", error=str(e))
