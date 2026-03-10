# Recommendation: Store Live-Search in MongoDB + UI Ideas & Edge Cases

**No implementation in this doc — suggestions only.**

---

## 1. Do I recommend implementing it?

**Yes, with conditions.**

- **Worth doing because:**
  - Future queries for the same entity get DB hits instead of repeating Google News RSS + external search → faster and more stable.
  - Aligns with “monitored mentions”: once we’ve validated a live result, treating it as something we “monitor” is consistent.
  - Reuses existing pipeline (article_documents, dedup, entity_mentions_worker); no new collections or schema required.

- **Conditions:**
  - **Store in the background** (e.g. after returning the response) so the user’s answer is not delayed by full-page fetches and writes.
  - **Cap per run** (e.g. 5–10 articles per `search_mentions` call) to avoid bursts and abuse.
  - **Only store when** the detected entity matches the search entity (so we don’t persist “Sahi” healthcare when the user asked for “Sahi” trading).
  - **Treat storage as best-effort:** if MongoDB or fetch fails, skip that article and still return the live results; never fail the request because of storage.

With those in place, the feature is low-risk and improves repeat queries without changing current behavior for the first-time user.

---

## 2. UI suggestions

Today the UI shows something like:

- **Source:** “Monitored mentions from your configured news, blogs, forums, and social sources (not full open‑web search) for **Sahi**.”
- Then the list and a footer with “You can also ask: …”.

No distinction is made between “from DB” vs “from live search.” Storing live results doesn’t require any UI change for correctness.

Below are **optional** UI improvements that would make behavior clearer and handle edge cases better.

### 2.1 Keep current copy (minimal change)

- No change: same header/footer. After storage, the next query just gets more results from “monitored sources” with no extra message.
- **Pros:** Simple, no new strings. **Cons:** User doesn’t know we’re now “remembering” some results.

### 2.2 Light transparency when we stored (recommended)

- When we **did** store at least one article from this response, add one short line in the **footer** (after the list, before “You can also ask”):
  - e.g. *“We’ve saved these mentions for future searches.”*
- Only show when storage actually happened (e.g. backend sends a flag or count).
- **Pros:** Sets expectation that repeat questions can be faster; no per-result clutter. **Cons:** Slightly longer footer in those cases.

### 2.3 “Last updated” / freshness (for edge cases)

- If you later want to address “I asked again and got the same results”:
  - Option A: In the **header**, add a single line like *“Results as of &lt;date/time&gt;”* or *“Index updated at &lt;time&gt;”* (from the oldest/newest result or a single “as of” timestamp).
  - Option B: Small “Refresh” or “Search again” control that forces a new live search (and optionally skips DB-first for that request).
- **Pros:** Users understand why they see the same list twice; “Refresh” gives control. **Cons:** More UI and possibly a new API/flag.

### 2.4 Per-result “New” badge (optional, later)

- If you add an optional `origin: "live_search"` (or `first_seen_at`) and pass it to the UI, you could show a small “New” or “Just added” badge on results that were just stored from live search.
- **Pros:** Power users see what’s new. **Cons:** Schema/API change; might be noise for most users. **Recommendation:** Skip for v1; consider only if you get feedback that “what’s new” matters.

### Summary of UI recommendation

- **Minimum:** No UI change; feature still valuable.
- **Recommended:** Add a single footer line when we stored: *“We’ve saved these mentions for future searches.”*
- **Later:** Optional “Results as of …” and/or “Refresh” if users complain about staleness.

---

## 3. Edge cases

### 3.1 Stale / cached results

- **Case:** User asks “Where was Sahi mentioned?” → we return live results and store them. Five minutes later they ask again → we serve from DB and show the same set. The article might have been updated or the publisher might have changed the page.
- **Mitigation:** Accept that DB is a cache. Optional: show “Results as of &lt;date&gt;” or “Indexed at &lt;time&gt;” so it’s clear results aren’t “live right now.” Later you could add “refresh” or “prefer live” for that request.

### 3.2 Wrong entity stored (disambiguation)

- **Case:** Query is “Sahi” (trading). Live result is about “SAHI” (healthcare). Validation might pass if the snippet/title is ambiguous; we store with `entity: "Sahi"` and later surface it for “Sahi” trading.
- **Mitigation:** Only store when `detect_entity(title + article_text)` returns the **same** canonical entity as the search (e.g. resolve both to canonical “Sahi” and require match). Rely on `validate_mention_context` (context_keywords, ignore_patterns) as today. If context rejects, don’t store. This keeps stored articles aligned with the entity the user asked for.

### 3.3 Full fetch fails after validation

- **Case:** We validated with 1500 chars (e.g. snippet/first chunk). For storage we do a full trafilatura fetch; the site is slow, blocks the user-agent, or returns 403/500.
- **Mitigation:** Skip store for that URL; don’t retry in the same request. Log for debugging. User still gets the live result (we already have title/link/snippet). No need to fail or show an error.

### 3.4 Duplicate key / race

- **Case:** Two concurrent requests for “Sahi” both run live search, both get the same article, both try to insert. One wins; the other gets E11000 (duplicate key).
- **Mitigation:** Before insert, check `url_hash` (and optionally `content_hash`). On insert, catch duplicate key and treat as “already stored.” No error to the user; both responses succeed.

### 3.5 Cap and ordering

- **Case:** Live search returns 20 results; we cap storage at 10. We store the “top 10” by current ranking. Next time, DB returns those 10 and we might not run live search, so we never store the other 10.
- **Mitigation:** Accept this. We’re optimizing for “good coverage” not “store every possible result.” If you want to spread storage across runs, you could later add “store 2–3 new ones per run until we have N” — not necessary for v1.

### 3.6 published_at missing or weird

- **Case:** Live source gives no date or a bad format (e.g. “2 hours ago” or wrong timezone).
- **Mitigation:** Reuse the same pattern as forum ingestion: set `published_at = fetched_at` when missing or unparseable. DB and entity_mentions_worker already support that. No UI change required; we can show “—” or “Recent” if you don’t have a date.

### 3.7 User expects “new” results every time

- **Case:** User asks “latest mentions of Sahi” twice in a row and sees the same list (second time from DB).
- **Mitigation:** Optional “Results as of &lt;date&gt;” and/or “Refresh” so they understand it’s cached and can force a fresh search if they want. No change to storage logic.

### 3.8 Storage fails (MongoDB down, timeout)

- **Case:** Insert fails due to DB error or timeout.
- **Mitigation:** Catch the exception; do not fail the HTTP response. User still gets the live results we’re about to return. Optionally log and/or increment a “storage_failed” metric. Retry is out of scope for v1 (background job could retry later if you add a queue).

### 3.9 Entity detection mismatch at store time

- **Case:** We run `detect_entity` at store time and get “Zerodha” but the user asked for “Sahi” (e.g. comparison article). We might still want to store it for “Sahi” if the snippet mentioned Sahi and validation passed.
- **Recommendation:** Only store when the **detected** entity matches the **search** entity (after canonical resolution). That way we don’t store “Zerodha” articles when the user asked “Sahi,” even if the article mentions both. Simpler and avoids polluting the entity’s index.

### 3.10 Forum/social-only query

- **Case:** User asks “Show only forum or social mentions of Sahi.” We run live search (which is mostly articles); we filter to forum/social and might get 0. We don’t store in that path (we have nothing to show, and storing articles when the user asked for forum/social only would be wrong).
- **Mitigation:** Only consider storage when we’re **not** in “forum/social only” mode, or only store results that are actually forum/social (if any). Easiest: skip storage when `forum_only` is true.

---

## 4. Summary

| Topic | Suggestion |
|-------|------------|
| **Implement?** | **Yes**, with background store, cap per run, store only when detected entity = search entity, and best-effort (no request failure on storage failure). |
| **UI (minimal)** | No change; current “Monitored mentions from…” is enough. |
| **UI (recommended)** | When we stored ≥1 article, add one footer line: *“We’ve saved these mentions for future searches.”* |
| **UI (later)** | Optional “Results as of &lt;date&gt;” and/or “Refresh” to handle staleness expectations. |
| **Edge cases** | Handle: stale cache, wrong entity (store only on entity match), full fetch failure (skip store), duplicate key (treat as skip), missing date (use fetched_at), forum/social-only (skip store), and never fail the request due to storage. |

No code changes are described in this doc; it is recommendation and design only.
