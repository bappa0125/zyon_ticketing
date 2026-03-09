#!/usr/bin/env python3
"""Run entity mentions pipeline — article_documents → entity_mentions."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.entity_mentions_worker import run_entity_mentions_pipeline


def main():
    result = asyncio.run(run_entity_mentions_pipeline())
    print(result)
    return 0 if result.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
