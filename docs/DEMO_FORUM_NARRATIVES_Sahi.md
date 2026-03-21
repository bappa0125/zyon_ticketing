# Demo: Trading forum narratives (Sahi + competitors)

Uses **`config/clients.yaml`**: client **Sahi** and all listed competitors (Zerodha, Upstox, Groww, …).  
API base: **`/api`** (e.g. `http://localhost:8000/api/...`).

## 1. Refresh data (optional but recommended before a client demo)

1. **Rebuild backend** if you changed `config/` locally (image copies `config/` at build time):

   ```bash
   docker compose build backend && docker compose up -d backend
   ```

2. **Ingest** RSS → articles → entity mentions (your usual pipeline / workers).

3. **Backfill** last N days so forum rows get `narrative_*`, `forum_site`, `feed_domain` where articles support it:

   ```bash
   docker compose exec backend python scripts/backfill_entity_mentions_multi.py \
     --reprocess-days 30 --limit 2000 --delay 0.3
   ```

   - Increase `--limit` or `--reprocess-days` if the demo window is thin.
   - `--reprocess-days` re-runs detection and **replaces** mentions for those URLs (narrative tags refresh).

## 2. CXO narrative landscape (publication vs forum + gaps)

**UI — full CXO memo:** **Reports → Narrative briefing** (`/reports/narrative-briefing`) — same tab row as Executive Report (“Intelligence tables” | “Narrative briefing”). **PR dashboard** is **`/reports/pr`** (bookmark `/reports` redirects there). Legacy `/social/narrative-briefing` redirects here.

**UI — drill-down:** **Narrative landscape** (`/social/narrative-landscape`) — per-theme publication vs forum, gaps, moves.

**API:**

```bash
curl -s "http://localhost:8000/api/social/narrative-landscape?client=Sahi&range_days=30&top_tags=15" | python3 -m json.tool
```

**Full briefing pack (read-only — latest snapshot from Mongo, no live LLM):**

```bash
curl -s "http://localhost:8000/api/social/narrative-briefing-pack?client=Sahi&range_days=30" | python3 -m json.tool
```

Snapshots are written by **daily ingestion** (`narrative_briefing_daily` cron, **10:15** server time after positioning) and by **master backfill** (`narrative_briefing` phase). Populate manually:

`docker compose exec backend python scripts/run_narrative_briefing_daily.py`

**7-day mention trend (live, for sparkline UI):**

```bash
curl -s "http://localhost:8000/api/social/narrative-briefing-trends?client=Sahi&days=7" | python3 -m json.tool

# Explicit IANA zone (overrides `report_timezone` in clients.yaml):
curl -s "http://localhost:8000/api/social/narrative-briefing-trends?client=Sahi&days=7&timezone=Asia/Kolkata" | python3 -m json.tool
```

## 3. API calls for the deck (raw JSON)

**Forum mentions** (Sahi + every competitor in `clients.yaml`, last 30 days):

```bash
curl -s "http://localhost:8000/api/social/forum-mentions?client=Sahi&range_days=30&limit=80" | python3 -m json.tool
```

**Narrative traction** (tag × forum site — good for “what themes echo on which forums”):

```bash
curl -s "http://localhost:8000/api/social/forum-mentions/narrative-tags?client=Sahi&range_days=30&top_n=50" | python3 -m json.tool
```

**Forum topic traction** (topics joined from articles):

```bash
curl -s "http://localhost:8000/api/social/forum-mentions/topics?client=Sahi&range_days=30&top_n=20" | python3 -m json.tool
```

**Single competitor** (optional):

```bash
curl -s "http://localhost:8000/api/social/forum-mentions?entity=Zerodha&range_days=30&limit=40" | python3 -m json.tool
```

## 4. OpenAPI

`http://localhost:8000/docs` → tag **social** → confirm paths under `/api/social/...`.

## 5. If narratives look empty

- Confirm **`type: forum`** rows exist in Mongo `entity_mentions` (forum RSS domains / `feed_domain` on `article_documents`).
- Older articles may lack **`feed_domain`** until re-fetched or backfilled after fetcher changes.
- Rule-based tags need enough **title/summary/text** in `article_documents` for `tag_text_for_narratives` to match the taxonomy.
