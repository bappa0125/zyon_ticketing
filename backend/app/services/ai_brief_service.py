"""AI Brief — generate and store in MongoDB. Daily job + GET from DB."""

from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client, get_db

logger = get_logger(__name__)

COLLECTION = "ai_briefs"


def _json_safe(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


async def get_ai_brief_from_db(client: str, range_param: str) -> dict[str, Any] | None:
    """Return latest AI brief for client+range from MongoDB, or None."""
    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION]
    doc = await coll.find_one(
        {"client": client, "range": range_param},
        sort=[("generated_at", -1)],
        projection={"_id": 0, "client": 1, "range": 1, "generated_at": 1, "brief": 1, "inputs": 1},
    )
    if not doc:
        return None
    gen = doc.get("generated_at")
    if isinstance(gen, datetime) and gen.tzinfo is None:
        gen = gen.replace(tzinfo=timezone.utc)
    return {
        "client": doc.get("client"),
        "range": doc.get("range"),
        "generated_at": gen.isoformat() if hasattr(gen, "isoformat") else str(gen),
        "brief": doc.get("brief") or {},
        "inputs": doc.get("inputs") or {},
    }


async def save_ai_brief_to_db(
    client: str,
    range_param: str,
    brief: dict[str, Any],
    inputs: dict[str, Any] | None = None,
) -> None:
    """Store AI brief in MongoDB (upsert by client+range, keep latest)."""
    await get_mongo_client()
    db = get_db()
    coll = db[COLLECTION]
    now = datetime.now(timezone.utc)
    doc = {
        "client": client,
        "range": range_param,
        "generated_at": now,
        "brief": _json_safe(brief),
        "inputs": inputs or {},
    }
    await coll.update_one(
        {"client": client, "range": range_param},
        {"$set": doc},
        upsert=True,
    )
    logger.info("ai_brief_saved", client=client, range=range_param)
