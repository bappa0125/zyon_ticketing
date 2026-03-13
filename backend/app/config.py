"""Configuration loader - reads from config YAML and env vars."""
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


def _get_config_dir() -> Path:
    project_root = Path(__file__).resolve().parent.parent.parent
    config_dir = project_root / "config"
    if not config_dir.exists():
        config_dir = Path("/app/config")
    return config_dir


def load_yaml(env: str) -> dict[str, Any]:
    config_dir = _get_config_dir()
    path = config_dir / f"{env}.yaml"
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def load_monitoring_yaml() -> dict[str, Any]:
    """Load config/monitoring.yaml. Used for social data guardrails."""
    config_dir = _get_config_dir()
    path = config_dir / "monitoring.yaml"
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


class Settings(BaseSettings):
    app_env: str = Field(default="dev", alias="APP_ENV")
    mongodb_url: str = Field(default="mongodb://mongodb:27017", alias="MONGODB_URL")
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    qdrant_url: str = Field(default="http://qdrant:6333", alias="QDRANT_URL")
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="openrouter/free", alias="OPENROUTER_MODEL")
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    hf_token: str = Field(default="", alias="HF_TOKEN")
    mock_llm: bool = Field(default=False, alias="MOCK_LLM")
    apify_api_key: str = Field(default="", alias="APIFY_API_KEY")
    youtube_api_key: str = Field(default="", alias="YOUTUBE_API_KEY")

    class Config:
        env_file = ".env"
        extra = "ignore"


def get_config() -> dict[str, Any]:
    settings = Settings()
    base = load_yaml(settings.app_env)
    return {
        "app": base.get("app", {}),
        "server": base.get("server", {}),
        "mongodb": base.get("mongodb", {}),
        "redis": base.get("redis", {}),
        "qdrant": base.get("qdrant", {}),
        "openrouter": base.get("openrouter", {}),
        "embedding": base.get("embedding", {}),
        "crawler": base.get("crawler", {}),
        "llm": base.get("llm", {}),
        "qdrant_optimization": base.get("qdrant_optimization", {}),
        "url_discovery": base.get("url_discovery", {}),
        "media_mention": base.get("media_mention", {}),
        "monitoring": load_monitoring_yaml().get("monitoring", {}),
        "chat": base.get("chat", {}),
        "scheduler": base.get("scheduler", {}),
        "reddit_trending": base.get("reddit_trending", {}),
        "youtube_trending": base.get("youtube_trending") if isinstance(base.get("youtube_trending"), dict) else {},
        "narrative_shift": base.get("narrative_shift") if isinstance(base.get("narrative_shift"), dict) else {},
        "narrative_intelligence_daily": base.get("narrative_intelligence_daily") if isinstance(base.get("narrative_intelligence_daily"), dict) else {},
        "settings": settings,
    }
