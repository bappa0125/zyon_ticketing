"""Media search API — POST /api/media/search. Uses MongoDB media_articles only."""
import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.logging import get_logger
from app.services.media_article_search import search as media_article_search

router = APIRouter()
logger = get_logger(__name__)


class MediaSearchRequest(BaseModel):
    query: str


@router.post("/media/trigger-index")
async def trigger_media_index():
    """Trigger RSS ingestion + article fetcher (replaces removed media_ingestion)."""
    from app.services.monitoring_ingestion.rss_ingestion import run_rss_ingestion
    from app.services.monitoring_ingestion.article_fetcher import run_article_fetcher

    rss_result = await run_rss_ingestion()
    fetcher_result = await run_article_fetcher()
    return {
        "rss_inserted": rss_result.get("fresh_items_inserted", 0),
        "articles_fetched": fetcher_result.get("articles_fetched", 0),
    }


@router.post("/media/trigger-initial")
async def trigger_initial_ingestion():
    """Alias for trigger_media_index — runs RSS + article fetcher once."""
    return await trigger_media_index()


@router.post("/media/search")
async def media_search(request: MediaSearchRequest):
    """Search media_articles via MongoDB. Returns top 10 articles."""
    query = (request.query or "").strip()
    if not query:
        return {"results": [], "message": "query required"}
    try:
        results = await asyncio.to_thread(media_article_search, query, 10, True)
        try:
            from redis import Redis
            from app.config import get_config
            r = Redis.from_url(get_config()["settings"].redis_url)
            r.incr("media_index:media_search_requests")
        except Exception:
            pass
        return {"results": results, "count": len(results)}
    except Exception as e:
        logger.warning("media_search_failed", query=query, error=str(e))
        return {"results": [], "error": str(e)}
