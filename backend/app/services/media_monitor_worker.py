"""
Media Monitor Worker — runs media monitoring. Call periodically (e.g. every 15 min).
Uses media_monitor_service to search news, stores in MongoDB media_articles collection.
"""
from datetime import datetime

from app.core.client_config_loader import load_clients
from app.core.logging import get_logger
from app.services.media_monitor_service import (
    deduplicate_by_url,
    search_entity,
)
from app.services.mongodb import get_mongo_client

logger = get_logger(__name__)

COLLECTION_NAME = "media_articles"


async def run_media_monitor() -> dict:
    """
    Load clients from config/clients.yaml, search Google News RSS and DuckDuckGo
    for each client and competitor, store in MongoDB media_articles.
    Returns {inserted, skipped, errors}.
    """
    from app.services.mongodb import get_db, get_mongo_client

    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION_NAME]

    clients = await load_clients()
    inserted = 0
    skipped = 0
    errors = 0

    seen_urls: set[str] = set()

    for client_obj in clients:
        client_name = client_obj.get("name", "")
        competitors = client_obj.get("competitors", [])
        entities = [client_name] + (competitors if isinstance(competitors, list) else [])

        for entity in entities:
            if not entity or not isinstance(entity, str):
                continue
            try:
                articles = search_entity(entity, client_name)
                articles = deduplicate_by_url(articles)

                for a in articles[:10]:
                    url = (a.get("url") or "").strip().lower()
                    if not url:
                        continue
                    if url in seen_urls:
                        skipped += 1
                        continue
                    seen_urls.add(url)

                    pub_at = a.get("published_at") or a.get("timestamp") or datetime.utcnow()
                    doc = {
                        "entity": a.get("entity", entity),
                        "title": (a.get("title") or "")[:500],
                        "url": url,
                        "source": (a.get("source") or "")[:200],
                        "published_at": pub_at,
                        "snippet": (a.get("snippet") or "")[:500],
                    }

                    existing = await coll.find_one({"url": url})
                    if existing:
                        skipped += 1
                        continue

                    await coll.insert_one(doc)
                    inserted += 1

            except Exception as e:
                errors += 1
                logger.warning("media_monitor_entity_failed", entity=entity, error=str(e))

    logger.info(
        "media_monitor_run_complete",
        inserted=inserted,
        skipped=skipped,
        errors=errors,
    )
    return {"inserted": inserted, "skipped": skipped, "errors": errors}
