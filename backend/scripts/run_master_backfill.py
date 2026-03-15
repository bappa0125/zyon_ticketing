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
  --only PHASE      Run only this phase (e.g. --only forum_ingestion). All others skipped.
  --skip PHASE      Skip phase(s): rss, article_fetcher, forum_ingestion, entity_mentions, etc.
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
    only_phase: str | None = None  # if set, run only this phase (canonical name)

    def should_run(self, phase: str) -> bool:
        if self.only_phase is not None:
            return phase == self.only_phase
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


# --- Async phase runners: all run in one event loop to avoid "Event loop is closed" ---

async def _phase_rss_async(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("rss", True, 0, "dry-run")
    try:
        from app.services.monitoring_ingestion.rss_ingestion import run_rss_ingestion
        cfg = __import__("app.config", fromlist=["get_config"]).get_config()
        max_feeds = (cfg.get("scheduler") or {}).get("rss_max_feeds_per_run", 20)
        result = await run_rss_ingestion(max_feeds=max_feeds)
        return StepResult("rss", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("rss", False, time.monotonic() - start, message=str(e))


async def _phase_article_fetcher_async(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("article_fetcher", True, 0, "dry-run")
    try:
        from app.services.monitoring_ingestion.article_fetcher import run_article_fetcher
        cfg = __import__("app.config", fromlist=["get_config"]).get_config()
        max_items = (cfg.get("scheduler") or {}).get("article_fetcher_max_items_per_run", 40)
        result = await run_article_fetcher(max_items=max_items)
        return StepResult("article_fetcher", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("article_fetcher", False, time.monotonic() - start, message=str(e))


async def _phase_entity_mentions_async(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("entity_mentions", True, 0, "dry-run")
    try:
        from app.services.entity_mentions_worker import run_entity_mentions_pipeline
        cfg = __import__("app.config", fromlist=["get_config"]).get_config()
        batch = (cfg.get("scheduler") or {}).get("entity_mentions_batch_size", 150)
        result = await run_entity_mentions_pipeline(batch_size=batch)
        return StepResult("entity_mentions", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("entity_mentions", False, time.monotonic() - start, message=str(e))


async def _phase_entity_sentiment_async(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("entity_sentiment", True, 0, "dry-run")
    try:
        from app.services.entity_mentions_sentiment_worker import run_entity_mentions_sentiment
        result = await run_entity_mentions_sentiment(batch_size=50)
        return StepResult("entity_sentiment", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("entity_sentiment", False, time.monotonic() - start, message=str(e))


async def _phase_article_topics_async(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("article_topics", True, 0, "dry-run")
    try:
        from app.services.article_topics_worker import run_article_topics_pipeline
        cfg = __import__("app.config", fromlist=["get_config"]).get_config()
        batch = (cfg.get("scheduler") or {}).get("article_topics_batch_size", 30)
        result = await run_article_topics_pipeline(batch_size=batch)
        return StepResult("article_topics", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("article_topics", False, time.monotonic() - start, message=str(e))


async def _phase_ai_summary_async(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("ai_summary", True, 0, "dry-run")
    try:
        from app.services.ai_summary_worker import run_ai_summary_worker
        result = await run_ai_summary_worker()
        return StepResult("ai_summary", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("ai_summary", False, time.monotonic() - start, message=str(e))


async def _phase_reddit_monitor_async(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("reddit_monitor", True, 0, "dry-run")
    try:
        from app.services.reddit_worker import run_reddit_monitor
        result = await run_reddit_monitor()
        return StepResult("reddit_monitor", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("reddit_monitor", False, time.monotonic() - start, message=str(e))


async def _phase_youtube_monitor_async(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("youtube_monitor", True, 0, "dry-run")
    try:
        from app.services.youtube_worker import run_youtube_monitor
        result = await run_youtube_monitor()
        return StepResult("youtube_monitor", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("youtube_monitor", False, time.monotonic() - start, message=str(e))


def _phase_crawler_enqueue_sync(state: RunState) -> StepResult:
    """Sync phase (no MongoDB/Redis in hot path)."""
    start = time.monotonic()
    if state.dry_run:
        return StepResult("crawler_enqueue", True, 0, "dry-run")
    try:
        from app.services.crawler.scheduler import enqueue_crawls
        enqueue_crawls(max_per_run=10)
        return StepResult("crawler_enqueue", True, time.monotonic() - start)
    except Exception as e:
        return StepResult("crawler_enqueue", False, time.monotonic() - start, message=str(e))


async def _phase_forum_ingestion_async(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("forum_ingestion", True, 0, "dry-run")
    try:
        from app.services.forum_ingestion_worker import run_forum_ingestion
        result = await run_forum_ingestion()
        return StepResult("forum_ingestion", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("forum_ingestion", False, time.monotonic() - start, message=str(e))


async def _phase_reddit_trending_async(state: RunState) -> StepResult:
    cfg = __import__("app.config", fromlist=["get_config"]).get_config()
    if not (cfg.get("reddit_trending") or {}).get("enabled", False):
        return StepResult("reddit_trending", True, 0, "skipped (disabled in config)")
    start = time.monotonic()
    if state.dry_run:
        return StepResult("reddit_trending", True, 0, "dry-run")
    try:
        from app.services.reddit_trending_service import run_reddit_trending_pipeline
        result = await run_reddit_trending_pipeline()
        return StepResult("reddit_trending", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("reddit_trending", False, time.monotonic() - start, message=str(e))


async def _phase_youtube_narrative_async(state: RunState) -> StepResult:
    cfg = __import__("app.config", fromlist=["get_config"]).get_config()
    yt = cfg.get("youtube_trending") or {}
    if not (isinstance(yt, dict) and yt.get("enabled", False)):
        return StepResult("youtube_narrative", True, 0, "skipped (disabled in config)")
    start = time.monotonic()
    if state.dry_run:
        return StepResult("youtube_narrative", True, 0, "dry-run")
    try:
        from app.services.youtube_trending_service import run_youtube_narrative_pipeline
        result = await run_youtube_narrative_pipeline()
        return StepResult("youtube_narrative", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("youtube_narrative", False, time.monotonic() - start, message=str(e))


async def _phase_narrative_shift_async(state: RunState) -> StepResult:
    cfg = __import__("app.config", fromlist=["get_config"]).get_config()
    ns = cfg.get("narrative_shift") or {}
    if not (isinstance(ns, dict) and ns.get("enabled", False)):
        return StepResult("narrative_shift", True, 0, "skipped (disabled in config)")
    start = time.monotonic()
    if state.dry_run:
        return StepResult("narrative_shift", True, 0, "dry-run")
    try:
        from app.services.narrative_shift_service import run_narrative_shift_pipeline
        result = await run_narrative_shift_pipeline()
        return StepResult("narrative_shift", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("narrative_shift", False, time.monotonic() - start, message=str(e))


async def _phase_narrative_daily_async(state: RunState) -> StepResult:
    cfg = __import__("app.config", fromlist=["get_config"]).get_config()
    nid = cfg.get("narrative_intelligence_daily") or {}
    if not (isinstance(nid, dict) and nid.get("enabled", False)):
        return StepResult("narrative_daily", True, 0, "skipped (disabled in config)")
    start = time.monotonic()
    if state.dry_run:
        return StepResult("narrative_daily", True, 0, "dry-run")
    try:
        from app.services.narrative_intelligence_daily_service import run_daily_synthesis
        result = await run_daily_synthesis()
        return StepResult("narrative_daily", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("narrative_daily", False, time.monotonic() - start, message=str(e))


async def _phase_ai_search_narrative_async(state: RunState) -> StepResult:
    cfg = __import__("app.config", fromlist=["get_config"]).get_config()
    asc = cfg.get("ai_search_narrative") or {}
    if not (isinstance(asc, dict) and asc.get("enabled", False)):
        return StepResult("ai_search_narrative", True, 0, "skipped (disabled in config)")
    start = time.monotonic()
    if state.dry_run:
        return StepResult("ai_search_narrative", True, 0, "dry-run")
    try:
        from app.services.ai_search_narrative_service import run_ai_search_narrative_pipeline
        result = await run_ai_search_narrative_pipeline()
        return StepResult("ai_search_narrative", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("ai_search_narrative", False, time.monotonic() - start, message=str(e))


async def _phase_ai_search_visibility_async(state: RunState) -> StepResult:
    cfg = __import__("app.config", fromlist=["get_config"]).get_config()
    vis = cfg.get("ai_search_visibility") or {}
    if not (isinstance(vis, dict) and vis.get("enabled", False)):
        return StepResult("ai_search_visibility", True, 0, "skipped (disabled in config)")
    start = time.monotonic()
    if state.dry_run:
        return StepResult("ai_search_visibility", True, 0, "dry-run")
    try:
        from app.services.ai_search_visibility_service import run_visibility_pipeline
        result = await run_visibility_pipeline()
        return StepResult("ai_search_visibility", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("ai_search_visibility", False, time.monotonic() - start, message=str(e))


async def _phase_coverage_summary_async(state: RunState) -> StepResult:
    """Coverage PR summary: 1 LLM call per client per day; summarizes page results for PR team."""
    start = time.monotonic()
    if state.dry_run:
        return StepResult("coverage_summary", True, 0, "dry-run")
    try:
        from app.services.coverage_pr_summary_service import run_coverage_pr_summary_batch
        result = await run_coverage_pr_summary_batch()
        return StepResult("coverage_summary", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("coverage_summary", False, time.monotonic() - start, message=str(e))


async def _phase_sahi_async(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("sahi_strategic_brief", True, 0, "dry-run")
    try:
        from app.services.sahi_strategic_brief_service import run_sahi_strategic_brief_daily
        result = await run_sahi_strategic_brief_daily()
        return StepResult("sahi_strategic_brief", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("sahi_strategic_brief", False, time.monotonic() - start, message=str(e))


async def _phase_ai_brief_async(state: RunState) -> StepResult:
    start = time.monotonic()
    if state.dry_run:
        return StepResult("ai_brief_daily", True, 0, "dry-run")
    try:
        from app.api.reports_api import run_ai_brief_daily
        result = await run_ai_brief_daily()
        return StepResult("ai_brief_daily", True, time.monotonic() - start, result=str(result))
    except Exception as e:
        return StepResult("ai_brief_daily", False, time.monotonic() - start, message=str(e))


async def _phase_executive_competitor_report_async(state: RunState) -> StepResult:
    """Build and store Executive Competitor Intelligence report (no LLM). Runs after all data phases."""
    start = time.monotonic()
    if state.dry_run:
        return StepResult("executive_competitor_report", True, 0, "dry-run")
    try:
        from app.services.executive_report_service import build_and_save_executive_report
        result = await build_and_save_executive_report(range_param="7d")
        ok = result.get("ok", False)
        return StepResult(
            "executive_competitor_report",
            ok,
            time.monotonic() - start,
            result=str(result),
            message=result.get("reason", "") if not ok else "",
        )
    except Exception as e:
        return StepResult("executive_competitor_report", False, time.monotonic() - start, message=str(e))


def main():
    parser = argparse.ArgumentParser(description="Master backfill – run all ingestion jobs in order")
    parser.add_argument("--strict", action="store_true", help="Exit on first failure")
    parser.add_argument("--dry-run", action="store_true", help="Print phases only, do not run")
    parser.add_argument("--only", type=str, default=None, metavar="PHASE", help="Run only this phase (e.g. forum_ingestion)")
    parser.add_argument("--skip", action="append", default=[], help="Skip phase (repeat for multiple)")
    parser.add_argument("--skip-deps", action="store_true", help="Skip Redis/Qdrant preflight checks")
    args = parser.parse_args()

    # Resolve --only to canonical phase name
    only_phase = None
    if args.only and args.only.strip():
        only_raw = args.only.strip().lower()
        ONLY_ALIASES = {
            "forum": "forum_ingestion",
            "forum_ingestion": "forum_ingestion",
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
            "narrative_shift": "narrative_shift",
            "narrative_daily": "narrative_daily",
            "ai_search_narrative": "ai_search_narrative",
            "ai_search_visibility": "ai_search_visibility",
            "coverage_summary": "coverage_summary",
            "sahi": "sahi_strategic_brief",
            "sahi_strategic_brief": "sahi_strategic_brief",
            "ai_brief": "ai_brief_daily",
            "ai_brief_daily": "ai_brief_daily",
            "crawler": "crawler_enqueue",
            "crawler_enqueue": "crawler_enqueue",
            "executive_report": "executive_competitor_report",
            "executive_competitor_report": "executive_competitor_report",
        }
        only_phase = ONLY_ALIASES.get(only_raw, only_raw)

    state = RunState(
        strict=args.strict,
        dry_run=args.dry_run,
        skip={s.strip().lower() for s in args.skip if s.strip()},
        skip_deps=args.skip_deps,
        only_phase=only_phase,
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
        "ai_search_narrative": "ai_search_narrative",
        "ai_search_visibility": "ai_search_visibility",
        "coverage_summary": "coverage_summary",
        "sahi": "sahi_strategic_brief",
        "ai_brief": "ai_brief_daily",
        "ai_brief_daily": "ai_brief_daily",
        "crawler": "crawler_enqueue",
        "crawler_enqueue": "crawler_enqueue",
        "forum": "forum_ingestion",
        "forum_ingestion": "forum_ingestion",
        "executive_report": "executive_competitor_report",
        "executive_competitor_report": "executive_competitor_report",
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
        asyncio.run(_run_all_async(state))
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


async def _run_all_async(state: RunState) -> None:
    """Run all phases in a single event loop to avoid 'Event loop is closed'."""
    # Preflight
    if not state.dry_run:
        print("Preflight: Checking MongoDB...")
        ok = await check_mongodb()
        if not ok:
            print("  MongoDB is required. Exiting.")
            raise SystemExit(1)
        print("  MongoDB OK")
    if not state.skip_deps and not state.dry_run:
        redis_ok = await check_redis()
        if redis_ok:
            print("  Redis OK")
        else:
            print("  Redis unavailable (crawler_enqueue may fail, continuing)")

    # Phases: (name, async_runner or sync_runner). Sync runners return StepResult; async are awaited.
    PHASES: list[tuple[str, Callable]] = [
        ("rss", _phase_rss_async),
        ("article_fetcher", _phase_article_fetcher_async),
        ("reddit_monitor", _phase_reddit_monitor_async),
        ("youtube_monitor", _phase_youtube_monitor_async),
        ("crawler_enqueue", _phase_crawler_enqueue_sync),
        ("forum_ingestion", _phase_forum_ingestion_async),
        ("entity_mentions", _phase_entity_mentions_async),
        ("entity_sentiment", _phase_entity_sentiment_async),
        ("article_topics", _phase_article_topics_async),
        ("ai_summary", _phase_ai_summary_async),
        ("reddit_trending", _phase_reddit_trending_async),
        ("youtube_narrative", _phase_youtube_narrative_async),
        ("narrative_shift", _phase_narrative_shift_async),
        ("narrative_daily", _phase_narrative_daily_async),
        ("ai_search_narrative", _phase_ai_search_narrative_async),
        ("ai_search_visibility", _phase_ai_search_visibility_async),
        ("coverage_summary", _phase_coverage_summary_async),
        ("sahi_strategic_brief", _phase_sahi_async),
        ("ai_brief_daily", _phase_ai_brief_async),
        ("executive_competitor_report", _phase_executive_competitor_report_async),
    ]

    phase_names = [p for p, _ in PHASES]
    if state.only_phase and state.only_phase not in phase_names:
        print(f"  ERROR: --only '{state.only_phase}' is not a valid phase. Valid: {', '.join(phase_names)}")
        raise SystemExit(1)

    for phase_name, runner in PHASES:
        if not state.should_run(phase_name):
            reason = "--only" if state.only_phase else "--skip"
            print(f"  [{phase_name}] SKIP ({reason})")
            continue
        try:
            if asyncio.iscoroutinefunction(runner):
                r = await runner(state)
            else:
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
                raise SystemExit(1)


if __name__ == "__main__":
    main()
