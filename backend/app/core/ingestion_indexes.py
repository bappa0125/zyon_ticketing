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

        # pr_daily_snapshots (P1/P2 report collections)
        try:
            ps = db["pr_daily_snapshots"]
            await ps.create_index([("client", 1), ("date", -1)], name="ix_client_date")
        except Exception as e:
            logger.debug("pr_daily_snapshots_index_skip", error=str(e))
        try:
            pr = db["pr_press_releases"]
            await pr.create_index([("client", 1), ("published_at", -1)], name="ix_client_published_at")
        except Exception as e:
            logger.debug("pr_press_releases_index_skip", error=str(e))
        try:
            pp = db["pr_press_release_pickups"]
            await pp.create_index([("client", 1), ("published_at", -1)], name="ix_client_published_at")
            await pp.create_index([("press_release_id", 1), ("article_url", 1)], name="ix_pr_url_unique")
        except Exception as e:
            logger.debug("pr_press_release_pickups_index_skip", error=str(e))
        try:
            po = db["pr_opportunities"]
            await po.create_index([("client", 1), ("type", 1), ("date", -1)], name="ix_client_type_date")
        except Exception as e:
            logger.debug("pr_opportunities_index_skip", error=str(e))

        # narrative_positioning (PR-focused intelligence per client)
        try:
            np = db["narrative_positioning"]
            await np.create_index([("client", 1), ("date", -1)], name="ix_client_date")
        except Exception as e:
            logger.debug("narrative_positioning_index_skip", error=str(e))

        # ai_search_answers (AI search narrative pipeline)
        try:
            asc_cfg = cfg.get("ai_search_narrative") or {}
            coll_name = (asc_cfg.get("mongodb") or {}).get("answers_collection") or "ai_search_answers"
            asc = db[coll_name]
            await asc.create_index([("date", -1), ("query", 1)], name="ix_date_query")
        except Exception as e:
            logger.debug("ai_search_answers_index_skip", error=str(e))

        # AI Search Visibility (Phase 1)
        try:
            vis_cfg = cfg.get("ai_search_visibility") or {}
            mongo = vis_cfg.get("mongodb") or {}
            answers_name = mongo.get("answers_collection") or "visibility_answers"
            runs_name = mongo.get("runs_collection") or "visibility_runs"
            snap_name = mongo.get("snapshots_collection") or "visibility_weekly_snapshots"
            rec_name = mongo.get("recommendations_collection") or "visibility_recommendations"
            await db[answers_name].create_index(
                [("query", 1), ("engine", 1), ("week", -1)],
                name="ix_query_engine_week",
            )
            await db[runs_name].create_index(
                [("client", 1), ("query", 1), ("engine", 1), ("week", -1)],
                name="ix_client_query_engine_week",
            )
            await db[snap_name].create_index([("client", 1), ("week", -1)], name="ix_client_week")
            await db[rec_name].create_index([("client", 1), ("week", -1)], name="ix_client_week")
        except Exception as e:
            logger.debug("ai_search_visibility_index_skip", error=str(e))

        # executive_competitor_reports (weekly report, fetch latest by generated_at)
        try:
            ecr = db["executive_competitor_reports"]
            await ecr.create_index([("generated_at", -1)], name="ix_generated_at")
        except Exception as e:
            logger.debug("executive_competitor_reports_index_skip", error=str(e))

        logger.info("ingestion_indexes_ensured")
    except Exception as e:
        logger.warning("ingestion_indexes_setup", error=str(e))
