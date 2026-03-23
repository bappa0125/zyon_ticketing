"""Clients API - monitored clients and competitors."""
from typing import Any

from fastapi import APIRouter

from app.core.client_config_loader import (
    get_client_profile,
    get_competitor_names,
    load_clients,
)

router = APIRouter(tags=["clients"])


@router.get("/clients")
async def get_clients():
    """
    Return monitored clients with domain, competitors, and profile (vertical + features).
    Omitted YAML fields use defaults (see client_config_loader.DEFAULT_*).
    Cached in Redis (TTL 300s).
    """
    raw = await load_clients()
    clients = []
    for c in raw:
        name = (c.get("name") or "").strip()
        row: dict[str, Any] = {
            "name": name,
            "domain": (c.get("domain") or "").strip(),
            "competitors": get_competitor_names(c),
        }
        profile = get_client_profile(c)
        row["vertical"] = profile["vertical"]
        row["features"] = profile["features"]
        tz = c.get("report_timezone")
        if isinstance(tz, str) and tz.strip():
            row["report_timezone"] = tz.strip()
        clients.append(row)
    return {"clients": clients}
