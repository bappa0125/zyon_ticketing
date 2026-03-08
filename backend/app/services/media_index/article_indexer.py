"""Article indexer - detect mentions, store in MongoDB + Qdrant."""
import re
from datetime import datetime
from typing import Optional
from uuid import uuid4

from app.config import get_config
from app.core.logging import get_logger
from app.services.embedding_service import embed
from app.services.media_index.article_parser import fetch_and_parse
from app.services.media_index.media_crawler import crawl_sources

logger = get_logger(__name__)

# Monitored entities - expand via config
DEFAULT_MONITORED = ["Sahi.com", "Sahi trading"]


def _load_monitored() -> list[str]:
    cfg = get_config().get("media_index", {})
    return cfg.get("monitored_entities", DEFAULT_MONITORED)


def detect_mentions(text: str, entities: list[str]) -> list[str]:
    """Detect which monitored entities are mentioned in text."""
    if not text:
        return []
    text_lower = text.lower()
    found = []
    for e in entities:
        if not e:
            continue
        # Exact or domain match
        if e.lower() in text_lower:
            found.append(e)
        elif re.search(rf"\b{re.escape(e)}\b", text_lower, re.I):
            found.append(e)
    return found


def _get_media_articles_collection():
    from pymongo import MongoClient
    cfg = get_config()
    url = cfg["settings"].mongodb_url
    db_name = cfg["mongodb"].get("database", "chat")
    client = MongoClient(url)
    return client[db_name]["media_articles"]


def _get_qdrant_media():
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, VectorParams, Distance
    cfg = get_config()
    client = QdrantClient(url=cfg["settings"].qdrant_url)
    coll = "media_article_embeddings"
    size = cfg["qdrant"].get("vector_size", 384)
    collections = client.get_collections().collections
    if not any(c.name == coll for c in collections):
        client.create_collection(
            collection_name=coll,
            vectors_config=VectorParams(size=size, distance=Distance.COSINE),
        )
    return client, coll


def index_articles(max_articles: int = 20) -> int:
    """
    Crawl sources, fetch articles, detect mentions, store if mentions found.
    Returns count of articles indexed.
    """
    monitored = _load_monitored()
    entries = crawl_sources(max_articles=max_articles)
    indexed = 0
    coll = _get_media_articles_collection()
    qdrant, qcoll = _get_qdrant_media()
    seen_urls = set()
    for e in entries[:max_articles]:
        url = e.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        parsed = fetch_and_parse(url, e.get("source_domain", ""))
        if not parsed:
            continue
        text_for_mention = f"{parsed.get('title','')} {parsed.get('content','')}"
        entities = detect_mentions(text_for_mention, monitored)
        if not entities:
            continue
        from app.services.media_intelligence.sentiment import classify_sentiment
        from app.services.media_intelligence.alerts import create_alert

        content_preview = (parsed.get("content", "") or "")[:2000]
        sentiment = classify_sentiment(f"{parsed.get('title','')} {content_preview}")
        doc = {
            "title": parsed.get("title", ""),
            "url": parsed.get("url", ""),
            "source": parsed.get("source", ""),
            "publish_date": parsed.get("publish_date"),
            "content": content_preview,
            "entities_detected": entities,
            "sentiment": sentiment,
            "timestamp_indexed": datetime.utcnow(),
        }
        try:
            coll.insert_one(doc)
            for company in entities:
                create_alert(
                    company=company,
                    title=doc["title"],
                    source=doc["source"],
                    url=doc["url"],
                    publish_date=doc.get("publish_date"),
                )
            text_embed = f"{doc['title']} {doc['content'][:1500]}"
            vec = embed(text_embed)
            point = PointStruct(
                id=str(uuid4()),
                vector=vec,
                payload={
                    "url": doc["url"],
                    "title": doc["title"],
                    "source": doc["source"],
                    "publish_date": str(doc["publish_date"]) if doc.get("publish_date") else None,
                    "entities_detected": doc["entities_detected"],
                    "content_preview": doc["content"][:300],
                },
            )
            qdrant.upsert(collection_name=qcoll, points=[point])
            indexed += 1
        except Exception as ex:
            logger.warning("index_article_failed", url=url, error=str(ex))
    return indexed
