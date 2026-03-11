"""Topic Analytics API — aggregate topics from entity_mentions + article_documents.
Uses article_documents.topics (KeyBERT) joined by url."""
from typing import Optional

from fastapi import APIRouter

from app.services.topics_service import get_topics_analytics

router = APIRouter(tags=["topics"])


@router.get("/topics")
async def get_topics(client: Optional[str] = None, range_param: str = "7d"):
    """
    Return topic analytics from entity_mentions + article_documents.
    Topics stored on article_documents (KeyBERT), joined by url.
    ?client=Sahi to filter by client entities.
    ?range_param=24h|7d|30d for time window.
    Returns: topics with mentions, trend_pct, sentiment, by_entity, sample_headlines, action (talk/careful/avoid).
    """
    data = await get_topics_analytics(client=client, range_param=range_param)
    return {"topics": data["topics"], "client": data.get("client"), "competitors": data.get("competitors", []), "range": data.get("range", "7d")}
