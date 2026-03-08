"""Real-time mention alerts - create when new articles are detected."""
from datetime import datetime
from typing import Optional

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)


def _get_alerts_collection():
    from pymongo import MongoClient
    cfg = get_config()
    client = MongoClient(cfg["settings"].mongodb_url)
    db = client[cfg["mongodb"].get("database", "chat")]
    return db["mention_alerts"]


def create_alert(
    company: str,
    title: str,
    source: str,
    url: str,
    publish_date: Optional[datetime] = None,
) -> None:
    """Create an alert record when a new mention is detected."""
    try:
        coll = _get_alerts_collection()
        doc = {
            "company": company,
            "title": title,
            "source": source,
            "url": url,
            "publish_date": publish_date,
            "created_at": datetime.utcnow(),
        }
        coll.insert_one(doc)
        logger.info("mention_alert_created", company=company, url=url[:80])
    except Exception as e:
        logger.warning("mention_alert_failed", company=company, error=str(e))


def get_alerts(company: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Get alerts. Optional company filter."""
    coll = _get_alerts_collection()
    q = {"company": company} if company else {}
    cursor = coll.find(q).sort("created_at", -1).limit(limit)
    out = []
    for doc in cursor:
        out.append({
            "company": doc.get("company", ""),
            "title": doc.get("title", ""),
            "source": doc.get("source", ""),
            "url": doc.get("url", ""),
            "publish_date": str(doc["publish_date"])[:10] if doc.get("publish_date") else None,
        })
    return out
