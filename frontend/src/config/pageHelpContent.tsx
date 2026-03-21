/**
 * Section-based help: per-page sections with interpretation, controls, and PR agency use.
 * Rendered in the sliding Help panel (right). Multiple sections per page when the page has distinct areas.
 */
import type { ReactNode } from "react";

export type HelpControl = {
  name: string;
  howToUse: string;
};

export type HelpSection = {
  sectionTitle: string;
  whatItIs: ReactNode;
  howToInterpret?: ReactNode;
  controls?: HelpControl[];
  prAgencyUse: ReactNode;
};

export type PageHelp = {
  title: string;
  summary: string;
  sections: HelpSection[];
};

const p = "mb-2 last:mb-0";
const ul = "list-disc pl-5 space-y-1 mb-2 last:mb-0";
const muted = "text-[var(--ai-muted)]";
const strong = "text-[var(--ai-text)]";

export const PAGE_HELP: Record<string, PageHelp> = {
  "/": {
    title: "Home",
    summary: "Overview of all app sections. Each card links to a page: Chat, Dashboard, Topics, Reputation, Alerts, Targets, Media Intel, Sentiment, Coverage, Clients, Media, Opportunities, Social.",
    sections: [
      {
        sectionTitle: "Where to go",
        whatItIs: (
          <p className={p}>
            Use the cards to jump to any section. Descriptions match what each page does so you can choose the right view.
          </p>
        ),
        prAgencyUse: (
          <p className={p + " " + muted}>
            Start with Dashboard for client pulse; use Chat for ad-hoc questions; use Alerts and Reputation for risk and response.
          </p>
        ),
      },
    ],
  },

  "/chat": {
    title: "Chat",
    summary: "Conversational AI with live search and pipeline steps. Ask questions in natural language; the assistant can run retrieval and show reasoning.",
    sections: [
      {
        sectionTitle: "Chat & pipeline",
        whatItIs: (
          <p className={p}>
            You send messages and get answers. When pipeline steps are enabled, you see which tools ran (e.g. search, retrieval) before the final response.
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li><span className={strong}>New chat</span> — starts a fresh thread; previous threads stay in the sidebar.</li>
            <li><span className={strong}>Pipeline steps</span> — show the process (Searching → Reading → Writing) so you can trust and trace the answer.</li>
            <li><span className={strong}>Live search</span> — augments answers with recent web/context when available.</li>
          </ul>
        ),
        controls: [
          { name: "Sidebar", howToUse: "Switch or start conversations. Use “New chat” for a clean slate." },
          { name: "Message input", howToUse: "Type your question and send. Be specific (e.g. “Compare Sahi and Zerodha coverage last 7 days”) for better results." },
        ],
        prAgencyUse: (
          <p className={p + " " + muted}>
            Use Chat for ad-hoc synthesis and quick answers. For client-ready metrics and share of voice, use <strong className={strong}>Dashboard</strong> or <strong className={strong}>Topics</strong>; for spikes and sentiment, use <strong className={strong}>Alerts</strong> and <strong className={strong}>Reputation</strong>. Chat is best for “what if” questions and narrative summaries you can paste into emails or briefs.
          </p>
        ),
      },
    ],
  },

  "/dashboard": {
    title: "Executive PR Pulse",
    summary: "Single view of mentions, share of voice, timeline, ranked sources, and AI-generated brief. Use it as the main client-facing pulse and for weekly reports.",
    sections: [
      {
        sectionTitle: "Filters & controls",
        whatItIs: (
          <p className={p}>
            The header controls which client and time window the whole page uses. All widgets (KPIs, charts, tables, AI brief) respect these filters.
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li>Changing <strong className={strong}>Client</strong> switches the entity set (client + competitors from config).</li>
            <li><strong className={strong}>Range</strong> (24h / 7d / 30d) defines the lookback; 7d is typical for weekly reports.</li>
          </ul>
        ),
        controls: [
          { name: "Client dropdown", howToUse: "Select the brand you’re reporting on. Only configured clients appear; this drives competitor comparison everywhere." },
          { name: "Range dropdown", howToUse: "Choose 24h (daily pulse), 7d (weekly), or 30d (monthly). Use 7d for most client calls and board decks." },
          { name: "Download HTML brief", howToUse: "Downloads a static HTML report of the current view. Share as an attachment or print for offline meetings." },
          { name: "Download PDF", howToUse: "Same content as HTML but rendered as PDF. Use for formal deliverables and email attachments." },
        ],
        prAgencyUse: (
          <p className={p + " " + muted}>
            Start every client check-in from this page. Use the same range (e.g. 7d) for consistency. Export PDF for clients who want a one-pager; use the on-screen view for live walkthroughs. Pair with Topics for “what to say” and Reputation for “what to fix.”
          </p>
        ),
      },
      {
        sectionTitle: "KPIs & share of voice",
        whatItIs: (
          <p className={p}>
            Total mentions is the deduplicated count (by url + entity) in the selected range. Share of voice (bar and donut) shows how that volume splits between your client and each competitor.
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li><strong className={strong}>Total mentions</strong> — one number for the period; compare week-over-week by changing range or re-running next week.</li>
            <li><strong className={strong}>Bar chart</strong> — longer bar = more mentions; client is usually labeled “(client)”.</li>
            <li><strong className={strong}>Donut</strong> — same split as percentages; centre shows total count.</li>
          </ul>
        ),
        prAgencyUse: (
          <p className={p + " " + muted}>
            Lead client calls with “This week you had X mentions; your share of voice was Y%.” If a competitor’s bar is larger, use it as a hook: “Zerodha had more pickup—here’s where and what we can do next.” Use Alerts to explain spikes.
          </p>
        ),
      },
      {
        sectionTitle: "Mentions per day & ranked sources",
        whatItIs: (
          <p className={p}>
            The bar chart shows daily volume (stacked by entity). Ranked sources is a table of outlets with mention counts for client and each competitor.
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li><strong className={strong}>Mentions per day</strong> — spikes often align with news, launches, or crises; compare client vs competitors by colour.</li>
            <li><strong className={strong}>Ranked sources</strong> — sort by total to see which outlets drive volume; use entity columns to see who “owns” which publication.</li>
          </ul>
        ),
        prAgencyUse: (
          <p className={p + " " + muted}>
            Use the daily chart to tell a story: “Tuesday’s spike was the product launch.” Use ranked sources to build pitch lists: prioritise outlets where the client is under-represented vs competitors. Suggest “we need more presence in X” with data.
          </p>
        ),
      },
      {
        sectionTitle: "Trending topics & actions",
        whatItIs: (
          <p className={p}>
            Topics are extracted from article text; each row shows volume, trend %, sentiment, and a suggested action (Talk / Careful / Avoid) from the sentiment mix.
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li><strong className={strong}>Vol</strong> — mention count for that topic.</li>
            <li><strong className={strong}>Trend %</strong> — up or down vs prior period.</li>
            <li><strong className={strong}>Act</strong> — TALK (leaning positive), CAREFUL (mixed), AVOID (leaning negative). Expand the row for sample headlines.</li>
          </ul>
        ),
        prAgencyUse: (
          <p className={p + " " + muted}>
            Feed this into messaging and spokesperson briefs. “Talk” topics = safe to lean in; “Avoid” = prepare Q&A and avoid amplifying unless you have a clear angle. Use sample headlines to draft talking points and rebuttals.
          </p>
        ),
      },
      {
        sectionTitle: "AI PR Brief",
        whatItIs: (
          <p className={p}>
            One-click generation of an executive summary, tone guidance, talk/avoid points, target outlets, and focus articles. Uses a single LLM call with cache and daily quota to stay within free-tier limits.
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li>Content is based on the current client and range (dashboard + topics + reputation + headlines).</li>
            <li><strong className={strong}>Cached</strong> means the same client/range was generated recently; you get instant display without a new API call.</li>
          </ul>
        ),
        controls: [
          { name: "Generate AI Brief", howToUse: "Click once. Wait a few seconds. The brief appears below. If you change client or range, generate again; previous brief is replaced." },
        ],
        prAgencyUse: (
          <p className={p + " " + muted}>
            Use the AI brief as a first draft for client emails and internal strategy docs. Copy executive summary into the top of a weekly email; use talk/avoid for spokesperson briefs; use target outlets and focus articles to prioritise outreach. Always fact-check numbers against the Dashboard; the AI synthesises narrative, not raw counts.
          </p>
        ),
      },
    ],
  },

  "/topics": {
    title: "Topics & trending",
    summary: "Topic-level volume, trend %, sentiment, and recommended actions (Talk / Careful / Avoid). Use for messaging and briefing.",
    sections: [
      {
        sectionTitle: "Topics table",
        whatItIs: (
          <p className={p}>
            Topics are extracted from article text and joined with entity mentions. Each row is a theme with volume, trend, sentiment summary, and an action label.
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li><strong className={strong}>Vol</strong> — mention count for that topic in the selected range.</li>
            <li><strong className={strong}>Trend %</strong> — change vs prior window; ↑ = rising, ↓ = falling.</li>
            <li><strong className={strong}>Sentiment</strong> — positive/neutral/negative mix.</li>
            <li><strong className={strong}>Act</strong> — TALK / CAREFUL / AVOID from sentiment. Expand rows for sample headlines.</li>
          </ul>
        ),
        controls: [
          { name: "Client dropdown", howToUse: "Filters topics to mentions that include this client (and its competitor set)." },
          { name: "Range dropdown", howToUse: "Time window for topic counts and trend (e.g. 7d vs prior 7d)." },
          { name: "Export Brief", howToUse: "Downloads a TSV of the table for use in spreadsheets or external reports." },
        ],
        prAgencyUse: (
          <p className={p + " " + muted}>
            Use “Talk” topics for proactive pitches and spokesperson angles; “Avoid” for crisis prep and Q&A. Sample headlines help you draft exact lines. Cross-reference with Reputation when a topic is driving negative sentiment.
          </p>
        ),
      },
    ],
  },

  "/reputation": {
    title: "Reputation",
    summary: "Sentiment breakdown by entity, negative topics, and negative sources. Use for risk and response planning.",
    sections: [
      {
        sectionTitle: "Sentiment & negative drivers",
        whatItIs: (
          <p className={p}>
            Tables show positive / neutral / negative counts per entity and list topics and sources that are driving negative sentiment.
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li>Compare client vs competitors on the same range.</li>
            <li>Negative topics list themes dragging sentiment; sample headlines give context.</li>
            <li>Negative sources = outlets where negative mentions cluster.</li>
          </ul>
        ),
        controls: [
          { name: "Client dropdown", howToUse: "Select the brand; data is for this entity set." },
          { name: "Range dropdown", howToUse: "Time window (24h / 7d / 30d)." },
          { name: "Download HTML brief", howToUse: "Offline snapshot of the reputation report." },
        ],
        prAgencyUse: (
          <p className={p + " " + muted}>
            If negative spikes on one domain, consider outreach or correction only where there are factual errors. Use negative topics for Q&A and holding statements; use Alerts to catch spikes early.
          </p>
        ),
      },
    ],
  },

  "/alerts": {
    title: "Alerts",
    summary: "Spike detection over a sliding window. Use for early warning and campaign tracking.",
    sections: [
      {
        sectionTitle: "Spikes",
        whatItIs: (
          <p className={p}>
            Compares current-window volume to baseline to flag unusual bursts (by entity, topic, or source).
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li>Higher spike score = stronger deviation from baseline.</li>
            <li>Cross-check with Reputation if sentiment turns negative.</li>
          </ul>
        ),
        prAgencyUse: (
          <p className={p + " " + muted}>
            Spike on “regulatory” + negative sentiment → prioritise comms review and holding statements. Use for crisis early warning and to prove campaign impact when spikes are positive.
          </p>
        ),
      },
    ],
  },

  "/targets": {
    title: "Targets",
    summary: "Outlets where client and competitors appear. Use to prioritise outreach and pitch lists.",
    sections: [
      {
        sectionTitle: "Targets table",
        whatItIs: (
          <p className={p}>
            Ranks domains by where you and competitors are mentioned so you can target PR and relationship building.
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li>High client + competitor overlap = contested narrative space.</li>
            <li>Use with Topics to align pitches to themes that outlet already covers.</li>
          </ul>
        ),
        prAgencyUse: (
          <p className={p + " " + muted}>
            Domains with high competitor mentions but low client = opportunity for thought leadership if the audience matches. Use for “we need to be in X” conversations with clients.
          </p>
        ),
      },
    ],
  },

  "/media-intelligence": {
    title: "Media Intelligence",
    summary: "Dashboard-style feed and filters for coverage discovery.",
    sections: [
      {
        sectionTitle: "Feed & filters",
        whatItIs: (
          <p className={p}>
            Explores the unified feed with optional domain and content-quality filters.
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li>Snippet vs full_text indicates how much context was extracted.</li>
            <li>Also-mentions shows co-occurring entities in the same article.</li>
          </ul>
        ),
        prAgencyUse: (
          <p className={p + " " + muted}>
            Filter to one domain to see narrative consistency before pitching spokespeople. Use for deep dives when Dashboard view isn’t enough.
          </p>
        ),
      },
    ],
  },

  "/sentiment": {
    title: "Sentiment",
    summary: "Sentiment summaries and mention-level drill-down.",
    sections: [
      {
        sectionTitle: "Sentiment data",
        whatItIs: <p className={p}>Distribution and mention-level detail for analysis.</p>,
        howToInterpret: (
          <ul className={ul}>
            <li>Neutral is common; compare deltas across time ranges.</li>
            <li>Pair with Topics to see which themes drive polarized sentiment.</li>
          </ul>
        ),
        prAgencyUse: (
          <p className={p + " " + muted}>
            Shift from 7d to 30d to see if a negative cluster is persistent or a one-off. Use for client questions like “how are we trending?”
          </p>
        ),
      },
    ],
  },

  "/coverage": {
    title: "Coverage",
    summary: "Coverage comparison and timeline.",
    sections: [
      {
        sectionTitle: "Coverage",
        whatItIs: <p className={p}>Compares entities and timelines.</p>,
        howToInterpret: (
          <ul className={ul}>
            <li>Align range with campaign windows for before/after.</li>
          </ul>
        ),
        prAgencyUse: (
          <p className={p + " " + muted}>
            After a launch, use 24h for immediate pulse and 7d for week-over-week narrative.
          </p>
        ),
      },
    ],
  },

  "/clients": {
    title: "Clients",
    summary: "Configured clients used across Dashboard, Topics, and reports.",
    sections: [
      {
        sectionTitle: "Client list",
        whatItIs: <p className={p}>Lists clients from config; selection elsewhere drives entity set and competitor comparison.</p>,
        prAgencyUse: (
          <p className={p + " " + muted}>
            Ensure the client you’re reporting on exists here; add or fix in config if needed.
          </p>
        ),
      },
    ],
  },

  "/media": {
    title: "Media",
    summary: "Media pipeline status and latest ingested content.",
    sections: [
      {
        sectionTitle: "Media",
        whatItIs: <p className={p}>Access to pipeline status and latest content.</p>,
        prAgencyUse: (
          <p className={p + " " + muted}>
            If counts are stale, check ingestion schedules and source configs.
          </p>
        ),
      },
    ],
  },

  "/opportunities": {
    title: "PR Opportunities",
    summary:
      "Topic gaps (where competitors have coverage and the client does not), plus three LLM-assisted tabs: story comment alerts (no-comment phrasing in ingested news), outreach drafts, and competitor response angles. The Story comment alerts tab includes an on-page explainer for leadership. All depend on recent media ingestion and correct client entity names.",
    sections: [
      {
        sectionTitle: "Topic gaps",
        whatItIs: (
          <p className={p}>
            Lists topics where competitors have mentions in the window but your selected client does not — useful for editorial and pitching strategy.
          </p>
        ),
        controls: [
          { name: "Client", howToUse: "Pick the brand; the table refreshes for that client’s entity set from config." },
        ],
        prAgencyUse: (
          <p className={p + " " + muted}>
            Use with <strong className={strong}>Targets</strong> to prioritise outlets. Pair with Media Intel when validating why a gap exists.
          </p>
        ),
      },
      {
        sectionTitle: "Story comment alerts (often empty — by design)",
        whatItIs: (
          <p className={p}>
            Not general “good stories.” The backend only flags <strong className={strong}>article_documents</strong> from the{" "}
            <strong className={strong}>last 7 days</strong> that (1) include your client in the <code className="text-xs">entities</code> array and (2) contain
            specific English phrases journalists use when someone <strong className={strong}>didn’t comment</strong> — e.g. “declined to comment,” “no comment,” “we reached out,”
            “could not be reached,” “contacted for comment.” Then an LLM adds a short suggested action.
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li>
              <strong className={strong}>Empty tab</strong> is normal if your feed rarely runs those exact phrases or you have little 7-day coverage with full article text.
            </li>
            <li>
              <strong className={strong}>Generate / Refresh</strong> must run (or the daily job) to write rows; the UI only reads what was stored.
            </li>
          </ul>
        ),
        controls: [
          {
            name: "Generate / Refresh",
            howToUse:
              "Runs the PR opportunities batch for the selected client: scans for quote phrases, builds outreach drafts, competitor angles. Use after ingestion or when data was empty.",
          },
        ],
        prAgencyUse: (
          <p className={p + " " + muted}>
            Treat as a <strong className={strong}>narrow alert channel</strong> for “story explicitly sought comment / no response” situations — not a replacement for reading headlines. For broader narrative work, use Dashboard, Topics, or Narrative views.
          </p>
        ),
      },
      {
        sectionTitle: "Outreach drafts & competitor responses",
        whatItIs: (
          <p className={p}>
            <strong className={strong}>Outreach drafts</strong> target outlets where the client has zero coverage but competitors appear; lines are LLM-generated pitch openers.{" "}
            <strong className={strong}>Competitor responses</strong> use recent competitor mention articles and suggest one response angle for your client.
          </p>
        ),
        prAgencyUse: (
          <p className={p + " " + muted}>
            Edit every draft before sending; align with compliance. If outreach is empty, ensure <code className="text-xs">source_domain</code> is backfilled on mentions/articles where needed.
          </p>
        ),
      },
    ],
  },

  "/social": {
    title: "Social",
    summary: "Latest social posts and related context.",
    sections: [
      {
        sectionTitle: "Social",
        whatItIs: <p className={p}>Recent social activity for tracked entities.</p>,
        howToInterpret: (
          <p className={p + " " + muted}>
            Cross-reference with Alerts when social volume spikes with media pickup.
          </p>
        ),
        prAgencyUse: (
          <p className={p + " " + muted}>
            Use for integrated reports (media + social) and crisis monitoring.
          </p>
        ),
      },
    ],
  },

  "/social/forums": {
    title: "Forum mentions",
    summary:
      "Retail and trader conversation: an unbranded theme digest (Indian forums + optional Reddit), a three-part PR intelligence pack, brand-filtered mentions, and topic traction — all from ingested forum threads.",
    sections: [
      {
        sectionTitle: "How to use this page (workflow)",
        whatItIs: (
          <p className={p}>
            Work <strong className={strong}>top to bottom</strong>. First, read the <strong className={strong}>Retail discourse themes</strong> box for what retail communities are talking about <em>without</em> needing a brand name in the text. Then use <strong className={strong}>Entity filter</strong> when you care about a specific company (Zerodha, Sahi, etc.). The tables below show which topics and threads mention those brands.
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li>
              <strong className={strong}>Theme digest + PR pack</strong> — “What is the market mood?” (IPO chatter, F&amp;O, trust, regulation, education angles). Good for weekly client decks and prep calls.
            </li>
            <li>
              <strong className={strong}>Topics by traction</strong> — Which <em>named topics</em> appear most in forum mentions in the last 14 days (can follow your entity filter).
            </li>
            <li>
              <strong className={strong}>Recent forum mentions</strong> — Raw rows: entity, source site, title, link. Use for verification, quotes, and escalation.
            </li>
            <li>
              <strong className={strong}>By source</strong> — Quick count of mentions per domain in your current mention list (helps see if one forum dominates).
            </li>
          </ul>
        ),
        prAgencyUse: (
          <p className={p + " " + muted}>
            Use the top section for <strong className={strong}>retainer-style landscape briefs</strong> (“what retail is debating this week”). Use the filtered mentions for <strong className={strong}>brand-specific monitoring</strong> and stakeholder Q&amp;A. Always treat linked threads as <strong className={strong}>illustrative samples</strong>, not a census of all investors — pair with your client’s compliance process before external use.
          </p>
        ),
      },
      {
        sectionTitle: "Retail discourse themes & PR pack (controls)",
        whatItIs: (
          <p className={p}>
            This panel aggregates themes from <strong className={strong}>Indian forums</strong> (ValuePickr, TradingQnA, Traderji) and, when enabled, <strong className={strong}>Reddit</strong> posts already stored in the system. Themes come from a fixed keyword taxonomy — not from an LLM guessing headlines. The <strong className={strong}>three cards</strong> are a ready-made “PR intelligence pack”: discourse map, risk/FAQ hooks, and content/spokesperson angles.
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li>
              <strong className={strong}>Meta line</strong> (small caps under the title) — Digest date, rolling window (e.g. last 7 days), whether data was <strong className={strong}>cached</strong> or <strong className={strong}>live</strong>, which <strong className={strong}>surfaces</strong> had data, and how many forum docs / Reddit posts were scored.
            </li>
            <li>
              <strong className={strong}>Disclaimer</strong> (if shown) — Read before sharing externally; it limits statistical claims.
            </li>
            <li>
              <strong className={strong}>Cover line</strong> — One-line summary of the PR pack for that window.
            </li>
            <li>
              <strong className={strong}>Card 1 — Discourse map</strong> — Top themes across all surfaces; use for exec summaries and client “what are people talking about?”
            </li>
            <li>
              <strong className={strong}>Card 2 — Risk &amp; FAQ hooks</strong> — Themes tied to trust, regulation, pricing, platform, support; use for Q&amp;A prep and issues monitoring (not legal advice).
            </li>
            <li>
              <strong className={strong}>Card 3 — Content &amp; spokesperson angles</strong> — Education, products, and narrative hooks grounded in observed threads; use for pitches, bylines, and calendar ideas (align with compliance).
            </li>
            <li>
              <strong className={strong}>Theme detail by surface</strong> — Same themes broken down per forum/Reddit so you can cite where a narrative is loudest.
            </li>
          </ul>
        ),
        controls: [
          {
            name: "Recompute now",
            howToUse:
              "Rebuilds the digest immediately using the latest stored forum and Reddit content (rolling window, usually 7 days). Can take a moment. Use when you need the freshest snapshot after new ingestion.",
          },
          {
            name: "Run scheduled job",
            howToUse:
              "Triggers the same job the server scheduler runs (if enabled in config). Use after large backfills or when cached data is stale and you want a server-side refresh.",
          },
          {
            name: "Lead examples / sample thread links",
            howToUse:
              "Open links to verify tone and context before paraphrasing for clients. Prefer quoting patterns, not copying text, unless rights and forum rules allow.",
          },
        ],
        prAgencyUse: (
          <p className={p + " " + muted}>
            Drop the three cards straight into a <strong className={strong}>weekly status doc</strong>: Card 1 for the cover email, Card 2 for the issues slide, Card 3 for content/editorial. For <strong className={strong}>fast-moving meme or viral Reddit</strong> narratives, also check <strong className={strong}>Social → Reddit trending</strong> — this digest is broader and more theme-stable. If the panel says “No digest yet,” run forum (and Reddit) ingestion, then use <strong className={strong}>Run scheduled job</strong> or Recompute.
          </p>
        ),
      },
      {
        sectionTitle: "Entity filter, mentions table & topics",
        whatItIs: (
          <p className={p}>
            <strong className={strong}>Entity filter</strong> narrows <strong className={strong}>Recent forum mentions</strong> and <strong className={strong}>Topics by traction</strong> to threads where that brand (or configured alias) was detected. It does <strong className={strong}>not</strong> change the unbranded theme digest at the top — that block is intentionally market-wide.
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li>
              <strong className={strong}>Mentions count</strong> — Number of matching rows in the last 14 days for your filter (approximate pulse for that brand on forums).
            </li>
            <li>
              <strong className={strong}>Topics by traction</strong> — Aggregated topic labels with mention counts and sample titles; good for “what themes attach to our name on forums.”
            </li>
          </ul>
        ),
        controls: [
          {
            name: "Entity filter",
            howToUse:
              "Type a brand or alias (e.g. Zerodha, Sahi), then click Refresh to reload mentions and topics. Leave empty to see all forum mentions in range.",
          },
          {
            name: "Refresh",
            howToUse:
              "Reloads the mentions list and topics table from the API using the current entity filter. Does not rebuild the theme digest — use Recompute now / Run scheduled job for that.",
          },
        ],
        prAgencyUse: (
          <p className={p + " " + muted}>
            For <strong className={strong}>account teams</strong>: set the client name, refresh, scan Recent mentions for escalations, and use Topics by traction in the weekly call. For <strong className={strong}>new business</strong>: leave the filter empty to sample overall forum noise, then use the top PR pack for category thought leadership.
          </p>
        ),
      },
    ],
  },

  "/social/narrative-shift": {
    title: "Narrative Shift Intelligence",
    summary: "Emerging narratives from YouTube, Reddit, and news (72h). Run backfill to populate.",
    sections: [
      {
        sectionTitle: "Narrative Shift",
        whatItIs: (
          <p className={p}>
            Detects narrative clusters from API-fetched content (YouTube, Reddit, news). Charts show engagement, platform distribution, top influencers; the table lists topics with pain points and recommended Sahi messaging.
          </p>
        ),
        howToInterpret: (
          <ul className={ul}>
            <li><strong className={strong}>Narrative engagement</strong> — relative volume per cluster.</li>
            <li><strong className={strong}>Platform distribution</strong> — share by source.</li>
            <li><strong className={strong}>Sahi messaging</strong> — LLM-suggested talking points for the app.</li>
          </ul>
        ),
        controls: [
          { name: "Backfill script", howToUse: "Run: python backend/scripts/run_narrative_shift_backfill.py (in backend container) to populate data." },
        ],
        prAgencyUse: (
          <p className={p + " " + muted}>
            Use for weekly narrative briefs and content strategy. Messaging column suggests angles for Sahi.
          </p>
        ),
      },
    ],
  },
};

export function getPageHelp(pathname: string): PageHelp | null {
  const normalized = pathname?.replace(/\/$/, "") || "/";
  if (PAGE_HELP[normalized]) return PAGE_HELP[normalized];
  if (pathname && PAGE_HELP[pathname]) return PAGE_HELP[pathname];
  return null;
}
