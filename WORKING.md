# WORKING.md — current task state

> Live scratchpad. Update on every meaningful step. User has flaky connection;
> on "continue" read this file and resume from **Next action**.
>
> **IDENTITY / CONTACT WORK DOC SET** (read these before any contact/identity/
> comms/perspective work — significant prior work lives here, do NOT disregard):
> - `.claude/plans/cellebrite-comms-geo-deep-dive.md` — Phase G unified-by-number
>   contacts (canonical rollup + alias chips + "one structure, two lenses").
> - `.claude/plans/alex-call-roadmap.md` — Epic 1D comms direction & identity
>   correctness + device-local alias.
> - `data/forensic_export/<C1..C9>/` — per-device EXACT contacts/aliases/comms.
> - This file's **2026-05-26 contact-conflation project** section below.
> PRINCIPLE: per-device / contact-book PERSPECTIVE is the default; keep identities
> separate, named as that phone saved them. Rollup / cross-identity "Link
> identities" is OPT-IN (default OFF), read-only, never merges data or changes
> per-device names. (Cross-identity filter shipped 2026-06-10; default corrected
> ON→OFF after user feedback.)

## 2026-06-09 — SEARCH & DISCOVERY → FULL DETAILED SEARCH ENGINE (IN PROGRESS)
User: the Cellebrite "Search & Discovery" tab is too shallow — "supposed to be a detailed search engine." Confirmed 4 problems + scope decision (Full detailed search engine + Both inline-detail AND deep-link).
- **Goal:** (a) search ALL ~31 node types w/ distinct labelled categories (today only person/message/location/Other/file; "Other" lumps 9 types, ~20 types invisible); (b) expandable result rows + in-place detail panel; (c) deep-links that land on the EXACT record pre-filtered (thread_id/evidence_id/location/node id) — teach Files/Events/Comms tabs to consume a target id; (d) fix phantom "scoped to N phones" (= default all-selected, not a real scope → use phoneCtx.allSelected).
- **Confirmed root causes (investigation done):**
  - 6-phone scope: PhoneReportsContext.jsx:108 defaults selectedReportKeys to ALL keys; CellebriteDiscovery.jsx:62 treats size>0 as explicit scope.
  - Coverage: discovery_search (neo4j_service.py:7396) composes only search_cellebrite_persons + search_cellebrite_comms_messages + router file match.
  - No expand UI: ResultGroup rows are flat (CellebriteDiscovery.jsx:317), 2 icon buttons only.
  - Pivots: only person→comms filters (via _filter_intent+person_keys). message→comms sends EMPTY person_keys (msgs carry thread_id not person_keys). file/location/resource = bare requestCellebriteTabSwitch with no target; Files/Events tabs read NO handoff.
- **Key files:** FE CellebriteDiscovery.jsx, api.js (discoverySearch ~2746); BE cellebrite.py (/discovery/search ~298), neo4j_service.py (discovery_search ~7396, search_cellebrite_persons RESOURCE_LABELS ~7171, search_cellebrite_comms_messages ~9742, get_cellebrite_events ~9900); neo4j_writer.py (node props ground truth); PhoneReportsContext.jsx (allSelected ~188); commsHandoff.js; consumers CellebriteCommsCenter/FilesExplorer/EventCenter/CrossPhoneGraph.jsx; CellebriteView.jsx (tab registry + switch listeners).
- **Plan:** 1) ground-truth node props per label → 2) BE config-driven multi-label discovery_search w/ distinct categories + node_id + detail fields → 3) BE record-detail endpoint(s) → 4) FE expandable rows + detail panel + all-type toggles → 5) FE deep-link handoff (target ids) into Files/Events/Comms → 6) fix phantom scope → 7) verify on case 43f1afb1.
- **BACKEND DONE (UNCOMMITTED, needs owl-backend restart to go live):** rewrote `neo4j_service.discovery_search` as a config-driven engine across ~32 node labels → distinct labelled categories grouped by family (Communications / People / Location / Web & Apps / Accounts & Security / Calendar & Notes / Social & Media / Device & System / Media & Files). Each item carries key, title, subtitle, timestamp, report_key, `detail`[{label,value}] (inline expand — no 2nd fetch), and deep-link ids (person_keys / thread_id+message_id / latitude+longitude / evidence_id) + `pivot` hint. People = dedicated lightweight person-only query (comm_count relevance); chat Messages = tuned search_cellebrite_comms_messages (thread-linked); all else = generic `_label_group` (diacritics-folded CONTAINS, count + bounded top-N via 2 CALL subqueries — no collect-all). Router (`/discovery/search`) file group now carries family+detail+pivot. VERIFIED in-process on case 43f1afb1: trabajo/piney/whatsapp/gmail return 4–15 rich categories, shapes correct.
- **PERF:** sequential was 13s; fanned out across a ThreadPoolExecutor (12 workers, each its own session) → ~3.5s warm. Floor is Neo4j CPU (concurrent substring scans over 561k nodes). Acceptable for thorough search; FRONTEND will be SUBMIT-based (Enter/button), not per-keystroke, to avoid firing 3.5s scans on every debounce. TRUE sub-second = Neo4j full-text indexes (standard-folding analyzer handles Spanish) — a schema change + Lucene disk/mem on the OOM-prone host ([[project_host_no_swap_oom]]) → OFFER to user as follow-up, don't add unilaterally.
- **FRONTEND DONE (UNCOMMITTED, live via Vite HMR):**
  - `CellebriteDiscovery.jsx` FULL REWRITE: submit-based search (Enter/button — not per-keystroke, since an all-types scan is ~4s), family-grouped results (9 families, colour-accented) with per-family show/hide chips + counts, every row EXPANDS IN PLACE to a key/value detail panel (fixes "can't expand"), working deep-links, fixed phantom scope (uses `phoneCtx.allSelected` → only shows "scoped to N of M phones" when the user actually narrowed; default all-selected = search everything, no scope param).
  - Deep-links (`utils/commsHandoff.js` gained generic `setDiscoveryTarget`/`consumeDiscoveryTarget` {caseId,tab,search}): people/contacts→Comms participant filter (existing `_filter_intent`); messages/emails→Comms body/subject deep-search (auto-opens thread); files→Files filename search; locations/cell-towers/journeys→Locations place search; resources→Graph. Consumers wired: `CellebriteFilesExplorer.jsx` (+isActive prop), `CellebriteLocations.jsx`, `CellebriteCommsCenter.jsx` each consume their target on activate → set searchQuery. Categories with no native home = inline detail only (honest; no misleading "open").
  - Router (`/discovery/search`): Files evidence scan now runs CONCURRENTLY with the Neo4j scan (ThreadPoolExecutor) → all-types warm ~5-6s → ~4.0s. Empty file group dropped.
- **VERIFIED:** `npx vite build` clean (all lucide icons resolve). owl-backend RESTARTED. Live HTTP E2E (case 43f1afb1, user conor@…): /discovery/search 200, 11 categories incl Media&Files (evidence_id+pivot=files), detail fields + pivots correct, diacritics fold works (Día matches dia), warm ~4.0s. `phoneCtx.allSelected` confirmed exported (PhoneReportsContext.jsx:188).
- **PERF follow-up to OFFER user:** ~4s is the floor (CPU-bound substring scan over 561k nodes). True sub-second = Neo4j full-text indexes (standard-folding analyzer = native Spanish folding) — schema change + Lucene disk/mem on OOM-prone host ([[project_host_no_swap_oom]]); don't add unilaterally.
- **S&D COMMITTED** b5a75cf + checklist/state e5479f0; PR branch `feat/cellebrite-search-discovery` pushed (open PR via GitHub URL — gh absent).

## 2026-06-09 — TESTER BUG FIXES ROUND 2 — ✅ DONE + COMMITTED c86ba68 (same branch), backend RESTARTED
Worked through ALL tester reports from the QA hub (Alex, 2026-06-09) per user's "spin up agents, work through all, don't ask until complete." Investigated via parallel Explore agents, implemented + verified:
- **user-bug-1 device-lens names** ✅ — counterparty now named as the VIEWING phone saved them (Pefro/Mry not global "Trabajo 444"). `_project_call/message/email` take optional `dcn` map; threaded into get_cellebrite_events, get_event_related, thread_detail calls/emails branch (chat already did it). VERIFIED 17/17 sampled msg counterparts match dcn; 213 numbers have >1 device-name. Phase 2 (universal label) NOT done.
- **user-bug-2 unicode search** ✅ client-side — `cellebriteSearch.normForSearch` (NFKC+diacritics+emoji/zw strip both sides). VERIFIED 𝓚𝓪𝓽𝓱𝓲𝓪🎭→kathia. Backend-vs-stylised-STORED-names = follow-up (needs normalised shadow field + backfill).
- **user-bug-3 comms timeline window** ✅ — CommsCrossTypeTimeline 33vh→100%.
- **user-feature-4 PDF export** ✅ — comms_export_service + /comms/export/pdf (reuses WeasyPrint render_pdf) + Comms Center Timeline/Conversation buttons (window.open → cookie auth). VERIFIED valid PDFs both modes; MAX_ITEMS=2000 (~20s worst single-heavy-participant, typical filtered fast).
- **tl-time-hover** ✅ EventsTable title tooltip. **media-smooth-scroll** ✅ img dims + audio preload=none.
- **dedup-collapse** → NEEDS-INFO (no clear bug; await repro). **nav-load-more-*** → WORKS in code (EventCenter load-more = follow-up).
- QA hub: round-2 `fix-*` checklist section (6 items) added; TESTING_FEEDBACK_STATE.md statuses updated. 72 checklist items total.
- **NEXT ACTION:** user in-browser verification of the round-2 fixes (esp. device-lens names isolating C5/C6; unicode search; PDF buttons). Open the PR (branch pushed). Follow-ups noted: universal labels (bug-1 P2), backend stylised-unicode search backfill (bug-2), EventCenter load-more, dedup repro.

## 2026-06-09 — QA TESTING HUB: discussion threads + tester-submitted feature/bug items + repro steps — ✅ COMPLETE (UNCOMMITTED), server live
Extends the shipped testing hub (commits ea00c17→0d655ea) with three tester-facing features. All built; I finished + verified the last uncommitted batch this session.
- **Backend (`services/testing_feedback_storage.py`):** disk shape gained top-level `comments` {item_id:[{id,author,text,created_at}]} and `user_items` [] (kept SEPARATE from the tester-keyed `items` map so a thread can't collide with a status record). New `add_comment` (append-only, attributed), `add_user_item(kind∈feature|bug,title,body,author)`, `delete_user_item` (cascades: pops items+comments). `upsert_feedback` gained `repro` field. `_empty()`/`_load()` migrate old files forward. `clear_all` resets to `_empty()`.
- **Backend (`routers/testing.py`):** `POST /api/testing/comment`, `POST /api/testing/item`, `DELETE /api/testing/item/{id}` — author always from the verified token. `FeedbackIn` gained `repro`.
- **Frontend (`static/testing-hub.html`):** right-side **discussion drawer** (per-item status snapshot across testers + chat thread; Ctrl/Cmd+Enter posts), **create feature/bug modal**, **Reproduction steps** textarea alongside Notes, kind badges, "Tester-submitted" section leading the list (newest first), per-item footer (💬 count + last-activity "Xd ago"), live in-place footer/drawer refresh on save/comment.
- **`scripts/harvest_app_events.py`:** made CASE-AGNOSTIC (`--case`, explicit paths, or all graph cases) — unrelated cleanup riding along in the same uncommitted set.
- **BUG I FIXED THIS SESSION:** the `API` object was missing `item: '/api/testing/item'` (only `comment` had been added) → create/delete posted to `undefined`. Added it. This was the one thing left incomplete.
- **VERIFIED:** py_compile clean (all 3 files); storage round-trip test (create→feedback w/ repro→comment→delete-cascade + validation rejects) passes via venv; **live E2E** against running :8000 — login neil/testing, POST item/comment, DELETE all 200 (smoke item cleaned up); served `/testing` now contains the `API.item` fix + all UI markers. Section renderer keys (`sec.h/d/items`) match the synthetic "Tester-submitted" section.
- **NEXT ACTION:** offer to commit (on a branch off main, then PR — matches the #84/#85 workflow). Frontend is served from disk (no restart needed); backend already running with the new endpoints.

## 2026-05-29 — TIMELINE "No phone events match" after restart — ✅ ROOT-CAUSED + HARDENED (UNCOMMITTED)
User: Timeline stuck on "No phone events match the current filters" + browser `net::ERR_CONNECTION_TIMED_OUT`.
- **Not a code regression.** Backend healthy; /events returns data fine. Cause: right after my owl-backend RESTART the caches were COLD — first events/envelope ~9.5s + per-type body fetches (message 7s, call 6s, email 4s, ×~17 types SEQUENTIAL) blew past the browser/proxy connection idle timeout → every per-type fetch threw → the loop's `catch` SILENTLY swallowed them → aggregated=[] → rendered the generic "No phone events match" empty state (indistinguishable from a real failure). Warm timings are fine (envelope 1.6-2s, types 1-7s).
- **FIX (CellebriteTimeline.jsx):** the fetch loop now counts errored stages; if the result is empty *because* stages errored (`aggregated.length===0 && errorCount>0`) it sets `loadFailed` → renders a "Couldn't load events — the request timed out / connection dropped" panel with a **Retry** button (bumps `reloadKey` in the fetch deps) instead of the misleading "no events" text. A real empty result (0 errors) still shows the normal empty message.
- Build clean (HMR live). Backend warm now → a reload loads the timeline.
- **NOTE:** CellebriteEventCenter has the SAME silent-swallow pattern — should get the same loadFailed/Retry treatment (not yet done). Pre-existing perf: timeline fires ~17 sequential multi-second per-type fetches; cold-load is slow by design — could parallelize/cap but out of scope unless asked.
- **NEXT ACTION:** tell user to reload (works now); optionally harden EventCenter identically; then resume the has-attachment/scrubber commit.

## 2026-05-29 — "HAS ATTACHMENT" → SERVER-SIDE (reaches past the 5000/type cap) — ✅ DONE (UNCOMMITTED), backend RESTARTED
User wanted the has-attachment filter to be a true server-side picture (past the cap), with the option to "filter list by has media or filter all by has media". Upgraded the (previously client-only) toggle to also drive the server fetches + envelopes.
- **Property:** probed live DB — `coalesce(n.attachment_count,0) > 0` ≡ `attachment_file_ids size > 0` (identical: Communication 19,526 / PhoneCall 0 / Email 44). Use attachment_count (simple, proven, doesn't error).
- **Backend `has_attachment` param added to:** `get_cellebrite_events` (+restricts active types to call/message/email + `AND coalesce(n.attachment_count,0)>0`), `get_cellebrite_events_envelope` (same), `get_cellebrite_comms_threads` (chat: `EXISTS{ (am)-[:PART_OF]->chat WHERE attachment_count>0 }` pre-cap so it reaches past cap; calls/emails: gate the aggregated items), `get_cellebrite_comms_envelope` (3 legs), `get_cellebrite_comms_between` (3 legs), `get_contact_comms_feed` (single `n` clause on item + total queries). Endpoints `/events`, `/events/envelope`, `/comms/threads`, `/comms/envelope`, `/comms/between`, `/comms/contact-feed` all take `has_attachment`. api.js: added `hasAttachment` to getEvents, getEventsEnvelope, getThreads, getEnvelope, getBetween, getContactFeed.
- **Frontend:** each view now passes `hasAttachment: hasAttachmentOnly` to its body + envelope fetch AND adds `hasAttachmentOnly` to the fetch-effect deps (so toggling refetches). The existing client-side `has:attachment` matcher injection stays as a harmless safety net + is the actual mechanism for CommsThreadView (thread detail is fully-loaded, no server param). Views: CellebriteTimeline, CellebriteEventCenter, CellebriteCommsCenter (threads+envelope), CommsCrossTypeTimeline (main+seed+loadMore+envelope), CommsContactFeed, CommsContactDrawer.
- **VERIFIED (backend, case 43f1afb1):** /events/envelope?has_attachment → total 19,528 (Communication 19,484 + Email 44), range 2017→2023. /events?event_types=message&has_attachment → 5,000 rows ALL with attachments (was ~105/500 unfiltered) → cap now applies to MEDIA rows. /comms/between?has_attachment → 300/300 carry attachments. (Comms-envelope count 15,602 < events-envelope 19,484 = comms feed's stricter sender+chat shape, pre-existing.) FE build clean. owl-backend RESTARTED.
- **Files (UNCOMMITTED, on top of the client-side batch below):** BE `services/neo4j_service.py`, `routers/cellebrite.py`; FE `services/api.js`, `CellebriteTimeline.jsx`, `CellebriteEventCenter.jsx`, `CellebriteCommsCenter.jsx`, `comms/CommsCrossTypeTimeline.jsx`, `comms/CommsContactFeed.jsx`, `comms/CommsContactDrawer.jsx`.
- **NEXT ACTION:** user in-browser check (toggle now reaches the full media set, not just the loaded slice). Then offer commit.

## 2026-05-29 — "HAS ATTACHMENT" FILTER everywhere + COLLAPSIBLE SCRUBBER — ✅ DONE (UNCOMMITTED), frontend-only (HMR)
User: (1) a "Has Attachment" option in all messaging views; (2) the scrubber should be collapsible/expandable.
- **Has Attachment (client-side, composes with search):** added a `has:` operator to the shared `utils/cellebriteSearch.js` (KNOWN_OPERATORS + `itemHasAttachment()` helper checking attachments[]/attachment_file_ids/attachment_count/has_attachments + a matchItem gate; aliases attachment/attachments/media/file). New shared `shared/AttachmentFilterToggle.jsx` (📎 controlled toggle). Each view tracks a `hasAttachmentOnly` bool and injects `has:'attachment'` into its parsed query (so it ANDs with text search); the filter useMemos now run when `searchQuery || hasAttachmentOnly`. Wired into: CellebriteTimeline, CellebriteEventCenter, CommsThreadView, CommsContactFeed (search-bar toggle); CommsContactDrawer (sub-header, filters feedItems before grouping); CommsCrossTypeTimeline (toolbar, filters orderedItems); Comms Center thread list via CommsCompactToolbar → CellebriteCommsCenter (gates on thread-level `has_attachments`/`attachment_count` BEFORE the metadata/deep-body branches). NOTE: client-side over loaded items — on the 5000/type-capped Timeline/Event Center it filters the loaded slice (consistent with how search already works there; truncation banner already flags the cap). Could add a server `has_attachment` param later (attachment_count exists on nodes → cheap) if a true cross-cap filter is wanted.
- **Collapsible scrubber:** new shared `shared/CollapsibleScrubber.jsx` — thin toggle header (BarChart3 + label + "· date range filtered" when a window is set + Show/Hide chevron) that conditionally renders TimelineScrubber and forwards all props. Replaced the always-mounted `<TimelineScrubber>` with `<CollapsibleScrubber>` in CellebriteTimeline (label "Timeline", open), CellebriteEventCenter ("Timeline", open), CellebriteLocations ("Locations", open), CommsThreadView ("Messages", defaultOpen=false, compact). CommsCompactToolbar (Comms Center) already had its own scrubberOpen collapse — left as-is.
- Build clean (`npx vite build`). Frontend-only → Vite HMR live, NO backend restart.
- **Files (UNCOMMITTED):** new `shared/AttachmentFilterToggle.jsx`, `shared/CollapsibleScrubber.jsx`; mod `utils/cellebriteSearch.js`, `CellebriteTimeline.jsx`, `CellebriteEventCenter.jsx`, `CellebriteLocations.jsx`, `CellebriteCommsCenter.jsx`, `comms/CommsThreadView.jsx`, `comms/CommsContactFeed.jsx`, `comms/CommsContactDrawer.jsx`, `comms/CommsCrossTypeTimeline.jsx`, `comms/CommsCompactToolbar.jsx`.
- **NEXT ACTION:** user in-browser check; then offer commit (prior media/truncation/scrubber commits 0f40e09 + 61961f4 are on main, unpushed; this is a new uncommitted batch on top).

## 2026-05-29 — MEDIA EVERYWHERE v2: voicenotes/multimedia in all timelines + tables + flyouts — ✅ DONE + COMMITTED 61961f4, backend RESTARTED
User: extend the message-thread media rendering (voicenotes/audio players, images, video, files via `CommsAttachment`) to EVERY surface — every timeline, the comms tab, every conversation flyout. (Builds on 2026-05-27 PART A which fixed the contact-feed endpoint.)
- **Decisions (user, via AskUserQuestion):** list/timeline rows = **compact preview + expand** (thumbnail strip / 🎙 voicenote chip / count; click → full `CommsAttachment` inline; full media also still in detail flyout). Spreadsheet tables = **media badge** (icon+count chip → popover of `CommsAttachment`; don't break the grid).
- **Already rendered media (no change):** CommsMessageBubble/CommsCallRow/CommsEmailCard/RailEmailBody → CommsThreadView, CommsContactFeed (chat), CommsContactDrawer, EventDetailDrawer, rail EventBody.
- **Data gaps fixed:** `/cellebrite/events` (Timeline + Event Center feed) and `/events/{key}/related` (rail lists) did NOT carry attachments.
- **DONE:**
  - [x] BE `neo4j_service._project_event`: added `attachment_file_ids` passthrough (covers message/call/email + around-email; empty for non-comms).
  - [x] BE `cellebrite.py get_events`: `_resolve_attachments(case_id, result["events"])` when `not lean` (lean=locations only).
  - [x] BE `cellebrite.py get_event_related`: resolve attachments on thread + around.
  - [x] FE new `comms/CommsMediaStrip.jsx` (compact preview + expand; `expandable={false}` variant for windowed rows → renders a `<span>`, clicks bubble to row→flyout).
  - [x] FE new `comms/CommsMediaBadge.jsx` (📎N chip → portalled popover of `CommsAttachment`, for tables).
  - [x] FE wire: TimelineRow (CellebriteTimeline; height budgeted via `TL_ROW_MEDIA_PX=36`), RelatedList (rail EventAccordion; expandable), EventsTable (badge in Summary cell), CommsContactTable (badge in Body cell), CommsCrossTypeTimeline (inline 📎N indicator — fixed-height `<button>` row, no nested btn).
  - [x] Swim-lane/dot views (EventTimelinePanel, CellebriteTimelineSwimLane, CommsCrossTypeSwimLane) = **deliberate skip** — pure SVG dot/marker visualisations, no rows to attach media to; clicking a dot opens the flyout (full media).
  - [x] `npx vite build` clean. owl-backend RESTARTED (port 8000).
- **VERIFIED (backend):** `GET /api/cellebrite/events?event_types=message&limit=500` (case 43f1afb1-1d2b-4b3f-a832-19cd049c8a9e) → 105/500 rows now carry `attachments` (84 Audio `.opus` voicenotes, 18 Image, 1 Video) with evidence_id+category+filename. Category casing Audio/Image/Video maps correctly via attachmentKind toLowerCase.
- **Files (UNCOMMITTED):** BE `backend/services/neo4j_service.py`, `backend/routers/cellebrite.py`; FE new `comms/CommsMediaStrip.jsx`, `comms/CommsMediaBadge.jsx`; FE wired `CellebriteTimeline.jsx`, `shared/rail/EventAccordion.jsx`, `events/EventsTable.jsx`, `comms/CommsContactTable.jsx`, `comms/CommsCrossTypeTimeline.jsx`.
- **NEXT ACTION:** in-browser visual spot-check by user (they're testing). Then OFFER COMMIT (these + the uncommitted scrubber date-picker + prior uncommitted scrubber-crash fixes are all still local). Optional polish: TimelineRow media strip budgets one line (36px) with overflow-hidden — a rare row with many attachments + long wrap could clip the chip overflow (full media still in flyout).

## 2026-05-29 — TIMELINE "5,000 items" SILENT TRUNCATION — ✅ FIXED (UNCOMMITTED), backend RESTARTED
User: "There looks to be a 5000 limit in timeline — All time · 5,000 items". Correct: `CellebriteTimeline` fetches `/cellebrite/events` per type capped at `limit:5000`; the per-type cap silently dropped older events AND the scrubber then labelled the capped slice "All time · 5,000 items". Violates [[feedback_no_silent_truncation]] (truncation must be visible; don't just raise the limit — fix the contract).
- **Why not "load all" (like Locations):** event feed is huge + rich — envelope shows **561,600 total events** for this case (Communication alone 266,545; the message body fetch at limit=300000 TIMED OUT). Loading all rich rows is the exact thing the per-type cap was added to avoid. So the fix is honesty + an envelope, not a bigger limit.
- **FIX (envelope + visible truncation, mirrors Comms Center):**
  - BE `neo4j_service.get_cellebrite_events_envelope()` (new) — cheap count-by-date aggregation across ALL active event labels (reuses `_build_event_filters` + new `_EVENT_TYPE_LABELS` map), returns total + per-type counts + min/max date + per-day histogram, NO row loading. Plausibility guard drops sentinel dates (<2000-01-01 / >today+1) so 1970/0001 sentinels can't stretch the scrubber axis (buildBucketsFromEnvelope has no isPlausibleTs of its own).
  - BE router `GET /cellebrite/events/envelope`. api.js `getEventsEnvelope`.
  - FE `CellebriteTimeline`: new envelope fetch effect (deps caseId/reportKeys/types — NOT the scrubber window, so it describes the WHOLE range); passes `envelope` to `TimelineScrubber` (now shows true total + full range + "scrubber covers full range"); captures `truncated_types` from the per-type body fetches → **amber banner**: "Showing the most recent 5,000 per type for X — N events exist in total. Narrow the date range to load older events."
- **VERIFIED (backend):** `GET /events/envelope` → total 561,600, min 2005-04-04, max 2025-12-15, 2369 histogram days, per-type counts present; ~9.5s cold (count over 561k nodes/19 labels — runs async/background, scrubber upgrades when it lands). FE build clean. owl-backend restarted.
- **Files (UNCOMMITTED, on top of the media-everywhere set):** BE `services/neo4j_service.py`, `routers/cellebrite.py`; FE `services/api.js`, `components/cellebrite/CellebriteTimeline.jsx`.
- **EXTENDED to Event Center + audited every other table/view (user: "extend to Event Center table + any other table/view where it exists"):**
  - **CellebriteEventCenter** (map + EventsTable + EventTimelinePanel — all share the same per-type 5000 body fetch): same fix applied — captures `truncated_types`, fetches the events envelope (NOW with `only_geolocated` support so its total matches the map's geo-only mode), passes `envelope` to its TimelineScrubber, shows the amber banner ("Map & table show the most recent 5,000 per type… N match in total"). Envelope service+endpoint+api.js gained `only_geolocated` (mirrors body geo guards: Location/CellTower need lat+lon; comms accept lat OR nearest; other types unfiltered). VERIFIED: geo envelope total 245,794 vs full 561,600 (correctly smaller; comms excluded since 0 are geolocated — matches body).
  - **AUDIT of every other event/comms surface — no further silent-cap fix needed:**
    - CellebriteLocations: loads ALL points (limit 500000 ≈ 68k actual; the `limit:500` call is only the filter-suggestion sample). Already "all there" per dc5103e.
    - Comms Center thread list + CommsCrossTypeTimeline: cursor-paginated (`/comms/between`, infinite scroll) + already use the comms envelope → honest.
    - Contact-feed (CommsContactFeed/Drawer): returns a TRUE uncapped `total` + pages (per 2026-05-25 fix) → honest.
    - CellebriteUnifiedContacts: already had its own `truncated` banner.
- **NEXT ACTION:** user in-browser check — Timeline scrubber should read e.g. "All time · 561,600 items · scrubber covers full range" + amber banner; Event Center same (geo total in geo mode). Then offer commit. Optional: envelope ~9.5s cold (count over 561k nodes/19 labels) could be cached/index-tuned; narrowing the window makes it cheaper.

## 2026-05-29 — TIMELINE SCRUBBER: crashes + page-hang on interaction — ✅ FIXED (UNCOMMITTED)
Continuation of the timeline-crash work (prior commit 912f4a8 fixed only the `toISOString` RangeError crash). User still saw **crashes AND page hanging** when interacting with the scrubber. Found THREE distinct root causes, all fixed frontend-only (Vite HMR live; no backend/data change — per [[project_cellebrite_v2_migration]] prefer frontend stopgaps over legacy-data cleanup):
- **CAUSE 1 — histogram bucket explosion (the visible "hang" tied to the scrubber).** `social_media` has a `1970-01-20` sentinel timestamp (epoch-near-zero from a failed ingest date-parse) and it's a SMALL type (1006 rows) so it loads fully on every timeline view. 3 `Email` rows also carry `0001-01-01`. `buildBuckets` let these set `minTs` → span ~53yr (or ~2024yr for 0001) → 'week' unit → **2,768 (or ~105,000) SVG `<g>` bars**, re-rendered on every drag pointermove. FIX in `TimelineScrubber.jsx`: `isPlausibleTs()` excludes timestamps outside `[2000-01-01 .. now+1d]` from the AXIS BOUNDS (items still drop into the nearest edge bar — nothing hidden), + `MAX_BUCKETS=2000` hard cap (widen sizeMs) as a backstop in BOTH `buildBuckets` and `buildBucketsFromEnvelope`. Bars 2,768→285; axis now 2017→2023 not 1970.
- **CAUSE 2 — un-virtualized timeline list (the 42s/12s freezes).** `CellebriteTimeline` rendered EVERY event as a DOM row: **67,637 rows = 42s main-thread freeze on load**, and a **12s freeze on every drag-commit** (pointerup changes `windowStart` → parent re-renders & reconciles the whole 67k subtree ONCE before the clearing effect fires). FIX: new windowed `TimelineList` (forwardRef) in CellebriteTimeline.jsx — flattens day-groups → render items, precomputes per-item heights (variable: header 30, row 34 +18/extra line for direction/summary) + cumulative offsets, binary-searches the visible slice (TL_OVERSCAN_PX=600), renders top/bottom spacers. `scrollToDate` now calls `listRef.current.scrollToDay()` (computed offset) since headers may be windowed out of the DOM. `TimelineRow` root `<li>`→`<div>` (no longer inside `<ul>`). Mirrors LocationsTable/EventsTable windowing.
- **CAUSE 3 — setState-in-render warning** (real anti-pattern in the drag path): `onPointerUp` called `onWindowChange` (parent setState) INSIDE the `setDragPreview` updater (runs during child render). FIX: mirror preview in `dragPreviewRef`, commit by reading the ref + `setDragPreview(null)` separately.
- **VERIFIED in-browser (puppeteer, case OPDMD28=43f1afb1, fresh token via /tmp/mint2.py run from backend/ with ../venv):** initial render block 42,391ms→**412ms**; drag block 11,594ms→**251ms**; histogram 2,768→**285** bars; DOM rows 67,637→**~28 windowed** (28→44 on mid-scroll = recycling works); **0 JS errors** (warning gone); no error boundary; headers + multi-line rows + phone chips render correctly (screenshots /tmp/c_tl_loaded.png, /tmp/c_tl_scrub.png). Harness: NODE_PATH=/home/conorbowles51/app_backup/frontend/node_modules node /tmp/verify_scrub.cjs (+ /tmp/verify_phase.cjs for per-phase block timing, /tmp/verify_shot.cjs for screenshots).
- **Files changed (UNCOMMITTED, both esbuild-clean):** `frontend/src/components/cellebrite/shared/TimelineScrubber.jsx`, `frontend/src/components/cellebrite/CellebriteTimeline.jsx`.
- **NEXT ACTION:** OFFER COMMIT of the 2 files. Then offer push (local main still ahead & unpushed per prior sessions). Optional v2 polish: sticky day-header was dropped by windowing (headers now scroll inline) — could add a floating current-day chip; and the per-row height is estimated (generous, overflow-hidden) so a row with unusually long wrapped content could clip — fine for current data.

## 2026-05-28 — LOCATIONS TAB: stale "5,000 cap" text + trajectory freeze — ✅ FIXED + COMMITTED 0111bb4 (load-time floor remains)
Team: Locations tab still shows "capped at 5,000 points"; trajectory very slow — Chrome "page unresponsive" popups, ~5 min to render.
- **FIX 1 (stale text):** CellebriteLocations raw-mode hint hardcoded "Capped at 5,000 points" (fetch cap was already lifted to 500k). Replaced with live count ("{N} points loaded — trajectory uses every point; dense dots thin out").
- **FIX 2 (freeze):** EventMapPanel rendered EVERY point as a DOM `divIcon` Marker+Popup in MarkerClusterGroup → ~68k DOM icons on the main thread = the multi-min freeze (preferCanvas doesn't apply to divIcons). Now: above CANVAS_THRESHOLD=3000 geo-points, render canvas `CircleMarker`s (preferCanvas), decimated to MAX_CANVAS_MARKERS=8000 via even stride (selected point always kept); click→onEventClick (rail detail). Trajectory POLYLINE still drawn from `tracks`, uses EVERY point (path complete). Visible note "N of M points shown as dots · full path drawn · table lists all". Sparse sets keep divIcon+cluster.
- **VERIFIED (puppeteer /tmp/verify_loc.cjs):** stale text gone; "68,252 points loaded"; "7,584 of 68,252 points shown as dots"; single canvas layer; 0 console errors. (Responsiveness probes were flaky in headless; the divIcon→canvas swap removes the known main-thread freeze by construction.)
- **REMAINING LOAD-TIME FLOOR (not yet addressed, needs user trade-off decision):** backend `/cellebrite/events` for all 10 phones returns **54.8 MB / 68,252 events in 16.5s** (cold). That + 55MB JSON.parse is an inherent ~15-25s WAIT (spinner, responsive — not a freeze) when loading ALL points. Fields are interlinked (search place:/near:/app:/type: + table use most of the 32 fields) so trimming is risky. To make it snappy, options to offer the user: (a) lean trajectory endpoint returning compact [lat,lon,ts,device] arrays (polyline stays complete; dots decimate; table fetched lazily/full only in table view) — best, bigger build; (b) server-side `max_points` downsample for the map with full data via date/search narrowing — conflicts with the earlier hard-won "capture every point" so MUST confirm. See [[project_cellebrite_v2_migration]] (location-dense perf).
- **✅ LOAD-TIME + ALL-POINTS DONE (user: "all locations need to be there") — COMMITTED dc5103e:** kept EVERY point (no downsample), fixed the 3 real costs:
  1. **Lean fetch** — `get_cellebrite_events(lean=True)` projects only used columns + omits nulls (was `RETURN n`, ~36 keys mostly null). 54.8MB/16.5s → 37.8MB/8.9s, same 68,252 rows, table+search fields intact. (`_project_location_lean`; router `lean` param; api.js `lean`; CellebriteLocations passes lean:true.) Backend RESTARTED.
  2. **Map = single canvas layer** (`CanvasPointsLayer` in EventMapPanel) drawing ALL points in one loop (~100ms) — replaced 68k per-point objects (the ~50s hang). Pans via overlay pane, hit-tests clicks. No decimation; polyline already used every point. Removed the decimation note/cap.
  3. **Table virtualised** (`LocationRowsView` in LocationsTable) — was 68k `<tr>` (own freeze); now windows visible rows + spacers, all rows scrollable.
  - MEASURED: headless load+render ~100s → ~25s; **max main-thread block 53s → <0.5s**; 0 points dropped; 0 console errors. (Headless timers noisy — block-gap + screenshot are the reliable signals.)
  - NOTE: backend lean query is still ~8.9s (Neo4j scan+ORDER BY of 68k); acceptable + responsive. Could shave more by dropping ORDER BY (frontend sorts) if needed.
- **NEXT ACTION:** commits NOT pushed — local main ahead by dc5103e, 0111bb4, 55d82be, ed6146e, c0b14c1, b51604d, 9c2fd9c (+ earlier session 06f10d0/09bd9a8/2a98a3d). OFFER PUSH. Fresh token at /tmp/owl_token.txt (old one expired mid-session; mint via /tmp/mint2.py if needed).

## 2026-05-28 — TIMELINE TIMEZONE INCONSISTENCY ("two overlapping timelines") — ✅ FIXED + COMMITTED 55d82be
Team report: WhatsApp/IG messages read at correct time, but log entries / website-access entries showed ~4h off (detail view 4h later than timeline), the day appeared to end at 8 PM, and events weren't in true linear order.
- **DIAGNOSIS — NOT a data bug (no re-ingest).** Stored timestamps are uniformly UTC: verified (a) report XML `<value>` text == `formattedTimestamp`, all `+00:00` (30,192/30,192 in C5); (b) every event type (Communication/PhoneCall/VisitedPage/LogEntry/DeviceEvent) shares the SAME UTC activity "sleep window" (~05–09 UTC dead zone) → no 4h scale split. Sorting (by absolute instant) was already correct.
- **ROOT CAUSE = inconsistent frontend rendering:** `formatShortTime` (messages, commsUtils) rendered browser-LOCAL; `formatTs` (events/detail/timeline, eventUtils) used LOCAL getters under a hardcoded "UTC" label → same instant shown on two clocks. AND CellebriteTimeline grouped days by the raw UTC string (`timestamp.slice(0,10)`) → UTC-midnight = 8 PM US-East boundary, splitting a local evening across two buckets.
- **FIX (frontend-only, committed 55d82be):** new `shared/cellebriteTime.js` (Intl fmtTime/fmtDateTime/fmtShort/dayKey/zoneAbbr/offsetLabel for a chosen IANA zone; DST per-timestamp) + `shared/CellebriteTimezone.jsx` (per-case TZ context + `useCellebriteTime` hook + tab-bar selector). Default **Device = America/New_York** (case phones are US-East), **UTC** toggle for cross-device alignment; selector shows live offset "Device · EDT (UTC−4)". `formatTs`+`formatShortTime` delegate to the util (one clock everywhere). Timeline day-grouping + Comms thread date-separators bucket by selected-zone calendar day; `formatDateSep` parses Y-M-D as plain local date. Reactive surfaces (hook): Timeline, EventsTable, EventDetailDrawer, CommsThreadView, CommsContactFeed, OverviewDetailView, CommsCrossTypeTimeline.
- **VERIFIED (puppeteer /tmp/verify_tz.cjs):** selector "Device · EDT (UTC−4)"; Device↔UTC toggle shifts every row consistently (14:04 ET ↔ 19:04 UTC); Feb events correctly convert at EST/−5 (per-timestamp DST); day headers group local; 0 console errors. Screenshots /tmp/c_tz_device.png, /tmp/c_tz_utc.png. See [[project_cellebrite_timestamps_utc]].
- **NEXT ACTION (on resume):** commit 55d82be (+ earlier c0b14c1/ed6146e/b51604d/9c2fd9c) NOT pushed — offer push. Optional polish: swimlane "sameDay" gap checks (CellebriteTimelineSwimLane:760, CommsCrossTypeSwimLane:728) still use browser-local toDateString — minor, convert to dayKey if a swimlane misgroups; and the detail drawer could append a per-event zone tag (e.g. "EST") for historical events whose offset differs from the selector's current-date label.

## 2026-05-27 — MEDIA ON ALL MESSAGE SCREENS + "SEND TO AI" (transcription / image recognition) — ✅ DONE + COMMITTED
User: "I can see media/voice in chats — make sure visible on ALL message screens. Also add the ability to send voice/media to AI tools (transcription, image recognition), incl. in the file viewer tab."
- **PART A (media everywhere) — root gap found + fixed (commit c0b14c1):** thread view (`/comms/threads/{id}`), `/comms/between`, and event detail all call `_resolve_attachments`, but the **contact-feed** endpoint (`/comms/contact-feed/{key}` → Communications-tab drill + Comms-Center contact drawer) did NOT → those feeds showed messages with NO media (bubbles read `item.attachments`, which was never populated). FIX = added `_resolve_attachments(case_id, result["items"])` to the contact-feed endpoint. Overview/Events/Timeline are summary TABLES (paperclip count + open-in-rail by design) — left as-is. VERIFIED: contact-feed now returns resolved attachments (29/400 items for Trabajo, each with evidence_id + category).
- **PART B (on-demand AI media analysis) — built + COMMITTED ed6146e.** Reuses the already-wired ingestion processors (no new deps): whisper 20250625 + ffmpeg 7.1 ARE installed; OpenAI vision wired (gpt-4o).
  - Backend: `EvidenceService.transcribe_evidence` (local Whisper, `audio_processor.transcribe_audio` + `audio_ingestion._get_whisper_model`) + `analyze_image_evidence` (`image_processor.process_image`, openai→tesseract fallback). `evidence_storage.set_analysis(id, kind, result)` caches on the record (locked reload-mutate-save, multi-worker safe). Endpoints `POST /evidence/{id}/media-analyze` (kind auto-detect from category/ext; 503 when tool unavailable; returns cached unless force) + `GET /evidence/{id}/analysis`. owl-backend RESTARTED.
  - Frontend: shared `cellebrite/files/MediaAnalysisPanel.jsx` (+ `mediaKindFor`): image→"Recognize image", audio/video→"Transcribe" (+ orig-lang vs translate-to-EN). Lazy in chat (no per-attachment fetch); `autoLoadCache` in the single-file viewer. Wired into `FileDetailPanel` ("AI processing" section) + `CommsAttachment` (action under each image/audio/video attachment, uses `attachment.evidence_id`). api.js: `analyzeMedia`, `getAnalysis`.
  - VERIFIED on REAL evidence: WhatsApp voice note PTT-20221213-WA0168.opus → Spanish transcript ("Mija, por favor… le voy a mandar una foto de los otros lados…"); image IMG-20221213-WA0170 → gpt-4o described scene + read handwritten numbers (40/1500/2500/…); cached re-run returns cached:true (no re-charge); file viewer shows the "AI processing" section + cached transcript in-browser (puppeteer /tmp/c_fileviewer.png), 0 functional console errors (one benign 401 = the audio-preview evidenceUrl, pre-existing).
- **NEXT ACTION (on resume):** (1) commits c0b14c1 + ed6146e NOT pushed — offer push. (2) The Comms-Center thread-view attachment AI button wasn't screenshot-verified (puppeteer thread-click flakiness) but uses the SAME MediaAnalysisPanel + resolved evidence_id — renders deterministically; spot-check live if asked. (3) optional: a "translate" toggle is per-panel; consider a case-wide default language.

## 2026-05-27 — NUMBER-ALONGSIDE-NAME EVERYWHERE (P4 completion across ALL cellebrite tabs) — ✅ DONE (UNCOMMITTED)
User: "the new contact approach we put in Contacts (unified) isn't implemented in the Communications tab, nor the Comms Center participants list — and likely elsewhere too. Make it correct all through the app." = finish P4 (a contact NAME is never shown without its NUMBER) on every surface that was missed.
- **Approach:** one consistent rule — replace every bare person-name render with the shared `<PersonName>` (shared/PersonName.jsx). It derives the number from the `phone-<digits>` key (so NO backend change needed — numbers come free client-side), shows "(unnamed) +<num>" for bare-number/empty names, and omits the number for app/email identities (no phone). NO backend edits this session.
- **PersonName extended (2 new props):** `highlights` (renders the label via HighlightedText so search-highlighted surfaces keep their match marks while gaining the number) + `hideNumber` (for two-column layouts that already have a dedicated phone column — keeps the "(unnamed)" cleanup, suppresses the duplicate inline number).
- **16 files changed (all esbuild-clean), per-tab:**
  - shared/PersonName.jsx (extended: highlights + hideNumber).
  - **Comms Center (flagged):** comms/CommsParticipantsFilter.jsx (picker rows + selected chips), comms/CommsEntityFilter.jsx (rows + From/To chips), comms/CommsThreadView.jsx (participant colour-key strip), comms/CommsMessageBubble.jsx (sender header), comms/CommsCallRow.jsx (from→to), comms/CommsEmailCard.jsx (from→to).
  - **Communications tab (flagged):** CellebriteCommunicationView.jsx — dropped the broken/empty "Phone" column (it read p.phone which is mostly null), Name col → PersonName (name+number), shared-contacts panel → PersonName. colSpan 7→6.
  - **Overview:** overview/OverviewEmailsView.jsx (From/To cols), overview/OverviewContactsView.jsx (Name col hideNumber + Phone col falls back to phoneFromKey(key) so it's never blank), overview/ContactDetailDrawer.jsx (header), overview/MergeIdentitiesDialog.jsx (selected + result rows).
  - **Events:** events/EventsTable.jsx (From/To cols).
  - **Rail:** shared/rail/EventAccordion.jsx (counterpart), shared/rail/RailEmailBody.jsx (from/to), shared/rail/GraphSelectionAccordion.jsx (PersonCard — consolidated name+number, dropped redundant phone span).
- **DELIBERATE skips (defensible, noted):** (1) CrossPhoneGraph CANVAS person-node labels — drawing numbers on 1,410 nodes = unreadable; the number shows in the selection rail (GraphSelectionAccordion, fixed) on node pick. (2) Communications-tab drill BREADCRUMB + thread-title comma-summary — navigation chrome, not a contact listing; the per-participant strip / feed below them carry the numbers.
- **REVERSED a prior decision:** earlier WORKING note said "Filter chips (CommsEntityFilter/ParticipantsFilter) deliberately not cluttered with numbers." User explicitly wants numbers there → now added. See [[feedback_cellebrite_number_alongside_name]].
- **VERIFIED in-browser (puppeteer, /tmp/verify_contacts.cjs, token /tmp/owl_token.txt valid ~until Jun 1):** Communications tab rows show "Trabajo 444 +12404291127 / Pefro +12404608695 / 8121besino +13014089877…" (screenshot /tmp/c_communications.png — Contact col + Shared Contacts panel both numbered). Comms Center Participants filter loaded 94 rows: phone contacts show numbers ("!lobo Menso +12024893555"); email/newsletter identities correctly show name-only (no phone). 0 console errors.
- **NOT a backend change for the number sweep** → Vite HMR served the frontend edits live.
- **✅ COMMITTED b51604d** (Neil B) — the 16-file number-alongside-name sweep.
- **✅ ALIASES TOO (user said "commit then do aliases too") — DONE + COMMITTED 9c2fd9c:**
  - Backend `neo4j_service.person_aliases(case_id)` → {person_key:[{name,report_keys}]} (every saved name across devices, from ContactEntry, most-used first, 1 query, 120s TTL). Attached to `get_cellebrite_communication_network` (contacts + shared_contacts union) and `get_cellebrite_comms_entities` (both paths, cap 8/entity). py_compile OK; **owl-backend RESTARTED** (live, health 200, endpoints return aliases — Trabajo 444 → [Lan Chita,Maitria,Esperosonal,Doñita,…]).
  - Frontend new shared `<AliasChips>` (unified chip group factored out; omits primary name, "+N" overflow). Communications tab → new "Also saved as" column + Shared Contacts panel chips + alias search. Participants filter → alias chips (two-line rows) + alias/number search (typing "Maitria" finds "Trabajo 444"). esbuild-clean.
  - VERIFIED in-browser: Communications tab shows "Trabajo 444 +12404291127 | Lan Chita·Maitria·Esperosonal +4"; participants filter alias-search surfaces Trabajo via "Maitria" with chips. 0 console errors. Screenshots /tmp/c_communications.png, /tmp/c_part_alias2.png.
  - CommsEntityFilter left untouched (NOT rendered anywhere — legacy; CommsParticipantsFilter is the active Comms Center filter).
- **NEXT ACTION (on resume):** (1) Both batches committed (b51604d, 9c2fd9c) — NOT pushed; offer push if user wants. (2) media-reg b74oiiy6e (C8/C2/C4/C9/C1b chat attachments) is NO LONGER running (evidence.json last written 09:03 today) — verify those phones' attachments resolve / decide whether to resume the remaining reports.

## 2026-05-26 — DEVICE-OWNERSHIP / MISLABELLING ANALYSIS (forensic, IN PROGRESS)
Case 43f1afb1. Victim **Edvin Augustin Leon, died Nov 9 2022**. Alleged hit-orderer = **"Trabajo 444" = +12404291127** (`phone-12404291127`). User reports evidence sheet says **C5 AND C6 belong to the deceased** — suspected mislabel. Confirmed mislabel via post-death OUTGOING activity (dead man can't call/text; incoming proves nothing since all 10 phones stop in+out together AT SEIZURE).

KEY DATA (live Neo4j, ts stored as ISO STRINGS — compare with string `> '2022-11-09'`, NOT datetime()):
- **C6 (06306962, key cellebrite-220049582-06306962)** = **almost certainly Trabajo's OWN phone**, NOT the victim's. 3 converging signals: (1) +12404291127 is one of C6's own device MSISDNs — ONLY report where it's an owner number; (2) Trabajo's WhatsApp `12404291127@s.whatsapp.net` is in C6 owner-identity all_identifiers; (3) **57,361 messages on C6 have Trabajo as sender** vs 58–359 on every other phone (owner fingerprint). 2,074 outgoing calls + heavy msgs AFTER death, until Dec 14 seizure. Auto-detector mislabelled owner "Mry" (phone-12404233667) due to multi-SIM aggregation: C6 has 1 IMEI (355865103000524) / 8 ICCIDs / 2 IMSIs / 3 numbers (+12404233667 last-use 8/25, +12404291127 10/31, +12403981223 12/11).
- **C5 (06306946)** = third party **"Pefro" (+12404608695)**, also alive (295 outgoing calls + sent SMS to Dec 14). Victim appears ON C5 only as CONTACTS ("Agustin" +12027608243, "Edvin izabal") → C5 owner KNEW victim, but C5 ≠ victim's phone.
- **C1-06304890 (Carlo Yaque del Cid, iPhone, examiner LeDoux)** = only device dark at murder window: last sent Nov 6, last call Nov 10 16:57, full in+out silence, imaged Nov 15. **USER CONFIRMED: Carlo arrested the day after the murder (Nov 10)** → arrest/seizure pattern, not victim. Carlo also linked to C7's "🤑" via carlos.yaque13@gmail.com.
- **Victim Edvin Augustin Leon owns NONE of the 10 devices** (only a contact). Either never imaged or hiding under a wrong owner label (same multi-SIM/identity-merge artifact).
- All 10 devices' last activity = SEIZURE time (Nov 15 → Feb 2 2023 range), confirmed living users on 9 of 10.
- **TRUE PRIMARY-USER PROFILE (approach b — dominant SENT_MESSAGE sender cross-checked vs device's own MSISDNs), done 2026-05-26:**
  - C1 (06305320) = **Alexis Andrade** +12408146400 (snapchat cs13s same person)
  - C1b (06304890) = **Carlo Yaque del Cid** +12407254620/+12025699225/+13163897207 — ARRESTED Nov 10 (confirmed by user)
  - C2 (06306207) = **"Dsnt"/senderchapin502** +13015376576 & +13014420513 (uses both own numbers + snapchat)
  - C3 (06306208) = **Sender Lemus** +12407063529/+12407063672
  - C4 (06306369) = **"🤑" = Carlos Yaque** +14344805691 (LOW volume; carlos.yaque13@gmail.com → same Carlo as C1b/C7)
  - C5 (06306946) = **"Pefro"** +12404608695
  - C6 (06306962) = **Trabajo 444** +12404291127 (57,361 msgs vs next 2,861 — overwhelming; = alleged hit-orderer)
  - C7 (06306964) = **+14105010984** (no saved name resolved)
  - C8 (06308586) = **Bryan** +13015416552 (own-MSISDN; his outgoing not materialised as SENT_MESSAGE so dominant-sender shows counterparties)
  - C9 (06310028) = **Vides Martinez** +13015567274 (telegram 5621295398 same person)
  - **Victim Edvin Augustin Leon owns NONE of the 10** (appears only as contact "Agustin"/"Edvin izabal" on C5). Caveat: Carlo/🤑 spans C1b/C4/C7 — multi-device or owner-detection conflation, needs care. Names shown are themselves subject to the conflation bug below.
  - Method caveat: dominant-sender reliable where it matches own MSISDN (C1,C3,C5,C6,C9,C1b); C7/C8 lean on own-MSISDN (owner outgoing not always a SENT_MESSAGE). SENT_MESSAGE rel = the sender PARTY; C6 "Sent"-folder SMS have NO sender rel, "Inbox" do.

## 2026-05-26 — CONTACT-CONFLATION BUG + PER-SIM/CONTACT/COMMS PROJECT (NEW, planning → awaiting design decision)
User requirements (verbatim intent): (1) profile true primary user of all 10 [DONE above]; (2) profile each SIM definitely used per device; (3) per-SIM/per-device COMPREHENSIVE contact list with phone number + **name EXACTLY as saved on device** — many contacts currently missing; (4) STOP the rollup conflating all names into the first/principal instance — preserve ALL original names at device AND SIM level; (5) guaranteed-accurate list of ALL in/out comms; (6) phone number ALWAYS shown alongside any contact name in the UI.
ROOT CAUSE FOUND (neo4j_writer.py): `_ensure_person` (line ~504) MERGEs on `phone-<e164>` and sets `name` **ON CREATE only**; ON MATCH patches just extra_props (never `name`). → the FIRST handler to touch a number wins the name forever; every other saved name (other devices, SIMs, contacts vs message-parties) is **discarded at ingest**. No `name_aliases` field exists → names already LOST from the graph. ⇒ accurate contact lists must be rebuilt from source XML.
DATA-MODEL REALITY (verified): no `Contact` node label (contacts fold into Person, 15,234 nodes, single `name`); SIM modelling broken (7 SIMCard nodes, ICCID empty, junk dynamic props msisdn_1_*); contact_source IS captured on 1,493/15,234 persons (values: InteractionC 936, Recents 282, WhatsApp 122, TextNow, Telegram, **SIM only 3**…). C6 XML has NO separate SIM extraction (just Logical+Physical of phone); the "8 ICCID/2 IMSI" are device-info SIM-history artifacts, not SIM card dumps. ⇒ **literal "contacts stored ON each SIM" is nearly empty** — contacts are phone/app-account scoped. Real win = preserve exact per-device names + show numbers.
PLAN (4 parts): **(P2)** XML-source forensic export per device — SIMs used (MSISDN+last-known-use/IMSI/ICCID), every Contact exact name+numbers+source, all comms in/out w/ counterparty number+exact name+direction+ts+app (bypasses buggy graph; immediate value). **(P3)** Fix conflation in ingest+model: preserve all names — DESIGN CHOICE PENDING: (A) `name_aliases:[{name,report,source}]` on Person [lighter] vs (B) separate `ContactEntry` nodes per original record linked to Person + source Device/SIM [faithful, native per-SIM/per-device lists] — recommend B; needs reingest. **(P4)** Frontend: show phone number alongside name everywhere (LocationsTable, ContactDetailDrawer, conversation/timeline views, etc.).
- **DECISIONS LOCKED (user, 2026-05-26):** (1) **P2 first** (XML export), then P3, then P4. (2) Name model = **BOTH views via a toggle** → build **ContactEntry nodes as the faithful per-source foundation** (exact name as saved on a given device/account); the canonical phone-keyed Person AGGREGATES its ContactEntries to yield the "all aliases for one number" list view. One structure, two lenses.
- **C6 NUMBER CERTAINTY (verified 2026-05-26, user asked "are we dropping anything?"):** NO. C6 device lists 3 MSISDNs but only 1 has real traffic: +12404291127 "Trabajo 444" = 57,361 msgs (Jan→Dec 2022, ramp Aug1.7k/Sep12k/Oct16k/Nov18.5k/Dec8.4k) + 13,229 calls (6,729 out/6,500 in = ~all of C6's calls) → REAL OWNER. +12404233667 "Mry" = 51 msgs/1 call (negligible). +12403981223 "Viejita Viejita" = 0/0 (inert, actually a C5 identity). The "3 numbers" = Cellebrite over-harvesting device-info MSISDNs (voicemail/"my number"/contacts-marked-me/SIM-history), NOT dropped data. ⇒ P2 rule: "SIM/number definitely used" = backed by actual comms traffic, not merely listed in device-info.
- **P2 BUILT + VALIDATED (2026-05-26): `scripts/forensic_export.py`** (UNCOMMITTED). Reuses CellebriteXMLParser (parse_header + stream_models), bypasses neo4j_writer entirely. Run: `venv/bin/python scripts/forensic_export.py [LABEL...]` (labels C1 C1b C2 C3 C4 C5 C6 C7 C8 C9; default all). Output `data/forensic_export/<LABEL>/`: contacts.csv (exact Name+numbers+emails+Source+Account, NO merge), numbers_used.csv (traffic-backed ids + sent/recv/calls + first/last + all names_seen), aliases.csv (per id, EVERY distinct name = the conflation surfaced), comms.csv (ALL msgs+calls: ts, direction, app, counterparty number+name-as-saved, body/duration, folder, status), summary.txt (IMEI/MSISDN/IMSI/ICCID + owner numbers by real traffic + totals).
  - DIRECTION = per-message IsPhoneOwner flag on From (owner-sent=Outgoing), else Folder. App msgs (WhatsApp) carry only From → counterparty recovered from parent Chat's non-owner participant(s); group(>2)→labelled "(group) <name>". Fixed 2 bugs in validation: defaultdict-read pollution in sort key; outgoing-app-msg counterparty (now 93% attributed, was ~0).
  - **C6 VALIDATION (matches everything):** owner by traffic = 12404291127@s.whatsapp.net (Trabajo) 57,354 owner-sent — independent confirmation C6=Trabajo's phone. His OWN WhatsApp self-name = "J" ("Trabajo 444" is how OTHERS saved him). 13,005 contact records recovered vs ~1,493 contact-persons in graph = the "missing contacts" quantified. aliases.csv shows e.g. +12154068761 saved as Rosi/Rosy🍀/Rosy🍀estrankila — conflation evidence. CAVEAT: shared service addrs (notification@facebookmail.com) accrue many alias names = noise, not a real person.
  - **STATUS: running other 9 in background (cmd b51qzw1tt → /tmp/.../b51qzw1tt.output).** On completion: spot-check each summary.txt owner vs the primary-user table above; then report to user + decide P2 packaging (zip/Excel?) before P3.
- **P2 COMPLETE — all 10 exported (2026-05-26), owner-by-traffic CONFIRMS primary-user table + refines it:**
  - C1=Alexis Andrade +12408146400 (self cs13s/CS1331; Andrade-family 56183073755 "Elifelet Andrade" also owner-flagged) — 3,983 contacts
  - C1b=Carlo Yaque del Cid +12025699225 (self "Yq13"/"3M") — 2,940 — arrested Nov 10
  - C2="Sender"/senderchapin502 +13014420513 & +13015376576 (self "31"/"31 31") — 2,303
  - C3=Sender Lemus +12407063529 (self "31") — 1,612
  - C4=Carlos Yaque +14344805691 (self "Y13") = **SAME PERSON as C1b** (Y13/Yq13) — 2,552 contacts but only 51 msgs (burner/secondary)
  - C5="Pefro" +12404608695, **real-name candidates "Juan Salguero"/"Manuel Pedro"** (ties to salguerojuan840@gmail.com from DictionaryWord finding) — 1,517
  - C6=Trabajo 444 +12404291127 (self "J") — 13,005
  - C7=+14105010984, **names recovered "Franklin Amaya"/"David Omar"/"Maliante Cortez"** (was "no name" in graph) — 470
  - **C8=DISCREPANCY: traffic-owner "Ilisi"/"Jose/Galileo Campos" (5857356905, +13015416552, fb Campos, snap s1cary3) — NOT "Bryan" as the graph's over-flagged detection implied. NEEDS REVIEW.** — 252
  - C9=Vides Martinez +13015567274 (self "👹👺"/"👹 Martinez") — 235
  - META: owner self-names are almost all nicknames/numbers/emojis (burner-handle pattern); IsPhoneOwner flag attaches to MULTIPLE identities per device (phone+whatsapp+snapchat+fb) which conflation collapses. Victim Edvin Augustin Leon owns NONE.
  - CONFLATION BLAST RADIUS: **306 numbers across the case carry >1 saved name the graph silently dropped** (C6=121, C1b=46, C5=35, C2/C4=31…). (worst-collision outliers like C2=204 are shared service addrs not fully filtered — exclude non-personal ids in P3.)
- P2 deliverables in `data/forensic_export/<C*>/` (contacts/numbers_used/aliases/comms.csv + summary.txt). C8 anomaly + C7 names noted; will self-correct via P3.
- **DECISIONS (user, 2026-05-26):** replace bad data via **TARGETED BACKFILL** (full reingest kept in reserve). NEW REQUIREMENT: a **"Report" tab** in the Cellebrite view beside Overview = honest accurate analysis of all phones/people/numbers (owners-by-traffic, SIMs used, recovered contacts/aliases, accurate in/out comms, anomalies like C8, post-death usage, victim-not-owner). User principle: **fixes must be embedded in the real ingestion pipeline + bad data replaced — NOT delivered only as side scripts/exports.** [[feedback_fix_pipeline_not_side_artifacts]]
- **LOCKED SEQUENCE:** **P3** pipeline fix + backfill → **P5** Report tab (+endpoint) → **P4** number-alongside-name UI.
  - **P3 DESIGN:** (a) `neo4j_writer._ensure_person` STOP discarding names: accumulate per-key name set in-memory during the run (early-return currently drops repeat-sighting names — must record name+source even on cache hit, WITHOUT extra DB writes), at finalisation write `name_aliases` (union with existing cross-report) + recompute PRIMARY `name` preferring a real name over bare-number/JID/email (auto-fixes C7 bare-number, C8 mislabel). (b) `_write_contact` also CREATE a `ContactEntry` node per original record (exact name + numbers[raw+canon] + source[phone book/SIM/app] + account + model_id), `(:Person)-[:HAS_ENTRY]->(:ContactEntry)-[:EXTRACTED_FROM]->(:PhoneReport)` → gives view B (name as saved on device X); aggregate HAS_ENTRY → view A (all aliases for one number). (c) exclude non-personal ids (mail/notification/support/system-message) from alias rollup. (d) backfill script reuses the SAME writer methods over the 10 XMLs (no full reingest) to add ContactEntry+aliases+fix names onto existing Persons; comms/calls/locations untouched (validated accurate).
- **P3 PIPELINE FIX IMPLEMENTED (2026-05-26, UNCOMMITTED) — neo4j_writer.py + ingestion.py:**
  - `__init__`: `self._person_names: Dict[key,Counter]` (every real name a key is seen under, accumulated even on cache hit) + `self.identity_only=False` (backfill flag) + `contact_entries_created` counter.
  - Module helpers `_is_real_name(name,ident)` (rejects bare number/JID/email echoes, "_$!<…>", "(no name)") + `_is_personal_key(key)` (excludes notification/noreply/support/@facebookmail/system-message/@g.us from alias rollup).
  - `_ensure_person`: records name into `_person_names` BEFORE the in-run early-return (the early-return was why only first name survived).
  - `_write_contact`: captures `raw_phone_numbers` (as-saved) + calls new `_merge_contact_entry()` → MERGEs a **ContactEntry** node per address-book record (saved_name exact, raw_numbers, numbers, emails, contact_storage=Source[SIM/WhatsApp/phone book], account) with `(:Person)-[:HAS_ENTRY]->(:ContactEntry)-[:EXTRACTED_FROM]->(:PhoneReport)`, all MERGE/idempotent, edges written inline (one query) so they survive identity_only.
  - `finalise_person_identities()` (new, called as ingestion.py **Step 8.33** after finalise_sim_card): per key writes `name_aliases = apoc.coll.toSet(existing + seen)` + upgrades primary `name` to most-common real name ONLY if current is junk (bare#/JID/email/==key/`_$!<`). Never downgrades a good/owner name. Returns count.
  - `identity_only` mode: `_create_node` + generic `_create_relationship` become no-ops → backfill reuses the EXACT handlers to add names+entries WITHOUT recreating the 200k+ existing comm nodes/edges. apoc.coll.toSet verified available. Both files py_compile OK.
  - **Backfill `scripts/backfill_contact_identities.py`** (UNCOMMITTED): per report, writer.identity_only=True, run write_batch over all models + finalise_person_identities(). Idempotent. Run as conorbowles51 with NEO4J_* env. Reuses forensic_export.REPORTS map. case_id hardcoded 43f1afb1.
  - BEFORE state: phone-12404291127="Trabajo 444" no aliases; phone-12154068761="Es Moren Ke Esta Conel Nica" (a WRONG first-sighting primary; C6 saved it as Rosi/Rosy🍀) no aliases; 0 ContactEntry nodes.
  - **STATUS: C6 backfill RUNNING (bg cmd b53dg0z44).** On done: verify phone-12404291127 + phone-12154068761 now have name_aliases (all saved names) + sensible primary; ContactEntry count >0 for C6; spot-check HAS_ENTRY links. Then backfill the other 9. Then restart owl-backend so live app serves the fix (backend holds OLD writer in memory — only matters for NEW UI ingests, not reads). Then P5 Report tab + P4 number-alongside-name.
- **PERF: first C6 backfill (b53dg0z44) hit the 580s `timeout` (exit 143, incomplete but idempotent).** Optimized 3 ways (UNCOMMITTED, compile OK): (1) `@lru_cache(200k)` on `_generate_person_key` (libphonenumber ran 191k×; now ~unique-id×); (2) `_write_instant_message` identity_only fast-path = only From-party name accumulation, skips all prop building; (3) backfill filters to IDENTITY_TYPES {Contact,Call,Chat,InstantMessage,Email} so 80k+ Location/NetworkUsage/VisitedPage/Cookie models skip handler dispatch. Re-running C6 in bg WITHOUT timeout (cmd **bkhyd603n**), progress logged every 50k models.
- **C6 backfill #1 (bkhyd603n) COMPLETED OK** (13,004 entries, 6,349 persons, 0 err, 634s) BUT exposed a **major pre-existing keying bug** (see next). +12154068761 alias recovery worked perfectly (Rosi/Rosy🍀/…). 
- **🔴 BUG FOUND + FIXED: account-fallback conflation (neo4j_writer `_write_contact`).** Trabajo (phone-12404291127) got 119 ContactEntries + ~50 alias names that are OTHER people (Sarai/Julia/Karina Cordero — each a distinct Person). ROOT CAUSE: WhatsApp/Telegram contacts often have NO PhoneNumber entry, only a `UserID` JID (their real id, e.g. `13015563943@s.whatsapp.net`=Sarai). Old `best_id = first_valid_phone or phone_numbers[0] or (emails[0] if emails else account)` IGNORED user_ids and fell back to `account` = the address-book OWNER's WhatsApp id → **every number-less app contact keyed onto the device owner** (117 of 119 on C6). This bug is in the ORIGINAL ingest too — silently merged app contacts onto owners across ALL reports; ContactEntry layer made it visible. **= a big chunk of the "many missing contacts."** FIX: `best_id = first_valid_phone or phone_numbers[0] or user_ids[0] or emails[0]` — never `account`. (UNCOMMITTED, compiles.)
- **CLEANUP done:** deleted 13,004 C6 ContactEntries + cleared 6,349 name_aliases (only C6 was backfilled). Re-running C6 with the fix (bg **bhodyysi0**). Backfill `_ensure_person` MERGE will CREATE the correctly-keyed Person if missing → recovers the previously-merged contacts as their own identities; comms stay correct (incoming already linked to sender JID; only the address-book record was mis-merged).
- **C6 re-backfill w/ account-fix (bhodyysi0) VERIFIED CLEAN:** Trabajo phone-12404291127 aliases now just ["Esperosonal","Boda"] (2 legit entries w/ his real number) — was 50 strangers; "Sarai" ContactEntry now links to phone-13015563943 (her JID), not owner; 13,004 entries, 6,360 persons, 0 err, 588s.
- **✅ P3 COMPLETE (all 10 backfilled, 0 errors):** 28,824 ContactEntries case-wide; 384 persons w/ >1 recovered alias; account-fallback bug fixed. Owners now named: C7 phone-14105010984="Mtant"/[Mtant,Juan Rivera]; C8 phone-13015416552="Bryan"/[…,Bryan,Ili]. Per-device entries: C1=3976 C1b=2937 C2=2297 C3=1610 C4=2552 C5=1516 C6=13004 C7=462 C8=239 C9=231.
- **⚠️ owl-backend NOT yet restarted** — holds OLD writer in memory; only affects NEW UI ingests (graph reads see corrected data). Plan: ONE restart after P5 backend endpoint is added. `sudo systemctl restart owl-backend` (--workers 1, ~35s).
- **✅ owl-backend RESTARTED** (active) — P3 pipeline fix + new endpoint now live. owl-frontend active.
- **✅ P5 BUILT + DATA-VALIDATED (2026-05-26, UNCOMMITTED) — "Report" tab beside Overview:**
  - Backend: `neo4j_service.get_cellebrite_device_report(case_id)` + endpoint `GET /api/cellebrite/report/devices` (cellebrite.py). Per-device: identity (label/model/examiner/IMEI), declared_owner (BELONGS_TO) vs **primary_user by traffic** (top SENT_MESSAGE sender, EXCLUDING System Message, PREFERRING a sender whose key ∈ device's own numbers → `matches_device_number` flag), owner aliases (name_aliases), device_numbers, messages, calls in/out, contact_entries, locations, activity_first/last.
  - VALIDATED via direct call — all 10 owners correct + [OWN#]: C1 Alexis Andrade, C1b "Y13 ??"(Carlo), C2 3014420513, C3 Sender Lemus, C4 🤑, C5 Pefro, C6 Trabajo 444 (57361 sent), C7 Mtant, C8 Bryan, C9 Vides Martinez. Endpoint live (curl 401=registered).
  - Frontend: `CellebriteReport.jsx` (table: Device | Primary user[+device#/inferred badge, number, ingest-label mismatch flag] | Contacts | Messages | Calls in/out | Activity window; expandable row → device numbers+IMEI, all saved aliases, counts). Wired into CellebriteView TABS (key 'report', after overview) + TabPane + `cellebriteAPI.getDeviceReport`. All 3 files esbuild-clean. Number shown beside name (partial P4 already).
- **✅ P5 VERIFIED IN-BROWSER (2026-05-27, puppeteer):** logged in via minted token (auth_service.create_access_token{sub:oferreira@…}), opened case "OPDMD28 - Sender Godoy Lemus" (=43f1afb1), Cellebrite view → Report tab renders beside Overview with all 10 devices, DEVICE# badges, numbers beside names, counts, activity windows; row-expand shows numbers/IMEI/aliases. Screenshots /tmp/v3_report_tab.png, v4_report_expanded.png. CAUGHT: live endpoint was serving STALE owner logic (backend restarted before the owner-query improvement) → restarted again, now correct. NOTE device labels use investigator overrides (e.g. "C9 - Jonathan Vides Martinez", "C2 - Sender Godoy Lemus"). FINDING: C2 / C1b owner display = bare number ("3014420513" / "Y13 ??") since the owner's own number has no clean saved name — honest but ugly; consider a "(device owner — unnamed)" fallback in P4 polish. Pre-existing unrelated console errors on workspace load (Failed to load snapshots / Setup status check / EntitiesPanelSection) — not from Report tab.
- **✅ P4 IMPLEMENTED (2026-05-27, UNCOMMITTED) — number alongside name:**
  - New shared `frontend/.../cellebrite/shared/PersonName.jsx`: `phoneFromKey(key)` (phone-<digits>→+digits) + `<PersonName name personKey numbers>` renders "name +number"; bare-number-name → "(unnamed)".
  - Applied to the name-without-number gaps: OverviewMessagesView (Sender col), OverviewCallsView (From/To cols), comms `CommsContactTable.PersonCell` (sender/recipient cells), and CellebriteReport primary-user (bare-number → "(unnamed)", number from numbers||phoneFromKey(key)).
  - Already-compliant surfaces left as-is (number already shown): UnifiedContacts (number col + alias chips), CommsContactDrawer (phone chips under name), CommunicationView (phone column). Filter chips (CommsEntityFilter/ParticipantsFilter) deliberately not cluttered with numbers — revisit if user wants.
  - All 5 changed files esbuild-clean.
- **✅ P4 VERIFIED (2026-05-27, puppeteer):** Report tab C2 now reads "(unnamed)" + clean "+13014420513" + "labelled 'Dsnt' at ingest" mismatch flag. Fixed: bare-number detection now phone-format regex (not exact match — "3014420513" missing country code wasn't matching); number derived from phone-<digits> KEY first (pu.numbers[0] held junk MSISDN text "mobile number is 13014420513"). PersonName + CommsContactTable.PersonCell use same key-first + phone-format-regex logic. FINDING: device-report endpoint slow (~2-3s, ~40 per-device aggregate queries) → tab shows "Building device report…" briefly; consider batching the per-device queries into one if it bothers users.
- **P5 OWNER-LOGIC REDESIGN (2026-05-27) — user flagged "(unnamed)" + "System Message as primary user" as red flags.** Investigated: live Report had NO System Message (user likely saw pre-restart state); but the volume-based heuristic WAS fragile + "(unnamed)" ignored available real names. FIXES (neo4j_service.get_cellebrite_device_report + CellebriteReport.jsx):
  - **assigned_owner** NEW field = investigator's device_name_override with "C#[.x] - " prefix stripped (C2→"Sender Godoy Lemus", C7→"Edgar Castro Contreras", etc.) = GROUND TRUTH custodian. Report LEADS with this; never "(unnamed)".
  - **Dominant-user-by-traffic selection redesigned**: ORDER BY is_own DESC, **named DESC**, sent DESC — among own-number senders prefer one with a REAL (non-numeric) name, then volume. Fixes C2 (now "Dsnt" not unnamed "3014420513") AND keeps C6 "Trabajo 444" (named + 57k dominates). Deliberately does NOT use Person.is_phone_owner (over-flagged: on C6 it's on "Mry"/51msgs not Trabajo/57k who isn't flagged). System Message excluded.
  - Frontend: Owner column leads with assigned_owner (+"assigned" badge), shows owner number + device#/inferred badge beneath, and an amber **"traffic dominated by '<name>'"** flag when the dominant traffic identity is a clearly different person (e.g. C6 assigned "Gloria Esperanza Lol (Pimp Ops)" but traffic=Trabajo 444 — real forensic signal). Removed the old declared-owner mismatch flag (assigned_owner supersedes it). Header → "Owner / dominant user".
  - VALIDATED direct: all 10 have assigned_owner + named traffic owner (C2=Dsnt, C6=Trabajo, etc.). Backend restarted (bg brioojkf3). Re-verify in browser pending.
- **✅ OWNER-LOGIC REDESIGN VERIFIED in-browser (2026-05-27):** Report leads with assigned owners (Jonathan Vides Martinez, Brayan Alexis Bonilla Andrade, Sender Godoy Lemus, Carlos Yaque Del Cid, Gloria Esperanza Lol, Edgar Castro Contreras, etc.) + ASSIGNED/DEVICE# badges + amber divergence flags: C2 "traffic dominated by 'Dsnt'", C6 "traffic dominated by 'Trabajo 444'" (Gloria-assigned). NO "(unnamed)", NO "System Message". Screenshot /tmp/v3_report_tab.png. Backend live.
- **✅ COMMITTED 2026-05-27 (Neil B <thenofisamizdat@gmail.com>, branch main, NOT pushed):** 8510947 contact-identity ingest fix (ContactEntry+aliases+account-fix+Step8.33+models.manual_owner_name), 3db57f3 forensic_export+backfill scripts, 864d7fa Report endpoint, 1a323b6 Report tab UI + number-alongside-name, 8145f6a bulk_register_c9 helper. git user.name/email set to Neil B in repo .git/config. Only .claude/* + WORKING.md left uncommitted (intentional). NOT pushed (matches prior workflow; push only if user asks).
- **✅ MERGED origin/main (2026-05-27, commit 0dfa86f):** remote pushed 13 Cross-Phone Graph + selection-rail UI commits (ed9cc54..5bca0a8). CLEAN auto-merge — only `backend/services/neo4j_service.py` overlapped (remote graph-ranking helpers _fold/_cypher_fold/_person_where/_resource_where vs my get_cellebrite_device_report — different functions, auto-resolved). Frontend ZERO overlap (remote touched CrossPhoneGraph/CommsCrossType*/rail; I touched CellebriteView/api.js/Report/Overview/CommsContactTable). Backend py_compile OK, both /report/devices + /cross-phone-graph return 200. In-browser (puppeteer /tmp/verify_merge.cjs): Report tab=10 rows, Cross-Phone Graph=1,410 nodes + canvas, no error boundary. Only console noise = pre-existing benign validateDOMNesting in EntitiesPanelSection (not our files). Screenshots /tmp/m_report.png, /tmp/m_graph.png.
- **✅ PUSHED to origin/main (2026-05-27): 5bca0a8..0dfa86f.** origin hadn't moved since fetch (clean push). main == origin/main == 0dfa86f. Integrated state (contact-identity fix + Report tab + number-alongside-name + remote graph UI) now on remote.
- **2026-05-27 — AUDIO/MEDIA IN COMMS CHAT VIEW (diagnosed):** UI + backend FULLY support audio (inline <audio>)/image/video (CommsMessageBubble→CommsAttachment; thread queries include media-only msgs). BUT attachments only RENDER where evidence rows are tagged with cellebrite_file_id = media-registration Step 9, done ONLY for C1/C3/C5/C7. For C6/C8/C2/C4/C9/C1-06304890 (Step 9 skipped on fast CLI ingest) `_resolve_attachments`→`evidence_storage.get_by_cellebrite_file_ids` returns nothing → attachments come back missing:true → bubbles show but audio/media unplayable. PROVEN: C6 sample 0/4 file_ids resolve, C5 3/4 resolve. C6 (Trabajo) has **11,438 msgs with attachments** currently unviewable. Files ARE on disk (bulk-registered 996,307 rows) — Step 9 just never tagged cellebrite_file_id. FIX = run deferred media-registration (Step 9) for the 6 reports: standalone batched register_media_files (no graph re-ingest) OR re-run roots WITHOUT CELLEBRITE_SKIP_MEDIA_REGISTRATION=1 (~40min each, rewrites 1GB evidence.json). See [[project_cellebrite_ingestion_failures]] for the skip-media history.
- **2026-05-27 — RUNNING media-registration Step 9 for the 6 skipped reports (user approved).** New `scripts/register_media.py` (UNCOMMITTED): standalone Step 9 — parse report → CellebriteFileLinker → build_model_file_map → register_media_files(evidence_storage, owner=oferreira@…, model_file_map). Concurrency-SAFE with live backend: register writes via evidence_storage._file_locked (reload-mutate-save); backend reads call _refresh_if_stale (mtime) so it picks up tags WITHOUT restart. Backed up evidence.json → data/evidence.json.pre-mediareg-20260527-021055 (1.1G). RAM ~9-11G avail + swap, backend healthy 200 during run.
  - **C6 RUNNING (bg b70hgr210)** — first report. Parses 213k models then registers (~11,438 attachment msgs; dedups by sha, upserts cellebrite_* onto existing bulk-registered rows). Verify on done: C6 sample file_ids [6cfe0586…, ccadbb3f…, e73d6385…, 1def4afe…] now resolve via get_by_cellebrite_file_ids (were 0/4), then browser-check C6 chat shows audio/media.
- **2026-05-27 — FIXED unified-contacts per-device names (user: "didn't work AT ALL" on Trabajo).** DIAGNOSIS: backfill DID work — ContactEntry has rich per-device names for +12404291127 (C1=Trabajo 444, C2=J/~J, C3=Maitria, C5=Lan Chita, C6=Esperosonal/Boda, C8=Doñita). The VIEW was wrong: `get_unified_contacts` built per-device "Known as" from the single rolled-up Person.name + comm-span, so every device showed "Trabajo 444". FIX (neo4j_service.get_unified_contacts): new query loads ContactEntry (saved_name, source report) per person; alias-building now uses those per-device saved names (each alias's report_keys = the device it was SAVED on), falling back to Person.name+comm-span only for identities with NO ContactEntry. Frontend UnifiedContactAccordion devicesIndex deduped. VERIFIED live: endpoint now returns per-device varied names (C3 Maitria, C5 Lan Chita, C8 Doñita…). Backend restarted. UNCOMMITTED: neo4j_service.py, UnifiedContactAccordion.jsx. NOTE: same fix improves the Contacts-tab AliasChipGroup ×N chips too.
- **2026-05-27 — LOCATION COVERAGE GAP found (user: "thousands of locations missed on ingestion, capture EVERY location").** Location MODELS are fully ingested (C2 graph 42,717 ≈ XML 42,607; C6 18≈17 — Android extractions are genuinely lean). REAL GAP via parser audit (/tmp/loc_audit.py on C2): **WirelessNetwork models carry a coordinate (24,047 of 24,390 in C2) that `_write_wireless_network` DROPS** — only `_write_location` materialises coords. Also CellTower 856 (stored as cell-tower layer not map Location), SearchedItem 17. Case-wide ~25k WiFi geolocations not captured as Locations. Graph confirms: only Location + CellTower nodes carry latitude. FIX PLAN: (a) pipeline — every coordinate-bearing model also yields a Location point tagged by source (WiFi/Cell/Search); (b) backfill — re-parse each report XML and MERGE Location nodes from those coords (idempotent, like harvest_geotags; no re-upload). NUANCE: WiFi "known network" coords can be approximate/stale (Apple crowd-DB) — tag location_type='WiFi' so investigators see the source. SECONDARY: locations list/table view caps at limit=5000 (CellebriteLocations getEvents) though tiles aggregate all — raise/paginate.
- "UNKNOWN ERROR loading locations" = almost certainly TRANSIENT: all location endpoints return 200 w/ data (events 4MB, tiles, tracks); no 500 in backend log (only benign nearest_location_lat/lon property-key WARNINGS). Cause = requests landing during my repeated backend restarts + media-reg RAM pressure → proxy 502 → non-JSON → api.js "Unknown error". Resolves once restarts/media-reg settle.
- FIXED this session: unified-contacts per-device names (ContactEntry-sourced) + AliasChipGroup duplicate-key (key=`${a.key}::${a.name}`) + UnifiedContactAccordion devicesIndex dedup.
- **"10% significant locations" memory RESOLVED:** no location sampling exists in code (SKIPPED_MODEL_TYPES empty; Location models 99.9% ingested). The ~10% the user recalls = the ActivitySensorData summarisation (172k motion Measurement/Sample children → 17,082 MotionActivity windows) — but that's iOS CoreMotion ACTIVITY (stationary/walking/driving), NO GPS (_write_motion_activity reads "Measurements" motion metrics, not coords). So NOT dropped locations. The REAL gap is WiFi/cell/search coords (~25k case-wide, confirmed C2 audit).
- **DECISION (user 2026-05-27): capture ABSOLUTELY EVERY location point, tagged by source (option 1) + pipeline-fix-then-backfill.** BUILD = a GENERAL coordinate harvester (don't enumerate sources & risk missing one): for ANY parsed model carrying a coordinate (direct lat/lon, "Position" child, or nested Coordinate) that isn't already a Location, MERGE a Location node (key `loc-<src>-<model_id>`, location_type=source label e.g. WiFi/Cell Tower/Search, lat/lon, timestamp, CONTAINS from report + WAS_AT from owner). Pipeline: new orchestrator step calling writer.harvest_all_coordinates(models). Backfill: standalone re-parse each XML + harvest (idempotent MERGE, like harvest_geotags; no re-upload). Also raise the locations list view limit=5000 / paginate. coord_of() logic proven in /tmp/loc_audit.py.
- **✅ LOCATION HARVESTER BUILT + VALIDATED (2026-05-27, UNCOMMITTED):** neo4j_writer `_extract_coord()` (lat/lon from direct field / Position child / any nested Coordinate-or-latlon child) + `harvest_all_coordinates(models)` → MERGE Location node per coord-bearing non-Location/non-CellTower model, tagged location_type=<src> (WiFi/Search/Journey/…) + location_source_model, geocoded, CONTAINS from report + WAS_AT from owner. Counter harvested_coords_created in get_stats. Pipeline: ingestion.py **Step 8.36** (before CONTAINS sweep). Backfill: `scripts/backfill_locations.py` (re-parse XML, idempotent MERGE, memory-bounded per-batch streaming; GEOCODER=geonames). VALIDATED on C9: 2 WiFi points created, location_type=WiFi, geocoded Gaithersburg, CONTAINS+WAS_AT present. All py_compile OK.
- **STATUS: full location backfill RUNNING (bg b7c2ydxsq): C1 C1b C2 C3 C4 C5 C6 C7 C8** (C9 already done). C2 is the big one (~24k WiFi points). media-reg C6 (b70hgr210) STILL running concurrently — both memory-bounded; RAM 14G avail, watch it.
- **✅ ROOT CAUSE of "locations look sparse / trajectory less comprehensive" = the 5000 CAP (user confirmed: filtering to C2 alone revealed the rest).** CellebriteLocations.jsx getEvents passed `limit:5000` — split across all 9 selected devices, location-dense phones (C2 ~42k) were starved. FIX: frontend limit 5000→500000 (backend /events already allows le=500000; get_cellebrite_events has no lower internal cap). VERIFIED: events endpoint returns 52,001 for C2 at limit=500000 (was capped 5000). Frontend esbuild OK; Vite HMR (no backend restart needed). NOTE backend hard-ceiling 500000 (far above current ~69k); honors no-silent-truncation for any realistic case.
- **Location harvester backfill (b7c2ydxsq) progressing:** C1=1, C1b=0, C2=3289+ (running). Location count 44k→50,575+ and climbing. media-reg b70hgr210 still running.
- **✅ PER-DEVICE NAMING NOW IN COMMS CENTER (2026-05-27):** user: contact/identity fix worked in Unified Contacts but not Comms Center (thread list showed "Trabajo 444" on every device). FIX = single backend resolver `neo4j_service.device_contact_names(case_id)` → {(person_key, report_key): saved_name} from ContactEntry (120s TTL cache, 16,450 pairs). Applied at comms chokepoints: get_cellebrite_comms_threads (chat participants + call-pair a/b names, resolved vs thread's report_key), get_cellebrite_thread_detail (message sender names + participants). VERIFIED live: C3 threads now show Trabajo as "Maitria" (chat+call). CONSISTENCY MODEL: device-context views (threads/messages) = per-device saved name; case-wide identity selectors (Participants filter, Unified Contacts header) = canonical name + aliases (correct — they pick the identity, not a per-device label). Backend restarted.
- **✅ PER-DEVICE NAMING EXTENDED to contact-feed (2026-05-27):** get_contact_comms_feed now resolves call src/dst, message sender, email sender/recipient names via device_contact_names per item's report_key (`_nm()` helper). VERIFIED: Trabajo shows as "Maitria" on C3 feed. So per-device naming now covers thread list + thread detail + contact feed. comms/entities (case-wide entity FILTER) deliberately left canonical+aliases (identity selector, not device display — correct).
- **✅ C6 MEDIA-REGISTRATION DONE (b70hgr210, 5868s):** resolved_files=102,499, media_registered=55,478. C6 sample attachments now resolve 4/4 (were 0/4) → C6 audio/media will render in comms chat. Backend auto-refreshes evidence.json (no restart needed for resolution; restart already happened for code).
- **✅ LOCATION HARVESTER CONFIRMED CORRECT:** C2 harvested 24,038 WiFi/Search points (≈ audit's 24,047; delta = 0,0/out-of-range filter). Verified _extract_coord works on iOS C2 WiFi (388/400 sampled found; 12 misses are WiFi w/ no location). Total locations 44,136 → 68,200 and climbing. The earlier "3289 by 100k models" was just stream ordering (WiFi appear later in C2's stream), NOT a bug.
- **STATUS (2026-05-27): two bg jobs running:** location backfill b7c2ydxsq (finishing small reports C3-C8 after C2) + media-reg b74oiiy6e (C9 C8 C1b C4 C2 — multi-hour, ~98min each for big ones). RAM 19G.
- **✅ LOCATION BACKFILL COMPLETE (b7c2ydxsq):** C2=24,064 harvested, C4=40, C6/C7/C8/C9 a few, others 0. Total locations 44,136 → 68,252 (+24,116 WiFi/Search). 
- **✅ COMMITTED (Neil B, branch main, 2026-05-27):** 06f10d0 per-device contact naming across comms (device_contact_names + threads/thread-detail/contact-feed + get_unified_contacts per-device + AliasChip/devicesIndex fixes); 09bd9a8 capture every location (harvest_all_coordinates + Step 8.36 + backfill_locations.py) + remove 5000 cap; 2a98a3d register_media.py. NOTE owner-redesign (assigned_owner) was already absorbed into merge commit 0dfa86f (pushed). Only .claude/* + WORKING.md left uncommitted.
- **⚠️ NOT PUSHED:** local main ahead of origin by 06f10d0/09bd9a8/2a98a3d. origin/main==0dfa86f. Push when user asks.
- **bg media-reg b74oiiy6e RUNNING:** C9 C8 C1b C4 C2 (multi-hour, ~90min each for big iOS). On done: those phones' chat attachments resolve.
- **NEXT ACTION (on resume):** offer push to origin. media-reg b74oiiy6e finishes → verify attachments resolve for C8/C2/C4/C9/C1b. Everything else done + verified.
- **NEXT ACTION (on resume):** (1) confirm user sees per-device names in Comms Center + full locations (cap removed). (2) bg jobs: location backfill b7c2ydxsq (C2 ~24k WiFi) + media-reg b70hgr210 still running — verify on done, run media-reg other 5. (3) COMMIT batch: unified-contacts per-device fix, AliasChip/devicesIndex dedup, register_media.py, location harvester, locations cap removal, comms device_contact_names resolver. prior commits = Neil B <thenofisamizdat@gmail.com>. (await user authorship; prior commits = Neil B <thenofisamizdat@gmail.com>). UNCOMMITTED files: scripts/forensic_export.py, scripts/backfill_contact_identities.py, ingestion/scripts/cellebrite/{neo4j_writer,ingestion,models}.py, backend/services/neo4j_service.py, backend/routers/cellebrite.py, frontend/src/services/api.js, frontend/.../cellebrite/{CellebriteReport.jsx(new),CellebriteView.jsx,shared/PersonName.jsx(new),overview/OverviewMessagesView.jsx,overview/OverviewCallsView.jsx,comms/CommsContactTable.jsx}.

## ✅ ALL INGESTIONS COMPLETE 2026-05-26 — status check, nothing running
All 10 reports are in Neo4j (per-report :CbNode counts, verified live 2026-05-26): C6=240,050, C2=129,577, C4/bundle=114,834, C1-06304890=46,389, C8=39,405, C5=37,989, C7=28,754, C3=18,818, C1=10,766, C9=6,269. No ingestion processes running; owl-n4j idle ~1% CPU. Host healthy: 18G used / 12G avail, swap only 7G/31G (swap fix holding). C9 + C1-06304890 finished AFTER the older notes below were written — both success, 0 write_errors (logs `data/ingest_c9.log`, `data/ingest_c1-06304890.log`).
- **NEXT ACTIONS (deferred, both still open):**
  1. **Media-registration (Step 9)** for C6/C8/C2/C4/C9/C1-06304890 — user will do "a bit later". Only C1/C3/C5/C7 have EXIF/geotag enrichment. Run a standalone batched `register_media_files` pass per report (no graph re-ingest) OR re-run those roots WITHOUT `CELLEBRITE_SKIP_MEDIA_REGISTRATION=1` (~40min each, rewrites 1GB evidence.json). Needed only for Tier-2 LLM media analysis.
  2. **Commit the uncommitted code** (awaiting user authorship call): `backend/services/geocoder.py` (mode=1), `ingestion/scripts/cellebrite/neo4j_writer.py` (:CbNode + harvest_photo_geotags), `ingestion/scripts/cellebrite/ingestion.py` (skip-media gate + Step 8.35), scripts `bulk_register_reports.py` / `bulk_register_c9.py` / `ingest_one_report.py` / `harvest_geotags.py`. DO NOT commit `.claude/*` or `WORKING.md`.

## C9 FAST-REGISTER 2026-05-25 ~22:1x UTC (DONE) — replaced a slow UI upload with bulk-register
A 9th report **C9** (`220029502_06310028_C9_2023-03-02_Report`, 29,107 files, owner oferreira@, case 43f1afb1) was uploading via the UI at **~2.4 files/s (~2.3h ETA)** — pure registration grind: evidence.json is now ~1.06GB and gets fully rewritten every 100-file batch (backend pegged ~1 core on json.dumps). All 29,107 C9 files were already on disk (10,200 case-dir + 18,907 `_staging/cbca0ed5…/_extracted`). User approved the proven morning path. STEPS DONE:
- Backups: `data/evidence.json.pre-c9register-20260525-220805` (1.06GB) + `background_tasks.json.pre-c9register-…`.
- `systemctl stop owl-backend` (halted the live upload PID 942366; evidence.json frozen). Only unrelated v2 stack `:8002` left running.
- `cp -aln` hardlinked staging `_extracted/C9` → case dir → case-dir C9 = **29,107** files exact.
- New `scripts/bulk_register_c9.py` (clone of bulk_register_reports.py, REPORTS=[C9]) run as conorbowles51: hashed 29,107 in **28s**, ONE locked write — dropped 13,100 partial rows, inserted **0 primary + 29,107 duplicate**. evidence.json 1,204,223 → **1,220,230 rows**. NOTE: 0 primary = every C9 sha already on platform — C9 also fully on disk under a DIFFERENT case `d83fe4a4-dd52-4760-9c43-ab0dee82f050` (29,651 files); it was uploaded there before. All 29,107 case-43f1afb1 rows still created (per-case views), each is_duplicate→primary in d83fe4a4. Flagged to user whether 43f1afb1 was intended.
- Marked task `6a3eb52e` **completed** (29,107/29,107) in background_tasks.json with `finalized_by` note.
- Removed staging dir `cbca0ed5…` (389M of hardlinks; case-dir data survives via inode refcount). Disk 122G free.
- **owl-backend restarted** (--workers 1, active, listening :8000, returns 401 on authed endpoints = serving). owl-frontend was NOT stopped this round.
- `scripts/bulk_register_c9.py` is UNCOMMITTED (one-off helper, same class as bulk_register_reports.py).
- **C9 GRAPH INGEST — ✅ DONE 2026-05-25 23:43 UTC** (task 673e8b99, log `data/ingest_c9.log`, skip-media): RESULT_STATUS success, 0 write_errors, 6,322 nodes (graph shows 6,269 labeled — delta = shared Person MERGE). `duplicate=True` (C9 already on platform under case d83fe4a4). Geotag harvest via Step 8.35 ran inline. Media-registration (Step 9) NOT done (skip-media) — deferred with the others.

## IDENTITY-MERGE ACTION + CLEANUP 2026-05-25 (DONE, pushed)
- **Merge-identities action** (for the multi-number same-person case auto-resolution can't safely handle): `neo4j_service.merge_person_identities(case_id, primary_key, secondary_keys, actor)` (apoc.refactor.mergeNodes, records merged_from/aliases/merged_by/merged_at) + `POST /api/cellebrite/persons/merge` (evidence-write guard). Frontend: `MergeIdentitiesDialog.jsx` (new) + button in `ContactDetailDrawer` header + `api.mergePersons`. Accepts keys or bare numbers. Verified: round-trip merge moves rels + records provenance; endpoint 401 (registered). Commits daff34a / (backend). Backend restarted (health 200).
- **Group-JID cleanup**: deleted stray `whatsapp-statusbroadcast` ("status@broadcast") Person node (WhatsApp status pseudo-address, not a person; degree 4). One-off graph fix, no code.

## CONTACT FRAGMENTATION + CAP 2026-05-25 (DONE, committing) — key contact appeared to lose conversations
User: contact "Trabajo 444 / Maitria" +1 240-429-1127 (ordered the hit) showed only one phone of conversations; suspected wipe loss + 5000 cap. INVESTIGATED — NO DATA LOST. Root causes:
1. **Identity fragmentation**: her WhatsApp JID `12404291127@s.whatsapp.net` was keyed as a separate `email-` Person node (72k rels) from `phone-12404291127` (465). `_generate_person_key` saw the `@` → email branch. Case-wide this stranded **1,149 WhatsApp nodes / 147k rels**. (Also her alt numbers 13014589977 "27 Maitra" / 12026000064 "Maitro" are DIFFERENT numbers — NOT merged, zero shared counterparties, no evidence same person.)
2. **Contact-feed cap**: `comms/contact-feed` capped at 1000/5000 + hardcoded per-type LIMIT 2000/4000/1000, and computed `total` AFTER capping (under-reported). Hid >90% of a 110k-event thread.
FIXES (committing as Neil B):
- **Parser** (neo4j_writer.py `_generate_person_key`): WhatsApp/messaging JIDs `<digits>@s.whatsapp.net|@c.us` now key to phone identity. IMPORTANT: prepend `+` (parse as E.164) — JIDs carry full intl number; region-US parsing rejected 410 Salvadoran/UK/etc numbers on first merge pass.
- **Backfill** `scripts/merge_whatsapp_identities.py`: apoc.refactor.mergeNodes merged **1,141/1,149** WhatsApp nodes into phone identities (8 left = junk `0@` / non-validatable +521 legacy-Mexican / odd-length Cameroon, ~30 rels). Her `phone-12404291127` now degree 72,936; contact-feed TRUE total **110,956** events across 6 phones, 429 counterparties.
- **Cap removed** (neo4j_service.get_contact_comms_feed + cellebrite.py:1308): per-type LIMIT→$fetch_cap(offset+limit), endpoint le 5000→200000 default 2000, returns TRUE uncapped `total` + `truncated` flag (no silent truncation). ALSO rewrote all 3 fetch + 3 count queries to traverse FROM the person (CALL{} UNION) instead of scanning all Communication/PhoneCall/Email — the merged 72k-degree node made the old scan time out; now 2.9s.
- Backend restarted (health 200). VERIFIED: her feed returns 110,956 total, fast, truncated=True.
- KNOWN MINOR: 8 non-validatable WhatsApp JIDs unmerged (~30 rels); +521 legacy-Mexican mobile format not handled by libphonenumber is_valid — revisit if a Mexican contact matters.

## APP-EVENT COVERAGE EXPANSION 2026-05-25 (DONE, committed, pushed)
User: app-based events missing from Locations & Events / Timeline, asked if other types were missed. Exhaustive enumeration of all 54 model types across all 9 reports vs SUPPORTED found 12 dropped top-level types (217k instances); audit had been stale (ran on C3/C5/C9 before the iOS/Android reports C2/C4/C6/C7/C8 were uploaded). Added handlers + ingested (user approved all + motion windows-only):
- **62,096 event nodes backfilled** (no re-ingest) via `scripts/harvest_app_events.py`, exact XML parity: MotionActivity 17,082 (ActivitySensorData windows, summarised — NOT the 172k raw Measurement/Sample children), LogEntry 16,311, Cookie 10,115, AppSession 9,304 (AppsUsageLog 8,960 + ApplicationUsage 350), DeviceConnectivity 4,083, FileUpload 3,332, SocialMediaActivity 1,006, ChatActivity 775 (nested under Chat>ActivityLog — pulled in _write_chat), Journey 75 (57 geolocated via waypoints), Note 13.
- Pipeline fixed for FUTURE ingests: 10 types added to SUPPORTED (parser.py), handlers+counters+stats (neo4j_writer.py), event-center surfacing (neo4j_service.py get_cellebrite_events + /events/types + indexes), and **UNKNOWN-TYPE GUARD** (ingestion.py logs loud `UNKNOWN MODEL TYPES dropped` warning for any top-level type not in SUPPORTED∪SKIPPED — stops silent coverage drift).
- Verified live: /events/types returns all 19 event types with counts. Backend restarted (health 200), frontend active.
- COMMITS (Neil B): ce26c9f ingest+guard, cc43542 event-center, 89b7a2f backfill script. **Pushed to origin/main** after rebasing onto teammate Neil Byrne's 6 swim-lane/email/calls commits (0fb9dbe) — clean rebase, neo4j_service.py auto-merged (different sections), compiles. Backend now runs the merged code.
- NOTE: AppsUsageLog + ActivitySensorData were ALL in C4 (iOS). ChatActivity spread across C1/C2/C3/C1-06304890. SocialMediaActivity in C2/C6/C8.
- DEFERRED: 172k ActivitySensorDataMeasurement/Sample raw children intentionally NOT materialised (summarised onto MotionActivity windows); raw samples remain in report XML if ever needed.

## GEOCODER mode=2 PERF BUG 2026-05-25 — fixed (was collapsing location-dense ingests to <1 model/s)

C2 (iOS APPLE_IOS_FULL_FILE_SYSTEM, location-dense) crawled at **0.75 models/s** (~23h ETA) while Neo4j sat at 2% CPU. py-spy on the worker showed it pinned at 80% CPU inside `reverse_geocoder/cKDTree_MP.py` multiprocessing fork/join — `services/geocoder.py` built the geonames backend with `RGeocoder(mode=2)` (multi-process query) and called `.query([single_coord])` once PER Location node. mode=2 forks a worker pool on EVERY call → forking the 3.7GB process tens of thousands of times. **FIX (backend/services/geocoder.py): mode=2→mode=1** (in-process k-d tree, no fork) + per-coord result cache (round 4dp; cellebrite locations cluster). Verified: 5000 lookups 0.009s (573k/s) vs ~1s/call before; first call 1.0s one-time tree build. **UNCOMMITTED.** Affects ALL geocoding (backend Location ingest + harvest_geotags). C2 was KILLED mid-run (49,545 partial nodes) + RELAUNCHED on fixed code (task b7b72c54): force=True duplicate-delete wiped the partials, now writing at **~115 nodes/s**. C2 now also self-harvests its 211 geotags via Step 8.35 (fresh process = new code). Add `backend/services/geocoder.py` to the commit list.

## GEOTAG LEAK 2026-05-25 — geotags present in XML but NOT persisted (root-caused, recoverable, NOT a parser bug)

User flagged near-zero geotagged media. Investigated. Geotag coordinates ARE in every report's `<taggedFiles>` XML (verified: C1=0 genuinely, C3=23, C5=99, C7=2 `MetaDataLatitudeAndLongitude` items, all INSIDE taggedFiles). But only C5's 99 persisted to evidence rows. Three independent causes, NONE the EXIF parser (parser works — C5 got 99/99):
1. **C3** — its 23 GPS-bearing tagged file_ids have ZERO evidence rows (`found=0` by `cellebrite_file_id` in evidence.json) despite binaries being on disk (23/23 by basename). Geotag is only persisted as a side-effect of media-registration attaching EXIF to a media evidence row; those 23 tagged files never resolved into `_resolved_paths` → registered set, so coords dropped. Same code as C5.
2. **C7** — bulk_register_reports.py (2026-05-25) DROPPED + reinserted all C7 rows as plain rows (no EXIF); SHA re-patch by later full-pipeline run didn't restore coords → 0.
3. **C6/C8/bundle** — media-registration skipped (skip-media gate) → never attached.
**Why checks missed it:** every check verified the PARSER (correct EXIF tag names), validated on C5 where resolution worked (99/99 looked healthy). Never asserted `geotags-in-XML == geotags-persisted`. Persistence path (media-registration) is exactly the step skipped/clobbered this week.
**Recoverable:** coords live in XML, don't need the binary. PROPER FIX = harvest geotags straight from `<taggedFiles>` into graph (photo→Location) independent of binary resolution + run across ALL reports + add XML-vs-persisted parity assertion.

**[BUILT + VALIDATED 2026-05-25] `scripts/harvest_geotags.py`** (user approved, NO reingest needed). Reuses the validated parser's `parse_tagged_files()` to read GPS direct from `<taggedFiles>`, MERGEs one `Location` node per geotagged photo (key `loc-photo-<file_id>`, `location_type='Photo'`, `:CbNode`), reverse-geocodes (geonames), links `(:PhoneReport)-[:CONTAINS]->(l)` + `(:Person owner)-[:WAS_AT]->(l)`. Idempotent MERGE. `--check` = parity-only, exits non-zero on any XML-vs-graph mismatch (the guard). RUN AS: `sudo -u conorbowles51 env GEOCODER=geonames NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=testpassword venv/bin/python scripts/harvest_geotags.py [--check] [report_root ...]` (backend-first sys.path + NEO4J_*/GEOCODER in env — backend/config.py reads them from env). UNCOMMITTED.
- PARITY CHECK across all 9 reports found **365 geotagged photos in XML, 0 in graph** — quantified the full leak. Per report: C2=211, C5=99, C3=23, C8=21, C7=5, C4(bundle)=4, C6=2, C1=0, C1-06304890=0.
- HARVESTED (parity OK, verified nodes have lat/lon + geonames place_name + CONTAINS + WAS_AT): C6=2, C3=23, C5=99, C7=5, C8=21 → **150 geotags now in graph** across the 6 ingested reports.
- PENDING: C2 (211) + bundle C4 (4) — harvest AFTER they finish ingesting (need PhoneReport node for CONTAINS). Then run `--check` (no args) as the final gate; expect 369 xml == 369 graph, 0 mismatches.
- **[DONE 2026-05-25] WIRED INTO ORCHESTRATOR** (user approved). New `CellebriteNeo4jWriter.harvest_photo_geotags(tagged_files)` (neo4j_writer.py, before `link_all_to_report`) + counters `photo_geotags_expected/created` in `__init__` + both in `get_stats`. New orchestrator **Step 8.35** (ingestion.py, before Step 8.4 CONTAINS) calls it ALWAYS (reuses Step-3 tagged_files, not gated by skip-media), logs `Geotag harvest: created/expected` and a loud `GEOTAG PARITY MISMATCH` WARNING on any gap. Nodes created before 8.4 so the CONTAINS sweep links them; WAS_AT to owner done in the method. py_compile + import OK. UNCOMMITTED. NOTE: C2 ran on OLD code (no 8.35) → still needs standalone harvest; the **bundle ingest (fresh process, new code) will exercise 8.35 end-to-end** — verify its log shows the harvest line + parity.
- **[✅ COMPLETE 2026-05-25] ALL 8 REPORTS INGESTED + ALL GEOTAGS HARVESTED + FINAL PARITY PASSED (365 xml == 365 graph, 0 mismatches across 9 report XMLs).** Final node counts: C2=112,467 (re-run on mode=1 fix), C6=236,402, C5=37,956, C8=35,275, C7=27,555, C3=18,803, C4=82,433, C1=8,803. C4 (bundle) = single report 06306369. C2 + C4 self-harvested geotags via Step 8.35 (validated end-to-end: C2 has 211 photo-Location nodes, all geocoded + CONTAINS-linked). C1/C1-06304890 genuinely have 0 geotags. Per-report geotags: C2=211, C5=99, C3=23, C8=21, C7=5, C4=4, C6=2.
- **SERVICES RESTARTED**: owl-backend (--workers 1, health 200 after ~35s — loads 1GB evidence.json) + owl-frontend, both active. Backend now runs the fixed geocoder (mode=1) + Step 8.35, so future UI ingests get all fixes.
- **REMAINING: COMMIT (awaiting user — git has NO author configured; prior commits were root@investigation-platform, user wanted to decide attribution).** Code to commit: `backend/services/geocoder.py` (mode=1 fix), `ingestion/scripts/cellebrite/neo4j_writer.py` (:CbNode rel fix + harvest_photo_geotags + geotag stats), `ingestion/scripts/cellebrite/ingestion.py` (skip-media gate + Step 8.35), new scripts `bulk_register_reports.py` / `ingest_one_report.py` / `harvest_geotags.py`. DO NOT commit: `.claude/*` (local settings/locks/backup), `WORKING.md` (scratchpad). INFRA now in git: commit 8c2ba4a folded swap (32G+fstab+swappiness), --workers 1, GEOCODER=geonames, and TMPDIR→data/tmp into deploy/setup-server.sh so a server rebuild recreates them. CLARIFICATION: routine deploy/deploy.sh NEVER touched these (only git pull + restart); the only revert risk was a from-scratch setup-server.sh re-run / host reimage, now covered. Live host unchanged (drop-ins override.conf/workers.conf/tmpdir.conf still in effect; setup-server.sh edit is for future rebuilds). Nominatim still stopped (OOM). COMMITS (all Neil B <thenofisamizdat@gmail.com>): e072fb2 geocoder mode=1, b47e60f geotag harvest+parity+:CbNode+skip-media, a0dc26d CLI helpers, 8c2ba4a setup-server hardening. Branch main, NOT pushed.

## KEY FINDING 2026-05-25 — the 5 "uploads" are ZIPs already extracted on disk; ~32h is registration grind, NOT transfer

The 5 in-flight `file_upload` tasks are **archive (ZIP) uploads that already transferred + extracted server-side** — every active `_staging/<id>/` contains only `_extracted/<Report>/...`. Original report ZIPs were auto-unlinked post-extract (evidence.py:681). So ALL file data is on disk now, split between (a) case dir `ingestion/data/43f1afb1.../<Report>/` (registered-so-far portion) and (b) `_staging/<id>/_extracted/<Report>/` (remainder not yet moved). **Killing the tasks loses no data.** Owner oferreira@. Reports in flight: 2026-05-04.12-40-21 (folder-name export, 279,700), C6 06306962, C2 06306207, C7 06306964, C8 XMLReport 06308586.

The ~32h ETA is PURELY the registration loop (move file→case dir + rewrite 238MB evidence.json every BATCH_SIZE=100 files; evidence_service.py:311/381), bottlenecked at ~8 files/s aggregate regardless of concurrency. NOT network.

**FAST IN-PLACE FIX — EXECUTING 2026-05-25 ~00:30 UTC (user approved).** No re-upload.
- [DONE] Backups: `data/evidence.json.pre-bulkregister-20260525-001549` (242M) + background_tasks.json.pre-bulkregister-20260525-001549. Watcher loop killed.
- [DONE] `systemctl stop owl-backend` — confirmed inactive/dead (Main PID 715923 exited clean), evidence.json frozen @00:18. NOTE: two unrelated uvicorns persist & MUST be left alone — PID 299274 is a Docker container (cwd /app, app.main:app, port 8000 inside its netns), PID 299376 is the v2 stack (app-v3/owl-n4j :8002). Host :8000 dead.
- [DONE] Consolidated: `cp -aln` hardlinked each `_staging/<id>/_extracted/<rep>` into case-dir `<rep>`. Final case-dir counts EXACT vs task totals: C2=310,881, C8 XMLReport=119,482, 2026-05-04.12-40-21=279,700 (bundle, contains C4 etc.), C6=204,425, C7=81,819. Disk unchanged (hardlinks). chowned all 5 trees back to conorbowles51 (cp ran as root).
- [DONE] `scripts/bulk_register_reports.py` (run as conorbowles51 via venv) — hashed 996,307 files in 968s (~1000/s, IO-bound on tiny files) then ONE `evidence_storage._file_locked()`: dropped 83,900 partial rows (278,714→194,814) + inserted 739,016 primary + 257,291 dup = 996,307. evidence.json 278,714 → **1,191,121 records (~1.0GB)**. Per-report row counts verified EXACT vs file counts (C2 310,881 / C6 204,425 / C7 81,819 / C8 119,482 / 2026-05-04 279,700). KEEP reports untouched (C1 209,271, C3, C5, C1-06304890).
- [DONE] 5 stale file_upload tasks marked failed (59c1da54/73399103/bc5ee7a3/b55b998d/611e2461).
- [DONE] removed the 5 staging dirs; `_staging` empty; case-dir data intact (hardlinks). Disk 158G free.
- [DONE — IMPORTANT INFRA] **OOM on load**: 1GB evidence.json × `--workers 4` (each worker parses all 1.19M records, ~2.2G RSS each) + Neo4j ~9G > 31G swapless → OOM-loop, backend wouldn't stay up. FIX: new drop-in `/etc/systemd/system/owl-backend.service.d/workers.conf` sets `--workers 1`. NOT IN GIT — a deploy that rewrites the unit reverts it (same risk class as tmpdir.conf). Backend now health 200, 1 worker @2.2G RSS, ~9G free. To raise concurrency later, weigh RAM: each worker ≈2.2G + Neo4j up to 9G on a 31G no-swap box. See [[project_host_no_swap_oom]].
- INGESTION (user chose: start now, one at a time, smallest first). Driving via CLI `scripts/ingest_one_report.py "<rel>" "<evnum>" ["<device_id>"]` run as conorbowles51 + GEOCODER=geonames (proven reingest_all3 path; calls shared `process_cellebrite_report` force=True). RAM-watched by bg monitor `data/ingest_monitor.log` (polls 30s; exits/pings on done / avail<1500MB / error). Endpoint path NOT used (needs auth token; CLI proven).
  - Report roots: C7/C6/C2 = folder itself; **C8 nested** = `C8 XMLReport/220049582_06308586_C8_2023-01-18_Report (1)`; **2026-05-04 BUNDLE** = multiple sub-reports, e.g. `2026-05-04.12-40-21/220049582_06306369_C4_2022-12-12_Report` (inspect fully before ingest; ingest each sub-report root separately).
  - PERF FIX (2026-05-25 ~01:30, user-approved Option 1): cellebrite ingestion was ~10 nodes/s & DEGRADING because `neo4j_writer._create_relationship` (line ~511) used a LABEL-LESS `MATCH (a {key,case_id}) MATCH (b {key,case_id})` → AllNodesScan (2 full scans of ALL nodes per edge, ~184ms, worsening as graph grows). FIX = shared `:CbNode` secondary label on every cellebrite node + composite index `cb_node_case_key` on `:CbNode(case_id,key)` + labeled MATCH → O(log n). Changes in `ingestion/scripts/cellebrite/neo4j_writer.py`: 4 node-creation paths add :CbNode (_create_node CREATE adds `:CbNode`; _ensure_person / create_phone_report_node / finalise_sim_card add `SET x:CbNode`) + _create_relationship MATCHes now `:CbNode`. CONTAINS sweep (line ~2452) left as-is (one batched scan, not per-edge). Index created ONLINE. Existing 65,566 case nodes backfilled `SET n:CbNode` (so cross-report shared-Person endpoints resolve). **UNCOMMITTED** code change — commit after all 5 ingested + a UI-triggered run confirms (backend still on old in-memory writer; CLI picks up new code; restart backend before trusting UI ingests).
  - VALIDATED on C7 re-ingest: node rate ~10/s → **~95/s**, no query >1s, Neo4j CPU 100%→67%. (First C7 attempt task 68a54cf1 killed + its 5,493 partial nodes wiped; re-ingest task f1dbb2c9, log `data/ingest_c7_v2.log`.)
  - FRONTEND DOWN: `systemctl stop owl-frontend` during the fix to block team-triggered uploads/ingests. **RESTART owl-frontend when done.** Backend still up (--workers 1).
  - **OOM at media-registration (2026-05-25 ~01:35):** C7 graph wrote FAST (fix validated: ~95/s, all 19,653 models, 27,555 nodes, rels+CONTAINS done) but the CLI process then **OOM-killed (SIGKILL, hit 11.4G)** at Step 9 media-registration — file_linker loads the 1GB evidence.json (~3-5G as Python objects) on top of resident parsed models. Earlier the `--workers 4` restart also OOM-killed **Neo4j itself twice** (~9G java) — recovered, data intact (C1/C3/C5 counts match exactly). Root = **no swap on 31G box** ([[project_host_no_swap_oom]]).
  - **SWAP ADDED (2026-05-25, user-approved):** `/swapfile` 32G, `swapon`, `vm.swappiness=10` (`/etc/sysctl.d/99-swappiness.conf`), persisted in `/etc/fstab` (`/swapfile none swap sw 0 0`). NOT in git — survives reboot via fstab but a fresh host/deploy won't have it. Verified: Swap 31Gi avail. This is THE fix for the recurring OOM (protects Neo4j from being killed too).
  - **owl-backend STOPPED during CLI ingestions** (frees 2.2G + its evidence cache; frontend already down so nothing served). RESTART owl-backend (still --workers 1) when all ingestions done, alongside owl-frontend.
  - [✅ DONE] **C7** fully ingested (v3, swap-backed): RESULT_STATUS success, 0 write_errors, 27,555 nodes, ~42min (most of it media-registration). Swap peaked ~1G, NO OOM. C7 is the ONLY report with media-registration done.
  - **SKIP-MEDIA change (user-approved):** media-registration (Step 9, optional Tier-2) was the ~40-min slow part — it rewrites the 1GB evidence.json repeatedly. Added env gate in `ingestion/scripts/cellebrite/ingestion.py` (+`import os`): `CELLEBRITE_SKIP_MEDIA_REGISTRATION=1` skips Step 9. **UNCOMMITTED.** CLI batch sets it (fast, graph-only); backend/UI ingests still do full pipeline. Media files stay on disk + already have evidence rows from bulk-register → relink later via a standalone batched pass if Tier-2 LLM media analysis is wanted. (C8/C6/C2/bundle will NOT have media-linked; C7 does.)
  - [✅ DONE] **C6** (06306962, samsung SM-J737T1) task 3d48add5, log `data/ingest_c6.log`, skip-media: RESULT_STATUS success, 0 write_errors, 236,580 nodes (graph shows 236,402 labeled — delta = shared Person MERGE under earlier reports). Finished 2026-05-25 03:47 UTC. Swap held ~1G, no OOM. Monitor exited; queue did NOT auto-advance.
  - [✅ DONE] **C8** (06308586, samsung SM-A037U, phone 13015416552) task e820611e, log `data/ingest_c8.log`, skip-media: RESULT_STATUS success, 0 write_errors, 35,275 nodes. Finished 2026-05-25.
  - [IN PROGRESS] **C2** next (06306207, biggest ~310K) — about to launch, skip-media, log `data/ingest_c2.log`.
  - QUEUE after C2: 2026-05-04 bundle sub-reports (C4 06306369 + others — inspect `find <bundle> -iname '*_Report.xml'` & ingest each root separately). All with skip-media. Verify each: RESULT_STATUS success, write_errors low, nodes>0, geocode=geonames.
  - GRAPH STATE (2026-05-25): C6=236,402, C5=37,956, C7=27,555, C8=35,275(reported), C3=18,803, C1=8,803. 6 of 8 reports done. Pending: C2, bundle.
  - **MEDIA-REGISTRATION (Step 9) STATE — verified empirically 2026-05-25 by streaming evidence.json (count of rows with `cellebrite_category` set, grouped by report_key):** DONE for **C1 (17,177), C3 (13,751), C5 (37,876), C7 (29,007)** = 97,811 media evidence rows enriched. NOT done for **C6, C8, C2, bundle** (skip-media / not yet ingested) — they have 0 cellebrite-tagged rows. CORRECTION: the earlier "C7 is the ONLY report with media-registration" note was scoped to the 2026-05-25 batch only — C1/C3/C5 got Step 9 during their 2026-05-24 full-pipeline reingest (predates skip-media gate). NOTE: media files for ALL reports are on disk + have plain evidence rows from bulk-register (996,307 rows, NO cellebrite_report_key tag); skip-media only defers the EXIF/geotag/model_id enrichment that feeds Tier-2 LLM media analysis. Geotag coverage thin even where run: only C5 has geotagged media (99); C1/C3/C7=0. To complete media-linking on C6/C8/C2/bundle: standalone batched register_media_files pass per report (no graph re-ingest needed) OR re-run those reports WITHOUT the skip-media env (slow, ~40min each, rewrites 1GB evidence.json).
  - WHEN ALL DONE: restart owl-frontend + owl-backend (--workers 1 still applies); commit the uncommitted changes (neo4j_writer :CbNode fix, ingestion.py skip-media + import os, scripts/bulk_register_reports.py, scripts/ingest_one_report.py); note CbNode index + 65,566-node backfill already in Neo4j. Optionally run media-registration as a separate pass for C6/C8/C2/bundle if Tier-2 wanted.
- FUTURE (real fix, separate): 1GB evidence.json means every write rewrites ~1GB under lock AND each worker holds it all in RAM (forces --workers 1). Proper fix = append-only/JSONL or lazy/paged evidence storage so workers don't each cache all 1.19M records. Out of scope for this ASAP run; this is now the top scaling debt.

## STATUS CHECK 2026-05-24 22:40 UTC — uploads healthy, staging cleaned

Team (oferreira@owlconsultancygroup.com) is uploading 3 large cellebrite folders concurrently through the UI, case 43f1afb1. **All healthy, 0 failures, 0 backend 5xx, 0 ECONNRESET.** The TMPDIR fix + Nominatim-stopped (8.2G RAM free) are holding under real load.
- 59c1da54 `2026-05-04.12-40-21` — 35,000 / 279,700 (started 21:28)
- 73399103 `220049582_06306962_C6` — 1,700 / 204,425 (started 22:33)
- bc5ee7a3 `220049582_06306207_C2` — 1,900 / 310,881 (started ~22:37)
Throughput ~8 files/s each (batched-write rate, as designed). Multi-hour uploads; steady, not erroring.

**DISK CLEANUP DONE (user-approved):** `ingestion/data/_staging` had bloated to 122G — 14 ORPHANED staging dirs (2026-04-26 → 05-22) from past failed/aborted/wiped uploads. Confirmed safe: staging is transient-by-design (files moved to case dir; **0 evidence.json rows reference `_staging`**), all 14 predated today's 21:28 uploads. Deleted 87.4G → **free space 102G → 187G**. Kept today's 3 active dirs (fc81791d / a875866 / cf077956, 35G). evidence.json (203M) and case dirs untouched.

**NEXT ACTION on resume:** re-run the status check — (1) `python3` read of background_tasks.json for the 3 running uploads' progress/failed counts; (2) `journalctl -u owl-backend --since` for 5xx/ENOSPC + `owl-frontend` for ECONNRESET; (3) `df -h /` (watch headroom as ~795K files land, est ~90G across the 3 folders, fits in 187G); (4) when an upload completes, expect a cellebrite_ingestion to follow — monitor per [[cellebrite-ingestion-failures]] (`docker stats owl-n4j`). Nominatim MUST stay stopped. Note: C2 + C6 were both on the pending-reingest list ([[project_cellebrite_ingestion_failures]]).

## SESSION 2026-05-24 (evening) — CELLEBRITE UPLOAD FIX + OOM doom-loop resolved

**User report:** multiple cellebrite ZIP uploads today all failed with "There was a problem Internal Server Error" (last ~19:25 UTC). Needs reliable uploads.

### ROOT CAUSE (found, fixed, verified)
Uploads die at the **proxy layer, never reaching FastAPI** (0 `POST /api/evidence/upload` in owl-backend access log all day). Vite frontend service (`owl-frontend`, :5173) logged the real errors:
```
15:01:54 / 16:31:46 / 16:43:31  [vite] http proxy error: /api/evidence/upload → Error: read ECONNRESET
```
`read ECONNRESET` = backend reset the TCP connection mid-upload (so no HTTP response, hence no access-log line, hence browser sees a bare generic 500).
- Mechanism: `evidence.py` upload handler calls `await request.form()` (line 601, **outside** the try/except), which spools each multipart file to a Starlette `SpooledTemporaryFile(max_size=1MB)` that rolls over to `tempfile.gettempdir()` = **`/tmp`**. `/tmp` is a **16G tmpfs (RAM-backed)** and the host has **NO SWAP**. A tmpfs can't exceed available RAM+swap, so on a RAM-starved host a multi-GB cellebrite zip had nowhere to land → worker died/stalled mid-spool → ECONNRESET. Worker PIDs confirm respawns at 10:07/20:02/20:03 (the OOM-event times).
- Compounding driver: host OOM doom-loop (see below) kept RAM near zero.

### FIX (applied 2026-05-24 ~20:33 UTC)
1. **Stopped Nominatim** (`docker stop nominatim`) — it was the ~9G consumer driving OOM. Freed RAM 260Mi→10Gi available. Reversible (`docker start nominatim`); the import restarts from scratch on every container start anyway, so no progress lost.
2. **Redirected backend temp off the RAM tmpfs onto disk.** New systemd drop-in `/etc/systemd/system/owl-backend.service.d/tmpdir.conf` sets `TMPDIR`/`TMP`/`TEMP`=`/home/conorbowles51/app_v2/data/tmp` (on /dev/root ext4, 150G free). Created that dir (conorbowles51:conorbowles51, 0700). `daemon-reload` + `systemctl restart owl-backend`.
   - NOTE: fix lives in **systemd drop-in, NOT the git repo** — a deploy that rewrites the unit could lose it. evidence.py code unchanged.
3. **Verified:** health 200, 4 workers, all carry TMPDIR. Reproduced Starlette's exact spool (`SpooledTemporaryFile(max_size=1MB)` + 5MiB write → rollover) under the service env: the rolled-over file landed at `/home/conorbowles51/app_v2/data/tmp/#<inode>` on /dev/root ext4 — NOT `/tmp`. So multi-GB uploads now spill to the 150G disk.

### LIVE TEST IN PROGRESS — team uploading (user away ~1h from 2026-05-24 ~21:00 UTC)
The fix is being exercised for real: the team is uploading cellebrite ZIPs while the user is out for ~an hour. A background watcher (`data/upload_watch.log`) is recording outcomes every 60s and will exit early (re-invoking me) on any NEW upload 5xx / proxy error / disk <20G.

**NEXT ACTION on resume / "continue":**
1. `cat /home/conorbowles51/app_v2/data/upload_watch.log` — per-minute ok / fe_upload_errs / be_5xx / disk / mem since the watcher started.
2. Successful uploads since the user left:
   `journalctl -u owl-backend --since "2026-05-24 21:00:00" | grep 'POST /api/evidence/upload'` (expect `" 200 OK"`; a `507` now = staging-FS full, the new clear error).
3. Any new failures:
   `journalctl -u owl-frontend --since "2026-05-24 21:00:00" | grep -A1 'evidence/upload'` (a `read ECONNRESET` here = upload still dying → re-investigate).
4. Disk headroom (concurrent multi-GB zips spool→stage→extract ≈ 3× size each, 150G total):
   `df -h /home/conorbowles51/app_v2/data` and `du -sh data/tmp ingestion/data/_staging 2>/dev/null`.
5. If all uploads 200: fix confirmed end-to-end — tell the user, done. If 507s: disk filled under concurrent load — consider freeing space / serializing uploads. If ECONNRESET again: TMPDIR/headroom regressed — re-check `free -h` (Nominatim must still be stopped) and worker `/proc/<pid>/environ` TMPDIR.

Reminder: **Nominatim is stopped** (`docker stop nominatim`) and MUST stay stopped — restarting it re-triggers the OOM loop that broke uploads. See [[project_host_no_swap_oom]].

### Code hardening (DONE 2026-05-24 ~20:50 UTC) — UNCOMMITTED
Wrapped `await request.form()` in `backend/routers/evidence.py` (`upload_evidence`) in try/except: `OSError` w/ `errno.ENOSPC` → 507 "ran out of disk space"; other `OSError` → 500 with the real error; `MemoryError` → 507 "ran out of memory". Added `import errno`. So a genuine staging-fs-full now returns an actionable message instead of an opaque 500/ECONNRESET. py_compile OK, backend restarted (health 200, TMPDIR still applied). NOT committed — evidence.py change is in the git repo; leaving commit + authorship decision (prior commits went in as root, see below) to the user.

### HOST OOM DOOM-LOOP (diagnosed this session)
31G RAM, **NO SWAP**. Kernel OOM-killer fired repeatedly today (`global_oom`, victims were largest procs):
- 00:40 & 09:57 → Nominatim postgres (~9G) killed → import restarted from scratch each time
- 15:00 & 20:02 → **owl-n4j java (v1 Neo4j, ~9G) killed** → production DB restart (tx-log-corruption risk per [[cellebrite-ingestion-failures]])
- 20:03 → Nominatim postgres killed again
Trigger = Nominatim's ~9G postgres co-resident with Neo4j's ~9G heap on a swapless 31G box; several entries show `claude invoked oom-killer` (agent allocations tipped it over). Nominatim import can therefore NEVER finish on this host as-configured (it restarts from scratch on each OOM before completing). **Resuming Nominatim later REQUIRES first adding swap and/or freeing memory** (e.g. temporarily trim Neo4j heap during import, or pause v2 stack). Per user: Nominatim deferred until cellebrite work finalized + OOM resolved.

### Geo backfill (task 17) — STILL DEFERRED behind Nominatim
All 629 cellebrite Location nodes (466 distinct coords) already have geonames city-level geocoding (functional). Street-level upgrade via Nominatim deferred. NOTE: building a whole North-America Nominatim (2.4B nodes, 9G, hours, destabilises prod) to geocode 466 points is disproportionate — when we resume, weigh (a) add swap + finish local Nominatim [keeps coords on-host, privacy] vs (b) batch-reverse-geocode the 466 points against public Nominatim [trivial but leaks investigative coords externally]. User's call.

---

## SESSION 2026-05-23 (evening) — E+C+5+6 done, committed; C3 validation ingest in flight

User is OUT and authorised continuing autonomously ("say yes to confirmations"). Completed and COMMITTED the agreed batch:

- **E (coverage)** — NetworkUsage handler added (per-app data-usage timeline; moved SKIPPED→SUPPORTED + reconcile/stats/log wiring). SearchedItem.Origin + WebBookmark.Path captured; both handlers' hardcoded `TimeStamp` reads fixed to `_extract_timestamp`. SUPPORTED now 34 types; SKIPPED only {DictionaryWord}.
- **C (phone precondition + manual identifier)** — ingestion refuses a PhoneReport with no owning identity UNLESS investigator supplies a device identifier. Identifier → PhoneReport.phone_numbers + device-owner Person node (propagates to conversations/calls/locations). Optional alias when a real number exists. Wired orchestrator→service→router(422 guard)→UI(required field when no number). NOTE: not exercised end-to-end (all 3 phones HAVE numbers); verified by import/AST + logic review only.
- **5 (fcntl locks)** — new `services/_json_file_lock.save_json_atomic` (lock + unique-temp atomic write) applied to all 8 stores (snapshot, workspace, last_graph, case, presence, wiretap, triage cases+templates). Fixes the `.tmp` rename ENOENT race. NOTE: this is the lighter lock+atomic-write fix, NOT full reload-before-save — lost-update across workers still theoretically possible on these 8 (deferred; documented).
- **6 (UTC timestamps)** — new `services/_timeutil.utcnow_iso/parse_iso_utc/utcnow`. Task/ingest/evidence/log producers now emit offset-aware UTC. main.py watchdog uses aware now + tolerant parser (handles legacy-naive + new-aware mix). Other naive `datetime.now().isoformat()` producers (workspace witnesses/notes etc.) left as-is — out of scope, frontend handles them.
- **Lockfile chmod 0o666** in the 3 reload-under-lock managers (committed here too).

**Commits (authored as root@investigation-platform — flag to user for re-author):**
- `2c0428e` cellebrite: full model coverage + manual device identifier
- `1986995` infra: fcntl-locked atomic JSON writes for 8 stores + UTC-aware timestamps
- `ee75a58` cellebrite: ingest DictionaryWord (was skipped) — user asked if skipping loses values; audit of C5's 6,539 entries found a typed email (salguerojuan840@gmail.com), owner phone-number fragment, money amounts (100mil/13mil/14mil), possible DOB (08011971), names, phrase fragments. Un-skipped + handler added. SKIPPED_MODEL_TYPES now empty.

**Backend restarted 21:31 UTC** — clean boot, 4 workers, watchdog ran without error on the new timeutil, health 200. New code is LIVE.

**C3 validation ingest IN FLIGHT (launched 21:36 UTC, task 5dc3a54b):** running `process_cellebrite_report` as conorbowles51 via /tmp/validate_c3_ingest.py (force=True), log at /tmp/validate_c3_ingest.log. 16,663 models. Smallest phone, chosen to validate the new pipeline end-to-end on the fastest run before C1/C5. C3 has phone numbers so the precondition path isn't exercised by this run. Background waiter brqfkej36 notifies on completion.

**C3 validation RESULT (success):** status=success, 0 write_errors, 18,794 nodes, NetworkUsage=5,181 (new handler validated), owner "Sender Lemus" propagated (5 numbers, 5,363 out-edges). E coverage validated end-to-end. C3 Location nodes show geocode_source=none — see geocoder correction below (CLI-env artifact, not a real outage).

## GEOCODER state — CORRECTED 2026-05-23 (evening)

Earlier this session I wrongly told the user "geocoding is OFF / GEOCODER not in .env". TRUTH:
- `GEOCODER=geonames` is set in the **systemd unit** (`/etc/systemd/system/owl-backend.service` `Environment=...GEOCODER=geonames`), NOT in `.env` (which has no geocoder lines and hasn't changed since Feb 22). The live backend process HAS GEOCODER=geonames.
- Verified working: reverse_geocode(39.0840,-77.1528) → Rockville / Montgomery County / Maryland, geocode_source=geonames, accuracy=city.
- The C3 `geocode_source=none` was because the CLI validation script (/tmp/validate_c3_ingest.py via `sudo -u conorbowles51 python`) does NOT inherit the systemd Environment, so that process had GEOCODER unset. Real backend/UI ingests get geonames. NOT a real outage.
- **Nominatim will NOT auto-enable.** Finishing the import only makes the :8080 HTTP service answer queries. The backend stays geonames until we explicitly set `GEOCODER=nominatim` + `GEOCODER_URL=http://localhost:8080` + `GEOCODER_FALLBACK=geonames` and restart owl-backend. To switch: edit the systemd unit's Environment= line (that's where GEOCODER currently lives), `systemctl daemon-reload`, restart.
- Frontend needs NO changes for Nominatim: LocationsTable.jsx:158 / LocationTileAccordion.jsx:163 already render `address || place_name` and show a `via {geocode_source}` (+accuracy) badge, hidden for none/cellebrite. Nominatim just fills the `address` field geonames left null.

## REVISED DECISION (user, 2026-05-23 evening): ingest C5+C1 NOW (geonames), backfill geo when Nominatim done

Nominatim is hours away (IO-bound ways phase, no flatnode file, 2.1TB read, RAM contention from Neo4j 9.2G — see diagnosis below). So rather than wait, ingest now with geonames city-level and upgrade geo via backfill later.

**IN FLIGHT (launched 2026-05-23 ~22:55 UTC):** /tmp/ingest_c5_c1.py running as conorbowles51 with `GEOCODER=geonames` in env (confirmed primary_ready=True at launch — so this run DOES geocode, unlike the C3 CLI artifact). Sequential: C5 (task 2f374e76) then C1, force=True. Log /tmp/ingest_c5_c1.log. Waiter bi56vtdfv notifies on "ALL_DONE". C5 exercises the new DictionaryWord handler (6,541 entries).

**RESULT (2026-05-24 02:12 UTC — both finished):**
- **C1 (06305320): CLEAN.** task `completed`, 8,755 nodes, 0 write_errors, 488 Locations all geocode_source=geonames. DictWords=0, NetUsage=0 (C1 genuinely has none).
- **C5 (06306946): FAILED at 9.6%.** Orchestrator returned status=success but the SERVICE correctly marked the task `failed`: "2450 of 25595 entities (9.6%) failed to write. Top: Contact=1451, InstantMessage=621, InstalledApplication=355, Location=17, Chat=6." 34,250 nodes landed (missing ~2,450). 93 Locations all geonames, DictWords=6,516 (handler validated).
- **Root cause = transient Neo4j connection drops, NOT a code bug.** Two driver-level `Failed to read from defunct connection ...7687 OSError('No data')` errors logged during C5. C5 ran 22:54–01:12 overlapping Nominatim's peak IO thrash (host had ~266MB free at the time). The writer (`neo4j_writer.write_batch`, line 757-764) writes each model individually and on ANY exception just counts+logs it — **no retry** — so every model in flight during a connection blip is permanently dropped. PROOF it's environmental: C1 ran immediately after (01:12–02:12) with the IDENTICAL handlers and got 0 errors. If the Contact/InstantMessage handlers had a bug, C1's would have failed too. The failure concentration in Contact/IM/InstalledApp = the high-volume types that happened to be in flight during the two blips.

**C5 NEEDS RE-INGEST** (1,451 contacts + 621 messages missing). User chose: add retry + re-ingest C5 NOW (don't wait for Nominatim).

### RETRY FIX (done 2026-05-24 ~02:40 UTC) — `ingestion/scripts/neo4j_client.py`
Root cause of the no-retry was found: `Neo4jClient.run_query()` (the method the cellebrite writer routes ALL writes through) was the ONLY write method in the class that bypassed the existing `_execute_with_retry` helper — `create_entity`/`update_entity`/`ensure_document`/`create_relationship` all already retry on `(TransientError, ServiceUnavailable)` with exponential backoff. Fix = wrapped `run_query`'s session work in `_execute_with_retry`. So no change needed in neo4j_writer.py; the whole cellebrite write path now retries blips. Autocommit CREATEs return no rows → commit-read window nil → retry is safe. **UNCOMMITTED. Backend NOT yet restarted** — running 4 workers still have OLD run_query in memory; a UI-triggered ingest would lack retry until restart. The CLI re-ingest below is a fresh process so it HAS the fix. TODO: restart owl-backend + commit.

### SURGICAL WIPE (done 2026-05-24 ~02:45 UTC)
Can't merge-the-difference: 24 entity types use plain `CREATE` via `_create_node` (no upsert) — re-ingest would duplicate the 34,250 that landed. But a blanket wipe-by-report-key would damage C1: Person keys are `phone-<n>`/`email-<addr>` (case-global MERGE on {key,case_id}, NOT report-scoped), and C5 ran BEFORE C1 so shared people carry C5's report_key + C1 edges. SOLUTION = delete only C5's CREATE-based nodes, KEEP MERGE-based identity nodes (Person/PhoneReport/SIMCard). apoc.periodic.iterate batchSize=1000: **33,391 deleted, 0 failures**. Remaining C5: Person=858, PhoneReport=1. Re-ingest MERGEs persons idempotently (backfills the missing ~593 from failed contacts) + CREATEs entities fresh (no dupes) + C1 untouched. evidence.json left alone (file_linker upserts by sha256).

### C5 RE-INGEST IN FLIGHT (launched 2026-05-24 ~02:50 UTC, task a91589d5-d6cc-4df9-ba22-6e54e170f4a0)
`/tmp/reingest_c5.py` via `sudo -u conorbowles51 env GEOCODER=geonames venv/bin/python` (NOTE: must use venv/bin/python not system python3 — system lacks `jose`; first launch crashed on that, created no task). Clean start: GEOCODER=geonames primary_ready=True (geocodes), force=True. Log /tmp/reingest_c5.log, background cmd b25agrls9 notifies on exit. **Verify on completion: status=completed (not failed), write_errors well under 5% (retry should keep it near 0), Communication/VisitedPage/DictionaryWord/PhoneCall counts back, Person count risen above 858, Locations geocode_source=geonames. Confirm C1 still intact (8,755 nodes, shared-person edges alive).**

C1, C3 are fine (C3 geo backfill still pending Nominatim).

## INTERNATIONAL PHONE NORMALIZATION (started 2026-05-24, IN PROGRESS)
User: "normalize ALL phone numbers to work with international numbers too." Decisions (via AskUserQuestion): engine=**phonenumbers (libphonenumber)**; default region=**US + per-case override**; **abort C5 re-ingest + re-ingest all 3**.

C5 re-ingest (task a91589d5) ABORTED 2026-05-24 ~08:50 (killed venv/bin/python /tmp/reingest_c5.py; task still shows running in JSON — watchdog/restart will mark failed, or clean during wipe). `phonenumbers==9.0.31` installed in venv.

### Locked design (validated against real number shapes):
- Canonical form = **E.164** ("+13017289052", "+50233991579").
- Person key = **`phone-{e164_digits_WITH_country_code}`** → "phone-13017289052" (was "phone-3017289052"). Keeps the `^phone-(\d{7,15})$` contract that neo4j_service consumers rely on, but now globally unambiguous. THIS is why all 3 phones need re-ingest — every phone key changes.
- Validity gate = **is_valid_number** (region-aware). Rejects FB/WhatsApp numeric IDs, short codes, alpha handles, AND phone-length numeric-ID lookalikes like "1000144225" (area code 100 invalid — is_possible would wrongly accept). Only false-negatives = reserved/legacy ranges that don't occur in real extractions.
- Region only matters at INGEST (parsing raw strings). Once stored as E.164 everything downstream is region-agnostic, so the rollup (neo4j_service) needs NO region threading — its inputs become all-E.164. phone_normalise public fns (normalise/normalise_all/normalise_from_person_key/display_format) keep signatures; just swap engine to phonenumbers + add person_key().

### Steps:
1. [DONE] Rewrote backend/services/phone_normalise.py → phonenumbers engine, E.164, person_key(), is_valid_number gate, normalise_from_person_key prepends + for CC-included keys. 14/14 smoke tests pass.
2. [DONE] phonenumbers==9.0.31 added to requirements.txt + backend/requirements.txt (and installed in venv).
3. [DONE] case_storage.py: get_default_region (default "US") + set_default_region (reload-before-save).
4. [DONE] neo4j_writer.py: constructor default_region; _normalise_phone delegates to shared normalise (returns E.164 now); _generate_person_key uses shared person_key for phone branch; _ensure_phone_owner + PhoneReport + Contact handler all thread self.default_region; Contact phone_numbers canonicalised (keeps non-validating raw values, dedup). All call sites pass region. Integration test (realistic import order) ALL PASS.
5. [DONE] ingestion.py orchestrator: loads case_storage.get_default_region(case_id) (guarded import, US fallback) → passes to CellebriteNeo4jWriter.
   IMPORT NOTE: the lazy `from services.phone_normalise import ...` inside the writer needs `services` already cached + backend's config (not ingestion/scripts/config.py) resolved first. Works in real runs because backend is on path first and services imported at top of the CLI/backend before orchestrator inserts scripts_dir (same as the existing geocoder lazy-import). A test that puts ingestion/scripts first shadows config and fails — harness artifact, not a runtime bug.
6. [DONE] Restarted owl-backend ~09:1x UTC — health ok, neo4j connected. Watchdog marked aborted C5 task a91589d5 failed. (worker-count grep shows 1 = uvicorn proctitle-rename artifact, not a real degrade; health ok.)
7. [DONE] FULL cellebrite wipe for case 43f1afb1: apoc.periodic.iterate by `cellebrite_report_key IS NOT NULL` (every cellebrite node incl Person/PhoneReport carries it; verified 0 belong to other cases). 42,330 deleted across 43 batches, 0 failures, 0 remaining. Case/Documents/audio-evidence nodes untouched (no report_key).
8. [IN PROGRESS] Re-ingest C1→C3→C5 sequential via /tmp/reingest_all3.py (backend-first path, services imported at top, GEOCODER=geonames primary_ready=True, region=US, force=True). Launched ~09:2x UTC, background cmd bdsrxmgcl notifies on ALL_DONE. Log /tmp/reingest_all3.log. C1 task 1628d9cf.
   STATUS @ 2026-05-24 15:24 UTC — **ALL THREE DONE** (process exited 15:24, log shows ALL_DONE):
   - **C1 ✅ DONE** task 1628d9cf — status=success, 8,803 nodes, 0 write_errors.
   - **C3 ✅ DONE** task d8af08a6 — status=success, 18,826 nodes, 0 write_errors.
   - **C5 ✅ DONE** task f1f358a4 — status=success, 37,971 nodes, **4 write_errors** (one defunct-connection blip mid-run, retry fix c010ef9 absorbed it — vs 2,450 fails on the pre-retry run). Task marked `completed` (4/25,596 = 0.016%, well under 5% threshold).
9. [✅ VERIFIED 2026-05-24 19:55 UTC] All step-9 criteria pass (queried Neo4j live):
   - Phone keys carry country code: US→`phone-1NXXNXXXXXX`, El Salvador→`phone-503…`, Fiji→`phone-679…`. ✓
   - 0 malformed keys (all match `^phone-\d{7,15}$`). 0 genuinely-unnormalized US keys (a regex check flagged 2 ten-digit non-`1` keys but both are valid Fiji `+679…` E.164, false positives). ✓
   - Per-report Neo4j node counts: C1=8,803, C3=18,803, C5=37,956 (labeled-node counts; slightly under the orchestrator's reported totals because shared Person nodes MERGE under whichever report touched them first). ✓
   - **Cross-phone rollup: 33 Person nodes now span >1 report** — the international-normalization payoff (same number across phones collapses to one identity). ✓
   - Locations: all 629 cellebrite Location nodes geocode_source=geonames, 0 `none`. C3's earlier CLI-artifact `none` is resolved (ran through backend path this time). ✓

ALL COMMITTED — working tree clean. The international change, retry fix, DictionaryWord, phone_numbers dedup, and CellebriteOverview.jsx display join are all in: commits 80bc7a3 / 8e730a4 / c010ef9 / ee75a58 / 2c0428e (+ infra 1986995, f96d9cf, 2996176). WORKING.md's old "NOT YET COMMITTED" note was stale.

⚠️ AUTHORSHIP: all 8 recent commits authored as `root <root@investigation-platform...>` (CLI ran as root). Flagged to user for re-attribution decision — NOT rewritten (history rewrite is destructive; check if pushed first).

OLD verify criteria: status=success, write_errors<5%, NetworkUsage/DictionaryWord counts, owner propagation, Location geocode_source=geonames.

**Geo backfill (task 17, after Nominatim ready — waiter barvzxanb):** switch GEOCODER=nominatim in systemd unit + restart, then run a reverse-geocode backfill over ALL Location nodes (C5/C1/C3) where geocode_source in (geonames, none): re-run reverse_geocode(lat,lon) and update address/place_name/etc. Idempotent + cached. This upgrades all three phones to street-level without re-ingest. (C3's none-geo also gets fixed by this backfill, so C3 does NOT need re-ingest.)

## Nominatim progress (2026-05-24 19:55 UTC) — INDEXING PHASE (the long pole)
Ways/relations import done; now in the **indexing phase** ("Building index on table 'planet_osm_ways'", "Analyzing table 'place'"). This is the final long-running stage before "Setup finished". Container up 10h, healthy. NOT done. Geo backfill (task 17) + GEOCODER→nominatim switch still gated on it. Once done, the backfill upgrades all three phones' 629 Location nodes from geonames city-level to street-level WITHOUT re-ingest (idempotent reverse-geocode over lat/lon).

## Nominatim progress (2026-05-24 02:15 UTC)
Still importing — node phase DONE (2.415B nodes), **ways phase at ~137M ways and accelerating** (6.85k/s now, was 2.16k→3.15k→4.93k earlier — sped up once C5/C1 ingest finished and freed RAM/IO; host now 9G available vs 266MB during the thrash). Relations phase (after ways) not started; the long **indexing phase** (the real long pole) hasn't started either. Cumulative container IO 1.93TB read / 211GB write. Container up 7h, healthy, restart=unless-stopped. NOT done — "Setup finished" not in logs. Still hours out (likely completes overnight). Geo backfill + GEOCODER switch to nominatim still gated on it. NEED a fresh monitor — prior session waiter barvzxanb did not survive into this session.

## Nominatim slowness diagnosis (2026-05-23 ~22:47 UTC)
IO-bound, not CPU-bound. Container BLOCK I/O = 2.1TB read. Cause: ways phase resolves each way's geometry via node-coordinate lookups; NO flatnode file (lookups hit Postgres/disk) + host has 266MB free (Neo4j 9.2G + v2 stack consume RAM, so no page cache to hold node index) → random-read thrash. CPU 84% (<1 core), iowait 10-13%, THREADS=4. Indexing phase still ahead (the long pole). For next time / restart: use --flatnodes, bigger --cache, more threads, don't co-run with Neo4j 9.2G heap. Don't kill the current run (6h + 2.1TB deep).

## OLD plan (superseded): wait for Nominatim, then ingest C5+C1 once with street-level geo

Plan / next action (monitor barvzxanb notifies when Nominatim import finishes):
1. When Nominatim import done (waiter barvzxanb watches `docker logs nominatim` for "Setup finished"): switch GEOCODER to nominatim in the systemd unit Environment= line (+GEOCODER_URL=http://localhost:8080, +GEOCODER_FALLBACK=geonames), daemon-reload, restart owl-backend. Verify geocoder_status shows primary=nominatim, primary_ready=True.
2. Ingest **C5** (93,150 files, 6,541 DictionaryWords — the un-skip will fire here) then **C1** (209,270 files) once, through the backend (force=True). Monitor via task heartbeat.
3. **Also re-ingest C3** (force=True) so all three are consistent — its validation run got geocode_source=none (CLI artifact) and predates the DictionaryWord commit. Cheap (~15 min). Flagged to user.
4. C5/C1 are still WIPED in Neo4j (clean baseline); C3 has validation data that force=True will replace. Uploads all intact on disk.

NOTE: ingest C5/C1/C3 through the BACKEND (not a CLI script) so they inherit GEOCODER. Either trigger via UI, or if doing CLI, pass `GEOCODER=nominatim` (and GEOCODER_URL) explicitly in the env so the CLI process geocodes too.

## Current task
**Fix folder-upload throughput bottleneck — CODE DONE, AWAITING USER RE-UPLOAD (2026-05-22 16:54 UTC).** C5 re-upload was crawling at ~6 files/min (~10 days for 93,150 files) because every single file triggered 3 JSON rewrites: `evidence.json` (288 MB) + `background_tasks.json` (22 MB) twice. User accidentally had 2 parallel uploads competing.

**Cancelled tasks:**
- `8901ddcd` (725/93,150) — was the original C5 upload from 14:56
- `59284e2e` (115/93,150) — duplicate started at 16:17

**Code changes (uncommitted):**
- `backend/services/evidence_service.py` — `upload_folder_task` now batches: accumulates uploads, persists `evidence.json` + `background_tasks.json` once per BATCH_SIZE=100 files (plus a final flush). Drops per-file "processing→completed" two-step status spam.
- `backend/services/background_task_storage.py` — new `MAX_FILES_PER_TASK=100` cap on `task["files"][]` so any future caller appending per-file status entries doesn't bloat the JSON.

**Restart sequence (2026-05-22 16:54 UTC):**
1. Edited code (above).
2. `systemctl restart owl-backend` (first time) — old upload threads got SIGTERM'd mid-write and re-bloated the JSON back to 22 MB on exit (race), tasks still showed running.
3. `systemctl stop owl-backend`, edited JSON to cancel 2 tasks + trim `files[]` arrays on all 7 bloated tasks (dropped 161,835 entries), removed orphaned 278 MB `evidence.tmp` from interrupted atomic-write, `systemctl start owl-backend`.
4. Backend healthy, 4 workers up, no upload threads, JSON 22.6MB → 0.37MB. evidence.json still 288MB (legitimate data, untouched).

**Backups:**
- `data/background_tasks.json.pre-bottleneck-fix-20260522-165020` (22.6 MB, the bloated pre-trim state)

**Partial state wipe (done 2026-05-22 16:57 UTC):**
- 726 files removed from `ingestion/data/.../220049582_06306946_C5_2022-12-15_Report/` (3.1 GB freed). Folder gone.
- 840 evidence rows dropped from evidence.json (one per upload attempt across the two competing tasks; on-disk file count was lower because some paths were overwritten between the parallel uploads).
- Backup: `data/evidence.json.pre-c5-partial-wipe-20260522-165620` (288 MB).
- Backend restarted a 3rd time after wipe so in-memory evidence_storage reloaded the trimmed JSON.

## Next action
1. User re-uploads C5 via UI into a clean slate. Expected throughput: ~100× faster (one JSON write per ~100 files instead of ~3 per file). 93,150 files should land in minutes, not days.
2. After upload completes, user triggers Cellebrite ingestion; monitor `docker stats owl-n4j` per [[cellebrite-ingestion-failures]].
3. Then C6 (also wipe-and-retry once C5 succeeds).
4. Commit fix (`backend/services/evidence_service.py` + `backend/services/background_task_storage.py`) — the diff covers both the batching and the `MAX_FILES_PER_TASK` cap.

## Full cellebrite wipe (2026-05-22 18:11 UTC)
User asked to delete ALL cellebrite uploads + processed data for case `43f1afb1...` because state was messy (mix of old-pipeline ingests + half-uploaded folders) and 3 of 7 PhoneReports had empty `phone_numbers` (user said this should NEVER happen — see [[cellebrite-phone-number-required]]).

**What was wiped:**
- 8 cellebrite folders on disk (~45 GB freed): C9, C1, C1.1, C3, C4, C7, C8 (_Report), C8 (_XMLReport), C1-06304890.
- 263,052 cellebrite evidence rows from `evidence.json` (288 MB → 56.7 MB).
- 12 cellebrite tasks (file_upload + cellebrite_ingestion) from `background_tasks.json`.
- 7 PhoneReport nodes + 107,971 cellebrite-tagged nodes from Neo4j (Communication 34k, VisitedPage 23k, Person 11k, SearchedItem 10k, DeviceEvent 9k, PhoneCall 7k, Email 7k, Credential 4k, Location 1k, Meeting 501, WirelessNetwork 307, Account 210, WebBookmark 46, Device 20, CellTower 18). Used `apoc.periodic.iterate` batchSize=1000 — 108 batches, 10 seconds, zero failures, no tx-log corruption this time (the May-12 incident was a single 33k-node tx; APOC batching avoids that).
- 4 non-cellebrite nodes remain in Neo4j for the case (Case, Documents, etc — untouched).
- Single non-cellebrite audio file (`106854040_2300724_01-04-2025_114256_1-240-960-0892_80961.mp3`, 910 KB) remains in case dir — preserved.

**Backups:**
- `data/evidence.json.pre-cellebrite-wipe-20260522-181107` (287.6 MB)
- `data/background_tasks.json.pre-cellebrite-wipe-20260522-181107` (380 KB)
- Older backups from earlier in this session still present (`pre-bottleneck-fix`, `pre-c5-partial-wipe`, `pre-c5-delete`).

**Outstanding follow-ups:**
- Add precondition to cellebrite ingestion: refuse to commit a PhoneReport when `phone_numbers` is empty. See [[cellebrite-phone-number-required]]. Not done in this session; flagged as a code change for next sitting.
- Commit all uncommitted fixes: `backend/services/evidence_service.py`, `backend/services/background_task_storage.py`, `backend/services/evidence_storage.py`, `scripts/rebuild_c5_evidence_rows.py`.

## Multi-worker stale-state bug (FIXED 2026-05-22 22:50 UTC)
When checking C5 ingestion status, found that the 4th C5 upload (1b61a180) had completed at 19:43 but its 93k evidence rows were missing from evidence.json. Root cause: each uvicorn worker holds its own in-memory `_records`/`_tasks` dict; a single DELETE request landed on a worker with stale state and overwrote evidence.json on save, losing all writes from workers it hadn't synced with. The 22:32 retry upload (`f0bd5a87`) hit the same trap differently — old-backend worker still had cached records and persisted a mix of old+new.

**Fix:** `backend/services/evidence_storage.py` and `backend/services/background_task_storage.py` now wrap every mutation in a `_file_locked` context manager that: (1) takes an `fcntl.LOCK_EX` on a sidecar lock file, (2) reloads the JSON from disk, (3) applies the mutation, (4) atomically saves, (5) releases the lock. Worker in-memory caches are refreshed to the just-saved state. Reads stay unlocked and cached (eventually consistent, but never lose data).

**C5 evidence rebuild (DONE 2026-05-22 22:50 UTC):**
- `scripts/rebuild_c5_evidence_rows.py` — walks the on-disk C5 folder, SHA-256 each file, inserts one evidence row per file (primary for unique SHAs, suffix `_<n>` is_duplicate=True for content dupes within C5 or cross-case).
- Pass 1 (parallel with a zombie upload) made a mess; aborted by stopping backend, wiping C5 rows, rerunning clean.
- Final: 93,150 files on disk = 93,150 evidence rows (81,849 primary + 11,301 duplicates), perfect 1-to-1 match. 17s hash + ~10s merge.
- evidence.json: 56.7 MB → 135.9 MB (clean state with C5 records).

## Cellebrite ingestion overhaul (2026-05-23, IN PROGRESS — code done, pending restart + re-ingest)

C5's first ingestion at 04:28 UTC was correct against the parser's coverage, but the parser was leaking model types. Audited the writer against the actual XML types in C5's report (33 distinct types) and discovered:

- **3 supported types had no handler** (silent drop): Autofill, SIMData, User
- **2 types not in SUPPORTED_MODEL_TYPES** despite being investigatively important: InstalledApplication (588 in C5), FileDownload
- **6,540 DictionaryWord entries** mis-labeled "not_supported" in the reconciliation report (deliberately skipped, but flagged anyway)
- **PhoneReport had no CONTAINS edges** to its 30k entities — investigative views can't filter "everything from this device" in one hop
- **Message provenance fields dropped**: ForwardedMessageData, ReplyMessageData, MessageLabel
- **file_linker bloated evidence.json**: 188k C5 rows vs 93k actual files (re-ingest writes new rows instead of upserting by sha256)
- **No advisory lock** on cellebrite/process — the 2nd C5 POST at 04:11:13 slipped through 5s after a 409 because the duplicate check is racy when the first task hasn't written PhoneReport yet

**Code changes (all uncommitted, all in this branch):**
- `ingestion/scripts/cellebrite/parser.py` — added InstalledApplication + FileDownload to SUPPORTED, moved DictionaryWord to SKIPPED (was implicit-drop with bad label)
- `ingestion/scripts/cellebrite/neo4j_writer.py` — 5 new handlers (_write_autofill, _write_sim_data, _write_user, _write_installed_application, _write_file_download), new counters in `__init__` + `get_stats`, dispatch table extended, `_message_provenance_props` helper applied to InstantMessage and Email, new `link_all_to_report()` method using APOC batched MERGE
- `ingestion/scripts/cellebrite/ingestion.py` — Step 8.4 calls `writer.link_all_to_report()`, _RECONCILE_MAP extended with 5 new types, final log summary includes new counters
- `ingestion/scripts/cellebrite/file_linker.py` — `_register_batch` now upserts by (case_id, sha256) under `_file_locked`; existing rows get cellebrite_* metadata patched in, never duplicated
- `backend/routers/evidence.py` — `process_cellebrite_folder` rejects 409 if a sibling cellebrite_ingestion task with the same report_key is pending/running, regardless of force=true

**Verified:**
- All files AST-parse clean
- Module imports cleanly (no runtime errors)
- Reconciliation with sample C5-like input shows DictionaryWord=skipped, InstalledApplication=ok, FileDownload=ok
- Geocoder confirmed live (geonames backend) — 110 C5 Location nodes all have geocode_source=geonames

**Geocoder note (not changed):** `GEOCODER=geonames` in .env, `reverse-geocoder` pip pkg installed, backend uses it for any Location with no Cellebrite-supplied address. Only emits country/admin1/admin2/place_name (city level). To get richer street-address text, add nominatim as primary (geonames already the fallback) — deferred.

## Coverage audit + Tier 0/1 overhaul (2026-05-23 12:00-14:00 UTC)

User asked "how sure are we we're capturing everything from cellebrite reports". Built `scripts/audit_cellebrite_coverage.py` that streams every Cellebrite XML on disk and produces a coverage matrix vs UFEDLib's 56-class open reference + our own handler dispatch parsed from source. Ran across 3 reports (C3 sample / C5 main case / C9 other case): 45,200 models + 165,340 files audited.

**Findings — handlers that produced near-zero useful output:**
- SIMData 0% — XML emits Name/Value/Category per-property rows, my handler read ICCID/IMSI/MSISDN as direct fields.
- EXIF on tagged files 0% — of ~80 EXIF item names in MetaData section, 0 matched parser.py's name list. 122 photos had ExifEnumGPSLatitude/Longitude (sexagesimal), all dropped. 1,307 had EXIFCaptureTime, all dropped.
- VisitedPage 38% — Cellebrite uses `LastVisited` not `TimeStamp`; 15,995 browser-history timestamps silently dropped.
- DeviceEvent 0%, PoweringEvent 25% — handler read wrong field name aliases.

**Code changes (all uncommitted, all in this branch):**
- `ingestion/scripts/cellebrite/parser.py` — added `_exif_dt_to_iso`, `_us_dt_to_iso`, `_exif_gps_to_decimal` helpers; rewrote `parse_tagged_files()` EXIF block: now reads ExifEnumDateTimeOriginal, EXIFCaptureTime, ExifEnumGPSLatitude/Longitude (sexagesimal + decimal-fallback), ExifEnumGPSAltitude, ExifEnumMake/Model, ExifEnumPixelXDimension/Y, ExifEnumSoftware, EXIFOrientation, accessInfo ModifyTime/CreationTime/AccessTime, CoreFileSystemFileSystemNode* timestamps. NetworkUsage / DictionaryWord still in SKIPPED.
- `ingestion/scripts/cellebrite/models.py` — TaggedFile gained access_time, gps_altitude, camera_make, camera_model, image_width, image_height, orientation, exif_software.
- `ingestion/scripts/cellebrite/file_linker.py` — propagates all new TaggedFile fields into evidence records.
- `ingestion/scripts/cellebrite/neo4j_writer.py`:
  - Added `_TIMESTAMP_ALIASES` tuple + `_extract_timestamp(model, prefer)` helper. Wired through VisitedPage, Call, InstantMessage, Email, WirelessNetwork, RecognizedDevice, DeviceEvent/PoweringEvent, Autofill, FileDownload, Location, InstalledApplication, User.
  - `_base_props` now captures UserMapping universally.
  - Added `_extract_search_query` (URL → search term) for Google/Bing/DDG/YouTube/etc. — VisitedPage handler tags `is_search`/`search_query` props.
  - SIMData handler rewritten as aggregator: buffers Name=Value pairs into `_sim_properties`, `finalise_sim_card()` creates one MERGE'd SIMCard node per report at end.
  - Per-handler field captures added (Call: Status/Account; InstantMessage: Status/Identifier/Folder/DateDelivered; Email: Account; WirelessNetwork: Source/LastConnection/SecurityMode; CalendarEntry: Source/Category/RepeatRule/RepeatUntil; Password: Service/AccessGroup/ServiceIdentifier; RecognizedDevice: Source/SerialNumber; Chat: Account/Name/Description + is_group + participant_count; InstalledApplication: OperationMode/IsEmulatable/DecodingStatus; UserAccount: ServiceType/ServiceIdentifier/TimeCreated/credential+is_sensitive; User: Identifier/SerialNumber/TimeLastLoggedIn; FileDownload: TargetPath/StartTime/EndTime/LastAccessed/BytesReceived/DownloadState; Autofill: Key alias + LastUsedDate; Location: Name/Category/Description; DeviceEvent/PoweringEvent: EventType/Value/Element/Event/Description aliases.).
  - Contact handler walks Photos/Addresses/Organizations multimodel children → photo_file_ids / addresses+structured first-address / organizations+org_titles props on Person.
  - `_ensure_person` now uses `ON MATCH SET p += $match_patch` so Contact rich props land even when the Person was created earlier from a message.
- `ingestion/scripts/cellebrite/ingestion.py` — Step 8.3 calls `writer.finalise_sim_card()` before the CONTAINS sweep.
- `scripts/audit_cellebrite_coverage.py` — new tool. Recognises `_extract_timestamp` and `get_parties` helpers to avoid false negatives. Outputs `docs/cellebrite_coverage.md` (~600 lines) + `docs/cellebrite_coverage.json`. Re-run on every new upload.

**Coverage matrix — after vs before:**

| Type | Before | After | Change |
|---|---:|---:|---:|
| SIMData | 0% | 75% | +75 |
| DeviceEvent | 0% | 75% | +75 |
| FileDownload | 30% | 90% | +60 |
| Password | 33% | 78% | +45 |
| RecognizedDevice | 25% | 75% | +50 |
| PoweringEvent | 25% | 100% | +75 |
| InstalledApplication | 50% | 88% | +38 |
| UserAccount | 38% | 88% | +50 |
| Chat | 50% | 88% | +38 |
| Contact | 50% | 83% | +33 |
| InstantMessage | 50% | 90% | +40 |
| CalendarEntry | 50% | 90% | +40 |
| Email | 75% | 88% | +13 |
| Call | 67% | 89% | +22 |
| Autofill | 50% | 83% | +33 |
| User | 33% | 83% | +50 |
| VisitedPage | 38% | 75% | +37 |
| Location | 38% | 75% | +37 |
| WirelessNetwork | 43% | 86% | +43 |
| WebBookmark | 67% | 67% | 0 |
| SearchedItem | 60% | 60% | 0 |
| DictionaryWord / NetworkUsage | 0% (SKIPPED) | 0% (SKIPPED) | — |

**Open question / Tier 2 deferred:**
- NetworkUsage at 5,181 instances per-app data usage with byte counts — currently SKIPPED but probably useful timeline data; reconsider.
- WebBookmark and SearchedItem have known unread fields (Path on bookmark — always empty in our data; Origin on search — only 3 non-empty), low priority.
- Crash/visibility work (heartbeat / UI lockout / failure surfacing) deferred to next session.
- Types UFEDLib supports but our reports don't yet contain (Journey, Note, Notification, VoiceMail, SocialMediaActivity, Cookie, CreditCard, etc.) — defer until they appear.

## Visibility bundle (2026-05-23 13:00-13:35 UTC)

User: "ingestion task starts, then nothing it appears to stop... meanwhile it's running in the backend and I can monitor it but it says it will take 6 hours, and then mysteriously fails and runs a second time and leaves us with 2 partial ingestion." Built four-part fix:

- **V1 — Heartbeat in writer + ingest_cellebrite_report.** New `progress_callback(dict)` parameter on the orchestrator. After each 200-model batch in Step 8, plus at every phase boundary (writing → finalising_sim → linking_contains → geotag_backfill → registering_media), the callback fires with (phase, total, completed, failed). Throttled to max 1 call / 2s to keep background_tasks.json writes cheap. `writer.write_errors: Counter` now records per-model-type handler exceptions (previously swallowed into log warnings).
- **V2 — Service-level heartbeat + failure threshold.** `cellebrite_service.process_cellebrite_report` defines a heartbeat that calls `background_task_storage.update_task(progress_total, progress_completed, progress_failed)`. `updated_at` auto-bumps. At end, if write_errors / xml_model_count > 5%, the task is marked FAILED (not COMPLETED) with a top-5 error-type breakdown. Closes the "task says succeeded but data is missing" failure mode.
- **V3 — Backend startup watchdog.** Added to `main.py` lifespan. On boot, scans every running/pending cellebrite_ingestion + file_upload task; any with updated_at > 5 min old is marked FAILED with reason "process died mid-ingest (backend restarted)". Closes the "running forever after backend OOM" mode.
- **V4 — Frontend live progress + ETA.** `FileInfoViewer.checkCellebriteTask` now also captures `started_at` + `progress.failed`. Computes ETA from `(elapsed / completed) * (total - completed)`. Renders below the progress bar as e.g. "62.4% · ~12m left" plus a red "N write errors" counter when failed > 0. New `formatEta` helper near the top of the file (h/m/s readable). The polling-driven UI lockout was already in place (button-disable when `cellebriteTask !== null`); on page reload the 10s poll picks up the in-flight task within one tick.

**Files touched (uncommitted):**
- `backend/main.py` — watchdog in lifespan startup
- `backend/services/cellebrite_service.py` — heartbeat callback + failure-rate threshold + DEGRADED state
- `ingestion/scripts/cellebrite/ingestion.py` — progress_callback plumbing + per-batch + per-phase beacons
- `ingestion/scripts/cellebrite/neo4j_writer.py` — write_errors Counter + Counter import + stats exposure
- `frontend/src/components/FileInfoViewer.jsx` — formatEta helper + ETA/failed display in cellebrite task UI

**Verified:** all 4 files AST-parse, modules import, `ingest_cellebrite_report` signature now carries `progress_callback`. Backend restarted clean (13:33 UTC), 4 workers up, watchdog didn't rescue anything (no stale tasks to rescue).

## evidence.json.lock permission bug (FULLY FIXED 2026-05-23 18:41 UTC)

Four cellebrite ingests failed this afternoon with `[Errno 13] Permission denied: '/home/conorbowles51/app_v2/data/evidence.json.lock'`:
- 09388eb2 (C5) — failed 15:24:52 at 5,200/19,056 (watchdog rescued at 15:32 restart)
- 0f00cdaf (C3) — failed 16:01:56 at 100% Neo4j, died Step 9 (file_linker.register_media_files → evidence_storage._file_locked → lockfile open)
- 88a289ca (C1) — failed 17:14:24, same shape
- a6309687 (C3 retry) — failed 17:51:51, same shape (the chown described below hadn't actually landed yet; ctime on the lock file shows 18:07:57, so it was applied after this task died)

Root cause: JSON-mutation scripts run as `root` earlier today created/touched `evidence.json.lock` with root ownership mode 644. Backend (running as `conorbowles51`) couldn't open the file for append → EACCES.

**Two-part fix:**

1. **Ownership reset** (chown, applied 18:07:57 UTC):
   ```
   sudo chown conorbowles51:conorbowles51 \
     /home/conorbowles51/app_v2/data/evidence.json \
     /home/conorbowles51/app_v2/data/evidence.json.lock
   ```
   (The original WORKING.md note about this landing at 17:26 was written prematurely — the actual chown didn't run until 18:07, which is why a6309687 still failed at 17:51 with the same error.)

2. **Defensive code fix** (applied 18:40 UTC, backend restarted 18:40:38):
   Added `os.chmod(LOCK_FILE, 0o666)` immediately after `open(LOCK_FILE, "a")` inside `_file_locked()` in:
   - `backend/services/evidence_storage.py`
   - `backend/services/background_task_storage.py`
   - `backend/services/evidence_log_storage.py`
   Each chmod is wrapped in `try/except OSError: pass` so it's a no-op for non-owners. After any successful `_file_locked` call (root or backend), the lockfile is widened to 0o666 — so a future root-mode write can't lock the backend out again. Verified post-restart: all three lockfiles are now `0o666 conorbowles51:conorbowles51`.

Backend healthy after restart: 4 workers up (PIDs 568570-568573 under parent 568565), `/health` returns 200 in <10ms, no startup errors.

## Status check 16:52 UTC (superseded — see lockfile fix section)

Two concurrent loads:
- **Nominatim NA import** — 31 min in, ways phase, ~1.6M/220M+ ways processed at 2.16k/s. Slower than projected (revised ETA: 6-12 hours, not 1.5-3). Container healthy, no errors, disk 149 GB free. At 18:09 it was at 13.6M/220M ways at 3.15k/s (steady).
- **C1 cellebrite ingest** task 88a289ca was at 25% — it later failed at 17:14:24 with the EACCES bug (see lockfile fix section above). All four afternoon ingests died from the same root cause.

N6 (Nominatim wire-up) still gated on import completion.

## Nominatim deploy in progress (2026-05-23 16:21 UTC)

User chose Option A — NA only for now; EU deferred until GCP disk expansion lands. PBF download for EU killed at 76%, file deleted, freed ~25 GB.

Current state:
- `nominatim` container running (`mediagis/nominatim:4.4`, port 8080)
- NA-only PBF: `/home/conorbowles51/nominatim-data/north-america-latest.osm.pbf` (18 GB on disk; was Geofabrik's 19 GB)
- `nominatim import` running with `--threads 4`
- Expected DB size: 60-100 GB indexed
- Expected import duration: 1.5-3 hours
- Disk: 258 GB free at start
- Container restart policy: `unless-stopped` — survives docker daemon restart + host reboot

Path forward (per WORKING.md "Nominatim sequence"):
- N5 verify when container logs show "Setup finished."
- N6 wire backend (geocoder.conf drop-in + restart owl-backend)
- N7 prompt user for C5 re-ingest

Monitoring loop: ScheduleWakeup every ~30 min — checks `docker logs --tail 30 nominatim` for "Setup finished." string, fully detached from session state.

## Known follow-up: 8 services still using naive atomic-write (2026-05-23 15:32 UTC)

Today's cellebrite ingest died at 5,000/19,056 models because `evidence_log_storage._save_logs` did naïve atomic-write (open `.tmp` → rename) with no fcntl lock. Worker A and B both open the same `.tmp` path, B's rename consumes the file, A's rename gets ENOENT. Fixed today same-shape as morning's evidence_storage / background_task_storage fixes. But these 8 other services still have the bare pattern:

- snapshot_storage
- workspace_service
- last_graph_storage
- case_storage
- presence_service (high write frequency — most likely to hit the race next)
- wiretap_tracking
- triage/template_service
- triage/triage_storage

None on the cellebrite ingest hot path, but multi-user activity will eventually hit them. Apply the same `_file_locked` + `_refresh_if_stale` shape from evidence_log_storage. Defer to a focused cleanup pass.

## Known follow-up: backend naive ISO timestamps (2026-05-23 14:10 UTC)

`datetime.now().isoformat()` is used throughout the codebase for task `created_at` / `started_at` / `updated_at`. No timezone suffix, no `Z`. Server runs in UTC; JS parses naive ISO as **local time**, so on a UTC+N browser every "heartbeat age" reads N hours stale. Symptom hit live on 2026-05-23 14:09: a task last updated 21 seconds prior appeared as "Heartbeat: 1h ago / STALLED" on a UK browser.

Patched on the frontend side (BackgroundTasksPanel.jsx `getHeartbeatAge` + FileInfoViewer.jsx ETA computation): appends `Z` if no TZ present. Good enough; ingest doesn't need a backend restart.

Backend fix (when convenient): introduce a `utcnow_iso()` helper that returns `datetime.now(timezone.utc).isoformat()` and grep-replace every `datetime.now().isoformat()` to use it. Affects:
- backend/services/background_task_storage.py (create_task / update_task)
- backend/services/cellebrite_service.py (started_at / completed_at)
- backend/services/evidence_storage.py
- backend/services/evidence_log_storage.py
- backend/services/case_storage.py
- Anything else producing timestamps consumed by JS.

## Failed-ingest cleanup (2026-05-23 18:51 UTC)

User asked to wipe all data from the 4 afternoon failed ingests (asolorzano's runs) but keep the uploads. State now:

- **Neo4j**: 22,359 cellebrite nodes deleted via `apoc.periodic.iterate` batchSize=1000 (23 batches, 0 failures, 0 leftover). Matched the criterion `cellebrite_report_key IN ['cellebrite-220049582-06305320','cellebrite-220049582-06306208']` (C1 + C3). C5 PhoneReport + 12,463 entities from the morning's good ingest untouched.
- **background_tasks.json**: 4 failed cellebrite_ingestion task records dropped (09388eb2 C5, 0f00cdaf C3, 88a289ca C1, a6309687 C3-retry). 85 → 81 tasks.
- **evidence.json**: untouched. Confirmed the failed ingests died at Step 9 *before* writing any evidence rows — there was nothing to clean here. 161,042 rows total, 93,151 for case 43f1afb1 (all C5 from rebuild_c5_evidence_rows.py).
- **On-disk folders preserved**: C1 (15:01), C3 (15:13), C5 (04:28) all intact in `ingestion/data/43f1afb1-.../`.

Backups (owned by conorbowles51:conorbowles51):
- `data/background_tasks.json.pre-failed-cleanup-20260523-185152` (392 KB)
- `data/evidence.json.pre-failed-cleanup-20260523-185152` (135.9 MB)

## Next action (updated 2026-05-23 18:51 UTC)

Lockfile fix is in, backend restarted clean, all 3 lock files now 666 conorbowles51:conorbowles51. Failed-ingest data wiped. C1, C3, C5 folders are on disk and ready to re-ingest.

1. **Re-trigger C1 and C3 ingests from the UI** in whichever order (asolorzano or neil — both have the folders on disk). C5 is already good from the morning run and does NOT need to be re-ingested. With the visibility bundle live you should see:
   - Progress bar that updates every ~2s
   - "Processing N/M · ~Xm left" with ETA after the first few batches
   - Button disabled across page reload (server-side state)
   - Red "N write errors" counter if any handler raises (per-model-type breakdown in the FAILED reason)
   - If the backend crashes or restarts mid-ingest, task gets marked FAILED on next boot
2. Run `python3 scripts/audit_cellebrite_coverage.py` after each ingest. Compare the matrix against the static-analysis prediction.
3. Then C9 (and C3 sample) if desired.
4. Commit pending changes. Currently uncommitted on this branch:
   - Coverage + Tier 0/1 overhaul (ingestion/scripts/cellebrite/* + scripts/audit_cellebrite_coverage.py)
   - Visibility bundle (backend/main.py, backend/services/cellebrite_service.py, ingestion/scripts/cellebrite/ingestion.py + neo4j_writer.py, frontend/src/components/FileInfoViewer.jsx)
   - Lockfile defensive chmod (backend/services/evidence_storage.py + background_task_storage.py + evidence_log_storage.py) — this session
   Bundle as 2-3 logical commits when ready.

## Previous next-action (superseded by overhaul above)
1. ~~User triggers Cellebrite ingestion on C5~~ (DONE, but ran twice in parallel — overhaul fixes the lock)
2. ~~Repeat pattern for C6~~ (still pending; do after C5 succeeds with new code)
3. ~~Commit all five files as one PR~~ (now seven+ files; bundle with overhaul commit)

## Recursive folder-list timeout fix (2026-05-23 02:01 UTC)
User hit `net::ERR_CONNECTION_TIMED_OUT` clicking the C5 folder in `EvidenceProcessingView`. Root cause: `getFolderFilesRecursive` in the React component made one `/api/filesystem/list` call per directory, recursing through the whole tree. C5 has 414 directories, so ~414 sequential HTTP round-trips through the Vite dev proxy. The user's browser timed out partway through (request #193 in the failed trace).

**Fix:**
- `backend/routers/filesystem.py` — new `GET /api/filesystem/list_recursive?case_id=&path=` endpoint that walks the tree server-side with `os.walk` and returns a flat list of relative file paths in one response.
- `frontend/src/services/api.js` — added `filesystemAPI.listRecursive`.
- `frontend/src/components/EvidenceProcessingView.jsx` — `getFolderFilesRecursive` now calls `filesystemAPI.listRecursive` (one round-trip) instead of recursing per directory.

Backend restarted; user just needs a browser refresh to pick up the Vite HMR'd frontend.

## Console-noise cleanup (2026-05-23 02:10 UTC)
- `/api/profiles/profile-name 404` — deleted `profiles/example.json`, whose `"name"` field was the literal placeholder `"profile-name"`. The list endpoint reads the `name` field from each profile JSON, not the filename, so this template file was surfacing as a real profile and the frontend's profile-detail loop kept 404ing on it. Verified list now returns 15 profiles, `profile-name` not present.
- React `validateDOMNesting` warning at CaseManagementView.jsx — root cause: line 1960 outer "Processing History" toggle button contained a "Refresh" inner button. Restructured to flex-row siblings (toggle on left, refresh on right) matching the existing "Evidence Files" section's pattern. Verified zero remaining button-in-button instances.

## Polling rate reduction (2026-05-23 02:40 UTC)
User kept hitting `ERR_CONNECTION_TIMED_OUT` on one-shot requests too (`/api/cases/{id}`, `/api/profiles/wiretap`) — backend logs confirmed every request that *reached* the backend completed in <10ms. Concluded it's a client-side TCP issue (network path, GCP firewall, or browser concurrent-connection limit) under request burst. Reduced four `setInterval` polls from 3s to 10s to lower request rate ~3.3×:
- `FileInfoViewer.jsx:273` (checkActiveTask)
- `FileInfoViewer.jsx:315` (checkCellebriteTask)
- `FileInfoViewer.jsx:362` (checkActiveTasks for multi-folder)
- `BackgroundTasksPanel.jsx:90` (loadTasks)
Was peaking at ~1.3 req/sec on `/api/background-tasks` per tab; now ~0.4 req/sec.

## Cellebrite folder-card "Total Files: 0" (FIXED 2026-05-23 02:35 UTC)
Even after the O(n²) fix below, C5's folder card kept showing 0. Root cause: `/api/evidence` filters out Cellebrite artifact rows by default (`backend/routers/evidence.py:215`, `include_cellebrite_artifacts: bool = False` — intentional to keep response from ballooning to 100MB+ JSON). So all 93k C5 evidence rows are invisible to the frontend's `files` state, and the matching never finds any of them.

**Fix:** in `EvidenceProcessingView.jsx`, `totalFiles` now comes from `folderFiles.length` (raw on-disk walk via `listRecursive`), not from the matched evidence subset. File-type detection also walks the raw paths. `processed/unprocessed` counts still come from matched evidence — for Cellebrite folders this will read 0/0, which is accurate (cellebrite ingestion tracks completion at PhoneReport level, not per-file evidence.status). Applied to both call sites (folder-card click handler and multi-folder loadSelectedFoldersInfo loop).

## O(n²) folder-stats matching (FIXED 2026-05-23 02:30 UTC)
After C5's evidence rows were rebuilt to 93k records and the bulk recursive list endpoint returned 93k file paths, the C5 folder card showed "Total Files: 0". Root cause: `EvidenceProcessingView.jsx` computed folder stats by mapping every recursive file path through `files.find(f => ...)` — O(n²) over the evidence list, ~8.6B comparisons for C5, locking the UI thread long enough that the user gave up before it completed.

**Fix:** built two `useMemo`'d Maps from `files` (`evidenceByRelPath` keyed by normalized stored_path, `evidenceByFilename` keyed by original_filename) and a `useCallback`'d `findEvidenceForPath(filePath)` helper. Replaced both `files.find` sites (folder-card click handler and the multi-select foldersInfo loop) with the O(1) lookup. Dropped the suffix-style fallbacks because every record now carries a canonical stored_path. New cost: ~50ms Map build + ~10ms for 93k lookups; well under a single frame.

## Previous task (kept for context)
**Stabilise v1 backend — COMPLETE (2026-05-22).** Repair stable for 5 days. All four parts done 2026-05-17, committed (fe6d266 routers, 61a7d02 infra), and backup cleanup performed 2026-05-22.

1. **Workers bump 1 → 4** — DONE.
2. **Repair Neo4j store corruption** — DONE (APOC export → wipe → replay; 194067 nodes / 285528 rels, zero consistency errors).
3. **Neo4j memory + tx timeout** — DONE & committed (61a7d02).
4. **Event-loop unblock: async-def → def in routers** — DONE & committed (fe6d266).
5. **Cleanup safety backups** — DONE 2026-05-22, freed ~3.4 GB. See "Backup cleanup" below.

## Backup cleanup (2026-05-22)
Deleted 7 stale repair artifacts (sudo rm -rf):
- `neo4j/data.broken-pre-repair-20260517-040140` (1.5 GB)
- `neo4j/data/transactions/neo4j.{broken-pre-repair,partial-cyshell,replay-oom}-*` (1.4 GB total)
- `neo4j/data/databases/neo4j.{broken-pre-repair,partial-cyshell,replay-oom}-*` (508 MB total)

Kept as fallback restore artifacts (per user):
- `neo4j/import/neo4j.dump` (149 MB)
- `neo4j/import/owl-export-20260517-040719.cypher` (197 MB)

Live `data/databases/neo4j/` + `data/transactions/neo4j/` untouched; owl-n4j healthy post-cleanup.

## Today's session (2026-05-17, restart at 13:41 UTC)
Converted 77 FastAPI route handlers from `async def` to `def` so FastAPI runs them in the threadpool instead of the event loop. They were calling sync `neo4j_service.*` (which calls sync `session.run`) directly inside `async def`, blocking the worker's event loop for the entire query duration. With 4 workers that meant **4 global slots for slow Neo4j queries**; now it's **40 threads × 4 workers = 160 slots**.

Handlers that legitimately `await` (asyncio.to_thread, run_in_threadpool, request.is_disconnected, request.form, file.read, async generators) were left as async — they don't block. 3 such handlers identified by the scan and skipped:
- `graph.py::find_similar_entities_stream` (uses `await request.is_disconnected()`)
- `evidence.py::process_wiretap_folders` (uses `await process_wiretap_folder_async`)
- `financial.py::upload_notes_csv` (uses `await file.read()`)

**Files touched (all uncommitted):**
- `backend/routers/graph.py` — 40 handlers
- `backend/routers/evidence.py` — 25 handlers
- `backend/routers/financial.py` — 12 handlers
- `backend/routers/cellebrite.py` — 16 handlers (earlier this week)
- `backend/services/snapshot_storage.py` — mtime-cached reload (eliminates per-request disk read + the `[RELOAD]` log spam)
- `docker-compose.yml` — Neo4j heap/pagecache bump + `db.transaction.timeout=25s`

**Restart at 13:41 UTC** — backend healthy: 4 workers up, snapshot mtime cache active, `/api/auth/me` and friends respond in <100ms, no startup errors.

## Diagnostic baseline (post-restart 2026-05-17 13:42 UTC)
- Backend memory: ~460MB at fresh start (was 4.4G after 56min uptime pre-restart; expect to climb similarly).
- Neo4j: 4.8 GB / 31 GB container limit, CPU ~1%, 82 PIDs.
- System: 14G/31G used, load avg 0.2, no swap.
- 5xx count past 12h: 34 — **all before 12:22 UTC**; all were the pre-repair `NOT PART OF CHAIN` corruption. Zero since.
- Neo4j `query.log` is empty (slow query log disabled). If we ever need historical slow-query data we'll have to flip `db.logs.query.enabled=INFO`.

## How to recognize regression
- **Event-loop blocking again:** symptom is fast endpoints (`/api/auth/me`, `/api/snapshots`) intermittently taking seconds instead of <100ms while a heavy endpoint is in flight elsewhere.
- **25s tx timeout firing:** look for `TransientError` / `transaction has been terminated` in `journalctl -u owl-backend`.
- **Snapshot cache broken:** `[RELOAD] Loaded N snapshots from disk` repeating more than ~4 times in steady state (one per worker on boot is normal).

## Next action
Stabilisation task is closed. No pending action — awaiting next user request.

If a regression appears later, recognize it by the symptoms under "How to recognize regression" below.

## Cellebrite C2/C5/C6 cleanup (2026-05-22 — DONE)
Root cause: C2 zombie (121k models, on pre-repair Neo4j) corrupted the tx-log mid-ingest. C5/C6 retries hit the broken log. Full writeup in memory `project_cellebrite_ingestion_failures.md`.

**What was cleaned:**
- 15 task rows dropped from `data/background_tasks.json` (5 zombies — including the in-flight C5 file_upload `bdf6baef` at 33k/93k — plus 9 C5/C6 cellebrite_ingestion failures + 1 disk-full file_upload).
- 39,953 C2/C5/C6 evidence rows dropped from `data/evidence.json`.
- 33,257 stale C2 graph nodes + 1 C2 PhoneReport dropped from Neo4j (cypher direct).
- 10.3 GB of source files removed: C2 (2.7G), C5 (6.3G), C6 (1.3G).
- owl-backend stopped during JSON mutation, restarted clean (4 workers up, Neo4j connected).
- Backups at `data/{background_tasks,evidence}.json.pre-c2c5c6-cleanup-20260522-072612`.

**Re-ingest plan (user accepted):**
1. Re-upload C2 source folder → run Cellebrite ingestion. Monitor `docker stats owl-n4j` — heap is **8G** (bumped from 4G on 2026-05-22), expect peak well under that for ~310k nodes. Wait for `status=completed`.
2. Re-upload C5 → ingest → wait.
3. Re-upload C6 → ingest → wait.

If any re-ingest fails with `TransactionLogError`, **stop**. The store has re-corrupted; rerun the export-wipe-replay from the 2026-05-17 repair.

## Neo4j memory bump (2026-05-22 — DONE)
After cleanup, bumped v1 Neo4j memory settings in `docker-compose.yml`:
- Heap: 4G → **8G** (initial + max). 2× the budget that handled all prior successful Cellebrite ingestions on this case.
- Pagecache: 2G → **1G**. The on-disk graph is only 305 MB; 1G fits it 3× over. Freed 1G to give to heap.
- Added `-XX:+ExitOnOutOfMemoryError` to JVM args. If a future ingest does OOM, container crashes cleanly and Docker restarts it — prevents another tx-log-corrupting zombie like 2026-05-12.

Effective container RSS after restart: 8.62 GiB / 31.34 GiB (was 5.06 GiB). System still has 11 GiB available memory; v2 stack untouched.

If C2 re-ingest actually pushes heap usage toward 8G, room exists to bump to 12G (system has headroom). Don't bump pagecache unless the graph grows past ~500 MB on disk.

## Deferred (Tier 2/3 from stability plan)
- `--timeout-graceful-shutdown 30` on uvicorn (eliminates the cut-during-restart window). NB: today's restart was idle so no requests dropped; this is preventative.
- 25s global request-timeout middleware (defense-in-depth on top of Neo4j's `db.transaction.timeout`).
- Production frontend build (replace `vite --host` in systemd with nginx).
- systemd watchdog (auto-restart on hung worker).
- Nginx + 2 backend instances → zero-downtime deploys.

## Environment notes
- Live stack: app_v2 backend on :8000 (4 workers) + Vite on :5173.
- v2 stack at `/home/conorbowles51/app-v3/owl-n4j` (:8002, :5174, branch `evidence-engine-migration`). Don't touch it.
- `owl-n4j` runs as root *inside* container; data files on host owned by 7474:7474 from APOC's chown.
- `owl-pg` data must stay UID 999 on host — see `deploy/deploy.sh` Step 1b.
- APOC file export permanently enabled in container's `apoc.conf` (will reset if container is rebuilt from scratch).

## 2026-05-30 — PHONE INGESTION COMPLETENESS AUDIT (app data / social media) — ✅ VERIFIED COMPLETE
User: not all phones have app data / social media — is that correct? Checking we captured everything.
- **Verdict: CORRECT / no pipeline gap.** Reconciled live source XML (grep top-level model `type=`) vs Neo4j graph per report (case 43f1afb1, 10 PhoneReports). For every report the graph count == the XML top-level count for each app/social type. Cross-checked main-pipeline types too: InstalledApplication→InstalledApp, NetworkUsage→NetworkUsage all match (graph off-by-1 vs grep = nested refs, negligible). harvest_app_events.log corroborates (xml top-level vs graph printed per report).
- **Why it varies = extraction type + what each device decoded, not a drop:**
  - AppSession (AppsUsageLog/ApplicationUsage) + MotionActivity (ActivitySensorData) exist ONLY in C4 06306369's XML → only C4 has them. Other iOS FFS phones (C1 06305320, C2 06306207) have NO AppsUsageLog in source.
  - SocialMediaActivity only in C2(176)/C6(5)/C8(825) source.
  - Two sparse phones: C9 06310028 (Samsung A03s) & C1-06304890 (early iOS Legacy 2022-11, 17k nodes) — XML has essentially only comms/contacts/email (+ChatActivity); zero app-usage/social/network/installed in source.
  - Backfill ran on 9 reports (excluded C9 06310028 — but its XML has zero Phase-9 types, so nothing missed).
- NEXT ACTION: none / answered. If user wants a per-phone coverage UI surface, that's new work.

## 2026-05-30 — MADE harvest_app_events.py CASE-AGNOSTIC — ✅ DONE (UNCOMMITTED)
User: "make the backfill case-agnostic for future ingests."
- **Context:** the MAIN pipeline already captures all Phase-9 types on fresh ingest (all 11 in parser SUPPORTED_MODEL_TYPES + writer dispatch; ChatActivity emitted via _write_chat -> _write_chat_activities). So new cases don't NEED this script — it's now a remediation/verify tool for pre-fix reports or re-checks.
- **Change (scripts/harvest_app_events.py only):** removed hardcoded CASE_ID/CASE_DIR. Targets resolved by: `--case CASE_ID` (repeatable) -> reports under ingestion/data/<id>/; positional report paths -> case id derived from ingestion/data/<id>/ ancestor (case_id_from_path); neither -> every case with PhoneReport nodes in graph (discover_graph_cases). Threaded case_id through graph_counts/harvest_report/writer (no more global). New parse_args (flag guards) + build_worklist. Multi-case runs prefix lines with [<cid8>].
- **VERIFIED (read-only --check):** default = 10 reports, GRAND TOTAL identical to audit (AppSession 9304, SocialMediaActivity 1006, Cookie 10115, LogEntry 16311, MotionActivity 17082, ChatActivity 775, FileUpload 3332, DeviceConnectivity 4083, Journey 75, Note 13 = 62,096). --case <id>, explicit-path, unknown-flag + missing-value guards all work. py_compile clean. Did NOT run a mutating backfill (data already in parity = converging no-op). Also now discovers C9 06310028 which the original hardcoded run had missed (it has 0 Phase-9 types, so moot).
- NEXT ACTION: offer commit (scripts/harvest_app_events.py is its own change, separate from the uncommitted frontend has-attachment/scrubber batch).
