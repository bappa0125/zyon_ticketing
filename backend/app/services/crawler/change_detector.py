"""Hash-first change detection. Embeddings/LLM only when hash changes."""
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


def _text_diff_percent(old_text: str, new_text: str) -> float:
    """Rough change ratio (0=identical, 1=completely different)."""
    if not old_text and not new_text:
        return 0.0
    if not old_text or not new_text:
        return 1.0
    old_w = set(old_text.lower().split())
    new_w = set(new_text.lower().split())
    if not old_w and not new_w:
        return 0.0
    inter = len(old_w & new_w)
    union = len(old_w | new_w)
    return 1.0 - (inter / union) if union else 0.0


def detect_changes(
    old_text: str,
    new_text: str,
    old_hash: Optional[str] = None,
    new_hash: Optional[str] = None,
    similarity_threshold: float = 0.85,
    run_semantic: bool = True,
) -> tuple[bool, str]:
    """
    Hash-first: if hashes match, return no change.
    Only run embedding/semantic when hash differs.
    Returns (has_change, change_summary).
    """
    if not new_text:
        return False, ""

    # 1. Hash comparison - skip expensive work
    if old_hash and new_hash and old_hash == new_hash:
        return False, ""

    if not old_text:
        return True, "New page content"

    # 2. Quick text diff
    diff_pct = _text_diff_percent(old_text, new_text)
    if diff_pct < 0.02:
        return False, ""

    # 3. Optional: semantic similarity (only when hash changed)
    if run_semantic:
        try:
            from app.services.embedding_service import embed
            old_emb = embed(old_text[:8000])
            new_emb = embed(new_text[:8000])
            dot = sum(a * b for a, b in zip(old_emb, new_emb))
            na = sum(x * x for x in old_emb) ** 0.5
            nb = sum(x * x for x in new_emb) ** 0.5
            sim = dot / (na * nb) if na and nb else 0.0
            if sim >= similarity_threshold:
                return False, ""
        except Exception as e:
            logger.warning("embedding_failed", error=str(e))
            # Fallback to text diff
            if diff_pct < 0.15:
                return False, ""

    # Significant change
    if diff_pct > 0.5:
        summary = "Major content change detected"
    elif diff_pct > 0.2:
        summary = "Moderate content change detected"
    else:
        summary = "Minor content change detected"

    logger.info("change_detected", diff_pct=round(diff_pct, 3))
    return True, summary
