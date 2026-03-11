# Unresolved URLs: Missing Articles and Workarounds

## How many articles are we missing?

When we **cannot resolve or fetch** a URL (timeout, 4xx/5xx, or trafilatura returns no text), we used to mark the RSS item as `failed` and **never** create an `article_document`. Those articles never appeared in entity_mentions or the Media Intelligence dashboard.

To get exact counts in your environment, run the diagnostic script (requires backend dependencies and MongoDB):

```bash
# From project root, with backend image built (script is inside the image):
docker compose exec backend python scripts/count_unresolved_urls.py
```

If you run the backend locally with a virtualenv:

```bash
cd backend && pip install -r requirements.txt && MONGODB_URL=mongodb://localhost:27017 python scripts/count_unresolved_urls.py
```

The script prints:

- **RSS failed** – `rss_items` with `status=failed` (articles that never became `article_documents`).
- **Failed with news.google.com** – subset of failed where the URL is a Google News redirect.
- **Entity mentions with empty or news.google.com URL** – we have the mention but the link is bad/unresolved.
- **Article documents with news.google.com URL** – stored URL is still the redirect (resolution not run or failed).

So:

- **“Missing” articles** = count of `rss_items` with `status=failed` (before the workaround below).
- **Mentions with bad link** = entity_mentions with empty URL or URL containing `news.google.com`.

---

## Workarounds implemented

### 1. Store metadata when fetch fails (article fetcher)

**Implemented.** When `_fetch_and_extract(url)` fails (no full text), we no longer only set `rss_items.status = failed`. We now:

- Insert a **metadata-only** `article_document`: `article_text=""`, `article_length=0`, `title` and `summary` from RSS, `url` / `url_original` / `url_resolved` from the fetcher.
- Set `rss_items.status = processed` so we don’t retry indefinitely.
- Rely on **entity_mentions_worker** to create mentions from title + summary (snippet path) and set `content_quality = "snippet"`.

So we **no longer drop** those articles: they appear in the feed as snippet-only, and the count of “missing” articles from failed fetches goes to zero for new runs.

### 2. Background URL resolution job (cron-friendly)

**Implemented.** The script `scripts/fix_redirected_urls.py` resolves `news.google.com` (and other redirect) URLs and updates the DB. It does **not** run in the crawler pipeline, so it does not block ingestion.

- Updates **article_documents** and **entity_mentions** with the final resolved URL and sets **resolved_at**.
- Run in batches with `--limit` for cron; safe to run repeatedly.

```bash
# One-off full run
docker compose exec backend python scripts/fix_redirected_urls.py

# Batch (e.g. for daily cron so crawler is not impacted)
docker compose exec backend python scripts/fix_redirected_urls.py --limit 100
```

Example cron (daily at 2 AM, small batch):  
`0 2 * * * cd /app && python scripts/fix_redirected_urls.py --limit 100`

### 3. Show original URL when resolved is missing (UI)

**Implemented.** The Media Intelligence feed returns **url_original** for each item. When the stored link is empty or still a redirect (e.g. `news.google.com`), the UI shows the best available link and labels it **"Open (may redirect) →"** so users can still open the article.


---

## Summary

- **How many missing:** Run `scripts/count_unresolved_urls.py` and use **RSS failed** (and optionally **entity_mentions** with bad URL) for your numbers.
- **Fix for new items:** Article fetcher now stores **metadata-only** documents on fetch failure, so those articles are no longer missing and appear as snippet-only in Media Intelligence.
- **Existing data:** Run **fix_redirected_urls.py** (with optional `--limit`) on a schedule; the UI shows **url_original** with “Open (may redirect)” until links are resolved.
