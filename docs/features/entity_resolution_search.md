# Entity Resolution for Search Queries

**Status:** Implemented  
**Purpose:** Map natural-language search queries to canonical entity names before mention search, enabling correct disambiguation and context filtering for ambiguous entities like Sahi (trading vs health AI).

## Problem

When a user asks "latest news on Sahi" or "sahi trading app updates", the extracted query might be the full phrase. Passing it directly to `search_mentions` can bypass disambiguation logic that expects a canonical entity (e.g. "Sahi") from `clients.yaml`.

## Solution

Before calling `search_mentions`, resolve the query to a canonical entity using `clients.yaml`:

- **"latest news on Sahi"** → **"Sahi"**
- **"sahi trading app"** → **"Sahi"** (alias match)
- **"Zerodha"** → **"Zerodha"** (exact match)

The canonical entity is then used for:
1. Disambiguated search query (e.g. "Sahi trading" instead of "Sahi")
2. Post-search context filtering (require context_keywords in title/snippet)

## Implementation

| Component | File | Description |
|-----------|------|-------------|
| Resolution logic | `mention_context_validation.resolve_to_canonical_entity(query)` | Maps query to canonical name via clients.yaml (name, aliases, competitors) |
| Chat integration | `chat.py` | Resolves before `search_mentions`; passes canonical entity for search |

## Configuration

Uses existing `config/clients.yaml`:
- `name` — canonical entity name
- `aliases` — variants (e.g. "sahi trading app", "sahi app")
- `competitors` — also resolved to their canonical form

## Related

- [Pipeline stabilization](pipeline_stabilization.md) — context_keywords, disambiguation
- [Entity alias detection](entity_alias_detection.md) — alias resolution in entity detection
