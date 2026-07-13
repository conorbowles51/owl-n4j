# V2 Bridging Roadmap — ticket backlog
### Companion to `V1_V2_DIVERGENCE_REPORT.md` (the gap assessment)

_2026-07-13. One ticket per gap between v1 (the dev/test environment, now feature-frozen) and v2 (The Platform). Each ticket carries: what/why, the v1 reference (commits/files to port from), acceptance criteria, size, and a recommendation. Designed to be transcribed into Docket tickets — titles are written to be pasted as-is._

**Sizes:** S = hours–1 day · M = 2–5 days · L = 1–2 weeks · XL = multi-week (split before ticketing).
**Recommendations:** **PORT** (bring v1's implementation over) · **REBUILD** (meet the same need v2-natively) · **FIX** (v2 bug, no v1 port needed) · **DECIDE** (product call needed before work starts) · **DROP** (recommend not doing — listed so the drop is conscious).

---

## Portfolio summary

| Epic | Tickets | Priority | Weight |
|---|---|---|---|
| E1 Security & stability | BRG-001 … 009 | P0 | ~2 weeks, one dev |
| E2 Cellebrite ingestion integrity | BRG-010 … 017 | P1 — **gates any UFED re-ingest** | ~3–4 weeks |
| E3 Cellebrite application surfaces | BRG-018 … 025 | P2 | largest epic; 2 XLs to split |
| E4 Financial investigation | BRG-026 … 030 | P2 | ~2–3 weeks + one data decision |
| E5 Evidence intake | BRG-031 … 034 | P2 | ~2–3 weeks + one decision |
| E6 Reporting & export | BRG-035 … 038 | P2 | ~3–4 weeks; the courtroom deliverables |
| E7 Provenance, audit & AI accountability | BRG-039 … 045 | P3 | ~2 weeks + two decisions |
| E8 Honest limits (truncation signalling) | BRG-046 | P3 | ~1 week |
| E9 Enterprise readiness & cutover | BRG-047 … 052 | P4 | ~3–4 weeks |

**Decision tickets to schedule with Neil first** (each blocks work): BRG-025 (comms tally), BRG-029 (CSV notes import), BRG-030 (transaction data path), BRG-033 (wiretap), BRG-034 (on-demand media AI), BRG-043 (chat privacy), BRG-044 (manual vs AI merge), BRG-050 (QA hub), BRG-051 (command palette).

**Conscious drops (no ticket, recorded here):** `/nodes-by-type` legend endpoint (superseded by v2 edit-schema/spotlight) · fcntl JSON-locking fixes (moot on Postgres) · v1 server-side financial pagination experiment (reverted on v1 itself) · DKT-40 timeline TZ filter variant (net-reverted on v1) · v1's jsPDF client-side export *implementation* (the capability is BRG-035, the implementation is superseded).

---

## E1 · Security & stability — P0, do first, no dependencies

**BRG-001 · Remove unauthenticated write-Cypher endpoints** — S · FIX
`POST /api/graph/execute-single-query` and `/execute-batch-queries` accept arbitrary write Cypher with **no authentication** — an evidence-tampering vector. Verified 2026-07-13: no callers in v2 frontend, evidence-engine, or ingestion (dead code from v1's case-version loader).
Done when: endpoints deleted (preferred) or auth-gated + read-only; case-version load still works; OpenAPI no longer lists them.

**BRG-002 · Require auth on `/api/graph/locations`** — S · FIX
Returns any case's location points unauthenticated today.
Done when: 401 without token, 403 without case membership.

**BRG-003 · NaN-safe financial aggregates with visible exclusion counts** — S · FIX
One stored NaN amount turns `sum()/max()` into NaN, which `safe_float` flattens to **$0** — v1's flagship case shows $0 over 43,805 transactions today, and v2 has the identical code path. 144 unparseable amounts also vanish silently from aggregates.
Done when: aggregates skip non-finite amounts in Cypher; response carries `excluded_count`; UI shows "N amounts could not be parsed" when nonzero. (No-silent-truncation rule.)

**BRG-004 · Fix `/api/chat/extract-nodes` 500** — S · PORT (v1 `cbf70e9`)
`get_graph_summary()` is called without its required `case_id` → deterministic TypeError on every call. Port the v1 fix; adds the missing case isolation too.
Done when: endpoint returns a result graph for a real case; cross-case leakage test passes.

**BRG-005 · Fix theory & investigation timeline 500** — M · FIX
`DetachedInstanceError: <EvidenceFile> is not bound to a Session` in `workspace_service.get_theory_timeline` / `get_investigation_timeline`. Blocks theories and snapshot inputs.
Done when: both endpoints 200 with correct events on a case with theories + attached evidence.

**BRG-006 · Repair Cypher panel and case-scope `/api/query`** — S · FIX
`CypherPanel.tsx` posts to `/api/graph/cypher` (404; real route `/api/query`, different response shape). Separately `/api/query` reads the whole Neo4j DB across cases.
Done when: panel executes reads against the user's case only; write attempts rejected; response rendering matches.

**BRG-007 · Bound betweenness centrality** — M · FIX
Hangs >120s on a 7.6k-node case, synchronously.
Done when: returns bounded results or runs async with progress; never blocks >10s inline.

**BRG-008 · Stop event-loop blocking on Neo4j calls** — M · PORT (pattern from v1 `fe6d266`)
v2's handlers are `async def` calling the blocking Neo4j driver — one long graph query freezes the whole backend.
Done when: blocking calls run in threadpool (`def` handlers or `to_thread`); concurrent-request smoke test passes during a heavy graph query.

**BRG-009 · Auth on profile CRUD** — S · FIX
Processing-profile create/delete has no auth dependency (inherited gap, present in both trees; fix forward in v2 only).
Done when: profile mutations require an authenticated admin.

---

## E2 · Cellebrite ingestion integrity — P1. **Nothing re-ingests UFED data into v2 until this epic is done**, or the data will be silently incomplete and mis-keyed in ways later porting can't repair.

**BRG-010 · Port the ~19 missing artifact writers** — L · PORT (v1 `ingestion/scripts/cellebrite/neo4j_writer.py:1175-1224` dispatch)
v2's ingester writes ~38% of v1's artifact coverage. Missing: Notification, Voicemail, NetworkUsage (**parsed then silently dropped today**), Autofill, InstalledApplication, SIMData, Journey, DictionaryWord, SocialMediaActivity, ChatActivity, FileDownload, FileUpload, Note, DeviceConnectivity, Cookie, LogEntry, MotionActivity/ActivitySensorData, AppsUsageLog, User.
Done when: writer dispatch parity with v1; reconciliation report shows no parsed-but-unwritten model types.

**BRG-011 · Port ingestion integrity gates** — M · PORT (v1 `35fe75a`, `3040228`, `9f0f397`, `1b8a32c`)
Four gates v1 added after real failures: (a) hard-fail on empty `phone_numbers` (broken investigative views otherwise); (b) IMEI/MSISDN-fallback report keys (today two numberless devices collide as "duplicates" — wrong dedupe verdict can overwrite a distinct device); (c) nested-XML BFS detection to depth 6 (DKT-34 — real customer zips are `Report/Report/*.xml`, undetectable today); (d) under-count coverage warnings.
Done when: each gate has a fixture test reproducing the original failure.

**BRG-012 · Port owner-number/name inference** — M · PORT (v1 `f4cae84`)
Full-file-system extractions omit the header MSISDN and have an empty IsPhoneOwner party; v1 infers the owner from comms Account fields behind a 3-tier gate. Without it, FFS-extracted phones have no owner identity. Must not overwrite manually-set owners.
Done when: FFS fixture ingests with correct owner; manual-owner cases untouched.

**BRG-013 · Port international phone normalization** — S–M · PORT (v1 `8e730a4`, `backend/services/phone_normalise.py`)
v2 uses a US-centric regex for identity keys → international numbers conflate or split contacts.
Done when: libphonenumber E.164 keys everywhere the regex was used; identity-key regression fixtures pass.

**BRG-014 · Port contact-alias preservation + WhatsApp identity unification** — M · PORT (v1 `8510947`, `92d9cc6`)
All saved names/aliases per contact preserved (`_merge_contact_entry`); WhatsApp account numbers unified to the person.
Done when: multi-alias fixture retains every saved name; WhatsApp fixture resolves to one identity.

**BRG-015 · Geo ingestion: geotag harvest, coordinate coverage, fast reverse-geocoder** — M · PORT (v1 `b47e60f`, `09bd9a8`, `e072fb2`)
Photo-EXIF geotag harvest and all-coordinates capture are missing; v2's reverse geocoder still runs in the fork-per-call mode that collapsed v1 ingest to <1 model/s; the live geocoder isn't running at all.
Done when: geotagged-photo fixture produces map points; RGeocoder mode=1 + coordinate cache in place; `geocoder/status` reports ready.

**BRG-016 · Media linkage: trust Cellebrite metadata type over file extension** — S · PORT (v1 `fc20c20`)
Done when: odd-extension audio/media fixture links to its message.

**BRG-017 · Re-ingest the UFED corpus into v2 and reconcile against v1** — M · blocked by BRG-010…016
Done when: per-report reconciliation matches v1's counts per artifact type (or every difference is explained and logged); sequential ingest with memory monitoring per the C2-zombie lesson.

---

## E3 · Cellebrite application surfaces — P2. ~131 v1 commits across 6 families. The two XLs should be split into Docket-sized tickets at sprint planning.

**BRG-018 · Timeline second wave** — XL, split · PORT
Owner + recipient attribution on events (today owner-sent shows "Unknown"), timezone-correct display (`cellebriteTime` util + TZ selector — timestamps are stored UTC; day boundaries are wrong without it), multi-source duplicate collapse, inline media (thumbnails/voice player/full bodies), virtualized rows, keyset `/events` pagination + envelope endpoint, event-type coverage (Calendar, media-as-events, Autofill, Notification, Voicemail — pairs with BRG-010).
v1 refs: `0da927e`, `fd82ea7`, `55d82be`/`71c1a1b`/`81520e0`, `3cf58bf`, `504bcde`/`debb7cf`, `8c45053`, `8d3aeb3`/`4a74c1c`/`db56c5e`.
Done when: the DKT-23 duplicate repro and owner-attribution repro both pass on v2 with re-ingested data.

**BRG-019 · Cross-phone graph rebuild** — XL, split · PORT (~30 commits, `49105bc` `1b13d71` `3828e41` `546e1ab` `2395fb4` `9942414` era)
Directional edges + flow view, time-axis layout, server-side graph search + subgraph, expand-neighbours/pivot, path-flow between two people, edge-click event detail, honest cap counter (v1 `5bca0a8` lifted v2's silent 200/300 cap). v2 has the 331-line pre-rebuild snapshot.
Done when: direction/flow view works on re-ingested multi-phone case; no silent caps (ties to BRG-046).

**BRG-020 · Callouts + client report + Report tab** — L · PORT (`6360848`, `87ae085`, `864d7fa`, `d18eea7`)
Mark key events → assembled client report; per-device forensic Report tab with PDF. This is a client-deliverable workflow — weigh against BRG-035 so report generation lands on one foundation.
Done when: mark → report → PDF round-trip works on v2.

**BRG-021 · Search & Discovery center** — L · PORT (`b6f5023` + typeahead/search-help commits)
Unified search across artifact types; includes the DKT-42 lesson (haystack must lowercase participant names).
Done when: DKT-42 repro (contact-name search finds generically-titled 1:1 chat) passes.

**BRG-022 · Identity resolution & per-device naming** — L · PORT (`72dfa27`, `ac75970`, `d4ec444`, `06f10d0`, `9c2fd9c`, `b51604d`)
Investigator-asserted person merge (audited, reversible), person search, per-device perspective as default with opt-in rollup, number-alongside-name via shared PersonName everywhere. These encode explicit product decisions already made — port as specified, don't re-litigate.
Done when: merge/unmerge audited; every cellebrite surface shows number with name.

**BRG-023 · Locations at full scale** — M · PORT (`dc5103e`, `09bd9a8`, `0111bb4`)
Canvas all-points layer + lean fetch + 5,000-point cap removal (silent truncation of location evidence today), map-freeze fix.
Done when: full location set renders on the re-ingested corpus without cap.

**BRG-024 · DKT regression verification pass** — M · FIX/verify
After BRG-018/019/021 land, re-run every post-May DKT repro on v2 (DKT-23, 27, 29, 31, 34, 42 + the comms-center fixes). Most should be covered by the ports; this ticket is the proof.
Done when: each DKT repro documented as passing on v2.

**BRG-025 · Comms tally / "most contacted"** — S · **DECIDE**
DKT-43 was built then reverted on v1 main itself. Decide whether The Platform wants it; the envelope-path implementation exists on branch `docket/DKT-43` if yes.

---

## E4 · Financial investigation — P2

**BRG-026 · Port the `data_version` audit filter, reconciled with v2's `mode` axis** — M · PORT+design (v1 `d03757b` era)
v1 separates original vs re-audited (reprocessed) transactions; v2 separates evidence-backed vs LLM-inferred (`mode=transactions|intelligence`). These answer different questions — keep both axes.
Done when: both filters work independently on the transaction list and export; combined-filter behaviour specified and tested.

**BRG-027 · Payments/Receipts semantics** — S–M · PORT (v1 `c4fe355`)
Sign-based Payments (negative) / Receipts (positive) computation + UI rename; v2 still shows pre-sprint "Money In/Out". Includes the sign-normalization convention from TRANSACTION_REPROCESS_PLAN §3.0.1.
Done when: summary cards + export match v1's semantics on migrated data.

**BRG-028 · Financial export: merge the sprint design into v2's export service** — L · REBUILD
v1's export gained Money Flow perspective, per-entity breakdown pages, section picker, embedded charts; v2 independently built provenance labels + entity-flow tables + grouping. Don't port v1's file wholesale — specify the union on v2's foundation.
Done when: one export offering both perspectives; corrected amounts keep ✎ + footnotes; section picker works.

**BRG-029 · CSV notes import + transaction ref IDs + auto-extract categories** — M · **DECIDE** (v1 `7dbbe46`)
Built for the reprocess sprint workflow. Decide whether The Platform needs bulk notes import, or whether it was sprint scaffolding.

**BRG-030 · Get transaction data into v2** — L · **DECIDE first**
v2 has **zero** statement-extracted transactions; its financial module can't be QA'd. Two paths: (a) migrate v1's curated Neo4j transaction subgraph (preserves the reprocess sprint's 10K+ re-extracted, categorized, audited txns), or (b) re-extract from source statements through evidence-engine (clean but re-does months of curation). Recommendation: (a) — the curation and audit trail are the value.
Done when: chosen path executed; v1/v2 totals reconcile; curation history (original_amount, correction_reason) intact.

---

## E5 · Evidence intake — P2

**BRG-031 · tus resumable uploads** — L · PORT (v1 `6558672`…`1f63e3d`, `deploy/owl-tusd.service`, tus hooks, Uppy component)
Proven at 31.8GB and 35GB on v1. Without it, interrupted large uploads restart from zero and v2's synchronous in-request path times out at 1h.
Done when: a multi-GB upload survives an interruption and resumes; ingest triggers on completion.

**BRG-032 · Upload robustness + failure surfacing** — M · PORT (v1 `3040228`, `7e451cb`, `9fdb8d1`, `1f63e3d`/`2c0428e`)
Background registration, per-file failure counts, whole-batch-failure detection (100%-failed must never read COMPLETED), ENOSPC→507, amber "Action needed" task for silently-skipped no-phone reports.
Done when: each failure mode has a test and a visible user signal.

**BRG-033 · Wiretap pipeline** — M–L · **DECIDE**
v2's `/wiretap/process` is a stub returning "retired" while the route stays live. Either port v1's triad pipeline (`wiretap_service.py` + `ingest_audio.py`: .wav transcribe/translate, .sri parse, .rtf interpretation) or retire it properly (remove route + profile rules, document). A live endpoint that silently does nothing is the worst of both.
Done when: decision executed; no dead route either way.

**BRG-034 · On-demand media AI analysis** — M · **DECIDE** (v1 `ed6146e`)
v1: per-file on-demand transcribe/image-recognition, cached, **local Whisper** (offline-capable). v2: at-ingest only, via OpenAI (cloud dependency, no re-run). Decide whether on-demand + offline capability matters for enterprise deployments (air-gapped clients?).

---

## E6 · Reporting & export — P2. The courtroom deliverables; v2 currently cannot produce a case artifact.

**BRG-035 · Case export (the 15-section HTML/PDF)** — XL, split · REBUILD
Server-side on v2's `timeline_view_service` foundation (WeasyPrint already there), using v1's export as the content spec: all 15 sections including **audit log, transcriptions, rendered graph/timeline/map visualizations**, and confidentiality labels (v1 `05dc351`).
Done when: a full case export renders with every section on real data; audit log included; snapshot of output reviewed by an investigator.

**BRG-036 · Theory-scoped export** — M · REBUILD (depends BRG-035)
**BRG-037 · Snapshot PDF export** — M · REBUILD (depends BRG-035)
**BRG-038 · Map locations CSV export** — S · PORT (v1 `25bce82`, DKT-5)

---

## E7 · Provenance, audit & AI accountability — P3

**BRG-039 · Provenance stamps on user-created nodes + bool serialization fix** — S · PORT (v1 `ca91b9d`)
v2 can't distinguish investigator-authored nodes from ingested evidence; and booleans serialize as 1/0 (type-check ordering bug v1 fixed in the same commit).
Done when: manual nodes carry `user_created/created_by/created_at/source`; bools round-trip as booleans.

**BRG-040 · Complete AI-spend metering** — M · FIX
v2 meters only the final chat answer; classify/cypher-gen legs and the relationship-analyzer, triage-LLM, and evidence-processing call sites record nothing; Ollama leaves no row on either design. "No row" must never mean "no inference".
Done when: every LLM call site writes a ledger row (Ollama at $0); a full chat interaction shows all its legs.

**BRG-041 · System-log case filter + audit retention** — M · PORT (`3861f4d`) + REBUILD
Restore the `case_id` audit filter; replace the silent 10K-row hard-trim with archival or explicit retention policy (enterprise requirement — hard-deleting oldest audit rows is indefensible).

**BRG-042 · View-aware chat context from real views** — M · REBUILD (spec from v1 `f871397`; depends on E3/E4 surfaces landing)
v1 published what-the-analyst-sees (with row previews) from financial, cellebrite comms/events/files, graph-table, and workspace; v2's narrower contract has one publisher. Re-publish from the ported views using v2's contract.

**BRG-043 · Chat privacy semantics** — S · **DECIDE**
v1: conversations owner-only. v2: any case member can read any member's conversations. Silent change; pick deliberately (enterprise default: owner-only with explicit share).

**BRG-044 · Investigator-controlled merge path** — M · **DECIDE**
v2's AI merge is more robust (async, locks, crash recovery, reversible) but the LLM chooses the surviving facts; v1's manual merge + 3-step bulk wizard let the investigator decide field-by-field. For forensic defensibility, recommend restoring a manual mode inside v2's merge job (investigator-reviewed field selection), not a port of the old wizard.

**BRG-045 · QA/testing hub** — S–M · **DECIDE** (see BRG-050 note)
`/api/testing/*` (tester checklist + feedback capture) exists only on v1 and is the live channel for tester feedback (TESTING_FEEDBACK_STATE workflow). If alpha testing moves to v2, this must move with it or be replaced.

---

## E8 · Honest limits — P3

**BRG-046 · `total` + `truncated` + visible banners on every capped surface** — M–L · FIX (pattern: v1 `5bca0a8`, `61961f4`)
One sweep: `/api/graph` (~20K, feeds table/map/CSV), intersections (20K loader discards `truncated`), cross-phone graph (200/300), comms search (200), cellebrite timeline `total_estimate`, v2 timeline client 100-page stop. An analyst asserting "these phones never intersected" must never be reading a silently truncated set.
Done when: every listed surface returns honest totals and the UI shows a truncation banner; grep-level audit confirms no remaining silent caps.

---

## E9 · Enterprise readiness & cutover — P4

**BRG-047 · Production data load + full behavioral QA** — L
Load the production corpus into v2 (BRG-017 + BRG-030 feed this); re-run the 45-item yardstick as live QA — impossible today because v2 is empty.

**BRG-048 · Scale verification** — M
v1 500s on 571k-node cases. Prove v2's architecture handles production scale (ingest + graph reads + exports) or fix what doesn't.

**BRG-049 · Ops runbook + monitoring for the 6-service stack** — M
Neo4j, Postgres, Redis, ChromaDB, engine-API, engine-worker: health checks, restart procedures, disk/memory watermarks (this host has a history: tx-log corruption under memory pressure, tmpfs OOM, uid-ownership breakage). Encode the known failure modes.

**BRG-050 · Alpha feedback channel on v2** — S–M (pairs with BRG-045)
Wherever testers file feedback during alpha, it must point at v2.

**BRG-051 · Command palette: finish or remove** — S · **DECIDE**
Scaffolding-only in both trees; Cmd-K does nothing. Ship it or delete the dead state.

**BRG-052 · v1 cutover & decommission plan** — M
Cutover date, read-only grace period, data archival, DNS/port switch. **Until this executes, v1 runs in production with unauthenticated write-Cypher and `/api/timeline` — the pace of this roadmap is itself a security decision.**

---

## Suggested sequencing

```
Sprint 0 (now):        E1 complete (BRG-001…009) + decision meeting for the 9 DECIDE tickets
Sprints 1–2:           E2 (ingestion gate) → BRG-017 re-ingest | in parallel: BRG-030 txn data path, BRG-031/032 uploads
Sprints 2–5:           E3 (cellebrite surfaces, split XLs) | E4 financial | E6 export (BRG-035 first)
Sprints 5–6:           E5 remainder, E7, E8
Pre-cutover:           E9 (BRG-047 QA gate → BRG-052 cutover)
```

The single biggest schedule risk is E3 (two XLs). The single biggest *integrity* risk is skipping or reordering E2 — do not re-ingest before it.
