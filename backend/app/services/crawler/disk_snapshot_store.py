"""Disk-based snapshot storage - keeps last N snapshots per page, releases memory."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)


def _get_snapshot_dir() -> Path:
    cfg = get_config()
    base = cfg.get("crawler", {}).get("snapshot_dir", "./data/snapshots")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _page_dir(competitor_id: str, url: str) -> Path:
    """Unique dir per competitor+url (safe filename)."""
    safe = hashlib.md5(f"{competitor_id}:{url}".encode()).hexdigest()[:12]
    return _get_snapshot_dir() / safe


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def store_snapshot_disk(
    competitor_id: str,
    url: str,
    extracted: dict,
    content_hash_val: str,
) -> str:
    """
    Store extracted content on disk. Keeps only last N snapshots per page.
    Returns snapshot file path (used as id).
    """
    cfg = get_config()
    max_per_page = cfg.get("crawler", {}).get("snapshots_per_page", 20)
    page_dir = _page_dir(competitor_id, url)
    page_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow()
    fn = f"{ts.strftime('%Y%m%d_%H%M%S')}_{content_hash_val[:8]}.json"
    path = page_dir / fn
    doc = {
        "competitor_id": competitor_id,
        "url": url,
        "content_hash": content_hash_val,
        "timestamp": ts.isoformat(),
        **extracted,
    }
    with open(path, "w") as f:
        json.dump(doc, f, default=str)
    logger.info("snapshot_stored", path=str(path), competitor_id=competitor_id)

    # Prune old snapshots
    files = sorted(page_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    while len(files) > max_per_page:
        files[0].unlink()
        files = files[1:]

    return path.name


def get_latest_snapshot_disk(competitor_id: str, url: str) -> Optional[dict]:
    """Load most recent snapshot from disk."""
    page_dir = _page_dir(competitor_id, url)
    if not page_dir.exists():
        return None
    files = sorted(page_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    with open(files[0]) as f:
        return json.load(f)


def get_snapshot_metadata_disk(competitor_id: str, url: str) -> Optional[dict]:
    """
    Load only metadata (content_hash, timestamp) to avoid loading full content.
    For hash-first change detection.
    """
    page_dir = _page_dir(competitor_id, url)
    if not page_dir.exists():
        return None
    files = sorted(page_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    with open(files[0]) as f:
        d = json.load(f)
    return {
        "content_hash": d.get("content_hash"),
        "timestamp": d.get("timestamp"),
        "text_content": d.get("text_content", ""),
    }
