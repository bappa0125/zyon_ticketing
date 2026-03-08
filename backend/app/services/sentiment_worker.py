"""
Sentiment Worker — run sentiment analysis on media_articles.
Processes only documents without sentiment field. Max batch size: 20.
"""
from typing import Any

from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client
from app.services.sentiment_service import analyze_sentiment

logger = get_logger(__name__)

COLLECTION_NAME = "media_articles"
BATCH_SIZE = 20


async def run_sentiment_analysis() -> dict[str, int]:
    """
    Load articles from media_articles where sentiment is missing.
    Process in batches of 20, update MongoDB with sentiment and sentiment_score.
    Returns {processed, skipped, errors}.
    """
    from app.services.mongodb import get_db

    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION_NAME]

    query = {"sentiment": {"$exists": False}}
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

            sentiment_label, sentiment_score = analyze_sentiment(text)

            await coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {"sentiment": sentiment_label, "sentiment_score": sentiment_score}},
            )
            processed += 1

        except Exception as e:
            errors += 1
            logger.warning(
                "sentiment_analysis_failed",
                doc_id=str(doc.get("_id")),
                error=str(e),
            )

    if processed or errors:
        logger.info(
            "sentiment_worker_run_complete",
            processed=processed,
            errors=errors,
        )
    return {"processed": processed, "errors": errors}
