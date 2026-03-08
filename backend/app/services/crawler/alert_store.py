"""Alert storage - MongoDB operations for crawler alerts."""
from datetime import datetime

from pymongo import MongoClient
from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

# Sync client for worker context (RQ runs sync)
_client = None


def _get_sync_db():
    global _client
    if _client is None:
        config = get_config()
        url = config["settings"].mongodb_url
        db_name = config["mongodb"].get("database", "chat")
        _client = MongoClient(url)
    return _client[get_config()["mongodb"].get("database", "chat")]


def alerts_collection():
    return _get_sync_db()["alerts"]


def create_alert(competitor_id: str, change_summary: str, impact_score: float = 0.5) -> str:
    coll = alerts_collection()
    doc = {
        "competitor_id": competitor_id,
        "change_summary": change_summary,
        "impact_score": impact_score,
        "timestamp": datetime.utcnow(),
    }
    result = coll.insert_one(doc)
    return str(result.inserted_id)
