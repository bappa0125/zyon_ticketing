"""
Narrative tags config loader + fail-fast validator.

Single source of truth: config/narrative_tags.yaml

Validation rules (fail fast):
- unknown parent references
- self-parent references
- cycle detection in domain_tags.parents graph
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from app.core.logging import get_logger
from app.core.vertical_config_bundle import resolve_bundled_config_file

logger = get_logger(__name__)


@dataclass(frozen=True)
class NarrativeTagsConfig:
    raw: dict[str, Any]

    def vertical_block(self, vertical: str) -> dict[str, Any]:
        v = (vertical or "").strip().lower()
        root = self.raw.get("verticals") if isinstance(self.raw.get("verticals"), dict) else {}
        block = root.get(v) if isinstance(root, dict) else None
        return block if isinstance(block, dict) else {}

    def behavior_tags(self, vertical: str) -> dict[str, Any]:
        b = self.vertical_block(vertical).get("behavior_tags")
        return b if isinstance(b, dict) else {}

    def domain_tags(self, vertical: str) -> dict[str, Any]:
        d = self.vertical_block(vertical).get("domain_tags")
        return d if isinstance(d, dict) else {}


_CACHE: tuple[str, float, NarrativeTagsConfig] | None = None


def _load_yaml() -> NarrativeTagsConfig:
    global _CACHE
    path = resolve_bundled_config_file("narrative_tags.yaml")
    path_key = str(path.resolve())
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = -1.0
    if _CACHE and _CACHE[0] == path_key and _CACHE[1] == mtime:
        return _CACHE[2]
    if not path.exists():
        raise RuntimeError(f"Missing narrative tags config: {path}")
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        raise RuntimeError(f"Failed to parse narrative_tags.yaml: {e}") from e
    cfg = NarrativeTagsConfig(raw=data if isinstance(data, dict) else {})
    _CACHE = (path_key, mtime, cfg)
    return cfg


def get_narrative_tags_config() -> NarrativeTagsConfig:
    return _load_yaml()


def _domain_parent_map(domain_tags: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for tid, meta in (domain_tags or {}).items():
        if not isinstance(tid, str) or not tid.strip():
            continue
        parents = []
        if isinstance(meta, dict):
            p = meta.get("parents")
            if isinstance(p, list):
                parents = [str(x).strip() for x in p if isinstance(x, str) and str(x).strip()]
        out[tid.strip()] = parents
    return out


def _validate_domain_hierarchy(domain_tags: dict[str, Any], *, vertical: str) -> None:
    domain_ids = {str(k).strip() for k in (domain_tags or {}).keys() if isinstance(k, str) and str(k).strip()}
    parent_map = _domain_parent_map(domain_tags)

    # Unknown parent + self-parent checks
    for tid, parents in parent_map.items():
        for p in parents:
            if p == tid:
                raise RuntimeError(f"Invalid narrative_tags.yaml: domain tag '{tid}' lists itself as parent (vertical={vertical})")
            if p not in domain_ids:
                raise RuntimeError(
                    f"Invalid narrative_tags.yaml: domain tag '{tid}' references unknown parent '{p}' (vertical={vertical})"
                )

    # Cycle detection (DFS with recursion stack)
    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node: str, chain: list[str]) -> None:
        if node in visited:
            return
        if node in visiting:
            # cycle found
            cycle = " -> ".join(chain + [node])
            raise RuntimeError(f"Invalid narrative_tags.yaml: cycle detected in domain parents graph (vertical={vertical}): {cycle}")
        visiting.add(node)
        for p in parent_map.get(node, []):
            dfs(p, chain + [node])
        visiting.remove(node)
        visited.add(node)

    for tid in sorted(domain_ids):
        dfs(tid, [])


def validate_narrative_tags_config_or_raise() -> None:
    """
    Fail-fast validator invoked on backend startup.
    """
    cfg = get_narrative_tags_config()
    root = cfg.raw.get("verticals")
    if not isinstance(root, dict) or not root:
        raise RuntimeError("Invalid narrative_tags.yaml: missing 'verticals' root block")

    for v, block in root.items():
        if not isinstance(v, str) or not v.strip():
            raise RuntimeError("Invalid narrative_tags.yaml: vertical key must be a non-empty string")
        if not isinstance(block, dict):
            raise RuntimeError(f"Invalid narrative_tags.yaml: vertical '{v}' must be an object")

        behavior = block.get("behavior_tags")
        if not isinstance(behavior, dict) or not behavior:
            raise RuntimeError(f"Invalid narrative_tags.yaml: vertical '{v}' missing behavior_tags")
        if "unclassified_behavior" not in behavior:
            raise RuntimeError(f"Invalid narrative_tags.yaml: vertical '{v}' must include behavior tag 'unclassified_behavior'")

        domain = block.get("domain_tags")
        if not isinstance(domain, dict):
            raise RuntimeError(f"Invalid narrative_tags.yaml: vertical '{v}' domain_tags must be an object (can be empty)")

        _validate_domain_hierarchy(domain, vertical=v)

    logger.info("narrative_tags_config_validated", verticals=list(root.keys()))

