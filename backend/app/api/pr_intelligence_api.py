"""PR Intelligence API — topic-article mapping, first mention, amplifier, journalist-outlet.
No LLM; uses KeyBERT topics from article_documents."""
from typing import Optional

from fastapi import APIRouter, Query

from app.services.pr_intelligence_service import (
    get_topic_article_mapping,
    get_first_mentions,
    get_amplifiers,
    get_journalist_outlet_index,
)

router = APIRouter(tags=["pr-intelligence"])


@router.get("/pr-intelligence/topic-articles")
async def api_topic_articles(
    client: str = Query(..., description="Client name, e.g. Sahi"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
    topic: Optional[str] = Query(None, description="Filter topics by substring"),
    limit_per_topic: int = Query(20, ge=1, le=100, description="Max articles per topic"),
):
    """Map topics to articles. Uses KeyBERT topics from article_documents."""
    return await get_topic_article_mapping(
        client=client,
        range_param=range_param,
        topic_filter=topic,
        limit_per_topic=limit_per_topic,
    )


@router.get("/pr-intelligence/first-mentions")
async def api_first_mentions(
    client: str = Query(..., description="Client name"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
    topic: Optional[str] = Query(None, description="Filter by topic substring"),
    entity: Optional[str] = Query(None, description="Filter by entity"),
):
    """First mention per (topic, entity): earliest article and its author."""
    return await get_first_mentions(
        client=client,
        range_param=range_param,
        topic_filter=topic,
        entity_filter=entity,
    )


@router.get("/pr-intelligence/amplifiers")
async def api_amplifiers(
    client: str = Query(..., description="Client name"),
    topic: str = Query(..., description="Topic to analyze"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
    entity: Optional[str] = Query(None, description="Filter by entity"),
):
    """Amplifiers: articles after first mention, grouped by author and outlet."""
    return await get_amplifiers(
        client=client,
        topic=topic,
        range_param=range_param,
        entity_filter=entity,
    )


@router.get("/pr-intelligence/journalist-outlets")
async def api_journalist_outlets(
    client: str = Query(..., description="Client name"),
    range_param: str = Query("30d", alias="range", description="24h | 7d | 30d"),
):
    """Journalist → outlets index from article_documents and entity_mentions."""
    return await get_journalist_outlet_index(
        client=client,
        range_param=range_param,
    )
