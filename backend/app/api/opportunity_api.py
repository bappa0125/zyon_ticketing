"""PR opportunity API — topics competitors dominate but client lacks coverage."""
from typing import Optional

from fastapi import APIRouter, Query

from app.services.opportunity_service import detect_pr_opportunities

router = APIRouter(tags=["opportunities"])


@router.get("/opportunities")
async def get_opportunities(
    client: Optional[str] = Query(None, description="Client name, e.g. Sahi"),
):
    """
    Detect PR opportunities: topics where competitors have mentions but client has none.
    Requires client filter.
    """
    if not client or not client.strip():
        return {"opportunities": []}
    opportunities = await detect_pr_opportunities(client.strip())
    return {"opportunities": opportunities}
