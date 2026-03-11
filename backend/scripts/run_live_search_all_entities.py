"""Scheduled job: run live search for fixed entities (Sahi, Dhan, Groww, Zerodha) and store with dedup.

Safeguards to avoid rate limits/blocks:
- One entity at a time (no parallel search).
- Delay between entities (default 45s).
- Back off and stop run on 429 / 5xx / connection errors.
- Optional: run 1–2x per day via cron (e.g. 2 AM).

Usage:
  python scripts/run_live_search_all_entities.py
  python scripts/run_live_search_all_entities.py --delay 60
  python scripts/run_live_search_all_entities.py --no-external   # skip Tavily/DDG to reduce load

Cron example (daily at 2 AM): 0 2 * * * cd /app && python scripts/run_live_search_all_entities.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Backend app on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Entities to run live search for (client + selected competitors)
LIVE_SEARCH_ENTITIES = ["Sahi", "Dhan", "Groww", "Zerodha"]

DEFAULT_DELAY_SECONDS = 45
BACKOFF_SLEEP_ON_ERROR_SECONDS = 300  # 5 min before exiting so we don't retry immediately


def _is_rate_limit_or_server_error(exc: BaseException) -> bool:
    """True if we should stop the run to avoid further blocks."""
    s = str(exc).lower()
    if "429" in s or "rate limit" in s or "too many requests" in s:
        return True
    if "503" in s or "502" in s or "500" in s or "504" in s:
        return True
    if "blocked" in s or "forbidden" in s or "403" in s:
        return True
    if "connection" in s or "timeout" in s or "timed out" in s:
        return True
    resp = getattr(exc, "response", None)
    if resp is not None:
        status = getattr(resp, "status_code", None)
        if status in (429, 500, 502, 503, 504, 403):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run live search for Sahi, Dhan, Groww, Zerodha; store results with dedup. One entity at a time with delay."
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=DEFAULT_DELAY_SECONDS,
        help=f"Seconds to wait between entities (default {DEFAULT_DELAY_SECONDS})",
    )
    parser.add_argument(
        "--no-external",
        action="store_true",
        help="Disable external search (Tavily/DuckDuckGo) to reduce API load",
    )
    parser.add_argument(
        "--no-llm-rerank",
        action="store_true",
        help="Disable LLM rerank to reduce latency and API calls",
    )
    args = parser.parse_args()

    from app.core.logging import get_logger
    from app.services.media_mention.mention_search import search_mentions_live_only

    logger = get_logger(__name__)

    delay = max(10, min(args.delay, 300))  # clamp 10–300s
    entities = list(LIVE_SEARCH_ENTITIES)
    total_stored_mentions = 0

    logger.info(
        "live_search_job_start",
        entities=entities,
        delay_seconds=delay,
        use_external=not args.no_external,
        llm_rerank=not args.no_llm_rerank,
    )
    print(f"Live search job: {entities} (delay={delay}s, external={not args.no_external})")

    for i, entity in enumerate(entities):
        try:
            if i > 0:
                logger.info("live_search_job_sleep", entity_next=entity, seconds=delay)
                time.sleep(delay)

            results = search_mentions_live_only(
                company=entity,
                store_live_results=True,
                use_internal=True,
                use_google_news=True,
                use_external=not args.no_external,
                llm_rerank=not args.no_llm_rerank,
                forum_only=False,
            )
            count = len(results) if results else 0
            total_stored_mentions += count
            logger.info("live_search_job_entity_done", entity=entity, results_count=count)
            print(f"  {entity}: {count} results (stored in background)")

        except Exception as e:
            if _is_rate_limit_or_server_error(e):
                logger.warning(
                    "live_search_job_backoff",
                    entity=entity,
                    error=str(e),
                    sleep_seconds=BACKOFF_SLEEP_ON_ERROR_SECONDS,
                )
                print(
                    f"  Rate limit or server error for {entity}; stopping run. Sleep {BACKOFF_SLEEP_ON_ERROR_SECONDS}s then exit."
                )
                time.sleep(BACKOFF_SLEEP_ON_ERROR_SECONDS)
                return 1
            logger.exception("live_search_job_entity_failed", entity=entity, error=str(e))
            print(f"  {entity}: error - {e}")
            # Continue to next entity on other errors

    logger.info(
        "live_search_job_done",
        entities_processed=len(entities),
        total_results=total_stored_mentions,
    )
    print(f"Done. Processed {len(entities)} entities.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
