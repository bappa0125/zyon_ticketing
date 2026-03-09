# Pipeline Stabilization

This document describes the stabilization improvements applied to the Zyon AI monitoring ingestion and retrieval pipeline. The goal is to make the pipeline more reliable and reduce false positives while preserving all existing behavior.

## Overview

The pipeline flow after stabilization:

```
media_sources.yaml
  → RSS ingestion
  → freshness filter (72h)
  → article extraction
  → URL resolution (original + resolved)
  → deduplication (content_hash)
  → article_documents
  → entity detection
  → context validation
  → entity_mentions
  → DB-first retrieval
  → chat citations in UI
```

---

## 1. DB-First Mention Retrieval

**Problem:** The chatbot sometimes performed live search immediately, adding latency and external dependency.

**Solution:** A retrieval stage checks MongoDB first. The flow is:

1. **User query** → Intent classifier → Entity detection
2. **MongoDB mention retrieval** — query `entity_mentions`, `media_articles`, and `social_posts` for the detected entity
3. **If results exist** — return them (sort by `published_at` descending, limit 10)
4. **Else** — fall back to the existing search pipeline (retrieve_mentions + live discovery)

**Implementation:**

- `mention_retrieval_service.retrieve_mentions_db_first(entity, limit=10)` queries the three collections, merges and deduplicates by URL, sorts by `published_at` (or timestamp), and returns up to 10 items.
- `mention_search.search_mentions(company, ...)` calls `retrieve_mentions_db_first(company)` first; if the list is non-empty, it maps to the response shape expected by the chat (title, link, source, publish_date, snippet, type, score, sentiment) and returns. Otherwise it continues with the existing retrieval and live search.

**Returned fields:** title, source_domain, published_at, summary, sentiment, url, type.

**Important:** The existing search pipeline is not removed; it is only wrapped with a DB-first stage.

---

## 2. Google News Redirect URL Resolution

**Problem:** Google RSS feeds return redirect URLs (e.g. `news.google.com/rss/articles/…`). Downstream logic needs the final destination URL.

**Solution:** The **article fetch** stage (only) was extended:

- HTTP requests already use `follow_redirects=True` (httpx).
- After the request, both URLs are stored:
  - **`url_original`** — the URL from the feed or link
  - **`url_resolved`** — the final URL after redirects (`resp.url`)
- The canonical `url` field stored in documents is set to **`url_resolved`** so downstream services (dedup, citations, links) use the resolved URL.

**Implementation:** In `article_fetcher._fetch_and_extract(url)` the return value includes `(text, length, url_original, url_resolved)`. The document written to `article_documents` includes `url_original`, `url_resolved`, and `url` = `url_resolved`. Deduplication and hashing use the resolved URL.

**Important:** RSS ingestion logic was not modified; only the article fetch stage was extended.

---

## 3. Context-Aware Entity Validation

**Problem:** Ambiguous entities (e.g. “Sahi”) produce false positives when the word appears in a non-relevant context (e.g. “sahi hai” in Hindi, or healthcare AI).

**Solution:** A validation layer runs **after** entity detection (alias → regex → NER → LLM). A mention is considered valid only if:

1. An entity was detected, **and**
2. For entities with context rules: at least one **context keyword** appears in the article text, **and**
3. The text does **not** match any **ignore pattern**.

**Configuration:** `config/clients.yaml` is extended per client with:

- **`context_keywords`** — list of strings (e.g. trading, broker, demat, stock). For clients/entities that have this list, at least one keyword must appear in the article text.
- **`ignore_patterns`** — existing list; any phrase match in the text causes the mention to be discarded.

**Implementation:**

- `app/services/mention_context_validation.validate_mention_context(entity, article_text)` loads client config, finds the client for the entity (by name or competitor), applies ignore_patterns first (discard if any match), then requires at least one context_keyword in text if that client has context_keywords defined.
- When the pipeline writes to `entity_mentions`, it should call `validate_mention_context(entity, article_text)` and only insert if it returns `True`.

**Important:** The entity detection pipeline (alias, regex, NER, LLM) was not modified; validation is added only after detection.

---

## 4. Strong Deduplication

**Problem:** RSS and aggregators (e.g. Google News, site RSS) can produce the same article with different URLs or minor title variants, leading to duplicates.

**Solution:** A deduplication stage before insert:

- **Content hash:** `content_hash = md5(normalized_title + resolved_url)` (e.g. title stripped and lowercased, URL the resolved one).
- A **`content_hash`** field is added to article documents.
- A **unique index** on `content_hash` is created so duplicate (title, URL) pairs are rejected at insert time.
- Before fetching an article, we also check for an existing document with the same `content_hash` and skip if found (avoiding unnecessary HTTP and duplicate inserts).

**Implementation:** In `article_fetcher`: `_content_hash(normalized_title, resolved_url)`; document includes `content_hash`; `article_documents` has a unique index on `content_hash`. Existing `url_hash` and its index are unchanged.

**Important:** Existing schema fields were not removed; only the new field and index were added.

---

## 5. RSS Freshness Window

**Problem:** RSS feeds often re-emit older articles; ingesting them adds noise and duplicates.

**Solution:** A freshness filter during RSS ingestion:

- **Rule:** Ignore items with `published_at` older than **72 hours** (configurable via `monitoring.rss_ingestion.freshness_window_hours`).
- Applied **before** inserting into `rss_items`; items that are too old are skipped and not written.

**Implementation:** In `rss_ingestion.run_rss_ingestion`, a cutoff is computed as `now - freshness_window_hours` (default 72). Each entry’s `published_at` is compared to this cutoff; if older, the item is skipped and not inserted. Scheduler and crawler logic are unchanged.

---

## Testing

After implementation, verify:

1. **Query:** “latest mentions of Zerodha”  
   **Expected:** Results are retrieved from MongoDB first when available. Citations include title, source, summary, sentiment, url.

2. **Query:** “latest mentions of Sahi trading app”  
   **Expected:** Healthcare or unrelated “Sahi” results are filtered when context_keywords and ignore_patterns are configured for Sahi.

3. **Restart backend** and repeat the same queries. If new articles appear after ingestion runs, DB-first retrieval is returning data from MongoDB correctly.

---

## Related Docs

- [Monitoring ingestion pipeline](monitoring_ingestion_pipeline.md)
- [Entity detection](entity_detection.md)
- [Article fetcher](article_fetcher.md)
- [RSS ingestion](rss_ingestion.md)
