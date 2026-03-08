"""Streaming crawl job: process one page, release memory, hash-first detection."""
from app.config import get_config
from app.core.logging import get_logger
from app.services.crawler.crawler import crawl_and_extract
from app.services.crawler.snapshot_store_sync import (
    content_hash,
    get_competitor_sync,
    get_snapshot_metadata_sync,
    store_snapshot_sync,
    update_competitor_after_crawl_sync,
)
from app.services.crawler.change_detector import detect_changes
from app.services.crawler.rules_engine import rule_matches
from app.services.crawler.alert_store import create_alert

logger = get_logger(__name__)


def _inc_metric(name: str):
    try:
        from redis import Redis
        r = Redis.from_url(get_config()["settings"].redis_url)
        r.incr(f"crawler:{name}")
        r.incr(f"crawler:pages_crawled_today")
        r.expire("crawler:pages_crawled_today", 86400)  # 24h
    except Exception:
        pass


def _store_embedding_changed_only(competitor_id: str, snapshot_id: str, url: str, text: str):
    """Embed and store only changed content (batch size from config)."""
    try:
        from app.services.embedding_service import embed
        from app.services.qdrant_service import get_qdrant
        from qdrant_client.models import PointStruct
        from uuid import uuid4

        cfg = get_config()
        coll = cfg.get("crawler", {}).get("qdrant_page_collection", "page_embeddings")
        size = cfg.get("qdrant", {}).get("vector_size", 384)

        client = get_qdrant()
        vectors = client.get_collections().collections
        if not any(c.name == coll for c in vectors):
            from qdrant_client.models import VectorParams, Distance
            cfg = get_config()
            on_disk = cfg.get("qdrant_optimization", {}).get("on_disk", True)
            client.create_collection(
                coll,
                vectors_config=VectorParams(size=size, distance=Distance.COSINE),
                on_disk_payload=on_disk,
            )

        vec = embed(text[:8000])
        client.upsert(
            coll,
            [PointStruct(
                id=str(uuid4()),
                vector=vec,
                payload={"competitor_id": competitor_id, "snapshot_id": snapshot_id, "url": url, "content": text[:1000]},
            )],
        )
        logger.info("embedding_generated", competitor_id=competitor_id)
    except Exception as e:
        logger.warning("embedding_failed", error=str(e))


def crawl_website(competitor_id: str, website: str):
    """
    Streaming job: crawl → extract → store on disk → hash-first detect → embed only if change → release.
    """
    logger.info("crawl_started", competitor_id=competitor_id, website=website)

    try:
        extracted = crawl_and_extract(website)
    except Exception as e:
        logger.error("crawl_website_failed", competitor_id=competitor_id, error=str(e))
        update_competitor_after_crawl_sync(competitor_id, change_detected=False)
        return

    text = extracted.get("text_content", "")
    new_hash = content_hash(text)

    # Minimal prev load (hash + text for comparison)
    prev = get_snapshot_metadata_sync(competitor_id, website)
    old_hash = prev.get("content_hash") if prev else None
    old_text = prev.get("text_content", "") if prev else ""

    # Store snapshot on disk (releases MongoDB load)
    snapshot_id = store_snapshot_sync(competitor_id, website, extracted, text)
    _inc_metric("pages_crawled_total")

    cfg = get_config()
    threshold = cfg.get("crawler", {}).get("change_similarity_threshold", 0.85)
    freq = cfg.get("crawler", {}).get("frequency_minutes", 30)

    # Hash-first: only run semantic when hash changed
    run_semantic = old_hash != new_hash if old_hash else True
    has_change, summary = detect_changes(
        old_text, text,
        old_hash=old_hash,
        new_hash=new_hash,
        similarity_threshold=threshold,
        run_semantic=run_semantic,
    )

    update_competitor_after_crawl_sync(competitor_id, change_detected=has_change, frequency_minutes=freq)

    if has_change:
        comp = get_competitor_sync(competitor_id)
        rules = comp.get("tracking_rules", []) if comp else []
        if rule_matches(summary, text, rules):
            impact = 0.7 if "major" in summary.lower() else 0.5
            create_alert(competitor_id, summary, impact)
            _inc_metric("alerts_generated_total")
            logger.info("alert_created", competitor_id=competitor_id, summary=summary)

        # Embeddings only for changed content
        _store_embedding_changed_only(competitor_id, snapshot_id, website, text)

    # Release references
    del extracted, text, prev, old_text

    logger.info("crawl_completed", competitor_id=competitor_id)
