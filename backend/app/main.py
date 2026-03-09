"""FastAPI application entry point."""
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.api import chat, history, crawler, system_metrics, url_search, media_search, coverage, clients_api, media_api, sentiment_api, topics_api, coverage_api, opportunity_api, social_api
from app.core.logging import setup_logging, get_logger
from app.core.health import router as health_router
from app.core.metrics import router as metrics_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Starting AI Chatbot API")
    from app.config import get_config
    cfg = get_config()
    key = cfg["settings"].openrouter_api_key
    logger.info("OPENROUTER_API_KEY: set=%s", bool(key and len(key) > 10))
    if not key or len(key) < 10:
        logger.warning("OPENROUTER_API_KEY is missing or too short - chat will fail. Set it in .env and restart.")
    from app.services.mongodb import get_mongo_client
    await get_mongo_client()
    from app.core.social_posts_indexes import ensure_social_posts_indexes
    from app.core.ingestion_indexes import ensure_ingestion_indexes
    await ensure_social_posts_indexes()
    await ensure_ingestion_indexes()
    from app.core.ingestion_scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("Shutting down AI Chatbot API")


app = FastAPI(
    title="Zyon AI Chatbot API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Stream test must be registered first to avoid conflicts
async def _stream_test_gen():
    yield "stream "
    yield "ok"


@app.get("/api/stream-test", include_in_schema=False)
async def stream_test():
    return StreamingResponse(
        _stream_test_gen(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no"},
    )


app.include_router(chat.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(crawler.router, prefix="/api")
app.include_router(url_search.router, prefix="/api")
app.include_router(media_search.router, prefix="/api")
app.include_router(coverage.router, prefix="/api")
app.include_router(clients_api.router, prefix="/api")
app.include_router(media_api.router, prefix="/api")
app.include_router(sentiment_api.router, prefix="/api")
app.include_router(topics_api.router, prefix="/api")
app.include_router(coverage_api.router, prefix="/api")
app.include_router(opportunity_api.router, prefix="/api")
app.include_router(social_api.router, prefix="/api")
app.include_router(system_metrics.router)
app.include_router(health_router, tags=["health"])
app.include_router(metrics_router, tags=["metrics"])


@app.get("/")
async def root():
    return {"service": "zyon-chatbot", "status": "ok"}
