"""System metrics - CPU, RAM, queue size, pages crawled."""
import sys

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
