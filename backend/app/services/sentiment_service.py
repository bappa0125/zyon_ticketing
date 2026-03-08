"""Sentiment analysis using VADER — lightweight, no transformers."""
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer: SentimentIntensityAnalyzer | None = None


def _get_analyzer() -> SentimentIntensityAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


def analyze_sentiment(text: str) -> tuple[str, float]:
    """
    Analyze sentiment of text using VADER.
    Returns (sentiment_label, compound_score).
    compound > 0.05 → positive
    compound < -0.05 → negative
    else → neutral
    """
    if not text or not isinstance(text, str):
        return "neutral", 0.0
    analyzer = _get_analyzer()
    scores = analyzer.polarity_scores(text.strip())
    compound = scores.get("compound", 0.0)
    if compound > 0.05:
        return "positive", compound
    if compound < -0.05:
        return "negative", compound
    return "neutral", compound
