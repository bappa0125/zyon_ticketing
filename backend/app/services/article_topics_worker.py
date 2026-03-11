"""Article Topics Worker — extract topics (KeyBERT) on article_documents, store on doc.
Processes article_documents where topics is missing. Batch ~20–50."""
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client
from app.services.topic_service import extract_topics

logger = get_logger(__name__)

COLLECTION_NAME = "article_documents"
BATCH_SIZE = 30
TOP_N = 5
MAX_TEXT_LEN = 6000  # title + summary + article_text prefix


async def run_article_topics_pipeline(batch_size: int = BATCH_SIZE) -> dict[str, int]:
    """
    Load article_documents where topics is missing or empty.
    Extract topics via KeyBERT on title + summary + article_text.
    Store topics array on each document.
    Returns {processed, errors}.
    """
    from app.services.mongodb import get_db

    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION_NAME]

    query = {"$or": [{"topics": {"$exists": False}}, {"topics": []}, {"topics": None}]}
    cursor = coll.find(query).limit(batch_size)
    batch: list[dict[str, Any]] = []
    async for doc in cursor:
        batch.append(doc)

    processed = 0
    errors = 0

    for doc in batch:
        try:
            title = (doc.get("title") or "").strip()
            summary = (doc.get("summary") or "").strip()
            article_text = (doc.get("article_text") or "").strip()
            parts = [title, summary, article_text[:3000]]
            text = " ".join(p for p in parts if p)[:MAX_TEXT_LEN].strip()

            if not text:
                topics: list[str] = []
            else:
                topics = extract_topics(text, top_n=TOP_N)

            await coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {"topics": topics, "topics_updated_at": datetime.now(timezone.utc)}},
            )
            processed += 1

        except Exception as e:
            errors += 1
            logger.warning(
                "article_topics_extraction_failed",
                doc_id=str(doc.get("_id")),
                error=str(e),
            )

    if processed or errors:
        logger.info(
            "article_topics_worker_complete",
            processed=processed,
            errors=errors,
        )
    return {"processed": processed, "errors": errors}
