# Cellebrite Comms + Geo — Deep-Dive & Design Plan

**Status:** Draft for discussion. No code yet.
**Inputs:** Team conversation notes (May 11), 5 Cellebrite Reader screenshots (Extraction Summary, Chats, Contacts, Device Locations, Emails), current code map, Cellebrite PA/Pathfinder online research.

---

## 0. The honest baseline

Before designing anything new, the constraint is real:

- One phone's `report.xml` = **3 GB**.
- Total extraction = **9 GB zipped, ~150 GB unzipped**.
- A single case had **164,000 evidence rows** (hence commit `4eee7ed`).
- Browser memory ceiling: ~1.5 GB usable JS heap on a desktop tab; ~500 MB on mid-tier devices.
- Neo4j on the deploy box has no published RAM tier in this repo, but team flagged "may need to upgrade RAM."

The right strategy is **NOT** to make the browser hold more, it's to make the server slice better and the UI ask for less. Cellebrite Reader itself doesn't load 3 GB into the UI — it streams from a local SQLite/proprietary store, paginating every visible region. We need to do the same against Neo4j.

---

## 1. What Cellebrite Reader does that we don't (from screenshots + research)

Three patterns appear in **every** screenshot — these are non-negotiable conventions:

**A. Persistent right-rail detail pane, not a slide-over drawer.**
Reader keeps a thin right column with a stack of **collapsible accordions** (Conversation / Details / Attachments / Participants / Sources / Notes). Selection on the left/center updates the rail in place. No modal, no drawer, no scroll-back. Today we use a slide-over `EventDetailDrawer` that hides the list — that's a context-switch every time.

**B. Histogram scrubber lives ABOVE the table on every artifact view.**
Same exact widget across Chats, Contacts, Locations, Emails. We already have `TimelineScrubber.jsx` in Comms — it should be lifted to a tab-level component used in **every** Cellebrite tab.

**C. Bottom status bar with persistent counts.**
"Total: 8497 / Displayed: 8497 / Selected: 0" — always visible. Solves the recurring "is this all of it?" question. Today we surface "showing N of M" in some places but not consistently.

Other Reader/Pathfinder-specific patterns worth taking:

| Pattern | Reader/PA | Us today | Worth adopting? |
|---|---|---|---|
| **Conversation View** (renders chat as the user saw it on the device) | ✅ Bubbles + thread, exactly like the device | ✅ `CommsMessageBubble` already does this | Already done. |
| **"Consolidated Messages" filter** (All / Only deduplications / Only non-deduplications / Only items with additional info) | ✅ | ⚠️ We dedupe but don't expose the toggle | Yes — small win. |
| **Watch List** (regex/keyword/hash list, hits highlighted across all artifact views) | ✅ | ❌ | **Yes — high value.** |
| **Carve confidence score** for locations | ✅ | ❌ (we don't carve, we only parse) | No (we parse only). |
| **Cluster Map** (zoom-aware tile clustering) on Locations | ✅ | ⚠️ We use react-leaflet-cluster; adequate | Already done. |
| **Map tile click → right rail shows all points in tile** | ✅ | ❌ (we show one event at a time) | Yes. |
| **Per-app filter** (WhatsApp / Signal / Telegram / SMS) on Comms | ✅ | ✅ `CommsAppFilter` | Already done. |
| **Per-participant filter with cross-device dedup** | ✅ | ✅ `CommsEntityFilter` | Already done. |
| **Bookmark / Tag / Add to report** on any item | ✅ | ⚠️ "Link to profile" exists; no tag/bookmark layer | Tagging is the missing piece. |
| **Pathfinder Graph View** (people ↔ devices ↔ comms graph) | ✅ separate product | We have a generic graph view | Defer — already on roadmap. |
| **Person Resolution across phone/email/username** | ✅ | ✅ `dedupeThreads`, `get_cellebrite_comms_entities` | Already done. |
| **Date-range top-of-report filter** | ✅ | ✅ scrubber | Already done. |

Sources (search): [Timeline](https://cellebrite.com/en/how-to-use-the-timeline-graph-in-cellebrite-physical-analyzer/), [Locations](https://cellebrite.com/en/blog/overview-of-cellebrite-inspectors-cluster-map-feature/), [Chats filtering](https://cellebrite.com/en/how-to-filter-chat-conversations-to-find-specific-information-in-cellebrite-physical-analyzer/), [Pathfinder graph](https://cellebrite.com/en/series/tip-tuesday/investigative-analytics-how-to-use-the-graph-view-to-find-connections-and-interactions-between-multiple-parties-in-cellebrite-pathfinder/).

---

## 2. The user's actual feedback, mapped to causes

| User said | Root cause in our code | Fix category |
|---|---|---|
| "Scrubber added but cumbersome for extensive datasets" | Scrubber covers the whole timeline regardless of data density. With 164K events, every drag re-fetches via `getBetween(limit=2000)` which round-trips — the scrubber acts like a query gun, not an index. | UI behavior + caching |
| "Timeline infinite scroll still frustrating with large data volumes" | `CommsCrossTypeTimeline` fetches `limit=2000` once, no pagination. For one busy chat with 50K messages, you literally cannot reach the bottom. Phased loading (chat→calls→emails) adds 3 round-trips before any pixels render. | Pagination + windowed fetch |
| "Server RAM may require upgrading" | Cypher queries do `SKIP/LIMIT` after `ORDER BY`, which forces full sort on huge label sets. With composite index added in `fbe8df0` it helps, but `SKIP 100000 LIMIT 50` still reads 100050 rows. | Cursor-based pagination |
| "Date filtering showing unexpected 2022 data despite newer content" | `start_date`/`end_date` are passed as strings; some comms paths compare ISO strings, others compare timestamps; mixed types give wrong results. Also the scrubber's `min/max` is computed from the loaded slice, not the case envelope. | Type-correctness + envelope query |
| "Avoid symbols like slashes in search queries" | `cellebriteSearch.js parseQuery` doesn't escape regex metachars before client-side substring matching, and the server `CONTAINS` operator can match too eagerly. | Search input sanitisation |
| "Request size potentially capping at 5,000 records affecting date range" | `get_cellebrite_events` per-type cap = 5000. If a busy event type spans 3 years and gets capped, the scrubber shows the wrong "earliest". | Two-phase fetch (envelope vs. content) |
| "Browser limitations prevent smooth navigation of massive datasets" | We render `1× ROW_HEIGHT` virtual list but inside a single React tree with O(n) state. For 50K rows, even idle re-renders sting. | Off-thread parsing + leaner state |
| "150 GB / 9 GB zip / 3 GB single XML" | We `iterparse` constant-memory in ingestion ✅, but ingestion is single-threaded; the `decodedData` pass is the long pole, no progress per category. | Phased ingestion + "skip files" mode |
| "Create ingest without files mode" | `ingestion.py` always invokes `file_linker` to hash + register every media file — 100K+ small file hashes per phone. | Add `link_files=False` flag |
| "Compare platform results against Cellebrite to identify discrepancies" | No automatic count reconciliation between our parsed counts and Cellebrite's reported `<itemCount>` per modelType. | Add reconciliation report |
| "Location/address search if data exists" | Locations have `latitude`/`longitude` but no `address` or `place_name` field; nothing geocodes them. | Reverse-geocode at ingestion (offline) or on-demand |
| "Test cross-device overlap detection" | Intersection panel exists in `CellebriteEventCenter` but uses simple radius/time threshold; no precision/recall metrics. | Add a synthetic-data test harness |
| "Whisper transcript field may not be captured" | Out of scope for Comms/Geo deep dive — note for later. | — |
| "GPT-5.5 for robust summaries" | Out of scope. | — |

---

## 3. The two big areas — design proposals

### 3A. Comms Timeline / Feed

Current architecture (refresher):
- `CellebriteCommsCenter` does **3 sequential fetches** (chat, calls, emails), waits ~2× longest stage.
- `CommsCrossTypeTimeline` does **1 fetch up to 2000 mixed items**, virtualizes with fixed 28 px rows.
- `CommsThreadView` does **1 fetch per opened thread** with `limit=500`, no infinite scroll inside the thread.
- `TimelineScrubber` operates on whatever the current slice is, not the case envelope.

#### Proposed changes

**P1. Two-phase fetch — envelope first, content second.**
- New endpoint: `GET /cellebrite/comms/envelope?case_id&report_keys&from_keys&to_keys&types&apps`
- Returns `{ min_ts, max_ts, total_count, type_counts: {chat: N, calls: N, emails: N}, hist: [{ts_bucket, count}, ...] }` — one cheap aggregation query, no item rows.
- Frontend renders the scrubber + tab-counts + estimate **before** any rows arrive.
- Then the body fetch is just one window (`start_date`/`end_date` from the scrubber selection) capped at, say, 500. Way fewer rows downloaded; way more accurate scrubber.

**P2. Cursor-based pagination, drop SKIP/OFFSET.**
- Today: `SKIP $offset LIMIT $limit` → reads `offset+limit` rows, costly past page 5.
- Switch to keyset: `WHERE n.timestamp < $cursor_ts ORDER BY n.timestamp DESC LIMIT $limit` → constant cost per page.
- API change: `getBetween` returns `{items, next_cursor}`; frontend infinite-scrolls by appending pages.
- Composite index added in `fbe8df0` already supports this.

**P3. Single combined query per "fetch phase," not three.**
- Today: 3 round-trips for chat/calls/emails. Cypher can do this in one with `UNION ALL` over the three labels, then a single ORDER BY + LIMIT outside. One round-trip = 60 % less wall time on slow links.
- Caveat: keeping per-type caps may still want them as separate sub-queries — but unioned in one transaction.

**P4. Stop loading full thread for thread-list.**
- `getThreads()` currently materialises participant lists + first/last message preview server-side. For 200 threads that's hundreds of OPTIONAL MATCHes.
- Split into `getThreads()` (just IDs + metadata) + `getThreadPreviews(ids[])` called only for the visible window in the thread list. Same pattern as Gmail's `messages.list` + batched `messages.get`.

**P5. Scrubber that's always honest.**
- Today: scrubber min/max comes from loaded slice → if you load a 5000-row cap, the scrubber thinks data ends in 2024 even though it goes to 2026.
- After P1 envelope endpoint, scrubber min/max comes from the envelope (cheap). Histogram buckets too.
- Add a thin "loading…" stripe across un-fetched zones so the scrubber visibly distinguishes "no data" from "not yet fetched."

**P6. Persistent right-rail detail pane (Reader pattern) — universal across Cellebrite tabs.**
- Lift to a **shell-level component** in `CellebriteView`, not Comms-scoped.
- Works on every tab: Comms, Events, Locations (new), Overview, Timeline.
- Single `selectedEntity` piece of state per case; each tab dispatches `selectEntity({type, id})` instead of opening its own drawer.
- Type-aware accordion renderers: Conversation / Call / Email / Location / Contact / Device-event / Generic — chosen by node label.
- **Collapsible** for screen space, with collapsed icon strip showing the current selection's type icon. Width: ~360 px expanded, ~48 px collapsed.
- Collapsed state persists in `localStorage` keyed by `case_id`.
- Replaces `EventDetailDrawer` slide-over within Cellebrite tabs. Other call sites (Workspace, Profile drawer, Process Evidence) keep their current drawer behavior for now.

**P7. Watch List.**
- New page-level construct: a list of regex/keyword/hash entries the user maintains per case.
- Backend: when a Watch List entry is added/removed, run a single Cypher pass that tags matching nodes with `:Watched` + `watch_list_hits[]`. Cheap because it uses the new indexes.
- Frontend: every Comms row, Event row, Location row that is `:Watched` shows a small pill with the matched term. Filterable as `watched:true` operator.

**P8. Search input fixes.**
- `parseQuery`: strip `/`, `\`, `^`, `$`, `(`, `)`, `[`, `]`, `{`, `}`, `*`, `+`, `?` from raw terms before tokenising, OR honour them inside quoted phrases only.
- Server `search_cellebrite_comms_messages`: lowercase compare both sides; escape `%` and `_` if we ever switch to LIKE.

**P9. "Show consolidated" toggle.**
- Pill toggle: All / Only deduplicated / Only non-deduplicated / Only items with attachments / Only items with body. Maps to existing dedup logic + simple property predicates.

#### Effort sketch (no time estimates — just relative cost)

- P1 envelope: medium (new endpoint + new hook on the front).
- P2 cursor: medium (every paginated endpoint + every infinite-scroll caller).
- P3 union: small (one Cypher rewrite).
- P4 split list/preview: medium.
- P5 honest scrubber: small after P1.
- P6 right-rail: medium (UI rewrite of one component, no backend).
- P7 watch list: large (new model + new page + cross-cutting render).
- P8 search sanitisation: small.
- P9 consolidated toggle: small.

---

### 3B. Geo / Locations

Current architecture (refresher):
- `CellebriteEventCenter` is the only place locations show up — mixed with calls, messages, etc.
- Fetches per-type, capped at 5000 each.
- `EventMapPanel` renders all geolocated events with `react-leaflet-cluster`, no per-tile right rail.
- `Location` and `CellTower` graph nodes hold `lat/lng/timestamp/source_app` but no `address`, no `accuracy`, no `confidence`.
- Tracks endpoint `getTracks` returns per-device polylines.
- No "Locations" tab — it's buried inside Events.

#### Proposed changes

**G1. A dedicated Locations tab.**
- Reader has it. We bury locations inside Events. With 164K events, the locations get drowned. Promote to a top-level tab with the same map+table+rail layout the Reader screenshot shows.

**G2. Tile-bucket aggregation server-side.**
- New endpoint: `GET /cellebrite/locations/tiles?case_id&zoom&bbox&start_date&end_date`
- Returns `{ tiles: [{tile_id, lat, lon, count, top_apps: []}], total }` aggregated by quadkey at the requested zoom.
- Frontend asks the server for the **summary** at the current zoom/bbox, not raw points. Only when zoom ≥ 15 does it ask for raw points.
- This is exactly how Mapbox/Tableau handle 100K+ points: aggregate at the tile level, drill into points only when the user zooms in.

**G3. Tile click → right rail with tile contents.**
- When user clicks a cluster, fetch `GET /cellebrite/locations/in-tile?tile_id&start_date&end_date&limit=200`, populate the right rail with a paginated list of locations in that bucket (Service, Date, Type, Name, Address, Lat, Lon, Distance, Accuracy).
- Reader does this verbatim.

**G4. Reverse geocoding (offline-first).**
- Add a build-time step that downloads the Nominatim/OSM dump for the regions the case touches; reverse-geocode each `Location` node at ingestion, store `address`, `country`, `admin1`, `admin2`, `place_name`.
- Fallback for rural points: cell-tower MCC/MNC → carrier + country. Already in `CellTower` node.
- Without this, free-text "show me messages near London" is impossible.

**G5. Address / place search.**
- New search operator: `place:london` / `near:51.5,-0.1,5km`. Resolved via the new `address` field (G4) for `place:` and a Cypher distance predicate for `near:`.
- For `near:`, use `point({latitude, longitude})` and `point.distance` — Neo4j 5 supports this natively.

**G6. Confidence + accuracy fields propagated through ingestion.**
- Cellebrite XML carries `<accuracy>` and (for carved locations) a confidence value. Currently dropped.
- Add `accuracy_meters` and `confidence_score` to the `Location` node. Render as a faint halo radius on the map — wide for low-confidence cell-tower points, tight for GPS fixes.

**G7. Cell-tower triangulation.**
- Today every CellTower point is a single dot. With multiple consecutive towers within minutes, a triangulated centroid (or arc intersection) is more useful.
- Server-side: when you fetch tracks, include cell-tower triangulation segments — a polyline from tower-A to tower-B with timestamp band.
- Out of scope for V1 of this work; flag for V2.

**G8. Geofence intersection (cross-device).**
- We already have an "Intersection Panel" that finds overlapping events. Extend it: define a geofence (drawn on the map) and ask "which devices were inside this fence between dates X and Y."
- Output: ranked list of device + count + time-density mini-histogram. Drill-in opens those locations in the right rail.

**G9. Map state persistence per case.**
- After tab-keep-alive in `fbe8df0`, the map keeps state across tab switches. But cross-session (refresh) it forgets. Persist `bbox`, `zoom`, `playheadTime`, `activeEventTypes` to localStorage keyed by `case_id`.

#### Effort sketch

- G1 tab: small (lift existing components).
- G2 tile aggregation: medium (Cypher + endpoint + frontend hook).
- G3 right-rail tile contents: small after G2.
- G4 reverse geocode: medium-large (offline data, ingestion step, schema change).
- G5 search operators: small after G4.
- G6 confidence/accuracy: small (parser + schema + render).
- G7 triangulation: defer.
- G8 geofence intersection: medium.
- G9 persist map state: trivial.

---

## 4. Scaling — the strategic answer

The team's instinct ("upgrade RAM, chunk XML, ingest without files") is right but not enough on its own. Here's the layered defence:

**L1 — Don't ingest what you don't need (unblocks today).**
- New flag: `link_files: bool = True` on `cellebrite_ingestion.run(...)`. When false, skip `file_linker.run()` entirely. Result: ingestion of a 9 GB extraction drops from O(file_count × hash) to O(XML stream).
- Surface in UI as "Ingest XML only — link files later." User can re-run with `link_files=True` once they know which artifacts they care about.
- Estimated win: 60–80 % time + 90 %+ I/O off the ingestion path on big phones.

**L2 — Phased ingestion with per-category progress (today's pain).**
- Today: parser streams `decodedData` linearly; the server says "processing…" for 20 minutes with no breakdown.
- Refactor: emit a `category_started` / `category_completed` event for each `modelType` block. Frontend shows a checklist: ✅ Contacts (8497), ✅ Calls (1240), ⏳ InstantMessage (12 / ~80 000), ⏳ Location, …
- No throughput change but huge perceived-progress improvement, and easier to spot which category is misbehaving.

**L3 — Reconciliation report.**
- After ingestion, write a `cellebrite_ingest_report.json` next to the report folder containing `{modelType, xml_count, persisted_count, skipped_count, errors[]}`.
- Surface at the top of the Cellebrite tab as a banner if any `persisted < xml_count`. Lets the team confirm "we got everything Cellebrite saw" before doing analysis. This was the user's exact ask: *"Compare platform results against Cellebrite to identify discrepancies."*

**L4 — Cypher under SKIP/LIMIT discipline.**
- Already partly addressed by `fbe8df0` indexes.
- Finish: convert all paginated endpoints to keyset cursors (P2 above). Stop sorting full label sets per page.

**L5 — Server-side tile aggregation for geo (G2).**
- 100K location points = ~12 MB JSON if we send them all. Tile-aggregated at zoom 6 = ~5 KB. Same data, 2400× smaller.

**L6 — Off-thread response parsing.**
- Move JSON parse for big responses (`>1 MB`) into a Web Worker. The 200 ms blocking parse on the main thread is what creates the "stutter" feeling, even when the network is fine.

**L7 — RAM upgrade, last resort.**
- Only after L1–L6 are in. The point of L1–L6 is to make a 4-GB box adequate, not to need 64 GB. If we do upgrade, push the headroom to Neo4j page cache (`dbms.memory.pagecache.size`), not the OS.

---

## 5. Where I'd start (proposed sequence — for discussion)

A short, ordered shortlist that delivers visible improvement at each step and unblocks the next.

**Phase A — make the data honest (foundation):**
1. Reconciliation report (L3). Tells us where we already have parser bugs.
2. Fix the date-filter bug (`start_date`/`end_date` type coercion). Single source of truth for date comparisons.
3. Sanitise search (P8). Removes the slashes/symbols footgun.
4. Persistent counts in status bar across all tabs (Reader pattern).

**Phase B — make the comms feed scale:**
5. Envelope endpoint (P1) → honest scrubber (P5) → cursor pagination (P2).
6. Single-query union for thread fetch (P3).
7. Right-rail detail pane (P6).

**Phase C — make geo first-class:**
8. Dedicated Locations tab (G1).
9. Tile aggregation + tile-click rail (G2 + G3).
10. Confidence/accuracy through the parser (G6).

**Phase D — quality of life:**
11. Watch List (P7).
12. Reverse geocode + place search (G4 + G5).
13. Geofence intersection (G8).
14. Off-thread parsing (L6).

**Phase E — heavy lift only if needed:**
15. Ingest-without-files mode (L1).
16. Phased ingestion with checklist (L2).

I'd ship Phase A and B together as the V1 of this work. Phase C as V2. Phase D and E if/when the user signal demands.

---

## 6. Open questions for the user

1. **Are deleted/carved messages important?** Reader exposes `deleted_state`. We store it (`deleted_state: "Intact" | "Deleted" | "Trash"`) but don't filter on it anywhere. Should there be a "show deleted only" toggle?
2. **Watch List scope.** Per-case, per-investigator, or shared across the org?
3. **Reverse-geocoding source.** OK to pull a one-time OSM dump (~50 GB compressed for global, smaller per-region), or do you want a hosted service? Self-hosted Nominatim is the boring-correct answer; Google Maps Geocoding API is fast but per-call cost adds up at 100K points.
4. **"Ingest without files" — UI placement.** Toggle on the upload page, or always-XML-first then a "link files now" button later?
5. **Right-rail vs. drawer.** ✅ Resolved — universal rail across all Cellebrite tabs, collapsible. Implemented in P6.
6. **Synthetic test phones.** The two-overlapping-phones test the team mentioned — should I generate them as XML fixtures we can re-ingest (best for repeatability), or scaffold them directly as Cypher?

---

## 7. What I'd defer / decline

- **Pathfinder-style graph view** for comms is already on the roadmap as the generic graph; not a Cellebrite-specific build.
- **Carved location confidence** (Cellebrite's PA does carving from raw memory). We parse a parsed file — we can't carve. Don't fake a confidence score we didn't compute.
- **"Conversation View as the user saw it"** including full theme/wallpaper. Users like it but it's cosmetic; the bubble rendering we have is enough.
- **GPT-5.5 / model routing** — separate workstream, deferred per user.

---

## 8. Risk register

| Risk | Mitigation |
|---|---|
| Right-rail rewrite breaks current "Link to profile" flows | Keep the slide-over as a fallback for items not in Comms tab; only flip Comms first. |
| Cursor pagination breaks the "show all 50K rows" muscle memory | Add a visible "Load more" + "Loaded N of M" so users know there is more. |
| Tile aggregation hides outliers (one rare point inside a busy tile) | At zoom ≥ 13 always switch to raw points; show a small "+N more" badge on tiles. |
| Watch List can be misused (everyone's name watched) | Soft limit + per-case scope; "watched" pill never replaces the underlying record. |
| Reverse geocoding adds a heavy ingestion dependency | Make it optional — only run when the toggle is on or for a specific date window. |
| Ingest-without-files mode produces orphaned attachment refs | Show a clear "attachment available — click to link files" placeholder; never hide the ref. |

---

## 9. Phase F — UX polish (added 2026-05-13 from user feedback during deploy testing)

Three small asks raised after the perf chain shipped + while looking at OPDMD28 in the browser. None of them are deep work; they're isolated UX/scaling fixes.

### F1. Locations tab — blank map bug

**Symptom (observed):** Locations table shows aggregated tile rows (e.g. 678/159/102/55/32/23 locations) but the map area above is blank — no markers, no base tiles, just empty white.

**Root cause:** `EventMapPanel`'s `BoundsFitter` fits once on first paint then sets `fitted.current = true`, blocking re-fits. When `tiles` arrives *after* the first paint (the common case — fetch is async), the bounds-fit window has closed and Leaflet stays at its `center=[0,0]` zoom 2 default, but with a container that may have measured 0 height while the parent flex was still settling. `VisibilityInvalidator` only fires `invalidateSize()` on `isActive` flips, not on initial mount when `isActive` was already true.

**Fix:**
- `BoundsFitter`: re-fit whenever `events.length` transitions from 0 → N. Track `lastCount` instead of a one-shot `fitted` flag.
- `VisibilityInvalidator`: also call `invalidateSize()` on every `events.length` increase (Leaflet caches container size; needs a kick after late data arrival).

**Scope:** Edit `frontend/src/components/cellebrite/events/EventMapPanel.jsx` only. No backend, no API change.

### F2. Collapsible workspace left menu in Cellebrite

**Anchor:** `WorkspaceView.jsx:553-569`. The `<div className="w-80 ...">` wrapping `CaseContextPanel`.

**Approach:**
- Add `const [leftCollapsed, setLeftCollapsed] = useState(false)` (per-session, not persisted — matches the rail's behaviour).
- When `selectedSection === 'cellebrite'`, render either:
  - `w-80` panel + chevron-left button in its top-right corner to collapse, OR
  - `w-8` strip with chevron-right button to expand.
- Toggle button only renders in Cellebrite mode — graph/table/timeline users get no behaviour change.

**Scope:** Edit `frontend/src/components/WorkspaceView.jsx` only. No backend.

### F3. Rail shows related conversations + events for clicked message/call

**Use case (from user):** Clicking a Telegram message or a phone call in the timeline/comms feed should surface, in the right rail:
1. **Conversation thread** — the surrounding messages in the same thread (sender ↔ recipient pair, ±N before/after the clicked event).
2. **Around this time** — other comms (calls/messages/emails) between the SAME parties within ±24h of the clicked event.

**Backend:**
- New endpoint `GET /api/cellebrite/events/{node_key}/related?case_id=...&window_h=24&limit=50`.
- New `Neo4jService.get_event_related(case_id, node_key, window_h, limit)`:
  - Resolve event's sender + recipient(s) via the same per-label OPTIONAL MATCH used in `get_cellebrite_event_detail`.
  - **Thread branch:** if the event has a thread/conversation key (Telegram/WhatsApp/SMS messages do; calls/emails fall back to party-pair), MATCH siblings ordered by timestamp.
  - **Around branch:** MATCH PhoneCall/Email/Communication where both parties match (in either direction) AND `date` ± window_h covers the event's timestamp.
  - Return `{ thread: [event-rows], around: [event-rows] }`. Project the same shape `EventBody` already consumes.

**Frontend:**
- `EventAccordion`: after the existing detail load, fire a second fetch for `/related`. Render below `<EventBody>`:
  - Two collapsible sub-sections ("Conversation" — thread, "Around this time" — cross-channel pair window).
  - Each row click → `selectEntity({...})` re-publishes selection. Existing rail wiring re-renders with the new event's accordion + its own related set (so users can hop along the thread without leaving the rail).
- API helper in `frontend/src/services/api.js`: `cellebriteEventsAPI.getEventRelated(caseId, nodeKey, opts)`.

**Scope:**
- Backend: `services/neo4j_service.py`, `routers/cellebrite.py`.
- Frontend: `services/api.js`, `components/cellebrite/shared/rail/EventAccordion.jsx`.
- No schema changes — uses existing relationships.

### F4 (deferred, not in this batch). Optimisations identified during browser test

Not building yet — flagged for next pass:
- `/cellebrite/events/tracks` fired 3× during a Locations tab session (10.86s max). Likely the same React StrictMode + tab-switch double-invocation pattern we already fixed for Comms — needs the same `reportsReady` gate verification on Locations.
- `/cellebrite/locations/tiles` fired 2× from the same session — same root cause.
- `/cellebrite/events` fired 16× (max 2.2s each) — needs investigation; might be per-marker rail drilldown firing per click without a dedup guard.

These are perf, not correctness — the data does land. Park until F1–F3 ship.

---

## 10. Build sequence going forward

1. **F1, F2, F3 — Phase F** (this round). Smallest first → biggest.
2. Return to deferred items from §5: **D11 Watch List**, **D13 Geofence intersection**, **D14 Off-thread parsing**.
3. Park **F4** (extra perf passes) until user confirms the lived-in feel is acceptable.
4. **E15 Ingest-without-files** + **E16 Phased ingestion** — only when the user signal demands.

---

## 11. Phase G — Unified-by-number contacts (added 2026-05-13)

**Customer ask (verbatim):**
> all these guys have different contact names for probably some of the
> same people. Can, in the cellebrite view, connect via phone number?
> so meaning if everyone is texting 202-805-2817 we want to see the all
> the messages by number so show the number and put in parenthesis the
> different contact names used.
> example: 202-805-2817 (Alex, Boss, Solorzano, Chief Owl, Alex Cell)

**Decisions (locked in via AskUserQuestion):**

| Aspect | Choice |
|---|---|
| Placement | Both — Comms filter chip rollup + new "Contacts (unified)" tab |
| Match key | E.164-normalised phone number |
| Alias display | All aliases as wrapped chip group |
| Click behaviour | Click filters Comms feed; right-click / hover icon opens unified rail |

### G1. Backend — canonical number + rollup endpoint

- New helper `services/cellebrite/phone_normalise.py`:
  - `normalise(raw: str, default_region: str = 'US') -> str | None`
    Returns E.164 (`+12028052817`) or `None` for un-normalisable inputs
    (short codes, alphanumeric senders, app IDs).
  - Lightweight regex first; fall back to `phonenumbers` library if it's
    already a dep, otherwise stick with regex (10-digit US default,
    keep leading-+ as-is).

- New `Neo4jService.get_unified_contacts(case_id, report_keys, search, limit, offset)`:
  - One Cypher pass that gathers all Person nodes in the case (filtered
    by `report_keys` if provided), groups by canonical number, returns
    rows of:
    ```
    {
      "canonical": "+12028052817",        # null for non-phone aliases
      "display_number": "+1 (202) 805-2817",
      "aliases": [{"name":"Alex","key":"phone-...","report_keys":["..."]},...],
      "report_keys": [...],               # union across aliases
      "person_keys": [...],               # union across aliases (for filter wiring)
      "msg_count": N,
      "call_count": N,
      "email_count": N,
      "first_seen": "2026-...",
      "last_seen":  "2026-..."
    }
    ```
  - Counts come from a follow-up MATCH on the unioned `person_keys`.
  - Aliases sorted by frequency (most-used name first).

- New endpoint `GET /api/cellebrite/contacts/unified?case_id=&report_keys=&search=&limit=&offset=`.

### G2. Frontend — new "Contacts (unified)" tab

- Add to `CellebriteView.jsx` tab tree alongside Overview / Comms /
  Locations / Files / Events.
- New `components/cellebrite/CellebriteUnifiedContacts.jsx`:
  - Sortable table: number, alias chip-group, msg/call/email counts,
    first/last seen, devices.
  - Click row → publish unified-contact selection through the rail
    (right rail shows `UnifiedContactAccordion`).
  - "Filter Comms feed" button per row → switch to Comms tab with the
    union of person_keys pre-selected.

### G3. Comms entity filter — group by canonical number

- `CommsEntityFilter.jsx`: add a "Group by number" toggle (default ON).
  When ON:
  - Fetch the unified rollup (cached per case + report_keys).
  - Render each canonical row as a single chip:
    `+1 (202) 805-2817`
    with the alias chip-group below the number (small wrapped pills).
  - Selecting the chip pushes the union of `person_keys` into the
    existing comms filter.
- When OFF: behaves exactly as today (per-Person rows).

### G4. Unified rail accordion

- New `components/cellebrite/shared/rail/UnifiedContactAccordion.jsx`:
  - Header: canonical number + alias chip-group.
  - Body: per-device breakdown (phone chip + alias used on that phone +
    counts), recent comms across all aliases (uses the existing
    `/related`-style projection but anchored on the unioned key set).
- Register in `rail/index.js` against `type: 'contact_unified'`.

### G5 (deferred). Cross-channel ID unification

Not in this batch — add only if user signal demands. Would extend
G1's normaliser to also fold:
- Email addresses (when the same name + same phone aliases also share
  an email)
- App-only IDs (Telegram username, WhatsApp ID) using the existing
  Person-name overlap as a join key.

This is materially harder (false-positive risk goes up) so it belongs
behind a feature flag.

### Build sequence

1. **G1** backend (normaliser + endpoint) — must be first; everything
   below consumes it.
2. **G2** new tab — easiest win for the customer; ships a visible
   table they can browse straight away.
3. **G3** Comms filter toggle — the immediate quality-of-life win the
   customer described.
4. **G4** rail accordion — ties it together so right-click on a chip
   gives a full per-number drill-in.

---

## 12. Phase H — Resizable Cellebrite tab panes (added 2026-05-13)

**User pain:** "It's very hard to work in the messaging row even with
the Conversation timeline minimized." The Comms Center (and other
Cellebrite tabs) stack their internal panes with fixed heights — when
the user wants to focus on the message feed, the From/To filter and
the histogram scrubber are eating space they don't need at that
moment.

**Decisions (locked in via AskUserQuestion):**
- **Scope:** all Cellebrite tabs in one pass (Comms / Locations /
  Events / Unified Contacts).
- **Persistence:** per-case localStorage. Investigators get their
  layout back when they reopen a case.

### H1. Reusable `<ResizableSplit>` primitive

`frontend/src/components/cellebrite/shared/ResizableSplit.jsx`

```
<ResizableSplit
  storageKey="cb.comms.filter.{caseId}"
  direction="vertical"          // also supports horizontal
  defaultSize={220}             // px for the "first" pane
  minSize={80} maxSize={500}
  first={<EntityFilter ... />}
  second={<MessageFeed ... />}
/>
```

- 8px draggable divider with hover affordance + grab cursor.
- `pointermove` listener on `document` while dragging — same trick the
  rail uses for its width split.
- Reads + writes `localStorage[storageKey]`. Per-case keys keep "this
  case is comms-heavy" preferences distinct from "this case is
  location-heavy".
- Companion hook `useResizablePane(storageKey, defaultSize)` for sites
  where the consumer already has its own outer flex and just wants the
  height value.

### H2. Comms Center splits

Two stacked drag handles between:
1. From/To filter ↕ Histogram scrubber + filter chips
2. Histogram scrubber + filter chips ↕ Conversation feed

Default heights: filter 220px, scrubber+chips 140px. Feed flexes.

`storageKey` shape: `cb.comms.{section}.{caseId}` so the Comms-feed
preferences for case OPDMD28 don't bleed into another case.

### H3. Locations tab split

Map ↕ table split (currently fixed `h-64` on the table). Drag handle
between map and table; same primitive.

### H4. Events Center split

Same pattern as Locations — the existing map/table split becomes
draggable.

### What we're NOT building this round (deferred)

- **Horizontal splits**: e.g. side-by-side map+table inside Locations.
  Today's vertical stack works fine; horizontal can land in a follow-
  up if someone asks.
- **Save preset layouts**: per-case is enough; saving named layouts
  per investigator is complexity we don't need until someone wants it.
- **Drag-to-fully-collapse**: the resize handles bound the panes by
  `minSize`. If users want a section gone, the existing collapse
  buttons (where they exist) handle that better.

### Build sequence

1. **H1** primitive — must come first; everything else consumes it.
2. **H2** Comms — the immediate user pain.
3. **H3** Locations — quick win, single split.
4. **H4** Events Center — same as Locations.

---

## 13. Phase I — RFC-822 email threading at ingestion (PARKED)

**Why parked, not built now:** today's "email thread" in the UI is a
synthetic per-pair grouping (everything between sender and first
recipient on this device). That's good enough to surface
conversation context — investigators stopped asking once the
ThreadAccordion landed.

**What true threading would change:**
- Parse `Message-ID`, `In-Reply-To`, and `References` headers at
  ingestion in `services/triage_processors/email_processor.py`
- Persist them on the `Email` node (already partly done — `message_id`
  is captured)
- Add `[:REPLIES_TO]` or `[:IN_THREAD]` relationships between Email
  nodes during the writer pass
- Build a `(:EmailThread)` parent node per `References` chain so the
  thread has its own identity (subject normalisation, participant
  list, message count) — same shape as `(:Communication)` thread
  parents for chats
- Update `get_thread_detail` to handle a new `thread_type='email_thread'`
  that fetches by parent reference, not by party-pair
- `get_overview_emails` would emit the real `thread_id` when the
  email belongs to one, falling back to the per-pair synthetic id
  for orphaned messages

**Effort sketch:** medium. The header parsing is the easy bit; the
fiddly part is normalising subjects (RE:/FWD: stripping) and
deduping when the same email arrives in two mailboxes (Sent + Inbox).
Risk: `References` chains can get long and noisy in real corporate
mail; need a sensible cap.

**Trigger to build:** when an investigator says "I want to see the
actual reply chain" rather than "I want to see emails between these
two parties".

---

## 14. Phase J — Complex spatial + temporal search (PARKED)

**User ask:** describe boundaries in English ("everywhere within 5km
of the Mall in DC") AND set time bounds ("between 14:00 and 16:00 on
March 3rd"), and get all matching points back.

**What we already have:**
- `place:london` — substring match on geocoded address / place_name /
  country / admin levels (Phase D `8550415`).
- `near:51.5,-0.1,5km` — radius around a centre point (Phase D).
- Date range filter (`startDate` / `endDate` query params on
  `/cellebrite/events`).
- Server-side reverse-geocoding (Phase D, optional via Nominatim or
  GeoNames).

**What's missing for the full ask:**

1. **English place → bounding shape resolution.**
   "The Mall in DC" needs a forward-geocode + a polygon (not a single
   centre). Today our `near:` is point + radius. Forward-geocoding a
   landmark via Nominatim returns a `boundingbox` and a `geojson`
   polygon — both usable.

2. **Polygon-in-Cypher matching.**
   Neo4j 5 has `point.distance` (already used for `near:`). For
   polygons we need either:
   - Server-side filtering: pull candidate points by bounding box
     first, then point-in-polygon test in Python (cheap on the
     post-bbox set, expensive on the whole case).
   - APOC `apoc.spatial.geocodeOnce` + `apoc.spatial.distance` are
     in scope but APOC isn't installed everywhere — would need to be
     a deploy prerequisite.

3. **Temporal-window combinator with spatial filter.**
   Trivial in Cypher once both inputs are typed — `WHERE
   point.distance(...) < r AND date >= $lo AND date <= $hi`. The
   harder part is the **per-day window** ("between 14:00 and 16:00
   every day") which needs a per-row time-of-day extraction.

4. **English query parser.**
   "Within 5km of the Mall in DC between 14:00 and 16:00 on March
   3rd" needs to parse into structured form. Two paths:
   - **Strict DSL**: `place:"the Mall in DC" within:5km date:2024-03-03 time:14:00-16:00` —
     extends our existing `parseQuery` token grammar. Predictable,
     no LLM, fast. Investigators learn it once.
   - **LLM-driven**: free-form English → JSON via the existing chat
     context channel. Friendlier, handles any phrasing, but
     unreliable on ambiguous inputs and needs a feedback loop ("did
     you mean X?").

5. **Map-driven boundary drawing.**
   Investigators sometimes want to draw a polygon directly on the
   map and ask "show me everything inside this." Leaflet has the
   `leaflet-draw` plugin (~30 KB). One-line add to EventMapPanel,
   raises a `drawn:created` event with the polygon's GeoJSON.

**Effort sketch (relative cost):**
- Drawn-polygon filtering (frontend Leaflet-draw + client-side
  point-in-polygon on the visible 5K cap): **small**, days.
- Forward-geocode for English place names + bbox/polygon: **medium**,
  needs Nominatim search endpoint + caching layer.
- DSL extension for time-of-day windows: **medium**, parser tweak +
  per-row filter.
- LLM-driven free-form parser: **large**, needs eval harness, fall-
  back to DSL on parse failure, telemetry to learn from misses.
- APOC-based server-side spatial in Neo4j: **large**, deploy chore.

**Proposed sequence when this gets prioritised:**
1. **J1** — Leaflet-draw polygon on map + "filter to drawn area"
   button. Fastest investigator win, no backend changes.
2. **J2** — Extend the search DSL with `time:HH:MM-HH:MM` (per-day
   time-of-day window).
3. **J3** — Forward-geocode English place names via
   `/api/cellebrite/geocoder/forward?q=...` returning `{lat, lon,
   bbox, polygon}`. Hook into `place:"…"` to support polygon match
   when the geocoder returns one.
4. **J4** — LLM English → DSL translator with the existing chat
   context. Strictly optional sugar; the DSL is the truth.

**Trigger to build:** when investigators say "I want to lasso the
crime scene on the map and see who was there between 14:00 and 16:00."


---

## 15. Phase K — Comms Center redesign (planned 2026-05-14)

**User pain (after living with it):** even with the resizable panes
shipped in Phase H, the Comms Center feels squeezed. Six rows of
header chrome (~470px) plus a ~150px bottom timeline leaves too
little room for the actual conversation feed on a 1080p laptop.

**Locked-in user decisions:**
- **All three improvement strategies together** (compact toolbar +
  Browse/Read mode + fold cross-type timeline).
- **From/To becomes Participants** with per-chip `Any | From | To`
  direction toggle, AND the panel(s) collapsible for users who want
  more space.

### K1. Participants combined filter (replaces split From/To)

Replace the two side-by-side EntityFilter panels with a single
"Participants" picker. Selection model:

```
[ + Add participant ]  [ Alex ↕ ✕ ]  [ Boss ↕ ✕ ]  [ Mom ↑ ✕ ]
```

Each selected chip carries a per-chip role:
- ↕ **Any** (default) — comm where this person is in either role
- ↑ **From** — comm where this person is the sender
- ↓ **To**   — comm where this person is the recipient

Click the role icon on a chip to cycle through the three states.

**Filter logic (server-side params):**
- All `Any` participants → unioned into a `participants:[k1,k2]`
  array; filter is `(sender IN list) OR (any recipient IN list)`.
- `From` participants → added to `from_keys` (existing param).
- `To` participants → added to `to_keys` (existing param).
- Mixed selections combine the three (AND across role groups).

The picker itself opens as a popover: searchable list of entities,
similar to the current EntityPanel content but presented once.
Collapsible: chevron button hides the filter strip entirely; chips
stay visible in compact form so the user knows what's filtered.

### K2. Compact toolbar (single row)

Collapse three current rows (Source app filter row, Type filter row,
Search bar row) into one toolbar:

```
[Search........................] [📱 Apps (3) ▾] [💬 Msg ☎ Call ✉ Email] [📊 Scrubber ▾] [⋯]
```

- **Search**: stays inline as the most-used input.
- **Apps**: dropdown popover. Counter shows "3" if 3 apps active,
  otherwise "All apps". Inside the popover: the same pill grid we
  show today.
- **Type pills**: stay visible (3 toggles, ~80px wide combined).
- **Scrubber**: collapsed to an 8px-tall density spark that expands
  to the full TimelineScrubber on click. The spark still shows the
  envelope curve at low resolution so users can see "is there a
  spike worth zooming into?" without expanding.
- **Overflow `⋯`**: dropdown for less-used controls (clear filters,
  export, etc.).

### K3. Browse / Read mode toggle

Top-level toggle in the header (next to PhoneSelector or in the
toolbar):

- **Browse mode** (default): full toolbar visible, bottom timeline
  visible. Same as today.
- **Read mode**: all filter chrome hidden. Thread list + thread
  view eat the screen. Bottom timeline hidden. Search stays as a
  thin button that expands to full search on click.

Per-case localStorage so the user's preferred mode persists across
visits to the same case.

### K4. Fold cross-type timeline into main scrubber

The bottom `CommsCrossTypeTimeline` is always-mounted, ~150px tall,
and shows tick marks for every message/call/email. Its information
isn't unique — it's a denser view of the same envelope the main
scrubber already aggregates.

Replacement: extend the main scrubber to render colored tick marks
underneath its density curve:
- Amber dots for messages
- Blue dots for calls
- Red dots for emails

Click a tick → jump-to behaviour the cross-type timeline already
provides. The dedicated bottom pane goes away entirely.

### Build order

1. **K1** — Participants filter. Biggest UX win, hardest piece.
2. **K2** — Compact toolbar. Reclaims most vertical space once K1
   has shrunk the participants section.
3. **K3** — Browse/Read toggle. Tiny code, huge perceived
   improvement. Can ship independently of K1/K2.
4. **K4** — Fold bottom timeline. Last because it touches the
   scrubber and main split simultaneously; lowest urgency once K1+K2
   have reclaimed enough space.

**Trade-offs accepted:**
- Power users who currently use the From / To split will need to
  click the role toggle on each chip instead of placing entities in
  the right column. Direction-strict filtering is rare; the cost is
  a click.
- The dropdown popovers add discoverability friction vs. always-
  visible pills. Counters next to each dropdown ('Apps (3)') and a
  visible affordance arrow mitigate this.
- Read mode hides controls — users still in Browse/Read confusion
  can hit the toggle to flip back. Esc could also exit Read mode
  for a fast-bail.

**Trigger to revisit:** if the chip-with-direction-toggle pattern
proves confusing in user testing, fall back to two collapsible
panels (Participants-Any + Participants-Strict-Direction) instead
of per-chip toggles.

