"""Intent Classification — hybrid rule + embedding layer. Gates search pipelines."""
from typing import Literal, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

Intent = Literal["chat", "search", "analytics"]

SEARCH_SIMILARITY_THRESHOLD = 0.5
SEARCH_EXAMPLES = [
    "give me top articles about Zerodha",
    "latest news on Sahi",
    "find articles about Upstox with sources",
    "show me recent mentions of Groww",
    "search for articles about Sahi trading app",
]
_search_embeddings: list[list[float]] | None = None


def _get_search_embeddings() -> list[list[float]]:
    """Lazy-load embeddings for search intent examples. Uses existing embedding service."""
    global _search_embeddings
    if _search_embeddings is None:
        try:
            from app.services.embedding_service import embed
            _search_embeddings = [embed(ex) for ex in SEARCH_EXAMPLES]
        except Exception as e:
            logger.warning("intent_embedding_load_failed", error=str(e))
            _search_embeddings = []
    return _search_embeddings


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return dot / (na * nb)


def classify_intent(message: str) -> tuple[Intent, Optional[str]]:
    """
    Hybrid intent classification: rule-based first, embedding fallback.
    No LLM calls. Uses existing lightweight embedding model.

    Returns:
        (intent, search_entity) — search_entity is the extracted company/topic for search intent.
    """
    from app.services.url_discovery.intent_detector import (
        is_greeting_or_casual,
        extract_company_or_topic,
    )

    msg = message.strip()
    if len(msg) < 3:
        return ("chat", None)

    # 1. Rule: greetings and casual -> chat
    if is_greeting_or_casual(msg):
        return ("chat", None)

    # 2. Rule: entity + trigger patterns -> search
    entity = extract_company_or_topic(msg)
    if entity:
        return ("search", entity)

    # 3. Embedding: similarity to search examples
    try:
        from app.services.embedding_service import embed
        embeds = _get_search_embeddings()
        if embeds:
            user_emb = embed(msg)
            sims = [_cosine_sim(user_emb, ex) for ex in embeds]
            max_sim = max(sims) if sims else 0.0
            if max_sim >= SEARCH_SIMILARITY_THRESHOLD:
                # High similarity but no entity — still need entity for search. Don't trigger.
                return ("chat", None)
    except Exception as e:
        logger.debug("intent_embedding_failed", error=str(e))

    # 4. Default: chat (no entity reference -> don't trigger search)
    return ("chat", None)
