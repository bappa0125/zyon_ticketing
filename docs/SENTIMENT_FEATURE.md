# Sentiment Analysis: What’s Done, What You See, Enterprise & PR Use

## What was implemented

1. **Entity mentions sentiment worker**  
   Runs VADER on `entity_mentions` where `sentiment` is missing. Uses **title + summary/snippet** per row, writes `sentiment` (positive/neutral/negative) and `sentiment_score`. Batch 50, scheduled every 20 minutes (configurable).

2. **Sentiment Summary API**  
   **GET /api/sentiment/summary** now aggregates by default from **entity_mentions** (main pipeline). Optional `?client=Sahi` filters to that client’s entities (client + competitors from config). Optional `?source=media_articles` uses the legacy media_articles collection.

3. **Scheduler**  
   New job `entity_mentions_sentiment` runs every 20 minutes so new mentions get sentiment without blocking ingestion.

4. **UI**  
   - **Sentiment page** (`/sentiment`): Chart of positive/neutral/negative **per entity**, filtered by client. Data = entity_mentions (same as Media Intelligence).  
   - **Media Intelligence feed** (`/media-intelligence`): Each card shows a **sentiment badge** (positive / neutral / negative) when that mention has sentiment set.

---

## What you should see

- **Sentiment page**  
  - One horizontal bar per entity (e.g. Sahi, Dhan, Groww, Zerodha). Each bar is stacked: green = positive, grey = neutral, red = negative.  
  - If you enter a client (e.g. Sahi) in the filter, only that client’s entities (client + competitors from config) are included.  
  - If there’s no sentiment yet: “No sentiment data yet. Run media monitoring and sentiment analysis.” Run the ingestion pipeline and wait for the sentiment job (or run the worker once, see below).

- **Media Intelligence feed**  
  - Each mention card can show a small **sentiment label** (e.g. “positive”, “neutral”, “negative”) when that row in entity_mentions has sentiment populated.

To backfill sentiment for existing mentions once:

```bash
docker compose exec backend python -c "
import asyncio
from app.services.entity_mentions_sentiment_worker import run_entity_mentions_sentiment
asyncio.run(run_entity_mentions_sentiment(batch_size=500))
"
```

---

## Is this what large enterprises do?

Yes. In enterprise media/PR tools (e.g. Cision, Meltwater, Brandwatch, Sprout):

- **Sentiment is run on every mention** (article, tweet, post) and stored.
- **Dashboards** show sentiment distribution (positive/neutral/negative) per brand, per time range, and per source.
- **Alerts** can trigger on negative spikes or sentiment trend changes.
- **Reports** for clients include share of voice, volume, and sentiment breakdown.

What you have now is the core: sentiment per mention, aggregation per entity, and a client filter. Adding time-range filters, trend charts, and alerts would make it closer to full enterprise reporting.

---

## How a PR firm uses it

1. **Coverage tone**  
   See at a glance whether coverage of the client (and competitors) is mostly positive, neutral, or negative.

2. **Client reports**  
   Export or screenshot the Sentiment page (and Media Intelligence feed) to show “X% positive, Y% neutral, Z% negative” and example headlines.

3. **Crisis / negative spike**  
   A sudden rise in negative mentions (or a drop in positive) can prompt a response plan or client call.

4. **Competitor comparison**  
   Filter by client to see client vs competitors on the same chart; e.g. “Sahi vs Zerodha vs Groww” sentiment mix.

5. **Campaign impact**  
   Compare sentiment before/after a launch or campaign (with a time-range view, if you add it later).

6. **Feed context**  
   On Media Intelligence, the sentiment badge on each card helps staff quickly triage which mentions to read first (e.g. negative or positive).

In short: PR teams use sentiment to **measure tone of coverage**, **report to clients**, **spot issues early**, and **compare against competitors**. Your implementation supports exactly that workflow.
