import asyncio


async def _main() -> None:
    from app.services.narrative_strategy_reddit_ingest import ingest_reddit_raw

    out = await ingest_reddit_raw()
    print(out)


if __name__ == "__main__":
    asyncio.run(_main())

