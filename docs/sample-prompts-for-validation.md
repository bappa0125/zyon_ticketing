# Sample Prompts for Validating Live-Search Storage

Use these prompts in the chat UI to validate that:

1. **Mention search** returns results (from DB or live search).
2. **Live-search storage** runs when results come from live search (no DB hits); repeat the same query later to see if results are then served from DB.
3. **Forum/social-only** still shows "No forum or social mentions" when none exist and does not trigger storage.
4. **URLs** are real publisher links (no `news.google.com` in the displayed URL).

---

## 1. First-time mention (triggers live search + storage when DB is empty)

Use when the entity has little or no data in MongoDB (e.g. a niche entity or right after a clean DB).

| Prompt | What to check |
|--------|----------------|
| **Where was Sahi mentioned?** | You get a list of mentions (news/articles). Links should be real publisher URLs, not Google News redirects. |
| **Latest news on Zerodha** | Same: list with title, source, date, summary, URL. |
| **Show me recent mentions of Groww** | Same. |

**Validation:**  
- Response shows "Source: Monitored mentions from your configured news, blogs, forums, and social sources…".  
- At least one result has a clickable URL that goes to the real site (e.g. inc42.com, economictimes.com), not `news.google.com`.  
- If this was a **live search** (no DB results), the backend will store up to 10 validated articles in the background for next time.

---

## 2. Repeat query (DB-first after storage)

Use **after** running one of the prompts above for an entity that had no DB results before (so live search ran and storage may have happened).

| Prompt | What to check |
|--------|----------------|
| **Where was Sahi mentioned?** (again, after 1–2 min) | If storage ran, this request may be served from MongoDB (faster, same or similar results). |
| **Latest news on Sahi** | Same idea. |

**Validation:**  
- Response is returned without a long delay (no full live search if DB had enough results).  
- Results are still relevant and URLs are still real publisher links.  
- Backend logs (optional): look for `mention_search_db_first_used` to confirm DB was used.

---

## 3. Forum/social-only (no storage, clear message)

| Prompt | What to check |
|--------|----------------|
| **Show only forum or social mentions of Sahi** | You see either (a) a list of forum/social-only mentions, or (b) the message: "No forum or social mentions found for **Sahi** in our monitored sources." |
| **Show only forum or social mentions of Zerodha** | Same. |

**Validation:**  
- You never get a generic open-web answer (e.g. SAHI healthcare) when you asked for forum/social only.  
- When there are no forum/social results, the reply clearly says so and does not call Perplexity.  
- Storage is **not** run for forum/social-only requests (by design).

---

## 4. Mixed / general mention queries

| Prompt | What to check |
|--------|----------------|
| **Where was Sahi mentioned last week?** | List of mentions (from DB or live). |
| **Compare mentions of Sahi vs Zerodha** | Behavior depends on your implementation; at least no errors. |
| **Give me top articles about Upstox** | List of articles with title, source, date, URL. |

**Validation:**  
- No 500 or stack traces.  
- Links are usable and point to real articles.

---

## 5. Edge cases (optional)

| Prompt | What to check |
|--------|----------------|
| **Where was [unknown entity] mentioned?** | Either "No mentions found" or a short message; no crash. |
| **Show only forum or social mentions of [entity]** when you know there are no forum/social sources | You get "No forum or social mentions found for **[entity]**…". |

---

## Quick checklist

- [ ] **Mention query** (e.g. "Where was Sahi mentioned?") returns a list with real publisher URLs.  
- [ ] **Repeat same query** after a short wait: response is fast and still correct (DB-first when storage ran).  
- [ ] **Forum/social-only** either shows forum/social results or the explicit "No forum or social mentions" message.  
- [ ] No **Google News redirect URLs** in the displayed links.  
- [ ] No **off-topic** answers (e.g. healthcare SAHI when you asked for Sahi trading) when using forum/social-only.

---

## Backend logs (optional)

If you have access to backend logs, you can confirm:

- **Live search ran:** No `mention_search_db_first_used` before the first query for an entity with no DB data.  
- **Storage ran:** `store_live_result_inserted` or `store_live_results_done` after a live-search response.  
- **DB-first on repeat:** `mention_search_db_first_used` on the second query for the same entity.
