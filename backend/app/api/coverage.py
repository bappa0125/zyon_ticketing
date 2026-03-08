"""Media coverage API - alerts, timeline, compare, topics."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from app.config import get_config
from pydantic import BaseModel

from app.services.media_intelligence.alerts import get_alerts

router = APIRouter()


def _get_media_articles():
    from pymongo import MongoClient
    cfg = get_config()
    client = MongoClient(cfg["settings"].mongodb_url)
    db = client[cfg["mongodb"].get("database", "chat")]
    return db["media_articles"]


def _normalize_entity(e: str) -> str:
    """Normalize entity for comparison (entities vs entities_detected)."""
    return (e or "").strip()


@router.get("/alerts")
async def api_alerts(
    company: Optional[str] = Query(None, description="Filter by company"),
    limit: int = Query(50, ge=1, le=200),
):
    """Get mention alerts."""
    alerts = get_alerts(company=company, limit=limit)
    return {"alerts": alerts}


class TimelineItem(BaseModel):
    date: str
    count: int


def _date_str(v) -> Optional[str]:
    """Convert publish_date to YYYY-MM-DD."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, str) and len(v) >= 10:
        return v[:10]
    return None


@router.get("/coverage/timeline")
async def api_coverage_timeline(
    company: str = Query(..., description="Company name"),
):
    """Mention counts grouped by date."""
    coll = _get_media_articles()
    match_company = {"$regex": company, "$options": "i"}
    q = {"$or": [{"entities_detected": match_company}, {"entities": match_company}]}
    cursor = coll.find(q)
    by_day: dict[str, int] = {}
    for doc in cursor:
        dt = doc.get("publish_date") or doc.get("timestamp_indexed")
        dstr = _date_str(dt)
        if dstr:
            by_day[dstr] = by_day.get(dstr, 0) + 1
    mentions_by_day = [{"date": k, "count": v} for k, v in sorted(by_day.items())]
    return {"company": company, "mentions_by_day": mentions_by_day}


class CompareResponse(BaseModel):
    pass


@router.get("/coverage/compare")
async def api_coverage_compare(
    companies: str = Query(..., description="Comma-separated company names"),
):
    """Mention count per company."""
    names = [c.strip() for c in companies.split(",") if c.strip()]
    coll = _get_media_articles()
    counts = {}
    for company in names:
        n = coll.count_documents({"$or": [{"entities_detected": {"$regex": company, "$options": "i"}}, {"entities": {"$regex": company, "$options": "i"}}]})
        counts[company] = n
    return counts


@router.get("/coverage/topics")
async def api_coverage_topics(
    company: str = Query(..., description="Company name"),
    top_n: int = Query(10, ge=1, le=50),
):
    """Trending topics (keywords) for a company."""
    import re
    coll = _get_media_articles()
    match_company = {"$regex": company, "$options": "i"}
    q = {"$or": [{"entities_detected": match_company}, {"entities": match_company}]}
    cursor = coll.find(q)
    stopwords = {"the", "and", "for", "with", "from", "that", "this", "has", "have", "are", "was", "were", "its", "said", "per", "will", "can", "not", "but", "they", "their"}
    freq = {}
    for doc in cursor:
        text = f"{doc.get('title','')} {doc.get('content','')} {doc.get('content_preview','')}".lower()
        words = re.findall(r"\b[a-z]{5,}\b", text)
        for w in words:
            if w not in stopwords and not w.isdigit():
                freq[w] = freq.get(w, 0) + 1
    sorted_words = sorted(freq.items(), key=lambda x: -x[1])[:top_n]
    topics = [w for w, _ in sorted_words]
    return {"company": company, "topics": topics}
