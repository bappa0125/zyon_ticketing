"""Run one forum ingestion cycle. Fetches HTML sources (Traderji, TradingQnA, ValuePickr) from media_sources.yaml, extracts text, stores in article_documents. Exit 0 on success."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.forum_ingestion_worker import run_forum_ingestion


def main():
    result = asyncio.run(run_forum_ingestion())
    print("Forum ingestion result:", result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
