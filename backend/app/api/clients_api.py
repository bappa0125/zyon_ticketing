"""Clients API - monitored clients and competitors."""
from fastapi import APIRouter

from app.core.client_config_loader import load_clients

router = APIRouter(tags=["clients"])


@router.get("/clients")
async def get_clients():
    """
    Return monitored clients with domain and competitors.
    Cached in Redis (TTL 300s).
    """
    clients = await load_clients()
    return {"clients": clients}
