"""In-process ingestion scheduler: RSS (4h), article fetch (10m), entity mentions (15m)."""
import asyncio
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

_scheduler: BackgroundScheduler | None = None


def _job_rss():
    """Scheduled job: RSS ingestion every N hours."""
    from app.services.monitoring_ingestion.rss_ingestion import run_rss_ingestion

    logger.info("scheduler_job_start", job="rss_ingestion")
    try:
        result = asyncio.run(run_rss_ingestion(max_feeds=10))
        logger.info("scheduler_job_complete", job="rss_ingestion", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="rss_ingestion", error=str(e))


def _job_article_fetcher():
    """Scheduled job: Article fetch every N minutes."""
    from app.services.monitoring_ingestion.article_fetcher import run_article_fetcher

    logger.info("scheduler_job_start", job="article_fetcher")
    try:
        result = asyncio.run(run_article_fetcher(max_items=20))
        logger.info("scheduler_job_complete", job="article_fetcher", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="article_fetcher", error=str(e))


def _job_entity_mentions():
    """Scheduled job: Entity mentions pipeline every N minutes."""
    from app.services.entity_mentions_worker import run_entity_mentions_pipeline

    logger.info("scheduler_job_start", job="entity_mentions")
    try:
        result = asyncio.run(run_entity_mentions_pipeline(batch_size=50))
        logger.info("scheduler_job_complete", job="entity_mentions", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="entity_mentions", error=str(e))


def _job_reddit():
    """Scheduled job: Reddit monitor every N minutes."""
    from app.services.reddit_worker import run_reddit_monitor

    logger.info("scheduler_job_start", job="reddit_monitor")
    try:
        result = asyncio.run(run_reddit_monitor())
        logger.info("scheduler_job_complete", job="reddit_monitor", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="reddit_monitor", error=str(e))


def _job_youtube():
    """Scheduled job: YouTube monitor every N minutes."""
    from app.services.youtube_worker import run_youtube_monitor

    logger.info("scheduler_job_start", job="youtube_monitor")
    try:
        result = asyncio.run(run_youtube_monitor())
        logger.info("scheduler_job_complete", job="youtube_monitor", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="youtube_monitor", error=str(e))


def _job_crawler_enqueue():
    """Scheduled job: Enqueue crawler jobs for due competitors."""
    from app.services.crawler.scheduler import enqueue_crawls

    logger.info("scheduler_job_start", job="crawler_enqueue")
    try:
        enqueue_crawls(max_per_run=10)
        logger.info("scheduler_job_complete", job="crawler_enqueue")
    except Exception as e:
        logger.exception("scheduler_job_failed", job="crawler_enqueue", error=str(e))


def start_scheduler():
    """Start the ingestion scheduler if enabled in config."""
    global _scheduler

    cfg = get_config()
    sched_cfg = cfg.get("scheduler") or {}
    if not sched_cfg.get("enabled", False):
        logger.info("ingestion_scheduler_disabled", reason="scheduler.enabled=false")
        return

    rss_hours = sched_cfg.get("rss_interval_hours", 4)
    article_min = sched_cfg.get("article_fetcher_interval_minutes", 10)
    entity_min = sched_cfg.get("entity_mentions_interval_minutes", 15)
    reddit_min = sched_cfg.get("reddit_interval_minutes", 120)
    youtube_min = sched_cfg.get("youtube_interval_minutes", 120)
    crawler_min = sched_cfg.get("crawler_enqueue_interval_minutes", 30)

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(_job_rss, "interval", hours=rss_hours, id="rss_ingestion")
    _scheduler.add_job(_job_article_fetcher, "interval", minutes=article_min, id="article_fetcher")
    _scheduler.add_job(_job_entity_mentions, "interval", minutes=entity_min, id="entity_mentions")
    _scheduler.add_job(_job_reddit, "interval", minutes=reddit_min, id="reddit_monitor")
    _scheduler.add_job(_job_youtube, "interval", minutes=youtube_min, id="youtube_monitor")
    _scheduler.add_job(_job_crawler_enqueue, "interval", minutes=crawler_min, id="crawler_enqueue")

    _scheduler.start()
    logger.info(
        "ingestion_scheduler_started",
        rss_interval_hours=rss_hours,
        article_fetcher_interval_minutes=article_min,
        entity_mentions_interval_minutes=entity_min,
        reddit_interval_minutes=reddit_min,
        youtube_interval_minutes=youtube_min,
        crawler_enqueue_interval_minutes=crawler_min,
    )


def stop_scheduler():
    """Stop the ingestion scheduler cleanly."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("ingestion_scheduler_stopped")
