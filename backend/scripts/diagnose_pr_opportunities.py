#!/usr/bin/env python3
"""Diagnose PR Opportunities (outreach, topic gaps, quote alerts, etc.).

Checks: entity_mentions/article_documents counts, source_domain, date range,
entity names, media_articles vs article_documents, quote patterns.
Run: docker compose run --rm backend python scripts/diagnose_pr_opportunities.py [--client Sahi]
"""
import argparse
import asyncio
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

QUOTE_PATTERNS = re.compile(
    r"\b(declined to comment|did not (respond|return)|no comment|not available for comment|"
    r"could not be reached|refused to comment|we reached out|contacted for comment)\b",
    re.I,
)


async def main(client_name: str = "Sahi"):
    from app.config import get_config
    from app.core.client_config_loader import load_clients, get_entity_names, get_competitor_names

    config = get_config()
    from motor.motor_asyncio import AsyncIOMotorClient

    mc = AsyncIOMotorClient(config["settings"].mongodb_url)
    db_name = config["mongodb"].get("database", "chat")
    db = mc[db_name]

    em = db["entity_mentions"]
    art = db["article_documents"]
    ma = db["media_articles"]
    snap = db["pr_daily_snapshots"]
    opp = db["pr_opportunities"]

    clients_list = await load_clients()
    client_obj = next(
        (c for c in clients_list if (c.get("name") or "").strip().lower() == client_name.strip().lower()),
        None,
    )
    if not client_obj:
        print(f">>> Client '{client_name}' not found in clients.yaml")
        return

    entities = get_entity_names(client_obj)
    competitors = get_competitor_names(client_obj)
    today = datetime.now(timezone.utc)
    cutoff_7d = today - timedelta(days=7)
    today_str = today.strftime("%Y-%m-%d")

    print("=== PR Opportunities diagnostic ===\n")
    print(f"Client: {client_name}")
    print(f"Entities: {entities}")
    print(f"Competitors: {competitors}\n")

    # 1. Data for last 7 days
    em_7d = await em.count_documents({
        "entity": {"$in": entities},
        "$or": [{"published_at": {"$gte": cutoff_7d}}, {"timestamp": {"$gte": cutoff_7d}}],
    })
    art_7d = await art.count_documents({
        "entities": {"$in": entities},
        "$or": [{"published_at": {"$gte": cutoff_7d}}, {"fetched_at": {"$gte": cutoff_7d}}],
    })
    em_today = await em.count_documents({
        "entity": {"$in": entities},
        "$or": [
            {"published_at": {"$gte": today.replace(hour=0, minute=0, second=0, microsecond=0)}},
            {"timestamp": {"$gte": today.replace(hour=0, minute=0, second=0, microsecond=0)}},
        ],
    })

    print("1. Data volume (last 7d)")
    print(f"   entity_mentions (entities): {em_7d}")
    print(f"   article_documents (entities): {art_7d}")
    print(f"   entity_mentions for today: {em_today}")
    if em_7d == 0 and art_7d == 0:
        print("   >>> No data for entities in last 7d. Run ingestion (RSS, article fetcher, entity_mentions).")
    print()

    # 2. source_domain
    em_with_sd = await em.count_documents({
        "entity": {"$in": entities},
        "$or": [{"published_at": {"$gte": cutoff_7d}}, {"timestamp": {"$gte": cutoff_7d}}],
        "source_domain": {"$exists": True, "$nin": [None, ""]},
    })
    art_with_sd = await art.count_documents({
        "entities": {"$in": entities},
        "$or": [{"published_at": {"$gte": cutoff_7d}}, {"fetched_at": {"$gte": cutoff_7d}}],
        "source_domain": {"$exists": True, "$nin": [None, ""]},
    })
    em_no_sd = em_7d - em_with_sd
    art_no_sd = art_7d - art_with_sd

    print("2. source_domain (needed for outreach by outlet)")
    print(f"   entity_mentions with source_domain: {em_with_sd} / {em_7d}")
    print(f"   article_documents with source_domain: {art_with_sd} / {art_7d}")
    if em_no_sd > 0 or art_no_sd > 0:
        print("   >>> Run: python scripts/backfill_source_domain.py --force")
    print()

    # 3. Topic gaps: article_documents vs media_articles
    art_with_topics = await art.count_documents({
        "entities": {"$in": entities},
        "topics": {"$exists": True, "$type": "array", "$ne": []},
    })
    ma_total = await ma.count_documents({})
    ma_with_topics = await ma.count_documents({
        "entity": {"$in": entities},
        "topics": {"$exists": True, "$type": "array", "$ne": []},
    })

    print("3. Topic gaps (topic opportunities)")
    print(f"   article_documents with topics (KeyBERT): {art_with_topics}")
    print(f"   media_articles total: {ma_total}, with topics: {ma_with_topics}")
    if art_with_topics == 0 and ma_with_topics == 0:
        print("   >>> No topics. Run article_topics pipeline for article_documents.")
    else:
        print("   >>> Using article_documents.topics (primary) or media_articles (fallback)")
    print()

    # 4. Entity name match
    em_entities = await em.distinct("entity", {"entity": {"$in": entities}})
    art_entity_sample = []
    async for d in art.find({"entities": {"$in": entities}}, {"entities": 1}).limit(5):
        art_entity_sample.extend(d.get("entities") or [])

    print("4. Entity name match")
    print(f"   entity_mentions distinct entity values: {em_entities}")
    print(f"   article_documents sample entities: {list(set(art_entity_sample))[:10]}")
    print()

    # 5. Quote opportunity candidates
    art_with_text = await art.count_documents({
        "entities": {"$in": entities},
        "$or": [{"published_at": {"$gte": cutoff_7d}}, {"fetched_at": {"$gte": cutoff_7d}}],
    })
    quote_candidates = 0
    async for d in art.find({
        "entities": {"$in": entities},
        "$or": [{"published_at": {"$gte": cutoff_7d}}, {"fetched_at": {"$gte": cutoff_7d}}],
    }).limit(500):
        text = (d.get("article_text") or d.get("summary") or d.get("title") or "")[:2000]
        if QUOTE_PATTERNS.search(text):
            quote_candidates += 1

    print("5. Quote opportunities")
    print(f"   article_documents with text (7d): {art_with_text}")
    print(f"   Quote-phrase candidates (sample 500): {quote_candidates}")
    if quote_candidates == 0:
        print("   >>> Few articles contain 'declined to comment', 'no comment', etc. Normal.")
    print()

    # 6. Stored data
    snap_today = await snap.find_one({"client": client_name, "date": today_str})
    opp_count = await opp.count_documents({"client": client_name})
    opp_recent = await opp.count_documents({"client": client_name, "date": {"$gte": (today - timedelta(days=7)).strftime("%Y-%m-%d")}})

    print("6. Stored PR data")
    print(f"   pr_daily_snapshots for {today_str}: {'yes' if snap_today else 'no'}")
    if snap_today:
        ot = snap_today.get("outreach_targets") or []
        print(f"   outreach_targets in snapshot: {len(ot)}")
    print(f"   pr_opportunities total for client: {opp_count}")
    print(f"   pr_opportunities last 7d: {opp_recent}")
    if not snap_today and (em_7d > 0 or art_7d > 0):
        print("   >>> Run: python scripts/run_pr_opportunities.py --pr-report-first --client", client_name)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", "-c", default="Sahi", help="Client name")
    args = parser.parse_args()
    asyncio.run(main(args.client))
