"""Topic extraction using KeyBERT — lightweight keyword extraction."""
from typing import List

_keybert_model = None


def _get_model():
    global _keybert_model
    if _keybert_model is None:
        from keybert import KeyBERT
        _keybert_model = KeyBERT(model="all-MiniLM-L6-v2")
    return _keybert_model


def extract_topics(text: str, top_n: int = 3) -> List[str]:
    """
    Extract top topics from text using KeyBERT.
    Combines title + snippet before extraction.
    Returns list of up to top_n topic phrases.
    """
    if not text or not isinstance(text, str):
        return []
    text = text.strip()
    if not text:
        return []
    try:
        model = _get_model()
        keywords = model.extract_keywords(
            text,
            keyphrase_ngram_range=(1, 2),
            top_n=top_n,
            use_mmr=False,
        )
        topics = [kw[0] for kw in keywords if kw[0]]
        return topics[:top_n]
    except Exception:
        return []
