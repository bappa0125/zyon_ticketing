# Executive Competitor Intelligence Report — Implementation Readiness

## Do we have all the data and code to implement without breaking anything?

**Short answer: Almost all. You can implement the report without changing existing pipelines or breaking current behavior.** One new aggregation layer (backend and/or frontend) is needed to assemble the mockup sections from existing APIs.

---

## Data and APIs that already exist (per client)

| Mockup section | Existing API(s) | Client param | What you get |
|----------------|-----------------|--------------|--------------|
| **1. Reputation & Sentiment** | `GET /reports/reputation?client=X&range=7d` | ✓ | `sentiment`: per-entity positive/neutral/negative counts. `negative_topics`, `negative_sources`. No 0–100 “reputation score” in API — derive from sentiment mix if needed. |
| | `GET /sentiment/summary?client=X` | ✓ | Per-entity pos/neu/neg counts (entity_mentions). |
| **2. PR agency summary & Share of voice** | `GET /media-intelligence/dashboard?client=X&range=7d` | ✓ | `coverage` (entity + mentions), `by_domain`, `pr_summary` (text). SOV % = (entity mentions / total) × 100 from `coverage`. |
| **3. Coverage intel** | `GET /coverage/article-counts?client=X` | ✓ | Total articles, with_client, competitor_only. |
| | `GET /coverage/competitors?client=X` | ✓ | Coverage comparison (client vs competitors). |
| | `GET /media-intelligence/dashboard?client=X&range=7d` | ✓ | `by_domain` = per-source counts; “top publications” and “gaps” derivable. |
| **4. PR opportunities** | `GET /opportunities?client=X` | ✓ | Topic gaps (competitors have, client doesn’t). |
| | `GET /opportunities/pr-intel?client=X&days=7` | ✓ | `quote_alerts`, `outreach_drafts`, `competitor_responses` from pr_opportunities. |
| **5. PR Intelligence 7d synopsis** | No single “synopsis” endpoint. | — | **Option A:** Use `GET /reports/ai-brief?client=X&range=7d` (LLM brief). **Option B:** Use `pr_summary` from media-intelligence dashboard (deterministic). **Option C:** New 2–3 sentence summary from pr-intelligence topic-articles + coverage. |
| **6. Narrative shift & PR brief** | `GET /social/narrative-shift` | No (global) | Narratives, platform_totals — same for all. |
| | `GET /social/narrative-positioning?client=X&days=7` | ✓ | Per-client PR brief, positioning, narratives, threats, opportunities. |
| **7. AI Search Visibility** | `GET /social/ai-search-visibility/dashboard?client=X&weeks=8` | ✓ | Latest snapshot, trend, recommendations, samples. |

So: **all sections except “PR Intelligence 7d synopsis” have a direct or derivable data source.** For the synopsis, reusing an existing brief or `pr_summary` is enough for v1.

---

## What is missing (no new pipelines)

1. **One aggregation entry point**  
   Either:
   - **Backend:** One new endpoint, e.g. `GET /reports/executive-competitor?range=7d`, that:
     - Loads the 5 clients (from `executive_competitor_analysis.yml` when that’s in use),
     - For each client calls existing services/APIs (reputation, media dashboard, coverage, opportunities, narrative positioning, visibility dashboard),
     - Optionally derives: reputation score, SOV %, trend vs previous period,
     - Returns one JSON with all sections (and data-quality notes).
   - **Frontend only:** One new page that calls existing APIs per client (e.g. 5 × 6–7 calls), then assembles the report. Works but more requests and logic in the UI.

2. **Optional “reputation score” (0–100)**  
   Not in APIs. Can be derived in the aggregation layer from sentiment (e.g. weighted pos/neu/neg) or omitted and keep sentiment mix only.

3. **Optional “trend vs prev 7d”**  
   Either: call reputation/sentiment with `range=14d` and compute diff in aggregation, or add a small backend helper that returns current vs previous period.

4. **PR Intelligence 7d synopsis**  
   Use existing `reports/ai-brief` or media `pr_summary` for v1; no new pipeline.

No new ingestion, no new DB collections, no changes to existing API contracts.

---

## Can we implement without breaking anything?

**Yes.**

- **New only:** New route(s) (e.g. `/reports/executive-competitor`) and one new frontend page (e.g. `/reports/executive-competitor` or `/executive-competitor-intelligence`).
- **Existing:** All current APIs and pages stay as they are. The report only **reads** from the same services/DB the rest of the app uses.
- **Client set:** When `executive_competitor_analysis.use_this_file: true`, `load_clients()` already returns the 5 brands; the new report uses that list so it stays in sync with the rest of the app.

---

## Prerequisites to build this

### 1. Config and client set

- **`config/executive_competitor_analysis.yml`** with the 5 clients (Sahi, Zerodha, Dhan, Groww, Kotak Securities) — already present.
- **`executive_competitor_analysis.use_this_file: true`** in `config/dev.yaml` (or your env) so the report and pipelines use these 5.

### 2. Data in the system

- **Backfill run** so the 5 clients have data:
  - Entity mentions (and sentiment where applicable)
  - Article documents / coverage
  - Narrative positioning (PR brief) per client
  - AI Search Visibility snapshots and runs
  - PR opportunities (quote alerts, etc.) if you use that batch

Command (from project root, with Docker):

```bash
docker compose exec backend python scripts/run_master_backfill.py
```

Optional: `--dry-run` first; use `--skip <phase>` if you want to skip heavy phases.

### 3. Services and env

- **MongoDB** and **Redis** up.
- **OPENROUTER_API_KEY** set if you use any LLM-dependent pipeline (narrative positioning, AI brief, PR opportunities, etc.).
- Config (and optional env) loaded so the backend sees `executive_competitor_analysis` and the 5-client file.

### 4. Implementation steps (high level)

1. **Backend**
   - Add one endpoint, e.g. `GET /reports/executive-competitor?range=7d`.
   - In that endpoint: load clients (from config/loader); for each client call existing services (reputation, media_intelligence get_dashboard, coverage, opportunities, narrative_positioning load_positioning, ai_search_visibility load_dashboard); optionally derive SOV, reputation score, trend; build one JSON (sections 1–7 + meta).
   - Optionally add a tiny helper for “PR Intelligence 7d synopsis” (e.g. return ai-brief or pr_summary per client) so the response matches the mockup.

2. **Frontend**
   - Add one page (e.g. under `/reports/` or `/executive-competitor-intelligence`) that:
     - Calls the new endpoint (or multiple existing APIs if you skip the aggregator).
     - Renders the mockup layout: meta bar, executive summary + takeaways, then sections 1–7 with tables/cards and data-quality lines.

3. **No change** to existing APIs, pipelines, or client loader behavior beyond what you already have (executive file when enabled).

---

## Summary

| Question | Answer |
|----------|--------|
| Do we have the data? | Yes — all sections map to existing APIs or derivable from them; only “7d synopsis” is reused from existing brief/summary. |
| Do we have the code? | Yes — existing services and routes; you add one aggregation layer (backend and/or frontend) and one report page. |
| Will it break anything? | No — report is additive (new route + new page), read-only on existing data. |
| Prerequisites? | Config (5 clients, use_this_file), backfill so data exists, MongoDB/Redis/optional OPENROUTER_API_KEY, then implement aggregator + report page. |

You have what you need to implement the mockup end-to-end without breaking existing behavior.

---

## 502 Bad Gateway when clicking "Generate report now"

Report generation can take **1–2 minutes** (many service calls for 5 clients). If the gateway in front of the backend times out, you get **502 Bad Gateway**.

**If using Docker (nginx):**
- `docker/nginx.conf` has a dedicated location for `/api/reports/executive-competitor` with **600s** (10 min) read/send timeout. Apply it by recreating nginx:  
  `docker compose up -d --force-recreate nginx`

**If running frontend in dev (Next.js proxy to backend):**
- The Next.js rewrite can time out. Bypass the proxy by calling the backend directly: set `NEXT_PUBLIC_API_URL=http://localhost:8000/api`, ensure the backend is running on port 8000, and reload the app. The report request will then go from the browser to the backend with no proxy timeout.
