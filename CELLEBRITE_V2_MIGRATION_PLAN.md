# Cellebrite v1 → v2 Migration Plan

> **Purpose of this document**
>
> When we're ready to port Cellebrite ingestion + viewing to v2, this is the
> single source of truth for *what's there today*, *what we want to keep*,
> *what we want to fix*, and *how to do the port without re-introducing
> known bugs*.
>
> Read this end-to-end before touching any v2 Cellebrite code. Update the
> "Status" markers in §6 as components land. Treat unanswered questions in
> §8 as blockers — don't guess.
>
> Last updated: 2026-05-06. Author context: written after a session
> diagnosing a Process Evidence page hang caused by 164K legacy
> Cellebrite-artifact rows in `data/evidence.json`.

---

## 1. Context

- **v1** = the current implementation living in this repo (`/home/conorbowles51/app_v2`, despite the folder name — this is "v1" of the product).
- **v2** = a future codebase / branch / app where Cellebrite handling will be rebuilt. Concrete location TBD (see §8).
- The motivation for v2 isn't "v1 is broken" — it's "v1 was built incrementally, and now that we know what users actually need, we want to lay foundations properly." Most v1 user-facing functionality should *survive* the port; what changes is the storage/ingestion contract underneath.

---

## 2. Source inventory (v1)

Use this when locating "where is X today?"

### Backend — ingestion
| File | Purpose |
|---|---|
| `ingestion/scripts/cellebrite/parser.py` | Streaming `iterparse` of UFED `Report.xml`. Yields `ParsedModel` batches of size 200. |
| `ingestion/scripts/cellebrite/models.py` | Dataclasses: `CellebriteReport`, `CaseInfo`, `DeviceInfo`, `ExtractionInfo`, `TaggedFile`, `Party`, `ParsedModel`. |
| `ingestion/scripts/cellebrite/file_linker.py` | TaggedFile UUID → on-disk path; SHA-256; category detection (Image/Audio/Video/Text). |
| `ingestion/scripts/cellebrite/neo4j_writer.py` | MERGE-based node/edge writer. Tags every node with `cellebrite_report_key` for bulk delete. |
| `ingestion/scripts/cellebrite/ingestion.py` | 9-step orchestrator. Progress logging, error handling. |

### Backend — service layer
| File | Purpose |
|---|---|
| `backend/services/cellebrite_service.py` | `check_cellebrite_report()` (header parse + collision check), `process_cellebrite_report()` (background task wrapper). |
| `backend/services/cellebrite_intersection_service.py` | On-demand cross-phone analytics: spatial co-presence, cell tower, WiFi, comm hub, convoy. |
| `backend/services/neo4j_service.py` | 40+ Cellebrite-specific Cypher queries: timeline, comms entities, threads, events, cross-phone graph, intersection (lines ~5408–7360). |

### Backend — routes
| File | Purpose |
|---|---|
| `backend/routers/evidence.py` | Cellebrite *ingestion entry points*: `/evidence/cellebrite/check`, `/evidence/cellebrite/process`. Also: `_is_cellebrite_report_root`, `_cellebrite_root_prefixes`, `_looks_like_cellebrite_artifact` (the page-load filter we just added). |
| `backend/routers/cellebrite.py` | All *read* endpoints (~915 lines): list reports, comms, timeline, events, cross-phone graph, intersections, file tree. |

### Frontend
| File / dir | Purpose |
|---|---|
| `frontend/src/components/cellebrite/CellebriteView.jsx` | Top-level tab routing. |
| `frontend/src/components/cellebrite/CellebritePhonesSection.jsx` | Lists detected phones (PhoneReport nodes). |
| `frontend/src/components/cellebrite/CellebriteOverview.jsx` | Per-phone summary + drill-down tables. |
| `frontend/src/components/cellebrite/CellebriteCommsCenter.jsx` | Multi-phone chat / call / email threads + full-text search. |
| `frontend/src/components/cellebrite/CellebriteTimeline.jsx` | Chronological event feed. |
| `frontend/src/components/cellebrite/CellebriteEventCenter.jsx` | Geolocated events on map + playback. |
| `frontend/src/components/cellebrite/CellebriteCrossPhoneGraph.jsx` | Shared-contact graph. |
| `frontend/src/components/cellebrite/CellebriteFilesExplorer.jsx` | File tree (group by category / parent / app / path). |
| `frontend/src/components/cellebrite/comms/*` | Sub-components for Comms Center. |
| `frontend/src/components/cellebrite/events/*` | Map / track / playback. |
| `frontend/src/components/cellebrite/overview/*` | Drill-down detail views. |
| `frontend/src/utils/cellebriteSearch.js` | Client-side text-match search. |
| `frontend/src/context/PhoneReportsContext.jsx` | Global state: reports, filters, selections. |

### Tests
| File | Purpose |
|---|---|
| `tests/test_cellebrite_timeline_e2e.py` | Single end-to-end test against live Neo4j. ~10–15 min runtime. **Coverage gaps: no parser unit tests, no file_linker tests, no writer idempotency tests, no intersection tests, no frontend tests.** |

### Storage artifacts on disk
- `data/evidence.json` — 199 MB / 232K records as of 2026-05-06. Currently bloated with ~164K Cellebrite extraction-leaf rows from one case (`43f1afb1...`). v2 must avoid creating these rows in the first place.
- `ingestion/data/<case_id>/<UFED Report folder>/` — typical structure: one top-level `Report.xml` + `chats/`, `contacts/`, `files/{Audio,Image,Video,Document,...}/`, `photos/`, `useraccounts/`, `thumbnails/`, `databases/`, `decoded/`, `native/`, `FileUploads/`.

---

## 3. What v1 got right — preserve in v2

These are non-obvious wins. **Port the idea even if the code gets rewritten.**

1. **Streaming XML parse.** `parser.py` uses `iterparse` and yields `ParsedModel` batches of 200 — constant memory regardless of XML size. Keep this contract.
2. **Per-node `cellebrite_report_key` tag.** `neo4j_writer.py` stamps every node it writes with `cellebrite_report_key`, `case_id`, `source_type="cellebrite"`, `cellebrite_id` (original UUID). This is what makes bulk delete and per-report filtering tractable. Keep the convention.
3. **`MERGE` on `(case_id, key)` for `PhoneReport`.** Commit `056ac35` ("Upsert PhoneReport on ingest to prevent duplicate nodes") was a real bug fix. Idempotent re-ingest is a hard requirement.
4. **Person dedup chain.** `_generated_person_key()` (lines 54–90 in `neo4j_writer.py`): phone → email → app-ID → name. The order matters; preserve it.
5. **Pre-ingest collision check.** `check_cellebrite_report()` parses just the XML header (first 4KB) for metadata + collision flag, before committing to a multi-minute parse. Cheap, fast, and prevents accidental double-ingest.
6. **Background-task pattern.** Ingestion runs via `background_task_storage` so the upload request returns immediately and progress is surfaced through the same UI plumbing as other long jobs.
7. **Modular intersection analytics.** `cellebrite_intersection_service.py` is on-demand and pure read — not part of ingest. Keep it that way.
8. **Rich frontend surface.** Comms Center, Timeline, Event Center, Cross-Phone Graph, Files Explorer represent real investigator workflows. Don't strip features in v2; refactor underneath.
9. **Forensic provenance.** Every node carries the original Cellebrite UUID. Investigators can correlate findings back to source. Don't drop this.

---

## 4. What v1 got wrong — fix in v2

Listed with **root cause** (not just symptom), so v2 design avoids the same trap.

### 4.1 Extraction leaves registered as evidence rows (the big one)
- **Symptom:** `data/evidence.json` has 164K rows in one case; Process Evidence page hangs on a 50 MB JSON response.
- **Root cause:** `_sync_filesystem_blocking()` in `routers/evidence.py` walks the case directory and registers every file it doesn't recognize. Cellebrite extractions aren't a single logical unit in v1's data model — they're "a folder full of files," indistinguishable from any other upload.
- **Why the prune fix isn't enough:** Detection relies on `*.xml` glob at the folder top. UFED variants (`*.xmlExtra`, `*.xmlTranslation`, `*.xmlNodeSource`) bypass it. We patched with a path-fingerprint filter at the *list* layer, but the rows are still in the store and bloat every save.
- **v2 fix:** Treat a Cellebrite extraction as a *single logical evidence unit* (one `EvidenceRecord` whose `kind = "cellebrite_extraction"` and whose `stored_path` points at the folder root). Per-file leaves are accessed through a Cellebrite-specific API (`/cellebrite/files/...`) and NEVER live in `evidence.json`.
- **Detection in v2:** Multi-signal — XML-namespace match OR folder-shape signal (presence of ≥2 of `chats/`, `files/`, `useraccounts/`, `databases/`, `thumbnails/`, `decoded/`, `native/`, `FileUploads/`). Match on any.

### 4.2 Single-XML assumption
- **Symptom:** The 4th-folder case in our debug session had no plain `Report.xml` — only suffixed variants. Detection failed.
- **Root cause:** `detect_cellebrite_xml()` (`ingestion.py:37`) does `*.xml` glob and picks one.
- **v2 fix:** Search for any file whose first 4KB matches the Cellebrite namespace marker, regardless of extension. If multiple are present, document the priority (main `.xml` wins; suffixed variants are merged or ignored per spec).

### 4.3 `parse_tagged_files()` likely loads bulk into memory
- **Symptom:** Not yet observed in production, but the rest of the parser is streaming so this is a soft spot for big extractions.
- **Root cause:** Tagged-files block parsed in one pass.
- **v2 fix:** Stream tagged-files too. If we need a full UUID→path map, build it lazily / page it.

### 4.4 Re-ingest doesn't cascade-clean dropped entity types
- **Symptom:** None observed yet — but if v2 drops or renames a model type, the old v1 nodes from a prior ingest will linger because MERGE only touches what it writes.
- **Root cause:** MERGE-only strategy assumes the writer covers everything every time.
- **v2 fix:** Tag every node not just with `cellebrite_report_key` but with `ingest_schema_version`. Re-ingest deletes nodes whose schema_version is older than the current writer's, then writes fresh.

### 4.5 Intersection service loads up to 20K events into Python
- **Symptom:** `_load_events()` (`cellebrite_intersection_service.py:82`) hard-caps at 20K. Beyond that, intersection analysis silently misses events.
- **Root cause:** Cross-phone sweep done in Python instead of in Cypher.
- **v2 fix:** Push the sweep into Cypher (spatial windowing + temporal join) or, if that's too gnarly, page through events with explicit pagination — never silently truncate.

### 4.5b Timeline silent truncation — investigator integrity issue
- **Why this is a hard problem, not a soft one:** Confirmed by the user 2026-05-06 — when the events endpoint was called with a normal limit, **the Timeline silently dropped events**. Investigators were drawing conclusions from incomplete timelines without knowing the data was clipped. That's a forensic-integrity bug, not a performance bug.
- **Current bandaid:** Frontend calls `/api/cellebrite/events?limit=500000` to make truncation extremely unlikely. Cost: multi-MB JSON per load, ~10 MB of response data queued on flaky links, page appears to hang. Backend Neo4j is also asked to materialize all events in one shot.
- **Root cause:** No pagination contract between the timeline view and the events endpoint, AND no signal back to the user when results were clipped. Silent truncation is the worst possible failure mode for an investigative tool.
- **v2 fix (in priority order):**
  1. **Truncation must never be silent.** Any list response that hits a server-side cap returns a `truncated: true` flag and a `cursor` to fetch the next page. Frontend surfaces this — "showing 1–10,000 of N+ events" — never shows N events when there are more.
  2. **Real cursor-based pagination on `/api/cellebrite/events`.** Ordered by timestamp; cursor = (timestamp, id) tuple.
  3. **Virtualized timeline on the frontend.** Fetches a window around the visible zoom/scroll position; scrolling/zooming out fetches more. Network load drops from ~10 MB to tens of KB per interaction.
  4. **Client-side aggregation at coarse zooms.** When the user is zoomed all the way out (full case timeline), the server returns time-bucketed counts (e.g. per-day event counts), not raw events. Bucket resolution increases as the user zooms in.

### 4.6 N+1 attachment resolution
- **Symptom:** `_resolve_attachments()` (`routers/cellebrite.py:219`) does one evidence lookup per message attachment. 500-message thread = 500 round-trips.
- **Root cause:** No batch endpoint.
- **v2 fix:** Resolve attachments in a single batch query when loading a thread.

### 4.7 Collision check runs twice
- **Symptom:** Both frontend pre-check and ingest-time check re-query Neo4j.
- **v2 fix:** One source of truth; cache the check result on the background task and consult it during ingest.

### 4.8 Heavy client-side state
- **Symptom:** `PhoneReportsContext` likely holds full reports / contacts / threads in memory.
- **Root cause:** No server-side pagination contract.
- **v2 fix:** Server-paginated APIs from day one. Even small UFED extractions can blow up on phones with heavy usage.

### 4.9 Test coverage skewed to E2E only
- **Symptom:** One 10–15 min E2E test, no unit coverage for parser / writer / linker / intersection.
- **v2 fix:** Unit tests on parser fixtures (small XML samples), writer idempotency tests with a Neo4j sandbox, linker path-resolution tests. E2E becomes the smoke test, not the only test.

### 4.10 Path-pattern filter is a maintenance debt
- **What it is:** `_looks_like_cellebrite_artifact()` (`routers/evidence.py:133-146`) — string match on UFED folder names.
- **Why it exists:** Stopgap so the v1 list endpoint doesn't return 164K artifact rows.
- **v2 fix:** Becomes unnecessary because v2 doesn't register artifact rows in the first place. Remove the filter once v1 data is migrated.

---

## 5. v2 design principles (the contract)

These are the principles every v2 Cellebrite component must obey. If a proposed change violates one of these, stop and reconsider.

1. **A Cellebrite extraction is one evidence unit.** One row in evidence storage, one PhoneReport node in Neo4j, an opaque folder on disk. Per-file leaves are Cellebrite-domain objects, not Evidence objects.
2. **Detection is multi-signal, no single point of failure.** Namespace match + folder-shape signal. A UFED folder must be detectable even with no plain `.xml` at the top.
3. **Streaming throughout ingest.** Header parse, model parse, tagged-files parse, neo4j writes — all bounded memory regardless of extraction size.
4. **Idempotent re-ingest with schema versioning.** `ingest_schema_version` on every node. Re-ingest cleans up nodes from older schemas before writing.
5. **Pagination is a server-side contract, not a client-side concern.** Every list endpoint has explicit `limit`/`cursor` parameters. Frontend never assumes the full result set fits in memory.
5a. **Silent truncation is forbidden.** Any list response that hits a cap MUST return `truncated: true` plus a continuation cursor. The frontend MUST surface this — "showing N of M+" — so an investigator never reads incomplete data as complete. This is a forensic-integrity rule, not a UX nicety.
6. **No N+1 in the read path.** Attachments, contacts, related entities — resolve in batch.
7. **Tests are unit-first.** E2E exists, but every parser change ships with a fixture-based unit test.
8. **Forensic provenance is non-negotiable.** Every node retains its original Cellebrite UUID and a reference back to the source extraction.
9. **Heavy work is opt-in.** Intersection analytics are computed on demand, not at ingest. Same for any future analytics.
10. **Detection and filtering happen in one place.** v1 has the detection logic split across `ingestion.py`, `evidence.py`, and the path-fingerprint filter. v2 has one Cellebrite detector that everyone calls.

---

## 6. Component-by-component porting plan

For each component: what to port, what to rewrite, what to drop. Update the **Status** markers as v2 work lands.

### 6.1 Detector
**Status:** ☐ Not started
- **Port:** namespace-match logic (4KB header read).
- **Rewrite:** add folder-shape signal (≥2 of named subfolders). Single detector function used by ingestion, sync-filesystem, and the list-endpoint filter.
- **Drop:** the standalone `_looks_like_cellebrite_artifact()` path filter (becomes unnecessary).

### 6.2 Parser
**Status:** ☐ Not started
- **Port:** `iterparse` streaming, batch_size=200, model dispatch table (32 model types listed in survey §2).
- **Rewrite:** `parse_tagged_files()` to stream. Header parse must handle multiple matching XMLs (suffixed variants).
- **Drop:** nothing — parser is one of v1's stronger pieces.

### 6.3 File linker
**Status:** ☐ Not started
- **Port:** UUID→path mapping, SHA-256, category detection.
- **Rewrite:** the linker should NOT register evidence rows for leaves. It can produce a map / index for Cellebrite-domain queries, but those entries are not `EvidenceRecord` rows.

### 6.4 Neo4j writer
**Status:** ☐ Not started
- **Port:** MERGE strategy, `cellebrite_report_key` tagging, person-dedup chain.
- **Add:** `ingest_schema_version` on every node. Pre-write cleanup of older-version nodes for the same `cellebrite_report_key`.
- **Add:** explicit batched delete for re-ingest (don't rely solely on MERGE to overwrite).

### 6.5 Ingestion orchestrator
**Status:** ☐ Not started
- **Port:** 9-step structure with progress logging.
- **Rewrite:** the step that registered per-file evidence rows is removed. Instead, register a single `EvidenceRecord` of kind `cellebrite_extraction` pointing at the folder root.

### 6.6 Service layer
**Status:** ☐ Not started
- **Port:** `check_cellebrite_report` (header parse + collision check), `process_cellebrite_report` (background task wrapper).
- **Rewrite:** unify collision check — one path, cached on the background task, consumed by ingest.
- **Port wholesale:** `cellebrite_intersection_service.py` after pushing the event-sweep into Cypher (or formal pagination).

### 6.7 Read API (`backend/routers/cellebrite.py`)
**Status:** ☐ Not started
- **Port:** all endpoint shapes (list reports, comms, timeline, events, cross-phone graph, file tree, intersections). The frontend depends on these.
- **Rewrite:** every list endpoint gains `limit` + `cursor`. Attachment resolution becomes batch.
- **Drop:** any endpoint that's confirmed unused after a frontend audit (TBD).

### 6.8 Evidence list integration
**Status:** ☐ Not started
- **v2 contract:** an `EvidenceRecord` of kind `cellebrite_extraction` is shown in Process Evidence as a single row labeled with the device + extraction date. Clicking it navigates to the existing Cellebrite views — it does NOT expand into per-file rows.
- **Drop:** all the v1 path-fingerprint filtering, the `_cellebrite_root_prefixes` cache, the `_is_cellebrite_report_root` filesystem peek from the list endpoint. Detector returns a clean answer at ingest time and is never re-run on every list call.

### 6.9 Frontend
**Status:** ☐ Not started
- **Port:** all 8 major views (`CellebritePhonesSection`, `CellebriteOverview`, `CellebriteCommsCenter`, `CellebriteCommunicationView`, `CellebriteTimeline`, `CellebriteEventCenter`, `CellebriteCrossPhoneGraph`, `CellebriteFilesExplorer`). Plus `comms/`, `events/`, `overview/` subtrees.
- **Rewrite:** `PhoneReportsContext` to drive paginated fetches instead of holding global state. `cellebriteSearch.js` to call a server endpoint instead of doing client-side text match (or document explicitly that it's intentional and bounded).
- **Drop:** any view that the frontend audit shows as unused.

### 6.10 Tests
**Status:** ☐ Not started
- **Port:** the existing E2E timeline test as a smoke test.
- **Add:** parser unit tests on small fixtures (one fixture per model type at minimum).
- **Add:** writer idempotency tests (ingest → ingest again → verify no duplicates).
- **Add:** linker tests (path resolution, category detection edge cases).
- **Add:** detector tests (namespace-match-only, folder-shape-only, both, neither).

---

## 7. Migration sequence

Don't try to flip Cellebrite in a single PR. Order:

1. **Detector first.** Build and test the new multi-signal detector standalone. Land it; have v1 *and* v2 both use it.
2. **Evidence-record contract second.** Define the `kind = "cellebrite_extraction"` row shape. Add a one-shot migration that collapses the legacy 164K leaf rows in `evidence.json` into single extraction rows (or just deletes them and re-detects).
3. **Ingest path third.** New writer with `ingest_schema_version`, new orchestrator that produces the single evidence row.
4. **Read API fourth.** Pagination + batch attachment resolution. Frontend keeps working off existing endpoints until then.
5. **Frontend fifth.** Refactor `PhoneReportsContext` to paginate. Views ported one at a time, behind a feature flag if needed.
6. **Cleanup last.** Once v2 is the default, remove the v1 path-fingerprint filter, `_cellebrite_root_prefixes`, `_is_cellebrite_report_root` from `routers/evidence.py`. Delete legacy filtering code. Shrink `evidence.json` migration finalizes.

---

## 8. Open questions / decisions needed before porting

These are blockers for v2 work. **Don't guess; ask.**

1. **Where does v2 live?** Same repo, different branch? Separate repo? Same backend, different routes? This drives every other decision.
2. **Migration of existing v1 data:** do we migrate the existing PhoneReport nodes in Neo4j (re-tag with `ingest_schema_version`)? Or wipe + re-ingest from the original UFED folders?
3. **`evidence.json` cleanup:** the user explicitly deferred this on v1 (see `WORKING.md` decision 2026-05-06). When v2 lands, do we (a) collapse the 164K legacy rows into single extraction rows in place, (b) wipe and re-detect, or (c) leave them as orphans filtered out by the existing v1 filter?
4. **Frontend feature flagging:** can we ship v2 frontend views behind a flag and let users toggle? Or is it a hard cutover?
5. **Backwards compat for saved investigator artifacts:** any user-created tags, notes, or links anchored to v1 PhoneReport / Communication / Person nodes — do we preserve those in v2? Probably yes, but we need a node-ID continuity story.
6. **Performance budget:** what's the target ingest time per GB of UFED data? What's the target page-load on a phone with 100K messages? v1 has no documented budget; v2 should set one.
7. **Multi-XML semantics:** when a UFED export has both `Report.xml` and `Report.xmlExtra`, are these the *same data* (skip the variants) or *complementary data* (merge them)? Confirm with a real example before coding.

---

## 9. Quick-reference: known commits worth re-reading

When porting, these v1 commits encode lessons learned. Read the diff before touching the equivalent v2 area.

| Commit | Lesson |
|---|---|
| `056ac35` | Upsert PhoneReport on ingest — idempotency was a real bug |
| `4c73e60` | Parser coverage, dedup detection, delete, name override |
| `9439f73` | Bidirectional thread dedup — comms threads need care |
| `aeb3e59` | Timeline silently dropping recent events — TZ + filter logic is fragile |
| `bf3568e` | Phase 4 backfill + TZ compare — same theme, different surface |
| `609f81f` | Histogram scrubber + dedup + chips — the "big UX commit" worth studying for what users actually use |
| `4f0ec5b` | Full-text message search — confirms server-side search is needed |

Run `git log --oneline -- '**/*ellebrite*' '**/cellebrite/*'` to refresh this list when porting.

---

## 10. How to use this document

- Re-read §3 (what v1 got right) and §4 (what v1 got wrong) before designing any v2 component.
- Use §6 as a checklist; flip ☐ to ✅ as components land. Don't skip components — gaps create the same kind of incremental drift v1 suffered from.
- §8 questions are blockers; resolve them with the user before writing v2 code.
- §5 principles are the contract. If a v2 PR violates a principle, that's a blocker discussion, not a "we'll fix it later."
