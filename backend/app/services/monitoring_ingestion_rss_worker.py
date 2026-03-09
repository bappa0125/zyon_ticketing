"""
RSS Ingestion Worker — scheduled task: one cycle of RSS metadata ingestion.
STEP 4: Fetches RSS feeds, stores metadata in rss_items. No article crawling.
Invoke periodically (e.g. cron or docker restart with sleep); does not run an infinite loop.
"""
import asyncio

from app.core.logging import get_logger
from app.services.monitoring_ingestion.rss_ingestion import run_rss_ingestion

logger = get_logger(__name__)


async def run_rss_ingestion_worker(max_feeds: int = 10) -> dict:
    """Run one RSS ingestion cycle. Returns stats from run_rss_ingestion."""
    return await run_rss_ingestion(max_feeds=max_feeds)


def run_once(max_feeds: int = 10) -> dict:
    """Synchronous entrypoint for one cycle (e.g. from script or cron)."""
    return asyncio.run(run_rss_ingestion_worker(max_feeds=max_feeds))


if __name__ == "__main__":
    # Single run then exit; scheduler/cron restarts or re-invokes
    stats = run_once()
    logger.info(
        "rss_ingestion_worker_done",
        feeds_processed=stats.get("feeds_processed", 0),
        articles_discovered=stats.get("articles_discovered", 0),
        duplicates_skipped=stats.get("duplicates_skipped", 0),
    )
