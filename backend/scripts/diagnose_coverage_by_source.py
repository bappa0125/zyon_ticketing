"""Diagnose why Coverage by Source shows zeros.

Checks: source_domain values, entity mentions, date range, media_sources match.
Run: docker compose exec backend python scripts/diagnose_coverage_by_source.py
"""

import asyncio
from datetime import datetime, timedelta, timezone

from app.config import get_config
from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    config = get_config()
    client = AsyncIOMotorClient(config["settings"].mongodb_url)
    db = client[config["mongodb"].get("database", "chat")]

    em = db["entity_mentions"]
    art = db["article_documents"]

    # Entity names (Sahi + competitors)
    try:
        from app.core.client_config_loader import load_clients, get_entity_names

        clients_list = await load_clients()
        client_obj = next((c for c in clients_list if (c.get("name") or "").strip().lower() == "sahi"), None)
        entities = get_entity_names(client_obj) if client_obj else ["Sahi"]
    except Exception:
        entities = ["Sahi"]

    cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)

    # Counts
    em_total = await em.count_documents({})
    em_with_sd = await em.count_documents({"source_domain": {"$exists": True, "$nin": [None, ""]}})
    em_empty_sd = await em.count_documents({"$or": [{"source_domain": {"$in": [None, ""]}}, {"source_domain": {"$exists": False}}]})
    em_recent = await em.count_documents({"$or": [{"published_at": {"$gte": cutoff_7d}}, {"timestamp": {"$gte": cutoff_7d}}]})
    try:
        from app.services.media_intelligence_service import _mongo_case_insensitive_entity_filter

        em_entities_7d = await em.count_documents({
            "$and": [
                _mongo_case_insensitive_entity_filter("entity", entities),
                {
                    "$or": [
                        {"published_at": {"$gte": cutoff_7d}},
                        {"timestamp": {"$gte": cutoff_7d}},
                    ],
                },
            ],
        })
    except Exception:
        em_entities_7d = await em.count_documents({
            "entity": {"$in": entities},
            "$or": [{"published_at": {"$gte": cutoff_7d}}, {"timestamp": {"$gte": cutoff_7d}}],
        })

    art_total = await art.count_documents({})
    art_with_sd = await art.count_documents({"source_domain": {"$exists": True, "$nin": [None, ""]}})
    art_empty_sd = await art.count_documents({"$or": [{"source_domain": {"$in": [None, ""]}}, {"source_domain": {"$exists": False}}]})

    # Sample source_domain values from entity_mentions
    pipeline = [
        {"$match": {"source_domain": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {"_id": "$source_domain", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 20},
    ]
    sd_samples = list(await em.aggregate(pipeline).to_list(length=20))

    # Full media_sources domain set (same mapping as Media Intelligence dashboard)
    config_domain_set: set[str] = set()
    domain_to_name: dict[str, str] = {}
    try:
        from app.services.monitoring_ingestion.media_source_registry import load_media_sources
        from app.services.media_intelligence_service import _map_to_config_domain, _normalize_domain

        for src in load_media_sources():
            d = _normalize_domain(src.get("domain") or "")
            if d:
                config_domain_set.add(d)
                domain_to_name[d] = (src.get("name") or d)[:80]
    except Exception:
        _map_to_config_domain = None  # type: ignore
        _normalize_domain = None  # type: ignore

    print("=== Coverage by Source diagnostic ===\n")
    print(f"Entities (Sahi + competitors): {entities}\n")
    print("entity_mentions:")
    print(f"  total: {em_total}")
    print(f"  with source_domain: {em_with_sd}")
    print(f"  empty/missing source_domain: {em_empty_sd}")
    print(f"  in last 7d: {em_recent}")
    print(f"  in last 7d for your entities: {em_entities_7d}")
    print()
    print("article_documents:")
    print(f"  total: {art_total}")
    print(f"  with source_domain: {art_with_sd}")
    print(f"  empty/missing source_domain: {art_empty_sd}")
    print()
    print("Top source_domain values in entity_mentions (✓ = maps to a row in Coverage by source):")
    for s in sd_samples:
        d_raw = s["_id"] or "(empty)"
        c = s["count"]
        if _map_to_config_domain and _normalize_domain and isinstance(d_raw, str):
            norm = _normalize_domain(d_raw) or d_raw.strip().lower()
            mapped = _map_to_config_domain(norm, config_domain_set)
            if mapped:
                label = "✓"
                extra = f" → table key '{domain_to_name.get(mapped, mapped)}' ({mapped})"
            else:
                label = "✗"
                extra = " (not in media_sources.yaml — dashboard shows 0 for that outlet row)"
        else:
            label = "?"
            extra = ""
        print(f"  {d_raw}: {c}  {label}{extra}")
    print()
    print(f"media_sources.yaml: {len(config_domain_set)} configured domains (full list used for ✓/✗).")
    print()
    if em_entities_7d == 0:
        print(">>> No entity_mentions for your entities in last 7d. Run RSS + article fetcher + entity_mentions pipeline.")
    elif em_with_sd == 0:
        print(">>> All entity_mentions have empty source_domain. Backfill or fix ingestion.")
    elif not sd_samples:
        print(">>> No source_domain values found. Check data pipeline.")
    else:
        print(">>> Rows with ✗ are expected to show 0 in 'Coverage by source' (domain not in media_sources).")
        print(">>> Outlets in YAML with 0 mentions: ingestion/entity detection never wrote mentions for that domain.")


if __name__ == "__main__":
    asyncio.run(main())
