"""Clients API - monitored clients and competitors."""
from fastapi import APIRouter

from app.core.client_config_loader import get_competitor_names, load_clients

router = APIRouter(tags=["clients"])


@router.get("/clients")
async def get_clients():
    """
    Return monitored clients with domain and competitors (names only for backward compat).
    Cached in Redis (TTL 300s).
    """
    raw = await load_clients()
    clients = []
    for c in raw:
        clients.append({
            "name": (c.get("name") or "").strip(),
            "domain": (c.get("domain") or "").strip(),
            "competitors": get_competitor_names(c),
        })
    return {"clients": clients}
