# CXO report & narrative graph — design and brutal assessment

**Objective (your words):**  
The CXO report should answer:

1. **“How is our company being talked about across the internet compared to competitors?”**  
2. **“What narrative is forming and how should we position ourselves?”**

The system should be driven by a **narrative graph** fed by RSS, news, live search, social, and forums. Narratives can **start** in forum/social → get amplified → hit news, or the reverse, or start in between. Either way, the goal is the same: compare company vs competitors and guide positioning.

**Constraints:** Performant, respect LLM limits, forum guidelines, don’t get blocked (prefer RSS or official API; crawler only with care).

---

## 1. Does this make sense? (Brutal)

**Yes.** The two questions are the right ones for a CXO report. A **narrative graph** that (a) unifies content from all channels (RSS, news, live search, social, forums) and (b) captures **flow** (where a narrative started, how it spread) is the right mental model. It supports both “how we’re talked about vs competitors” and “what narrative is forming and how to position.”

**Where we are today:**

| What you want | What we have today |
|---------------|---------------------|
| One narrative graph from RSS, news, live search, social, forums | Narrative shift = YouTube + Reddit + `article_documents` (news). No live search. Forum = one page per forum (listing page), not thread-level. |
| “Where did the narrative start / how did it spread?” (flow) | We cluster by embedding and store platform_distribution per narrative, but we **do not** store **per-item dates** or **first-seen-by-platform**. So we cannot say “this narrative first appeared in forum, then reddit, then news.” |
| CXO report answers the two questions directly | Report has sections (reputation, coverage, narrative themes, positioning mix, etc.) but no **single narrative-graph-backed** section that explicitly answers “how we’re talked about vs competitors” and “what narrative is forming, how to position.” |

So: the **objective is right**; the **current implementation is not yet a narrative graph with flow and full feeds**. Below is a concrete design that gets you there without over‑engineering and respects LLM limits and forum safety.

---

## 2. Narrative graph — what it is and what we need

**Narrative graph (for this product):**

- **Nodes:**  
  - **Narratives** = themes/topics we can name (e.g. “Broker withdrawal delays”, “Sahi vs Zerodha for beginners”, “Options tax confusion”).  
  - Optionally: **content nodes** (article, thread, post) as evidence.
- **Edges / structure:**  
  - **Narrative → source:** this narrative **appeared in** source X at time T (forum thread, reddit post, article, etc.).  
  - **Flow:** for each narrative we can compute **first_seen** (earliest T) and **by channel** (forum, social, news). So we can say: “Narrative N started in forum on D1, appeared in Reddit on D2, hit news on D3” (or the reverse).

We do **not** need a general-purpose graph DB for v1. We need:

1. A **unified notion of “narrative”** (same theme across channels).  
2. **Per-occurrence** records: (narrative_id, channel, source_type, source_id, url, date).  
3. **Flow** = sort occurrences by date → “first in forum, then social, then news” (or whatever order).

So: **narrative graph = narratives + occurrences with channel + date**; flow is derived by sorting. Storage can be MongoDB (narratives collection + narrative_occurrences collection). Add a real graph DB later only if we need path queries or complex traversal.

---

## 3. Feeds that must feed the graph

| Feed | Today | Should feed graph? | Notes |
|------|--------|--------------------|--------|
| **RSS** | Yes → `rss_items` → `article_documents` | Yes | Already in narrative_shift as “news”. Keep; ensure articles have date + source. |
| **News (article_documents)** | Yes | Yes | Same as RSS output; include source_domain, published_at. |
| **Live search** | Yes → `media_articles` | Yes | Today not in narrative_shift. Add: treat as another channel (e.g. “live_search”) with date. |
| **Social (Reddit, YouTube)** | Yes → `social_posts`; narrative_shift also pulls API | Yes | Already in. Ensure we have timestamp per item for flow. |
| **Forums** | One page per forum → one doc | Yes, but **thread-level** | Current forum signal is useless for narrative. Need **thread-level** content (RSS-first; crawler with strict limits if no RSS). |

So: **RSS, news, live search, social, forums** all feed the graph. Forum is the only feed that requires a **change in ingestion** (thread-level); the rest are mostly wiring + a unified “narrative + occurrences” model.

---

## 4. Forum: RSS first, crawler fallback, don’t get blocked

**Principle:** Prefer **RSS or official API**. Use crawler only when necessary, with **strict rate limits and politeness** so we don’t get blocked.

- **RSS (if available):**  
  - Many forums expose RSS for “latest threads” or per-category.  
  - Use RSS to get **thread URLs** (and titles, sometimes dates).  
  - Store each thread as a **separate content unit** (e.g. `forum_threads` or `article_documents` with `source_type=forum`, `thread_id`).  
  - If the feed only has titles/links, we can still do **topic/narrative assignment** from titles; optionally **fetch thread body** for a small subset (e.g. top N by engagement or recency) with a **low rate** (e.g. 1 request per minute per domain).  
- **No RSS / API:**  
  - **Crawler path:** listing page → parse thread links → fetch **only a few threads per run** (e.g. 5–10 per forum), with **delay between requests** (e.g. 60–120 s). Use **view/reply count** on the listing (if available) to prioritize which threads to fetch.  
  - Store one doc per thread; run entity detection + topic extraction (KeyBERT) on thread text.  
- **Activity/views:** If the listing page exposes reply count or views, use them to (a) prioritize which threads to fetch and (b) attach to the thread doc for “traction” and narrative importance.

**Don’t get blocked:**  
- Respect `robots.txt` and cache aggressively.  
- Prefer RSS so we don’t hit thread pages at all for discovery.  
- If we must crawl, cap threads per run and space out requests.  
- No parallel burst to the same domain.

---

## 5. Unified narrative pipeline (all feeds → narrative graph)

**Idea:** One pipeline that pulls from **all** channels (RSS/news, live search, social, forums), normalizes to **content items** (title + text/snippet + url + channel + date), then builds **narratives** and **occurrences** so we can compute flow.

**Steps (high level):**

1. **Ingest (per channel):**  
   - RSS/news: from `article_documents` (with date, source_domain).  
   - Live search: from `media_articles` (with timestamp).  
   - Social: from `social_posts` or existing API pull (Reddit, YouTube) with timestamp.  
   - Forums: from **thread-level** docs (RSS-derived or crawler), with date.

2. **Normalize to “content items”:**  
   - Each item = { text (title + snippet/body), url, channel (rss | news | live_search | reddit | youtube | forum), source_id, date }.  
   - Cap text length per item (e.g. 1–2k chars) to keep embedding cost and LLM context bounded.

3. **Narrative assignment:**  
   - **Option A (recommended for v1):** Embed all items; cluster (e.g. KMeans or HDBSCAN). Each cluster = one narrative. Label with **one LLM call per cluster** (topic + one-line summary). So LLM use = number of clusters (e.g. 5–10 per run), not per item.  
   - **Option B:** Predefined taxonomy of narratives; assign items to narrative by embedding similarity to taxonomy labels (no LLM per item; optional LLM to refine taxonomy).  
   - Store: **narratives** (id, label, summary, cluster_embedding or centroid); **narrative_occurrences** (narrative_id, channel, source_id, url, date, optional entity/client).

4. **Flow:**  
   - For each narrative: query occurrences, sort by date.  
   - First occurrence by channel = “where it started” (or “earliest seen in channel X”).  
   - Simple rule: “First seen in forum/social → then news” = narrative started in community and hit media; “First seen in news → then forum” = the other way.  
   - Store **flow summary** per narrative (e.g. first_channel, first_date, channel_sequence) for the report.

5. **Positioning (“how we’re talked about vs competitors” / “how to position”):**  
   - For each narrative, we already have (or can add) **entity mentions** (which clients/competitors appear in which items).  
   - So: “In narrative N, clients A,B appear; competitor C appears; client D absent.”  
   - CXO section: (1) **Narrative graph summary:** key narratives + flow (started in forum → news, etc.). (2) **Per client:** how they’re talked about vs competitors (which narratives they’re in, where they’re absent). (3) **Positioning:** one short LLM call per client (or one call for all) that summarizes “what narrative is forming and how to position” using the graph + entity presence. That keeps LLM to **one or a few calls per report**, not per item.

**Performance:**

- Embedding: batch all items (e.g. 500–2k per run); one batch embed.  
- Clustering: in-memory (e.g. sklearn KMeans).  
- LLM: only for cluster labels + final positioning summary (bounded).  
- Store occurrences in MongoDB; flow = sort by date (indexed). No graph DB required for v1.

**LLM limits:**

- No LLM per article/thread/post.  
- LLM only for: (a) labeling clusters (e.g. 5–10 calls per run), (b) optional “substantive?” filter on forum threads (if used, batch threads and one call per batch), (c) CXO positioning summary (1 call per client or 1 for all).  
- Total per report run: on the order of 10–20 LLM calls, not hundreds.

---

## 6. Where to store: vector DB vs graph DB

- **Vector DB (we have Qdrant):**  
  - Use for: **similarity search** (e.g. “find items similar to this narrative”), **dedup**, or **clustering input**.  
  - We already use embeddings for narrative_shift clustering; we can store narrative centroids or item embeddings in Qdrant and use them for “which narrative does this new item belong to?” without re-clustering every time.  
  - Good for **scalability** and **incremental** assignment of new items to existing narratives.

- **Graph DB (e.g. Neo4j):**  
  - Natural for: Narrative —[appeared_in]→ Content (channel, date); Narrative —[mentions]→ Entity.  
  - Not required for **v1** if we can answer “where did narrative start / how did it spread?” from **MongoDB**: narratives + narrative_occurrences (narrative_id, channel, source_id, url, date). Flow = sort by date.  
  - Introduce a graph DB when we need **path queries** (e.g. “all paths from forum to news”) or **complex traversal**. Until then, MongoDB is simpler and we already have it.

**Recommendation:**  
- **MongoDB** for narratives + narrative_occurrences + flow (computed).  
- **Vector DB (Qdrant)** for embeddings and optional “assign new item to narrative” by similarity.  
- **Graph DB:** defer until we have a concrete need for graph-native queries.

---

## 7. CXO report: two questions explicitly

**Section: “How we’re talked about vs competitors”**

- Input: narrative graph + entity_mentions (or entity tags on occurrences).  
- Output: For each client (and key competitors): which narratives they appear in, share of voice per narrative (if we have counts), and where they’re **absent** (narratives with no mention).  
- Can be mostly **non-LLM** (aggregation + tables). Optional one-sentence summary per client from LLM.

**Section: “What narrative is forming and how to position”**

- Input: narrative graph (themes + flow) + per-client presence.  
- Output: (1) **Flow summary:** e.g. “Key narratives this week: X (started in forum, then news), Y (started in news), Z (started in social).” (2) **Positioning:** “Given narratives X, Y, Z and your presence in X and absence in Z, consider …”  
- **One LLM call** (or one per client) that takes as input: list of narratives with flow, client’s presence/absence, and outputs 2–4 short positioning bullets. No LLM on raw items.

This makes the CXO report **directly answer** the two questions, backed by the narrative graph.

---

## 8. Implementation order (pragmatic)

| Phase | What | Why |
|-------|------|-----|
| 1 | **Forum thread-level ingestion** | Without it, forum adds no real signal. Prefer RSS for thread discovery; crawler with strict rate limits only if needed. Store one doc per thread; run entity_mentions + KeyBERT per thread. |
| 2 | **Unified content items** | Normalize RSS/news, live search, social, forum threads to one “content item” shape (text, url, channel, date). Reuse existing collections; add a view or a small ETL that produces items for the narrative pipeline. |
| 3 | **Narrative + occurrences model** | One batch job: from items → embed → cluster → label clusters (LLM per cluster). Store narratives and narrative_occurrences (narrative_id, channel, source_id, url, date). Add entity/client to occurrences where we have mentions. |
| 4 | **Flow** | For each narrative, sort occurrences by date; compute first_channel, first_date, channel_sequence. Store or compute on read. |
| 5 | **CXO sections** | (a) “How we’re talked about vs competitors” from occurrences + entities. (b) “What narrative is forming and how to position” from flow + one LLM positioning summary. |
| 6 | **Vector DB (optional)** | Use Qdrant to store narrative centroids and optionally assign new items to narratives by similarity to avoid re-clustering every run. |

---

## 9. Risks and mitigations

| Risk | Mitigation |
|------|-------------|
| Forum blocking | RSS first; crawler only with low rate (e.g. 5–10 threads per forum per run, 1 req/min). Respect robots.txt. |
| LLM cost/latency | No LLM per item. LLM only for cluster labels (5–10 calls) + positioning summary (1–few calls). |
| Noise (forums, social) | Filter: min engagement or “substantive?” batch check; or take only top-N by engagement for narrative assignment. |
| Flow wrong direction | Flow is “first occurrence by date”; we don’t infer causality, only order. Label as “first seen in X, then Y.” |
| Scale (too many items) | Cap items per channel per run (e.g. 200 news, 100 social, 50 forum threads). Sample if needed. |

---

## 10. Summary

- **Objective:** CXO report answers “how we’re talked about vs competitors?” and “what narrative is forming, how to position?” — **yes, it makes sense.**  
- **Narrative graph:** Same themes across RSS, news, live search, social, forums + **occurrences with channel and date** → flow = “where it started, how it spread.” No need for a graph DB in v1; MongoDB + (optionally) Qdrant is enough.  
- **Forums:** RSS-first for thread discovery; thread-level content (and optional crawler with strict limits). Use view/activity to prioritize; don’t get blocked.  
- **Performance / LLM:** Embeddings + clustering; LLM only for cluster labels and positioning summary. Bounded and performant.  
- **Implementation:** Thread-level forum → unified items → narratives + occurrences → flow → CXO sections that explicitly answer the two questions.

This design aligns the report with your objective, uses a single narrative graph fed by all channels, captures flow without over-engineering, and respects forum guidelines and LLM limits.
