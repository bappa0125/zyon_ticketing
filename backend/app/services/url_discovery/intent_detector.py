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


# Greetings and casual phrases - do NOT trigger article search
GREETING_PATTERNS = [
    r"^\s*(hi|hello|hey|hola|yo)\s*[!.,]?\s*$",
    r"^\s*(hi|hello|hey)\s+(how\s+are\s+you|how\s+r\s+u|how\s+do\s+you\s+do)\s*[!.,]?\s*$",
    r"^\s*how\s+are\s+you\s*[!.,]?\s*$",
    r"^\s*what'?s?\s+up\s*[!.,]?\s*$",
    r"^\s*how'?s?\s+it\s+going\s*[!.,]?\s*$",
    r"^\s*how\s+are\s+things\s*[!.,]?\s*$",
    r"^\s*good\s+(morning|afternoon|evening)\s*[!.,]?\s*$",
    r"^\s*(hey\s+)?there\s*[!.,]?\s*$",
    r"^\s*supp?\s*[!.,]?\s*$",
]

GREETING_PHRASES = {
    "hi", "hello", "hey", "hola", "yo", "howdy",
    "hi how are you", "hello how are you", "hey how are you",
    "how are you", "how r u", "how do you do", "how r u doing",
    "whats up", "what's up", "whats good",
    "hows it going", "how's it going", "how are things",
    "good morning", "good afternoon", "good evening",
    "hi there", "hello there", "hey there",
}


def is_greeting_or_casual(message: str) -> bool:
    """True if message is a greeting or casual small talk - do NOT run article search."""
    msg = message.strip().lower()
    if len(msg) < 3:
        return True
    if msg in GREETING_PHRASES:
        return True
    norm = re.sub(r"[!.,?]+", "", msg)
    if norm in GREETING_PHRASES:
        return True
    if any(re.match(pat, msg, re.I) for pat in GREETING_PATTERNS):
        return True
    # Short messages that are mostly greetings
    words = set(w.strip(".,!?") for w in msg.split())
    if words <= {"hi", "hello", "hey", "how", "are", "you", "doing", "fine", "good"}:
        return True
    return False


def extract_search_query(message: str) -> str | None:
    """
    Extract search query for live search. Always returns something for substantive messages.
    Do NOT return a query for greetings or casual phrases.
    """
    msg = message.strip()
    if len(msg) < 10:
        return None
    if is_greeting_or_casual(msg):
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
    r"\b(latest|recent)\s+results?\s+(on|about)\b",
    r"\bgive\s+me\s+(the\s+)?(latest|recent)\s+results?\s+(on|about)\b",
    r"\bfind\s+.*\s+(mentions?|articles?|coverage)\b",
    r"\bsearch\s+for\s+.*\s+(mentions?|articles?)\b",
    r"\bmost\s+recent\s+mentions?\b",
]

# Simpler: message has a domain (X.com) or entity + any of these words
TRIGGER_WORDS = {"mention", "mentions", "mentioned", "article", "articles", "news", "website", "websites", "url", "urls", "link", "links", "coverage", "find", "search", "recent", "latest", "result", "results"}


def extract_company_or_topic(message: str) -> str | None:
    """Extract company/topic from message. Resolves aliases (e.g. 'grow app' -> Groww)."""
    msg_lower = message.strip().lower()
    raw_entity: str | None = None
    # Pattern-based
    for pat in TRIGGER_PATTERNS:
        if re.search(pat, msg_lower, re.I):
            raw_entity = _extract_entity(message)
            break
    if raw_entity is None:
        # Domain present (Sahi.com) + any trigger word
        if re.search(r"\b[a-zA-Z0-9][-a-zA-Z0-9]*\.(?:com|io|ai|co|org|net|in)\b", message):
            if any(w in msg_lower for w in TRIGGER_WORDS):
                raw_entity = _extract_entity(message)
    if raw_entity is None:
        # Domain only + "find|search|recent|mention|article|news" anywhere
        domain_match = re.search(r"\b([a-zA-Z0-9][-a-zA-Z0-9]*\.(?:com|io|ai|co|org|net|in))\b", message)
        if domain_match and re.search(r"\b(find|search|recent|mention|article|news|website|coverage)\b", msg_lower):
            return domain_match.group(1)
    if not raw_entity:
        return None
    # Resolve via known entities (e.g. "grow app" -> Groww)
    try:
        from app.services.entity_detection_service import detect_entity
        canonical = detect_entity(message)
        if canonical:
            return canonical
    except Exception:
        pass
    return raw_entity


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


# Suggested prompts - shown when user asks something out of scope
SUGGESTED_PROMPTS = [
    "Give me the latest articles about Sahi",
    "Give me the latest result on Sahi app",
    "Show me recent mentions of Zerodha",
    "Find articles about Upstox",
    "Latest news on Groww",
    "Search for mentions of Sahi trading app",
]


def get_out_of_scope_message() -> str:
    """Return message telling user what phrases to ask. No search, no LLM."""
    lines = [
        "I can only help with **articles and mentions** about monitored companies (Sahi, Zerodha, Upstox, Groww).",
        "",
        "**Try asking:**",
    ]
    for p in SUGGESTED_PROMPTS:
        lines.append(f"- {p}")
    lines.append("")
    lines.append("_I don't run general web search or answer random questions._")
    return "\n".join(lines)


def is_in_scope_for_search(message: str) -> bool:
    """
    True ONLY when message clearly asks for articles/mentions about a company.
    Random questions, greetings, general knowledge -> False. No search.
    """
    if is_greeting_or_casual(message):
        return False
    company = extract_company_or_topic(message)
    return company is not None


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

    # "latest news on X" / "news on X" / "articles on X"
    on_match = re.search(
        r'\b(?:latest|recent|top\s+)?(?:news|articles?|mentions?)\s+on\s+([^.?!]+?)(?:\s+and\s+|\s+with\s+|\s*$|\.)',
        message,
        re.I,
    )
    if on_match:
        entity = on_match.group(1).strip()
        if len(entity) > 2 and len(entity) < 100:
            return entity

    # "latest result on X" / "recent results about X"
    result_match = re.search(
        r'\b(?:latest|recent)\s+results?\s+(?:on|about)\s+([^.?!]+?)(?:\s+and\s+|\s+with\s+|\s*$|\.)',
        message,
        re.I,
    )
    if result_match:
        entity = result_match.group(1).strip()
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
