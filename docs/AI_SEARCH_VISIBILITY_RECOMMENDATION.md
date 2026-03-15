# AI Search Visibility Monitoring — Recommendation (No Implementation Yet)

This document is a **brutal, architecture-first recommendation** for replacing the current "AI Search Narrative" feature with **AI Search Visibility Monitoring**, without breaking existing pipelines, while staying performant and under LLM/API limits.

---

## 1. Reality Check: Why Not Build It All at Once

| Requirement | Brutal truth |
|-------------|--------------|
| **100 prompts (5 groups × 20)** | Manageable in config. Running all weekly is not, on free/low tier. |
| **3 engines (Perplexity, ChatGPT, Gemini)** | 100 × 3 = **300 API calls per run**. Free tiers are usually tens of calls/day, not hundreds/week in one burst. |
| **Automatic prompt discovery** | Needs external data (Google PAA, trending APIs). Scraping = ToS/brittle; APIs = cost. "Learning" which prompts matter = more LLM or scoring logic = more cost/complexity. |
| **Recommendations per gap** | If you use 1 LLM call per "competitor visible, us not" → dozens of extra calls per week. Unsustainable on free tier. |
| **Weekly execution** | Good. Caching by (query, engine, week) is essential so you don’t re-run the same prompt in the same week. |

**Conclusion:** Implement in **phases**. Phase 1 = one engine, curated prompts, weekly cache, entity detection on answers, rule-based recommendations, weekly snapshot + dashboard. Add engines, prompt discovery, and smarter recommendations in later phases when you have quota and budget.

---

## 2. Architectural Principles (Non-Negotiable)

- **Do not modify** existing ingestion (RSS, forums, social) or entity-detection pipelines. **Call** entity detection from the new visibility pipeline as a library.
- **New capability only:** New config, new collections, new scheduler job(s), new API routes, new UI. Replace the current "AI Search Narrative" **page** with the new dashboard; keep or migrate the single `ai_search_answers`-style storage into the new model.
- **Reuse:** Entity detection (company + competitors), client/competitor config from `clients.yaml`, existing auth and API patterns.
- **Accumulate over time:** Store results by week; trend = reading past weeks. No deletion of history for core metrics.

---

## 3. Phase 1 Scope (Recommended First Ship)

- **One AI engine:** Perplexity only (already integrated via OpenRouter). Add ChatGPT and Gemini in Phase 2.
- **Curated prompts only:** No automatic discovery. Define five prompt groups in config (or DB) with a **small** set per group (e.g. 5–10 per group, 25–50 total). You can list 20 per group in config but **cap execution** (e.g. `max_prompts_per_run: 30`, `max_per_group_per_run: 6`) so you stay under ~50 calls per week.
- **Weekly run:** One job per week (e.g. Sunday 02:00 UTC). Cache: for each (client, query, engine, week), if a result exists, skip. So you can backfill or re-run only missing (query, week) pairs.
- **Storage:**
  - **Visibility runs:** `(client, query, engine, week, answer_text, entities_found[], computed_at)`. Reuse existing entity detection on `answer_text` to fill `entities_found`.
  - **Weekly snapshots:** `(client, week, overall_visibility_index, per_group_metrics[], per_engine_metrics[])` for dashboard and trend.
  - **Recommendations:** `(client, week, query, engine, competitors_in_answer[], recommendation_text)` — rule-based in Phase 1.
- **Visibility metrics:**
  - **AI Visibility Index (overall):** `(number of runs where company in entities_found) / (total runs this week) * 100`.
  - **Prompt group visibility:** Same ratio per group.
  - **Engine visibility:** Same per engine (Phase 2 when you have multiple engines).
- **Recommendations (Phase 1):** Rule-based only. For each run where `entities_found` contains competitor(s) but not the company → one row: "Query: X. Sahi not visible; competitors: A, B. Recommendation: Publish content addressing [query topic]." No LLM per gap. Optional: one LLM call per week to summarize "Top 5 recommendations" from that list.
- **Dashboard (CXO):** One page replacing "AI Search Narrative": Overall AI Visibility Index, table (Group | Prompts run | Company visible count | Score %), simple trend (e.g. last 8 weeks), and a recommendations list. No multi-engine breakdown until Phase 2.

**Phase 1 API call budget (example):** 30 prompts × 1 engine × 1 run/week = 30 Perplexity calls/week. With 4–5s delay between calls, that’s ~2–3 minutes per run and fits typical free-tier limits if you don’t also run other heavy Perplexity usage the same day.

---

## 4. Prompt Strategy (Config, Not Auto-Discovery in Phase 1)

Define five groups in config (YAML or DB), each with a list of prompts. Example structure:

```yaml
# config/ai_visibility_prompts.yaml (or under ai_search_visibility in dev.yaml)
prompt_groups:
  - id: broker_discovery
    name: "Broker discovery queries"
    prompts:
      - "Best stock trading app India 2024"
      - "Top discount brokers India"
      # ... up to 20; Phase 1 can cap to first 5–10 per run
  - id: zerodha_alternative
    name: "Zerodha alternative queries"
    prompts: [ ... ]
  - id: feature_driven
    name: "Feature-driven queries"
    prompts: [ ... ]
  - id: problem_driven
    name: "Problem-driven trader queries"
    prompts: [ ... ]
  - id: product_comparison
    name: "Product comparison queries"
    prompts: [ ... ]
```

Execution cap in pipeline config: e.g. `max_prompts_per_run: 30`, `max_per_group: 6`, so you never run more than 30 in one weekly job.

---

## 5. Automatic Prompt Discovery (Phase 2+)

- **Do not** implement in Phase 1. It depends on external data and/or extra LLM calls.
- When you do:
  - **One source first:** e.g. one "related queries" or "People Also Ask" API (DataForSEO, SEMrush, or similar). Avoid scraping for PAA (ToS, brittle).
  - **Candidate pool:** New prompts go into a "candidate" set. Run a **small** sample per week (e.g. 5 new prompts), score by "company in answer?" or answer quality. Promote high-value candidates into the main pool.
  - **Cap growth:** e.g. max 5 new prompts per week so the pool doesn’t explode and blow rate limits.
  - **Optional LLM expansion:** "Generate 3 related prompts for: X" once per discovered query, not per prompt per run. Still costly; do only if you have quota.

---

## 6. Multi-Engine (Phase 2)

- **Phase 1:** Perplexity only.
- **Phase 2:** Add ChatGPT (OpenAI or OpenRouter) and Gemini (Google AI or OpenRouter). Abstract the "engine" behind an interface: `run_query(engine_id, query) -> answer_text`. Each engine has its own rate limits and cost; config should allow `enabled_engines: [perplexity]` and later `[perplexity, chatgpt, gemini]`.
- **Budget:** 30 prompts × 3 engines = 90 calls/week. Ensure you have quota and budget before enabling all three.

---

## 7. Visibility Detection (Reuse Only)

- Use **existing** entity detection (e.g. from `entity_detection_service` or the logic that detects company/competitors in text). Input = `answer_text`; output = list of entity names found.
- For each stored answer, run detection once and store `entities_found: ["Sahi", "Zerodha"]`. Then:
  - Company visible = company name in `entities_found`.
  - Competitors visible = competitor names in `entities_found`.
- No new detection model or pipeline; just a new **caller** of the existing logic.

---

## 8. Cost and Rate-Limit Controls

- **Cache by (client, query, engine, week).** If a result exists for the current week, skip. Enables backfill and avoids duplicate calls.
- **Weekly schedule only.** No daily run for this pipeline.
- **Config caps:** `max_prompts_per_run`, `max_per_group_per_run`, `delay_seconds_between_calls` (e.g. 4–5s).
- **Single run at a time:** Use the same backfill lock as other ingestion jobs so the visibility job doesn’t run concurrently with a manual "run all" and double the load.
- **Optional:** Per-engine daily cap (e.g. max 20 Perplexity calls per day) so if you later run multiple jobs, you don’t exceed provider limits.

---

## 9. Data Model (Suggested)

- **`visibility_runs`** (or keep `ai_search_answers` and extend):  
  `client, query, group_id, engine, week (e.g. 2025-W10), answer_text, entities_found[], computed_at`  
  Unique key: `(client, query, engine, week)`.

- **`visibility_weekly_snapshots`:**  
  `client, week, overall_index, group_metrics[{ group_id, name, prompts_run, company_visible_count, score_pct }], engine_metrics[{ engine, prompts_run, company_visible_count, score_pct }]`  
  One doc per (client, week).

- **`visibility_recommendations`:**  
  `client, week, query, engine, competitors_found[], recommendation_text (rule-based or later LLM)`  
  Optional: one summary field in snapshot: `top_recommendations[]` (e.g. top 5).

Indexes: `(client, week)` for snapshots; `(client, query, engine, week)` for runs; `(client, week)` for recommendations.

---

## 10. Recommendation Engine (Phase 1 = Rules Only)

- For each run where `entities_found` has at least one competitor and does **not** contain the company:
  - Insert a recommendation: "Query: \<query\>. \<Company\> not visible. Competitors in answer: \<list\>. Recommendation: Publish content addressing [query topic]." Use the query text as the "topic."
- No LLM per gap. Optional: one weekly LLM call to turn the list of such rows into "Top 5 strategic actions" for the CXO dashboard. If you’re strict on limits, skip even that in Phase 1.

---

## 11. Trend Tracking

- When you write a weekly snapshot, you have (client, week, overall_index, group_metrics). The dashboard reads the last N weeks (e.g. 8 or 12) and shows:
  - Line chart: week vs overall_index.
  - Table: week, overall index, per-group scores (optional).
No extra pipeline; just query and display.

---

## 12. CXO Dashboard (Replace AI Search Narrative Page)

- **Replace** the current "AI Search Narrative" page and nav item with **"AI Search Visibility"** (or "AI Visibility Monitoring").
- **Content:**
  - KPI: **Overall AI Visibility Index** (current week).
  - Table: **By prompt group** — Group name | Prompts run | Company visible count | Score %.
  - Table: **By engine** (Phase 2) — Engine | Prompts run | Company visible | Score %.
  - **Trend:** Chart or table of last 8 weeks (overall index).
  - **Recommendations:** List of rule-based (and later top-N LLM) recommendations with query and suggested action.
- **Filters:** Client (from existing clients list), week selector. No change to existing auth or layout patterns.

---

## 13. Future Extensions (Designed For, Not Built Now)

- **AI citation tracking:** Store raw answer; later parse or use API-specific citation format. No schema change now if you keep full `answer_text`.
- **Share of voice:** From `entities_found` count how often each entity appears across runs; aggregate by week/group/engine. Schema already supports it.
- **Answer ranking estimation:** Later: heuristics (e.g. position of company name in answer). No change to Phase 1 schema.
- **Narrative analysis:** Later: LLM or rules on `answer_text` to classify sentiment or narrative. Same storage.
- **Content opportunity detection:** Queries where company is not visible are already your recommendation source; "content opportunity" = same data with a different label or view.

Keep **raw answer text** and **entities_found** in the run table so these can be added without re-running prompts.

---

## 14. What Not to Do

- Don’t run 100 prompts × 3 engines in v1. Cap prompts and use one engine.
- Don’t add automatic prompt discovery before the curated-prompt pipeline is stable and under limits.
- Don’t use an LLM for every recommendation gap in Phase 1.
- Don’t change existing ingestion or entity-detection code; call it from the new visibility pipeline.
- Don’t remove or overwrite raw answers; keep them for future citation/narrative/ranking work.
- Don’t run the visibility job daily; weekly is enough and reduces cost and rate-limit risk.

---

## 15. Summary: Phased Plan

| Phase | Scope | API load (example) |
|-------|--------|---------------------|
| **1** | One engine (Perplexity), curated prompts (capped 25–30/run), weekly cache, entity detection on answers, rule-based recommendations, weekly snapshot, CXO dashboard replacing AI Search Narrative | ~30 calls/week |
| **2** | Add ChatGPT and Gemini; increase prompt cap if quota allows; engine-level metrics | ~90 calls/week if 30×3 |
| **3** | Automatic prompt discovery (one source, candidate pool, capped new prompts per week) | +variable |
| **Later** | Citations, SOV, ranking heuristics, narrative analysis, content opportunities | Mostly reads + optional LLM |

Implementing Phase 1 only gives you a working "How visible is Sahi in AI answers and what should we do?" dashboard without breaking existing systems or hitting LLM limits, and leaves room for prompt discovery and multi-engine in Phase 2+.
