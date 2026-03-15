# Executive Competitor Analysis — What the report will show

When `executive_competitor_analysis.use_this_file: true` in config, the app uses **config/executive_competitor_analysis.yml** and runs all pipelines for these **5 clients**: **Sahi, Zerodha, Dhan, Groww, Kotak Securities**.

---

## What the report will show (per client, across existing URLs)

Data is produced **per client** by the same pipelines the app already runs. There is no single “executive report” page yet; the following is what **will be available** across the app’s existing URLs once backfill has run.

### 1. **AI Search Visibility** (`/social/ai-search-narrative`)

- **Overall AI Visibility Index** (% of prompts where the brand appeared in Perplexity answers).
- **By prompt group**: Broker discovery, Zerodha alternatives, Feature-driven, Problem-driven, Product comparison — prompts run, company visible count, score %.
- **Trend**: Last 4/8/12 weeks of the visibility index.
- **Sample prompts & results**: Example queries and AI answers, with “Visible in answer” / “Not in answer” and entities found.
- **Recommendations**: Rule-based suggestions where competitors appeared but the brand did not.

*Shown for: Sahi, Zerodha, Dhan, Groww, Kotak Securities (switch client in the UI).*

---

### 2. **Narrative Positioning** (`/social/narrative-intelligence`)

- **PR brief**: Executive summary of trending narratives, client vs competitors, and actions.
- **Positioning**: Headline, pitch angle, suggested outlets.
- **Narratives**: Themes, sentiment, platforms, evidence count, sample quotes.
- **Threats** and **Opportunities**.
- **Evidence refs** and **Content suggestions** (Articles, YouTube, Reddit).

*Shown per client (Sahi, Zerodha, Dhan, Groww, Kotak Securities).*

---

### 3. **Coverage** (e.g. `/coverage` or coverage APIs)

- Coverage metrics by source/domain for the selected client vs competitors.
- Share of voice and top sources.

*Per client.*

---

### 4. **Other existing URLs** (PR Intelligence, Reports, Social, etc.)

- Any dashboard or API that is **client-scoped** will show data for whichever of the five clients is selected.
- Data is the same as today; the only change is that **five brands** (Sahi, Zerodha, Dhan, Groww, Kotak Securities) are now **clients**, so each gets its own narrative, visibility, and coverage run.

---

## What is **not** implemented yet

- **Single one-page executive summary** that aggregates all five clients (e.g. one table or one PDF with all five side by side). That would require a new page/API that pulls from the above and renders one consolidated view.
- **Executive competitor analysis** here means: “Use these 5 clients for all pipelines and show their data in the existing per-client URLs.” A combined one-pager can be added later on top of this.

---

## After backfill

- Use the **client** dropdown (or `client` query param) on each relevant URL to switch between **Sahi**, **Zerodha**, **Dhan**, **Groww**, and **Kotak Securities**.
- Each client will have its own AI Visibility snapshot, Narrative Positioning report, and coverage data for the weeks that have been run.
