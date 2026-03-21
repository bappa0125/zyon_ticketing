#!/usr/bin/env python3
"""Build and save forum theme digest (Mongo: forum_theme_digest). Run: docker compose exec backend python scripts/run_forum_theme_digest.py"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.forum_theme_digest_service import run_forum_theme_digest_job  # noqa: E402


def main() -> None:
    result = asyncio.run(run_forum_theme_digest_job())
    print(result)
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
