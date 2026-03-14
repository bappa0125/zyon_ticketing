#!/usr/bin/env python3
"""
Backfill Narrative Positioning for all clients.

Runs the narrative positioning batch (1 LLM call per client) and stores in narrative_positioning.

Run: python backend/scripts/run_narrative_positioning_backfill.py
Or:  docker compose exec backend python scripts/run_narrative_positioning_backfill.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    print("Running narrative positioning batch for all clients...")
    from app.services.narrative_positioning_service import run_positioning_for_all_clients

    result = await run_positioning_for_all_clients()
    print("Result:", result)
    print("\nDone. Check /social/narrative-positioning?client=Sahi&days=7")


if __name__ == "__main__":
    asyncio.run(main())
