"""Run one RSS metadata ingestion cycle. For cron/scheduler; exits after one run."""
import asyncio
import os
import sys

# Ensure app is on path when run as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.monitoring_ingestion.rss_ingestion import run_rss_ingestion


def main():
    asyncio.run(run_rss_ingestion(max_feeds=10))


if __name__ == "__main__":
    main()
