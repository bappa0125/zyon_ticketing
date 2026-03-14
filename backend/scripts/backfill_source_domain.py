"""Backfill source_domain from URL when missing or mismatched.

Fixes coverage-by-source zeros: populates source_domain from the article/mention URL
when it's empty, so media intelligence can attribute mentions to the right domains.

Usage:
  docker compose exec backend python scripts/backfill_source_domain.py
  docker compose exec backend python scripts/backfill_source_domain.py --limit 500 --dry-run
  docker compose exec backend python scripts/backfill_source_domain.py --force  # re-extract all from URL
"""

import argparse
import asyncio
from datetime import datetime, timezone

from app.config import get_config
from app.core.logging import get_logger
from app.services.monitoring_ingestion.article_fetcher import _source_domain_from_url

logger = get_logger(__name__)


async def _get_db():
    from motor.motor_asyncio import AsyncIOMotorClient

    config = get_config()
    url = config["settings"].mongodb_url
    db_name = config["mongodb"].get("database", "chat")
    client = AsyncIOMotorClient(url)
    return client[db_name]


async def backfill_article_documents(
    limit: int | None = None, dry_run: bool = False, force: bool = False
) -> dict:
    """Backfill source_domain on article_documents where missing, using URL."""
    db = await _get_db()
    coll = db["article_documents"]

    query = {
        "url": {"$exists": True, "$nin": [None, ""], "$regex": r"^https?://", "$options": "i"},
    }
    if not force:
        query["$or"] = [
            {"source_domain": {"$in": [None, ""]}},
            {"source_domain": {"$exists": False}},
        ]
    cursor = coll.find(query).sort("_id", 1)
    if limit:
        cursor = cursor.limit(limit)

    updated = 0
    skipped = 0
    async for doc in cursor:
        url = (doc.get("url") or doc.get("url_resolved") or "").strip()
        if not url or "news.google.com" in url.lower():
            skipped += 1
            continue
        sd = _source_domain_from_url(url)
        if not sd:
            skipped += 1
            continue
        if not dry_run:
            try:
                await coll.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"source_domain": sd[:200], "source_domain_backfilled_at": datetime.now(timezone.utc)}},
                )
                updated += 1
            except Exception as e:
                logger.warning("backfill_article_failed", _id=str(doc["_id"]), error=str(e))
        else:
            updated += 1

    return {"updated": updated, "skipped": skipped}


async def backfill_entity_mentions(
    limit: int | None = None, dry_run: bool = False, force: bool = False
) -> dict:
    """Backfill source_domain on entity_mentions where missing, using URL."""
    db = await _get_db()
    coll = db["entity_mentions"]

    query = {"url": {"$exists": True, "$ne": None, "$nin": ["", None]}}
    if not force:
        query["$or"] = [
            {"source_domain": {"$in": [None, ""]}},
            {"source_domain": {"$exists": False}},
        ]
    cursor = coll.find(query).sort("_id", 1)
    if limit:
        cursor = cursor.limit(limit)

    updated = 0
    skipped = 0
    async for doc in cursor:
        url = (doc.get("url") or "").strip()
        if not url or "news.google.com" in url.lower():
            skipped += 1
            continue
        sd = _source_domain_from_url(url)
        if not sd:
            skipped += 1
            continue
        if not dry_run:
            try:
                await coll.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"source_domain": sd[:200], "source_domain_backfilled_at": datetime.now(timezone.utc)}},
                )
                updated += 1
            except Exception as e:
                logger.warning("backfill_mention_failed", _id=str(doc["_id"]), error=str(e))
        else:
            updated += 1

    return {"updated": updated, "skipped": skipped}


async def main():
    parser = argparse.ArgumentParser(description="Backfill source_domain from URL")
    parser.add_argument("--limit", type=int, default=None, help="Max documents per collection")
    parser.add_argument("--dry-run", action="store_true", help="Count only, no writes")
    parser.add_argument("--force", action="store_true", help="Re-extract from URL even when source_domain exists")
    args = parser.parse_args()

    print("Backfilling source_domain from URL" + (" (missing only)" if not args.force else " (force re-extract)") + "...")
    if args.dry_run:
        print("(dry run - no writes)")

    art = await backfill_article_documents(limit=args.limit, dry_run=args.dry_run, force=args.force)
    print(f"article_documents: {art}")

    ment = await backfill_entity_mentions(limit=args.limit, dry_run=args.dry_run, force=args.force)
    print(f"entity_mentions: {ment}")

    total = art["updated"] + ment["updated"]
    if total > 0 and not args.dry_run:
        print(f"\nBackfilled {total} documents. Refresh Media Intelligence to see coverage by source.")
    elif args.dry_run and (art["updated"] > 0 or ment["updated"] > 0):
        print(f"\nWould backfill {total} documents. Run without --dry-run to apply.")


if __name__ == "__main__":
    asyncio.run(main())
