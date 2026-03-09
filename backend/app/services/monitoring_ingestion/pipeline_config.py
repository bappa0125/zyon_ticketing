"""STEP 1: Monitoring ingestion pipeline configuration.
Loads clients, monitoring config, and media sources. No ingestion, no side effects."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

_CONFIG_CACHE: "PipelineConfig | None" = None


def _get_config_dir() -> Path:
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    config_dir = project_root / "config"
    if not config_dir.exists():
        config_dir = Path("/app/config")
    return config_dir


def _load_clients_for_pipeline() -> list[dict[str, Any]]:
    """Load clients from config/clients.yaml (read-only, no Redis)."""
    path = _get_config_dir() / "clients.yaml"
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("clients", [])


def _load_media_sources_for_pipeline() -> list[dict[str, Any]]:
    """Load media sources from config/media_sources.yaml."""
    path = _get_config_dir() / "media_sources.yaml"
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("sources", [])


def _monitored_entities_from_clients(clients: list[dict]) -> list[str]:
    """Derive monitored entity names (client names + competitors)."""
    entities: list[str] = []
    seen: set[str] = set()
    for c in clients:
        name = (c.get("name") or "").strip()
        if name and name not in seen:
            entities.append(name)
            seen.add(name)
        for comp in c.get("competitors") or []:
            if comp and isinstance(comp, str):
                comp = comp.strip()
                if comp and comp not in seen:
                    entities.append(comp)
                    seen.add(comp)
    return entities


@dataclass
class PipelineConfig:
    """Configuration for the monitoring ingestion pipeline (STEP 1)."""

    monitored_entities: list[str] = field(default_factory=list)
    clients: list[dict[str, Any]] = field(default_factory=list)
    media_sources: list[dict[str, Any]] = field(default_factory=list)
    ingestion_batch_size: int = 20
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "monitored_entities": self.monitored_entities,
            "clients": self.clients,
            "media_sources": self.media_sources,
            "ingestion_batch_size": self.ingestion_batch_size,
            "enabled": self.enabled,
        }


def get_pipeline_config() -> PipelineConfig:
    """
    Load and return the monitoring ingestion pipeline configuration.
    STEP 1: Configuration only. Uses config/clients.yaml, config/media_sources.yaml,
    and config/monitoring.yaml. Does not modify any existing module.
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    clients = _load_clients_for_pipeline()
    media_sources = _load_media_sources_for_pipeline()
    monitored_entities = _monitored_entities_from_clients(clients)

    config = get_config()
    monitoring = config.get("monitoring", {})
    ingestion = monitoring.get("ingestion", {})
    batch_size = ingestion.get("batch_size", 20) if isinstance(ingestion, dict) else 20

    _CONFIG_CACHE = PipelineConfig(
        monitored_entities=monitored_entities,
        clients=clients,
        media_sources=media_sources,
        ingestion_batch_size=batch_size,
        enabled=True,
    )
    logger.info(
        "monitoring_ingestion_config_loaded",
        entities=len(monitored_entities),
        clients=len(clients),
        sources=len(media_sources),
    )
    return _CONFIG_CACHE
