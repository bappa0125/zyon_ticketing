"""Ingestion scheduler - initial + incremental modes. No LLM during ingestion."""
from app.config import get_config
from app.core.logging import get_logger
from app.services.media_ingestion.rss_crawler import crawl_rss_sources
from app.services.media_ingestion.article_parser import fetch_and_parse
from app.services.media_ingestion.article_storage import url_exists, store_article
from app.services.media_ingestion.entity_detector import detect_entities

logger = get_logger(__name__)

MAX_CONCURRENT_FETCHES = 3
MAX_SOURCES_PER_CYCLE = 5
MAX_ARTICLES_PER_CYCLE = 20
MAX_ARTICLES_PER_SOURCE_INITIAL = 200


def run_initial_ingestion() -> int:
    """
    Initial ingestion: crawl all RSS feeds, up to 200 articles per source.
    Store all articles. No URL skip.
    """
    cfg = get_config().get("media_ingestion", {})
    max_per_source = cfg.get("max_articles_per_source_initial", MAX_ARTICLES_PER_SOURCE_INITIAL)
    entries = crawl_rss_sources(initial_mode=True, max_articles_per_cycle=9999)
    stored = 0
    for e in entries:
        url = e.get("url", "")
        if not url:
            continue
        parsed = fetch_and_parse(url, e.get("source_domain", ""))
        if not parsed:
            continue
        text = f"{parsed.get('title','')} {parsed.get('content','')}"
        entities = detect_entities(text)
        try:
            if store_article(
                title=parsed.get("title", ""),
                url=parsed.get("url", ""),
                source=parsed.get("source", ""),
                publish_date=parsed.get("publish_date"),
                content=parsed.get("content", "")[:2000],
                entities=entities,
            ):
                stored += 1
        except Exception:
            pass
    _inc_metrics(stored, "initial")
    logger.info("initial_ingestion_done", stored=stored, total=len(entries))
    return stored


def run_incremental_ingestion() -> int:
    """
    Incremental: fetch RSS, skip if URL exists, ingest only new articles.
    Max 5 sources, 20 articles per cycle.
    """
    cfg = get_config().get("media_ingestion", {})
    max_articles = cfg.get("max_articles_per_cycle", MAX_ARTICLES_PER_CYCLE)
    entries = crawl_rss_sources(initial_mode=False, max_articles_per_cycle=max_articles)
    stored = 0
    for e in entries[:max_articles]:
        url = e.get("url", "")
        if not url:
            continue
        if url_exists(url):
            continue
        parsed = fetch_and_parse(url, e.get("source_domain", ""))
        if not parsed:
            continue
        text = f"{parsed.get('title','')} {parsed.get('content','')}"
        entities = detect_entities(text)
        try:
            if store_article(
                title=parsed.get("title", ""),
                url=parsed.get("url", ""),
                source=parsed.get("source", ""),
                publish_date=parsed.get("publish_date"),
                content=parsed.get("content", "")[:2000],
                entities=entities,
            ):
                stored += 1
        except Exception:
            pass
    _inc_metrics(stored, "incremental")
    logger.info("incremental_ingestion_done", stored=stored, checked=len(entries))
    return stored


def _inc_metrics(stored: int, mode: str):
    try:
        from redis import Redis
        r = Redis.from_url(get_config()["settings"].redis_url)
        r.incr("media_ingestion:articles_indexed_total", stored)
        r.incr("media_ingestion:crawler_cycles_total")
    except Exception:
        pass
