#!/usr/bin/env python3
"""Run narrative shift pipeline (API fetch + clustering + store). Populates data for UI."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.narrative_shift_service import run_narrative_shift_pipeline


def main():
    result = asyncio.run(run_narrative_shift_pipeline())
    print(result)


if __name__ == "__main__":
    main()
