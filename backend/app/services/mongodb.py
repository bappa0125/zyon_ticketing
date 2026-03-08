"""MongoDB connection and conversation/message storage."""
from datetime import datetime
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: Optional[AsyncIOMotorClient] = None


async def get_mongo_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        config = get_config()
        url = config["settings"].mongodb_url
        db_name = config["mongodb"].get("database", "chat")
        _client = AsyncIOMotorClient(url)
        logger.info("MongoDB connected", database=db_name)
    return _client


def get_db():
    """Get database - call from async context after get_mongo_client."""
    config = get_config()
    return _client[config["mongodb"].get("database", "chat")]


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
