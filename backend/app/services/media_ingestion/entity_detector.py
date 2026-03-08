"""Entity detector - keyword-based detection of monitored companies."""
import re

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_ENTITIES = ["Sahi", "Zerodha", "Upstox"]


def _load_entities() -> list[str]:
    cfg = get_config().get("media_ingestion", get_config().get("media_index", {}))
    return cfg.get("monitored_entities", DEFAULT_ENTITIES)


def detect_entities(text: str, entities: list[str] | None = None) -> list[str]:
    """Detect which monitored entities are mentioned in text. Returns list of detected names."""
    if not text:
        return []
    if entities is None:
        entities = _load_entities()
    text_lower = text.lower()
    found = []
    for e in entities:
        if not e:
            continue
        if e.lower() in text_lower:
            found.append(e)
        elif re.search(rf"\b{re.escape(e)}\b", text_lower, re.I):
            found.append(e)
    return list(dict.fromkeys(found))
