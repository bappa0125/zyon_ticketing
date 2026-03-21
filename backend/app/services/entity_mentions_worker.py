"""Entity mentions pipeline — article_documents → entity detection → entity_mentions.
Reads article_documents (preferring unprocessed), detects entities, validates context,
stores entity_mentions and marks doc as processed so backlog is drained without re-processing.

Forum detection: page domain (TradingQnA, ValuePickr, Traderji) OR rss feed_domain
(e.g. news.ycombinator.com for Hacker News items whose article host is external).
Narrative tags: config/narrative_taxonomy.yaml (rule-based) for positioning / gap analytics."""
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client, get_db
from app.services.narrative_tagging_service import (
    forum_site_key,
    is_forum_document,
    tag_text_for_narratives,
)

logger = get_logger(__name__)

COLLECTION_ARTICLE_DOCUMENTS = "article_documents"
COLLECTION_ENTITY_MENTIONS = "entity_mentions"
# Larger default so each run processes more; unprocessed-first query drains backlog
BATCH_SIZE = 150


async def run_entity_mentions_pipeline(batch_size: int = BATCH_SIZE, newest_first: bool = False) -> dict[str, int]:
    """
    Read article_documents (unprocessed), run entity detection,
    validate context, write entity_mentions, mark each doc as processed.
    When newest_first=True, process newest articles first (for on-demand pipeline so UI updates).
    Returns {processed, inserted, skipped, errors}.
    """
    from app.services.entity_detection_service import detect_entities
    from app.services.mention_context_validation import validate_mention_context

    await get_mongo_client()
    db = get_db()
    article_coll = db[COLLECTION_ARTICLE_DOCUMENTS]
    mentions_coll = db[COLLECTION_ENTITY_MENTIONS]

    unprocessed_query = {
        "$or": [
            {"entity_mentions_processed_at": {"$exists": False}},
            {"entity_mentions_processed_at": None},
        ]
    }
    sort_order = [("fetched_at", -1)] if newest_first else [("fetched_at", 1)]
    cursor = (
        article_coll.find(unprocessed_query)
        .sort(sort_order)
        .limit(batch_size)
    )
    docs = await cursor.to_list(length=batch_size)

    processed = 0
    inserted = 0
    skipped = 0
    errors = 0

    async def _mark_processed(coll, doc_id):
        try:
            await coll.update_one(
                {"_id": doc_id},
                {"$set": {"entity_mentions_processed_at": datetime.now(timezone.utc)}},
            )
        except Exception as e:
            logger.warning("entity_mentions_mark_processed_failed", _id=str(doc_id), error=str(e))

    DETECTION_WINDOW = 15000
    CONTENT_QUALITY_FULL_TEXT = "full_text"
    CONTENT_QUALITY_SNIPPET = "snippet"

    for doc in docs:
        url = ""
        try:
            processed += 1
            url = doc.get("url") or doc.get("url_resolved") or ""
            title = (doc.get("title") or "")[:500]
            source_domain = (doc.get("source_domain") or "")[:200]
            feed_domain = (doc.get("feed_domain") or "").strip().lower()[:200]
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
                logger.info(
                    "entity_mentions_detection",
                    reason="no_entity",
                    article_url=url[:200] if url else "",
                )
                skipped += 1
                await _mark_processed(article_coll, doc["_id"])
                continue

            if has_full_text:
                summary = article_text[:500].strip()
            else:
                summary = (rss_summary or title or "")[:500].strip()
            sd = (source_domain or "").strip().lower()
            is_forum = is_forum_document(sd, feed_domain)
            mention_type = "forum" if is_forum else "article"
            narrative_tags, narrative_primary = tag_text_for_narratives(validation_text)
            fsite = forum_site_key(sd, feed_domain) if is_forum else None
            narrative_surface = "forum" if is_forum else "article"
            narrative_role = "amplifier" if is_forum else "publication"

            for entity in entities_found:
                if not validate_mention_context(entity, validation_text, source_domain):
                    logger.info(
                        "entity_mentions_detection",
                        reason="context_rejected",
                        entity=entity,
                        article_url=url[:200] if url else "",
                    )
                    continue

                existing = await mentions_coll.find_one({"entity": entity, "url": url})
                if existing:
                    continue

                now_utc = datetime.now(timezone.utc)
                mention_doc = {
                    "entity": entity,
                    "title": title,
                    "source_domain": source_domain,
                    "published_at": published_at,
                    # When published_at is outside the dashboard window, timestamp keeps the row
                    # visible for "last 7d / 30d" (detection/index time vs article date).
                    "timestamp": now_utc,
                    "summary": summary,
                    "sentiment": None,
                    "url": url[:2000],
                    "type": mention_type,
                    "content_quality": content_quality,
                    "narrative_tags": narrative_tags,
                    "narrative_primary": narrative_primary,
                    "narrative_surface": narrative_surface,
                    "narrative_role": narrative_role,
                    "forum_site": fsite,
                    "feed_domain": feed_domain or None,
                }
                author = (doc.get("author") or "").strip()[:300] if isinstance(doc.get("author"), str) else ""
                if author:
                    mention_doc["author"] = author
                await mentions_coll.insert_one(mention_doc)
                inserted += 1
                logger.info(
                    "entity_mentions_detection",
                    reason="inserted",
                    entity=entity,
                    article_url=url[:200] if url else "",
                    content_quality=content_quality,
                )

            await _mark_processed(article_coll, doc["_id"])

        except Exception as e:
            errors += 1
            logger.warning("entity_mentions_insert_failed", url=url[:80] if url else "", error=str(e))
            try:
                await _mark_processed(article_coll, doc["_id"])
            except Exception:
                pass

    logger.info(
        "entity_mentions_pipeline_run_complete",
        processed=processed,
        inserted=inserted,
        skipped=skipped,
        errors=errors,
    )
    return {"processed": processed, "inserted": inserted, "skipped": skipped, "errors": errors}
