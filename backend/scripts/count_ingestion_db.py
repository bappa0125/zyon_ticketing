"""Print document counts for ingestion collections (before/after running pipelines)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_config
from motor.motor_asyncio import AsyncIOMotorClient


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
        print("=== Ingestion DB counts ===")
        print(f"  rss_items:          {c.get('rss_items', 0)} (new: {c.get('rss_items_new', 0)}, processed: {c.get('rss_items_processed', 0)}, failed: {c.get('rss_items_failed', 0)})")
        print(f"  article_documents:   {c.get('article_documents', 0)}")
        print(f"  entity_mentions:     {c.get('entity_mentions', 0)}")
        print(f"  media_articles:      {c.get('media_articles', 0)}")

    asyncio.run(_run())
