"""
Count how many articles/mentions we're missing or have unresolved URLs.
Run: docker compose exec backend python scripts/count_unresolved_urls.py

Metrics:
- rss_items with status=failed (never made it to article_documents → no entity_mentions from RSS)
- entity_mentions with empty url or url containing news.google.com (mention exists but link bad/unresolved)
- article_documents with url containing news.google.com (resolved may have failed)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_config
from motor.motor_asyncio import AsyncIOMotorClient


async def main() -> None:
    config = get_config()
    client = AsyncIOMotorClient(config["settings"].mongodb_url)
    db = client[config["mongodb"].get("database", "chat")]

    rss = db["rss_items"]
    ad = db["article_documents"]
    em = db["entity_mentions"]

    # 1. RSS items that failed fetch → never in article_documents (we're "missing" these entirely)
    rss_failed = await rss.count_documents({"status": "failed"})
    rss_total = await rss.count_documents({})
    rss_new = await rss.count_documents({"status": "new"})
    rss_processed = await rss.count_documents({"status": "processed"})

    # 2. Of failed, how many have Google News URL (redirect often the cause)
    rss_failed_google = await rss.count_documents({"status": "failed", "url": {"$regex": "news.google.com", "$options": "i"}})

    # 3. entity_mentions with empty or unresolved-looking URL (we have mention but link may not work)
    em_empty_url = await em.count_documents({"$or": [{"url": ""}, {"url": {"$exists": False}}, {"url": None}]})
    em_google_url = await em.count_documents({"url": {"$regex": "news.google.com", "$options": "i"}})
    em_total = await em.count_documents({})

    # 4. article_documents still with news.google.com (resolved failed or never run)
    ad_google_url = await ad.count_documents({"url": {"$regex": "news.google.com", "$options": "i"}})
    ad_total = await ad.count_documents({})

    print("=== Unresolved / missing URL metrics ===\n")
    print("RSS (rss_items):")
    print(f"  Total: {rss_total}  |  Processed: {rss_processed}  |  New: {rss_new}  |  Failed: {rss_failed}")
    print(f"  Failed (likely missing from article_documents): {rss_failed}")
    print(f"  Failed with news.google.com URL: {rss_failed_google}")
    print()
    print("Entity mentions (entity_mentions):")
    print(f"  Total: {em_total}")
    print(f"  Empty or missing url (mention exists, no link): {em_empty_url}")
    print(f"  URL contains news.google.com (unresolved redirect): {em_google_url}")
    print()
    print("Article documents (article_documents):")
    print(f"  Total: {ad_total}")
    print(f"  URL contains news.google.com: {ad_google_url}")
    print()
    print("Summary:")
    print(f"  Articles 'missing' (RSS failed, no article_document): {rss_failed}")
    print(f"  Mentions with bad/unresolved URL: {em_empty_url + em_google_url} (of {em_total})")


if __name__ == "__main__":
    asyncio.run(main())
