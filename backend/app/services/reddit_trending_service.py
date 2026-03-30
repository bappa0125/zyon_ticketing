"""
Reddit trending pipeline — separate from Apify/social_posts.

- Fetches from Reddit public JSON API (no API key).
- Stores in dedicated MongoDB collections and Redis key namespace.
- Generates themes and Sahi content suggestions via LLM (free tier).
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

# social_posts schema constant (kept local to avoid circular imports)
SOCIAL_POSTS_COLLECTION = "social_posts"

# --- Config helpers ----------------------------------------------------------

def _cfg() -> dict[str, Any]:
    return get_config().get("reddit_trending") or {}


def _mongodb_cfg() -> dict[str, Any]:
    return _cfg().get("mongodb") or {}


def _redis_cfg() -> dict[str, Any]:
    return _cfg().get("redis") or {}


def _posts_collection_name() -> str:
    return _mongodb_cfg().get("posts_collection") or "reddit_trending_posts"


def _summaries_collection_name() -> str:
    return _mongodb_cfg().get("summaries_collection") or "reddit_trending_summaries"


def _redis_prefix() -> str:
    return (_redis_cfg().get("key_prefix") or "reddit_trending").strip()


def _redis_key(name: str) -> str:
    return f"{_redis_prefix()}:{name}"


# --- Reddit fetch (public JSON API) ------------------------------------------

def _fetch_subreddit(subreddit: str, sort: str = "hot", top_period: str = "day", limit: int = 20) -> list[dict]:
    """Sync fetch one subreddit. Returns list of raw listing children."""
    cfg = _cfg()
    user_agent = (cfg.get("user_agent") or "ZyonRedditTrending/1.0").strip()
    if not user_agent:
        user_agent = "ZyonRedditTrending/1.0"
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
    if sort == "top":
        url += f"?t={top_period}"
    url += "&" if "?" in url else "?"
    url += f"limit={min(limit, 100)}"
    headers = {"User-Agent": user_agent}
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("reddit_trending_fetch_failed", subreddit=subreddit, error=str(e))
        return []
    children = (data.get("data") or {}).get("children") or []
    return [c.get("data") for c in children if isinstance(c.get("data"), dict)]


def _normalize_post(raw: dict, subreddit: str) -> dict[str, Any] | None:
    """Normalize Reddit listing item to our schema."""
    try:
        title = (raw.get("title") or "").strip()
        if not title:
            return None
        selftext = (raw.get("selftext") or "")[:2000]
        body_snippet = (selftext or title)[:500]
        permalink = (raw.get("permalink") or "").strip()
        if permalink and not permalink.startswith("http"):
            permalink = f"https://www.reddit.com{permalink}"
        score = int(raw.get("score") or 0)
        num_comments = int(raw.get("num_comments") or 0)
        created_utc = raw.get("created_utc")
        if isinstance(created_utc, (int, float)):
            created_at = datetime.fromtimestamp(float(created_utc), tz=timezone.utc)
        else:
            created_at = datetime.now(timezone.utc)
        return {
            "subreddit": subreddit,
            "title": title[:500],
            "body_snippet": body_snippet,
            "url": permalink[:2000],
            "score": score,
            "num_comments": num_comments,
            "created_utc": created_at.isoformat(),
            "reddit_id": (raw.get("id") or "")[:20],
        }
    except Exception as e:
        logger.debug("reddit_trending_normalize_skip", error=str(e))
        return None


def _engagement_score(score: int, num_comments: int) -> int:
    # Very cheap heuristic: comments are higher-signal than upvotes.
    return int(score or 0) + (3 * int(num_comments or 0))


async def fetch_trending_posts() -> list[dict[str, Any]]:
    """
    Fetch hot/top posts from configured subreddits via Reddit JSON API.
    Returns list of normalized posts (our schema).
    """
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return []
    subreddits = cfg.get("subreddits") or []
    if not subreddits:
        return []
    sort = (cfg.get("sort") or "hot").strip().lower() or "hot"
    top_period = (cfg.get("top_period") or "day").strip().lower()
    limit = min(int(cfg.get("posts_per_subreddit") or 20), 100)
    delay = max(0.5, float(cfg.get("delay_seconds_between_subreddits") or 1.5))

    all_posts: list[dict[str, Any]] = []
    for sub in subreddits:
        if not isinstance(sub, str) or not sub.strip():
            continue
        sub = sub.strip()
        raw_list = await asyncio.to_thread(
            _fetch_subreddit, sub, sort=sort, top_period=top_period, limit=limit
        )
        for raw in raw_list:
            doc = _normalize_post(raw, sub)
            if doc:
                all_posts.append(doc)
        await asyncio.sleep(delay)

    # Sort by score desc, then by num_comments
    all_posts.sort(key=lambda p: (p.get("score") or 0, p.get("num_comments") or 0), reverse=True)
    return all_posts


# --- MongoDB (reddit_trending_* collections) ----------------------------------

async def _get_db():
    from app.services.mongodb import get_mongo_client, get_db
    await get_mongo_client()
    return get_db()


async def save_posts_to_mongo(posts: list[dict[str, Any]]) -> int:
    """Replace current batch in reddit_trending_posts (drop + insert for simplicity). Returns count inserted."""
    if not posts:
        return 0
    db = await _get_db()
    coll_name = _posts_collection_name()
    coll = db[coll_name]
    fetched_at = datetime.now(timezone.utc)
    docs = [{**p, "fetched_at": fetched_at, "pipeline": "reddit_trending"} for p in posts]
    try:
        await coll.delete_many({"pipeline": "reddit_trending"})
        if docs:
            await coll.insert_many(docs)
        return len(docs)
    except Exception as e:
        logger.warning("reddit_trending_mongo_save_failed", error=str(e))
        return 0


async def load_posts_from_mongo(limit: int = 200) -> list[dict[str, Any]]:
    """Load latest posts from reddit_trending_posts, sorted by score desc."""
    db = await _get_db()
    coll = db[_posts_collection_name()]
    cursor = coll.find({"pipeline": "reddit_trending"}).sort("score", -1).limit(limit)
    out = []
    async for doc in cursor:
        d = dict(doc)
        d.pop("_id", None)
        fetched = d.get("fetched_at")
        if hasattr(fetched, "isoformat"):
            d["fetched_at"] = fetched.isoformat()
        out.append(d)
    return out


async def save_summary_to_mongo(themes: list[dict], sahi_suggestions: list[dict]) -> None:
    """Append one summary record to reddit_trending_summaries."""
    db = await _get_db()
    coll = db[_summaries_collection_name()]
    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "themes": themes,
        "sahi_suggestions": sahi_suggestions,
        "pipeline": "reddit_trending",
    }
    try:
        await coll.insert_one(doc)
    except Exception as e:
        logger.warning("reddit_trending_summary_save_failed", error=str(e))


# --- Social posts (for narrative/sentiment UI) --------------------------------

async def ingest_posts_to_social_posts(posts: list[dict[str, Any]]) -> dict[str, int]:
    """
    Persist Reddit trending posts into `social_posts` so existing Sentiment + Narrative pipelines can use them.
    This is intentionally lightweight and uses:
    - entity detection (clients.yaml + config aliases)
    - existing narrative/sentiment backfills downstream (sentiment_api already backfills on read)
    """
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return {"inserted": 0, "updated": 0, "skipped": 0}
    if not posts:
        return {"inserted": 0, "updated": 0, "skipped": 0}

    from app.services.mongodb import get_mongo_client, get_db
    from app.core.hash_utils import generate_content_hash
    from app.services.entity_detection_service import detect_entity

    await get_mongo_client()
    db = get_db()
    coll = db[SOCIAL_POSTS_COLLECTION]

    inserted = 0
    updated = 0
    skipped = 0
    now = datetime.now(timezone.utc)

    for p in posts:
        try:
            subreddit = (p.get("subreddit") or "").strip()
            title = (p.get("title") or "").strip()
            body = (p.get("body_snippet") or "").strip()
            url = (p.get("url") or "").strip()
            reddit_id = (p.get("reddit_id") or "").strip()
            score = int(p.get("score") or 0)
            num_comments = int(p.get("num_comments") or 0)

            text = " ".join([t for t in (title, body) if t]).strip()
            if not text:
                skipped += 1
                continue

            entity = detect_entity(text)
            if not entity:
                skipped += 1
                continue

            published_at = None
            created = (p.get("created_utc") or "").strip()
            if created:
                try:
                    published_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except Exception:
                    published_at = now
            else:
                published_at = now

            content_hash = generate_content_hash(text[:500])
            engagement = {
                "likes": score,
                "retweets": 0,
                "comments": num_comments,
                "score": _engagement_score(score, num_comments),
            }

            # Dedup/upsert by (platform, pipeline, reddit_id) when available, else by URL.
            filt: dict[str, Any] = {"platform": "reddit", "pipeline": "reddit_trending"}
            if reddit_id:
                filt["reddit_id"] = reddit_id
            elif url:
                filt["url"] = url
            else:
                skipped += 1
                continue

            doc = {
                "platform": "reddit",
                "pipeline": "reddit_trending",
                "entity": entity,
                "subreddit": subreddit[:80],
                "reddit_id": reddit_id[:20],
                "title": title[:300],
                "body": body[:1200],
                "text": text[:500],
                "url": url[:500],
                "engagement": engagement,
                "content_hash": content_hash,
                "published_at": published_at,
                "fetched_at": now,
            }

            res = await coll.update_one(filt, {"$set": doc}, upsert=True)
            if getattr(res, "upserted_id", None):
                inserted += 1
            elif getattr(res, "modified_count", 0) > 0:
                updated += 1
            else:
                skipped += 1
        except Exception as e:
            logger.debug("reddit_trending_social_upsert_failed", error=str(e))
            skipped += 1

    if inserted or updated:
        logger.info("reddit_trending_social_ingest_complete", inserted=inserted, updated=updated, skipped=skipped)

    return {"inserted": inserted, "updated": updated, "skipped": skipped}


# --- Redis (reddit_trending:* keys) -------------------------------------------

async def save_posts_to_redis(posts: list[dict[str, Any]]) -> None:
    """Cache posts list in Redis. TTL from config."""
    if not posts:
        return
    from app.services.redis_client import get_redis
    r = await get_redis()
    key = _redis_key("posts")
    ttl = int(_redis_cfg().get("posts_ttl_seconds") or 1800)
    payload = json.dumps([_serialize_for_json(p) for p in posts], ensure_ascii=False)
    await r.setex(key, ttl, payload)


def _serialize_for_json(obj: Any) -> Any:
    """Make object JSON-serializable (datetime -> str)."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize_for_json(v) for v in obj]
    return obj


async def load_posts_from_redis() -> list[dict[str, Any]] | None:
    """Load cached posts from Redis. Returns None if miss."""
    from app.services.redis_client import get_redis
    r = await get_redis()
    raw = await r.get(_redis_key("posts"))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def save_themes_to_redis(themes: list[dict]) -> None:
    ttl = int(_redis_cfg().get("themes_ttl_seconds") or 3600)
    from app.services.redis_client import get_redis
    r = await get_redis()
    await r.setex(_redis_key("themes"), ttl, json.dumps(themes, ensure_ascii=False))


async def save_sahi_to_redis(suggestions: list[dict]) -> None:
    ttl = int(_redis_cfg().get("sahi_suggestions_ttl_seconds") or 3600)
    from app.services.redis_client import get_redis
    r = await get_redis()
    await r.setex(_redis_key("sahi"), ttl, json.dumps(suggestions, ensure_ascii=False))


async def load_themes_from_redis() -> list[dict] | None:
    from app.services.redis_client import get_redis
    r = await get_redis()
    raw = await r.get(_redis_key("themes"))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def load_sahi_from_redis() -> list[dict] | None:
    from app.services.redis_client import get_redis
    r = await get_redis()
    raw = await r.get(_redis_key("sahi"))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def load_latest_summary_from_mongo() -> tuple[list[dict], list[dict]]:
    """Return (themes, sahi_suggestions) from the most recent reddit_trending_summaries doc."""
    db = await _get_db()
    coll = db[_summaries_collection_name()]
    doc = await coll.find_one(
        {"pipeline": "reddit_trending"},
        sort=[("generated_at", -1)],
        projection={"themes": 1, "sahi_suggestions": 1},
    )
    if not doc:
        return [], []
    themes = doc.get("themes") if isinstance(doc.get("themes"), list) else []
    sahi = doc.get("sahi_suggestions") if isinstance(doc.get("sahi_suggestions"), list) else []
    return themes, sahi


# --- LLM: themes and Sahi suggestions ----------------------------------------

async def generate_themes_from_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One LLM call: summarize posts into 4–6 themes. Returns list of {label, description}."""
    cfg = _cfg()
    llm_cfg = cfg.get("llm") or {}
    model = (llm_cfg.get("model") or "openrouter/free").strip()
    max_tokens = int(llm_cfg.get("max_tokens_themes") or 400)
    # Build compact input (titles + short snippets only)
    lines = []
    for i, p in enumerate((posts or [])[:100], 1):
        title = (p.get("title") or "").strip()
        snippet = (p.get("body_snippet") or "")[:120]
        sub = p.get("subreddit") or ""
        lines.append(f"{i}. [r/{sub}] {title} — {snippet}")
    text = "\n".join(lines) or "No posts."
    system = (
        "You are an analyst. Given Reddit post titles and snippets from trading/investing communities (India and global), "
        "identify 4–6 recurring themes or topics. Return ONLY valid JSON array of objects with keys: label, description. "
        "Example: [{\"label\": \"SIP vs lump sum\", \"description\": \"Debate on systematic investment vs one-time investment.\"}]"
    )
    user = f"Identify themes from these posts:\n\n{text[:8000]}"
    out = await _llm_single_call(model=model, max_tokens=max_tokens, system=system, user=user)
    if not out:
        return []
    try:
        parsed = json.loads(out)
        if isinstance(parsed, list):
            return [{"label": x.get("label", ""), "description": x.get("description", "")} for x in parsed if isinstance(x, dict)]
        return []
    except Exception:
        return []


async def generate_sahi_suggestions_from_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One LLM call: suggest 4–6 article topics Sahi should create. Returns list of {title, rationale}."""
    cfg = _cfg()
    llm_cfg = cfg.get("llm") or {}
    model = (llm_cfg.get("model") or "openrouter/free").strip()
    max_tokens = int(llm_cfg.get("max_tokens_sahi") or 400)
    lines = []
    for i, p in enumerate((posts or [])[:100], 1):
        title = (p.get("title") or "").strip()
        snippet = (p.get("body_snippet") or "")[:120]
        sub = p.get("subreddit") or ""
        lines.append(f"{i}. [r/{sub}] {title} — {snippet}")
    text = "\n".join(lines) or "No posts."
    system = (
        "You are a content strategist. Given Reddit discussions from India and global trading/investing communities, "
        "suggest 4–6 article topics or talking points that Sahi (an investing/trading education brand) could create. "
        "Return ONLY valid JSON array of objects with keys: title, rationale. "
        "Example: [{\"title\": \"SIP vs lump sum: when to use which\", \"rationale\": \"High engagement in Indian forums.\"}]"
    )
    user = f"Suggest Sahi content topics from these discussions:\n\n{text[:8000]}"
    out = await _llm_single_call(model=model, max_tokens=max_tokens, system=system, user=user)
    if not out:
        return []
    try:
        parsed = json.loads(out)
        if isinstance(parsed, list):
            return [{"title": x.get("title", ""), "rationale": x.get("rationale", "")} for x in parsed if isinstance(x, dict)]
        return []
    except Exception:
        return []


async def _llm_single_call(model: str, max_tokens: int, system: str, user: str) -> str:
    """One non-streaming LLM call. Returns full response text or empty string."""
    from app.services.llm_gateway import LLMGateway
    gateway = LLMGateway()
    gateway.set_model(model)
    out = ""
    try:
        async for chunk in gateway.chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            stream=False,
            use_web_search=False,
        ):
            out += chunk or ""
    except Exception as e:
        logger.warning("reddit_trending_llm_failed", error=str(e))
        return ""
    # Strip markdown code blocks if present
    s = (out or "").strip()
    if s.startswith("```"):
        lines = s.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines)
    return s


# --- Full pipeline run --------------------------------------------------------

async def run_reddit_trending_pipeline() -> dict[str, Any]:
    """
    Run full pipeline: fetch Reddit → save to Mongo + Redis → LLM themes → LLM Sahi → save to Redis + Mongo.
    Returns counts and status.
    """
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return {"ok": False, "reason": "reddit_trending disabled"}
    result: dict[str, Any] = {
        "ok": True,
        "posts_fetched": 0,
        "posts_saved_mongo": 0,
        "themes_count": 0,
        "sahi_count": 0,
    }
    posts = await fetch_trending_posts()
    result["posts_fetched"] = len(posts)
    if not posts:
        return result
    result["posts_saved_mongo"] = await save_posts_to_mongo(posts)
    await save_posts_to_redis(posts)
    themes = await generate_themes_from_posts(posts)
    result["themes_count"] = len(themes)
    await save_themes_to_redis(themes)
    sahi = await generate_sahi_suggestions_from_posts(posts)
    result["sahi_count"] = len(sahi)
    await save_sahi_to_redis(sahi)
    await save_summary_to_mongo(themes, sahi)
    return result


async def run_reddit_trending_social_ingest() -> dict[str, Any]:
    """
    Fetch Reddit trending posts and upsert into `social_posts` (no LLM).
    Designed for cheap, reliable ingestion that powers narrative traction UI.
    """
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return {"ok": False, "reason": "reddit_trending disabled"}
    posts = await fetch_trending_posts()
    stats = await ingest_posts_to_social_posts(posts)
    return {"ok": True, "posts_fetched": len(posts), **stats}
