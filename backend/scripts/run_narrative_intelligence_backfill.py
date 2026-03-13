#!/usr/bin/env python3
"""
Backfill Narrative Intelligence Daily.

1. Runs narrative_shift pipeline (fetch + cluster + store) to ensure we have data.
2. Runs daily synthesis (1 LLM call) and stores in narrative_intelligence_daily.

Run: python backend/scripts/run_narrative_intelligence_backfill.py
Or:  docker compose exec backend python scripts/run_narrative_intelligence_backfill.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    print("Step 1: Running narrative shift pipeline...")
    from app.services.narrative_shift_service import run_narrative_shift_pipeline
    ns_result = await run_narrative_shift_pipeline()
    print("  Result:", ns_result)

    print("\nStep 2: Running daily narrative intelligence synthesis...")
    from app.services.narrative_intelligence_daily_service import run_daily_synthesis
    daily_result = await run_daily_synthesis()
    print("  Result:", daily_result)
    print("\nDone. Check /social/narrative-shift and the Daily Intelligence table.")


if __name__ == "__main__":
    asyncio.run(main())
