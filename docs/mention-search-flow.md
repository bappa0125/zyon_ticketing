# Mention search flow: when DB, live search, forum/social, Apify, and OpenRouter are used

This doc explains **step by step**, with **sample prompts** and **all combinations**, when:
- RSS/DB results are fetched
- Live search is fetched
- Forum and social mentions are fetched
- Forum/social-only filtering works
- Apify is called
- OpenRouter is called

---

## Part 1: When does the chat run “mention search” at all?

Mention search (MongoDB + optional live search) runs **only when all** of these are true:

1. **Intent** is classified as **search** (or chat + follow-up with an entity).
2. We have a **company/entity** to search for (e.g. "Sahi", "Zerodha").
3. The message is **in scope** for search (not greeting, not “recall questions”, not “out of scope”).

**Sample prompts that trigger search:**
- “Where was Sahi mentioned?”
- “Latest news on Sahi”
- “Show me recent mentions of Zerodha”
- “Show only forum or social mentions of Sahi”

**Sample prompts that do NOT trigger search:**
- “Hi” / “Hello” → greeting → **OpenRouter only**, no search.
- “What’s the weather?” → out of scope → suggested prompts only, **no search, no OpenRouter**.
- “Recall my questions” → recall flow → **no mention search**.

So: **RSS/DB and live search are only considered when the user asks a mention-style question with an entity.**

---

## Part 2: What runs when mention search *is* triggered?

When chat decides to run search, it calls **one** function:

- `search_mentions(company, ...)` in `mention_search.py`.

That function has a fixed order:

1. **DB-first** (MongoDB).
2. **Only if DB returns nothing**: live search (internal + Google News RSS + external).

So:

- **When are RSS/DB results used?**  
  Whenever MongoDB has at least one mention for the entity. Then we **return those** and **do not** run live search.

- **When is live search used?**  
  Only when the **first** DB step returns **no** results. Then we run internal + Google News RSS + (optionally) external search.

---

## Part 3: Step-by-step inside `search_mentions` (where DB vs live comes from)

### Step 1 — DB-first (RSS/DB results)

- **What:** `retrieve_mentions_db_first(company, limit=10)` from `mention_retrieval_service.py`.
- **Where data comes from (in order):**
  1. **entity_mentions** – entity + published_at (articles/forums that passed entity detection).
  2. **article_documents** – by `entities` (includes RSS→article_fetcher→entity_mentions pipeline).
  3. **media_articles** – from media monitor.
  4. **social_posts** – Reddit/YouTube/Twitter posts **already stored** in DB (populated by **scheduled** Apify workers, not by this request).

- **When you get “RSS feed / DB” results:**  
  Whenever **any** of these collections has documents for that entity. So:
  - **RSS → article_documents → entity_mentions** = “RSS/DB” articles.
  - **Forum ingestion → article_documents → entity_mentions** with `type: forum` = “forum” from DB.
  - **social_posts** = “social” from DB (Reddit, YouTube, Twitter stored by background jobs).

- **If Step 1 returns any results:**  
  We rank them (source weight + recency + forum boost), resolve/filter Google News URLs, and **return**.  
  **Live search is not run.**

**Sample:**  
Prompt: *“Where was Sahi mentioned?”*  
If MongoDB has Sahi in `entity_mentions` or `social_posts` → you see **RSS/DB + forum/social from DB**. No live search.

---

### Step 2 — Secondary DB (only if Step 1 returned nothing)

- **What:** `retrieve_mentions(company, min_count=MIN_MENTIONS)` – same service, different method.
- **Where:** `media_articles` and `social_posts` only.
- **When:** Only when Step 1 gave **no** results. So this is still “DB”, not “live”.

---

### Step 3 — Live search (only if DB still has no results)

We run live search **only when** `mongodb_had_results` is false and we still have no `all_results`:

1. **Internal** (`use_internal=True`): `_fetch_more_articles(search_query, company)`  
   - Uses `media_monitor_service.search_entity` (e.g. Google News + DuckDuckGo).  
   - This is **live** article search, not DB.

2. **Google News RSS** (`use_google_news=True`): `_search_google_news_rss(search_query, max_results=20)`  
   - Fetches Google News RSS **live** for the query.  
   - So “live search” here = **live** Google News RSS fetch.

3. **External** (`use_external=True`): `url_search_service.search(...)`  
   - External search API (e.g. Tavily/DuckDuckGo).  
   - Again **live**, not DB.

**Sample:**  
Prompt: *“Where was Sahi mentioned?”*  
If there are **no** Sahi rows in `entity_mentions`, `article_documents`, `media_articles`, or `social_posts` → we run **live search** (internal + Google News RSS + external). Results are then filtered, ranked, and URLs resolved (Google News redirects removed).

---

## Part 4: When are “forum” and “social” mentions fetched?

- **From DB:**  
  - **Forum:** From `entity_mentions` (and underlying `article_documents`) where `type == "forum"` (e.g. tradingqna.com, traderji.com). Filled by **forum_ingestion_worker** (scheduled).  
  - **Social:** From `social_posts` (Reddit, YouTube, Twitter). Filled by **reddit_worker**, **youtube_worker** (and optionally social_monitor_worker) when they run on the **scheduler**.

So “forum” and “social” in the **chat** are always **from MongoDB** at answer time. We don’t call Apify or scrape forums during the chat request.

- **Forum/social-only request:**  
  When the user says things like “Show only forum or social mentions of Sahi”:
  1. We still run the **same** `search_mentions("Sahi")` (DB first, then live if DB empty).
  2. In **chat.py**, we then **filter** the combined results to types: `forum`, `reddit`, `youtube`, `twitter`.
  3. If the filtered list is **empty**, we **don’t** call OpenRouter/Perplexity; we stream: *“No forum or social mentions found for **Sahi** in our monitored sources.”*
  4. If the filtered list is **non-empty**, we show only those (with a “Forum and social mentions only” header).

So:
- **Forum/social data** = from DB (and if DB had nothing, from live search, but we only *show* forum/social types).
- **Forum/social-only** = filter on types + explicit “no mentions” message when empty, and we never fall back to open-web (Perplexity) for that question.

---

## Part 5: When is Apify called?

Apify is **not** called during the chat or during `search_mentions`.

It is called only by **scheduled jobs** (see `ingestion_scheduler.py`):

| Job                 | What it does                          | When (default)   |
|---------------------|----------------------------------------|------------------|
| **reddit_monitor**  | Runs Reddit Apify actor, writes to `social_posts` | e.g. every 120 min |
| **youtube_monitor** | Runs YouTube Apify actor, writes to `social_posts` | e.g. every 120 min |

So:
- **When** Apify is called: on a **timer** (e.g. every 2 hours for Reddit/YouTube).
- **Effect:** New rows in `social_posts`. Later, when the user asks “Where was Sahi mentioned?” or “Show only forum or social mentions of Sahi”, we **read** from `social_posts` (and entity_mentions). So “social mentions” in the UI = data that **was** fetched by Apify in a **previous** scheduled run.

---

## Part 6: When is OpenRouter called?

OpenRouter is used only in the **chat** flow, in these cases:

| Scenario | OpenRouter called? | use_web_search (Perplexity)? |
|----------|--------------------|------------------------------|
| **Greeting** (e.g. “Hi”) | Yes | No |
| **Out of scope** (e.g. “What’s the weather?”) | No | No – we only show suggested prompts |
| **Recall questions** | No | No – different flow |
| **Mention search** with **some results** (DB or live) | No | No – we format and stream results directly |
| **Mention search**, **forum/social only**, **no forum/social results** | No | No – we stream “No forum or social mentions found” |
| **Mention search**, **no results**, **and not** “forum/social only” | Yes | Yes (Perplexity) – LLM does web search to try to answer |
| **Mention search**, **no results**, **and** “forum/social only” | No | No – we never use Perplexity for forum/social-only |
| **General chat** (no search, but in scope) | Yes | No (unless some other path sets it) |

So in short:
- **OpenRouter is called** when we need an LLM reply: e.g. greeting, or mention search with **no** results (and not forum/social-only).
- **Perplexity (open-web search)** is used only when we had **no** mention results and the user did **not** ask for “forum/social only”.

---

## Part 7: End-to-end examples (all in one place)

### Example 1: “Where was Sahi mentioned?” and DB has Sahi

1. Intent = search, entity = Sahi → **mention search runs**.
2. `search_mentions("Sahi")` → **Step 1 (DB-first)** returns rows (e.g. from `entity_mentions` / `social_posts`).
3. We **return those** (ranked, URLs cleaned). **No live search.** **No OpenRouter.**  
→ User sees **RSS/DB + forum/social from DB**.

### Example 2: “Where was Sahi mentioned?” and DB has no Sahi

1. Intent = search, entity = Sahi → **mention search runs**.
2. **Step 1 (DB-first)** returns nothing → **Step 2** still nothing → **Step 3 (live search)** runs: internal + Google News RSS + external.
3. We get live articles, rank, clean URLs, return. **No OpenRouter.**  
→ User sees **live search** results (no DB).

### Example 3: “Show only forum or social mentions of Sahi” and DB has forum/social for Sahi

1. Intent = search, entity = Sahi, **forum_only = true** (from `_is_forum_or_social_only_request`).
2. `search_mentions("Sahi")` runs (DB first, then live if needed).
3. In chat we **filter** to types `forum`, `reddit`, `youtube`, `twitter`. We have some → show only those with “Forum and social mentions only” header. **No OpenRouter.**  
→ User sees **forum/social only**, from DB (and if DB was empty, from live, but only forum/social types).

### Example 4: “Show only forum or social mentions of Sahi” and no forum/social results

1. Same as above, but after filtering, **no** forum/social items.
2. We stream: *“No forum or social mentions found for **Sahi** in our monitored sources.”*  
3. **No OpenRouter, no Perplexity.**  
→ User gets a clear “no mention” message and no wrong SAHI (e.g. healthcare) from the web.

### Example 5: “Hi”

1. Intent = greeting → **no mention search**.
2. We build messages with vector context and call **OpenRouter** (no web search).  
→ User gets a greeting from the LLM.

### Example 6: “Latest news on Sahi” and no results, not forum-only

1. Intent = search, entity = Sahi → **mention search runs**.
2. DB returns nothing, live search returns nothing (or we still have no results).
3. **forum_only** is false → we call **OpenRouter** with **use_web_search=True** (Perplexity).  
→ User may get an answer from the LLM using open-web search (e.g. generic “Sahi” news).

---

## Part 8: Summary table

| What you care about        | When it happens |
|----------------------------|------------------|
| **RSS/DB results**         | When `retrieve_mentions_db_first` returns rows (entity_mentions, article_documents, media_articles, social_posts). Then we use only DB; no live search. |
| **Live search**            | Only when DB (Step 1 and Step 2) returns **no** results. Then we run internal + Google News RSS + external. |
| **Forum/social from DB**   | Same DB step: `entity_mentions` (type=forum) and `social_posts` (Reddit/YouTube/Twitter). |
| **Forum/social-only**      | Chat filters results to forum/social types; if empty, we show “No forum or social mentions” and **never** call Perplexity. |
| **Apify**                  | Only in **scheduled** jobs (reddit_worker, youtube_worker). Not during chat or mention search. |
| **OpenRouter**             | When we need an LLM reply: greeting, or mention search with **no** results (and not forum/social-only). |
| **OpenRouter + Perplexity**| When mention search had **no** results and the request was **not** “forum/social only”. |

This is the full set of possibilities and combinations for how RSS/DB, live search, forum/social, Apify, and OpenRouter are used in your implementation.
