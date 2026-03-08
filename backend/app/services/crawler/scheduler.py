"""Dynamic scheduler - priority queues, due competitors only."""
from redis import Redis
from rq import Queue
from app.config import get_config
from app.core.logging import get_logger
from app.services.crawler.jobs import crawl_website
from app.services.crawler.snapshot_store_sync import get_competitors_for_crawl_sync

logger = get_logger(__name__)

QUEUE_NAMES = ["high_priority", "normal_priority", "low_priority"]


def get_queue(name: str = "low_priority") -> Queue:
    url = get_config()["settings"].redis_url
    redis_conn = Redis.from_url(url)
    return Queue(name, connection=redis_conn)


def get_crawler_queue() -> Queue:
    """Crawler jobs use low_priority queue."""
    return get_queue("low_priority")


def enqueue_crawls(max_per_run: int = 10):
    """
    Enqueue only competitors due for crawl, ordered by priority.
    Limits jobs per run for streaming behavior.
    """
    queue = get_crawler_queue()
    competitors = get_competitors_for_crawl_sync()[:max_per_run]
    for c in competitors:
        cid = str(c["_id"])
        website = (c.get("website") or "").strip()
        if website:
            queue.enqueue(crawl_website, cid, website)
            logger.info("enqueued_crawl", competitor_id=cid, website=website, priority=queue.name)
