"""Multi-layer entity detection: ignore → alias → regex → NER → embedding/LLM fallback."""
import hashlib
import re
from typing import Any, NamedTuple, Optional

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

# Confidence by detection layer (for entity_mentions)
CONFIDENCE_ALIAS = 0.95
CONFIDENCE_REGEX = 0.85
CONFIDENCE_NER = 0.75
CONFIDENCE_EMBEDDING = 0.70
CONFIDENCE_LLM = 0.65

# Detection source values for entity_mentions.detected_by
DETECTED_BY_ALIAS = "alias"
DETECTED_BY_REGEX = "regex"
DETECTED_BY_NER = "ner"
DETECTED_BY_EMBEDDING = "embedding"
DETECTED_BY_LLM = "llm"

# Finance context keywords — embedding/LLM fallback only when text contains these
FINANCE_CONTEXT_KEYWORDS = (
    "trading",
    "broker",
    "demat",
    "stock app",
    "derivatives",
    "investment platform",
)

# Minimum cosine similarity to consider text "about" an entity (embedding layer)
EMBEDDING_ENTITY_THRESHOLD = 0.42

# LLM cache: max in-memory entries when Redis not used
_LLM_CACHE_MAX_SIZE = 2000

_entity_map: dict[str, list[str]] | None = None
_ignore_patterns: list[str] = []
# Precompiled alias lookup: list of (alias_lower, entity) sorted by alias length desc for longest match
_alias_lookup: list[tuple[str, str]] = []
_entity_regex: Optional[re.Pattern[str]] = None
_entity_to_canonical: dict[str, str] = {}  # normalized name/alias -> canonical entity
_nlp = None  # spaCy model, lazy-loaded
_llm_cache: dict[str, Optional[str]] = {}  # article_url_hash -> entity or None
_llm_cache_keys: list[str] = []  # FIFO for eviction


class EntityDetectionResult(NamedTuple):
    """Result for entity_mentions: entity name, confidence score, detection source."""

    entity: Optional[str]
    confidence: float
    detected_by: str  # alias | regex | ner | embedding | llm


def _load_clients_sync() -> list[dict[str, Any]]:
    """Load clients from the same file as the API (clients.yaml or executive file when enabled)."""
    from app.core.client_config_loader import load_clients_sync

    return load_clients_sync()


def _build_entity_map() -> tuple[dict[str, list[str]], list[str], list[tuple[str, str]]]:
    """Build entity -> aliases (lowercase), ignore patterns, and precompiled alias lookup from active clients config."""
    clients = _load_clients_sync()

    entity_map: dict[str, list[str]] = {}
    entities_seen: set[str] = set()
    ignore_set: set[str] = set()

    for c in clients:
        name = (c.get("name") or "").strip()
        for p in c.get("ignore_patterns") or []:
            if p and isinstance(p, str):
                ignore_set.add(p.strip().lower())
        if name:
            aliases = c.get("aliases")
            if isinstance(aliases, list):
                entity_map[name] = [str(a).strip().lower() for a in aliases if a]
            else:
                entity_map[name] = [name.lower()]
            if name.lower() not in entity_map[name]:
                entity_map[name].insert(0, name.lower())
            entities_seen.add(name)
        for comp in c.get("competitors") or []:
            comp_name = (comp.get("name") or "").strip() if isinstance(comp, dict) else (comp or "").strip() if isinstance(comp, str) else ""
            if not comp_name:
                continue
            if comp_name not in entities_seen:
                if isinstance(comp, dict) and isinstance(comp.get("aliases"), list):
                    entity_map[comp_name] = [str(a).strip().lower() for a in comp["aliases"] if a]
                else:
                    entity_map[comp_name] = [comp_name.lower()]
                if comp_name.lower() not in entity_map[comp_name]:
                    entity_map[comp_name].insert(0, comp_name.lower())
                entities_seen.add(comp_name)
            for p in (comp.get("ignore_patterns") or []) if isinstance(comp, dict) else []:
                if p and isinstance(p, str):
                    ignore_set.add(p.strip().lower())

    ignore = sorted(ignore_set)

    # Precompiled alias lookup: (alias_lower, entity) sorted by alias length desc for longest match
    alias_pairs: list[tuple[str, str]] = []
    for entity, aliases in entity_map.items():
        for a in aliases:
            if a:
                alias_pairs.append((a, entity))
    alias_pairs.sort(key=lambda x: -len(x[0]))
    return entity_map, ignore, alias_pairs


def _get_entity_map() -> tuple[dict[str, list[str]], list[str]]:
    global _entity_map, _ignore_patterns, _alias_lookup
    if _entity_map is None:
        _entity_map, _ignore_patterns, _alias_lookup = _build_entity_map()
    return _entity_map, _ignore_patterns


def _get_entity_regex() -> tuple[Optional[re.Pattern[str]], dict[str, str]]:
    """Build regex of canonical entity names (word boundary) and map normalized->canonical."""
    global _entity_regex, _entity_to_canonical
    entity_map, _ = _get_entity_map()
    if not entity_map:
        return None, {}
    if _entity_regex is not None:
        return _entity_regex, _entity_to_canonical
    # Sort by length descending so longer names match first (e.g. "Angel One" before "Angel")
    names = sorted(entity_map.keys(), key=lambda x: -len(x))
    pattern = r"\b(" + "|".join(re.escape(n) for n in names) + r")\b"
    _entity_regex = re.compile(pattern, re.IGNORECASE)
    for entity, aliases in entity_map.items():
        _entity_to_canonical[entity.lower()] = entity
        for a in aliases:
            if a:
                _entity_to_canonical[a] = entity
    return _entity_regex, _entity_to_canonical


def _layer1_ignore(text: str) -> bool:
    """Layer 1: if text matches any ignore pattern, return True (skip detection)."""
    entity_map, ignore_patterns = _get_entity_map()
    normalized = text.strip().lower()
    if not normalized:
        return True
    for pat in ignore_patterns:
        if pat and re.search(r"\b" + re.escape(pat) + r"\b", normalized):
            return True
    return False


def _layer2_alias(text: str) -> Optional[str]:
    """Layer 2: precompiled alias lookup (longest match first). Case-insensitive."""
    _get_entity_map()
    normalized = text.strip().lower()
    if not normalized:
        return None
    for alias, entity in _alias_lookup:
        if alias in normalized:
            return entity
    return None


def _layer2_alias_all(text: str) -> list[str]:
    """Layer 2: return all entities whose alias appears in text. Case-insensitive."""
    _get_entity_map()
    normalized = text.strip().lower()
    if not normalized:
        return []
    found: set[str] = set()
    for alias, entity in _alias_lookup:
        if alias in normalized:
            found.add(entity)
    return list(found)


def _layer3_regex(text: str) -> Optional[str]:
    """Layer 3: regex match for canonical entity names (broker/trading references)."""
    regex, to_canonical = _get_entity_regex()
    if not regex or not text:
        return None
    m = regex.search(text)
    if not m:
        return None
    key = m.group(1).lower()
    return to_canonical.get(key)


def _layer3_regex_all(text: str) -> list[str]:
    """Layer 3: return all entities matched by regex in text (finditer)."""
    regex, to_canonical = _get_entity_regex()
    if not regex or not text:
        return []
    found: set[str] = set()
    for m in regex.finditer(text):
        key = m.group(1).lower()
        entity = to_canonical.get(key)
        if entity:
            found.add(entity)
    return list(found)


def _layer4_ner(text: str) -> Optional[str]:
    """Layer 4: NER (spaCy) — match ORG entities to monitored list."""
    entity_map, _ = _get_entity_map()
    if not entity_map or not text or not text.strip():
        return None
    try:
        import spacy
    except ImportError:
        return None
    global _nlp
    if _nlp is None:
        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            try:
                _nlp = spacy.load("en_core_web_sm", disable=["parser"])
            except OSError:
                logger.debug("entity_detection_ner_spacy_not_available")
                return None
    doc = _nlp(text[:100000])
    to_canonical: dict[str, str] = {}
    for entity, aliases in entity_map.items():
        to_canonical[entity.lower()] = entity
        for a in aliases:
            if a:
                to_canonical[a] = entity
    for ent in doc.ents:
        if ent.label_ != "ORG":
            continue
        key = ent.text.strip().lower()
        if not key:
            continue
        if key in to_canonical:
            return to_canonical[key]
        for entity, aliases in entity_map.items():
            if key in aliases:
                return entity
    return None


def _layer4_ner_all(text: str) -> list[str]:
    """Layer 4: return all ORG entities from NER that match monitored list."""
    entity_map, _ = _get_entity_map()
    if not entity_map or not text or not text.strip():
        return []
    try:
        import spacy
    except ImportError:
        return []
    global _nlp
    if _nlp is None:
        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            try:
                _nlp = spacy.load("en_core_web_sm", disable=["parser"])
            except OSError:
                logger.debug("entity_detection_ner_spacy_not_available")
                return []
    doc = _nlp(text[:100000])
    to_canonical: dict[str, str] = {}
    for entity, aliases in entity_map.items():
        to_canonical[entity.lower()] = entity
        for a in aliases:
            if a:
                to_canonical[a] = entity
    found: set[str] = set()
    for ent in doc.ents:
        if ent.label_ != "ORG":
            continue
        key = ent.text.strip().lower()
        if not key:
            continue
        if key in to_canonical:
            found.add(to_canonical[key])
        else:
            for entity, aliases in entity_map.items():
                if key in aliases:
                    found.add(entity)
                    break
    return list(found)


def _has_finance_context(text: str) -> bool:
    """True if text contains any finance-related context keyword."""
    lower = text.strip().lower()
    return any(kw in lower for kw in FINANCE_CONTEXT_KEYWORDS)


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


def _layer5_embedding(text: str) -> Optional[str]:
    """
    Layer 5: embedding-based fallback. Uses existing embedding model (e.g. SentenceTransformers).
    Embed text and 'article about [Entity]' for each entity; return entity with max similarity
    above threshold if finance context. No OpenRouter/LLM call.
    """
    entity_map, _ = _get_entity_map()
    if not entity_map or not text or not text.strip():
        return None
    if not _has_finance_context(text):
        return None
    try:
        from app.services.embedding_service import embed
    except ImportError:
        return None
    text_snippet = text[:4000].strip()
    text_vec = embed(text_snippet)
    best_entity: Optional[str] = None
    best_sim = 0.0
    for entity in entity_map.keys():
        query = f"article or news about {entity} broker trading"
        ent_vec = embed(query)
        sim = _cosine_sim(text_vec, ent_vec)
        if sim > best_sim and sim >= EMBEDDING_ENTITY_THRESHOLD:
            best_sim = sim
            best_entity = entity
    return best_entity


def _detect_entity_sync_with_metadata(
    text: str,
    stats: Optional[dict[str, int]] = None,
) -> EntityDetectionResult:
    """Sync detection layers 1–4; returns entity, confidence, detected_by for entity_mentions."""
    if stats is None:
        stats = {}
    empty = EntityDetectionResult(entity=None, confidence=0.0, detected_by="")
    if not text or not isinstance(text, str):
        return empty
    if _layer1_ignore(text):
        return empty

    entity = _layer2_alias(text)
    if entity is not None:
        stats["by_alias"] = stats.get("by_alias", 0) + 1
        logger.debug("entity_detection_stage", stage=DETECTED_BY_ALIAS, entity=entity)
        return EntityDetectionResult(entity=entity, confidence=CONFIDENCE_ALIAS, detected_by=DETECTED_BY_ALIAS)

    entity = _layer3_regex(text)
    if entity is not None:
        stats["by_regex"] = stats.get("by_regex", 0) + 1
        logger.debug("entity_detection_stage", stage=DETECTED_BY_REGEX, entity=entity)
        return EntityDetectionResult(entity=entity, confidence=CONFIDENCE_REGEX, detected_by=DETECTED_BY_REGEX)

    entity = _layer4_ner(text)
    if entity is not None:
        stats["by_ner"] = stats.get("by_ner", 0) + 1
        logger.debug("entity_detection_stage", stage=DETECTED_BY_NER, entity=entity)
        return EntityDetectionResult(entity=entity, confidence=CONFIDENCE_NER, detected_by=DETECTED_BY_NER)

    return empty


def detect_entity(
    text: str,
    stats: Optional[dict[str, int]] = None,
    with_metadata: bool = False,
) -> Optional[str] | EntityDetectionResult:
    """
    Multi-layer detection (sync): ignore → alias → regex → NER. No LLM.
    Returns canonical entity or None (or EntityDetectionResult when with_metadata=True).
    If stats is provided, increments by_alias, by_regex, by_ner.
    """
    result = _detect_entity_sync_with_metadata(text, stats=stats)
    if with_metadata:
        return result
    return result.entity


def detect_entities(text: str) -> list[str]:
    """
    Return all entities mentioned in text (alias + regex + NER). No LLM.
    Same layers as detect_entity but collects every match. Deduped, stable order.
    """
    if not text or not isinstance(text, str):
        return []
    if _layer1_ignore(text):
        return []
    found: set[str] = set()
    for entity in _layer2_alias_all(text):
        found.add(entity)
    for entity in _layer3_regex_all(text):
        found.add(entity)
    for entity in _layer4_ner_all(text):
        found.add(entity)
    return sorted(found)


def _article_url_hash(article_url: str) -> str:
    """Stable hash for LLM cache key."""
    return hashlib.sha256(article_url.strip().encode("utf-8")).hexdigest()[:32]


def _llm_cache_get(article_url: str) -> tuple[bool, Optional[str]]:
    """Get cached LLM result (in-memory). Returns (hit, entity). hit=True with entity=None means cached no-entity."""
    global _llm_cache
    key = _article_url_hash(article_url)
    if key not in _llm_cache:
        return (False, None)
    return (True, _llm_cache[key])


def _llm_cache_set(article_url: str, entity: Optional[str]) -> None:
    """Store LLM result in-memory (including None for no-entity); evict oldest if over capacity."""
    global _llm_cache, _llm_cache_keys
    key = _article_url_hash(article_url)
    if key in _llm_cache:
        return
    while len(_llm_cache) >= _LLM_CACHE_MAX_SIZE and _llm_cache_keys:
        old = _llm_cache_keys.pop(0)
        _llm_cache.pop(old, None)
    _llm_cache[key] = entity
    _llm_cache_keys.append(key)


async def _llm_cache_get_redis(article_url: str) -> tuple[bool, Optional[str]]:
    """Get from Redis if available. Returns (hit, entity): hit=False means miss; hit=True, entity=None means cached no-entity."""
    try:
        from app.services.redis_client import get_redis
        r = await get_redis()
        key = f"entity_detection_llm:{_article_url_hash(article_url)}"
        val = await r.get(key)
        if val is None:
            return (False, None)
        return (True, None if val == "__NONE__" else val)
    except Exception:
        return (False, None)


async def _llm_cache_set_redis(article_url: str, entity: Optional[str], ttl_seconds: int = 86400) -> None:
    """Store in Redis if available. Use __NONE__ for no-entity so we can distinguish from cache miss."""
    try:
        from app.services.redis_client import get_redis
        r = await get_redis()
        key = f"entity_detection_llm:{_article_url_hash(article_url)}"
        await r.setex(key, ttl_seconds, "__NONE__" if entity is None else entity)
    except Exception:
        pass


async def detect_entity_async(
    text: str,
    stats: Optional[dict[str, int]] = None,
    with_metadata: bool = False,
    article_url: Optional[str] = None,
) -> Optional[str] | EntityDetectionResult:
    """
    Full pipeline including Layer 5: embedding then optional LLM. Use for article_documents pipeline.
    When article_url is provided, LLM result is cached (Redis or in-memory) to avoid duplicate calls.
    Returns entity or EntityDetectionResult when with_metadata=True.
    """
    if stats is None:
        stats = {}

    result = _detect_entity_sync_with_metadata(text, stats=stats)
    if result.entity is not None:
        if with_metadata:
            return result
        return result.entity

    if not _has_finance_context(text):
        if with_metadata:
            return EntityDetectionResult(entity=None, confidence=0.0, detected_by="")
        return None

    entity = _layer5_embedding(text)
    if entity is not None:
        stats["by_embedding"] = stats.get("by_embedding", 0) + 1
        logger.debug("entity_detection_stage", stage=DETECTED_BY_EMBEDDING, entity=entity)
        if with_metadata:
            return EntityDetectionResult(entity=entity, confidence=CONFIDENCE_EMBEDDING, detected_by=DETECTED_BY_EMBEDDING)
        return entity

    config = get_config()
    use_llm = (
        config.get("monitoring", {})
        .get("entity_detection", {})
        .get("use_llm_fallback", False)
    )
    if not use_llm:
        if with_metadata:
            return EntityDetectionResult(entity=None, confidence=0.0, detected_by="")
        return None

    entity_map, _ = _get_entity_map()
    entity_list = sorted(entity_map.keys())
    if not entity_list:
        if with_metadata:
            return EntityDetectionResult(entity=None, confidence=0.0, detected_by="")
        return None

    # LLM cache: reuse result for same article (Redis first, then in-memory)
    if article_url:
        hit, cached_entity = await _llm_cache_get_redis(article_url)
        if not hit:
            hit, cached_entity = _llm_cache_get(article_url)
        if hit:
            if cached_entity is not None:
                stats["by_llm"] = stats.get("by_llm", 0) + 1
            if with_metadata:
                return EntityDetectionResult(entity=cached_entity, confidence=CONFIDENCE_LLM if cached_entity else 0.0, detected_by=DETECTED_BY_LLM if cached_entity else "")
            return cached_entity

    prompt = (
        "Identify if the text mentions any of these companies: "
        + ", ".join(entity_list)
        + ". Return only the company names mentioned, one per line, or NONE if none."
    )
    try:
        from app.services.llm_gateway import LLMGateway

        gateway = LLMGateway()
        if not gateway.api_key:
            if with_metadata:
                return EntityDetectionResult(entity=None, confidence=0.0, detected_by="")
            return None
        messages = [
            {"role": "system", "content": "You answer with only company names or NONE. No explanation."},
            {"role": "user", "content": f"Text:\n{text[:8000]}\n\n{prompt}"},
        ]
        collected: list[str] = []
        async for chunk in gateway.chat_completion(messages, stream=True):
            if isinstance(chunk, str) and not chunk.startswith("{"):
                collected.append(chunk)
        response = "".join(collected).strip().upper()
        entity = None
        if "NONE" not in response or len(response) >= 50:
            for name in entity_list:
                if name.upper() in response or name in response:
                    entity = name
                    break
        if article_url:
            await _llm_cache_set_redis(article_url, entity)
            _llm_cache_set(article_url, entity)
        if entity is not None:
            stats["by_llm"] = stats.get("by_llm", 0) + 1
            logger.debug("entity_detection_stage", stage=DETECTED_BY_LLM, entity=entity)
            if with_metadata:
                return EntityDetectionResult(entity=entity, confidence=CONFIDENCE_LLM, detected_by=DETECTED_BY_LLM)
            return entity
    except Exception as e:
        logger.warning("entity_detection_llm_fallback_failed", error=str(e))
    if with_metadata:
        return EntityDetectionResult(entity=None, confidence=0.0, detected_by="")
    return None


def get_entities_and_aliases() -> dict[str, list[str]]:
    """Return entity -> aliases map for external use (e.g. Reddit/YouTube search)."""
    entity_map, _ = _get_entity_map()
    return dict(entity_map)


def ensure_initialized() -> None:
    """Precompile alias dictionary and regex at service start. Call once at startup."""
    _get_entity_map()
    _get_entity_regex()


def detect_entity_with_metadata(
    text: str,
    stats: Optional[dict[str, int]] = None,
) -> EntityDetectionResult:
    """Sync detection; returns EntityDetectionResult (entity, confidence, detected_by) for entity_mentions."""
    return _detect_entity_sync_with_metadata(text, stats=stats)


def log_detection_run_stats(stats: dict[str, Any]) -> None:
    """Log detection stage statistics for a batch run. Call after processing many texts."""
    if not stats:
        return
    articles_scanned = stats.get("articles_scanned", 0)
    alias_matches = stats.get("by_alias", 0)
    regex_matches = stats.get("by_regex", 0)
    ner_matches = stats.get("by_ner", 0)
    llm_matches = stats.get("by_llm", 0)
    logger.info(
        "entity_detection_run_stats",
        articles_scanned=articles_scanned,
        alias_matches=alias_matches,
        regex_matches=regex_matches,
        ner_matches=ner_matches,
        llm_matches=llm_matches,
        by_embedding=stats.get("by_embedding", 0),
    )
    logger.info(
        "entity_detection_batch_summary",
        msg=(
            f"Articles scanned: {articles_scanned} | "
            f"Alias matches: {alias_matches} | "
            f"Regex matches: {regex_matches} | "
            f"NER matches: {ner_matches} | "
            f"LLM fallback matches: {llm_matches}"
        ),
    )
