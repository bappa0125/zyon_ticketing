"""Run sentiment analysis on entity_mentions where sentiment is missing (one-off or cron)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.entity_mentions_sentiment_worker import run_entity_mentions_sentiment


def main():
    result = asyncio.run(run_entity_mentions_sentiment(batch_size=100))
    print(result)


if __name__ == "__main__":
    main()
