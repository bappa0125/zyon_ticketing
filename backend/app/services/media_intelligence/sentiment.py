"""Sentiment classification for articles - positive, negative, neutral."""
import re

POSITIVE_WORDS = frozenset([
    "growth", "profit", "success", "launch", "raise", "expansion", "partnership",
    "breakthrough", "award", "innovation", "record", "surge", "rise", "gain",
    "positive", "optimistic", "strong", "upgrade", "exceed", "beat",
])
NEGATIVE_WORDS = frozenset([
    "decline", "loss", "fail", "drop", "fall", "concern", "warning", "layoff",
    "cut", "negative", "worst", "crash", "miss", "downgrade", "lawsuit",
    "breach", "fraud", "scandal", "penalty", "fine", "risk",
])


def classify_sentiment(text: str) -> str:
    """Classify text as positive, negative, or neutral."""
    if not text or not isinstance(text, str):
        return "neutral"
    t = text.lower()[:3000]
    words = set(re.findall(r"\b[a-z]{4,}\b", t))
    pos = len(words & POSITIVE_WORDS)
    neg = len(words & NEGATIVE_WORDS)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"
