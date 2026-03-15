"""Competitor coverage comparison API — client vs competitors mention counts."""
from fastapi import APIRouter, Query

from app.services.coverage_service import (
    compute_coverage,
    get_article_counts,
    get_competitor_only_articles,
    get_mentions_client_and_competitors,
)
from app.services.coverage_pr_summary_service import get_latest_summary

router = APIRouter(tags=["coverage"])


@router.get("/coverage/article-counts")
async def get_counts(
    client: str = Query(..., description="Client name, e.g. Sahi"),
):
    """
    Total article_documents, count with client in entities, competitor-only count.
    Explains why competitor-only may be lower than total (entities set only at insert by article_fetcher).
    """
    return await get_article_counts(client)


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


@router.get("/coverage/competitor-only-articles")
async def get_competitor_only(
    client: str = Query(..., description="Client name, e.g. Sahi"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Articles where only competitors are mentioned (client not in entities).
    Entity detection runs on title + summary/text; these docs have entities = e.g. [Zerodha, Upstox] with no client.
    """
    result = await get_competitor_only_articles(client, limit=limit)
    return result


@router.get("/coverage/mentions")
async def get_mentions(
    client: str = Query(..., description="Client name, e.g. Sahi"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Mentions of client and competitors (entity_mentions): articles where any of these entities appear.
    For the second table: client + competitor mentions with title, summary, journalist (author).
    """
    return await get_mentions_client_and_competitors(client, limit=limit)


@router.get("/coverage/pr-summary")
async def get_pr_summary(
    client: str = Query(..., description="Client name, e.g. Sahi"),
):
    """
    Latest coverage PR summary for the client (LLM-generated once per day).
    Summarizes Sahi/client coverage, competitor coverage, and actionable intel for the PR team.
    """
    return await get_latest_summary(client)
