"""Entity mentions pipeline — article_documents → entity_detection → entity_mentions.
Reads article_documents, detects entities, validates context, stores normalized mention records."""
from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client, get_db

logger = get_logger(__name__)

COLLECTION_ARTICLE_DOCUMENTS = "article_documents"
COLLECTION_ENTITY_MENTIONS = "entity_mentions"
BATCH_SIZE = 50


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

    cursor = article_coll.find({}).sort("fetched_at", -1).limit(batch_size)
    docs = await cursor.to_list(length=batch_size)

    for doc in docs:
        url = ""
        try:
            processed += 1
            url = doc.get("url") or doc.get("url_resolved") or ""
            title = (doc.get("title") or "")[:500]
            source_domain = (doc.get("source_domain") or "")[:200]
            published_at = doc.get("published_at") or doc.get("fetched_at")
            article_text = (doc.get("article_text") or "")[:10000]

            if not url or not article_text.strip():
                skipped += 1
                continue

            entity = detect_entity(f"{title} {article_text[:2000]}")
            if not entity:
                skipped += 1
                continue

            if not validate_mention_context(entity, article_text):
                skipped += 1
                continue

            existing = await mentions_coll.find_one({"url": url, "entity": entity})
            if existing:
                skipped += 1
                continue

            summary = article_text[:500].strip()
            mention_doc = {
                "entity": entity,
                "title": title,
                "source_domain": source_domain,
                "published_at": published_at,
                "summary": summary,
                "sentiment": None,
                "url": url[:2000],
                "type": "article",
            }
            await mentions_coll.insert_one(mention_doc)
            inserted += 1

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
