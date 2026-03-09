#!/usr/bin/env python3
"""Remove fake/placeholder mention documents from MongoDB.
Deletes docs where url contains example.com or source is TechNews/FinanceDaily.
Collections: entity_mentions, media_articles, social_posts, article_documents.

Usage:
  MONGODB_URL=mongodb://localhost:27017 python scripts/remove_fake_mentions.py
  # Or from repo root with app config: cd backend && python scripts/remove_fake_mentions.py
"""
import os
import sys

# Optional: use app config if available
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.config import get_config
    _has_app_config = True
except Exception:
    _has_app_config = False

# Documents matching any of these are removed
FAKE_SOURCE_NAMES = {"technews", "financedaily"}


def is_fake_doc(doc: dict) -> bool:
    url = (doc.get("url") or doc.get("link") or "").strip().lower()
    if "example.com" in url:
        return True
    source = (doc.get("source") or doc.get("source_domain") or "").strip().lower()
    if source in FAKE_SOURCE_NAMES:
        return True
    return False


def main():
    if _has_app_config:
        os.environ.setdefault("APP_ENV", "dev")
        cfg = get_config()
        url = cfg["settings"].mongodb_url
        db_name = cfg["mongodb"].get("database", "chat")
    else:
        url = os.environ.get("MONGODB_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("MONGODB_DATABASE", "chat")

    from pymongo import MongoClient
    client = MongoClient(url)
    db = client[db_name]

    collections = ["entity_mentions", "media_articles", "social_posts", "article_documents"]
    total_deleted = 0
    for coll_name in collections:
        try:
            coll = db[coll_name]
            to_delete = [doc["_id"] for doc in coll.find({}) if is_fake_doc(doc)]
            if to_delete:
                result = coll.delete_many({"_id": {"$in": to_delete}})
                n = result.deleted_count
                total_deleted += n
                print(f"{coll_name}: deleted {n} fake doc(s)")
            else:
                print(f"{coll_name}: no fake docs found")
        except Exception as e:
            print(f"{coll_name}: skip ({e})")
    print(f"Done. Total removed: {total_deleted}")


if __name__ == "__main__":
    main()
