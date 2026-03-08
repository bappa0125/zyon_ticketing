"""Media ingestion scheduler - incremental mode every 30 minutes. No LLM."""
import time

from app.config import get_config
from app.core.logging import get_logger
from app.services.media_ingestion.ingestion_scheduler import run_incremental_ingestion

logger = get_logger(__name__)


def main():
    cfg = get_config().get("media_ingestion", get_config().get("media_index", {}))
    interval = cfg.get("crawl_frequency_minutes", 30) * 60
    logger.info("media_ingestion_scheduler_started", interval_seconds=interval)
    while True:
        try:
            run_incremental_ingestion()
        except Exception as e:
            logger.error("media_ingestion_cycle_error", error=str(e))
        time.sleep(interval)


if __name__ == "__main__":
    main()
