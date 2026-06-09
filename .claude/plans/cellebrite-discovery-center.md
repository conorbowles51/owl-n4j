# Cellebrite — Search & Discovery Center (Epic 2A)

Builds the unified omni-search the call notes asked for ("search-and-discovery
center"). Roadmap tickets: **S2-01** discovery shell, **S2-02** result grouping +
type filter, **S2-03** pivot-to-view with carried filter, **S2-04** phrase search
reaches the graph. None of these shipped in PRs #56–#83 — this fills that gap.

This is distinct from the cross-phone *graph* search (S2-13..16, already shipped):
that searches the graph canvas; this searches **all phones × all data types** in
one place and pivots out to the right tab.

## Goal

One search box → type a phrase / name / number / address → get results grouped by
type (People, Messages, Calls, Emails, Files, Locations), each result openable in
its native tab pre-filtered (pivot), and a one-click "Show in graph".

## Backend — one new endpoint

`GET /api/cellebrite/discovery/search` in `backend/routers/cellebrite.py`
- Params: `case_id` (Query, required), `q` (the phrase), `report_keys` (optional
  CSV to scope to phones), `types` (optional CSV of result kinds to include),
  `start_date`/`end_date` (optional), `limit_per_type` (default ~10), `current_user`.
- Auth + access: `current_user = Depends(get_current_db_user)` + `_require_case_access(...)`,
  matching every other Cellebrite endpoint.
- Delegates to a new `neo4j_service.discovery_search(case_id, q, ...)` that runs a
  small set of bounded, case-scoped Cypher matches (one per type) and returns:
  ```json
  {
    "query": "piney bench",
    "groups": [
      {"type":"person",  "label":"People",   "total": 4, "items":[{...}]},
      {"type":"message", "label":"Messages", "total": 31, "items":[{...}]},
      {"type":"call",    "label":"Calls",    "total": 2,  "items":[{...}]},
      {"type":"email",   "label":"Emails",   "total": 0,  "items":[]},
      {"type":"file",    "label":"Files",    "total": 5,  "items":[{...}]},
      {"type":"location","label":"Locations","total": 1,  "items":[{...}]}
    ]
  }
  ```
- Each item carries enough to render + pivot: `key`, `title`, `subtitle`,
  `timestamp` (where relevant), `report_key`, `person_keys` (for pivoting comms),
  and type-specific fields (e.g. `lat/lon` for locations, `original_filename` for
  files).
- **Reuse, don't reinvent** the matching logic. Building blocks already exist:
  - People/places: `search_cellebrite_persons` (already diacritics-folded).
  - Message bodies / email subjects: `search_cellebrite_comms_messages`.
  - Files by filename: the `/files` `search` param path (filename substring).
  - Locations by address/place_name: the Location node `place_name`/`address`
    fields (the "Piney Bench Road" case) — bounded `CONTAINS` (case-folded).
  The new service method composes these (or thin Cypher equivalents) with a
  per-type cap so the endpoint stays cheap. Each group returns a `total` (count)
  even when only `limit_per_type` items are inlined, so the UI can say "+N more".

## Frontend — new Discovery tab

1. **`frontend/src/components/cellebrite/CellebriteDiscovery.jsx`** (new)
   - Receives `caseId`, `reports`, `isActive` (the standard tab contract).
   - Search box (debounced) + optional phone (report) scope chips + optional date
     window + type toggles (People/Messages/Calls/Emails/Files/Locations).
   - Calls a new `cellebriteAPI`/`cellebriteDiscoveryAPI.search(...)` in `api.js`
     with an AbortSignal (cancel in-flight on new keystrokes), following the
     existing fetch conventions.
   - Renders results **grouped by type** (S2-02), each group collapsible with its
     total and a "+N more" affordance; empty groups show a muted "no matches".
   - Clear empty state (no query) and error state (Retry), matching other tabs.

2. **Pivot out (S2-03)** — reuse the proven mechanism, no new infra:
   - People → pivot to Comms/Timeline via `selectEntity({ payload:{ _filter_intent:'comms', person_keys:[...] }})` + `requestCellebriteTabSwitch('comms')` and set perspective.
   - Message/Call/Email → open the owning thread/event in Comms/Timeline
     (carry person_keys + time window through the same selection rail / handoff).
   - Location → pivot to Locations/Events (carry the location key/time).
   - File → pivot to Files (carry the filename/entity).
   - "Show in graph" → pivot to Graph with the person/resource keys.
   - All of this rides the existing `CellebriteSelectionContext`, `commsHandoff`,
     and `requestCellebriteTabSwitch` utilities documented in the codebase.

3. **Register the tab** in `frontend/src/components/cellebrite/CellebriteView.jsx`:
   - Add `{ key:'discovery', label:'Search & Discovery', icon: Search }` to `TABS`
     (placed near the top so it's the natural entry point).
   - Import `CellebriteDiscovery`; add the `mountedTabs.has('discovery')` TabPane
     render passing `caseId`, `reports`, `isActive`.

4. **`frontend/src/services/api.js`** — add `discoverySearch(caseId, {...})` to the
   Cellebrite API surface (alongside `cellebriteAPI`), matching existing param/AbortSignal style.

## Phrase search reaches the graph (S2-04)
The "Show in graph" pivot resolves the result's person/resource keys and hands
them to the cross-phone graph (which already supports search→rebuild+frame+select
via the shipped S2-15/16 path). Discovery just feeds it the keys.

## Out of scope (kept honest)
- No new heavy ranking/relevance engine — bounded substring/equality matches with
  per-type caps, like the rest of the module. Good enough to *find*; the native
  tabs do the deep work after pivot.
- No animated "flow over time" (separate stretch ticket S2-21).

## Validation
- Backend: `py_compile` the router + service; smoke-test the endpoint against the
  live case `60b9367c-...` (Operation Silver Bridge) for "piney bench" and a known
  person/number, confirming each group returns sane counts/items.
- Frontend: `npm run build` (full vite build — esbuild standalone trips on
  react-leaflet-cluster).
- Manual: type a query, confirm grouping, open one result of each type via pivot,
  and "Show in graph".

## Delivery
- Branch `feat/cellebrite-discovery-center`, one PR closing S2-01..S2-04.
- Then return to the **testing hub** and add Discovery rows + the pivot/graph-bug
  rows + a clearly-labelled "regression check" section (pre-existing comms filters
  & events playback), served at `/testing` with JSON feedback persistence.
