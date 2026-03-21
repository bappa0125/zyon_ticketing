#!/usr/bin/env python3
"""
Persist CXO narrative briefing packs for all clients (LLM memo + exhibits → Mongo).

Scheduled via ingestion_scheduler and run_master_backfill. Manual run:

  docker compose exec backend python scripts/run_narrative_briefing_daily.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _main() -> None:
    from app.services.narrative_briefing_service import run_narrative_briefing_for_all_clients
    from app.services.mongodb import get_mongo_client

    await get_mongo_client()
    out = await run_narrative_briefing_for_all_clients()
    print(out)


if __name__ == "__main__":
    asyncio.run(_main())
