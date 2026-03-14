#!/usr/bin/env python3
"""Run PR opportunities batch: quote alerts, outreach drafts, competitor responses.
Populates pr_opportunities from entity_mentions + article_documents.
Run manually or via cron. Requires: entity_mentions, article_documents (and pr_daily_snapshots for outreach)."""
import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def _run_all():
    from app.services.pr_opportunities_service import run_pr_opportunities_all_clients
    return await run_pr_opportunities_all_clients()


async def _run_client(client: str):
    from app.services.pr_opportunities_service import run_pr_opportunities_batch
    return await run_pr_opportunities_batch(client)


def main():
    parser = argparse.ArgumentParser(description="Run PR opportunities batch (quote alerts, outreach drafts, competitor responses)")
    parser.add_argument("--client", "-c", help="Run for single client only (default: all)")
    parser.add_argument("--pr-report-first", action="store_true", help="Run pr_report daily snapshot first (needed for outreach targets)")
    parser.add_argument("--backfill-source-domain", action="store_true", help="Run source_domain backfill first (fixes empty outlet data)")
    args = parser.parse_args()

    async def go():
        if args.backfill_source_domain:
            script_dir = Path(__file__).resolve().parent
            backend_dir = script_dir.parent
            backfill_script = script_dir / "backfill_source_domain.py"
            print("Running source_domain backfill...")
            subprocess.run(
                [sys.executable, str(backfill_script), "--force"],
                cwd=str(backend_dir),
                check=True,
            )
        if args.pr_report_first:
            from app.services.pr_report_service import run_daily_snapshot_all_clients
            print("Running pr_report daily snapshot first...")
            r = await run_daily_snapshot_all_clients()
            print("pr_report:", r)
        if args.client:
            result = await _run_client(args.client)
            print(result)
        else:
            result = await _run_all()
            print(result)

    asyncio.run(go())


if __name__ == "__main__":
    main()
