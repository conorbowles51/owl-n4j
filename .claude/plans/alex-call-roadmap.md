# Roadmap: Alex Call Notes → 3-Sprint Plan

Source: call with Alex + handwritten + typed notes. Synthesized against the actual
codebase (file/line refs below are real). Three sprints, full roadmap, groomed tasks.

> **Theme arc:** Sprint 1 = *Trust & Stability* (fix what's broken/confusing).
> Sprint 2 = *Discovery & Flow* (search everywhere, graph directionality, node creation).
> Sprint 3 = *Deliverables & Depth* (client reporting, deep-history navigation, enrichment).

---

## Notes decode (handwritten image)

Best reading of the handwritten page, reconciled with the typed notes:

- Look at **Accelerator programs in Ireland** *(business action item — not a product task; parked at bottom)*
- **From / Recipient / Phone owner → From → Voice**: when the phone is the **sender**, show that name; recipient should render as the contact name **as saved on that device**. Show **both phone numbers**.
- **Timeline**: toggle **older→newer / newer→older**. Show **full date + time**. **Filter to selected timezone**.
- **"Load more" button** at bottom of the list.
- **Cross-phone graph**: directionality of messages & calls. Bugs: *search not rebuilding graph*, *selected not showing*, *filters not working* → leads to **Search + Discovery center**.
- **Communications** needs **multi-select + multi-filter**.
- **Ability to create Nodes** *(manually add an entity/node — and per follow-up, this must work in graphs and tables across the whole platform, not only cross-phone graph)*.

---

## What already exists (so we don't re-plan it)

Two prior plans cover real ground; this roadmap **builds on**, not over, them:

- `timeline-scrubber-and-search.md` — shared search engine (`utils/cellebriteSearch.js`),
  `CellebriteSearchInput`, `TimelineScrubber`. **Largely shipped** — `shared/CellebriteSearchInput.jsx`,
  `shared/CollapsibleScrubber.jsx`, `shared/HighlightedText.jsx` exist.
- `cellebrite-multi-phone-identity.md` — phone palette, `PhoneSelector`, per-row identity.
  **Largely shipped** — `shared/PhoneSelector.jsx`, `shared/PhoneIdentityChip.jsx`, `cellebriteTime.js` exist.

Already-good-enough today (verified):
- **Timezone engine** exists: `shared/cellebriteTime.js` (`fmtDateTime`, `dayKey` are zone-aware via
  `Intl.DateTimeFormat`), `shared/CellebriteTimezone.jsx` provider + selector. Timeline already groups by
  **local** day (`CellebriteTimeline.jsx:304` uses `tzDayKey`), so the worst "midnight shifts the day" bug
  is handled. Remaining gaps are *display affordances* (offset label on each row, working-zone clarity), not core logic.
- **Inline media**: `comms/CommsMediaStrip.jsx` renders thumbnails inline on every message surface (commit `61961f4`).
- **Message direction text**: `CommsMessageBubble.jsx:145-165` and `CellebriteTimeline.jsx:689-691`
  already build `sender → recipient`. The *graph* is where directionality is missing.
- **Events envelope**: `/api/cellebrite/events/envelope` (`cellebrite.py:755-790`) gives honest totals
  even when the body is capped — the foundation for "Load more" already exists.

So several call items are **partially done**; the tasks below are scoped to the **real remaining delta**.

---

# SPRINT 1 — Trust & Stability

**Goal:** the platform is honest, predictable, and crash-free under real investigative load.
Nothing new to learn; existing views just stop confusing or breaking.

### Epic 1A — Bug scrub & stability pass
- [ ] **S1-01 — Bug-scrub session + triage board.** Walk every Cellebrite tab with a 2-phone, ~230K-event
      case loaded. Log each crash/error/empty-silent-state into a triage list (sev 1–3). *Deliverable: the
      triaged list itself; subsequent tasks reference its IDs.* (No code.)
- [ ] **S1-02 — Invalid-Date hardening audit.** Grep all `toISOString()` / `new Date(` call sites in
      `frontend/src/components/cellebrite/**`. Confirm each guards NaN. Known-good guards:
      `CellebriteTimeline.jsx:319-322`, `timeline.js:143-148`. Fix any unguarded site found in S1-01.
- [ ] **S1-03 — Empty/error states everywhere.** Every tab must render a clear state for (a) no phones
      selected, (b) zero results, (c) fetch error with **retry**. `NoPhonesSelectedEmptyState.jsx` exists —
      ensure it (or an equivalent) is mounted in Comms, Events, Timeline, Graph, Files.
- [ ] **S1-04 — Load-under-pressure check.** Verify the per-type 5,000 cap (`CellebriteTimeline.jsx:187`,
      `cellebrite.py:690`) never lets the UI attempt a full 230K render. Confirm the honest truncation
      notice (`CellebriteTimeline.jsx:396-407`) fires. Document the safe ceiling.

### Epic 1B — Timeline ordering & timestamp legibility
- [ ] **S1-05 — Sort-direction toggle (older→newer / newer→older).** Add a control to `CellebriteTimeline.jsx`.
      Today the sort is hard-coded DESC at `CellebriteTimeline.jsx:293-297`. Make direction state-driven
      (default keeps DESC), persisted per-case in localStorage. Day-group ordering and intra-day row order
      both follow the toggle.
- [ ] **S1-06 — Full date + time on rows.** Row currently shows time-only (`CellebriteTimeline.jsx:682`
      slices off the date). For clarity, show full `YYYY-MM-DD HH:MM` via `formatTs` when rows are not under
      an obvious day header (e.g. in flat/search results), keep time-only under day headers.
- [ ] **S1-07 — Timezone-offset chip on timestamps.** Surface the active zone offset (e.g. `UTC−4`) next to
      timestamps, sourced from the existing zone engine (`cellebriteTime.js:100-106`). The selector already
      shows it globally (`CellebriteTimezone.jsx:84-87`); add an inline per-row/section affordance so a
      reader understands *why* a record sits on a given day. **No new tz logic — display only.**

### Epic 1C — Timezone working-model polish
- [ ] **S1-08 — "Working timezone" applies to filters, not just display.** Confirm date-range filtering
      operates in the selected zone end-to-end (grouping already does via `tzDayKey`). If the date-range
      inputs/scrubber convert to UTC before filtering, align them to the selected zone so a "Nov 4" filter
      means local Nov 4. Spike first (is the filter path zone-aware?), then fix if needed.
- [ ] **S1-09 — Make the zone selector discoverable per case.** Ensure `CellebriteTimezone` selector is
      visible in Timeline + Event Center headers (not buried). Default to device zone; offer UTC.

### Epic 1D — Comms direction & identity correctness (from handwritten "From/Recipient/owner")
- [ ] **S1-10 — Sender = device owner name when phone is sender.** In `CommsMessageBubble.jsx:145-165`
      verify the owner-as-sender renders the owner's name (currently "You" at `:154`); decide with Alex
      whether owner shows as real name vs "You" in cross-phone context.
- [ ] **S1-11 — Recipient shows the on-device saved contact name.** Ensure the recipient label uses the
      contact name **as stored on the sending device**, not a global canonical name. Trace the recipient
      field through `commsUtils.js` → bubble. Spike to confirm the backend exposes the device-local alias;
      file a backend follow-up if it doesn't.
- [ ] **S1-12 — Show both phone numbers.** On message/call rows and detail, display both parties' raw
      numbers alongside names (`PersonName.jsx` is the formatting choke point).

### Epic 1E — Timeline density: scan thousands of rows without drilling in  *(elaborated per follow-up)*

> **Why this is bigger than it looks.** The timeline is **virtualized** — fixed `timelineRowHeight`,
> `bottomPad` spacer, `overflow-hidden` rows (`CellebriteTimeline.jsx` `TimelineRow` `:705-769`,
> windowed list `:673`). That fixed-height contract is exactly why media is mounted today with
> `expandable={false}` (`:760-766`, see `CommsMediaStrip.jsx:114-122`): a row literally cannot grow
> inline without breaking the scroller's height math. So "make it clickable and show the message" is a
> real layout problem, not a flag flip. We solve it without abandoning virtualization.

- [ ] **S1-13 — To/From numbers inline on the row.** Today the row builds `sender → recipient` from
      **names only** (`CellebriteTimeline.jsx:683-691`), and recipient falls back `counterpart` →
      `recipients[0]`. Render the **number** beside each name (`Name · +1 555…`), for both parties, so an
      investigator reads who↔who *and* the raw identifiers while scrolling. Keep it on one truncating line;
      full values in `title`/flyout. Reuse `PersonName.jsx` so formatting is consistent. **Spike S1-13a:**
      confirm `ev.sender` / `ev.counterpart` / `ev.recipients[]` carry `identifier`/number from the events
      payload (`/api/cellebrite/events`); if not, add to the lean event projection in `neo4j_service`.
> **Decision (from follow-up): render inline by default — no click to reveal.** Text body, image
> thumbnail(s), AND a working voice-note player must be visible *in the row itself*. A fixed-height row
> cannot host an audio player, so the windowed list must move to **variable / measured row heights**. This
> is the load-bearing task of the epic; everything else depends on it.

- [ ] **S1-14 — Variable-height virtualized rows.** Convert the windowed timeline list (`:673`,
      `timelineRowHeight`, `bottomPad`) from fixed-height to **measured per-index heights** (measure-and-cache;
      e.g. a `ResizeObserver`/measurement cache keyed by event id). Recompute `bottomPad`/offsets from the
      cache. This is the prerequisite for inline media + body. **Spike S1-14a:** validate scroll stability
      and perf with ~5–10K rows of mixed heights before rolling out (jump-to-day, scroll restore, fast fling).
- [ ] **S1-15 — Inline message body (no click).** Render the message text/body directly in the row, not
      just `ev.summary`. Clamp to N lines with a "more" affordance for long bodies so row height stays bounded
      (the measured-height system from S1-14 absorbs the variation). Investigator reads the message while
      scrolling — zero clicks.
- [ ] **S1-16 — Inline image thumbnails (no click).** Show the actual image thumbnails inline (today
      `CommsMediaStrip` already renders up to `MAX_THUMBS=3` tiny thumbs in the non-expandable branch,
      `:75-90` / `:114-122`). Lazy-load (`loading="lazy"`, already set) and only request when the row enters
      the viewport so thousands of rows don't fire thousands of requests at once. Click a thumb → full-size
      lightbox (additive, not required to view the preview).
- [ ] **S1-17 — Inline voice-note player (no click to open).** Render an actual inline audio player for the
      🎙 voice kind (`CommsMediaStrip.jsx:31`) so the investigator **plays the voicenote straight from the
      timeline row** without opening/expanding the message. Reuse `CommsAttachment`'s audio renderer in a
      compact inline form. Voice element sits **alongside** any other media for that message (handwritten
      note: "voice element directly alongside the media preview"). Lazy-init the audio element on viewport
      entry; only fetch audio bytes on play.
- [ ] **S1-18 — Density & performance tuning.** With body + thumbnails + inline player + To/From numbers all
      visible, keep the row scannable: bounded default height, line-clamped body, consistent layout grid.
      Verify the measured-height scroller stays smooth at ~230K rows (virtualization still only mounts the
      visible window; inline media is lazy). Confirm jump-to-day from the scrubber still lands correctly with
      variable heights.

**Sprint 1 verification gates**
1. Triage board has zero open sev-1 items.
2. Toggling sort flips both day-group and row order; persists on reload.
3. Each timestamp shows a zone offset; switching zone re-labels and re-groups consistently.
4. A message where the phone owner is the sender shows the agreed name; recipient shows the device-saved
   contact name; **both numbers are visible on the timeline row itself**.
5. Scrolling thousands of rows, **with zero clicks**: each row shows the message text, image thumbnail(s),
   and a voice-note player that plays inline. Clicking a thumbnail opens a full-size lightbox (additive).
   Scroll stays smooth at ~230K rows (variable-height virtualization + lazy media); jump-to-day still lands
   correctly.

---

# SPRINT 2 — Discovery & Flow

**Goal:** investigators can find anything across all phones/types and pivot between views without
losing context; the graph shows *who initiated what*; users can author nodes anywhere.

### Epic 2A — Centralized Search & Discovery center
- [ ] **S2-01 — Discovery shell.** New top-level Cellebrite tab `CellebriteDiscovery.jsx` that queries
      **all phones + all data types** at once. Reuse the shared engine (`utils/cellebriteSearch.js`) and
      `CellebriteSearchInput`. Backed by existing endpoints: `/comms/messages/search`
      (`cellebrite.py:624-650`), `/events` (`:681`), `/cross-phone-graph/search` (`:232`).
- [ ] **S2-02 — Result grouping + type filter.** Results grouped by type (comms / events / locations /
      files / people) with multi-select type filter. Each result row shows phone identity chip
      (`PhoneIdentityChip.jsx`).
- [ ] **S2-03 — Pivot-to-view with carried filter.** Clicking a result opens the right view (Timeline /
      Comms / Graph / Files) **with the matched entity/term pre-applied as a filter**. There's an existing
      "Filter Comms" intent path (`CellebriteCommsCenter.jsx:226-246`) — generalize that propagation
      mechanism into a small shared "pivot intent" bus so any result can drive any view.
- [ ] **S2-04 — Phrase search reaches the graph.** Confirm a phrase like `"Piney Bench Road"` surfaces a
      usable node result and offers "open in graph" + "open in timeline." (Ties to 2D fixes below.)

### Epic 2B — Cross-Phone Graph: the three reported bugs
- [ ] **S2-05 — Search rebuilds the graph.** Bug: "search not rebuilding graph." In
      `CellebriteCrossPhoneGraph.jsx` (search tokeniser `:44-60`, filter path `~:571`), ensure Filter-mode
      search actually re-derives the rendered node/link set (and re-runs the force layout) instead of only
      highlighting. Repro with `"Piney Bench Road"`.
- [ ] **S2-06 — Selection visibly reflects on canvas.** Bug: "selected not showing." Ensure a selected
      node/result is visually emphasized (ring/scale/center) on the `react-force-graph-2d` canvas; verify
      the camera-preserve effect (`:216-223`) isn't swallowing the highlight.
- [ ] **S2-07 — Filters actually narrow the graph.** Bug: "filters not working." Audit the 14 edge-type
      toggles (`GRAPH_EVENT_TYPES :86-111`) and phone filter; confirm each toggle re-derives links/nodes.
      Add a "no matches" empty state.

### Epic 2C — Cross-Phone Graph: a *more complete* search  *(elaborated per follow-up — big)*

> **Today's limits.** Graph search is shallow: it tokenises (`:44-60`) and matches node **labels** in two
> modes (highlight vs filter). It does **not** search by edge/relationship content, attributes, numbers, or
> reach nodes outside the hard ~200-person render cap (`cellebrite.py:254-298`, search `:232-251`). A phrase
> like `"Piney Bench Road"` should resolve a place even if it's a location attribute, not a node label.

- [ ] **S2-12 — Define "complete graph search" (spike → spec).** Enumerate what should be searchable:
      node labels, aliases, **phone numbers / identifiers**, edge types & counts, location names/addresses,
      app names, and free text on connected events. Decide ranking and whether search runs **server-side**
      (so it reaches beyond the 200-node render cap) vs the current client tokeniser. Output: short spec.
- [ ] **S2-13 — Server-backed graph search endpoint.** Extend `/cross-phone-graph/search`
      (`cellebrite.py:232-251`) so a query returns matching **nodes + the subgraph needed to show them**
      (matched node + immediate neighbours + connecting edges), independent of the default render cap. Lets
      search surface a node that isn't in the currently-rendered 200 and pull it (and its context) into view.
- [ ] **S2-14 — Search across edges/attributes/numbers.** Match on relationship type, identifiers/numbers,
      location addresses, and app — not just node label. Wire results so `"Piney Bench Road"` resolves the
      place node and its connected people/edges.
- [ ] **S2-15 — Search → rebuild + frame + select.** A search result rebuilds the graph to the matched
      subgraph, frames it (camera fit), and applies the visible selection from S2-06. Provide "expand
      neighbours" to grow outward from a result one hop at a time (keeps the canvas legible vs dumping 200).
- [ ] **S2-16 — Pivot from a graph result.** From a found node/edge, "open in Timeline" / "open in Comms"
      with the entity pre-filtered (uses the S2-03 pivot bus). Closes the "find → investigate" loop.

### Epic 2D — Cross-Phone Graph: direction & flow of communication  *(elaborated per follow-up — big)*

> **Today's limit.** Edges are **undirected** — they show *that* two parties are connected, not *who
> initiated* or *which way traffic flowed*. The graph models shared contacts, not communication flow.
> Making it directional touches the backend graph builder (it must carry initiator + per-direction counts),
> the edge renderer (arrows/particles), and the analysis UX (flow over time).

- [ ] **S2-17 — Backend: per-edge direction + counts (spike → schema).** **Spike S2-17a:** confirm whether
      `neo4j_service.get_cellebrite_cross_phone_graph` (called at `cellebrite.py:254-298`) can emit, per
      comms/call edge, an **initiator** and **directional counts** (A→B count, B→A count) and time span.
      The underlying message/call data already has direction (`CommsMessageBubble.jsx:145-165` builds
      sender→recipient), so the relationships exist — this aggregates them onto the graph edge. Output:
      edge schema (`{from, to, dir_counts:{ab, ba}, first_ts, last_ts, initiator}`).
- [ ] **S2-18 — Directed edge rendering.** With direction data, render arrowheads
      (`linkDirectionalArrowLength`) source→target and optionally animated `linkDirectionalParticles` to
      convey flow. For two-way comms, show a dominant-direction arrow plus a balance indicator (e.g. edge
      thickness or A↔B count label).
- [ ] **S2-19 — Flow emphasis & asymmetry.** Encode volume/asymmetry: edge width ∝ total count; particle
      density or colour ∝ which party sent more. Lets an investigator see "X overwhelmingly messages Y,
      rarely the reverse" at a glance — a communication *trajectory*, not a static link.
- [ ] **S2-20 — Direction legend + toggles.** Legend explaining arrows/particles; toggles to show/hide
      directional particles and to switch between "connection view" (undirected, current) and "flow view"
      (directed). Default keeps current view; flow view is opt-in so we don't regress familiar behaviour.
- [ ] **S2-21 — (Stretch) Flow over time.** Tie the graph to a time window (reuse the scrubber concept) so
      direction/volume animates across the case period — chains of activity across phones become visible.
      Stretch goal; spike feasibility against the force-graph perf budget before committing.

### Epic 2E — Communications multi-select & multi-filter
- [ ] **S2-22 — Multi-select communication types.** In `CellebriteCommsCenter.jsx` extend `CommsTypeFilter.jsx`
      from one-at-a-time to multi-select (call + message + email combinable). Backend already returns mixed
      types via `/comms/between` (`:524-577`).
- [ ] **S2-23 — Combine filters (type × participant × app × attachment).** Ensure participant filter
      (`:45-105`), `CommsAppFilter.jsx`, and `AttachmentFilterToggle.jsx` AND together cleanly in both
      "split" and "any" participant modes.

### Epic 2F — Create Nodes (platform-wide)  *(expanded per follow-up — spans ALL system graphs)*

> **Reality check (from codebase audit).** Node creation **already exists** in the main system and is not
> Cellebrite-specific: `GraphView.jsx:1347` has an "Add Node" button → `AddNodeModal.jsx` →
> `POST /api/graph/create-node` (`graph.py:140` → `neo4j_service`). `GraphTableView.jsx:9` has the same
> "+ Add Node" wired to the same endpoint. A separate entity-profile path exists too
> (`EntityEditorModal.jsx` → `POST /api/case-profiles/`). What's **missing** is parity on the surfaces
> that lack it: the **Cellebrite cross-phone graph** (no affordance) and the **v2 GraphCanvas**
> (`frontend_v2/.../GraphCanvas.tsx` — none yet). So this epic is mostly *extend an existing capability to
> every graph/table*, plus add provenance — **not** build create-node from scratch.

- [ ] **S2-24 — Audit + provenance spike (platform-wide).** Reconcile the two existing creation paths
      (graph node `POST /api/graph/create-node` vs entity profile `POST /api/case-profiles/`): which is
      canonical for "add a node to a graph"? Decide a shared provenance/audit shape (`user_created: true`,
      created_by, created_at) so user-authored nodes are visually + queryably distinct from imported data on
      **every** graph (main, Cellebrite, v2). Output: short design note + the single dialog/endpoint to
      standardise on. *(No new core endpoint expected — `create-node` already exists; this confirms reuse.)*
- [ ] **S2-25 — Create node in the Cellebrite Cross-Phone Graph.** Add the missing "Add node" affordance to
      `CellebriteCrossPhoneGraph.jsx` (today it has none), routing through the standardised dialog/endpoint
      from S2-24; user sets label/type, optionally links to existing nodes.
- [ ] **S2-26 — Create node in the main graph (verify) + v2 GraphCanvas (add).** Main `GraphView.jsx`
      already has Add Node — verify it conforms to the S2-24 provenance shape. Add the affordance to the v2
      `frontend_v2/src/features/graph/components/GraphCanvas.tsx`, which has none yet. Promote/reuse a shared
      creation component so all graphs share one dialog rather than divergent modals.
- [ ] **S2-27 — Create node/row parity across tables.** `GraphTableView.jsx` already has "+ Add Node";
      extend the same affordance to the Cellebrite tables (`EventsTable.jsx`, unified contacts, overview
      tables) routing through the same dialog + endpoint, so authored entities appear consistently in tables
      *and* graphs across the platform.
- [ ] **S2-28 — Provenance + audit on the create-node path.** Ensure the existing
      `POST /api/graph/create-node` (`graph.py:140`) persists provenance (`user_created`, created_by,
      created_at) and that every graph renders user-authored nodes with a clear visual distinction from
      imported data. Extend the endpoint only if the fields aren't already captured. **Signed off by user —
      build approved.**

**Sprint 2 verification gates**
1. One search box surfaces matches across all phones + types; clicking a result lands in the right view
   with the filter applied.
2. **Complete graph search:** `"Piney Bench Road"` resolves the place even though it's an attribute (not a
   node label), pulls in a node that was *outside* the rendered 200-cap, rebuilds + frames the subgraph,
   and shows it visibly selected; "expand neighbours" grows outward one hop.
3. Toggling an edge type narrows the canvas; "no matches" shows an empty state.
4. **Direction & flow:** message/call edges render arrows initiator→recipient; flow view shows asymmetry
   (edge width/particles) so "X mostly messages Y, rarely reverse" is visible at a glance; flow view is an
   opt-in toggle that doesn't regress the default connection view.
5. Comms can show call+message+email together, filtered by participant and app simultaneously.
6. A user can create a node from **every** graph in the system (main `GraphView`, Cellebrite cross-phone
   graph, v2 `GraphCanvas`) and from the tables; it persists with provenance, is visually marked as
   user-authored (distinct from imported data), and appears consistently across all graph and table surfaces.

---

# SPRINT 3 — Deliverables & Depth

**Goal:** turn analysis into client-ready output, and give reliable access to the *full* historical record.

### Epic 3A — Deep-history navigation ("Load more" / infinite scroll)
- [ ] **S3-01 — Decide load model.** Confirm with Alex: explicit **"Load more"** button (handwritten note's
      ask) vs infinite scroll. Default to "Load more" (predictable, less jank on 230K sets).
- [ ] **S3-02 — Paginated event loading in Timeline.** `/events` already supports `offset`
      (`cellebrite.py:691`); the envelope (`:755-790`) gives the true total. Replace the silent per-type
      5,000 cap with progressive loading: load first page, show `"Showing N of TOTAL — Load more"`, append
      on click. Keep dedupe (`CellebriteTimeline.jsx:196-198`).
- [ ] **S3-03 — Keyset pagination for deep pages (backend).** Offset pagination re-reads rows at depth.
      `/comms/between` already has cursor/keyset (`cellebrite.py:546-552`). **Spike → add cursor pagination
      to `/events`** so paging into ~230K events stays fast. Backend task in `neo4j_service`.
- [ ] **S3-04 — Apply "Load more" to other capped lists.** Comms threads (200, `:467`), thread detail
      (500, `:506`), files (500, `:1110`) — give each a consistent "Load more" affordance using the same
      pattern/component.

### Epic 3B — Client-facing reporting & enrichment
- [ ] **S3-05 — Report export spike.** There is **no export today** — `CellebriteReport.jsx:18-202` is a
      read-only device profile. Decide format (PDF vs DOCX vs printable HTML) and generation location
      (client print-to-PDF vs backend render). **Spike → recommendation.**
- [ ] **S3-06 — Entity summaries.** Generate per-entity summary blocks (who, devices present on, contact/
      message/call counts, activity window, aliases) building on the data already in `CellebriteReport.jsx`
      and unified contacts. Reusable `EntitySummaryCard.jsx`.
- [ ] **S3-07 — Timeline callouts.** Let investigators mark/annotate key events and pull them into a
      "callouts" section for the report. Persist annotations (small backend write — confirm scope).
- [ ] **S3-08 — Investigation-context visualizations.** Export-friendly versions of the graph + a condensed
      timeline suitable for a client deliverable (clean styling, legend, no debug chrome).
- [ ] **S3-09 — Assemble report.** Compose selected entity summaries + callouts + visualizations into a
      single client-facing document. **Generation/export of the document is a side-effectful step — confirm
      with Alex before wiring any download/email-out.**

### Epic 3C — Timeline thumbnails polish (close the loop on the call ask)
- [ ] **S3-10 — Click-to-expand inline in Timeline.** `CommsMediaStrip.jsx` is mounted in Timeline with
      `expandable={false}` (`CellebriteTimeline.jsx:760-766`) because windowed rows have fixed height.
      Provide expansion via the detail flyout (already opens on row click) or a lightbox so investigators
      preview media without leaving the timeline. Confirm voice-message element renders alongside media.

**Sprint 3 verification gates**
1. Timeline loads page-by-page to the full ~230K record set via "Load more" without crashing; counter is
   honest (`N of TOTAL`).
2. Deep pages load fast (keyset, not offset re-reads).
3. An investigator can produce a client-facing report containing entity summaries, chosen timeline
   callouts, and clean visualizations.
4. Media in the timeline can be expanded without opening a separate tab; voice messages play inline.

---

## Cross-cutting notes & dependencies

- **Backend writes — SIGNED OFF.** S2-28 (create-node persistence + provenance), S3-07 (annotations), and
  S3-09 (report generation/export) introduce persistence/side-effects. Build approved by user. Still surface
  any actual export/email *send* step for explicit approval at run time (that's a per-action confirm, not a
  design gate).
- **Spikes gate several tasks:** S2-17a (edge direction in graph data), S2-24 (create-node provenance shape),
  S1-13a (sender/recipient identifier in events payload), S1-11 (device-local recipient alias availability),
  S1-14a (variable-height virtualization perf), S3-03 (events keyset), S3-05 (report format). Run these early
  in their sprint.
- **Reuse over rebuild:** search engine, scrubber, phone identity, timezone engine, and media strip already
  exist — every task above leans on them rather than re-implementing.

## Explicitly NOT in this roadmap
- Accelerator-programs-in-Ireland note — business action item, parked, not a product task.
- New event/data types or Neo4j relabelling beyond the create-node provenance flag.
- Server-side full-text reindexing — existing search endpoints are sufficient for the working set.
