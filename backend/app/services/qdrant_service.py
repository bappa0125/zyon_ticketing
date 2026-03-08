"""Qdrant vector store for chat embeddings."""
from typing import Optional
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams

from app.config import get_config
from app.core.logging import get_logger
from app.services.embedding_service import embed

logger = get_logger(__name__)

_client: Optional[QdrantClient] = None


def get_qdrant() -> QdrantClient:
    global _client
    if _client is None:
        config = get_config()
        url = config["settings"].qdrant_url
        _client = QdrantClient(url=url)
        logger.info("Qdrant connected")
    return _client


def get_collection_name() -> str:
    return get_config()["qdrant"].get("collection", "chat_embeddings")


def get_vector_size() -> int:
    return get_config()["qdrant"].get("vector_size", 384)


def ensure_collection() -> None:
    """Create collection if it doesn't exist."""
    client = get_qdrant()
    name = get_collection_name()
    size = get_vector_size()
    collections = client.get_collections().collections
    if not any(c.name == name for c in collections):
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=size, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection", collection=name)


def upsert_message(conversation_id: str, message_id: str, role: str, content: str) -> None:
    """Store message embedding in Qdrant."""
    ensure_collection()
    client = get_qdrant()
    vector = embed(content)
    point = PointStruct(
        id=str(uuid4()),
        vector=vector,
        payload={
            "conversation_id": conversation_id,
            "message_id": message_id,
            "role": role,
            "content": content,
        },
    )
    client.upsert(
        collection_name=get_collection_name(),
        points=[point],
    )


def search_similar(conversation_id: str, query: str, limit: int = 5) -> list[dict]:
    """Retrieve relevant past messages for context."""
    ensure_collection()
    client = get_qdrant()
    query_vector = embed(query)
    results = client.search(
        collection_name=get_collection_name(),
        query_vector=query_vector,
        query_filter=None,  # Could filter by conversation_id for scoped search
        limit=limit,
    )
    return [
        {
            "content": r.payload.get("content", ""),
            "role": r.payload.get("role", ""),
        }
        for r in results
    ]
