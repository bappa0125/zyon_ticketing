"""
Run Apify Twitter (and optional YouTube) social monitor once → MongoDB social_posts.

Usage (from repo root, with APIFY_API_KEY in .env):
  docker compose run --rm backend python scripts/run_social_monitor_once.py

Requires monitoring.social_sources.twitter: true and apify.* settings in config/monitoring.yaml.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def _main() -> None:
    from app.services.social_monitor_worker import run_social_monitor

    out = await run_social_monitor()
    print("social_monitor_result:", out)


if __name__ == "__main__":
    asyncio.run(_main())
