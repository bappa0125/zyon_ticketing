"""URL Discovery API - POST /api/url-search."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.url_discovery.url_agent import discover_urls

router = APIRouter(prefix="/url-search", tags=["url-search"])


class UrlSearchRequest(BaseModel):
    query: str
    summarise: bool = False


@router.post("")
async def url_search(req: UrlSearchRequest):
    """
    Search for URLs where a company/topic is mentioned.
    Returns verified links with title, source, snippet.
    """
    if not req.query or len(req.query.strip()) < 2:
        raise HTTPException(status_code=400, detail="query required (min 2 chars)")

    result = discover_urls(
        company_or_topic=req.query.strip(),
        summarise=req.summarise,
    )

    if "error" in result:
        raise HTTPException(status_code=429, detail=result["error"])

    return {
        "results": result.get("results", []),
        "cached": result.get("cached", False),
        "summary": result.get("summary"),
    }
