"""Entity mentions pipeline — article_documents → entity_detection → entity_mentions.
Reads article_documents, detects entities, validates context, stores normalized mention records."""
from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client, get_db

logger = get_logger(__name__)

COLLECTION_ARTICLE_DOCUMENTS = "article_documents"
COLLECTION_ENTITY_MENTIONS = "entity_mentions"
BATCH_SIZE = 50
_FORUM_DOMAINS = {
    "tradingqna.com",
    "traderji.com",
    "valuepickr.com",
}


async def run_entity_mentions_pipeline(batch_size: int = BATCH_SIZE) -> dict[str, int]:
    """
    Read article_documents, run entity detection, validate context, write entity_mentions.
    Returns {processed, inserted, skipped, errors}.
    """
    from app.services.entity_detection_service import detect_entity
    from app.services.mention_context_validation import validate_mention_context

    await get_mongo_client()
    db = get_db()
    article_coll = db[COLLECTION_ARTICLE_DOCUMENTS]
    mentions_coll = db[COLLECTION_ENTITY_MENTIONS]

    processed = 0
    inserted = 0
    skipped = 0
    errors = 0

    # Process articles whose url is not yet in entity_mentions (so every article is eventually processed)
    pipeline = [
        {"$lookup": {"from": COLLECTION_ENTITY_MENTIONS, "localField": "url", "foreignField": "url", "as": "mentions"}},
        {"$match": {"mentions": {"$size": 0}}},
        {"$sort": {"fetched_at": -1}},
        {"$limit": batch_size},
    ]
    cursor = article_coll.aggregate(pipeline)
    docs = await cursor.to_list(length=batch_size)

    DETECTION_WINDOW = 8000

    for doc in docs:
        url = ""
        try:
            processed += 1
            url = doc.get("url") or doc.get("url_resolved") or ""
            title = (doc.get("title") or "")[:500]
            source_domain = (doc.get("source_domain") or "")[:200]
            published_at = doc.get("published_at") or doc.get("fetched_at")
            article_text = (doc.get("article_text") or "")[:10000]
            rss_summary = (doc.get("summary") or "").strip()[:2000]

            if not url or not article_text.strip():
                skipped += 1
                continue

            detection_text = f"{title} {rss_summary} {article_text[:DETECTION_WINDOW]}".strip()
            entity = detect_entity(detection_text)
            if not entity:
                logger.info(
                    "entity_mentions_detection",
                    reason="no_entity",
                    article_url=url[:200] if url else "",
                )
                skipped += 1
                continue

            if not validate_mention_context(entity, article_text):
                logger.info(
                    "entity_mentions_detection",
                    reason="context_rejected",
                    entity=entity,
                    article_url=url[:200] if url else "",
                )
                skipped += 1
                continue

            # Safety deduplication: skip if same url + entity already exists
            existing = await mentions_coll.find_one({"entity": entity, "url": url})
            if existing:
                skipped += 1
                continue

            summary = article_text[:500].strip()
            sd = (source_domain or "").strip().lower()
            mention_type = "forum" if sd in _FORUM_DOMAINS else "article"
            mention_doc = {
                "entity": entity,
                "title": title,
                "source_domain": source_domain,
                "published_at": published_at,
                "summary": summary,
                "sentiment": None,
                "url": url[:2000],
                "type": mention_type,
            }
            await mentions_coll.insert_one(mention_doc)
            inserted += 1
            logger.info(
                "entity_mentions_detection",
                reason="inserted",
                entity=entity,
                article_url=url[:200] if url else "",
            )

        except Exception as e:
            errors += 1
            logger.warning("entity_mentions_insert_failed", url=url[:80] if url else "", error=str(e))

    logger.info(
        "entity_mentions_pipeline_run_complete",
        processed=processed,
        inserted=inserted,
        skipped=skipped,
        errors=errors,
    )
    return {"processed": processed, "inserted": inserted, "skipped": skipped, "errors": errors}
