"""
Article Fetcher Worker — scheduled task: one cycle of article fetch and extraction.
STEP 5: Fetches article pages, extracts text with trafilatura, stores in article_documents.
No entity detection. One run then exit; no infinite loop.
"""
import asyncio

from app.core.logging import get_logger
from app.services.monitoring_ingestion.article_fetcher import run_article_fetcher

logger = get_logger(__name__)


async def run_article_fetcher_worker(max_items: int = 20) -> dict:
    """Run one article fetch cycle. Returns metrics."""
    return await run_article_fetcher(max_items=max_items)


def run_once(max_items: int = 20) -> dict:
    """Synchronous entrypoint for one cycle (e.g. script or cron)."""
    return asyncio.run(run_article_fetcher_worker(max_items=max_items))


if __name__ == "__main__":
    stats = run_once()
    logger.info(
        "article_fetcher_worker_done",
        articles_fetched=stats.get("articles_fetched", 0),
        failures=stats.get("failures", 0),
        avg_article_length=stats.get("avg_article_length", 0),
    )
