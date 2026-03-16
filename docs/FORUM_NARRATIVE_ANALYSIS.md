# Forum topics & narratives for narrative graph — brutal analysis

**Context:** TradingQnA, Traderji, ValuePickr (and similar) have a lot of discussion about the Indian market. You want to use this for **narrative graph** and **position clients on that graph**. This doc analyzes the best way to get topics and narratives from these forums **in the context of our application** — no sugar-coating.

---

## 1. What we actually ingest today (forums)

| What you see on TradingQnA | What we store |
|----------------------------|---------------|
| Many threads, lots of discussion, petty or substantive | **One URL per forum** — e.g. `https://tradingqna.com/latest` |
| Per-thread: title, OP, replies, nuance | **One document per forum per run** — the HTML of the “latest” **listing page** |
| Rich, thread-level topics and narratives | **One blob of text** (trafilatura extract of that listing page) → one set of KeyBERT topics per forum per run |

So: we do **not** ingest individual threads. We ingest the **listing page** of each forum. The “lot of petty discussion” you see on the site is **not** in our system. We have at most one “article” per forum per run (and we dedupe by url_hash, so we don’t even get a new doc until that listing page URL/content changes). Entity mentions (type=forum) come from that single page; forum traction joins to that single doc’s `topics`. Our “forum” signal is therefore **extremely coarse** and **not** representative of thread-level discussion.

**Conclusion:** With the current design we **cannot** get real topics and narratives from TradingQnA-style forums. We get at best a weak proxy from one page per forum.

---

## 2. What “narrative graph” means in our app

In this codebase:

- **Narrative shift:** Clusters of text (YouTube + Reddit + `article_documents`) → themes + pain points + messaging. Stored in `narrative_shift_runs`. **Not** a graph DB; it’s **clusters + labels**.
- **Narrative positioning:** Per-client view built from narrative_intelligence_daily, narrative_shift, Reddit themes, YouTube summaries, **entity_mentions**, **article_documents**, social_posts. One LLM call per client → narratives, positioning, threats, opportunities. Forum enters only as:
  - **entity_mentions** where type=forum (when that **one** forum page mentions the client), and
  - **article_documents** (that same one page) as “article_snippets”.

So the “narrative graph” we use for positioning is **theme clusters + per-client evidence**, not a literal graph. To “position client on narrative graph” here means: **which themes/narratives the client appears in, and where they’re absent**. Forums today contribute almost nothing useful because we only have one page per forum.

---

## 3. What we’d need to get real topics and narratives from forums

To use TradingQnA (and similar) for a narrative graph and client positioning, we need **thread-level** content, then topic and narrative extraction on that.

### 3.1 Thread-level ingestion (non-negotiable)

- **Today:** One `entry_url` per forum → one fetched page → one `article_documents` doc per forum per run.
- **Needed:**  
  - **Step 1:** Fetch the listing page(s) (e.g. `tradingqna.com/latest`).  
  - **Step 2:** Parse the DOM/HTML to get **thread URLs** (e.g. `/t/12345`, `/topic/xyz`).  
  - **Step 3:** For each thread URL (with caps and rate limits), fetch the thread page, extract **title + OP + first N replies** (or full thread), store **one document per thread** (e.g. in `article_documents` with `source_domain=tradingqna.com` and a `thread_id` or similar, or a dedicated `forum_threads` collection).

So we need a **forum-aware crawler** that knows how to:

- Find thread links on listing pages (TradingQnA, Traderji, ValuePickr each have different structure).
- Fetch thread pages and extract post content (again, DOM/structure is site-specific).

Without this, any “topics and narratives” we derive are from the listing page only — not from the discussions.

### 3.2 Topics from threads

- Run **KeyBERT** (or similar) on **each thread** (e.g. title + first post, or title + first 3 posts). Store `topics` on the thread doc.
- **Forum traction:** Aggregate over **threads** (e.g. entity_mentions joined to thread docs by url). Then “topics by traction” reflect real discussion themes (e.g. “withdrawal delays”, “Sahi vs Zerodha”, “options tax”) instead of one coarse topic set per forum.

Our current `forum_traction_service` logic (join entity_mentions → article_documents → unwind topics → group by topic) is fine **once** we have many thread-level docs instead of one doc per forum.

### 3.3 Narratives from forums (for the “narrative graph”)

Two ways to align with our app:

- **A) Reuse narrative_shift-style pipeline for forums**  
  - Take thread-level docs (title + summary/text).  
  - Embed + cluster (e.g. KMeans) → “forum narratives” (themes + short summary).  
  - Store in something like `forum_narrative_runs` (or extend `narrative_shift_runs` with `source: forum`).  
  - Feed these into **narrative_positioning** as an extra input (e.g. “forum_themes” / “forum_narratives”).  
  - Client positioning: which forum narratives mention the client (from entity_mentions on threads) vs where they’re absent.

- **B) Taxonomy-based**  
  - Define a fixed set of narratives (e.g. “Broker comparison”, “Tax/regulation”, “Platform reliability”, “F&O / options”).  
  - Classify each thread (LLM or embedding similarity to narrative labels).  
  - Roll up: “Narrative X has N threads; client appears in M.”  
  - Same end: client on narrative graph = presence/absence per narrative.

In both cases, the **unit of analysis must be the thread** (or post), not the listing page.

---

## 4. Brutal truths (in context of our app)

1. **One URL per forum is useless for narrative graph.** We don’t have “a lot of petty discussion” in the system; we have one blob per forum. No amount of better KeyBERT or LLM will fix that. **Fix:** thread-level discovery + fetch.

2. **Forums are noisy.** Even with threads, many are chitchat, duplicates, or off-topic. For “narrative” and “positioning” we should **filter**: e.g. minimum replies, or LLM “is this a substantive discussion about brokers/products/market?” so we don’t position clients on noise.

3. **Our “narrative graph” is clusters + evidence, not a graph DB.** Positioning = “client in narrative A, B; absent in C.” Forums can feed that **if** we have narrative labels (or clusters) at thread level and entity_mentions at thread level.

4. **Forum structure is site-specific.** TradingQnA ≠ Traderji ≠ ValuePickr. We need either (a) one adapter per forum (parse listing → get thread links → parse thread page), or (b) a generic “list of links → fetch each → extract” with config per domain. No single magic crawler for “all forums.”

5. **Legal / ToS.** Scraping many threads can violate forum ToS. Prefer RSS if available, or official API. If we only have scraping, cap rate and volume and consider legal review.

6. **Narrative shift today does not separate “forum” from “news”.** It pulls `article_documents` (including our current one-doc-per-forum) into a single pool with YouTube and Reddit. So forum is a tiny, noisy slice. Once we have thread-level forum docs, we could (a) run a **forum-only** narrative pipeline (embed + cluster threads → forum narratives), and (b) feed that into narrative_positioning as “forum_narratives”, while keeping narrative_shift as YouTube + Reddit + news. That gives a clearer “forum narrative graph” and avoids diluting Reddit/YouTube with forum noise.

---

## 5. Best path (recommendation in our app context)

| Step | What | Why |
|------|------|-----|
| 1 | **Thread-level forum ingestion** | Without it, we don’t have real discussion content. Implement listing-page parsing → thread URL discovery → fetch thread page → store one doc per thread (same or dedicated collection). Start with TradingQnA (one adapter), then replicate pattern for Traderji, ValuePickr. |
| 2 | **Topic extraction per thread** | KeyBERT on title + first post (or first N posts). Store `topics` on thread doc. Keeps existing forum_traction aggregation logic but with real traction. |
| 3 | **Entity mentions at thread level** | Run entity_mentions_worker (or equivalent) on thread docs so `entity_mentions` has one row per (entity, thread_url), type=forum. Then positioning and “forum traction” are per-thread. |
| 4 | **Forum narratives (optional but recommended)** | Run a **forum-only** clustering pipeline (embed threads → KMeans → narrative labels). Store as forum_narrative_runs or similar. Feed into narrative_positioning as “forum_narratives” so we can say “client appears in forum narratives A, B; absent in C.” |
| 5 | **Filter noise** | Minimum replies or LLM-based “substantive discussion” filter so we don’t build narratives from petty/chitchat threads. |

Then:

- **Topics:** From thread-level KeyBERT + aggregation (existing forum_traction + topics API).
- **Narratives:** From forum-only clustering (or taxonomy) → “forum narrative graph” (themes/nodes); client positioning = which of these narratives the client appears in (from entity_mentions on threads).

**Bottom line:** We don’t get real topics and narratives for TradingQnA and similar forums without **thread-level ingestion**. The best way, in our app’s context, is: thread-level crawl → thread-level topics + entity_mentions → optional forum-specific narrative clustering → feed into narrative positioning so clients are positioned on that forum narrative graph.
