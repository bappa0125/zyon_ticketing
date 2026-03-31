import asyncio
import json
from datetime import datetime, timezone


async def main():
    from app.services.narrative_strategy_reddit_ingest import ingest_reddit_raw
    from app.services.narrative_strategy_engine import generate_narrative_strategy_v2

    started = datetime.now(timezone.utc)
    ingest = await ingest_reddit_raw()
    # Persist clusters by running the engine once (LLM on)
    out = await generate_narrative_strategy_v2(company="default", vertical="broker", limit=8, use_llm=True)
    ended = datetime.now(timezone.utc)
    print(
        json.dumps(
            {
                "ok": True,
                "started_at": started.isoformat(),
                "ended_at": ended.isoformat(),
                "ingest": ingest,
                "narratives_returned": len(out),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())

