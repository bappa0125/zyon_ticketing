from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from app.core.vertical_config_bundle import resolve_bundled_config_file


@dataclass(frozen=True)
class Company:
    name: str
    slug: str


_CACHE: tuple[str, float, dict[str, Company], dict[str, Company]] | None = None


def _load() -> tuple[dict[str, Company], dict[str, Company]]:
    global _CACHE
    path = resolve_bundled_config_file("companies.yaml")
    path_key = str(path.resolve())
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = -1.0
    if _CACHE and _CACHE[0] == path_key and _CACHE[1] == mtime:
        return _CACHE[2], _CACHE[3]
    if not path.exists():
        raise RuntimeError(f"Missing companies config: {path}")
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    root = data.get("companies") if isinstance(data, dict) else None
    if not isinstance(root, list) or not root:
        raise RuntimeError("Invalid companies.yaml: missing companies list")
    by_slug: dict[str, Company] = {}
    by_name: dict[str, Company] = {}
    for row in root:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        slug = str(row.get("slug") or "").strip().lower()
        if not name or not slug:
            raise RuntimeError("Invalid companies.yaml: each company requires name and slug")
        if slug in by_slug:
            raise RuntimeError(f"Invalid companies.yaml: duplicate slug '{slug}'")
        comp = Company(name=name, slug=slug)
        by_slug[slug] = comp
        nk = name.strip().lower()
        if nk in by_name:
            raise RuntimeError(f"Invalid companies.yaml: duplicate name '{name}' (case-insensitive)")
        by_name[nk] = comp
    _CACHE = (path_key, mtime, by_slug, by_name)
    return by_slug, by_name


def get_company_by_slug(slug: str) -> Company | None:
    s = str(slug or "").strip().lower()
    if not s:
        return None
    by_slug, _ = _load()
    return by_slug.get(s)


def get_company_by_name(name: str) -> Company | None:
    n = str(name or "").strip().lower()
    if not n:
        return None
    _, by_name = _load()
    return by_name.get(n)


def require_company(slug: str) -> Company:
    c = get_company_by_slug(slug)
    if not c:
        raise ValueError(f"Unknown client slug: {slug}")
    return c


def company_name(slug: str) -> str:
    c = get_company_by_slug(slug)
    return c.name if c else ""


def all_company_slugs() -> list[str]:
    by_slug, _ = _load()
    return list(by_slug.keys())

