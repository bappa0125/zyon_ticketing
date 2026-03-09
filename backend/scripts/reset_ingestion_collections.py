#!/usr/bin/env python3
"""One-time MongoDB reset for broken ingestion collections. Use only for development.
Drops: media_articles, entity_mentions, rss_items.
Does NOT drop: article_documents, social_posts, conversations, messages."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from app.config import get_config
    from motor.motor_asyncio import AsyncIOMotorClient

    cfg = get_config()
    url = cfg["settings"].mongodb_url
    db_name = cfg["mongodb"].get("database", "chat")
    client = AsyncIOMotorClient(url)
    db = client[db_name]

    to_drop = ["media_articles", "entity_mentions", "rss_items"]
    for coll_name in to_drop:
        try:
            await db[coll_name].drop()
            print(f"Dropped {coll_name}")
        except Exception as e:
            print(f"Drop {coll_name}: {e}")
    print("Done. Run ingestion pipelines to repopulate.")


if __name__ == "__main__":
    asyncio.run(main())
