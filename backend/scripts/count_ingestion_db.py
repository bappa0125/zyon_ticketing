"""Print document counts for ingestion collections (before/after running pipelines)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_config
from motor.motor_asyncio import AsyncIOMotorClient


def _get_rss_diagnosis():
    """Check why rss_items might have 0 'new' items."""
    try:
        from app.services.monitoring_ingestion.media_source_registry import get_rss_sources
        from app.services.monitoring_ingestion import get_ready_sources, get_ordered_ready_sources
        sources = get_rss_sources()
        ready = get_ready_sources(sources)
        ordered = get_ordered_ready_sources(ready)
        return {
            "rss_sources_configured": len(sources),
            "rss_sources_ready_now": len(ready),
            "config_ok": len(sources) > 0,
        }
    except Exception as e:
        return {"rss_sources_configured": 0, "rss_sources_ready_now": 0, "config_ok": False, "error": str(e)}


async def main() -> dict:
    config = get_config()
    client = AsyncIOMotorClient(config["settings"].mongodb_url)
    db = client[config["mongodb"].get("database", "chat")]

    counts = {}
    for coll_name in ("rss_items", "article_documents", "entity_mentions", "media_articles"):
        try:
            counts[coll_name] = await db[coll_name].count_documents({})
        except Exception:
            counts[coll_name] = 0

    rss = db["rss_items"]
    counts["rss_items_new"] = await rss.count_documents({"status": "new"})
    counts["rss_items_processed"] = await rss.count_documents({"status": "processed"})
    counts["rss_items_failed"] = await rss.count_documents({"status": "failed"})

    return counts


if __name__ == "__main__":
    async def _run():
        c = await main()
        diag = _get_rss_diagnosis()

        print("=== Ingestion DB counts ===")
        print(f"  rss_items:          {c.get('rss_items', 0)} (new: {c.get('rss_items_new', 0)}, processed: {c.get('rss_items_processed', 0)}, failed: {c.get('rss_items_failed', 0)})")
        print(f"  article_documents:   {c.get('article_documents', 0)}")
        print(f"  entity_mentions:     {c.get('entity_mentions', 0)}")
        print(f"  media_articles:      {c.get('media_articles', 0)}")
        print()
        print("=== RSS pipeline check ===")
        print(f"  RSS sources in config: {diag.get('rss_sources_configured', 0)}")
        print(f"  Sources 'ready' to crawl now: {diag.get('rss_sources_ready_now', 0)}")
        if diag.get("error"):
            print(f"  Config/import error: {diag['error']}")
        print()
        new = c.get("rss_items_new", 0)
        total_rss = c.get("rss_items", 0)
        if new == 0:
            print("--- Why is 'new' 0? ---")
            if total_rss == 0 and diag.get("rss_sources_configured", 0) == 0:
                print("  * No RSS sources loaded (check config/media_sources.yaml and that config is mounted at /app/config in Docker).")
            elif total_rss == 0:
                print("  * No rss_items in DB yet. Scheduler may not have run, or feeds returned no fresh/non-duplicate items (72h freshness, url dedup).")
            else:
                print("  * Article fetcher is consuming all 'new' items (normal if pipeline is healthy). Check article_documents and entity_mentions above.")
            print()

    asyncio.run(_run())
