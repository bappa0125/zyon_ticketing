"""Content hashing for deduplication — MD5-based content hash."""
import hashlib


def generate_content_hash(text: str) -> str:
    """
    Generate MD5 hash of text for deduplication.
    Before inserting a social post, check MongoDB for existing document with same hash.
    """
    if not text or not isinstance(text, str):
        return ""
    return hashlib.md5(text.strip().encode("utf-8")).hexdigest()
