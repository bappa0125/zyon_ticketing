"""Media Intelligence dashboard API — single endpoint for dashboard data."""
from typing import Optional

from fastapi import APIRouter, Query

from app.services.media_intelligence_service import get_dashboard

router = APIRouter(tags=["media-intelligence"])


@router.get("/media-intelligence/dashboard")
async def api_media_intelligence_dashboard(
    client: str = Query(..., description="Primary client name, e.g. Sahi"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
    domain: Optional[str] = Query(None, description="Filter feed and coverage by source domain, e.g. moneycontrol.com"),
    content_quality: Optional[str] = Query(None, description="Filter feed by content depth: full_text | snippet"),
):
    """
    Return dashboard data: coverage, feed, timeline, top publications, topics, by_domain.
    """
    data = await get_dashboard(
        client=client,
        range_param=range_param,
        domain_filter=domain,
        content_quality=content_quality,
    )
    return data
