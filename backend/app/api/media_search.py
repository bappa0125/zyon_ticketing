"""Media index search API - POST /api/media/search."""
import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.logging import get_logger
from app.services.media_index import article_search

router = APIRouter()
logger = get_logger(__name__)


class MediaSearchRequest(BaseModel):
    query: str


@router.post("/media/trigger-index")
async def trigger_media_index():
    """Manually trigger incremental media ingestion."""
    import asyncio
    from app.services.media_ingestion.ingestion_scheduler import run_incremental_ingestion
    count = await asyncio.to_thread(run_incremental_ingestion)
    return {"indexed": count}


@router.post("/media/trigger-initial")
async def trigger_initial_ingestion():
    """Run initial ingestion: all sources, up to 200 articles per source."""
    import asyncio
    from app.services.media_ingestion.ingestion_scheduler import run_initial_ingestion
    count = await asyncio.to_thread(run_initial_ingestion)
    return {"indexed": count}


@router.post("/media/search")
async def media_search(request: MediaSearchRequest):
    """Search internal media index. Returns top 10 articles."""
    query = (request.query or "").strip()
    if not query:
        return {"results": [], "message": "query required"}
    try:
        results = await asyncio.to_thread(article_search.search, query, limit=10)
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
