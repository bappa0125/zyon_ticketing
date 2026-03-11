"""
Media mention search - combines all monitoring sources via mention_retrieval_service,
plus live article discovery (Google News RSS, Tavily/DuckDuckGo) when fewer than 10.
Deduplicates, validates, quality scores, optionally reranks.
Ranking: source weight (from media_sources.yaml) + recency + forum visibility boost.
Validated live-search results can be stored in article_documents (background) for future DB-first retrieval.
Option B: metadata-only records (no resolved URL / blocked fetch) are also stored with url_note for DB-first display.
"""
import hashlib
import re
import threading
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from bs4 import BeautifulSoup

from app.config import get_config
from app.core.logging import get_logger
from app.services.media_mention.trusted_sources import is_trusted as is_trusted_source

logger = get_logger(__name__)

# Forum visibility boost so discussions surface when news coverage is scarce
FORUM_SCORE_BOOST = 15

MAX_CANDIDATES = 10
MAX_VALIDATED = 20
MIN_MENTIONS = 10
MAX_CONCURRENT = 2
TIMEOUT = 5
VALIDATION_CHARS = 1500
MIN_SCORE = 50
TOP_RESULTS = 25
LLM_MAX_TOKENS = 200
TITLE_SIMILARITY_THRESHOLD = 0.85

# Store validated live-search articles in article_documents for future DB-first retrieval (background, capped)
STORE_LIVE_CAP = 10

_SOURCE_WEIGHTS_CACHE: Optional[dict[str, int]] = None


def _load_source_weights() -> dict[str, int]:
    """Load domain -> weight from config/media_sources.yaml. Normalized domain (lower, no www)."""
    global _SOURCE_WEIGHTS_CACHE
    if _SOURCE_WEIGHTS_CACHE is not None:
        return _SOURCE_WEIGHTS_CACHE
    weights: dict[str, int] = {}
    try:
        from app.services.monitoring_ingestion.media_source_registry import load_media_sources
        for s in load_media_sources():
            domain = (s.get("domain") or "").strip().lower()
            if not domain:
                continue
            if domain.startswith("www."):
                domain = domain[4:]
            w = s.get("weight")
            if w is not None and isinstance(w, (int, float)):
                weights[domain] = int(w)
    except Exception as e:
        logger.debug("mention_search_source_weights_load_failed", error=str(e))
    _SOURCE_WEIGHTS_CACHE = weights
    return weights


def _domain_for_ranking(r: dict) -> str:
    """Normalized domain from result (source or source_domain or url)."""
    raw = (r.get("source") or r.get("source_domain") or "").strip()
    if not raw and r.get("url"):
        raw = urlparse(r.get("url", "")).netloc or ""
    raw = raw.lower()
    if raw.startswith("www."):
        raw = raw[4:]
    return raw.split(":")[0] if raw else ""


def _ranking_score(r: dict, source_weights: dict[str, int]) -> float:
    """score = source_weight*10 + recency_score; + FORUM_SCORE_BOOST when type==forum."""
    ts = _to_sortable_ts(r)
    now_ts = datetime.now(timezone.utc).timestamp()
    article_age_hours = max(0.0, (now_ts - ts) / 3600.0) if ts else 100.0
    recency_score = max(0.0, 100.0 - article_age_hours)
    domain = _domain_for_ranking(r)
    weight = source_weights.get(domain, 0)
    score = weight * 10 + recency_score
    if (r.get("type") or "").strip().lower() == "forum":
        score += FORUM_SCORE_BOOST
    return score


def _strip_html(text: str, max_len: int = 500) -> str:
    """Strip HTML tags from summary/snippet so we never show raw <a href=...> in the UI."""
    if not text or not isinstance(text, str):
        return ""
    s = text.strip()
    if "<" not in s and ">" not in s:
        return s[:max_len]
    try:
        soup = BeautifulSoup(s, "html.parser")
        return soup.get_text(separator=" ", strip=True)[:max_len]
    except Exception:
        return s[:max_len]


RESOLVE_GOOGLE_NEWS_TIMEOUT = 8.0


_GOOGLE_NEWS_RESOLVE_CACHE: dict[str, str] = {}
_GOOGLE_NEWS_RESOLVE_CACHE_MAX = 512


def _resolve_google_news_url(url: str, timeout: float = RESOLVE_GOOGLE_NEWS_TIMEOUT) -> str:
    """Resolve Google News redirect URL to final article URL. Returns original on failure."""
    if not url or "news.google.com" not in url:
        return url or ""
    cached = _GOOGLE_NEWS_RESOLVE_CACHE.get(url)
    if cached:
        return cached
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "ZyonMentionSearch/1.0"})
            final = str(resp.url)
            resolved = final if final and "news.google.com" not in final else url
            # Simple bounded cache (FIFO-ish) to avoid repeated redirect resolutions
            if len(_GOOGLE_NEWS_RESOLVE_CACHE) >= _GOOGLE_NEWS_RESOLVE_CACHE_MAX:
                try:
                    _GOOGLE_NEWS_RESOLVE_CACHE.pop(next(iter(_GOOGLE_NEWS_RESOLVE_CACHE)))
                except Exception:
                    _GOOGLE_NEWS_RESOLVE_CACHE.clear()
            _GOOGLE_NEWS_RESOLVE_CACHE[url] = resolved
            return resolved
    except Exception as e:
        logger.debug("resolve_google_news_url_failed", url=url[:80], error=str(e))
        return url


def _resolve_link_for_response(link: str) -> str:
    """If link is a Google News redirect, resolve to final URL; otherwise return as-is."""
    if not link or "news.google.com" not in link:
        return link or ""
    return _resolve_google_news_url(link, timeout=RESOLVE_GOOGLE_NEWS_TIMEOUT)


def _resolved_or_unavailable(link: str) -> tuple[str, str]:
    """
    Return (url_resolved_or_empty, url_original).
    If link is a Google News redirect and we can't resolve it, return ("", original).
    This preserves recall without surfacing Google redirect URLs to the user.
    """
    original = (link or "").strip()
    if not original:
        return ("", "")
    if "news.google.com" not in original:
        return (original, original)
    resolved = _resolve_google_news_url(original, timeout=RESOLVE_GOOGLE_NEWS_TIMEOUT)
    if resolved and "news.google.com" not in resolved:
        return (resolved, original)
    return ("", original)


def _fetch_article_text(url: str, max_chars: int = VALIDATION_CHARS) -> tuple[str, bool]:
    """Fetch article page, extract first max_chars. Returns (text, success)."""
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "ZyonMentionSearch/1.0"})
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text[:100_000], "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)[:max_chars]
        return (text, True)
    except Exception as e:
        logger.warning("mention_fetch_failed", url=url, error=str(e))
        return ("", False)


def _normalize_company(company: str) -> str:
    s = re.sub(r"\.(com|io|ai|co|org|net)$", "", company.lower())
    return s.strip()


def _entity_alternatives(entity: str) -> list[str]:
    """Common aliases for person/entity names (e.g. Shahrukh Khan -> SRK, Shah Rukh)."""
    s = entity.lower().strip()
    alts = [s, s.replace(" ", "")]
    if "shahrukh" in s and "khan" in s:
        alts.extend(["shah rukh khan", "srk"])
    if "shahrukh" in s:
        alts.append("shah rukh")
    return alts


def _validate_article(url: str, company: str) -> tuple[bool, str, int]:
    """Validate: fetch 1500 chars, verify company in text. Returns (passed, text, mention_count)."""
    text, ok = _fetch_article_text(url, VALIDATION_CHARS)
    if not ok:
        # Keep candidate later as "blocked/unfetched" rather than silently dropping (recall > precision for live search).
        return (False, "", 0)
    text_lower = text.lower()
    normalized = _normalize_company(company)
    if not normalized:
        return (True, text, 1)
    for alt in _entity_alternatives(normalized):
        if alt in text_lower:
            count = sum(1 for p in alt.split() if len(p) > 2 and p in text_lower) or 1
            return (True, text, count)
    count = text_lower.count(normalized) + sum(1 for p in normalized.split() if len(p) > 2 and p in text_lower)
    if normalized in text_lower:
        return (True, text, max(1, count))
    if any(p in text_lower for p in normalized.split() if len(p) > 2):
        return (True, text, count)
    return (False, text, 0)


def _url_normalize(url: str) -> str:
    """Normalize URL for dedup."""
    u = url.strip().lower()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    parsed = urlparse(u)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def _title_similar(a: str, b: str) -> bool:
    """True if titles are similar enough to consider duplicate."""
    if not a or not b:
        return False
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= TITLE_SIMILARITY_THRESHOLD


def _deduplicate(results: list[dict]) -> list[dict]:
    """Remove duplicates by URL and title similarity. Limit to 10."""
    seen_urls = set()
    seen_titles = []
    out = []
    for r in results:
        url = r.get("link") or r.get("url", "")
        if not url:
            continue
        norm_url = _url_normalize(url)
        if norm_url in seen_urls:
            continue
        title = (r.get("title") or "")[:200]
        if any(_title_similar(title, t) for t in seen_titles):
            continue
        seen_urls.add(norm_url)
        seen_titles.append(title)
        out.append(r)
        if len(out) >= MAX_CANDIDATES:
            break
    return out


def _quality_score(
    r: dict,
    company: str,
    validation_passed: bool,
    mention_count: int,
    body_text: str = "",
) -> int:
    """Score 0-100. Discard if < 50."""
    score = 0
    title = (r.get("title") or "").lower()
    company_lower = company.lower()
    if company_lower in title or _normalize_company(company) in title:
        score += 40
    if body_text and (company_lower in body_text.lower() or _normalize_company(company) in body_text.lower()):
        score += 20
    if mention_count >= 2:
        score += 10
    source = r.get("source", "") or ""
    try:
        parsed = urlparse(r.get("link") or r.get("url", ""))
        source = source or parsed.netloc or ""
    except Exception:
        pass
    if is_trusted_source(source):
        score += 20
    pub = r.get("publish_date") or r.get("date")
    if pub:
        try:
            dt = datetime.fromisoformat(str(pub).replace("Z", "+00:00")) if isinstance(pub, str) else pub
            if hasattr(dt, "replace"):
                dt = dt.replace(tzinfo=None) if dt.tzinfo else dt
            if (datetime.utcnow() - dt).days <= 30:
                score += 10
        except Exception:
            pass
    return min(100, score)


def _to_sortable_ts(r: dict) -> float:
    """Extract publish/timestamp from result to epoch float for sorting (newest first)."""
    pub = r.get("publish_date") or r.get("timestamp") or r.get("date")
    if pub is None or pub == "":
        return 0.0
    try:
        from time import struct_time
        if isinstance(pub, struct_time):
            return datetime(*pub[:6]).timestamp()
        if isinstance(pub, datetime):
            return pub.timestamp() if hasattr(pub, "timestamp") else 0.0
        s = str(pub).strip()
        if "T" in s or "-" in s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt.timestamp() if hasattr(dt, "timestamp") else 0.0
    except Exception:
        pass
    return 0.0


def _format_date(pub) -> str:
    """Format publish date as readable string, e.g. Mar 5, 2025."""
    if pub is None or pub == "":
        return ""
    try:
        from time import struct_time
        if isinstance(pub, struct_time):
            return datetime(*pub[:6]).strftime("%b %d, %Y")
        if isinstance(pub, str):
            dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            return dt.strftime("%b %d, %Y")
        if hasattr(pub, "strftime"):
            return pub.strftime("%b %d, %Y")
    except Exception:
        pass
    return str(pub)[:20]


def _search_google_news_rss(company: str, max_results: int = 20) -> list[dict]:
    """Fetch Google News RSS for company."""
    results = []
    try:
        import feedparser
        query = company.replace(" ", "+")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url, agent="ZyonMentionSearch/1.0")
        for e in feed.entries[:max_results]:
            link = e.get("link") or e.get("id", "") or ""
            if not link:
                continue
            url_resolved, url_original = _resolved_or_unavailable(link)
            raw_summary = (e.get("summary") or "") if hasattr(e, "summary") else ""
            snippet = _strip_html(raw_summary, 300)
            pub = e.get("published_parsed") or e.get("updated_parsed") or e.get("published")
            results.append({
                "title": (e.get("title") or "")[:500],
                "link": url_resolved,
                "url_original": url_original,
                "url_resolved": url_resolved,
                "source": (e.get("source", {}).get("title", "")) if isinstance(e.get("source"), dict) else "",
                "snippet": snippet,
                "publish_date": _format_date(pub),
                "url_note": "" if url_resolved else "Publisher URL unavailable (Google redirect not resolved).",
            })
    except Exception as e:
        logger.warning("google_news_rss_failed", company=company, error=str(e))
    return results


def _validate_and_score(
    candidates: list[dict],
    company: str,
    max_validate: int = MAX_VALIDATED,
) -> list[dict]:
    """Validate up to max_validate, score, discard < 50."""
    out = []
    to_validate = candidates[:max_validate]
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as ex:
        futures = {ex.submit(_validate_article, r.get("link") or r.get("url", ""), company): r for r in to_validate}
        for f in as_completed(futures):
            r = futures[f]
            url = r.get("link") or r.get("url", "")
            try:
                passed, body, mention_count = f.result()
                score = _quality_score(r, company, passed, mention_count, body)
                r = dict(r)
                r["score"] = score
                r["mention_count"] = mention_count
                r["validation_passed"] = passed
                if not passed:
                    # Keep metadata-only results when fetch/validation fails; label clearly for UI.
                    r["url_note"] = r.get("url_note") or "Content fetch blocked or unavailable (validated from headline/snippet only)."
                    # Ensure a minimum score so it can surface when there aren't many results.
                    r["score"] = max(int(r.get("score") or 0), MIN_SCORE)
                if r["score"] < MIN_SCORE:
                    continue
                logger.info("mention_result", query=company, url=url, score=r["score"], mention_count=mention_count, source=r.get("source"), validation_passed=passed)
                out.append(r)
            except Exception as e:
                logger.warning("mention_validate_error", url=url, error=str(e))
    return out


def _llm_rerank(articles: list[dict], company: str) -> list[dict]:
    """Optional LLM rerank. One call, 200 tokens."""
    if not articles or len(articles) <= 1:
        return articles
    cfg = get_config()
    api_key = cfg["settings"].openrouter_api_key
    if not api_key:
        return articles
    lines = "\n".join(f"{i+1}. {a.get('title','')} | {a.get('link','')}" for i, a in enumerate(articles))
    prompt = f"Rank the following articles by relevance to '{company}' (most relevant first). Reply with the numbers only, e.g. 3,1,5,2,4:\n{lines}"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=cfg["openrouter"].get("base_url", "https://openrouter.ai/api/v1"))
        rerank_model = cfg.get("media_mention", {}).get("rerank_model") or cfg.get("llm", {}).get("model") or "openai/gpt-3.5-turbo"
        resp = client.chat.completions.create(
            model=rerank_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=LLM_MAX_TOKENS,
        )
        if not resp.choices or len(resp.choices) == 0:
            return articles
        content = (resp.choices[0].message.content or "").strip()
        order = []
        for m in re.findall(r"\d+", content):
            idx = int(m) - 1
            if 0 <= idx < len(articles) and idx not in order:
                order.append(idx)
        if order:
            return [articles[i] for i in order]
    except Exception as e:
        logger.warning("mention_rerank_failed", error=str(e))
    return articles


def _fetch_more_articles(search_query: str, client: str) -> list[dict]:
    """Fetch more articles via media_monitor_service (Google News + DuckDuckGo). search_query may be disambiguated (e.g. Sahi trading)."""
    try:
        from app.services.media_monitor_service import search_entity
        items = search_entity(search_query, client, sources=["google_news", "duckduckgo"])
        out = []
        for r in items:
            out.append({
                "title": r.get("title", ""),
                "link": r.get("url", ""),
                "url": r.get("url", ""),
                "source": r.get("source", "") or urlparse(r.get("url", "")).netloc,
                "snippet": r.get("snippet", ""),
                "publish_date": _format_date(r.get("timestamp")),
                "type": "article",
            })
        return out
    except Exception as e:
        logger.warning("mention_article_discovery_failed", company=company, error=str(e))
        return []


def _get_disambiguated_search_query(company: str) -> str:
    """Use context_keywords to disambiguate (e.g. Sahi -> Sahi trading)."""
    try:
        from app.services.mention_context_validation import get_disambiguated_search_query
        return get_disambiguated_search_query(company) or company
    except Exception:
        return company


def _filter_by_context_keywords(results: list[dict], company: str) -> list[dict]:
    """Filter out results that don't contain any context_keyword when entity is ambiguous."""
    try:
        from app.services.mention_context_validation import get_context_keywords
        keywords = get_context_keywords(company)
        if not keywords:
            return results
        kept = []
        for r in results:
            title = (r.get("title") or "").strip()
            snippet = (r.get("snippet") or r.get("summary") or "").strip()
            text = (title + " " + snippet).lower()
            if any(kw.strip().lower() in text for kw in keywords if kw):
                kept.append(r)
            else:
                logger.debug("mention_context_filtered", title=title[:60], entity=company)
        return kept
    except Exception:
        return results


def _retrieval_to_mention(r: dict) -> dict:
    """Convert mention_retrieval output to search_mentions output format."""
    url = r.get("url", "")
    summary = r.get("summary", "")
    return {
        "title": r.get("title", ""),
        "link": url,
        "url": url,
        "source": r.get("source", ""),
        "source_domain": r.get("source", ""),
        "summary": summary,
        "snippet": summary[:200] if summary else "",
        "timestamp": r.get("timestamp", ""),
        "publish_date": r.get("published_at") or r.get("timestamp", ""),
        "sentiment": r.get("sentiment"),
        "type": r.get("type", "article"),
    }


def _metadata_hash(title: str, url_original: str, snippet: str) -> str:
    """Stable hash for metadata-only article_documents (no resolved URL). Used for dedup."""
    t = (title or "").strip().lower()[:500]
    u = (url_original or "").strip().lower()[:500]
    s = (snippet or "").strip()[:500]
    return hashlib.md5(("meta:" + t + u + s).encode("utf-8")).hexdigest()


def _store_validated_live_results(results: list[dict], company: str, cap: int = STORE_LIVE_CAP) -> None:
    """
    Background helper: store live results in article_documents.
    - Full path: when we have a resolved URL and fetch succeeds, store full doc (entity detection + context validation).
    - Option B (metadata-only): when URL is missing or fetch fails, store title/source/snippet/url_note so DB-first
      can show them with "Publisher link unavailable" / "Content fetch blocked" messaging.
    Dedup by url_hash (full) or metadata hash (metadata-only). Runs in a daemon thread; never raises to caller.
    """
    if not results or not (company or "").strip():
        return
    to_process = results[:cap]
    try:
        from pymongo import MongoClient

        from app.services.monitoring_ingestion.article_fetcher import (
            _content_hash,
            _fetch_and_extract,
            _normalize_url,
            _source_domain_from_url,
            _url_hash,
        )
        from app.services.entity_detection_service import detect_entity
        from app.services.mention_context_validation import resolve_to_canonical_entity, validate_mention_context

        cfg = get_config()
        settings = cfg.get("settings")
        mongodb_url = getattr(settings, "mongodb_url", "") if settings else ""
        db_name = (cfg.get("mongodb") or {}).get("database", "chat")
        if not mongodb_url:
            logger.debug("store_live_results_skip", reason="no_mongodb_url")
            return
        client = MongoClient(mongodb_url)
        db = client[db_name]
        article_coll = db["article_documents"]

        company_canonical = (resolve_to_canonical_entity(company) or company or "").strip()
        stored = 0
        for r in to_process:
            try:
                raw_url = (r.get("link") or r.get("url") or "").strip()
                url_for_fetch = ""
                if raw_url and "news.google.com" not in raw_url:
                    url_for_fetch = raw_url
                elif raw_url:
                    url_for_fetch = _resolve_google_news_url(raw_url, timeout=RESOLVE_GOOGLE_NEWS_TIMEOUT) or ""

                # Full path: resolved URL and fetch succeeded
                if url_for_fetch and "news.google.com" not in url_for_fetch:
                    article_text, article_length, url_original, url_resolved = _fetch_and_extract(url_for_fetch)
                    if article_text and article_text.strip():
                        title = (r.get("title") or "").strip()[:1000]
                        detection_text = f"{title} {article_text[:8000]}".strip()
                        entity = detect_entity(detection_text)
                        if entity and validate_mention_context(entity, article_text):
                            entity_canonical = (resolve_to_canonical_entity(entity) or entity or "").strip()
                            if not entity_canonical or not company_canonical or entity_canonical.lower() == company_canonical.lower():
                                url_hash = _url_hash(url_resolved)
                                content_hash = _content_hash(title, url_resolved)
                                if not article_coll.find_one({"url_hash": url_hash}) and not article_coll.find_one({"content_hash": content_hash}):
                                    source_domain = _source_domain_from_url(url_resolved) or (r.get("source") or "")[:200]
                                    fetched_at = datetime.now(timezone.utc)
                                    doc = {
                                        "url": url_resolved[:2000],
                                        "url_original": url_original[:2000],
                                        "url_resolved": url_resolved[:2000],
                                        "normalized_url": _normalize_url(url_resolved)[:2000],
                                        "url_hash": url_hash,
                                        "content_hash": content_hash,
                                        "source_domain": (source_domain or "")[:200],
                                        "title": title or "Untitled",
                                        "published_at": fetched_at,
                                        "article_text": article_text[:500000],
                                        "article_length": article_length,
                                        "fetched_at": fetched_at,
                                        "entities": [entity_canonical or entity],
                                        "summary": (r.get("snippet") or r.get("summary") or "")[:5000],
                                    }
                                    article_coll.insert_one(doc)
                                    stored += 1
                                    logger.info("store_live_result_inserted", company=company, url=url_resolved[:80], entity=entity)
                                    continue

                # Option B: metadata-only (no usable URL or fetch failed / blocked)
                title = (r.get("title") or "").strip()[:1000]
                if not title:
                    continue
                url_original = (r.get("url_original") or r.get("link") or r.get("url") or "").strip()[:2000]
                snippet = (r.get("snippet") or r.get("summary") or "").strip()[:5000]
                url_note = (r.get("url_note") or "").strip()[:500] or "Publisher link unavailable or content fetch blocked."
                meta_hash = _metadata_hash(title, url_original, snippet)
                if article_coll.find_one({"url_hash": meta_hash}):
                    continue
                source_domain = (r.get("source") or r.get("source_domain") or "").strip()[:200]
                fetched_at = datetime.now(timezone.utc)
                meta_doc = {
                    "url": "",
                    "url_original": url_original[:2000],
                    "url_resolved": "",
                    "normalized_url": "",
                    "url_hash": meta_hash,
                    "content_hash": meta_hash,
                    "source_domain": source_domain[:200],
                    "url_note": url_note,
                    "title": title,
                    "published_at": fetched_at,
                    "article_text": "",
                    "article_length": 0,
                    "fetched_at": fetched_at,
                    "entities": [company_canonical or company],
                    "summary": snippet[:5000],
                    "source": "live_search",
                }
                article_coll.insert_one(meta_doc)
                stored += 1
                logger.info("store_live_result_metadata_only", company=company, title=title[:60], url_note=url_note[:80])
            except Exception as e:
                err_str = str(e).lower()
                if "duplicate" in err_str or "e11000" in err_str:
                    pass
                else:
                    logger.warning("store_live_result_failed", url=(r.get("link") or r.get("url") or "")[:80], error=str(e))
        if stored:
            logger.info("store_live_results_done", company=company, stored=stored, attempted=len(to_process))
    except Exception as e:
        logger.warning("store_live_results_error", company=company, error=str(e))


def _url_normalize_for_dedup(url: str) -> str:
    """Normalize URL for deduplication (lowercase, strip)."""
    if not url or not isinstance(url, str):
        return ""
    u = url.strip().lower()
    if u.endswith("/"):
        u = u[:-1]
    return u[:500]


def search_mentions_db_only(company: str, forum_only: bool = False) -> list[dict]:
    """
    Return DB results only (entity_mentions, article_documents, media_articles, social_posts).
    Fast path for showing cached/ingested mentions first.
    """
    try:
        from app.services.mention_retrieval_service import retrieve_mentions_db_first, DB_FIRST_LIMIT
        db_first = retrieve_mentions_db_first(company, limit=DB_FIRST_LIMIT)
        if not db_first:
            return []
        db_items = [
            {"title": r.get("title"), "snippet": r.get("summary"), "summary": r.get("summary"), "url": r.get("url"), "link": r.get("url"), "source_domain": r.get("source_domain"), "source": r.get("source"), "published_at": r.get("published_at"), "sentiment": r.get("sentiment"), "type": r.get("type", "article"), "url_note": r.get("url_note")}
            for r in db_first
        ]
        filtered = _filter_by_context_keywords(db_items, company)
        if forum_only:
            filtered = [r for r in filtered if (str(r.get("type") or "").strip().lower() in ("forum", "reddit", "youtube", "twitter", "social"))]
        source_weights = _load_source_weights()
        for r in filtered:
            r["score"] = int(_ranking_score(r, source_weights))
        filtered.sort(key=lambda x: -x.get("score", 0))
        logger.info("mention_search_db_only", company=company, count=len(filtered))
        result = []
        for r in filtered:
            resolved, original = _resolved_or_unavailable(r.get("url", "") or "")
            result.append({
                "title": r.get("title", ""),
                "link": resolved,
                "url": resolved,
                "url_original": original if (original and original != resolved) else "",
                "url_note": (r.get("url_note") or "") if (not resolved and r.get("url_note")) else ("" if resolved else ("Publisher URL unavailable (Google redirect not resolved)." if original else "")),
                "source": r.get("source_domain", r.get("source", "")),
                "score": r.get("score", 0),
                "publish_date": r.get("published_at", ""),
                "snippet": r.get("summary", ""),
                "summary": r.get("summary", ""),
                "sentiment": r.get("sentiment"),
                "type": r.get("type", "article"),
            })
        return result
    except Exception as e:
        logger.debug("mention_search_db_only_failed", company=company, error=str(e))
        return []


def search_mentions_live_only(
    company: str,
    exclude_urls: set[str] | None = None,
    use_internal: bool = True,
    use_google_news: bool = True,
    use_external: bool = True,
    llm_rerank: bool = True,
    store_live_results: bool = True,
    forum_only: bool = False,
) -> list[dict]:
    """
    Run live search only (Google News RSS, internal, external). Exclude URLs already in exclude_urls.
    Returns unified list. Used after DB results to add fresh articles.
    """
    exclude_urls = exclude_urls or set()
    exclude_norm = {_url_normalize_for_dedup(u) for u in exclude_urls if u}

    all_results: list[dict] = []
    seen_urls: set[str] = set(exclude_norm)

    search_query = _get_disambiguated_search_query(company)
    if use_internal:
        for r in _fetch_more_articles(search_query, company):
            url = (r.get("url") or r.get("link", "")).strip().lower()
            u = _url_normalize_for_dedup(url)
            if u and u not in seen_urls:
                seen_urls.add(u)
                all_results.append(r)
    if use_google_news:
        for r in _search_google_news_rss(search_query, max_results=20):
            link = r.get("link", "") or ""
            url_original = r.get("url_original", "") or ""
            # Dedup by resolved if available else original.
            dedup_basis = (link or url_original).strip().lower()
            u = _url_normalize_for_dedup(dedup_basis)
            if u and u not in seen_urls:
                seen_urls.add(u)
                all_results.append({
                    "title": r.get("title", ""),
                    "link": link,
                    "url": link,
                    "url_original": url_original,
                    "url_resolved": r.get("url_resolved", link),
                    "url_note": r.get("url_note", ""),
                    "source": r.get("source", "") or urlparse(link).netloc,
                    "snippet": r.get("snippet", ""),
                    "publish_date": r.get("publish_date", ""),
                    "type": "article",
                })
    if use_external:
        try:
            from app.services.url_discovery.url_search_service import search as external_search
            for r in external_search(f'"{search_query}" news OR articles OR blog', max_results=10):
                link = r.get("link", r.get("url", ""))
                url = link.strip().lower() if link else ""
                u = _url_normalize_for_dedup(url)
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    all_results.append({
                        "title": r.get("title", ""),
                        "link": link,
                        "url": link,
                        "source": r.get("source") or (urlparse(link).netloc if link else ""),
                        "snippet": r.get("snippet", ""),
                        "type": "article",
                    })
        except Exception as e:
            logger.warning("mention_external_failed", company=company, error=str(e))

    # For live search, we already disambiguate the query (e.g. "Sahi trading").
    # Hard context-keyword filtering here can wipe out fresh results because headlines/snippets often omit keywords.
    # So we intentionally skip context filtering on the live-only path to maximize recall.
    if forum_only:
        all_results = [r for r in all_results if (str(r.get("type") or "").strip().lower() in ("forum", "reddit", "youtube", "twitter", "social"))]

    social = [r for r in all_results if r.get("type") != "article"]
    articles = [r for r in all_results if r.get("type") == "article"]

    if articles:
        validated = _validate_and_score(articles, company, max_validate=MAX_VALIDATED)
        validated_urls = {_url_normalize(r.get("link") or r.get("url", "")) for r in validated}
        if len(validated) + len(social) < MIN_MENTIONS:
            for r in _deduplicate(articles):
                if len(validated) + len(social) >= MIN_MENTIONS:
                    break
                u = _url_normalize(r.get("link") or r.get("url", ""))
                if u and u not in validated_urls:
                    r = dict(r)
                    r["score"] = r.get("score", 50)
                    validated.append(r)
                    validated_urls.add(u)
        articles = validated

    combined = social + articles
    source_weights = _load_source_weights()
    for r in combined:
        r["score"] = int(_ranking_score(r, source_weights))
    combined.sort(key=lambda x: -x.get("score", 0))
    top = combined[:max(MIN_MENTIONS, TOP_RESULTS)]

    if llm_rerank and len([r for r in top if r.get("type") == "article"]) > 1:
        art = [r for r in top if r.get("type") == "article"]
        soc = [r for r in top if r.get("type") != "article"]
        reranked = _llm_rerank(art, company)
        top = soc + reranked[:TOP_RESULTS]

    out = []
    for r in top:
        raw_link = r.get("link", r.get("url", "")) or ""
        # Never show Google News redirect URLs. If we can't resolve, keep the item but omit the URL.
        resolved_link, original_link = _resolved_or_unavailable(raw_link)
        out.append({
            "title": r.get("title", ""),
            "link": resolved_link,
            "url": resolved_link,
            "url_original": (r.get("url_original") or original_link) if not resolved_link else "",
            "url_note": (r.get("url_note") or ("Publisher URL unavailable (Google redirect not resolved)." if (original_link and not resolved_link) else "")),
            "source": r.get("source", "") or r.get("source_domain", ""),
            "score": r.get("score", 0),
            "publish_date": _format_date(r.get("publish_date") or r.get("timestamp")),
            "snippet": (r.get("snippet", "") or r.get("summary", "") or "")[:200],
            "summary": (r.get("summary", "") or r.get("snippet", "") or "")[:400],
            "sentiment": r.get("sentiment"),
            "type": r.get("type", "article"),
        })

    if store_live_results and not forum_only and out:
        thread = threading.Thread(
            target=_store_validated_live_results,
            args=(out, company, STORE_LIVE_CAP),
            daemon=True,
            name="store_live_mentions",
        )
        thread.start()

    logger.info("mention_search_live_only", company=company, count=len(out))
    return out


def search_mentions(
    company: str,
    use_internal: bool = True,
    use_google_news: bool = True,
    use_external: bool = True,
    llm_rerank: bool = True,
    store_live_results: bool = True,
    forum_only: bool = False,
) -> list[dict]:
    """
    Legacy: DB first, live only when DB empty. Use search_mentions_db_only + search_mentions_live_only
    for combined DB+live streaming.
    """
    all_results: list[dict] = []
    seen_urls: set[str] = set()
    mongodb_had_results = False
    live_search_ran = False

    # 1. Always try MongoDB first
    try:
        db_first = search_mentions_db_only(company, forum_only=forum_only)
        if db_first:
            return db_first
    except Exception as e:
        logger.debug("mention_search_db_first_skip", company=company, error=str(e))

    # 2. MongoDB returned nothing: try secondary MongoDB collections (media_articles, social_posts)
    try:
        from app.services.mention_retrieval_service import retrieve_mentions
        retrieval = retrieve_mentions(company, min_count=MIN_MENTIONS)
        for r in retrieval:
            m = _retrieval_to_mention(r)
            url = (m.get("url") or m.get("link", "")).strip().lower()
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(m)
        if all_results:
            mongodb_had_results = True
    except Exception as e:
        logger.warning("mention_retrieval_failed", company=company, error=str(e))

    # 3. Only when MongoDB gave no results: run live search (internal, Google News, external)
    search_query = _get_disambiguated_search_query(company)
    if not mongodb_had_results and not all_results:
        live_search_ran = True
        if use_internal:
            for r in _fetch_more_articles(search_query, company):
                url = (r.get("url") or r.get("link", "")).strip().lower()
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(r)
        if not all_results and use_google_news:
            for r in _search_google_news_rss(search_query, max_results=20):
                link = r.get("link", "")
                url = link.strip().lower() if link else ""
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append({
                        "title": r.get("title", ""),
                        "link": link,
                        "url": link,
                        "source": r.get("source", "") or urlparse(link).netloc,
                        "snippet": r.get("snippet", ""),
                        "publish_date": r.get("publish_date", ""),
                        "type": "article",
                    })
        if not all_results and use_external:
            try:
                from app.services.url_discovery.url_search_service import search as external_search
                for r in external_search(f'"{search_query}" news OR articles OR blog', max_results=10):
                    link = r.get("link", r.get("url", ""))
                    url = link.strip().lower() if link else ""
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append({
                            "title": r.get("title", ""),
                            "link": link,
                            "url": link,
                            "source": r.get("source", "") or (urlparse(link).netloc if link else ""),
                            "snippet": r.get("snippet", ""),
                            "type": "article",
                        })
            except Exception as e:
                logger.warning("mention_external_failed", company=company, error=str(e))

    # 4. Filter all results by context_keywords when entity is ambiguous (e.g. Sahi -> trading only)
    all_results = _filter_by_context_keywords(all_results, company)

    # 5. Split: social (from DB) vs articles (may need validation)
    social = [r for r in all_results if r.get("type") != "article"]
    articles = [r for r in all_results if r.get("type") == "article"]

    # 6. Validate and score article-type items
    if articles:
        validated = _validate_and_score(articles, company, max_validate=MAX_VALIDATED)
        validated_urls = {_url_normalize(r.get("link") or r.get("url", "")) for r in validated}
        if len(validated) + len(social) < MIN_MENTIONS:
            for r in _deduplicate(articles):
                if len(validated) + len(social) >= MIN_MENTIONS:
                    break
                u = _url_normalize(r.get("link") or r.get("url", ""))
                if u and u not in validated_urls:
                    r = dict(r)
                    r["score"] = r.get("score", 50)
                    validated.append(r)
                    validated_urls.add(u)
        articles = validated

    combined = social + articles

    # 7. Rank by source weight + recency (+ forum boost); sort by score descending
    source_weights = _load_source_weights()
    for r in combined:
        r["score"] = int(_ranking_score(r, source_weights))
    combined.sort(key=lambda x: -x.get("score", 0))
    top = combined[:max(MIN_MENTIONS, TOP_RESULTS)]

    if llm_rerank and len([r for r in top if r.get("type") == "article"]) > 1:
        art = [r for r in top if r.get("type") == "article"]
        soc = [r for r in top if r.get("type") != "article"]
        reranked = _llm_rerank(art, company)
        top = soc + reranked[:TOP_RESULTS]

    out = []
    for r in top:
        raw_link = r.get("link", r.get("url", "")) or ""
        resolved_link = _resolve_link_for_response(raw_link)
        # Never surface Google News redirect URLs; only include results with real publisher URLs
        if resolved_link and "news.google.com" in resolved_link:
            continue
        out.append({
            "title": r.get("title", ""),
            "link": resolved_link,
            "url": resolved_link,
            "source": r.get("source", "") or r.get("source_domain", ""),
            "score": r.get("score", 0),
            "publish_date": _format_date(r.get("publish_date") or r.get("timestamp")),
            "snippet": (r.get("snippet", "") or r.get("summary", "") or "")[:200],
            "summary": (r.get("summary", "") or r.get("snippet", "") or "")[:400],
            "sentiment": r.get("sentiment"),
            "type": r.get("type", "article"),
        })

    # 8. Optionally store validated live results in article_documents (background) for future DB-first retrieval
    if store_live_results and not forum_only and live_search_ran and out:
        thread = threading.Thread(
            target=_store_validated_live_results,
            args=(out, company, STORE_LIVE_CAP),
            daemon=True,
            name="store_live_mentions",
        )
        thread.start()

    return out
