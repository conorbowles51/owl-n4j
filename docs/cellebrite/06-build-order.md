# 06. Build order

Purpose: one sequence for every build unit defined in specs 01 to 05 and 07, with what each depends on, the
test that defines done, and the gates that must pass before the next stage starts. A session picks the
next unit from this file, builds it, tests it, commits it, and rewrites `docs/loupe-build-state.md`, as
`CLAUDE.md` requires. Unit ids are the owning spec's ids (`01-1.3` is spec 01 unit 1.3; `02-U4` is
spec 02 unit U4; `03-5` is spec 03 unit 5; `04-U7`; `05-S3` is spec 05 step 3). Spec 07 names its work by
section: `07-12.1C` is the cb-ux shared kit (07 section 12.1 item C), `07-6.4` is the lx-collect registry and
routes (07 section 6.4), `07-7.1` is the agent phone tools (07 section 7.1).

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
   - backend: both commands in `CLAUDE.md` under Tests (the financial `unittest discover` and the pytest
     command); the baselines are measured at the start of each job and written to its STATUS, and they
     must stay green; no fixed test count is used;
   - evidence-engine: Python 3.12 or later, run inside the engine container (the build-state file
     records that the engine suite cannot run on Python 3.10);
   - frontend_v2: `npx vitest run --project unit` and `--project browser` with `VITE_CACHE_DIR` set per
     `CLAUDE.md`, plus `npx tsc -b` and `npx eslint .`.
4. **Reference corpus:** the 14 phone reports on the server under `/mnt/owl-data/ingestion-data/`,
   read-only (C3 = P06 and C9 = P09 match the Mac copies record for record; the server C8, P02, is a
   different export from the Mac's split-section C8). Nothing is copied from the Mac (plan decision 2);
   numbers measured only on the Mac copies (the C3 zip, the split C8, their file outcomes) are reference
   values, reported beside the server numbers and never adjusted. The corpus manifest, synthetic fixtures
   built from the server folders and every measurement scratch output live in
   `/mnt/owl-data/cellebrite-corpus/` (mode 700), never in the repo. v1 wrote `owl_ingest_report.json`
   into each server folder; it is not part of the production and file counts exclude it. Case material is never committed;
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
| Shared phone interface kit | `frontend_v2/src/features/phones/ui`, plus `components/ui` where Loupe-wide (07 section 5) | 07 |
| Link-type registry, dossier and workspace link routes | backend and frontend, per 07 section 6.4 | 07 |

If two specs name different roots for the same thing, the owning spec in this table governs.

## 3. Stages at a glance

| Stage | Plan phase | Units | Ends with |
|---|---|---|---|
| A Ground truth | 0 | 01-0.1, 01-0.2, A3 server measurement batch | Counts recorded for C3, C9, C8 and all 14 server phones |
| B Capture | 1, 2 | 01-1.1 to 01-1.7, 01-2.1 to 01-2.4 | Exact reconciliation on every reference document; kill-and-resume proven |
| C Interpretation | 3 | 02-U1 to 02-U7, 02-U17, 04-U1 | A type absent from all code reaches timeline, map and identities |
| D Identity and projections | 4 | 02-U8, U9, U10, U12, U13, U15 | Deleting one of two phones sharing a contact leaves the other intact |
| E Screens | 5 | 07-12.1C, 07-6.4, 03-1 to 03-11 | Every testing-hub item (03 section 17.0) has a passing test |
| F Pattern of life | 7 | 04-U2 to 04-U14 | A statement window shows supporting, contradicting and missing data with sources |
| G Cross-evidence | 6 | 02-U11, 02-U14, 02-U16, 05-S0 to 05-S4, 03-12, 07-7.1 | Phone money readings corroborate ledger rows as p4; RSMF export; agent phone tools with full phone visibility, scoped to the case |
| H Investigative approaches | 8 | 05-S5 to 05-S11, 05-S15, 05-S16, 05-S16a to 05-S16c | Each approach built only after its gate passes |
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
| 1 | 01-0.1 | Reference corpus manifest: paths, sizes, container hashes, report version, producer for the 14 server reports | nothing | Manifest in `/mnt/owl-data/cellebrite-corpus/manifest.json` (never committed); a structure-only summary (counts, versions) in `docs/cellebrite/measurements/`; rerun is identical |
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
| 19a | 02-U17 | Sweep and runtime (02 sections 1.3 and 5.7) | 19 | Killing the backend mid-pass leaves the previous generation readable and the next start completes it; timing at C6 scale recorded and 02 section 1.3's reverse-if judged on it; the size of 02 section 5.7's one-transaction generation swap measured at C6 and P14 scale |
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
| 30a | 07-12.1C | cb-ux shared phone interface kit (07 section 5): semantic tokens and phone palette, keymap registry with `?`, copy helper, phone selection store, docked record panel slot, read-flagged progress requests; built on synthetic fixtures, needs no phone data | nothing | 07 section 12.1 finish list; Storybook stories in light and dark with accessibility checks; Financial tests stay green |
| 30b | 07-6.4 | lx-collect: one link-type registry replacing the hard-coded lists, dossier and workspace link routes, interview evidence with registry targets, reverse lookup, Add to Timeline for phone records, `phone_analysis` snapshots (07 section 6.4 items 1 to 13); phone types refused with a stated message until their resolvers register | nothing | CO-2 (API), CO-3, CO-5, CO-16 (API), CO-17 (API), CO-21 and the registry tests pass |
| 31 | 03-3 | Conversations screen; sidebar change; old Cellebrite feature removed (section 7); Add to Workspace and Add to… through the registry | 30, 30a, 30b | C-1 to C-13, A1, A14, A16 pass |
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
| 50 | 04-U13 | Workspace attachment of records and statement checks through the registry; statement check linked to the dossier interview | 49, 30b | Registry accepts the link targets; stale evaluation shown on the link |
| 51 | 04-U12 | AI claim drafting (full phone visibility, scoped to the case) | 49 | A request naming another case's extraction: 404 and no network call |
| 51a | 04-U14 | Patterns screen at `/cases/:id/phone-patterns`, shared Lanes component, key dates and case terms (04 section 8.6) | 39, 40, 49, 30a | POL-1 and J-5a pass |
| 52 | Gate F | End-to-end statement check on a synthetic two-phone case, plus a corpus run on the largest phone | 49, 50 | Recorded in the build state |

### Stage G: cross-evidence

| # | Unit | Delivers | Depends on | Done when |
|---|---|---|---|---|
| 53 | 02-U11 | Financial identifier kinds `phone_number` and `email` | 23 | Existing account-identity tests unchanged and new kinds match by normalised value |
| 54 | 02-U16 | Combined communication and money edges | 26, 53 | Edge counts equal Conversations `between` totals under the same `group_scope`; money sums p0 to p2 only |
| 55 | 02-U14 | Embedding gate, chat and workspace anchors | 27 | No phone text sent to an external embedding service without a per-case decision |
| 56 | 05-S0 | Analysis framework: tables, jobs, endpoints, coverage, directions, decisions, sensitive reveals, shared results layout (05 section 3.9) | 24, 30a | Framework tests in 05 section 3; AP-1 |
| 57 | 05-S1 | Measurement module M-1 to M-16 as read-only functions | 56 | Produces every gate value of section 5 |
| 58 | 05-S2 | Raw record view requirements met | 31, 32 | 05 section 17.1 checks pass on screens built in E |
| 59 | 05-S3 | Approach 1a: money signals, institution directory, readings, binding, corroboration, account leads | 56, 53; first run waits for CB-INDEX question 3 (none of the three phone cases exists in Loupe) | 05 section 4.7 gate and tests |
| 60 | 05-S4 | Approach 1b: coverage join and contradictions | 59 | 05 section 4.7 gate plus a bound account with a continuous reconciled run |
| 61 | 03-12 | RSMF export | 38; RSMF specification read and cited (03 20.8) | E-6 |
| 61a | 07-7.1 | Agent phone tools (schema `loupe.agent.phone_*/1`) to the ledger-tool standard, reading phone records in full within the case (no opaque labels) | 27, 55 | SA-7 and XF-3 pass; the agent evaluation set of 07 section 7.1 measured; asked in case A about a phone only in case B, the agent answers "not in this case" |

### Stage H: investigative approaches

Each unit starts only after its gate in 05 passes on the server measurements.

| # | Unit | Approach | Gate (05 section) |
|---|---|---|---|
| 62 | 05-S5 | 2 cross-phone message reconciliation | 5.6 |
| 63 | 05-S6 | 3 deletion and concealment timeline | 6.6 |
| 64 | 05-S7 | 4 knowledge and awareness | 7.6 |
| 65 | 05-S8 | 5 who used which phone | 8.6 |
| 66 | 05-S9 | 11 relationships over time | 14.6 |
| 67 | 05-S10 | Approach screen wired to 02-U16's `backend/services/phone/link_edges.py` (05 section 17.8; money per 02 section 11, no second implementation) | 54; a case with a reviewed phone-to-counterparty link |
| 68 | 05-S11 | 6, 7, 9, 10, each as its own unit | 9.6, 10.6, 12.6, 13.6 |
| 69 | 05-S15 | 12 extraction comparison | 15.6 (needs the C1 identity answer from A3) |
| 70 | 05-S16 | 13 incident window, with its entry points (J-5c) | 16.6 |
| 70a | 05-S16a | 14 common contacts | 16a.6 |
| 70b | 05-S16b | 15 directional from/to frequency matrix | 16b.6 |
| 70c | 05-S16c | 16 number switching | 16c.6 |

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
only, scratch output in `/mnt/owl-data/cellebrite-corpus/`, and the structure-only results committed to
`docs/cellebrite/measurements/`. No content leaves
the server in any form a person could read.

Results are in `docs/cellebrite/measurements/a3/README.md` and in each owning section.

| Measurement | For | Settles | Result |
|---|---|---|---|
| 01: largest phone element count, file count and capture timing estimate | 01 section 14 | the 30-minute target and memory budget | P14: 17,283,869 elements, 158,114 tagged files; counter parse 374 s at `nice 19`, flat 44 MiB (01 1.8, 1.9); folder 43,824,116,660 bytes in 237,826 files; hashing 37.3 MB/s measured at idle IO priority, so parse plus hashing about 13 to 26 min (**estimate, not measured**; 01 unit 0.1, 10.8). The 30-minute target stands until unit 2.4 measures it |
| 02: seed counts recomputed directly from the 14 reports | 02-U2 | the seed matches the server, not only the catalogue | **pass**: equal per type on all 14 once `RelatedModels` copies are counted; seed nesting **changed** to the union with the 95 server relations (02 3.5, decision 39) |
| 02 / 01: examiner zone versus device setting wherever both exist | 01 section 9.3 reverse-if | device zone rule | **pass**: agree on 8 of 9, differ on P12; the rule stands |
| 03 20.1: whether duplicate copies share the same second | 03-1 | duplicate rule D-9 | **pass**: exact equality finds most copies (03 20.1) |
| 03 20.3: real row sizes | 03-1 | the 5,000-row full-load figure D-2 | measured by `cb-interpret` on its first captures |
| 04 M1 to M12: DeviceEvent `Value` sets per type, UserMapping values, location affiliation and precision distributions, availability, and the rest of 04 section 13 | 04-U1 | activity-strength and attribution rows | recorded (04 13.1); M10 Bluetooth skipped (needs 02 identities); 8.2 threshold stands |
| 05 M-1 to M-16, X1 to X11 not runnable locally: cross-phone message pairs in the 10-report case and 3-phone case, notifications and short-code SMS with amounts, deletion distributions, co-travel statistics | 05 gates | which approaches proceed | approach 3 **pass**; 4 group roles **pass**, read-and-latency **fail**; 5 complementary use **pass**, co-location **fail**; 6 cross-phone list **fail**; 8 exact tier **pass**; 10 **fail**; 12 **fail**; S17 source database **pass** (stage J condition met); 2 **changed** (494 candidate pairs; tiering by `cb-crossev`); 1, 7, 9, 11, 13 to 16 need identities, ledger or vocabulary (`cb-crossev`, `cb-approaches`, `cb-pol`) |
| Two C1 reports in the 10-report case: device identity from header identifiers | 05-S15 | whether approach 12 has a real pair | **fail**: identifiers present in one report only; content Jaccard 0.0002; 0 equal record ids |

## 6. Cross-cutting fixes to existing Loupe that units depend on

Each is built inside the unit named, not as a separate project.

| Fix | Found in | Built in unit |
|---|---|---|
| Resumable upload caps folders and zips at 20,000 files; old route deletes zips after extraction | 01 section 4 | 01-1.7 |
| Engine audio transcription calls OpenAI only | 05 section 17.4 | 05-S12 |
| Engine video frames go to OpenAI whatever `image_provider` says | 05 section 17.4 | job `lx-defects`, because it affects all evidence today, not only phones |
| No global search; Cmd/Ctrl+K fires an event nothing listens for | 03 section 15 | 03-5 |
| Chat tells the model to cite page 1 when no page is known (the `CITE SOURCES` line in `backend/services/llm_service.py`: "If no page number is available, use page 1.") | 03 section 15 | 03-5 |
| Agent answers render without a document opener | 03 section 15 | 03-5 |
| Timeline stops at 200,000 events, drops undated events, shows 24-hour time in the browser's zone | 03 section 15 | 03-6 |
| Timeline PDF uses system fonts and caps linked entities and notes; backend image has no fonts | 03 section 15 | 03-7 |
| Map and Graph load the whole case uncapped | 03 section 15 | 03-10, 03-11 |
| Reports page calls `/api/reports`, which no route serves | 03 section 15 | where Neil's answer to CB-INDEX question 4 puts it (recommended: `cb-screens` with 03-7, as the case's list of exports); until then the sidebar entry stays as is (03 D-23) |
| Query panel posts to a missing route; fallback `/api/query` not case-scoped and runs in a write transaction | Loupe screen survey (plan 10.6) | job `lx-defects` (security defect, outside this plan's units) |
| "Not a duplicate" calls `/api/graph/reject-merge-pair`, which nothing serves; the served route is `/reject-merge` | Loupe screen survey | job `lx-defects` |

## 7. Removal of the old Cellebrite code

Per 01 section 11 and 03 D-25: the new code is built beside the old under new names (`/api/phones`,
`features/phones`, `app/phone/`), and the old is removed in the unit that replaces its last caller:

| Old | Removed in |
|---|---|
| Engine `app/pipeline/cellebrite/*`, `cellebrite_ingestion.py`, engine cellebrite route, arq function | 01-1.7 once the new upload path dispatches to the phone worker |
| Backend `routers/cellebrite.py`, `services/neo4j/cellebrite_service.py`, `cellebrite_intersection_service.py`; `services/phone_normalise.py` and `tests/test_phone_normalise.py` (its only caller is `cellebrite_service.py`; 02's `services/phone/identifiers.py` and `numbers.py` replace it; `tests/test_phone_normalise_retirement.py` keeps it to that one caller and goes with it) | 03-3 (Conversations replaces the last screen that calls them) |
| `frontend_v2/src/features/cellebrite/` and its route and sidebar entry | 03-3 |
| Old Cellebrite columns and migrations | kept (01 D21); no destructive migration |

## 8. Gates between stages

The last column lists the tests that 07 section 11 adds to each gate; 07 section 11 is authoritative for them.

| From | To | Gate | 07 section 11 tests added |
|---|---|---|---|
| A | B | Counter stable on C3, C9, C8; server batch recorded | The 07 section 15 spec changes applied, 07 merged, research note 09 written |
| B | C | Reconciliation exact on every reference document; kill and resume proven (01-2.4) | I-1, I-2, J-1a |
| C | D | Unknown-type test passes (02-U4); mappings re-derive without re-capture (02-U5); sweep kill test passes and the C6 and P14 timing and swap-size measurements are recorded (02-U17) | RQ-1 to RQ-8, U-backend, J-8a, one feed test per review action |
| D | E, F | Membership deletion test (02-U12) | (with C to D) |
| E | G | Every testing-hub item in 03 section 17.0 has a passing test | Row 30a: the 07 section 12.1 finish list. Row 30b: CO-2 (API), CO-3, CO-5, CO-16 (API), CO-17 (API), CO-21, registry tests. Stage E: J-1b, J-2, J-3a, J-4, J-6, J-7, J-8b, J-10a, J-11, J-12, J-13, J-13b, J-14a, J-15, J-16, J-17, UX-1 to UX-5, C-10 to C-13, MD-1, P-6 to P-8, U-5 to U-8, S-8 to S-10, G-5, G-6, T-7, E-8 to E-10, XF-5, XF-6, XF-9, XF-11, SA-1, SA-2, SA-3 (existing parts), SA-6, SA-8 (first part), CO cells for its surfaces, CO-2, CO-4, CO-6 to CO-8, CO-9a, CO-12, CO-14 to CO-17, CO-19, CO-20 |
| F | H | Gate F (row 52) | J-5a, J-9, J-10b, POL-1, CO cells for Patterns and Lanes; J-10c in the gate of whichever of stages E and F finishes second |
| G | H | Approach 1 gate (05 section 4.7) recorded either way | J-3b, J-5b, XF-1 to XF-4, XF-7, XF-8, XF-10, XF-12, SA-3 (rest), SA-4, SA-7, SA-8 (second part), CO-10, CO-11, CO-13, CO-18 (agent), CO cells for Graph, the agent evaluation set measured |
| H | done | Each approach's gate in 05 | J-5c, J-14b, the J-16 equality with approach 12, AP-1, CO-9b, CO cells for analyses |
| I | done | 05 sections 17.4 to 17.6 | M-5, M-6, M-7, CO-18 (transcript) |

Gate A to B, recorded 2026-11-01: **pass**. Counter stable: lxml and expat agree on all 14 reports with 0 differences, and a second lxml run is identical on C3, C9 and C8 (01 1.8). Server batch recorded: every row of section 5 has a result or a named owner. Reference manifest: a rerun is byte-identical on all 14 reports (01 unit 0.1). 07 merged with change rows U1 to U27 applied, and research note 09 written.

## 9. Risks and what to do if they occur

| Risk | Sign | Response |
|---|---|---|
| Capture too slow on the largest phone (338,715 top-level models, estimated 11 to 14 million elements) | 01 timing over target | Profile per 01 section 10; COPY batch size; never relax reconciliation |
| Interpretation sweep slows the API | 02 section 1.3 reverse-if (over 15 minutes or API p95 up by half) | Move the sweep to the phone worker as 02 records |
| A production in a new PA version breaks a self-description assumption | Registry drift flags on intake | Mapping suspended for affected fields (02 section 6); capture and reconciliation unaffected |
| Server host memory pressure (32 GB shared; v1 notes record OOM incidents) | Worker memory near 01's 1 GB container limit | Phone worker runs one job at a time (01 D14); schedule large ingests when other jobs are idle |
| No local model available for drafting or media | 04-U12, 05-S12 blocked | Features stay unavailable with stated wording; nothing falls back to an external provider without a recorded decision |
| OpenCelliD licence not acceptable | Neil's ruling | Cell towers stay identifier-only, shown as "not placed" |
