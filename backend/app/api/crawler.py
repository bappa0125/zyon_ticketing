"""Crawler API - competitors, test crawl."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.mongodb import get_mongo_client
from app.services.crawler.snapshot_store import create_competitor, get_competitors
from app.services.crawler.crawler import crawl_url
from app.services.crawler.scheduler import enqueue_crawls

router = APIRouter(prefix="/crawler", tags=["crawler"])


class CompetitorCreate(BaseModel):
    name: str
    website: str
    tracking_rules: list[str] | None = None


@router.get("/test")
async def test_crawl(url: str = "https://example.com"):
    """Test endpoint: crawl a sample page and return extracted text. Uses Playwright if available, else httpx."""
    try:
        html, text = crawl_url(url)
        return {"url": url, "text_preview": text[:2000], "text_length": len(text)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/competitors")
async def add_competitor(body: CompetitorCreate):
    """Register a competitor to monitor."""
    cid = await create_competitor(body.name, body.website, body.tracking_rules)
    return {"id": cid, "name": body.name, "website": body.website}


@router.get("/competitors")
async def list_competitors():
    """List all monitored competitors."""
    return await get_competitors()


@router.post("/crawl/trigger")
async def trigger_crawls():
    """Manually trigger crawl jobs for all competitors."""
    enqueue_crawls()
    return {"status": "enqueued"}
