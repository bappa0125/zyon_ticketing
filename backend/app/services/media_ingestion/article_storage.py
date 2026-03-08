"""Article storage - MongoDB (media_articles) + Qdrant (vectors). URL uniqueness."""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from app.config import get_config
from app.core.logging import get_logger
from app.services.embedding_service import embed
from app.services.media_ingestion.entity_detector import detect_entities

logger = get_logger(__name__)

COLLECTION = "media_articles"
QDRANT_COLLECTION = "media_article_embeddings"


def _get_mongo_collection():
    from pymongo import MongoClient
    cfg = get_config()
    client = MongoClient(cfg["settings"].mongodb_url)
    db = client[cfg["mongodb"].get("database", "chat")]
    coll = db[COLLECTION]
    coll.create_index("url", unique=True)
    return coll


def _get_qdrant():
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, VectorParams, Distance
    cfg = get_config()
    client = QdrantClient(url=cfg["settings"].qdrant_url)
    size = cfg["qdrant"].get("vector_size", 384)
    collections = client.get_collections().collections
    if not any(c.name == QDRANT_COLLECTION for c in collections):
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=size, distance=Distance.COSINE),
        )
    return client


def url_exists(url: str) -> bool:
    """Check if URL already in database."""
    coll = _get_mongo_collection()
    return coll.count_documents({"url": url}, limit=1) > 0


def store_article(
    title: str,
    url: str,
    source: str,
    publish_date: Optional[datetime],
    content: str,
    entities: list[str],
) -> bool:
    """
    Store article in MongoDB + Qdrant. Returns True if stored (URL was new).
    Ensures URL uniqueness - skips if URL exists.
    """
    coll = _get_mongo_collection()
    if coll.count_documents({"url": url}, limit=1) > 0:
        return False
    from app.services.media_intelligence.sentiment import classify_sentiment
    from app.services.media_intelligence.alerts import create_alert

    content_preview = content[:2000]
    sentiment = classify_sentiment(f"{title} {content_preview}")
    doc = {
        "title": title,
        "url": url,
        "source": source,
        "publish_date": publish_date,
        "content": content_preview,
        "entities": entities,
        "sentiment": sentiment,
        "timestamp_indexed": datetime.utcnow(),
    }
    try:
        coll.insert_one(doc)
        for company in entities:
            create_alert(
                company=company,
                title=title,
                source=source,
                url=url,
                publish_date=publish_date,
            )
        qdrant = _get_qdrant()
        text_embed = f"{title} {content[:1500]}"
        vec = embed(text_embed)
        point = PointStruct(
            id=str(uuid4()),
            vector=vec,
            payload={
                "url": url,
                "title": title,
                "source": source,
                "publish_date": str(publish_date) if publish_date else None,
                "entities": entities,
                "content_preview": content[:300],
            },
        )
        qdrant.upsert(collection_name=QDRANT_COLLECTION, points=[point])
        return True
    except Exception as e:
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            return False
        logger.warning("store_article_failed", url=url, error=str(e))
        raise
