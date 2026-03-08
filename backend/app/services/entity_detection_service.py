"""Entity alias detection — improve accuracy, avoid Hindi false positives."""
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from app.config import get_config

_entity_map: dict[str, list[str]] | None = None
_ignore_patterns: list[str] = []


def _load_clients_sync() -> list[dict[str, Any]]:
    """Load clients from file (sync, no Redis cache)."""
    project_root = Path(__file__).resolve().parent.parent.parent
    config_dir = project_root / "config"
    if not config_dir.exists():
        config_dir = Path("/app/config")
    path = config_dir / "clients.yaml"
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("clients", [])


def _build_entity_map() -> tuple[dict[str, list[str]], list[str]]:
    """Build entity -> aliases map from clients and monitoring config."""
    clients = _load_clients_sync()

    config = get_config()
    mon = config.get("monitoring", {})
    ed = mon.get("entity_detection", {})
    global_aliases = ed.get("entity_aliases", {})
    if isinstance(global_aliases, dict):
        global_aliases = {k: v if isinstance(v, list) else [] for k, v in global_aliases.items()}
    else:
        global_aliases = {}

    entity_map: dict[str, list[str]] = {}
    entities_seen: set[str] = set()

    for c in clients:
        name = (c.get("name") or "").strip()
        if name:
            aliases = c.get("aliases")
            if isinstance(aliases, list):
                entity_map[name] = [str(a).strip().lower() for a in aliases if a]
            else:
                alist = global_aliases.get(name)
                entity_map[name] = [a.strip().lower() for a in (alist if isinstance(alist, list) else [name]) if a]
            if name not in entity_map[name]:
                entity_map[name].insert(0, name.lower())
            entities_seen.add(name)
        for comp in c.get("competitors") or []:
            if comp and isinstance(comp, str):
                comp = comp.strip()
                if comp and comp not in entities_seen:
                    alist = global_aliases.get(comp)
                    entity_map[comp] = [a.strip().lower() for a in (alist if isinstance(alist, list) else [comp]) if a]
                    if comp.lower() not in entity_map[comp]:
                        entity_map[comp].insert(0, comp.lower())
                    entities_seen.add(comp)

    ignore = ed.get("ignore_patterns", [])
    ignore = [p.strip().lower() for p in ignore if p] if isinstance(ignore, list) else []

    return entity_map, ignore


def _get_entity_map() -> tuple[dict[str, list[str]], list[str]]:
    global _entity_map, _ignore_patterns
    if _entity_map is None:
        _entity_map, _ignore_patterns = _build_entity_map()
    return _entity_map, _ignore_patterns


def detect_entity(text: str) -> Optional[str]:
    """
    Detect canonical entity from text using aliases.
    Returns None if text matches ignore_patterns (e.g. conversational Hindi).
    """
    if not text or not isinstance(text, str):
        return None
    normalized = text.strip().lower()
    if not normalized:
        return None

    entity_map, ignore_patterns = _get_entity_map()

    for pat in ignore_patterns:
        if pat and re.search(r"\b" + re.escape(pat) + r"\b", normalized):
            return None

    best_entity: Optional[str] = None
    best_len = 0

    for entity, aliases in entity_map.items():
        for alias in aliases:
            if not alias:
                continue
            if alias in normalized:
                if len(alias) > best_len:
                    best_len = len(alias)
                    best_entity = entity

    return best_entity


def get_entities_and_aliases() -> dict[str, list[str]]:
    """Return entity -> aliases map for external use (e.g. Reddit/YouTube search)."""
    entity_map, _ = _get_entity_map()
    return dict(entity_map)
