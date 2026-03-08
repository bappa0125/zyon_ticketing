"""Sync snapshot storage for RQ worker - MongoDB for competitors, disk for snapshots."""
from datetime import datetime, timedelta
from typing import Optional
import hashlib

from pymongo import MongoClient
from app.config import get_config

_client = None


def _get_db():
    global _client
    if _client is None:
        cfg = get_config()
        _client = MongoClient(cfg["settings"].mongodb_url)
    return _client[get_config()["mongodb"].get("database", "chat")]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_competitors_sync() -> list[dict]:
    coll = _get_db()["competitors"]
    return list(coll.find({}))


def get_competitors_for_crawl_sync() -> list[dict]:
    """Competitors due for crawl, ordered by priority (next_crawl_time, crawl_priority)."""
    coll = _get_db()["competitors"]
    now = datetime.utcnow()
    cursor = coll.find({"website": {"$exists": True, "$ne": ""}})
    due = []
    for c in cursor:
        website = (c.get("website") or "").strip()
        if not website:
            continue
        next_time = c.get("next_crawl_time") or now
        if isinstance(next_time, datetime) and next_time > now:
            continue
        due.append(c)
    # Sort: higher priority first, then soonest next_crawl
    due.sort(
        key=lambda x: (
            -(x.get("crawl_priority") or 0),
            x.get("next_crawl_time") or datetime.min,
        )
    )
    return due


def get_competitor_sync(competitor_id: str) -> Optional[dict]:
    from bson import ObjectId
    coll = _get_db()["competitors"]
    return coll.find_one({"_id": ObjectId(competitor_id)})


def get_latest_snapshot_sync(competitor_id: str, url: str) -> Optional[dict]:
    """Use disk snapshot store for minimal memory; fallback to MongoDB if needed."""
    from app.services.crawler.disk_snapshot_store import get_latest_snapshot_disk
    disk = get_latest_snapshot_disk(competitor_id, url)
    if disk:
        return disk
    coll = _get_db()["web_snapshots"]
    return coll.find_one(
        {"competitor_id": competitor_id, "url": url},
        sort=[("timestamp", -1)],
    )


def get_snapshot_metadata_sync(competitor_id: str, url: str) -> Optional[dict]:
    """Hash + text only for change detection (minimal memory). Disk first, then MongoDB."""
    from app.services.crawler.disk_snapshot_store import get_snapshot_metadata_disk
    disk = get_snapshot_metadata_disk(competitor_id, url)
    if disk:
        return disk
    coll = _get_db()["web_snapshots"]
    doc = coll.find_one(
        {"competitor_id": competitor_id, "url": url},
        sort=[("timestamp", -1)],
        projection={"content_hash": 1, "text_content": 1, "timestamp": 1},
    )
    if doc:
        return {
            "content_hash": doc.get("content_hash"),
            "text_content": doc.get("text_content", ""),
            "timestamp": doc.get("timestamp"),
        }
    return None


def store_snapshot_sync(competitor_id: str, url: str, extracted: dict, text_content: str) -> str:
    """Store on disk; extracted = {title, main_content, pricing, headers, text_content}."""
    from app.services.crawler.disk_snapshot_store import store_snapshot_disk, content_hash as ch
    content_hash_val = ch(text_content)
    return store_snapshot_disk(competitor_id, url, {**extracted, "text_content": text_content}, content_hash_val)


def update_competitor_after_crawl_sync(
    competitor_id: str,
    change_detected: bool,
    frequency_minutes: int = 30,
):
    """Update last_crawled, next_crawl_time, change_frequency_score."""
    from bson import ObjectId
    coll = _get_db()["competitors"]
    now = datetime.utcnow()
    comp = coll.find_one({"_id": ObjectId(competitor_id)})
    if not comp:
        return
    base_interval = frequency_minutes
    score = comp.get("change_frequency_score", 0.5)
    if change_detected:
        # Recently changed: crawl more often
        interval = max(5, int(base_interval * 0.5))
        new_score = min(1.0, score + 0.1)
    else:
        # Low activity: crawl less often
        interval = int(base_interval * (1.5 - score * 0.5))
        new_score = max(0.2, score - 0.05)
    next_time = now + timedelta(minutes=interval)
    coll.update_one(
        {"_id": ObjectId(competitor_id)},
        {
            "$set": {
                "last_crawled": now,
                "next_crawl_time": next_time,
                "change_frequency_score": new_score,
            }
        },
    )

