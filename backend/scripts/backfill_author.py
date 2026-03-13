#!/usr/bin/env python3
"""
Backfill author on article_documents that lack it.
Re-fetches each article URL, extracts author (trafilatura + byline + newspaper3k), updates DB.
Also updates entity_mentions with the same URL.

Usage:
  python scripts/backfill_author.py [--limit 500] [--delay 1.5] [--batch 50]
  docker compose exec backend python scripts/backfill_author.py --limit 100
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client, get_db
from app.services.monitoring_ingestion.article_fetcher import _fetch_and_extract

logger = get_logger(__name__)

COLLECTION_ARTICLE_DOCUMENTS = "article_documents"
COLLECTION_ENTITY_MENTIONS = "entity_mentions"


async def run_backfill(
    limit: int | None = 500,
    delay_sec: float = 1.5,
    batch_size: int = 50,
) -> dict[str, int]:
    """Find article_documents without author, re-fetch, extract author, update article_documents and entity_mentions."""
    await get_mongo_client()
    db = get_db()
    article_coll = db[COLLECTION_ARTICLE_DOCUMENTS]
    mentions_coll = db[COLLECTION_ENTITY_MENTIONS]

    query = {
        "$or": [
            {"author": {"$exists": False}},
            {"author": None},
            {"author": ""},
        ]
    }
    cursor = (
        article_coll.find(query)
        .sort("fetched_at", -1)
        .limit(limit or 1_000_000)
    )
    docs = await cursor.to_list(length=limit or 100_000)
    total = len(docs)
    if total == 0:
        logger.info("backfill_author_no_docs", message="No article_documents without author")
        return {"updated": 0, "skipped": 0, "errors": 0, "total": 0}

    logger.info("backfill_author_start", total=total, limit=limit)

    updated = 0
    skipped = 0
    errors = 0

    for i, doc in enumerate(docs):
        url = (doc.get("url") or doc.get("url_resolved") or doc.get("url_original") or "").strip()
        if not url or not url.startswith("http"):
            skipped += 1
            continue

        try:
            _, _, _, _, author = _fetch_and_extract(url)
            if author and author.strip():
                doc_id = doc["_id"]
                await article_coll.update_one(
                    {"_id": doc_id},
                    {"$set": {"author": author.strip()[:300]}},
                )
                result = await mentions_coll.update_many(
                    {"url": url},
                    {"$set": {"author": author.strip()[:300]}},
                )
                updated += 1
                if (i + 1) % 10 == 0:
                    logger.info("backfill_author_progress", done=i + 1, total=total, updated=updated)
            else:
                skipped += 1
        except Exception as e:
            errors += 1
            logger.warning("backfill_author_failed", url=url[:80], error=str(e))

        if delay_sec > 0 and i < total - 1:
            await asyncio.sleep(delay_sec)

    logger.info(
        "backfill_author_complete",
        updated=updated,
        skipped=skipped,
        errors=errors,
        total=total,
    )
    return {"updated": updated, "skipped": skipped, "errors": errors, "total": total}


def main():
    p = argparse.ArgumentParser(description="Backfill author on article_documents by re-fetching and extracting")
    p.add_argument("--limit", type=int, default=500, help="Max articles to process (default 500)")
    p.add_argument("--delay", type=float, default=1.5, help="Seconds between fetches (default 1.5)")
    p.add_argument("--batch", type=int, default=50, help="Unused, for compatibility")
    args = p.parse_args()
    result = asyncio.run(
        run_backfill(
            limit=args.limit,
            delay_sec=max(0.0, args.delay),
        )
    )
    print(result)


if __name__ == "__main__":
    main()
