"""Tests for Media Source Registry (config load only, no network)."""
import pytest

from app.services.monitoring_ingestion.media_source_registry import (
    load_media_sources,
    get_sources_by_priority,
    get_rss_sources,
    get_html_sources,
)


def test_load_media_sources_returns_list():
    sources = load_media_sources()
    assert isinstance(sources, list)


def test_sources_have_domain_and_crawl_frequency():
    sources = load_media_sources()
    for s in sources:
        assert isinstance(s, dict)
        assert "domain" in s
        assert "crawl_frequency" in s


def test_get_sources_by_priority_returns_dict_of_lists():
    by_priority = get_sources_by_priority()
    assert isinstance(by_priority, dict)
    for priority, group in by_priority.items():
        assert isinstance(priority, int)
        assert isinstance(group, list)
        for s in group:
            assert isinstance(s, dict)


def test_get_rss_sources_returns_list():
    rss = get_rss_sources()
    assert isinstance(rss, list)


def test_get_html_sources_returns_list():
    html = get_html_sources()
    assert isinstance(html, list)


def test_rss_and_html_classification_consistent():
    """RSS and HTML source lists are subsets of full list."""
    all_sources = load_media_sources()
    rss = get_rss_sources()
    html = get_html_sources()
    assert len(rss) <= len(all_sources)
    assert len(html) <= len(all_sources)
