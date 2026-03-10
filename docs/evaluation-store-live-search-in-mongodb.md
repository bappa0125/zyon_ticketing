# Evaluation: Storing Live-Search Results in MongoDB

**Goal:** Determine whether validated live-search articles can be safely stored in `article_documents` so future queries are served from DB-first, without changing MongoDB schema, entity_mentions pipeline, entity detection, or the ingestion scheduler.

**Conclusion:** **YES** — the architecture supports it. Reusing existing `article_documents` plus current deduplication and the existing entity_mentions_worker is feasible. Below are the answers to each question and the recommended insertion point.

---

## Current System (Confirmed)

- **Flow:** `chat.py` → `mention_search.search_mentions(entity)` → `retrieve_mentions_db_first(entity)`.
- **Collections used for retrieval:** `entity_mentions`, `article_documents`, `media_articles`, `social_posts`.
- **Live search (no storage today):**
  - `_fetch_more_articles` (internal: media_monitor_service)
  - `_search_google_news_rss`
  - `url_search_service.search` (external)
- These return in-memory results only; nothing is written to MongoDB.

---

## 1. Can `article_documents` be reused for live-search articles without schema changes?

**YES.**

- **Schema in use:** `article_fetcher` and `forum_ingestion_worker` both write to `article_documents` with the same logical shape. No collection is “RSS-only”; the schema is generic.
- **Fields used (from code):**
  - **Required for dedup:** `url`, `url_resolved`, `url_original`, `normalized_url`, `url_hash`, `content_hash`
  - **Content:** `title`, `article_text`, `article_length`, `summary` (optional)
  - **Meta:** `source_domain`, `published_at`, `fetched_at`, `entities` (list)
- **Live-search inputs:** We have title, snippet, link (resolved URL), source, publish_date from live search. After fetching the full page we get `article_text`, `url_resolved`, and can set `published_at` from the result or `fetched_at`, and `summary` from snippet. `forum_ingestion_worker` already shows that `article_documents` is used without `rss_items` (no `rss_feed` or `status`); it sets `published_at` to `fetched_at` and omits `summary` when not available.
- **Conclusion:** The same document shape can represent live-search articles. No new fields or collections are required.

---

## 2. Does current deduplication prevent duplicate storage if the same article later arrives via RSS?

**YES.**

- **Mechanisms:**
  - **Unique indexes:** `article_fetcher` and `forum_ingestion_worker` both ensure `url_hash` and `content_hash` unique indexes (create_index in code; same indexes are assumed for any writer).
  - **Checks before insert:**
    - `find_one({"url_hash": url_hash})` → skip if exists
    - `find_one({"content_hash": content_hash})` → skip if exists
  - **Hash definitions:**
    - `url_hash = md5(normalize(url_resolved))`
    - `content_hash = md5(normalized_title + resolved_url)` (both trimmed/lowercased)
- **Live search → store first:** We store using resolved URL and title → `url_hash` and `content_hash` are set. Later, RSS ingestion for the same article will resolve to the same URL and get the same title from the feed → same hashes → `find_one` finds the existing doc → RSS path skips insert (or duplicate key on insert if we didn’t check).
- **RSS → store first:** Same hashes. If we later try to store from live search, we’d hit the same doc and skip.
- **Conclusion:** Existing deduplication (url_hash + content_hash) protects against duplicates regardless of whether the article first came from live search or RSS. No schema change needed.

---

## 3. Source flag: new field vs existing fields?

**Existing fields do NOT distinguish source.**

- **`source_domain`:** Set from the **URL’s netloc** (e.g. `inc42.com`, `economictimes.indiatimes.com`). It identifies the publisher, not the ingestion path (RSS vs live search).
- **No other field** in the current document indicates “from live search” vs “from RSS” vs “from forum.”
- **Constraint:** “Do NOT change MongoDB schema” is interpreted as no new required fields and no structural change. Adding an optional field (e.g. `origin: "live_search"`) would be a small schema extension; if we strictly avoid any new field, we **cannot** distinguish source in the document.
- **Recommendation:** For analytics/debugging, an optional field could be added later; for correctness and deduplication, **no source flag is required**. Dedup and entity_mentions_worker depend only on url/title/content and entity, not on origin.

---

## 4. Safest insertion point

**Recommended: inside `mention_search.py`, after the final ranked list is built and before returning (i.e. after step 7, in a new step 8).**

- **Why not inside `_fetch_more_articles` or `_search_google_news_rss`?**  
  Those only return lightweight result dicts (title, link, snippet, etc.). They don’t run validation, entity detection, or context validation. Pushing storage there would duplicate validation logic and mix “search” with “persistence” in multiple places.

- **Why not inside `url_search_service`?**  
  Same idea: url_search is generic search; it doesn’t know about entity, context_keywords, or our validation. Storage would require passing entity and validation into that layer and would spread “mention storage” across modules.

- **Why after ranking (after step 7)?**  
  By then we have:
  - Only **validated** items (passed `_validate_and_score`: fetch 1500 chars, company in text, score ≥ 50),
  - Deduplicated and ranked,
  - Google News URLs resolved/filtered in the final `out` list.
  So we only consider storing results we actually return (or a subset). We avoid storing low-quality or unvalidated URLs.

- **Concrete placement:** In `search_mentions()`, after building `out` (the list that is returned), add a loop: for each item in `out` (or a capped subset, e.g. first 5–10 per run), call a **sync helper** that:
  1. Resolves redirect if needed (reuse existing resolver).
  2. Fetches **full** article (reuse `article_fetcher._fetch_and_extract` for trafilatura + resolved URL).
  3. Runs `detect_entity(title + article_text)`.
  4. Runs `validate_mention_context(entity, article_text)`.
  5. If valid: build `article_documents` doc (same shape as article_fetcher), check `url_hash` / `content_hash`, insert if missing.

- **Reuse:** Use `article_fetcher._fetch_and_extract`, `_url_hash`, `_normalize_url`, `_content_hash`, `_source_domain_from_url` (all sync), plus `entity_detection_service.detect_entity` and `mention_context_validation.validate_mention_context`. No change to entity_mentions pipeline or scheduler.

---

## 5. Capping storage per entity per run

**Recommended: yes, cap the number of live-search articles stored per `search_mentions` call (e.g. 5–10 per run).**

- **Reason:** Live search can return many candidates (e.g. up to TOP_RESULTS + Google News 20 + external). Storing all validated results in one request could cause a burst of writes and full-page fetches. A cap (e.g. “store at most N articles per entity per run”) limits load and keeps behavior predictable.
- **Implementation:** In the new step-8 loop, process only the first N items from `out` (e.g. N=5 or 10). No schema change; purely in-code.

---

## 6. Will this interfere with the entity_mentions_worker pipeline?

**No. The worker will still process new documents and insert into `entity_mentions` as today.**

- **Worker logic:**  
  - Aggregation: `$lookup(entity_mentions, article_documents.url = entity_mentions.url)` → `$match(mentions.size == 0)` → articles whose `url` is **not** yet in `entity_mentions`.  
  - For each such document it reads: `url`, `title`, `source_domain`, `published_at`, `article_text`, `summary`, and optionally `url_resolved`.  
  - It runs `detect_entity(title + rss_summary + article_text)` and `validate_mention_context(entity, article_text)`, then inserts into `entity_mentions` with dedup on `(entity, url)`.

- **Live-search inserts:**  
  We insert into `article_documents` with the same `url` (resolved), `title`, `article_text`, `source_domain`, `published_at`, `summary` (snippet), and optionally `entities` (if we run detect_entity at store time). The worker does **not** depend on `rss_items` or any “source” field; it only depends on these fields.

- **Double detection:**  
  We can run `detect_entity` and `validate_mention_context` at store time to decide *whether* to insert into `article_documents`. The worker will run them again on the same doc. That’s redundant but safe and keeps behavior consistent with RSS/forum docs (worker always does its own detection and validation).

- **Conclusion:** Storing validated live-search articles in `article_documents` does not interfere with the entity_mentions_worker; it will pick them up in the next run and create `entity_mentions` as for any other article.

---

## Summary Table

| Question | Answer |
|--------|--------|
| 1. Reuse `article_documents` without schema change? | **YES** — same document shape as RSS/forum. |
| 2. Dedup prevents duplicates when same article comes via RSS later? | **YES** — url_hash + content_hash. |
| 3. Source flag? | Existing fields do **not** distinguish; optional field possible later; not required for correctness. |
| 4. Safest insertion point? | **Inside `mention_search.py`, after building the final `out` list (after step 7).** |
| 5. Cap per run? | **Recommended** — e.g. store at most 5–10 per `search_mentions` call. |
| 6. Interference with entity_mentions_worker? | **No** — worker will process new docs and insert into `entity_mentions` as today. |

---

## Risks (and mitigations)

| Risk | Mitigation |
|------|------------|
| **Duplicate key on insert** | Check `url_hash` and `content_hash` before insert; catch E11000 and treat as skip (same as article_fetcher). |
| **Full-page fetch latency in request** | Run store step asynchronously (e.g. fire-and-forget task or background queue) or cap and accept a small delay; avoid blocking the main response. |
| **Different extraction (BeautifulSoup vs trafilatura)** | Use `article_fetcher._fetch_and_extract` (trafilatura) for storage so stored text matches RSS path and worker expectations. |
| **Flooding DB** | Cap number of articles stored per `search_mentions` call (e.g. 5–10). |
| **Schema drift** | Build the doc with exactly the same fields as `article_fetcher`/`forum_ingestion_worker` (no new required fields). |

---

## Architecture support: YES

The existing ingestion and entity-detection pipeline can safely store validated live-search results in MongoDB:

- **Reuse:** `article_documents` schema and existing deduplication (url_hash, content_hash, normalized_url).
- **Reuse:** `article_fetcher._fetch_and_extract`, hash/domain helpers, `detect_entity`, `validate_mention_context`.
- **Insertion point:** `mention_search.py`, after the final ranked list is built.
- **No changes:** MongoDB schema (unless you add an optional origin field later), entity_mentions pipeline, entity detection logic, ingestion scheduler.

Future queries for the same entity will then retrieve these articles via `retrieve_mentions_db_first` (entity_mentions and article_documents), reducing repeated external live search.
