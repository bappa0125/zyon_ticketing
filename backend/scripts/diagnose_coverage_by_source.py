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

    # Media sources domains for match check
    try:
        from app.services.monitoring_ingestion.media_source_registry import load_media_sources

        config_domains = [s.get("domain") for s in load_media_sources() if s.get("domain")][:15]
    except Exception:
        config_domains = []

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
    print("Top source_domain values in entity_mentions:")
    for s in sd_samples:
        d = s["_id"] or "(empty)"
        c = s["count"]
        in_config = "✓" if d in config_domains or any(d.endswith("." + cd) or d == cd for cd in config_domains) else "?"
        print(f"  {d}: {c} {in_config}")
    print()
    print("Sample config domains (from media_sources):", config_domains[:10])
    print()
    if em_entities_7d == 0:
        print(">>> No entity_mentions for your entities in last 7d. Run RSS + article fetcher + entity_mentions pipeline.")
    elif em_with_sd == 0:
        print(">>> All entity_mentions have empty source_domain. Backfill or fix ingestion.")
    elif not sd_samples:
        print(">>> No source_domain values found. Check data pipeline.")
    else:
        print(">>> If coverage still zeros, source_domain values may not match media_sources keys.")


if __name__ == "__main__":
    asyncio.run(main())
