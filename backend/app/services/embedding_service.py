"""Lightweight embedding service for vector memory."""
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

_encoder = None


def get_encoder():
    """Lazy-load sentence-transformers model."""
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer
        _encoder = SentenceTransformer("all-MiniLM-L6-v2")
    return _encoder


def embed(text: str) -> list[float]:
    """Generate embedding for a single text."""
    encoder = get_encoder()
    return encoder.encode(text).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts."""
    encoder = get_encoder()
    return encoder.encode(texts).tolist()
