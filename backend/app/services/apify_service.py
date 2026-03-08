"""Apify client — run actors and return normalized results."""
from typing import Any

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        from apify_client import ApifyClient
        config = get_config()
        token = config.get("settings").apify_api_key or ""
        if not token:
            raise ValueError("APIFY_API_KEY is not set")
        _client = ApifyClient(token)
    return _client


def run_actor(actor_id: str, input_data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Run Apify actor and return items from default dataset.
    Handles API errors, network failures, rate limits.
    """
    try:
        client = _get_client()
        run = client.actor(actor_id).call(run_input=input_data)
        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            return []
        items = list(client.dataset(dataset_id).iterate_items())
        return items
    except ValueError as e:
        logger.warning("apify_config_error", error=str(e))
        return []
    except Exception as e:
        logger.warning("apify_run_failed", actor_id=actor_id, error=str(e))
        return []
