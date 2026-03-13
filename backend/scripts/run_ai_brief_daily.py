#!/usr/bin/env python3
"""Run AI brief generation for each client (7d), store in DB. For manual run or cron."""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.reports_api import run_ai_brief_daily


def main():
    result = asyncio.run(run_ai_brief_daily())
    print(result)


if __name__ == "__main__":
    main()
