"""MongoDB connection and conversation/message storage."""
import asyncio
from datetime import datetime
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_clients_by_loop: dict[int, AsyncIOMotorClient] = {}


def _loop_key() -> int:
    """
    Motor clients are effectively bound to an event loop.
    This app runs async code from multiple loops (e.g., APScheduler jobs using asyncio.run()).
    Key clients by running-loop id to avoid 'Future attached to a different loop' errors.
    """
    try:
        loop = asyncio.get_running_loop()
        return id(loop)
    except RuntimeError:
        # No running loop (sync context). Use a sentinel key.
        return 0


def reset_mongo_client() -> None:
    """Clear the cached Motor client. Use before asyncio.run() in scripts so the new loop gets a fresh client."""
    global _client, _clients_by_loop
    _client = None
    _clients_by_loop = {}


async def get_mongo_client() -> AsyncIOMotorClient:
    global _client, _clients_by_loop
    k = _loop_key()
    if k and k in _clients_by_loop:
        return _clients_by_loop[k]
    # Backward compat: keep _client for legacy sync reads
    config = get_config()
    url = config["settings"].mongodb_url
    db_name = config["mongodb"].get("database", "chat")
    c = AsyncIOMotorClient(url)
    if k:
        _clients_by_loop[k] = c
    _client = c
    logger.info("MongoDB connected", database=db_name)
    return c


def get_db():
    """Get database - call from async context after get_mongo_client."""
    config = get_config()
    # Prefer loop-scoped client when in async context.
    k = _loop_key()
    c = _clients_by_loop.get(k) if k else _client
    if c is None:
        # Caller violated contract (didn't await get_mongo_client first).
        raise RuntimeError("Mongo client not initialized; call await get_mongo_client() first")
    return c[config["mongodb"].get("database", "chat")]


def conversations_collection():
    return get_db()[get_config()["mongodb"].get("conversations_collection", "conversations")]


def messages_collection():
    return get_db()[get_config()["mongodb"].get("messages_collection", "messages")]


async def create_conversation(title: str = "New Chat") -> str:
    coll = conversations_collection()
    doc = {
        "title": title,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    result = await coll.insert_one(doc)
    return str(result.inserted_id)


async def add_message(conversation_id: str, role: str, content: str) -> str:
    coll = messages_collection()
    doc = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow(),
    }
    result = await coll.insert_one(doc)
    return str(result.inserted_id)


async def get_messages(conversation_id: str, limit: int = 50) -> list[dict]:
    coll = messages_collection()
    cursor = coll.find(
        {"conversation_id": conversation_id}
    ).sort("timestamp", 1).limit(limit)
    messages = []
    async for doc in cursor:
        messages.append({
            "id": str(doc["_id"]),
            "role": doc["role"],
            "content": doc["content"],
            "timestamp": doc["timestamp"].isoformat() if doc.get("timestamp") else None,
        })
    return messages


async def get_last_messages(conversation_id: str, n: int = 10) -> list[dict]:
    coll = messages_collection()
    cursor = coll.find(
        {"conversation_id": conversation_id}
    ).sort("timestamp", -1).limit(n)
    messages = []
    async for doc in cursor:
        messages.insert(0, {
            "id": str(doc["_id"]),
            "role": doc["role"],
            "content": doc["content"],
        })
    return messages
