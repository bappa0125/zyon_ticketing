"""System metrics - CPU, RAM, queue size, pages crawled, ingestion pipeline status."""
import sys
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter

router = APIRouter(prefix="/system", tags=["system"])


def _get_ram_mb() -> float:
    """Cross-platform RSS in MB (Linux /proc, macOS resource, fallback psutil)."""
    try:
        import resource
        # macOS: ru_maxrss in bytes; Linux: typically KB
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return rss / (1024 * 1024)
        return rss / 1024
    except Exception:
        pass
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except Exception:
        pass
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


@router.get("/metrics")
async def system_metrics():
    """Return CPU, RAM, crawler queue size, active jobs, pages crawled today."""
    out = {}

    # CPU
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        out["cpu_user_seconds"] = usage.ru_utime
        out["cpu_system_seconds"] = usage.ru_stime
    except Exception:
        out["cpu_user_seconds"] = 0
        out["cpu_system_seconds"] = 0

    out["ram_mb"] = round(_get_ram_mb(), 2)

    # Redis queue sizes and active jobs
    try:
        from redis import Redis
        from app.config import get_config
        from rq import Queue

        r = Redis.from_url(get_config()["settings"].redis_url)
        for qname in ["high_priority", "normal_priority", "low_priority"]:
            q = Queue(qname, connection=r)
            out[f"queue_{qname}_size"] = len(q)
        out["crawler_queue_size"] = out.get("queue_low_priority_size", 0)

        # Active jobs (RQ workers)
        from rq.registry import StartedJobRegistry
        total_active = 0
        for qname in ["high_priority", "normal_priority", "low_priority"]:
            q = Queue(qname, connection=r)
            reg = StartedJobRegistry(queue=q)
            total_active += len(reg)
        out["active_crawler_jobs"] = total_active
    except Exception:
        out["crawler_queue_size"] = 0
        out["active_crawler_jobs"] = 0

    # Pages crawled today
    try:
        from redis import Redis
        from app.config import get_config
        r = Redis.from_url(get_config()["settings"].redis_url)
        out["pages_crawled_today"] = int(r.get("crawler:pages_crawled_today") or 0)
    except Exception:
        out["pages_crawled_today"] = 0

    return out


@router.get("/ingestion-status")
async def ingestion_status():
    """
    Pipeline health: counts for rss_items, article_documents, entity_mentions,
    and how many were added in the last 24h. Use this to verify data is flowing.
    """
    from app.services.mongodb import get_mongo_client, get_db
    from app.config import get_config
    from app.services.monitoring_ingestion.media_source_registry import get_rss_sources

    await get_mongo_client()
    config = get_config()
    db_name = config["mongodb"].get("database", "chat")
    db = get_db()

    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    def _count(coll, query=None):
        try:
            return db[coll].count_documents(query or {})
        except Exception:
            return 0

    def _count_recent(coll, date_field, since):
        try:
            return db[coll].count_documents({date_field: {"$gte": since}})
        except Exception:
            return 0

    rss = db["rss_items"]
    art = db["article_documents"]
    em = db["entity_mentions"]

    rss_new = await rss.count_documents({"status": "new"})
    rss_processed = await rss.count_documents({"status": "processed"})
    rss_failed = await rss.count_documents({"status": "failed"})
    rss_total = await rss.count_documents({})

    art_total = await art.count_documents({})
    art_unprocessed = await art.count_documents({
        "$or": [
            {"entity_mentions_processed_at": {"$exists": False}},
            {"entity_mentions_processed_at": None},
        ]
    })
    art_last_24h = await art.count_documents({"fetched_at": {"$gte": last_24h}})

    em_total = await em.count_documents({})
    em_last_24h = await em.count_documents({"timestamp": {"$gte": last_24h}})
    try:
        em_published_24h = await em.count_documents({"published_at": {"$gte": last_24h}})
    except Exception:
        em_published_24h = em_last_24h

    rss_sources = get_rss_sources()
    sched = config.get("scheduler") or {}
    scheduler_enabled = sched.get("enabled", False)

    # Live search: only metadata-only stores set source="live_search"; full-path stores don't
    live_search_meta_24h = 0
    try:
        live_search_meta_24h = await art.count_documents({
            "source": "live_search",
            "fetched_at": {"$gte": last_24h},
        })
    except Exception:
        pass

    return {
        "scheduler_enabled": scheduler_enabled,
        "rss_sources_configured": len(rss_sources),
        "live_search_ingested_last_24h": live_search_meta_24h,
        "live_search_note": "Only metadata-only live search docs are tagged (source=live_search). Full-fetch live search inserts are not tagged, so this is a lower bound.",
        "rss_items": {
            "total": rss_total,
            "new": rss_new,
            "processed": rss_processed,
            "failed": rss_failed,
        },
        "article_documents": {
            "total": art_total,
            "unprocessed_pending_entity_mentions": art_unprocessed,
            "fetched_last_24h": art_last_24h,
        },
        "entity_mentions": {
            "total": em_total,
            "last_24h": em_last_24h,
            "published_last_24h": em_published_24h,
        },
        "interpretation": {
            "ok": "Pipeline is healthy if rss_items.new drains (article_fetcher runs), article_documents get processed (entity_mentions run), and entity_mentions grow.",
            "stuck_rss": "If rss_items.new keeps growing and article_documents barely increase, article_fetcher may be failing or too slow (increase article_fetcher_interval_minutes or max_items).",
            "stuck_articles": "If article_documents.unprocessed_pending_entity_mentions is high and entity_mentions barely grow, entity_mentions job may be failing or entities not matching.",
            "no_rss_sources": "If rss_sources_configured is 0, check config/media_sources.yaml has sources with rss_feed set and config is mounted in Docker.",
        },
    }


@router.post("/trigger-rss")
async def trigger_rss(force: bool = False):
    """
    Run one RSS ingestion cycle now. Returns feeds_processed, fresh_items_inserted, etc.
    By default respects crawl_frequency (only runs feeds that are 'ready').
    Use ?force=true to run up to max_feeds regardless of readiness (for testing / on-demand).
    """
    from app.services.monitoring_ingestion.rss_ingestion import run_rss_ingestion
    from app.config import get_config

    sched = (get_config().get("scheduler") or {})
    max_feeds = sched.get("rss_max_feeds_per_run", 35)
    result = await run_rss_ingestion(max_feeds=max_feeds, force=force)
    return {"ok": True, "force": force, "result": result}


@router.post("/trigger-pipeline")
async def trigger_pipeline(force_rss: bool = True):
    """
    Run the full ingestion pipeline once so the UI can show new data:
    1) RSS (force=true so feeds run regardless of crawl_frequency)
    2) Article fetcher (rss_items new → article_documents)
    3) Entity mentions (article_documents unprocessed → entity_mentions)
    Call this then refresh the dashboard; counts will update if new articles mention your client.
    """
    from app.services.monitoring_ingestion.rss_ingestion import run_rss_ingestion
    from app.services.monitoring_ingestion.article_fetcher import run_article_fetcher
    from app.services.entity_mentions_worker import run_entity_mentions_pipeline
    from app.config import get_config

    sched = (get_config().get("scheduler") or {})
    max_feeds = sched.get("rss_max_feeds_per_run", 35)
    max_articles = sched.get("article_fetcher_max_items_per_run", 40)
    batch_mentions = sched.get("entity_mentions_batch_size", 150)

    rss_result = await run_rss_ingestion(max_feeds=max_feeds, force=force_rss)
    article_result = await run_article_fetcher(max_items=max_articles)
    # Newest first so the just-fetched articles get entity detection and the UI can show them
    mentions_result = await run_entity_mentions_pipeline(batch_size=batch_mentions, newest_first=True)

    return {
        "ok": True,
        "rss": rss_result,
        "article_fetcher": article_result,
        "entity_mentions": mentions_result,
    }
