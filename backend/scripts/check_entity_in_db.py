"""Check if an entity (e.g. Sahi) has any data in entity_mentions and article_documents."""
import asyncio
import sys

from app.config import get_config
from motor.motor_asyncio import AsyncIOMotorClient


async def check_entity(name: str) -> None:
    config = get_config()
    client = AsyncIOMotorClient(config["settings"].mongodb_url)
    db = client[config["mongodb"].get("database", "chat")]

    name_clean = (name or "").strip()
    if not name_clean:
        print("Usage: python scripts/check_entity_in_db.py <entity_name>")
        return

    # entity_mentions: exact entity match (case-insensitive)
    em_count = await db["entity_mentions"].count_documents({"entity": {"$regex": f"^{name_clean}$", "$options": "i"}})
    em_sample = await db["entity_mentions"].find({"entity": {"$regex": f"^{name_clean}$", "$options": "i"}}).limit(3).to_list(length=3)

    # article_documents: entities array or title/url contains name
    ad_entities = await db["article_documents"].count_documents({"entities": name_clean})
    ad_title = await db["article_documents"].count_documents({"title": {"$regex": name_clean, "$options": "i"}})
    ad_url = await db["article_documents"].count_documents({"url": {"$regex": name_clean, "$options": "i"}})

    print(f"Entity: {name_clean}")
    print(f"  entity_mentions:  {em_count} (entity field)")
    if em_sample:
        for d in em_sample:
            url = (d.get("url") or "")[:80]
            print(f"    sample url: {url}  news.google.com={('news.google.com' in url)}")
    print(f"  article_documents: entities array={ad_entities}, title contains={ad_title}, url contains={ad_url}")
    regex_gn = {"$regex": "news.google.com"}
    em_gn = await db["entity_mentions"].count_documents({"url": regex_gn})
    ad_gn = await db["article_documents"].count_documents({"url": regex_gn})
    print(f"  Any stored url with news.google.com: entity_mentions={em_gn}, article_documents={ad_gn}")


if __name__ == "__main__":
    entity = sys.argv[1] if len(sys.argv) > 1 else "Sahi"
    asyncio.run(check_entity(entity))
