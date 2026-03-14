"""PR opportunity API — topic gaps + LLM opportunities (quote alerts, outreach drafts, competitor responses)."""
from typing import Optional

from fastapi import APIRouter, Query

from app.services.opportunity_service import detect_pr_opportunities
from app.services.pr_opportunities_service import get_pr_opportunities, run_pr_opportunities_all_clients

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


@router.get("/opportunities/pr-intel")
async def get_opportunities_pr_intel(
    client: str = Query(..., description="Client name"),
    days: int = Query(7, ge=1, le=30, description="Days of history"),
):
    """
    Fetch LLM-generated PR opportunities: quote alerts, outreach drafts, competitor response angles.
    Data from batch job (pr_opportunities collection).
    """
    if not client or not client.strip():
        return {"quote_alerts": [], "outreach_drafts": [], "competitor_responses": []}
    return await get_pr_opportunities(client.strip(), days=days)


@router.post("/opportunities/run-batch")
async def run_opportunities_batch(client: Optional[str] = Query(None, description="Run for single client only (default: all)")):
    """Trigger PR opportunities batch (quote alerts, outreach drafts, competitor responses)."""
    from app.services.pr_opportunities_service import run_pr_opportunities_batch
    if client and client.strip():
        result = await run_pr_opportunities_batch(client.strip())
        return {"client": client.strip(), **result}
    return await run_pr_opportunities_all_clients()
