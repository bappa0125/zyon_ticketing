"""Ensure ingestion collections have required indexes. Run at startup."""
from app.config import get_config
from app.core.logging import get_logger
from app.services.mongodb import get_db

logger = get_logger(__name__)


async def ensure_ingestion_indexes():
    """
    Create indexes for ingestion collections:
    - entity_mentions: entity + published_at
    - article_documents: entities, url_hash
    - social_posts: entity + published_at
    - rss_items: url
    """
    try:
        db = get_db()
        cfg = get_config()

        # entity_mentions
        try:
            em = db["entity_mentions"]
            await em.create_index([("entity", 1), ("published_at", -1)], name="ix_entity_published_at")
            await em.create_index([("url", 1), ("entity", 1)], name="ix_url_entity")
        except Exception as e:
            logger.debug("entity_mentions_index_skip", error=str(e))

        # article_documents
        try:
            ad = db["article_documents"]
            await ad.create_index("entities", name="ix_entities")
            await ad.create_index("url_hash", name="ix_url_hash")
            # Unprocessed-first query for entity_mentions_worker (backlog drain)
            await ad.create_index(
                [("fetched_at", 1)],
                name="ix_unprocessed_fetched",
                partialFilterExpression={
                    "$or": [
                        {"entity_mentions_processed_at": None},
                        {"entity_mentions_processed_at": {"$exists": False}},
                    ]
                },
            )
        except Exception as e:
            logger.debug("article_documents_index_skip", error=str(e))

        # social_posts
        try:
            sp = db["social_posts"]
            await sp.create_index([("entity", 1), ("published_at", -1)], name="ix_entity_published_at")
        except Exception as e:
            logger.debug("social_posts_index_skip", error=str(e))

        # rss_items
        try:
            rss = db["rss_items"]
            await rss.create_index("url", name="ix_url")
        except Exception as e:
            logger.debug("rss_items_index_skip", error=str(e))

        logger.info("ingestion_indexes_ensured")
    except Exception as e:
        logger.warning("ingestion_indexes_setup", error=str(e))
