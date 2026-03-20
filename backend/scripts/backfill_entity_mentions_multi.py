"""
Backfill entity_mentions so every (url, entity) from article_documents is present.
Processes in batches with optional delay to avoid DB/CPU spikes. Marks each doc as processed
(entity_mentions_processed_at) so the worker does not re-process.

Enterprise-grade: batched, rate-limited, idempotent.
Usage:
  python scripts/backfill_entity_mentions_multi.py [--batch 100] [--limit 500]
  python scripts/backfill_entity_mentions_multi.py --batch 50 --delay 1.0 --limit 2000
  python scripts/backfill_entity_mentions_multi.py --reprocess-days 30 --limit 3000   # re-run last N days
"""
import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client, get_db

logger = get_logger(__name__)

COLLECTION_ARTICLE_DOCUMENTS = "article_documents"
COLLECTION_ENTITY_MENTIONS = "entity_mentions"
DETECTION_WINDOW = 15000
CONTENT_QUALITY_FULL_TEXT = "full_text"
CONTENT_QUALITY_SNIPPET = "snippet"
_FORUM_DOMAINS = {"tradingqna.com", "traderji.com", "valuepickr.com"}


async def _mark_processed(article_coll, doc_id) -> None:
    """Set entity_mentions_processed_at so worker skips this doc."""
    try:
        await article_coll.update_one(
            {"_id": doc_id},
            {"$set": {"entity_mentions_processed_at": datetime.now(timezone.utc)}},
        )
    except Exception as e:
        logger.warning("backfill_mark_processed_failed", _id=str(doc_id), error=str(e))


async def run_backfill(
    batch_size: int = 100,
    limit: int | None = 500,
    delay_between_batches_sec: float = 0.5,
    skip_already_processed: bool = True,
    reprocess_days: int | None = None,
) -> dict[str, int]:
    from app.services.entity_detection_service import detect_entities
    from app.services.mention_context_validation import validate_mention_context

    await get_mongo_client()
    db = get_db()
    article_coll = db[COLLECTION_ARTICLE_DOCUMENTS]
    mentions_coll = db[COLLECTION_ENTITY_MENTIONS]

    query: dict = {}
    cursor_sort = [("fetched_at", -1)]
    if reprocess_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=reprocess_days)
        # Reprocess by time window (ignores entity_mentions_processed_at)
        query["$or"] = [{"fetched_at": {"$gte": cutoff}}, {"published_at": {"$gte": cutoff}}]
        skip_already_processed = False
    elif skip_already_processed:
        query["$or"] = [
            {"entity_mentions_processed_at": {"$exists": False}},
            {"entity_mentions_processed_at": None},
        ]

    cursor = article_coll.find(query).sort("fetched_at", -1)
    if limit:
        cursor = cursor.limit(limit)

    processed = 0
    inserted = 0
    skipped = 0
    errors = 0
    batch_count = 0

    async for doc in cursor:
        url = ""
        try:
            processed += 1
            url = doc.get("url") or doc.get("url_resolved") or ""
            title = (doc.get("title") or "")[:500]
            source_domain = (doc.get("source_domain") or "")[:200]
            published_at = doc.get("published_at") or doc.get("fetched_at")
            article_text = (doc.get("article_text") or "")[:DETECTION_WINDOW]
            rss_summary = (doc.get("summary") or "").strip()[:2000]

            if not url:
                skipped += 1
                await _mark_processed(article_coll, doc["_id"])
                continue

            has_full_text = bool(article_text.strip())
            if has_full_text:
                detection_text = f"{title} {rss_summary} {article_text[:DETECTION_WINDOW]}".strip()
                validation_text = article_text
                content_quality = CONTENT_QUALITY_FULL_TEXT
            else:
                detection_text = f"{title} {rss_summary}".strip()
                if not detection_text:
                    skipped += 1
                    await _mark_processed(article_coll, doc["_id"])
                    continue
                validation_text = detection_text
                content_quality = CONTENT_QUALITY_SNIPPET

            entities_found = detect_entities(detection_text)
            if not entities_found:
                skipped += 1
                await _mark_processed(article_coll, doc["_id"])
                continue

            if has_full_text:
                summary = article_text[:500].strip()
            else:
                summary = (rss_summary or title or "")[:500].strip()
            sd = (source_domain or "").strip().lower()
            mention_type = "forum" if sd in _FORUM_DOMAINS else "article"

            now_utc = datetime.now(timezone.utc)
            # IMPORTANT: never delete all mentions for a URL before inserts succeed.
            # A failed validation or exception would leave zero mentions (counts drop).
            for entity in entities_found:
                if not validate_mention_context(entity, validation_text, source_domain):
                    continue
                if reprocess_days is not None:
                    await mentions_coll.delete_many({"url": url, "entity": entity})
                existing = await mentions_coll.find_one({"entity": entity, "url": url})
                if existing:
                    continue
                mention_doc = {
                    "entity": entity,
                    "title": title,
                    "source_domain": source_domain,
                    "published_at": published_at,
                    # Always set so dashboard range (7d/30d) includes mentions indexed recently
                    # even when the article published_at is older.
                    "timestamp": now_utc,
                    "summary": summary,
                    "sentiment": None,
                    "url": url[:2000],
                    "type": mention_type,
                    "content_quality": content_quality,
                }
                await mentions_coll.insert_one(mention_doc)
                inserted += 1

            await _mark_processed(article_coll, doc["_id"])
            batch_count += 1
            if delay_between_batches_sec > 0 and batch_count >= batch_size:
                batch_count = 0
                await asyncio.sleep(delay_between_batches_sec)
        except Exception as e:
            errors += 1
            logger.warning("backfill_entity_mentions_failed", url=(url or "")[:80], error=str(e))
            try:
                await _mark_processed(article_coll, doc["_id"])
            except Exception:
                pass

    logger.info(
        "backfill_entity_mentions_complete",
        processed=processed,
        inserted=inserted,
        skipped=skipped,
        errors=errors,
    )
    return {"processed": processed, "inserted": inserted, "skipped": skipped, "errors": errors}


def main():
    p = argparse.ArgumentParser(
        description="Backfill entity_mentions; process in batches with optional delay. Marks docs as processed."
    )
    p.add_argument("--batch", type=int, default=100, help="Batch size before optional sleep")
    p.add_argument("--limit", type=int, default=None, help="Max article_documents to process (default: all unprocessed)")
    p.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds to sleep between batches (default 0.5, 0 to disable)",
    )
    p.add_argument(
        "--no-skip-processed",
        action="store_true",
        help="Process all docs including those already marked entity_mentions_processed_at",
    )
    p.add_argument(
        "--reprocess-days",
        type=int,
        default=None,
        metavar="N",
        help="Reprocess articles from last N days: delete mentions for their URLs, re-detect entities, set timestamp.",
    )
    args = p.parse_args()
    result = asyncio.run(
        run_backfill(
            batch_size=args.batch,
            limit=args.limit,
            delay_between_batches_sec=max(0.0, args.delay),
            skip_already_processed=not args.no_skip_processed,
            reprocess_days=args.reprocess_days,
        )
    )
    print(result)


if __name__ == "__main__":
    main()
