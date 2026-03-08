"""URL Discovery agent - orchestrates search, validation, cache, optional LLM."""
from typing import Optional

from app.config import get_config
from app.core.logging import get_logger
from app.services.url_discovery.url_search_service import search
from app.services.url_discovery.url_validator import validate_results
from app.services.url_discovery.url_cache import get_cached, set_cached, get_redis

logger = get_logger(__name__)

MAX_QUERIES = 1
MAX_RESULTS = 10
MAX_VALIDATION = 5
RATE_LIMIT_PER_MIN = 3
RATE_LIMIT_KEY = "url_discovery:rate:min"


def _build_search_query(company: str, extra: str = "") -> str:
    """Build search query for mentions."""
    base = f'"{company}" news OR blog OR mention'
    if extra:
        return f"{base} {extra}"
    return base


def _summarize_with_llm(results: list[dict], max_tokens: int = 200) -> Optional[str]:
    """Optional LLM summarization - only titles, snippets, URLs. Top 5 results."""
    if not results:
        return None
    cfg = get_config()
    api_key = cfg["settings"].openrouter_api_key
    if not api_key:
        return None
    top5 = results[:5]
    context = "\n".join(
        f"- {r.get('title', '')} | {r.get('link', '')} | {r.get('snippet', '')[:100]}"
        for r in top5
    )
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url=cfg["openrouter"].get("base_url", "https://openrouter.ai/api/v1"),
            api_key=api_key,
        )
        model = cfg.get("llm", {}).get("model", "openrouter/free")
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": f"Summarize these URL results in 2-3 sentences:\n{context}",
            }],
            max_tokens=max_tokens,
        )
        if resp.choices:
            return resp.choices[0].message.content
    except Exception as e:
        logger.warning("url_summarize_llm_failed", error=str(e))
    return None


def _check_rate_limit(redis) -> bool:
    """Max 3 searches per minute. Returns True if allowed."""
    key = RATE_LIMIT_KEY
    count = redis.incr(key)
    if count == 1:
        redis.expire(key, 60)
    return count <= RATE_LIMIT_PER_MIN


def _inc_url_metric(name: str):
    """Increment Redis-backed URL discovery metric."""
    try:
        r = get_redis()
        r.incr(f"url_discovery:{name}")
    except Exception:
        pass


def discover_urls(
    company_or_topic: str,
    summarise: bool = False,
    extra_query: str = "",
) -> dict:
    """
    Main entry: search, validate, optionally summarize.
    Enforces limits: 1 query, 10 results, 5 validations, 3 req/min.
    """
    redis = get_redis()

    if not _check_rate_limit(redis):
        _inc_url_metric("requests_total")
        return {"error": "Search rate limit reached.", "results": []}

    search_query = _build_search_query(company_or_topic, extra_query)

    cached = get_cached(redis, search_query)
    if cached:
        _inc_url_metric("cache_hits")
        _inc_url_metric("requests_total")
        return {"results": cached, "cached": True}

    _inc_url_metric("requests_total")
    _inc_url_metric("api_calls")

    raw_results = search(search_query, max_results=MAX_RESULTS)

    if not raw_results:
        return {"results": [], "cached": False}

    validated = validate_results(raw_results, company_or_topic, max_pages=MAX_VALIDATION)
    for _ in validated:
        _inc_url_metric("validation_requests")

    # If validation returns nothing (bot blocking, strict match), use raw results
    results_to_use = validated if validated else raw_results[:5]

    set_cached(redis, search_query, results_to_use)

    summary = None
    if summarise and results_to_use:
        summary = _summarize_with_llm(validated)

    return {
        "results": results_to_use,
        "cached": False,
        "summary": summary,
    }
