#!/usr/bin/env python3
"""Run the YouTube narrative pipeline on demand (fetch → LLM → save to Mongo)."""
import asyncio
import os
import sys

# Ensure backend root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.youtube_trending_service import run_youtube_narrative_pipeline


def main():
    result = asyncio.run(run_youtube_narrative_pipeline())
    print(result)


if __name__ == "__main__":
    main()
