"""Snapshot storage - MongoDB operations for web_snapshots and competitors."""
from datetime import datetime
from typing import Optional
import hashlib

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

# Collections are accessed via mongodb service
def _get_db():
    from app.services.mongodb import get_db
    return get_db()


def competitors_collection():
    db = _get_db()
    return db["competitors"]


def web_snapshots_collection():
    db = _get_db()
    return db["web_snapshots"]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def create_competitor(name: str, website: str, tracking_rules: list[str] | None = None) -> str:
    coll = competitors_collection()
    now = datetime.utcnow()
    doc = {
        "name": name,
        "website": website,
        "tracking_rules": tracking_rules or [],
        "last_crawled": None,
        "next_crawl_time": now,
        "crawl_priority": 0.5,
        "change_frequency_score": 0.5,
        "created_at": now,
    }
    result = await coll.insert_one(doc)
    return str(result.inserted_id)


async def get_competitors() -> list[dict]:
    coll = competitors_collection()
    cursor = coll.find({}).sort("created_at", -1)
    items = []
    async for doc in cursor:
        items.append({
            "id": str(doc["_id"]),
            "name": doc["name"],
            "website": doc["website"],
            "tracking_rules": doc.get("tracking_rules", []),
            "last_crawled": doc.get("last_crawled"),
        })
    return items


async def update_last_crawled(competitor_id: str):
    coll = competitors_collection()
    from bson import ObjectId
    await coll.update_one(
        {"_id": ObjectId(competitor_id)},
        {"$set": {"last_crawled": datetime.utcnow()}},
    )


async def store_snapshot(competitor_id: str, url: str, html: str, text_content: str) -> str:
    coll = web_snapshots_collection()
    ch = content_hash(text_content)
    doc = {
        "competitor_id": competitor_id,
        "url": url,
        "html": html[:500_000],  # limit size
        "text_content": text_content[:200_000],
        "content_hash": ch,
        "timestamp": datetime.utcnow(),
    }
    result = await coll.insert_one(doc)
    return str(result.inserted_id)


async def get_latest_snapshot(competitor_id: str, url: str) -> Optional[dict]:
    coll = web_snapshots_collection()
    doc = await coll.find_one(
        {"competitor_id": competitor_id, "url": url},
        sort=[("timestamp", -1)],
    )
    if doc:
        return {
            "id": str(doc["_id"]),
            "content_hash": doc.get("content_hash"),
            "text_content": doc.get("text_content", ""),
            "timestamp": doc.get("timestamp"),
        }
    return None
