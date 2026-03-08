"""Configuration loader - reads from config YAML and env vars."""
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


def load_yaml(env: str) -> dict[str, Any]:
    # Try project_root/config (local) then /app/config (Docker)
    project_root = Path(__file__).resolve().parent.parent.parent
    config_dir = project_root / "config"
    if not config_dir.exists():
        config_dir = Path("/app/config")
    path = config_dir / f"{env}.yaml"
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
    openrouter_model: str = Field(default="openai/gpt-3.5-turbo", alias="OPENROUTER_MODEL")

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
        "settings": settings,
    }
