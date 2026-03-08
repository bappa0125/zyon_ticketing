"""
Topic Worker — run topic detection on media_articles.
Processes only documents without topics field. Max batch size: 20.
"""
from typing import Any

from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client
from app.services.topic_service import extract_topics

logger = get_logger(__name__)

COLLECTION_NAME = "media_articles"
BATCH_SIZE = 20
TOP_N = 3


async def run_topic_detection() -> dict[str, int]:
    """
    Load articles from media_articles where topics is missing.
    Process in batches of 20, extract top 3 topics, update MongoDB.
    Returns {processed, errors}.
    """
    from app.services.mongodb import get_db

    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION_NAME]

    query = {"topics": {"$exists": False}}
    cursor = coll.find(query).limit(BATCH_SIZE)
    processed = 0
    errors = 0

    batch: list[dict[str, Any]] = []
    async for doc in cursor:
        batch.append(doc)

    for doc in batch:
        try:
            title = (doc.get("title") or "").strip()
            snippet = (doc.get("snippet") or "").strip()
            text = f"{title} — {snippet}".strip() if snippet else title
            if not text:
                text = title or ""

            topics = extract_topics(text, top_n=TOP_N)

            await coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {"topics": topics}},
            )
            processed += 1

        except Exception as e:
            errors += 1
            logger.warning(
                "topic_detection_failed",
                doc_id=str(doc.get("_id")),
                error=str(e),
            )

    if processed or errors:
        logger.info(
            "topic_worker_run_complete",
            processed=processed,
            errors=errors,
        )
    return {"processed": processed, "errors": errors}
