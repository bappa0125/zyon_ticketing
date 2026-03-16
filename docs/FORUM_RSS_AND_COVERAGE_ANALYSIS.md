# Forum RSS and coverage — analysis

**Implementation status:** TradingQnA and ValuePickr are now configured as **RSS** in `config/media_sources.yaml` (`latest.rss`). Traderji remains HTML. Thread-level forum docs flow via rss_ingestion → article_fetcher → entity_mentions (type=forum when `source_domain` is in `_FORUM_DOMAINS`).

**Questions:** (1) Is TradingQnA already on RSS? (2) Can we add more forum RSS? (3) Do we need to tweak implementation for better results? (4) SAHI/broker names may not appear in threads but the context (e.g. optimization, coverage) is valid — how do we get better coverage or handle that?

---

## 1. TradingQnA is not on RSS today

In `config/media_sources.yaml`, **TradingQnA** (and Traderji, ValuePickr, elitewealth, tradersexclusive) are configured as **HTML** sources, not RSS:

- `crawl_method: html`
- `entry_url: https://tradingqna.com/latest` (the “latest” listing page)
- `rss_feed: null`

So today we do **not** have TradingQnA RSS integrated. Forum content is ingested by **forum_ingestion_worker**, which uses **get_html_sources()** and fetches only that single `entry_url` per forum. Result: one document per forum per run (the listing page), not one per thread.

**Conclusion:** We are not using any forum RSS today. Adding forum RSS is a new step.

---

## 2. Adding more forum RSS

**Which forums can use RSS?**

- **Discourse forums** (e.g. many modern communities) expose:
  - `https://<forum>/latest.rss` — latest threads
  - Sometimes `https://<forum>/top.rss` or category feeds
- **TradingQnA** is likely Discourse (Zerodha). Try: `https://tradingqna.com/latest.rss`. Some monitoring suggests the feed may be rarely updated, but it’s worth adding; if it works, we get one RSS item per thread → one `article_documents` doc per thread after article_fetcher.
- **ValuePickr** (forum.valuepickr.com): if it’s Discourse, try `https://forum.valuepickr.com/latest.rss`.
- **Traderji** (older forum): may not have RSS; need to check. If none, keep current HTML entry_url for that one (or leave as-is until we have a thread-level crawler).
- **Reddit** is already in config as RSS (`r/IndianStreetBets`); that’s subreddit-level, not “forum” in the same sense as TradingQnA/Traderji.

**How to add forum RSS in config**

- For any forum that has an RSS feed (e.g. TradingQnA, ValuePickr if they expose `/latest.rss`):
  - Set `crawl_method: rss`
  - Set `rss_feed: https://<domain>/latest.rss` (or the real feed URL)
  - Keep `domain` and `category: forum` so:
    - The source is picked by **get_rss_sources()** (RSS pipeline).
    - `article_documents` get `source_domain` from the RSS item (taken from config `domain` in rss_ingestion).
    - **entity_mentions_worker** will set `type: forum` only if `source_domain` is in `_FORUM_DOMAINS` in `entity_mentions_worker.py` (today: tradingqna.com, traderji.com, valuepickr.com).
- For any **new** forum domain you add via RSS (e.g. another community), add that domain to `_FORUM_DOMAINS` so those docs are tagged as `type: forum`.
- You can leave `entry_url` in the YAML or remove it; for RSS sources, **get_html_sources()** is false (because `_is_rss_source()` is true), so **forum_ingestion_worker** will not fetch that URL. So no double ingest.

**Practical steps**

1. Add or confirm RSS URLs for forums that support it (e.g. TradingQnA `latest.rss`, ValuePickr if available).
2. In `media_sources.yaml`, for each such forum: `crawl_method: rss`, `rss_feed: <url>`, keep `domain` and `category: forum`.
3. Ensure every forum domain that should count as “forum” in the app is in **entity_mentions_worker** `_FORUM_DOMAINS` (and in any backfill script that uses the same set, e.g. backfill_entity_mentions_multi).

---

## 3. Do we need to tweak the implementation?

**For “RSS forum = thread-level docs”:**

- **RSS pipeline:** rss_ingestion writes to `rss_items` (one row per feed item = per thread when the feed is “latest threads”). article_fetcher then fetches each URL and writes one **article_documents** doc per URL. So with forum RSS we automatically get **one document per thread** — no code change required.
- **Forum type:** Docs get `source_domain` from the RSS source config. As long as that domain is in `_FORUM_DOMAINS`, entity_mentions_worker will set `type: forum`. **No code change** if we only add known forum domains.
- **Forum ingestion worker:** It only sees **get_html_sources()**. So any source that has `rss_feed` set will not be used by forum_ingestion_worker. We do **not** need to “exclude” RSS forums from the HTML worker; they’re already excluded.

**Optional tweaks for “better results” (not required for RSS to work):**

- **Freshness:** RSS ingestion already has a freshness window (e.g. 7 days). For forums, you can keep it or tighten (e.g. 3 days) so we don’t pull very old threads. Config-driven; no structural change.
- **Deduplication:** article_fetcher already dedupes by url_hash and content_hash. Thread URLs are stable, so we won’t duplicate threads. Fine as-is.
- **Topics:** After we have thread-level docs, **article_topics_worker** (KeyBERT) will run per doc, so each thread gets its own topics. Forum traction and narrative layers will then see real per-thread topics. No change needed for RSS itself.

**Conclusion:** No mandatory implementation tweak to “get better results” from adding forum RSS. The current RSS → article_fetcher → entity_mentions pipeline already gives thread-level coverage once we add the feeds. Optional: tune freshness and ensure all forum domains are in `_FORUM_DOMAINS`.

---

## 4. Broker name (e.g. SAHI) not in thread, but context is valid

**Current behavior**

- **entity_mentions** are created only when **entity detection** finds a client/entity **name or alias** in the text (alias + regex + NER in entity_mentions_worker; no embedding/LLM in that path).
- So if a thread is about “best app for referral” or “optimization” or “coverage” but never says “Sahi”, we get **no** entity_mention for Sahi. The thread still exists in **article_documents** (and can have topics from KeyBERT), but it is not “attributed” to Sahi.

**Ways to use “context is valid” (without inventing mentions)**

1. **More threads via RSS (no logic change)**  
   More forum threads → more chances that some threads actually mention Sahi (or competitors). So “better coverage” in the sense of more **direct** mentions. This does not help when the name truly never appears.

2. **Client “themes” or “narrative tags” (new, optional)**  
   - In clients config, add per-client **themes** or **keywords** (e.g. Sahi: referral, optimization, coverage, broker comparison).  
   - Use these **only for narrative/reporting**, not for creating entity_mentions:  
     - e.g. “Thread T has topics [referral, optimization]; Sahi’s themes include [referral, optimization] → tag T as **thematically relevant to Sahi** for the narrative layer.”  
   - Do **not** write an entity_mention with entity=Sahi for T (that would be a false positive).  
   - Use the tag only to: (a) show “threads relevant to Sahi’s themes” in a separate view or (b) feed into narrative positioning (“Sahi should care about narrative X because it’s about optimization/referral”).  
   - Implementation: either keyword overlap (thread topics vs client themes) or embedding similarity (embed thread summary, embed client description/themes, threshold). No change to entity_detection or entity_mentions schema required.

3. **Narrative graph as the place for “context”**  
   - Narratives are built from topics/clusters (e.g. “optimization”, “referral programs”, “broker coverage”).  
   - Clients are “positioned” in narratives by: (a) **direct mentions** (current entity_mentions) and (b) optionally **thematic relevance** (client themes overlap with narrative).  
   - So the CXO report can say: “Narrative ‘optimization/referral’ is forming; Sahi is thematically aligned (and appears in N threads by name). Consider positioning content there.”  
   - This keeps entity_mentions strict (name-based) and pushes “context valid” into the narrative/positioning layer.

**Recommendation**

- **Short term:** Add forum RSS to get more thread-level content and more real mentions; no change to entity logic. Accept that “context valid but name not present” will not create entity_mentions.
- **Medium term:** If you want “optimization / coverage” type threads to influence Sahi’s positioning: add **client themes** (config or embedding) and use them only for **narrative/reporting** (thematic relevance, not new entity_mentions). That gives better “coverage” of relevant discussions without polluting mention counts.

---

## 5. Summary

| Question | Answer |
|----------|--------|
| Is TradingQnA already on RSS? | **No.** It’s currently HTML with a single `entry_url` (listing page). |
| Can we add more forum RSS? | **Yes.** Add `rss_feed` (e.g. `https://tradingqna.com/latest.rss` for Discourse) and `crawl_method: rss`; keep `domain` and `category: forum`; ensure domain is in `_FORUM_DOMAINS`. Same for any other forum that exposes RSS. |
| Do we need to tweak implementation? | **No** for basic RSS→thread-level docs. Pipeline already gives one doc per thread. Optional: tune freshness; ensure all forum domains are in `_FORUM_DOMAINS`. |
| SAHI/broker not in thread but context valid? | **Today:** no entity_mention (by design). **Better coverage:** (1) More threads via RSS → more real mentions. (2) Optional: add client “themes” and use them only for narrative/thematic relevance (no new entity_mentions). Narrative graph can then position clients by both mentions and thematic fit. |

Adding forum RSS is config-only (and `_FORUM_DOMAINS` for new domains). Handling “context valid but no name” is an optional enhancement in the narrative/positioning layer, not a requirement for RSS to work well.
