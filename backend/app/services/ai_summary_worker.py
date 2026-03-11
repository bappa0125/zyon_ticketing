"""AI Summary Worker — generate one-line summary for article_documents and entity_mentions.
Uses title + snippet (and optional article_text slice). Stores in ai_summary field.
Free tier: ~50 LLM calls/day; use batch 25+25 once/day to stay within limit."""
from typing import Any

from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client

logger = get_logger(__name__)

ENTITY_MENTIONS_COLLECTION = "entity_mentions"
ARTICLE_DOCUMENTS_COLLECTION = "article_documents"
DEFAULT_BATCH_SIZE = 25  # Per collection; 25+25 = 50/day keeps under OpenRouter free tier
MAX_INPUT_CHARS = 1500


async def _generate_one_line_summary(text: str) -> str | None:
    """Call LLM to produce one short sentence. Returns None if no key or error."""
    if not text or not text.strip():
        return None
    from app.services.llm_gateway import LLMGateway
    gateway = LLMGateway()
    if not gateway.api_key:
        return None
    prompt = f"""Summarize the following in one short sentence (max 25 words). Output only the sentence, no quotes or prefix.

{text.strip()[:MAX_INPUT_CHARS]}"""
    try:
        chunks: list[str] = []
        async for chunk in gateway.chat_completion(
            [{"role": "user", "content": prompt}],
            stream=False,
        ):
            if chunk and not chunk.strip().startswith("{"):
                chunks.append(chunk)
        content = "".join(chunks).strip()
        if content and len(content) < 500:
            return content[:500]
        return None
    except Exception as e:
        logger.warning("ai_summary_llm_failed", error=str(e))
        return None


async def run_ai_summary_worker(batch_size: int | None = None) -> dict[str, int]:
    """
    Process article_documents and entity_mentions where ai_summary is missing.
    Generate one-line summary from title + snippet (and article_text when present). Update doc.
    batch_size: per collection (default 25); 25+25 keeps under ~50 LLM calls/day (free tier).
    Returns {processed, errors}.
    """
    await get_mongo_client()
    from app.config import get_config
    from app.services.mongodb import get_db

    if batch_size is None:
        batch_size = (get_config().get("scheduler") or {}).get("ai_summary_batch_size", DEFAULT_BATCH_SIZE)

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]
    art_coll = db[ARTICLE_DOCUMENTS_COLLECTION]

    processed = 0
    errors = 0

    # entity_mentions: no ai_summary or empty
    try:
        cursor = em_coll.find({
            "$or": [
                {"ai_summary": {"$exists": False}},
                {"ai_summary": None},
                {"ai_summary": ""},
            ],
        }).limit(batch_size)
        async for doc in cursor:
            title = (doc.get("title") or "").strip()
            snippet = (doc.get("summary") or doc.get("snippet") or "").strip()
            text = f"{title}. {snippet}".strip() if snippet else title
            if not text:
                continue
            summary = await _generate_one_line_summary(text)
            if summary:
                try:
                    await em_coll.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {"ai_summary": summary}},
                    )
                    processed += 1
                except Exception as e:
                    errors += 1
                    logger.warning("ai_summary_update_em_failed", id=str(doc.get("_id")), error=str(e))
    except Exception as e:
        logger.warning("ai_summary_entity_mentions_failed", error=str(e))

    # article_documents: no ai_summary or empty
    try:
        cursor = art_coll.find({
            "$or": [
                {"ai_summary": {"$exists": False}},
                {"ai_summary": None},
                {"ai_summary": ""},
            ],
        }).limit(batch_size)
        async for doc in cursor:
            title = (doc.get("title") or "").strip()
            snippet = (doc.get("summary") or "").strip()
            body = (doc.get("article_text") or "").strip()[:600]
            text = f"{title}. {snippet}".strip() if snippet else title
            if body:
                text = f"{text} {body}"
            text = text.strip()
            if not text:
                continue
            summary = await _generate_one_line_summary(text)
            if summary:
                try:
                    await art_coll.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {"ai_summary": summary}},
                    )
                    processed += 1
                except Exception as e:
                    errors += 1
                    logger.warning("ai_summary_update_art_failed", id=str(doc.get("_id")), error=str(e))
    except Exception as e:
        logger.warning("ai_summary_article_documents_failed", error=str(e))

    if processed or errors:
        logger.info("ai_summary_worker_run_complete", processed=processed, errors=errors)
    return {"processed": processed, "errors": errors}
