"""In-process ingestion scheduler: RSS (4h), article fetch (10m), entity mentions (15m)."""
import asyncio
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from redis import Redis

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

_scheduler: BackgroundScheduler | None = None

BACKFILL_LOCK_KEY = "ingestion:backfill_running"


def _skip_if_backfill(job_id: str) -> bool:
    """Return True if master backfill is running (scheduler should skip this job)."""
    try:
        cfg = get_config()
        url = cfg["settings"].redis_url
        r = Redis.from_url(url, decode_responses=True)
        if r.get(BACKFILL_LOCK_KEY):
            logger.info("scheduler_job_skipped", job=job_id, reason="master_backfill_running")
            return True
    except Exception as e:
        logger.debug("backfill_lock_check_failed", job=job_id, error=str(e))
    return False


def _job_rss():
    """Scheduled job: RSS ingestion every N hours."""
    if _skip_if_backfill("rss_ingestion"):
        return
    from app.services.monitoring_ingestion.rss_ingestion import run_rss_ingestion

    sched = (get_config().get("scheduler") or {})
    max_feeds = sched.get("rss_max_feeds_per_run", 20)
    logger.info("scheduler_job_start", job="rss_ingestion")
    try:
        result = asyncio.run(run_rss_ingestion(max_feeds=max_feeds))
        logger.info("scheduler_job_complete", job="rss_ingestion", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="rss_ingestion", error=str(e))


def _job_article_fetcher():
    """Scheduled job: Article fetch every N minutes."""
    if _skip_if_backfill("article_fetcher"):
        return
    from app.services.monitoring_ingestion.article_fetcher import run_article_fetcher

    sched = (get_config().get("scheduler") or {})
    max_items = sched.get("article_fetcher_max_items_per_run", 40)
    logger.info("scheduler_job_start", job="article_fetcher")
    try:
        result = asyncio.run(run_article_fetcher(max_items=max_items))
        logger.info("scheduler_job_complete", job="article_fetcher", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="article_fetcher", error=str(e))


def _job_entity_mentions():
    """Scheduled job: Entity mentions pipeline (unprocessed-first, batch 150)."""
    if _skip_if_backfill("entity_mentions"):
        return
    from app.services.entity_mentions_worker import run_entity_mentions_pipeline

    logger.info("scheduler_job_start", job="entity_mentions")
    try:
        batch = (get_config().get("scheduler") or {}).get("entity_mentions_batch_size", 150)
        result = asyncio.run(run_entity_mentions_pipeline(batch_size=batch))
        logger.info("scheduler_job_complete", job="entity_mentions", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="entity_mentions", error=str(e))


def _job_reddit():
    """Scheduled job: Reddit monitor every N minutes."""
    if _skip_if_backfill("reddit_monitor"):
        return
    from app.services.reddit_worker import run_reddit_monitor

    logger.info("scheduler_job_start", job="reddit_monitor")
    try:
        result = asyncio.run(run_reddit_monitor())
        logger.info("scheduler_job_complete", job="reddit_monitor", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="reddit_monitor", error=str(e))


def _job_youtube():
    """Scheduled job: YouTube monitor every N minutes."""
    if _skip_if_backfill("youtube_monitor"):
        return
    from app.services.youtube_worker import run_youtube_monitor

    logger.info("scheduler_job_start", job="youtube_monitor")
    try:
        result = asyncio.run(run_youtube_monitor())
        logger.info("scheduler_job_complete", job="youtube_monitor", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="youtube_monitor", error=str(e))


def _job_crawler_enqueue():
    """Scheduled job: Enqueue crawler jobs for due competitors."""
    if _skip_if_backfill("crawler_enqueue"):
        return
    from app.services.crawler.scheduler import enqueue_crawls

    logger.info("scheduler_job_start", job="crawler_enqueue")
    try:
        enqueue_crawls(max_per_run=10)
        logger.info("scheduler_job_complete", job="crawler_enqueue")
    except Exception as e:
        logger.exception("scheduler_job_failed", job="crawler_enqueue", error=str(e))


def _job_forum_ingestion():
    """Scheduled job: Forum ingestion (HTML sources) into article_documents."""
    if _skip_if_backfill("forum_ingestion"):
        return
    from app.services.forum_ingestion_worker import run_forum_ingestion

    logger.info("scheduler_job_start", job="forum_ingestion")
    try:
        result = asyncio.run(run_forum_ingestion())
        logger.info("scheduler_job_complete", job="forum_ingestion", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="forum_ingestion", error=str(e))


def _job_entity_mentions_sentiment():
    """Scheduled job: Run VADER sentiment on entity_mentions where sentiment is missing."""
    if _skip_if_backfill("entity_mentions_sentiment"):
        return
    from app.services.entity_mentions_sentiment_worker import run_entity_mentions_sentiment

    logger.info("scheduler_job_start", job="entity_mentions_sentiment")
    try:
        result = asyncio.run(run_entity_mentions_sentiment(batch_size=50))
        logger.info("scheduler_job_complete", job="entity_mentions_sentiment", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="entity_mentions_sentiment", error=str(e))


def _job_ai_summary():
    """Scheduled job: AI summaries for new entity_mentions and article_documents. Once/day to stay under free tier."""
    if _skip_if_backfill("ai_summary"):
        return
    from app.services.ai_summary_worker import run_ai_summary_worker

    logger.info("scheduler_job_start", job="ai_summary")
    try:
        result = asyncio.run(run_ai_summary_worker())
        logger.info("scheduler_job_complete", job="ai_summary", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="ai_summary", error=str(e))


def _job_article_topics():
    """Scheduled job: Extract topics (KeyBERT) on article_documents where topics is missing."""
    if _skip_if_backfill("article_topics"):
        return
    from app.services.article_topics_worker import run_article_topics_pipeline

    logger.info("scheduler_job_start", job="article_topics")
    try:
        batch = (get_config().get("scheduler") or {}).get("article_topics_batch_size", 30)
        result = asyncio.run(run_article_topics_pipeline(batch_size=batch))
        logger.info("scheduler_job_complete", job="article_topics", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="article_topics", error=str(e))


def _job_pr_opportunities():
    """Scheduled job: PR opportunities (quote alerts, outreach drafts, competitor responses). Once/day."""
    if _skip_if_backfill("pr_opportunities"):
        return
    from app.services.pr_opportunities_service import run_pr_opportunities_all_clients

    logger.info("scheduler_job_start", job="pr_opportunities")
    try:
        result = asyncio.run(run_pr_opportunities_all_clients())
        logger.info("scheduler_job_complete", job="pr_opportunities", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="pr_opportunities", error=str(e))


def _job_pr_report_daily():
    """Scheduled job: PR daily snapshots (outreach, benchmarks, sentiment). Once per day."""
    if _skip_if_backfill("pr_report_daily"):
        return
    from app.services.pr_report_service import run_daily_snapshot_all_clients

    logger.info("scheduler_job_start", job="pr_report_daily")
    try:
        result = asyncio.run(run_daily_snapshot_all_clients())
        logger.info("scheduler_job_complete", job="pr_report_daily", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="pr_report_daily", error=str(e))


def _job_sahi_strategic_brief():
    """Scheduled job: Generate Sahi strategic brief, store in DB. Once per day."""
    if _skip_if_backfill("sahi_strategic_brief"):
        return
    from app.services.sahi_strategic_brief_service import run_sahi_strategic_brief_daily

    logger.info("scheduler_job_start", job="sahi_strategic_brief")
    try:
        result = asyncio.run(run_sahi_strategic_brief_daily())
        logger.info("scheduler_job_complete", job="sahi_strategic_brief", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="sahi_strategic_brief", error=str(e))


def _job_ai_brief_daily():
    """Scheduled job: Generate AI brief for each client (7d), store in DB. Once per day."""
    if _skip_if_backfill("ai_brief_daily"):
        return
    from app.api.reports_api import run_ai_brief_daily

    logger.info("scheduler_job_start", job="ai_brief_daily")
    try:
        result = asyncio.run(run_ai_brief_daily())
        logger.info("scheduler_job_complete", job="ai_brief_daily", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="ai_brief_daily", error=str(e))


def _job_reddit_trending():
    """Scheduled job: Reddit trending pipeline (fetch subreddits → Mongo + Redis → LLM themes + Sahi)."""
    if _skip_if_backfill("reddit_trending"):
        return
    from app.services.reddit_trending_service import run_reddit_trending_pipeline

    if not get_config().get("reddit_trending", {}).get("enabled", False):
        return
    logger.info("scheduler_job_start", job="reddit_trending")
    try:
        result = asyncio.run(run_reddit_trending_pipeline())
        logger.info("scheduler_job_complete", job="reddit_trending", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="reddit_trending", error=str(e))


def _job_narrative_positioning():
    """Scheduled job: PR-focused narrative positioning per client (1 LLM call per client)."""
    if _skip_if_backfill("narrative_positioning"):
        return
    np_cfg = get_config().get("narrative_positioning")
    if not isinstance(np_cfg, dict) or not np_cfg.get("enabled", True):
        return
    from app.services.narrative_positioning_service import run_positioning_for_all_clients
    logger.info("scheduler_job_start", job="narrative_positioning")
    try:
        result = asyncio.run(run_positioning_for_all_clients())
        logger.info("scheduler_job_complete", job="narrative_positioning", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="narrative_positioning", error=str(e))


def _job_narrative_intelligence_daily():
    """Scheduled job: 1 LLM synthesis over narrative shift + Reddit + YouTube → store daily."""
    if _skip_if_backfill("narrative_intelligence_daily"):
        return
    nid_cfg = get_config().get("narrative_intelligence_daily")
    if not isinstance(nid_cfg, dict) or not nid_cfg.get("enabled", False):
        return
    from app.services.narrative_intelligence_daily_service import run_daily_synthesis
    logger.info("scheduler_job_start", job="narrative_intelligence_daily")
    try:
        result = asyncio.run(run_daily_synthesis())
        logger.info("scheduler_job_complete", job="narrative_intelligence_daily", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="narrative_intelligence_daily", error=str(e))


def _job_youtube_narrative():
    """Scheduled job: YouTube narrative pipeline (YouTube API + 1 LLM call → daily summary)."""
    if _skip_if_backfill("youtube_narrative_daily"):
        return
    yt_cfg = get_config().get("youtube_trending")
    if not isinstance(yt_cfg, dict) or not yt_cfg.get("enabled", False):
        return
    from app.services.youtube_trending_service import run_youtube_narrative_pipeline
    logger.info("scheduler_job_start", job="youtube_narrative")
    try:
        result = asyncio.run(run_youtube_narrative_pipeline())
        logger.info("scheduler_job_complete", job="youtube_narrative", result=result)
    except Exception as e:
        logger.exception("scheduler_job_failed", job="youtube_narrative", error=str(e))


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
    forum_min = sched_cfg.get("forum_ingestion_interval_minutes", 360)
    sentiment_min = sched_cfg.get("entity_mentions_sentiment_interval_minutes", 20)
    ai_summary_hours = sched_cfg.get("ai_summary_interval_hours", 24)
    article_topics_min = sched_cfg.get("article_topics_interval_minutes", 60)
    reddit_trending_cfg = cfg.get("reddit_trending") or {}
    reddit_trending_min = reddit_trending_cfg.get("fetch_interval_minutes", 45)

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(_job_rss, "interval", hours=rss_hours, id="rss_ingestion")
    _scheduler.add_job(_job_article_fetcher, "interval", minutes=article_min, id="article_fetcher")
    _scheduler.add_job(_job_entity_mentions, "interval", minutes=entity_min, id="entity_mentions")
    _scheduler.add_job(_job_entity_mentions_sentiment, "interval", minutes=sentiment_min, id="entity_mentions_sentiment")
    _scheduler.add_job(_job_ai_summary, "interval", hours=ai_summary_hours, id="ai_summary")
    _scheduler.add_job(_job_article_topics, "interval", minutes=article_topics_min, id="article_topics")
    _scheduler.add_job(_job_reddit, "interval", minutes=reddit_min, id="reddit_monitor")
    _scheduler.add_job(_job_youtube, "interval", minutes=youtube_min, id="youtube_monitor")
    _scheduler.add_job(_job_crawler_enqueue, "interval", minutes=crawler_min, id="crawler_enqueue")
    _scheduler.add_job(_job_forum_ingestion, "interval", minutes=forum_min, id="forum_ingestion")
    if reddit_trending_cfg.get("enabled", False):
        _scheduler.add_job(_job_reddit_trending, "interval", minutes=reddit_trending_min, id="reddit_trending")

    _scheduler.add_job(_job_ai_brief_daily, "cron", hour=6, minute=0, id="ai_brief_daily")
    _scheduler.add_job(_job_pr_report_daily, "cron", hour=5, minute=30, id="pr_report_daily")
    _scheduler.add_job(_job_pr_opportunities, "cron", hour=6, minute=30, id="pr_opportunities_daily")
    _scheduler.add_job(_job_sahi_strategic_brief, "cron", hour=7, minute=0, id="sahi_strategic_brief_daily")
    yt_cfg = cfg.get("youtube_trending")
    if isinstance(yt_cfg, dict) and yt_cfg.get("enabled", False):
        try:
            _scheduler.add_job(_job_youtube_narrative, "cron", hour=8, minute=0, id="youtube_narrative_daily")
        except Exception as e:
            logger.warning("youtube_narrative_daily job not scheduled", error=str(e))
    if isinstance(nid_cfg := cfg.get("narrative_intelligence_daily"), dict) and nid_cfg.get("enabled", False):
        try:
            _scheduler.add_job(_job_narrative_intelligence_daily, "cron", hour=9, minute=0, id="narrative_intelligence_daily")
        except Exception as e:
            logger.warning("narrative_intelligence_daily job not scheduled", error=str(e))
    np_cfg = cfg.get("narrative_positioning")
    if isinstance(np_cfg, dict) and np_cfg.get("enabled", True):
        try:
            _scheduler.add_job(_job_narrative_positioning, "cron", hour=9, minute=30, id="narrative_positioning")
        except Exception as e:
            logger.warning("narrative_positioning job not scheduled", error=str(e))

    # Run RSS once shortly after start so the queue gets new items without waiting 4h
    _scheduler.add_job(
        _job_rss,
        "date",
        run_date=datetime.now(timezone.utc) + timedelta(seconds=30),
        id="rss_ingestion_startup",
    )

    _scheduler.start()
    logger.info(
        "ingestion_scheduler_started",
        rss_interval_hours=rss_hours,
        article_fetcher_interval_minutes=article_min,
        entity_mentions_interval_minutes=entity_min,
        reddit_interval_minutes=reddit_min,
        youtube_interval_minutes=youtube_min,
        crawler_enqueue_interval_minutes=crawler_min,
        forum_ingestion_interval_minutes=forum_min,
        entity_mentions_sentiment_interval_minutes=sentiment_min,
        ai_summary_interval_hours=ai_summary_hours,
        article_topics_interval_minutes=article_topics_min,
    )


def stop_scheduler():
    """Stop the ingestion scheduler cleanly."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("ingestion_scheduler_stopped")
