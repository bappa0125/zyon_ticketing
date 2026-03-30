import asyncio


async def _main() -> None:
    from app.services.reddit_trending_service import run_reddit_trending_social_ingest

    out = await run_reddit_trending_social_ingest()
    print(out)


if __name__ == "__main__":
    asyncio.run(_main())

