"""Detect if user message requests URL discovery (mentions, articles, etc.).
Supports regex patterns and embedding-based intent. Live search is always tried first for substantive messages."""
import re
from typing import Tuple

# Example queries for "article/news search" intent - used for embedding similarity
ARTICLE_SEARCH_EXAMPLES = [
    "give me top articles about Zerodha",
    "latest news on Shahrukh Khan",
    "find articles about Sahi with sources and summary",
    "search for recent mentions of Upstox",
    "show me articles about this company",
]

_article_search_embeddings: list[list[float]] | None = None


def _get_article_search_embeddings() -> list[list[float]]:
    """Lazy-load embeddings for article search intent examples."""
    global _article_search_embeddings
    if _article_search_embeddings is None:
        try:
            from app.services.embedding_service import embed
            _article_search_embeddings = [embed(ex) for ex in ARTICLE_SEARCH_EXAMPLES]
        except Exception:
            _article_search_embeddings = []
    return _article_search_embeddings


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return dot / (norm_a * norm_b)


def is_article_search_intent_embedding(message: str) -> Tuple[bool, float]:
    """
    Use embedding model to detect article/news search intent.
    Returns (is_search_intent, max_similarity).
    """
    msg = message.strip()
    if len(msg) < 10:
        return (False, 0.0)
    try:
        from app.services.embedding_service import embed
        embeds = _get_article_search_embeddings()
        if not embeds:
            return (True, 0.6)  # No embeddings loaded, assume search for substantive
        user_emb = embed(msg)
        sims = [_cosine_sim(user_emb, ex) for ex in embeds]
        max_sim = max(sims) if sims else 0.0
        return (max_sim >= 0.5, max_sim)
    except Exception:
        return (True, 0.6)  # On error, assume search for substantive messages


def extract_search_query(message: str) -> str | None:
    """
    Extract search query for live search. Always returns something for substantive messages.
    Used when we always run live search first - need a query.
    """
    msg = message.strip()
    if len(msg) < 10:
        return None
    # 1. Use regex entity extraction when patterns match
    entity = extract_company_or_topic(msg)
    if entity:
        return entity
    # 2. For substantive messages, use cleaned message as search query (always run search)
    words = [w.strip(".,:;?!") for w in msg.split()]
    skip = {"give", "me", "show", "get", "the", "a", "an", "list", "find", "search", "for", "about", "with", "their"}
    cleaned = " ".join(w for w in words if w.lower() not in skip and len(w) > 1)
    return cleaned[:120] if cleaned else msg[:120]


TRIGGER_PATTERNS = [
    r"\b(websites?|sites?|urls?|links?)\s+where\s+",
    r"\b(mentioned?|mentions?)\s+(in|on|of)\b",
    r"\b(top\s+)?(articles?|news|blogs?|posts?)\s+(about|on|mentioning)\b",
    r"\b(give|show|get)\s+me\s+(the\s+)?(top\s+)?articles?\s+about\b",
    r"\bmedia\s+coverage\b",
    r"\bwebsites?\s+referencing\b",
    r"\b(where|find|identify|get)\s+.*\s+(was|were)?\s*mentioned\b",
    r"\b(give\s+me|show\s+me|list|find)\s+.*\s+(websites?|urls?|links?|sites?|mentions?|articles?)\b",
    r"\b\d+\s+(websites?|urls?|sites?|articles?)\s+where\b",
    r"\b(recent|latest|most\s+recent)\s+(mentions?|articles?|news|coverage)\b",
    r"\bfind\s+.*\s+(mentions?|articles?|coverage)\b",
    r"\bsearch\s+for\s+.*\s+(mentions?|articles?)\b",
    r"\bmost\s+recent\s+mentions?\b",
]

# Simpler: message has a domain (X.com) or entity + any of these words
TRIGGER_WORDS = {"mention", "mentions", "mentioned", "article", "articles", "news", "website", "websites", "url", "urls", "link", "links", "coverage", "find", "search", "recent", "latest"}


def extract_company_or_topic(message: str) -> str | None:
    """Extract company/topic from message. Returns None if not a URL discovery request."""
    msg_lower = message.strip().lower()
    # Pattern-based
    for pat in TRIGGER_PATTERNS:
        if re.search(pat, msg_lower, re.I):
            entity = _extract_entity(message)
            if entity:
                return entity
    # Domain present (Sahi.com) + any trigger word
    if re.search(r"\b[a-zA-Z0-9][-a-zA-Z0-9]*\.(?:com|io|ai|co|org|net|in)\b", message):
        if any(w in msg_lower for w in TRIGGER_WORDS):
            return _extract_entity(message)
    # Domain only + "find|search|recent|mention|article|news" anywhere
    domain_match = re.search(r"\b([a-zA-Z0-9][-a-zA-Z0-9]*\.(?:com|io|ai|co|org|net|in))\b", message)
    if domain_match and re.search(r"\b(find|search|recent|mention|article|news|website|coverage)\b", msg_lower):
        return domain_match.group(1)
    return None


FOLLOW_UP_PATTERNS = [
    r"answer\s+(the\s+)?last\s+question",
    r"answer\s+to\s+(the\s+)?last\s+question",
    r"give\s+me\s+(the\s+)?answer\s+to\s+(the\s+)?last",
    r"answer\s+(my\s+)?(last|previous)\s+(question|query|request)",
    r"answer\s+that",
    r"give\s+me\s+(the\s+)?answer",
    r"what\s+about\s+that",
    r"do\s+that",
    r"search\s+(for\s+)?that",
    r"find\s+that",
    r"yes\s*[,.]?\s*do\s+it",
    r"go\s+ahead",
    r"please\s+(answer|search|find)",
]


RECALL_QUESTIONS_PATTERNS = [
    r"\brecall\s+(my\s+)?(last\s+)?(\d+\s+)?(questions?|messages?|queries?)\b",
    r"\blist\s+(of\s+)?(my\s+)?(last\s+)?(the\s+)?(questions?|messages?|queries?)(\s+asked)?\b",
    r"\b(the\s+)?list\s+of\s+questions?(\s+asked)?\b",
    r"\bquestions?\s+asked\b",
    r"\bgive\s+me\s+(the\s+)?list\s+(of\s+)?(questions?|messages?)\b",
    r"\bwhat\s+(were|are)\s+(my\s+)?(last\s+)?(questions?|messages?)\b",
    r"\b(my\s+)?last\s+(\d+\s+)?questions?\b",
    r"\bsummarize\s+(my\s+)?(questions?|messages?)\b",
]


def is_recall_questions_request(message: str) -> bool:
    """True if user asks to recall/list their previous questions."""
    m = message.strip().lower()
    return any(re.search(pat, m, re.I) for pat in RECALL_QUESTIONS_PATTERNS)


def is_follow_up_request(message: str) -> bool:
    """True if user is asking to answer/search the previous question."""
    m = message.strip().lower()
    if len(m) > 80:
        return False
    return any(re.search(p, m, re.I) for p in FOLLOW_UP_PATTERNS)


def extract_company_from_text(text: str) -> str | None:
    """Extract domain/company from any text (e.g. previous message)."""
    domain = re.search(r'\b([a-zA-Z0-9][-a-zA-Z0-9]*\.(?:com|io|ai|co|org|net|in))\b', text)
    return domain.group(1) if domain else None


def _extract_entity(message: str) -> str:
    """Extract company/topic - quoted text, domain-like (X.com), articles about X, or noun phrase."""
    quoted = re.findall(r'"([^"]+)"', message)
    if quoted:
        return quoted[0].strip()

    # "articles about X" / "top articles about X" / "news about X" -> extract X
    about_match = re.search(
        r'\b(?:top\s+)?(?:articles?|news|mentions?)\s+about\s+([^.?!]+?)(?:\s+and\s+|\s+with\s+|\s*$|\.)',
        message,
        re.I,
    )
    if about_match:
        entity = about_match.group(1).strip()
        if len(entity) > 2 and len(entity) < 100:
            return entity

    # Domain-like: Sahi.com, example.io
    domain = re.search(r'\b([a-zA-Z0-9][-a-zA-Z0-9]*\.(?:com|io|ai|co|org|net|in))\b', message)
    if domain:
        return domain.group(1)

    words = message.split()
    skip = {"where", "websites", "urls", "sites", "articles", "mentioned", "mention", "give", "me", "show", "list", "the", "a", "an", "in", "on", "about", "last", "month", "week", "year", "was", "were"}
    entity = []
    for w in words:
        wc = w.strip(".,:;?!")
        if wc.lower() in skip and not entity:
            continue
        if wc.lower() in ("where", "that", "which") and entity:
            break
        if re.match(r"^\d+$", wc) and not entity:
            continue
        entity.append(wc)
        if len(entity) >= 5:
            break
    return " ".join(entity).strip() if entity else message[:80]
