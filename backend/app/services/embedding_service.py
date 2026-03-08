"""Lightweight embedding service for vector memory."""
import os
from typing import Optional

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

_encoder = None


def get_encoder():
    """Lazy-load sentence-transformers model."""
    global _encoder
    if _encoder is None:
        token = get_config()["settings"].hf_token or os.environ.get("HF_TOKEN", "") or None
        if token:
            os.environ["HF_TOKEN"] = token
        from sentence_transformers import SentenceTransformer
        kwargs = {"token": token} if token else {}
        _encoder = SentenceTransformer("all-MiniLM-L6-v2", **kwargs)
    return _encoder


def embed(text: str) -> list[float]:
    """Generate embedding for a single text."""
    encoder = get_encoder()
    return encoder.encode(text).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings. Batch size from config (default 4) for RAM control."""
    from app.config import get_config
    encoder = get_encoder()
    batch_size = get_config().get("crawler", {}).get("embedding_batch_size", 4)
    results = []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        results.extend(encoder.encode(chunk).tolist())
    return results
