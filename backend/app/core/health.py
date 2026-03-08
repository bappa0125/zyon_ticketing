"""Health check endpoints for liveness and readiness."""
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.config import get_config

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    services: dict[str, str]


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Liveness probe - service is running."""
    return HealthResponse(
        status="ok",
        services={"api": "up"},
    )


@router.get("/health/ready", response_model=HealthResponse)
async def ready(request: Request) -> HealthResponse:
    """Readiness probe - all dependencies available."""
    config = get_config()
    services: dict[str, str] = {"api": "up"}

    # Check MongoDB
    try:
        from app.services.mongodb import get_mongo_client
        client = await get_mongo_client()
        await client.admin.command("ping")
        services["mongodb"] = "up"
    except Exception:
        services["mongodb"] = "down"

    # Check Redis
    try:
        from app.services.redis_client import get_redis
        redis = await get_redis()
        await redis.ping()
        services["redis"] = "up"
    except Exception:
        services["redis"] = "down"

    # Check Qdrant
    try:
        from app.services.qdrant_service import get_qdrant
        qdrant = await get_qdrant()
        qdrant.get_collections()
        services["qdrant"] = "up"
    except Exception:
        services["qdrant"] = "down"

    all_up = all(s == "up" for s in services.values())
    return HealthResponse(
        status="ok" if all_up else "degraded",
        services=services,
    )
