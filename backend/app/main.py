"""FastAPI application entry point."""
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, history
from app.core.logging import setup_logging, get_logger
from app.core.health import router as health_router
from app.core.metrics import router as metrics_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Starting AI Chatbot API")
    # Initialize MongoDB connection before handling requests
    from app.services.mongodb import get_mongo_client
    await get_mongo_client()
    yield
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


app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(history.router, prefix="/api", tags=["history"])
app.include_router(health_router, tags=["health"])
app.include_router(metrics_router, tags=["metrics"])


@app.get("/")
async def root():
    return {"service": "zyon-chatbot", "status": "ok"}
