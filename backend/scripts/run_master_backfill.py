#!/usr/bin/env python3
"""
Master backfill script – runs all scheduled ingestion jobs in dependency order.

Use this as a daily morning run to catch up or ensure a full data refresh.
Handles dependencies, config checks, and continues on non-fatal errors by default.

Usage:
  docker compose exec backend python scripts/run_master_backfill.py
  docker compose exec backend python scripts/run_master_backfill.py --strict
  docker compose exec backend python scripts/run_master_backfill.py --dry-run
  docker compose exec backend python scripts/run_master_backfill.py --skip narrative --skip youtube

Options:
  --strict          Exit on first failure (default: continue on error)
  --dry-run         Print what would run, do not execute
  --skip PHASE      Skip phase(s): rss, article, entity, sentiment, topics,
                    ai_summary, reddit, youtube, reddit_trending, youtube_narrative,
                    narrative_shift, narrative_daily, sahi, ai_brief, crawler, forum
  --skip-deps       Skip optional dependency checks (Redis, Qdrant)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Callable

# Ensure app is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class StepResult:
    phase: str
    ok: bool
    duration_sec: float
    message: str = ""
    result: dict | None = None


@dataclass
class RunState:
    results: list[StepResult] = field(default_factory=list)
    strict: bool = False
    dry_run: bool = False
    skip: set[str] = field(default_factory=set)
    skip_deps: bool = False

    def should_run(self, phase: str) -> bool:
        if phase in self.skip:
            return False
        return True

    def record(self, r: StepResult):
        self.results.append(r)
        if self.strict and not r.ok:
            raise SystemExit(1)

    def summary(self) -> tuple[int, int]:
        ok = sum(1 for r in self.results if r.ok)
        fail = sum(1 for r in self.results if not r.ok)
        return ok, fail


async def check_mongodb() -> bool:
    """MongoDB is required. Return True if reachable."""
    try:
        from app.services.mongodb import get_mongo_client
        client = await get_mongo_client()
        await client.admin.command("ping")
        return True
    except Exception as e:
        print(f"  FATAL: MongoDB unreachable: {e}")
        return False


async def check_redis() -> bool:
    try:
        from app.services.redis_client import get_redis
        r = await get_redis()
        await r.ping()
        return True
    except Exception:
        return False


def run_async(coro):
    return asyncio.run(coro)


# --- Phase runners (mirror ingestion_scheduler logic) ---

def _phase_rss(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("rss", True, 0, "dry-run")
    try:
        from app.services.monitoring_ingestion.rss_ingestion import run_rss_ingestion
        cfg = __import__("app.config", fromlist=["get_config"]).get_config()
        max_feeds = (cfg.get("scheduler") or {}).get("rss_max_feeds_per_run", 20)
        result = run_async(run_rss_ingestion(max_feeds=max_feeds))
        return StepResult("rss", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("rss", False, time.monotonic() - start, message=str(e))


def _phase_article_fetcher(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("article_fetcher", True, 0, "dry-run")
    try:
        from app.services.monitoring_ingestion.article_fetcher import run_article_fetcher
        cfg = __import__("app.config", fromlist=["get_config"]).get_config()
        max_items = (cfg.get("scheduler") or {}).get("article_fetcher_max_items_per_run", 40)
        result = run_async(run_article_fetcher(max_items=max_items))
        return StepResult("article_fetcher", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("article_fetcher", False, time.monotonic() - start, message=str(e))


def _phase_entity_mentions(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("entity_mentions", True, 0, "dry-run")
    try:
        from app.services.entity_mentions_worker import run_entity_mentions_pipeline
        cfg = __import__("app.config", fromlist=["get_config"]).get_config()
        batch = (cfg.get("scheduler") or {}).get("entity_mentions_batch_size", 150)
        result = run_async(run_entity_mentions_pipeline(batch_size=batch))
        return StepResult("entity_mentions", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("entity_mentions", False, time.monotonic() - start, message=str(e))


def _phase_entity_sentiment(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("entity_sentiment", True, 0, "dry-run")
    try:
        from app.services.entity_mentions_sentiment_worker import run_entity_mentions_sentiment
        result = run_async(run_entity_mentions_sentiment(batch_size=50))
        return StepResult("entity_sentiment", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("entity_sentiment", False, time.monotonic() - start, message=str(e))


def _phase_article_topics(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("article_topics", True, 0, "dry-run")
    try:
        from app.services.article_topics_worker import run_article_topics_pipeline
        cfg = __import__("app.config", fromlist=["get_config"]).get_config()
        batch = (cfg.get("scheduler") or {}).get("article_topics_batch_size", 30)
        result = run_async(run_article_topics_pipeline(batch_size=batch))
        return StepResult("article_topics", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("article_topics", False, time.monotonic() - start, message=str(e))


def _phase_ai_summary(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("ai_summary", True, 0, "dry-run")
    try:
        from app.services.ai_summary_worker import run_ai_summary_worker
        result = run_async(run_ai_summary_worker())
        return StepResult("ai_summary", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("ai_summary", False, time.monotonic() - start, message=str(e))


def _phase_reddit_monitor(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("reddit_monitor", True, 0, "dry-run")
    try:
        from app.services.reddit_worker import run_reddit_monitor
        result = run_async(run_reddit_monitor())
        return StepResult("reddit_monitor", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("reddit_monitor", False, time.monotonic() - start, message=str(e))


def _phase_youtube_monitor(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("youtube_monitor", True, 0, "dry-run")
    try:
        from app.services.youtube_worker import run_youtube_monitor
        result = run_async(run_youtube_monitor())
        return StepResult("youtube_monitor", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("youtube_monitor", False, time.monotonic() - start, message=str(e))


def _phase_crawler_enqueue(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("crawler_enqueue", True, 0, "dry-run")
    try:
        from app.services.crawler.scheduler import enqueue_crawls
        enqueue_crawls(max_per_run=10)
        return StepResult("crawler_enqueue", True, time.monotonic() - start)
    except Exception as e:
        return StepResult("crawler_enqueue", False, time.monotonic() - start, message=str(e))


def _phase_forum_ingestion(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("forum_ingestion", True, 0, "dry-run")
    try:
        from app.services.forum_ingestion_worker import run_forum_ingestion
        result = run_async(run_forum_ingestion())
        return StepResult("forum_ingestion", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("forum_ingestion", False, time.monotonic() - start, message=str(e))


def _phase_reddit_trending(state: RunState) -> StepResult:
    cfg = __import__("app.config", fromlist=["get_config"]).get_config()
    if not (cfg.get("reddit_trending") or {}).get("enabled", False):
        return StepResult("reddit_trending", True, 0, "skipped (disabled in config)")
    start = time.monotonic()
    if state.dry_run:
        return StepResult("reddit_trending", True, 0, "dry-run")
    try:
        from app.services.reddit_trending_service import run_reddit_trending_pipeline
        result = run_async(run_reddit_trending_pipeline())
        return StepResult("reddit_trending", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("reddit_trending", False, time.monotonic() - start, message=str(e))


def _phase_youtube_narrative(state: RunState) -> StepResult:
    cfg = __import__("app.config", fromlist=["get_config"]).get_config()
    yt = cfg.get("youtube_trending") or {}
    if not (isinstance(yt, dict) and yt.get("enabled", False)):
        return StepResult("youtube_narrative", True, 0, "skipped (disabled in config)")
    start = time.monotonic()
    if state.dry_run:
        return StepResult("youtube_narrative", True, 0, "dry-run")
    try:
        from app.services.youtube_trending_service import run_youtube_narrative_pipeline
        result = run_async(run_youtube_narrative_pipeline())
        return StepResult("youtube_narrative", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("youtube_narrative", False, time.monotonic() - start, message=str(e))


def _phase_narrative_shift(state: RunState) -> StepResult:
    cfg = __import__("app.config", fromlist=["get_config"]).get_config()
    ns = cfg.get("narrative_shift") or {}
    if not (isinstance(ns, dict) and ns.get("enabled", False)):
        return StepResult("narrative_shift", True, 0, "skipped (disabled in config)")
    start = time.monotonic()
    if state.dry_run:
        return StepResult("narrative_shift", True, 0, "dry-run")
    try:
        from app.services.narrative_shift_service import run_narrative_shift_pipeline
        result = run_async(run_narrative_shift_pipeline())
        return StepResult("narrative_shift", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("narrative_shift", False, time.monotonic() - start, message=str(e))


def _phase_narrative_daily(state: RunState) -> StepResult:
    cfg = __import__("app.config", fromlist=["get_config"]).get_config()
    nid = cfg.get("narrative_intelligence_daily") or {}
    if not (isinstance(nid, dict) and nid.get("enabled", False)):
        return StepResult("narrative_daily", True, 0, "skipped (disabled in config)")
    start = time.monotonic()
    if state.dry_run:
        return StepResult("narrative_daily", True, 0, "dry-run")
    try:
        from app.services.narrative_intelligence_daily_service import run_daily_synthesis
        result = run_async(run_daily_synthesis())
        return StepResult("narrative_daily", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("narrative_daily", False, time.monotonic() - start, message=str(e))


def _phase_sahi(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("sahi_strategic_brief", True, 0, "dry-run")
    try:
        from app.services.sahi_strategic_brief_service import run_sahi_strategic_brief_daily
        result = run_async(run_sahi_strategic_brief_daily())
        return StepResult("sahi_strategic_brief", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("sahi_strategic_brief", False, time.monotonic() - start, message=str(e))


def _phase_ai_brief(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("ai_brief_daily", True, 0, "dry-run")
    try:
        from app.api.reports_api import run_ai_brief_daily
        result = run_async(run_ai_brief_daily())
        return StepResult("ai_brief_daily", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("ai_brief_daily", False, time.monotonic() - start, message=str(e))


def main():
    parser = argparse.ArgumentParser(description="Master backfill – run all ingestion jobs in order")
    parser.add_argument("--strict", action="store_true", help="Exit on first failure")
    parser.add_argument("--dry-run", action="store_true", help="Print phases only, do not run")
    parser.add_argument("--skip", action="append", default=[], help="Skip phase (repeat for multiple)")
    parser.add_argument("--skip-deps", action="store_true", help="Skip Redis/Qdrant preflight checks")
    args = parser.parse_args()

    state = RunState(
        strict=args.strict,
        dry_run=args.dry_run,
        skip={s.strip().lower() for s in args.skip if s.strip()},
        skip_deps=args.skip_deps,
    )

    # Phase name -> skip flag mapping (--skip accepts various aliases)
    # "narrative" skips both narrative_shift and narrative_daily
    SKIP_ALIASES: dict[str, str | list[str]] = {
        "rss": "rss",
        "article": "article_fetcher",
        "article_fetcher": "article_fetcher",
        "entity": "entity_mentions",
        "entity_mentions": "entity_mentions",
        "sentiment": "entity_sentiment",
        "entity_sentiment": "entity_sentiment",
        "topics": "article_topics",
        "article_topics": "article_topics",
        "ai_summary": "ai_summary",
        "reddit": "reddit_monitor",
        "reddit_monitor": "reddit_monitor",
        "youtube": "youtube_monitor",
        "youtube_monitor": "youtube_monitor",
        "reddit_trending": "reddit_trending",
        "youtube_narrative": "youtube_narrative",
        "narrative": ["narrative_shift", "narrative_daily"],
        "narrative_shift": "narrative_shift",
        "narrative_daily": "narrative_daily",
        "sahi": "sahi_strategic_brief",
        "ai_brief": "ai_brief_daily",
        "ai_brief_daily": "ai_brief_daily",
        "crawler": "crawler_enqueue",
        "crawler_enqueue": "crawler_enqueue",
        "forum": "forum_ingestion",
        "forum_ingestion": "forum_ingestion",
    }
    normalized_skip = set()
    for s in state.skip:
        v = SKIP_ALIASES.get(s, s)
        if isinstance(v, list):
            normalized_skip.update(v)
        else:
            normalized_skip.add(v)
    state.skip = normalized_skip

    print("=" * 60)
    print("Master Backfill – daily ingestion pipeline")
    print("=" * 60)
    if state.dry_run:
        print("(DRY RUN – no jobs will execute, skipping dependency checks)")
    if state.skip:
        print(f"  Skipping: {', '.join(sorted(state.skip))}")
    print()

    # Preflight: MongoDB required (skip in dry-run)
    if not state.dry_run:
        print("Preflight: Checking MongoDB...")
        ok = run_async(check_mongodb())
        if not ok:
            print("  MongoDB is required. Exiting.")
            sys.exit(1)
        print("  MongoDB OK")

    if not state.skip_deps and not state.dry_run:
        redis_ok = run_async(check_redis())
        if redis_ok:
            print("  Redis OK")
        else:
            print("  Redis unavailable (crawler_enqueue may fail, continuing)")

    # Set Redis lock so the in-process scheduler skips jobs while backfill runs
    backfill_lock_key = "ingestion:backfill_running"
    backfill_lock_ttl = 7200  # 2h if script dies
    redis_client = None
    if not state.dry_run:
        try:
            from redis import Redis
            cfg = __import__("app.config", fromlist=["get_config"]).get_config()
            redis_client = Redis.from_url(cfg["settings"].redis_url, decode_responses=True)
            redis_client.setex(backfill_lock_key, backfill_lock_ttl, "1")
            print("  Scheduler paused (backfill lock set).")
        except Exception as e:
            print(f"  WARNING: Could not set backfill lock (scheduler will not auto-pause): {e}")
            redis_client = None

    try:
        # Dependency-ordered phases
        PHASES: list[tuple[str, Callable[[RunState], StepResult]]] = [
            ("rss", _phase_rss),
            ("article_fetcher", _phase_article_fetcher),
            ("reddit_monitor", _phase_reddit_monitor),
            ("youtube_monitor", _phase_youtube_monitor),
            ("crawler_enqueue", _phase_crawler_enqueue),
            ("forum_ingestion", _phase_forum_ingestion),
            ("entity_mentions", _phase_entity_mentions),
            ("entity_sentiment", _phase_entity_sentiment),
            ("article_topics", _phase_article_topics),
            ("ai_summary", _phase_ai_summary),
            ("reddit_trending", _phase_reddit_trending),
            ("youtube_narrative", _phase_youtube_narrative),
            ("narrative_shift", _phase_narrative_shift),
            ("narrative_daily", _phase_narrative_daily),
            ("sahi_strategic_brief", _phase_sahi),
            ("ai_brief_daily", _phase_ai_brief),
        ]

        for phase_name, runner in PHASES:
            if not state.should_run(phase_name):
                print(f"  [{phase_name}] SKIP (--skip)")
                continue
            try:
                r = runner(state)
                state.record(r)
                status = "OK" if r.ok else "FAIL"
                extra = f" | {r.message}" if r.message else ""
                if r.result and r.ok and not state.dry_run:
                    extra = f" | {r.result}"
                print(f"  [{phase_name}] {status} ({r.duration_sec:.1f}s){extra}")
            except SystemExit:
                raise
            except Exception as e:
                r = StepResult(phase_name, False, 0, message=str(e))
                state.record(r)
                print(f"  [{phase_name}] FAIL | {e}")
                if state.strict:
                    sys.exit(1)

        print()
        ok_count, fail_count = state.summary()
        print(f"Summary: {ok_count} ok, {fail_count} failed")
        print("=" * 60)

        if fail_count > 0 and state.strict:
            sys.exit(1)
        sys.exit(0)
    finally:
        if redis_client:
            try:
                redis_client.delete(backfill_lock_key)
                print("  Scheduler resumed (backfill lock cleared).")
            except Exception as e:
                print(f"  WARNING: Could not clear backfill lock: {e}")


if __name__ == "__main__":
    main()
