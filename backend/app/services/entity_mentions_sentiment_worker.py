"""
Sentiment for entity_mentions — run VADER on title + summary/snippet, store sentiment.
Processes only rows where sentiment is missing. Batch-based, non-blocking.
Used so Media Intelligence feed and Sentiment page show tone per mention.
"""
from typing import Any

from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client, get_db
from app.services.sentiment_service import analyze_sentiment

logger = get_logger(__name__)

COLLECTION = "entity_mentions"
BATCH_SIZE = 50
MAX_TEXT_CHARS = 4000


async def run_entity_mentions_sentiment(batch_size: int = BATCH_SIZE) -> dict[str, int]:
    """
    Find entity_mentions where sentiment is missing, run VADER on title + summary,
    update with sentiment and sentiment_score. Returns {processed, errors}.
    """
    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION]

    query: dict[str, Any] = {
        "$or": [
            {"sentiment": {"$exists": False}},
            {"sentiment": None},
        ]
    }
    cursor = coll.find(query).limit(batch_size)
    docs = await cursor.to_list(length=batch_size)

    processed = 0
    errors = 0

    for doc in docs:
        try:
            title = (doc.get("title") or "").strip()[:2000]
            summary = (doc.get("summary") or doc.get("snippet") or "").strip()[:2000]
            text = f"{title} {summary}".strip()[:MAX_TEXT_CHARS] or title or "neutral"
            if not text:
                text = "neutral"

            label, score = analyze_sentiment(text)

            await coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {"sentiment": label, "sentiment_score": score}},
            )
            processed += 1
        except Exception as e:
            errors += 1
            logger.warning(
                "entity_mentions_sentiment_failed",
                _id=str(doc.get("_id", "")),
                error=str(e),
            )

    if processed or errors:
        logger.info(
            "entity_mentions_sentiment_complete",
            processed=processed,
            errors=errors,
        )
    return {"processed": processed, "errors": errors}
