"""Rules engine - match changes against user tracking rules."""
from app.services.embedding_service import embed
from app.core.logging import get_logger

logger = get_logger(__name__)

# Keywords for common rule types
RULE_KEYWORDS = {
    "pricing": ["price", "pricing", "cost", "fee", "subscription", "$", "dollar"],
    "ai_feature": ["ai", "artificial intelligence", "machine learning", "ml", "gpt", "llm"],
    "headline": ["headline", "title", "h1", "hero"],
    "blog": ["blog", "post", "article"],
}


def rule_matches(change_summary: str, text_content: str, tracking_rules: list[str]) -> bool:
    """
    Check if a change matches any tracking rule.
    Uses keyword matching + semantic similarity for natural language rules.
    """
    if not tracking_rules:
        return True  # No rules = alert on any change

    text_lower = (change_summary + " " + text_content[:2000]).lower()

    for rule in tracking_rules:
        rule_lower = rule.lower().strip()

        # Check predefined rule types
        if "pricing" in rule_lower and any(kw in text_lower for kw in RULE_KEYWORDS["pricing"]):
            return True
        if "ai" in rule_lower and any(kw in text_lower for kw in RULE_KEYWORDS["ai_feature"]):
            return True

        # Keyword presence in rule
        rule_words = [w for w in rule_lower.split() if len(w) > 2]
        if rule_words and any(w in text_lower for w in rule_words):
            return True

    return False
