# Sample MongoDB Results

Sample document shapes for the collections used by the monitoring and chat pipeline. These match what the code writes and what DB-first retrieval reads.

---

## 1. `rss_items`

RSS metadata only (no article body). Written by **RSS ingestion**; consumed by the article fetcher.

```json
{
  "_id": {"$oid": "65f1a2b3c4d5e6f700000001"},
  "title": "Sahi launches new options trading feature for retail investors",
  "url": "https://economictimes.indiatimes.com/markets/stocks/news/sahi-options-trading.html",
  "source_domain": "economictimes.indiatimes.com",
  "published_at": {"$date": "2025-03-05T08:30:00.000Z"},
  "discovered_at": {"$date": "2025-03-05T12:00:00.000Z"},
  "rss_feed": "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
  "status": "new"
}
```

---

## 2. `article_documents`

Full article text after fetch + trafilatura. Written by **article fetcher** (after RSS). Has `url_original`, `url_resolved`, `content_hash` for dedup.

```json
{
  "_id": {"$oid": "65f1a2b3c4d5e6f700000002"},
  "url": "https://economictimes.indiatimes.com/markets/stocks/news/sahi-options-trading.html",
  "url_original": "https://news.google.com/rss/articles/CBMi...",
  "url_resolved": "https://economictimes.indiatimes.com/markets/stocks/news/sahi-options-trading.html",
  "normalized_url": "https://economictimes.indiatimes.com/markets/stocks/news/sahi-options-trading.html",
  "url_hash": "a1b2c3d4e5f6789012345678abcdef01",
  "content_hash": "f0e1d2c3b4a596877869594837261514",
  "source_domain": "economictimes.indiatimes.com",
  "title": "Sahi launches new options trading feature for retail investors",
  "published_at": {"$date": "2025-03-05T08:30:00.000Z"},
  "article_text": "Sahi, the discount brokerage platform, announced...",
  "article_length": 2450,
  "fetched_at": {"$date": "2025-03-05T12:05:00.000Z"}
}
```

*Note: `entity` is added by a later pipeline step when entity detection runs; until then DB-first does not match `article_documents` by entity.*

---

## 3. `media_articles`

Live search results (Google News RSS, DuckDuckGo) stored by **media monitor worker**. Used for DB-first and coverage.

```json
{
  "_id": {"$oid": "65f1a2b3c4d5e6f700000003"},
  "entity": "Sahi",
  "client": "Sahi",
  "title": "Sahi trading app sees 2x growth in derivatives users",
  "url": "https://www.moneycontrol.com/news/business/sahi-derivatives-growth-1234567.html",
  "source": "moneycontrol.com",
  "timestamp": {"$date": "2025-03-06T10:00:00.000Z"},
  "snippet": "Sahi, the fintech brokerage, reported a doubling of derivatives traders on its platform in Q4..."
}
```

---

## 4. `social_posts`

Reddit/YouTube/Twitter mentions. Written by **reddit_worker**, **youtube_worker**, **social_monitor_worker**.

**Reddit example:**

```json
{
  "_id": {"$oid": "65f1a2b3c4d5e6f700000004"},
  "platform": "reddit",
  "entity": "Sahi",
  "text": "Switched to Sahi for options – lower brokerage and clean app. Anyone else using Sahi for F&O?",
  "url": "https://www.reddit.com/r/IndianStreetBet/comments/abc123/",
  "content_hash": "aabbccdd11223344",
  "engagement": {"score": 42, "num_comments": 8},
  "timestamp": {"$date": "2025-03-05T14:22:00.000Z"}
}
```

**YouTube example (typical shape):**

```json
{
  "_id": {"$oid": "65f1a2b3c4d5e6f700000005"},
  "platform": "youtube",
  "entity": "Zerodha",
  "text": "Zerodha vs Sahi vs Groww – which broker for beginners in 2025",
  "url": "https://www.youtube.com/watch?v=xyz789",
  "timestamp": {"$date": "2025-03-04T09:00:00.000Z"}
}
```

---

## 5. `entity_mentions`

Unified mentions (entity + title, url, summary, sentiment). Populated when the pipeline runs entity detection and context validation and writes to this collection. **DB-first retrieval** reads from here when present.

```json
{
  "_id": {"$oid": "65f1a2b3c4d5e6f700000006"},
  "entity": "Sahi",
  "title": "Sahi launches new options trading feature for retail investors",
  "source_domain": "economictimes.indiatimes.com",
  "published_at": {"$date": "2025-03-05T08:30:00.000Z"},
  "summary": "Sahi, the discount brokerage platform, announced a new options trading feature...",
  "sentiment": "positive",
  "url": "https://economictimes.indiatimes.com/markets/stocks/news/sahi-options-trading.html",
  "type": "article"
}
```

---

## What the chat sees (DB-first output)

When `retrieve_mentions_db_first("Sahi")` runs, it returns a **list of dicts** (not raw MongoDB docs), e.g.:

```json
[
  {
    "title": "Sahi launches new options trading feature for retail investors",
    "source_domain": "economictimes.indiatimes.com",
    "published_at": "2025-03-05T08:30:00.000Z",
    "summary": "Sahi, the discount brokerage platform, announced...",
    "sentiment": "positive",
    "url": "https://economictimes.indiatimes.com/...",
    "type": "article"
  },
  {
    "title": "Switched to Sahi for options – lower brokerage...",
    "source_domain": "reddit",
    "published_at": "2025-03-05T14:22:00.000Z",
    "summary": "Switched to Sahi for options – lower brokerage and clean app...",
    "sentiment": null,
    "url": "https://www.reddit.com/r/IndianStreetBet/...",
    "type": "reddit"
  }
]
```

These are merged from `entity_mentions`, `article_documents` (when `entity` is set), `media_articles`, and `social_posts`, then deduped by URL and sorted by `published_at` descending.
