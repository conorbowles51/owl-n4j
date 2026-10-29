# 06. Build order

Purpose: one sequence for every build unit defined in specs 01 to 05, with what each depends on, the
test that defines done, and the gates that must pass before the next stage starts. A session picks the
next unit from this file, builds it, tests it, commits it, and rewrites `docs/loupe-build-state.md`, as
`CLAUDE.md` requires. Unit ids are the owning spec's ids (`01-1.3` is spec 01 unit 1.3; `02-U4` is
spec 02 unit U4; `03-5` is spec 03 unit 5; `04-U7`; `05-S3` is spec 05 step 3).

Contents
1. Rules for every unit
2. Where code lives
3. Stages at a glance
4. The sequence, unit by unit
5. Server measurement batch (stage A3)
6. Cross-cutting fixes to existing Loupe that units depend on
7. Removal of the old Cellebrite code
8. Gates between stages
9. Risks and what to do if they occur

---

## 1. Rules for every unit

1. **One unit per session, finished, tested, committed** (`CLAUDE.md`, Working agreement and Session
   hygiene). After each commit, rewrite `docs/loupe-build-state.md` and commit it.
2. **Acceptance tests are the definition of done.** The test listed against a unit in its owning spec
   is written first or alongside, and the unit is not committed until it passes. A "no tests" result is
   never green (`CLAUDE.md`, Tests).
3. **Test suites per tree:**
   - backend: Python 3.10, `cd backend && python3 -m unittest discover -s tests -p 'test_*.py' -t .`
     (the financial suite baseline in `CLAUDE.md` must stay green: 3057 tests, OK, skipped 12);
   - evidence-engine: Python 3.12 or later, run inside the engine container (the build-state file
     records that the engine suite cannot run on Python 3.10);
   - frontend_v2: `npx vitest run --project unit` and `--project browser` with `VITE_CACHE_DIR` set per
     `CLAUDE.md`, plus `npx tsc -b` and `npx eslint .`.
4. **Reference corpus:** C3, C9 and the readable part of C8 on the development machine; the 14 phones
   under `/mnt/owl-data/ingestion-data/` on the server, read-only. Case material is never committed;
   fixtures are synthetic or structure-only.
5. **Measure before building** wherever a spec names a gate (plan 12.1 rule 1). A gate result is recorded
   in `docs/cellebrite/measurements/` (counts only) before the unit that depends on it starts.
6. **No unit deletes data before its replacement is complete** (plan section 4, defects 1 and 2).
7. **Every decision a unit takes that its spec did not** is added to that spec's decisions section with
   what would reverse it, in the same commit.

## 2. Where code lives

| Area | Location | Owning spec |
|---|---|---|
| Detection, intake, capture, counter, reconciliation, files, timestamps, phone worker | `evidence-engine/app/phone/` | 01 |
| Capture and later schema migrations | `backend/postgres/alembic/versions/` (one head) | 01, 02, 04, 05 |
| Registry, interpretation sweep, mappings loader, identity, projections, corrections, edges | `backend/services/phone/` and `backend/scripts/phone_registry_seed.py` | 02 |
| Reviewed mapping files | in-repo JSON, path set in 02 section 6 | 02, 04, 05 |
| Phone API | `backend/routers/phones.py` and sub-modules, prefix `/api/phones` | 03 |
| Pattern-of-life services and tables (`pol_*`) | backend, per 04 section 12 | 04 |
| Investigative approaches (`phone_analysis_*`) | `backend/services/phone_analysis/` | 05 |
| Media derivation (OCR, transcription, translation) | `evidence-engine/app/pipeline/phone_media/` | 05 |
| Frontend | `frontend_v2/src/features/phones/` and related feature folders per 03 | 03, 04 |

If two specs name different roots for the same thing, the owning spec in this table governs.

## 3. Stages at a glance

| Stage | Plan phase | Units | Ends with |
|---|---|---|---|
| A Ground truth | 0 | 01-0.1, 01-0.2, A3 server measurement batch | Counts recorded for C3, C9, C8 and all 14 server phones |
| B Capture | 1, 2 | 01-1.1 to 01-1.7, 01-2.1 to 01-2.4 | Exact reconciliation on every reference document; kill-and-resume proven |
| C Interpretation | 3 | 02-U1 to 02-U7, 04-U1 | A type absent from all code reaches timeline, map and identities |
| D Identity and projections | 4 | 02-U8, U9, U10, U12, U13, U15 | Deleting one of two phones sharing a contact leaves the other intact |
| E Screens | 5 | 03-1 to 03-11 | Every testing-hub item (03 section 17.0) has a passing test |
| F Pattern of life | 7 | 04-U2 to 04-U13 | A statement window shows supporting, contradicting and missing data with sources |
| G Cross-evidence | 6 | 02-U11, 02-U14, 02-U16, 05-S0 to 05-S4, 03-12 | Phone money readings corroborate ledger rows as p4; RSMF export |
| H Investigative approaches | 8 | 05-S5 to 05-S11, 05-S15, 05-S16 | Each approach built only after its gate passes |
| I Media | 9 | 05-S12 to 05-S14 | Local OCR, transcription and translation; video path honours the provider setting |
| J Conditional | | 05-S17 | Runs when a production includes source databases |

Stages E and F may interleave after D: Neil set pattern of life as a priority alongside conversations
(plan section 1, decision 10). The recommended interleave is in section 4.

## 4. The sequence, unit by unit

Each row: unit, what it delivers, depends on, done when (summarised; the owning spec's acceptance test
is authoritative).

### Stage A: ground truth

| # | Unit | Delivers | Depends on | Done when |
|---|---|---|---|---|
| 1 | 01-0.1 | Reference corpus manifest: paths, sizes, container hashes, report version, producer for C3, C9, C8 | nothing | Manifest file in `docs/cellebrite/measurements/` (no content); rerun is identical |
| 2 | 01-0.2 | Element-level counter (lxml) per 01 section 8 | 1 | Counts for C3, C9, C8 stable across runs and equal to the expat cross-check recorded in 01 section 1 |
| 3 | A3 | Server measurement batch, section 5 below | 2 | Every listed measurement recorded; each dependent gate marked pass, fail or changed |

### Stage B: capture

| # | Unit | Delivers | Depends on | Done when |
|---|---|---|---|---|
| 4 | 01-1.1 | Capture schema: ten tables of 01 section 6 | 2 | Upgrade, downgrade, upgrade on empty database; one head; insert and read one row per table |
| 5 | 01-1.2 | Detection and container hashing for UFDR, folder, zip, split sections, protected UFDR | 4 | Each sample and each synthetic form detected with the wording of 01 section 2; container hash matches the upload's |
| 6 | 01-1.3 | Single-pass capture writing one row per model through COPY with a cursor | 5 | Peak memory within 01's budget on C3; second capture of the same bytes writes nothing |
| 7 | 01-1.4 | Recount and reconciliation | 6 | Exact match on C3, C9, readable C8; an injected one-value change fails and names its path |
| 8 | 01-1.5 | Files: entries, seven verification outcomes, three reference mechanisms | 6 | C3 21,664 empty placeholders, C8 9,929 missing, 326 size and 236 MD5 mismatches reported; C9 852 extracted paths linked |
| 9 | 01-1.6 | Timestamps per 01 section 9 (device zone settled: device setting or decision only) | 6 | 22 offset-less values in C3 and 6 in C8 flagged with no instant; examiner zone stored as such |
| 10 | 01-1.7 | Upload path: resumable groups accept `.ufdr`, folder limit 200,000; old upload route no longer deletes containers | 5 | C3 folder (43,144 files) and C9 zip upload end to end on a test stack |
| 11 | 01-2.1 | Phone queue, worker, container | 6 | A phone job does not occupy a general slot; progress on the Redis channel |
| 12 | 01-2.2 | Pause, resume, cancel | 11 | Pause stops after a committed batch; resume completes to an identical capture |
| 13 | 01-2.3 | Staged replace | 11 | Old extraction stays active until the new capture reconciles; replace is an explicit action |
| 14 | 01-2.4 | Kill and resume | 12 | SIGKILL at random points on C3 and C8 resumes to the same reconciliation hashes |

### Stage C: interpretation

| # | Unit | Delivers | Depends on | Done when |
|---|---|---|---|---|
| 15 | 02-U1 | Body walker, `record_uid`, `file_uid`, value parsers | 7, 9 | Field and value counts equal 01's reconciled counts per document |
| 16 | 02-U2 | Registry tables and seed from the 14-phone catalogue | 15 | 62 types, 471 field rows, 55 named sets with 210 values plus `DecodingSourceOptions`, 47 nesting rows; rerun idempotent |
| 17 | 02-U3 | Observation pass and review queue | 16 | Samples raise no flag after seed; a synthetic extraction with six kinds of novelty raises exactly six |
| 18 | 02-U4 | Generic interpretation by value role | 16 | C3 22,881 time rows and 31 points; C8 171 Locations `not_positionable`; a synthetic unknown type appears on timeline and map |
| 19 | 02-U5 | Mapping loader, versions, retroactive applier, suspension on drift | 18 | Changing a mapping re-derives with no capture table written |
| 20 | 02-U6 | Initial type mappings for the core types | 19, A3 | C3: 1,657 calls each with caller and callee; 2,917 messages threaded |
| 21 | 04-U1 | Timestamp-meaning, activity-strength and attribution mapping rows | 19, A3 (04 M1 to M12) | Every (type, time field) has a meaning or explicit `unknown`; DeviceEvent rows written from server-measured values |
| 22 | 02-U7 | Coverage map and endpoint | 20 | C3 lists 35 types and 178 combinations; selection flags verbatim |

### Stage D: identity and projections

| # | Unit | Delivers | Depends on | Done when |
|---|---|---|---|---|
| 23 | 02-U8 | Identifiers, Unicode fold, default region | 18 | All fold vectors pass on Python 3.10; WhatsApp id and number give one identity |
| 24 | 02-U9 | Sightings, each phone's own names, owner tiers | 23 | One identity on two phones shows both saved names; owner tier recorded per phone, never refusing ingest |
| 25 | 02-U10 | Suggestions and decisions through `decisions.record` | 24 | No suggestion from names alone; link and unlink both recorded with actor |
| 26 | 02-U12 | Neo4j projection with membership | 24 | Deleting C9 from a C3+C9 case leaves every C3 identity and edge |
| 27 | 02-U13 | Thread documents and search hits | 24 | Search hit carries `record_uid`; thread files hidden from evidence listings |
| 28 | 02-U15 | Corrections on phone data | 24 | Corrected timestamp moves the event; both values shown; search uses the corrected value |

### Stage E: screens (with stage F interleaved)

Recommended interleave: E1 to E4, then F's projection and availability (04-U2 to U4), then E5 to E7,
then F's views (04-U6, U7), then E8 to E11, then the rest of F.

| # | Unit | Delivers | Depends on | Done when |
|---|---|---|---|---|
| 29 | 03-1 | Shared backend: filters (incl. `group_scope`), time display, labels, streams, records, `/api/phones` router | 20, 24 | 03 backend tests for 3.1 rules and A2, A6 pass |
| 30 | 03-2 | Shared frontend: time cell, participant label, stream list, record panel, badges, copy | 29 | A4, A5, A6, A7, A13 pass |
| 31 | 03-3 | Conversations screen; sidebar change; old Cellebrite feature removed (section 7) | 30 | C-1 to C-9, A1, A14, A16 pass |
| 32 | 03-4 | Extraction profile (examiner zone shown as such; coverage; verification outcomes) | 22, 8 | P-1 to P-5 pass |
| 33 | 04-U2 | `pol_activity_event` projection and strength view | 21 | Outgoing owner message strong interaction; Web platform demoted |
| 34 | 04-U3 | Attribution flags | 33 | Synced location flagged |
| 35 | 04-U4 | Availability bands and hourly rollup | 33 | No data versus data without interaction distinguished on synthetic nights |
| 36 | 03-5 | Search with fold, Cmd/Ctrl+K dialog, `rec://` citations, chat page-1 fix, agent links | 27 | S-1 to S-7, A8 pass |
| 37 | 03-6 | Timeline phone lens, lanes mode, timeline fixes (200,000 cap, undated events, 12-hour time, zone) | 29, 35 | T-1 to T-6, A3 for the lens |
| 38 | 03-7 | Export jobs: PDF with bundled fonts, no caps | 31 | E-1 to E-5, E-7, A9 to A12 |
| 39 | 04-U6 | Day view API and screen | 35, 30 | 6,000-item synthetic day complete with stated summaries |
| 40 | 04-U7 | Pattern grid, quiet hours, breaks | 35 | Synthetic 30 days yield the stated quiet hours and breaks |
| 41 | 03-8 | People: phone identities tab, dossier panel, suggestions | 25 | U-1 to U-4 |
| 42 | 03-9 | Media screen | 8 | M-1 to M-4 |
| 43 | 03-10 | Map phone layer | 18, 37 | G-1 to G-4 |
| 44 | 04-U5 | Place observations, offline cell reference import, WiFi anchors | 43; Neil's ruling on the OpenCelliD licence | Radius rules and exclusions per 04 |
| 45 | 03-11 | Graph communication edges; graph cap statement | 26, 02-U16 | R-1 to R-3; A3 complete across all surfaces |

### Stage F: pattern of life (remaining)

| # | Unit | Delivers | Depends on | Done when |
|---|---|---|---|---|
| 46 | 04-U8 | Stays, clusters, routine, deviations | 44 | Synthetic six-week routine yields two routine places and the flagged night |
| 47 | 04-U9 | Together and apart, no cap, no SSID matching | 44 | 25,000 pairs all returned; separated and compatible cases as specified |
| 48 | 04-U10 | Money lane and manual places | 33; financial admitted rows | Superseded rows absent; no time of day given to a transaction |
| 49 | 04-U11 | Claims and evaluation | 35, 46, 47 | Every claim kind's outcome rules pass; evaluation reproducible |
| 50 | 04-U13 | Workspace attachment of records and statement checks | 49 | New link targets accepted; stale evaluation shown on the link |
| 51 | 04-U12 | AI claim drafting (local model only) | 49; a local model provider | With no local provider: 409 and no network call |
| 52 | Gate F | End-to-end statement check on a synthetic two-phone case, plus a corpus run on the largest phone | 49, 50 | Recorded in the build state |

### Stage G: cross-evidence

| # | Unit | Delivers | Depends on | Done when |
|---|---|---|---|---|
| 53 | 02-U11 | Financial identifier kinds `phone_number` and `email` | 23 | Existing account-identity tests unchanged and new kinds match by normalised value |
| 54 | 02-U16 | Combined communication and money edges | 26, 53 | Edge counts equal Conversations `between` totals under the same `group_scope`; money sums p0 to p2 only |
| 55 | 02-U14 | Embedding gate, chat and workspace anchors | 27 | No phone text sent to an external embedding service without a per-case decision |
| 56 | 05-S0 | Analysis framework: tables, jobs, endpoints, coverage, directions, decisions, sensitive reveals | 24 | Framework tests in 05 section 3 |
| 57 | 05-S1 | Measurement module M-1 to M-13 as read-only functions | 56 | Produces every gate value of section 5 |
| 58 | 05-S2 | Raw record view requirements met | 31, 32 | 05 section 17.1 checks pass on screens built in E |
| 59 | 05-S3 | Approach 1a: money signals, institution directory, readings, binding, corroboration, account leads | 56, 53 | 05 section 4.7 gate and tests |
| 60 | 05-S4 | Approach 1b: coverage join and contradictions | 59 | 05 section 4.7 gate plus a bound account with a continuous reconciled run |
| 61 | 03-12 | RSMF export | 38; RSMF specification read and cited (03 20.8) | E-6 |

### Stage H: investigative approaches

Each unit starts only after its gate in 05 passes on the server measurements.

| # | Unit | Approach | Gate (05 section) |
|---|---|---|---|
| 62 | 05-S5 | 2 cross-phone message reconciliation | 5.6 |
| 63 | 05-S6 | 3 deletion and concealment timeline | 6.6 |
| 64 | 05-S7 | 4 knowledge and awareness | 7.6 |
| 65 | 05-S8 | 5 who used which phone | 8.6 |
| 66 | 05-S9 | 11 relationships over time | 14.6 |
| 67 | 05-S10 | Link edges in the graph (section 17.8) | a case with a reviewed phone-to-counterparty link |
| 68 | 05-S11 | 6, 7, 9, 10, each as its own unit | 9.6, 10.6, 12.6, 13.6 |
| 69 | 05-S15 | 12 extraction comparison | 15.6 (needs the C1 identity answer from A3) |
| 70 | 05-S16 | 13 incident window | 16.6 |

### Stage I: media

| # | Unit | Delivers | Depends on | Done when |
|---|---|---|---|---|
| 71 | 05-S12 | Local OCR and transcription; video frames honour the provider setting; phone file types without extensions dispatched | 42 | 05 section 17.4 |
| 72 | 05-S13 | Approach 8 media spread, exact tier then perceptual tier if measured necessary | 71, 8 | 11.6 |
| 73 | 05-S14 | Translation and image search by description | 71 | 17.5, 17.6 |

### Stage J: conditional

| # | Unit | Delivers | Runs when |
|---|---|---|---|
| 74 | 05-S17 | Source database view and independent re-parse (ALEAPP, iLEAPP, MIT licence, engine Python) | A production includes the phone's database files on disk |

## 5. Server measurement batch (stage A3)

Run read-only on the server at lowest priority (`nice -n 19`, `ionice -c3`), counts and salted hashes
only, results written to `docs/cellebrite/measurements/` on the development machine. No content leaves
the server in any form a person could read.

| Measurement | For | Settles |
|---|---|---|
| 01: largest phone element count, file count and capture timing estimate | 01 section 14 | the 30-minute target and memory budget |
| 02: seed counts recomputed directly from the 14 reports | 02-U2 | the seed matches the server, not only the catalogue |
| 02 / 01: examiner zone versus device setting wherever both exist | 01 section 9.3 reverse-if | device zone rule |
| 03 20.1: whether duplicate copies share the same second | 03-1 | duplicate rule D-9 |
| 03 20.3: real row sizes | 03-1 | the 5,000-row full-load figure D-2 |
| 04 M1 to M12: DeviceEvent `Value` sets per type, UserMapping values, location affiliation and precision distributions, availability, and the rest of 04 section 13 | 04-U1 | activity-strength and attribution rows |
| 05 M-1 to M-16, X1 to X11 not runnable locally: cross-phone message pairs in the 10-report case and 3-phone case, notifications and short-code SMS with amounts, deletion distributions, co-travel statistics | 05 gates | which approaches proceed |
| Two C1 reports in the 10-report case: device identity from header identifiers | 05-S15 | whether approach 12 has a real pair |

## 6. Cross-cutting fixes to existing Loupe that units depend on

Each is built inside the unit named, not as a separate project.

| Fix | Found in | Built in unit |
|---|---|---|
| Resumable upload caps folders and zips at 20,000 files; old route deletes zips after extraction | 01 section 4 | 01-1.7 |
| Engine audio transcription calls OpenAI only; video frames always go to OpenAI | 05 section 17.4 | 05-S12 |
| No global search; Cmd/Ctrl+K fires an event nothing listens for | 03 section 15 | 03-5 |
| Chat tells the model to cite page 1 when no page is known (`llm_service.py:503`) | 03 section 15 | 03-5 |
| Agent answers render without a document opener | 03 section 15 | 03-5 |
| Timeline stops at 200,000 events, drops undated events, shows 24-hour time in the browser's zone | 03 section 15 | 03-6 |
| Timeline PDF uses system fonts and caps linked entities and notes; backend image has no fonts | 03 section 15 | 03-7 |
| Map and Graph load the whole case uncapped | 03 section 15 | 03-10, 03-11 |
| Reports page calls `/api/reports`, which no route serves | 03 section 15 | not in this plan (03 D-23); recorded for Neil |
| Query panel posts to a missing route; fallback `/api/query` not case-scoped and runs in a write transaction | Loupe screen survey (plan 10.6) | not in this plan; recorded for Neil as a security defect |

## 7. Removal of the old Cellebrite code

Per 01 section 11 and 03 D-25: the new code is built beside the old under new names (`/api/phones`,
`features/phones`, `app/phone/`), and the old is removed in the unit that replaces its last caller:

| Old | Removed in |
|---|---|
| Engine `app/pipeline/cellebrite/*`, `cellebrite_ingestion.py`, engine cellebrite route, arq function | 01-1.7 once the new upload path dispatches to the phone worker |
| Backend `routers/cellebrite.py`, `services/neo4j/cellebrite_service.py`, `cellebrite_intersection_service.py` | 03-3 (Conversations replaces the last screen that calls them) |
| `frontend_v2/src/features/cellebrite/` and its route and sidebar entry | 03-3 |
| Old Cellebrite columns and migrations | kept (01 D21); no destructive migration |

## 8. Gates between stages

| From | To | Gate |
|---|---|---|
| A | B | Counter stable on C3, C9, C8; server batch recorded |
| B | C | Reconciliation exact on every reference document; kill and resume proven (01-2.4) |
| C | D | Unknown-type test passes (02-U4); mappings re-derive without re-capture (02-U5) |
| D | E, F | Membership deletion test (02-U12) |
| E | G | Every testing-hub item in 03 section 17.0 has a passing test |
| F | H | Gate F (row 52) |
| G | H | Approach 1 gate (05 section 4.7) recorded either way |

## 9. Risks and what to do if they occur

| Risk | Sign | Response |
|---|---|---|
| Capture too slow on the largest phone (338,715 top-level models, estimated 11 to 14 million elements) | 01 timing over target | Profile per 01 section 10; COPY batch size; never relax reconciliation |
| Interpretation sweep slows the API | 02 section 1.3 reverse-if (over 15 minutes or API p95 up by half) | Move the sweep to the phone worker as 02 records |
| A production in a new PA version breaks a self-description assumption | Registry drift flags on intake | Mapping suspended for affected fields (02 section 6); capture and reconciliation unaffected |
| Server host memory pressure (32 GB shared; v1 notes record OOM incidents) | Worker memory near 01's 1 GB container limit | Phone worker runs one job at a time (01 D14); schedule large ingests when other jobs are idle |
| No local model available for drafting or media | 04-U12, 05-S12 blocked | Features stay unavailable with stated wording; nothing falls back to an external provider without a recorded decision |
| OpenCelliD licence not acceptable | Neil's ruling | Cell towers stay identifier-only, shown as "not placed" |
