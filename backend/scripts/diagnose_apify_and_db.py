"""
Diagnostic: Apify API key validation + what is stored in DB (social_posts, entity_mentions).
Run: docker compose run --rm backend python scripts/diagnose_apify_and_db.py
"""
import asyncio
import os
import sys

# Ensure app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def check_apify_key():
    """Validate APIFY_API_KEY is set and optionally that it works."""
    from app.config import get_config

    config = get_config()
    settings = config.get("settings")
    key = getattr(settings, "apify_api_key", None) or ""
    env_key = os.environ.get("APIFY_API_KEY", "")

    print("=== APIFY API KEY ===")
    print(f"  From config (settings.apify_api_key): {'SET' if key else 'NOT SET'} (len={len(key) if key else 0})")
    print(f"  From env APIFY_API_KEY:              {'SET' if env_key else 'NOT SET'} (len={len(env_key) if env_key else 0})")
    used = key or env_key
    if not used:
        print("  Result: APIFY_API_KEY is NOT SET - Reddit/YouTube workers will not store any data.")
        return False

    try:
        from apify_client import ApifyClient
        client = ApifyClient(used.strip())
        client.user().get()
        print("  Apify client init + user().get(): OK (key valid)")
        return True
    except Exception as e:
        print(f"  Apify client validation: FAILED - {e}")
        return False


async def check_db_counts():
    """Report entity_mentions and social_posts counts by entity."""
    from app.config import get_config
    from motor.motor_asyncio import AsyncIOMotorClient

    config = get_config()
    url = getattr(config["settings"], "mongodb_url", None) or ""
    db_name = (config.get("mongodb") or {}).get("database", "chat")
    if not url:
        print("=== DB ===\n  MongoDB URL not set. Skip DB checks.")
        return

    client = AsyncIOMotorClient(url)
    db = client[db_name]

    print("\n=== ENTITY_MENTIONS (by entity) ===")
    pipeline = [{"$group": {"_id": "$entity", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}, {"$limit": 20}]
    try:
        cursor = db["entity_mentions"].aggregate(pipeline)
        rows = await cursor.to_list(length=20)
        if not rows:
            print("  (empty collection)")
        for r in rows:
            print(f"  {r['_id']}: {r['count']}")
    except Exception as e:
        print(f"  Error: {e}")

    print("\n=== SOCIAL_POSTS (by entity) ===")
    try:
        cursor = db["social_posts"].aggregate(pipeline)
        rows = await cursor.to_list(length=20)
        if not rows:
            print("  (empty collection - no Apify/Reddit/YouTube data stored)")
        else:
            for r in rows:
                print(f"  {r['_id']}: {r['count']}")
    except Exception as e:
        print(f"  Error: {e}")

    entities = ["Sahi", "Zerodha", "Groww", "Upstox"]
    print("\n=== COUNTS FOR SAHI, ZERODHA, GROWW, UPSTOX ===")
    for entity in entities:
        em = await db["entity_mentions"].count_documents({"entity": entity})
        sp = await db["social_posts"].count_documents({"entity": entity})
        print(f"  {entity}: entity_mentions={em}, social_posts={sp}")

    sched = (config.get("scheduler") or {})
    enabled = sched.get("enabled", False)
    reddit_min = sched.get("reddit_interval_minutes", 120)
    print("\n=== SCHEDULER ===")
    print(f"  enabled: {enabled}")
    print(f"  reddit_interval_minutes: {reddit_min}")
    if not enabled:
        print("  Scheduler is DISABLED - Reddit/YouTube jobs never run.")


def main():
    apify_ok = check_apify_key()
    asyncio.run(check_db_counts())
    print("\n=== SUMMARY ===")
    if not apify_ok:
        print("  Fix: Set APIFY_API_KEY in .env and ensure it is valid at apify.com.")
    print("  If social_posts is empty: ensure scheduler enabled and Reddit job has run.")


if __name__ == "__main__":
    main()
