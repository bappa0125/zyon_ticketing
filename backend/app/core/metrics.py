"""Prometheus metrics endpoint."""
from fastapi import APIRouter, Response
from prometheus_client import (
    Counter,
    Histogram,
    REGISTRY,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from prometheus_client.core import GaugeMetricFamily

router = APIRouter()


class CrawlerMetricCollector:
    """Collector that reads crawler metrics from Redis (updated by worker)."""

    def collect(self):
        try:
            from redis import Redis
            from app.config import get_config
            r = Redis.from_url(get_config()["settings"].redis_url)
            pages = int(r.get("crawler:pages_crawled_total") or 0)
            alerts = int(r.get("crawler:alerts_generated_total") or 0)
            today = int(r.get("crawler:pages_crawled_today") or 0)
        except Exception:
            pages = alerts = today = 0
        yield GaugeMetricFamily(
            "pages_crawled_total",
            "Total pages crawled by competitor monitor",
            value=pages,
        )
        yield GaugeMetricFamily(
            "alerts_generated_total",
            "Total alerts generated from detected changes",
            value=alerts,
        )
        yield GaugeMetricFamily(
            "pages_crawled_today",
            "Pages crawled in the last 24 hours",
            value=today,
        )


REGISTRY.register(CrawlerMetricCollector())


class UrlDiscoveryMetricCollector:
    """Collector for URL discovery metrics from Redis."""

    def collect(self):
        try:
            from redis import Redis
            from app.config import get_config
            r = Redis.from_url(get_config()["settings"].redis_url)
            requests_total = int(r.get("url_discovery:requests_total") or 0)
            cache_hits = int(r.get("url_discovery:cache_hits") or 0)
            api_calls = int(r.get("url_discovery:api_calls") or 0)
            validation_requests = int(r.get("url_discovery:validation_requests") or 0)
        except Exception:
            requests_total = cache_hits = api_calls = validation_requests = 0
        yield GaugeMetricFamily("url_search_requests_total", "Total URL search requests", value=requests_total)
        yield GaugeMetricFamily("url_search_cache_hits", "URL search cache hits", value=cache_hits)
        yield GaugeMetricFamily("url_search_api_calls", "URL search API calls", value=api_calls)
        yield GaugeMetricFamily("url_validation_requests", "URL validation requests", value=validation_requests)


REGISTRY.register(UrlDiscoveryMetricCollector())


class MediaIndexMetricCollector:
    """Collector for media index metrics from Redis."""

    def collect(self):
        try:
            from redis import Redis
            from app.config import get_config
            r = Redis.from_url(get_config()["settings"].redis_url)
            articles = int(r.get("media_index:articles_indexed_total") or 0)
            cycles = int(r.get("media_index:crawler_cycles_total") or 0)
            searches = int(r.get("media_index:media_search_requests") or 0)
        except Exception:
            articles = cycles = searches = 0
        yield GaugeMetricFamily("articles_indexed_total", "Total articles indexed in media index", value=articles)
        yield GaugeMetricFamily("crawler_cycles_total", "Total media index crawl cycles", value=cycles)
        yield GaugeMetricFamily("media_search_requests", "Media search API requests", value=searches)


REGISTRY.register(MediaIndexMetricCollector())

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
)
CHAT_REQUESTS = Counter("chat_requests_total", "Total chat requests")
CHAT_TOKENS = Counter("chat_tokens_total", "Total tokens streamed", ["role"])


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
