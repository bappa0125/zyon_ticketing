"""Index scheduler - crawl every 30 min, max 20 articles per cycle."""
from app.config import get_config
from app.core.logging import get_logger
from app.services.media_index.article_indexer import index_articles

logger = get_logger(__name__)


def run_index_cycle() -> int:
    """Run one crawl+index cycle. Returns articles indexed."""
    cfg = get_config().get("media_index", {})
    max_articles = cfg.get("max_articles_per_cycle", 20)
    count = index_articles(max_articles=max_articles)
    # Update Redis metrics
    try:
        from redis import Redis
        r = Redis.from_url(get_config()["settings"].redis_url)
        r.incr("media_index:articles_indexed_total", count)
        r.incr("media_index:crawler_cycles_total")
    except Exception:
        pass
    logger.info("media_index_cycle_done", indexed=count)
    return count
