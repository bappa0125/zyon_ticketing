# Phase 1 — Media Intelligence Feed: UI Structure & Implementation

## Goal

One page that acts as the **Media Mentions Feed**: a single place where the user can pick a client/entity and see all recent mentions (headline, source, date, snippet, link, and whether the mention is verified or unverified). Useful for quick scanning and deciding what to read or share.

---

## Page Location & Entry

- **Route:** `/media-intelligence` (new page; keep existing `/media` as-is for now).
- **Nav:** Add **“Media intelligence”** (or “Media mentions”) to the main nav; user lands on the feed.
- **Default entity:** First client from config (e.g. Sahi), or “Select a client” until one is chosen.

---

## UI Structure (Top to Bottom)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  [← Chat]  [Clients]  [Media]  …                                        │  ← existing nav
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Media intelligence                                                     │
│  Recent mentions for your tracked companies. Verified = full article    │
│  fetched; unverified = headline and snippet only.                        │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Client / entity    [Sahi ▼]     [Verified only ☐]  [Refresh]     │   │  ← controls
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Showing 12 mentions (8 verified, 4 unverified)                         │  ← summary strip
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ [Verified]                                                        │   │
│  │ How to Approach Sonic Automotive Stock Post Q4 Earnings?         │   │  ← card 1
│  │ TradingView · Mar 11, 2026                                        │   │
│  │ Summary snippet here…                                             │   │
│  │ Read article →                                                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ [Unverified]  ℹ headline/snippet only                             │   │
│  │ Price-Driven Insight from (SAH) for Rule-Based Strategy         │   │  ← card 2
│  │ Stock Traders Daily · Mar 11, 2026                                │   │
│  │ Snippet text…                                                     │   │
│  │ Publisher link unavailable (content fetch blocked)                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│  …                                                                      │
│                                                                         │
│  (empty state) No mentions for this entity. Try another client or run   │
│  monitoring.                                                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Section-by-Section

### 1. Header

- **Title:** “Media intelligence” (or “Media mentions”).
- **Subtitle (one line):**  
  “Recent mentions for your tracked companies. Verified = full article fetched; unverified = headline and snippet only.”
- **Breadcrumb / back:** Reuse existing pattern: “← Chat”, “Clients”, “Media”, etc., so the page fits the rest of the app.

### 2. Controls bar

- **Client / entity selector**
  - **Type:** Dropdown (or single select) populated from `GET /api/clients` (same as Clients page).
  - **Options:** Each client’s `name` (e.g. Sahi, then later more). Optionally append “(+ N competitors)” in the label if useful.
  - **Default:** First client, or empty “Select a client” with feed empty until selection.
  - **On change:** Refetch feed for selected entity.

- **“Verified only” toggle (optional for Phase 1)**
  - Checkbox: “Verified only”. When checked, filter feed to `mention_confidence === "verified"` (client-side or server-side).
  - **Tooltip/label:** “Only show mentions where we could fetch the full article.”

- **Refresh**
  - Button: “Refresh”. Refetches feed for current entity (no cache-bust needed if API is real-time).

### 3. Summary strip

- **Text:** “Showing N mentions (V verified, U unverified).”
  - If all verified: “Showing N mentions (all verified).”
  - If all unverified: “Showing N mentions (headline/snippet only).”
- **Placement:** Directly below controls, above the feed. Keeps the user informed without clutter.

### 4. Feed (card list)

- **Layout:** Vertical list of **cards** (not table), one per mention. Cards are easier to scan when each item has headline + source + date + snippet + link.
- **Order:** Newest first (by publish time).

**Per card:**

| Element        | Content / behavior |
|----------------|--------------------|
| **Badge**      | “Verified” (green/success) or “Unverified” (amber + optional tooltip: “Article body could not be fetched; based on headline and snippet.”). |
| **Headline**   | Bold, single line (truncate with ellipsis if long). If `link` is present: clickable → open article in new tab. If no link: plain text; do not make it look clickable. |
| **Source · Date** | One line: e.g. “TradingView · Mar 11, 2026” (source + formatted publish time). |
| **Snippet**    | 1–2 lines of summary/snippet; muted color. Truncate if long (e.g. 200 chars). |
| **Link line**  | If `link`: “Read article →” (opens in new tab). If no link: show `url_note` text (e.g. “Publisher link unavailable (content fetch blocked)”) in muted, smaller font. |

- **Spacing:** Comfortable padding between cards; subtle separator or shadow so cards are distinct.
- **Loading:** Skeleton cards (same structure, placeholders) or a single “Loading…” block.
- **Empty state:** When `items.length === 0`: “No mentions for this entity. Try another client or run monitoring.” (No table; friendly message.)

### 5. No pagination in Phase 1

- Single page of results (e.g. top 50). “Load more” or pagination can be Phase 2.

---

## Data Shape (API → UI)

Backend returns a list of **feed items**. Suggested shape:

```ts
interface MediaMentionFeedItem {
  id?: string;              // optional stable id (e.g. url_hash or _id)
  headline: string;
  source: string;           // publisher / source_domain
  publish_time: string;     // ISO or formatted
  snippet: string;
  link: string;             // empty if unavailable
  url_note?: string;        // when link empty, e.g. "Content fetch blocked..."
  mention_confidence: "verified" | "unverified";
  entity?: string;          // optional, for multi-entity views later
  type?: string;            // optional: "article" | "forum"
}
```

- **Verified:** `mention_confidence === "verified"` and `link` set when possible.
- **Unverified:** `mention_confidence === "unverified"`; show `url_note` when `link` is empty.

---

## How to Implement (Step-by-Step)

### Backend

1. **New endpoint: `GET /api/media-intelligence/feed`**
   - **Query params:**  
     - `entity` (required): e.g. `Sahi`.  
     - `limit` (optional, default 50, max 100).
   - **Logic:**
     - Query **entity_mentions** by `entity` (case-insensitive); get title, source_domain, published_at, summary, url, url_note, type.
     - Optionally join or query **article_documents** by `entities` containing that entity; get title, summary, published_at, url, url_resolved, url_note, article_text.
     - **Dedupe** by normalized url (or url_hash) so the same article doesn’t appear twice.
     - For each item set **mention_confidence:**  
       - “verified” if from article_documents with non-empty `article_text` and no `url_note` (or from entity_mentions with url and no url_note).  
       - “unverified” otherwise (metadata-only or fetch failed).
     - Sort by **published_at** (or fetched_at) desc.
     - Slice to `limit`.
   - **Response:** `{ "items": MediaMentionFeedItem[] }` with headline, source, publish_time, snippet, link, url_note, mention_confidence (and optional entity, type).

2. **Reuse clients**
   - Feed page uses existing `GET /api/clients` for the entity dropdown; no new API.

### Frontend

3. **New page: `app/media-intelligence/page.tsx`**
   - Title “Media intelligence” and subtitle as above.
   - Breadcrumb links: Chat, Clients, Media, etc. (same as other pages).
   - State: `entity` (string), `items` (feed items), `loading`, optional `verifiedOnly` (boolean).
   - Load clients once (useEffect), set default entity to first client or “”.
   - When `entity` is set, call `GET /api/media-intelligence/feed?entity=...` and set `items`.
   - Controls: dropdown for entity (from clients), optional “Verified only” checkbox, Refresh button.
   - Summary strip: compute from `items` (total, verified count, unverified count).
   - Render feed: map `items` to cards (filter by `verifiedOnly` if needed).

4. **New component: `components/MediaMentionsFeed.tsx`**
   - Props: `items`, `loading`, `verifiedOnlyFilter?: boolean`.
   - Renders:
     - Loading: skeleton cards or “Loading…”.
     - Empty: “No mentions for this entity…”.
     - Otherwise: list of **mention cards**.
   - **Sub-component or inline: `MentionCard`**
     - Props: one `MediaMentionFeedItem`.
     - Renders: badge, headline (link or text), source + date, snippet, link line (Read article or url_note).

5. **Nav**
   - In `layout.tsx`, add link “Media intelligence” (or “Media mentions”) pointing to `/media-intelligence`.

### Styling

6. Reuse existing patterns: `bg-[var(--background)]`, `text-zinc-100` / `zinc-400`, `border-zinc-800`, rounded cards, dark theme. Badge: small pill — e.g. green for Verified, amber for Unverified. Keep typography and spacing consistent with Media/Clients pages.

---

## What the User Gets

- **One place** to see “what’s being said” about a chosen client (e.g. Sahi).
- **Clear trust signal:** verified vs unverified so they know when the full article was fetched.
- **Quick scan:** headline, source, date, snippet, and one clear link or explanation when the link is missing.
- **Same data** that backs chat/mention search, so the experience is consistent and useful for daily monitoring.

This structure keeps Phase 1 simple, scannable, and ready to extend later with AI summary, trend chart, or top publications on the same page.
