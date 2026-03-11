#!/usr/bin/env python3
"""Backfill topics on article_documents (KeyBERT). Run once to populate existing docs."""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.article_topics_worker import run_article_topics_pipeline


async def main():
    parser = argparse.ArgumentParser(description="Backfill topics on article_documents")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--iterations", type=int, default=None, help="Max runs (default: run until no more)")
    args = parser.parse_args()

    total = 0
    iters = 0
    while True:
        r = await run_article_topics_pipeline(batch_size=args.batch_size)
        n = r.get("processed", 0) + r.get("errors", 0)
        total += r.get("processed", 0)
        iters += 1
        print(f"Iter {iters}: processed={r.get('processed')}, errors={r.get('errors')}")
        if n == 0 or (args.iterations and iters >= args.iterations):
            break
    print(f"Backfill complete: {total} documents updated over {iters} iterations")


if __name__ == "__main__":
    asyncio.run(main())
