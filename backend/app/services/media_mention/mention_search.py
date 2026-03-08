"""
Media mention search - combines all monitoring sources via mention_retrieval_service,
plus live article discovery (Google News RSS, Tavily/DuckDuckGo) when fewer than 10.
Deduplicates, validates, quality scores, optionally reranks.
"""
import re
from datetime import datetime
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

MAX_CANDIDATES = 10
MAX_VALIDATED = 5
MIN_MENTIONS = 10
MAX_CONCURRENT = 2
TIMEOUT = 5
VALIDATION_CHARS = 1500
MIN_SCORE = 50
TOP_RESULTS = 5
LLM_MAX_TOKENS = 200
TITLE_SIMILARITY_THRESHOLD = 0.85


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


def _search_google_news_rss(company: str, max_results: int = 5) -> list[dict]:
    """Fetch Google News RSS for company."""
    results = []
    try:
        import feedparser
        query = company.replace(" ", "+")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url, agent="ZyonMentionSearch/1.0")
        for e in feed.entries[:max_results]:
            link = e.get("link") or e.get("id", "")
            if link:
                pub = e.get("published_parsed") or e.get("updated_parsed") or e.get("published")
                results.append({
                    "title": (e.get("title") or "")[:500],
                    "link": link,
                    "source": (e.get("source", {}).get("title", "")) if isinstance(e.get("source"), dict) else "",
                    "snippet": (e.get("summary", "") or "")[:300],
                    "publish_date": _format_date(pub),
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
                if not passed:
                    continue
                if score < MIN_SCORE:
                    continue
                r = dict(r)
                r["score"] = score
                r["mention_count"] = mention_count
                r["validation_passed"] = passed
                logger.info("mention_result", query=company, url=url, score=score, mention_count=mention_count, source=r.get("source"), validation_passed=passed)
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


def _fetch_more_articles(company: str) -> list[dict]:
    """Fetch more articles via media_monitor_service (Google News + DuckDuckGo)."""
    try:
        from app.services.media_monitor_service import search_entity
        items = search_entity(company, company, sources=["google_news", "duckduckgo"])
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


def _retrieval_to_mention(r: dict) -> dict:
    """Convert mention_retrieval output to search_mentions output format."""
    url = r.get("url", "")
    return {
        "title": r.get("title", ""),
        "link": url,
        "url": url,
        "source": r.get("source", ""),
        "summary": r.get("summary", ""),
        "snippet": (r.get("summary") or "")[:200],
        "timestamp": r.get("timestamp", ""),
        "publish_date": r.get("timestamp", ""),
        "type": r.get("type", "article"),
    }


def search_mentions(
    company: str,
    use_internal: bool = True,
    use_google_news: bool = True,
    use_external: bool = True,
    llm_rerank: bool = True,
) -> list[dict]:
    """
    Retrieve mentions from all monitoring sources (media_articles, social_posts) via
    mention_retrieval_service. If fewer than MIN_MENTIONS, trigger article discovery
    (Google News + DuckDuckGo). Returns unified list: title, source, summary, url,
    timestamp, type (article|reddit|youtube|twitter).
    """
    all_results: list[dict] = []
    seen_urls: set[str] = set()

    # 1. Retrieve from MongoDB (media_articles, social_posts)
    try:
        from app.services.mention_retrieval_service import retrieve_mentions
        retrieval = retrieve_mentions(company, min_count=MIN_MENTIONS)
        for r in retrieval:
            m = _retrieval_to_mention(r)
            url = (m.get("url") or m.get("link", "")).strip().lower()
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(m)
    except Exception as e:
        logger.warning("mention_retrieval_failed", company=company, error=str(e))

    # 2. If fewer than MIN_MENTIONS, trigger article discovery
    if len(all_results) < MIN_MENTIONS and use_internal:
        for r in _fetch_more_articles(company):
            url = (r.get("url") or r.get("link", "")).strip().lower()
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

    # 3. Supplement with Google News RSS and external (Tavily/DuckDuckGo) if still short
    if len(all_results) < MIN_MENTIONS and use_google_news:
        for r in _search_google_news_rss(company, max_results=5):
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

    if len(all_results) < MIN_MENTIONS and use_external:
        try:
            from app.services.url_discovery.url_search_service import search as external_search
            for r in external_search(f'"{company}" news OR articles OR blog', max_results=10):
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

    # 4. Split: social (from DB) vs articles (may need validation)
    social = [r for r in all_results if r.get("type") != "article"]
    articles = [r for r in all_results if r.get("type") == "article"]

    # 5. Validate and score article-type items
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

    # 6. Sort: social first, then articles by score desc
    def sort_key(x):
        if x.get("type") != "article":
            return (0, 0)
        return (1, -x.get("score", 0))

    combined.sort(key=sort_key)
    top = combined[:max(MIN_MENTIONS, TOP_RESULTS)]

    if llm_rerank and len([r for r in top if r.get("type") == "article"]) > 1:
        art = [r for r in top if r.get("type") == "article"]
        soc = [r for r in top if r.get("type") != "article"]
        reranked = _llm_rerank(art, company)
        top = soc + reranked[:TOP_RESULTS]

    return [
        {
            "title": r.get("title", ""),
            "link": r.get("link", r.get("url", "")),
            "source": r.get("source", ""),
            "score": r.get("score", 0),
            "publish_date": _format_date(r.get("publish_date") or r.get("timestamp")),
            "snippet": (r.get("snippet", "") or r.get("summary", "") or "")[:200],
            "type": r.get("type", "article"),
        }
        for r in top
    ]
