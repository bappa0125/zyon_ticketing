#!/usr/bin/env python3
"""Run official YouTube Data API v3 ingest on demand (channels + search → Mongo)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.youtube_official_ingest_service import run_youtube_official_ingest


def main():
    result = asyncio.run(run_youtube_official_ingest())
    print(result)


if __name__ == "__main__":
    main()
