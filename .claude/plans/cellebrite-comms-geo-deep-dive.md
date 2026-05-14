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
