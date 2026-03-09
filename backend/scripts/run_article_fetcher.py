"""Run one article fetch cycle. For cron/scheduler; exits after one run."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.monitoring_ingestion.article_fetcher import run_article_fetcher


def main():
    asyncio.run(run_article_fetcher(max_items=20))


if __name__ == "__main__":
    main()
