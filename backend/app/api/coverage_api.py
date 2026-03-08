"""Competitor coverage comparison API — client vs competitors mention counts."""
from typing import Optional

from fastapi import APIRouter, Query

from app.services.coverage_service import compute_coverage

router = APIRouter(tags=["coverage"])


@router.get("/coverage/competitors")
async def get_coverage_compare(
    client: str = Query(..., description="Client name, e.g. Sahi"),
):
    """
    Compare media coverage: client and competitors.
    Loads entities from clients.yaml, aggregates mentions from media_articles.
    """
    coverage = await compute_coverage(client)
    return {"coverage": coverage}
