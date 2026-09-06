# The financial subsystem: full handoff

> **Takeover update, 6 September 2026:** Neil authorized continuing the work.
> Admission control is committed as `8ac2455`; the case-wide classification
> display is committed as `b8aeb5b`. **Item 8's planned wiring is complete.**
> The old approval requirement in sections 5, 8 and 12 is resolved; the missing
> TypeScript-consumer and missing-screen claims below describe the earlier head.
> Next is item 9, duplicates. Read the dated opening of
> [the build state](loupe-build-state.md) for current status, preserved limitations
> and Mac test instructions. The Linux sandbox limits below are historical.

Written at head `8a29fd2` on branch `integration/evidence-main-reunion`, for
agents who did not build it.

Everything here was checked against the source in the session that wrote it.
Where a claim could not be checked, it says so. Where an earlier document in this
repo is wrong, this file says which one and how, because two of them are wrong in
ways that will waste your time.

Read this, then `CLAUDE.md`, then `docs/loupe-build-state.md` for the running
detail. `docs/loupe-wiring-plan.md` is the agreed build order and is still
authoritative for sequence, but several of its factual premises have since been
proved wrong; the corrections are in this file under each unit.

---

## 1. What the thing is

Loupe is a forensic intelligence platform for Owl Consultancy Group, a private
investigations firm. It takes evidence of mixed kind and condition, mostly bank
statements arriving as productions from a prosecution, and turns it into
something an investigator can rely on in a matter and defend if challenged.

The financial subsystem is the centre of gravity. It is `backend/services/financial/`,
**55 Python modules**, with **61 matching test files** in `backend/tests/` running
**3,466 tests**. The package's `__init__.py` exports **741 symbols**. The frontend
side is `frontend_v2/src/features/financial/`, **73 files**.

The governing idea, and the thing that makes this codebase unusual, is that
**a number is never separated from the grounds for believing it.** A transaction
carries where it was read from, what proof class its source document earned, what
was decided about it and by whom, whether the statement period it belongs to
balances, and whether the amount was read with certainty or merely proposed. A
total that quietly covers a subset is treated as a defect, not a rounding
concern.

### The two stores, and the fact that they can disagree

This is the single most important structural fact in the subsystem and the one
most likely to mislead you.

There are **two** financial data stores.

**Postgres** holds the ledger: `financial_transactions` and its neighbours,
append-only, with the run that produced each row, the source document, the
adjudications recorded against it, the proof class, the statement period and its
reconciliation verdict. This is the evidentiary record.

**Neo4j** holds the graph: entities, counterparties, money flow, categories. This
is what the original financial screens were built on and what most of the
`/api/financial` routes still read.

**The graph is not a projection of the ledger.** `services/financial/projection.py`
exists, is tested, and has **zero production callers** — verified by grep this
session. So the two stores are populated by different paths and nothing detects
divergence between them. Quarantining a row changes the ledger and does not touch
the graph. Reconciling a period changes the ledger and does not touch the graph.

Do not describe the graph as derived from the ledger. Closing this is Phase 3
item 12 and it is not started.

---

## 2. Operational facts that will otherwise cost you a session

These are not preferences. Each one was learned by losing time to it.

**The repo path changes every session.** Resolve it once; never hardcode a path
from a previous session.

**The bash working directory resets unpredictably between calls.** Every command
must `cd` with an absolute path in the same invocation.

**Do not read an exit code through a pipe.** `npx tsc -b | tail` returns the
pipe's status. Redirect to a file and echo `$?`.

**Python is 3.10.12.** No newer syntax. Ignore the repo `venv/`; it is stale
(3.14, no packages) and activating it wastes a session.

**Disk is the standing hazard.** Three filesystems, all tight: `/` is 99% full,
`/sessions` has been at **zero bytes free** for many sessions, `/dev/shm` is 2.0G
and does not start empty. None of this is Loupe's doing and no session can clear
it — the space is held by other sessions' directories that are not readable or
removable from inside a session. Neil has to reclaim it on his side.

The workaround, established and verified this session, is **borrow rather than
install**:

- **Python packages.** Do not run the pip bootstrap in `CLAUDE.md`; it needs
  151M and there is rarely that much. Other sessions leave `/dev/shm/pylibs-*`
  trees behind and they are world-readable. Point `PYTHONPATH` at one. Verified
  green this session against `pylibs-sharp-peaceful-ramanujan`:

  ```
  cd backend && env PYTHONPATH=/dev/shm/pylibs-<some-other-session> \
    PYTHONPYCACHEPREFIX=/dev/shm/pyc-$(id -un) \
    PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 \
    python3 -m unittest discover -s tests -p 'test_financial_*.py' -t .
  ```

  **Check the candidate before trusting it** — the trees are not identical.
  Compare entry counts and import the full package list first. And **never
  delete your own tree before proving a borrowed one works**, or you will be left
  with no suite and no room to rebuild.

- **Chromium for the browser gate.** Same pattern: point
  `PLAYWRIGHT_BROWSERS_PATH` at an install another session left in `/dev/shm`.
  Verify it exists and is executable first.

- **Caches.** `VITE_CACHE_DIR` and `npm_config_cache` must both go to `/dev/shm`
  carrying the current user in the path, e.g. `/dev/shm/vite-cache-$(id -un)`.
  `/dev/shm` and `/tmp` are sticky and the sandbox user changes every session, so
  a fixed name left by an earlier session is owned by another uid and every write
  to it fails.

**`du` needs `-x`** or it follows into the virtiofs repo mount and reports 16G
for a directory holding 24K.

**Never read "no tests" as green.** Every frontend failure mode in this sandbox
reports it: a cache permission failure, a missing Chromium, the workspace
`unlink` denial. The gate is configured `passWithNoTests: true`, so a collection
failure looks like a clean run.

**The gates, and their real baselines, all re-measured this session:**

| Gate | Command | Baseline |
|---|---|---|
| Backend financial | `unittest discover -p 'test_financial_*.py'` | 3,466 tests, OK, skipped=12 |
| Types | `npx tsc -b` | exit 0 |
| Lint | `npx eslint .` | exit 0 |
| Frontend unit | `npx vitest run --project unit` | 79 files, 769 tests |
| Frontend browser | `npx vitest run --project browser` | 2 files, 4 tests |

There are **no expected failures**. Any failure is yours.

The **storybook** vitest project cannot run in this sandbox; its iframe
orchestrator fails against localhost. No story covers financial code. "vitest is
green" means unit and browser only. `npx vitest run` with no `--project` will try
storybook and hang for over ten minutes.

**A newly discovered flake, diagnosed this session:** the browser project can
fail on a cold vite cache with `Failed to fetch dynamically imported module`.
Re-run it; a warm cache passes. It is not file parallelism, which is what the
build-state file previously blamed.

**If a unit touches `services/evidence_*` or any router, also run**
`python3 -m pytest tests/ -k "evidence or cellebrite"` (59 passing). The
financial suite does not cover them, which one unit found out the hard way by
breaking them and passing its own gate.

**Git.** Branch is `integration/evidence-main-reunion`. **Never merge to main.
Push is blocked — Neil pushes.** Never modify git config. Commits go through a
temporary index whose path carries the current user; the full procedure is in
`CLAUDE.md` and must be followed exactly, including setting both the
`GIT_AUTHOR_*` and `GIT_COMMITTER_*` pairs on the same command.

---

## 3. How evidence actually moves through the system

Read this before planning any unit. It is the shape the plan is ordered around.

1. **A file arrives** and is stored as evidence against a case.
2. **Route check.** `services/financial/route_check.py` decides whether the file
   is a native bank format (camt.053, BAI2, MT940, NACHA) or a document for the
   OCR pipeline. Native files are **held** rather than processed, because sending
   a machine-readable statement through OCR destroys the thing that made it
   trustworthy. The endpoint is `routers/evidence.py:1318`; the interface shows
   it via `RouteBadge.tsx` and `ProcessHoldDialog.tsx`.
3. **Precheck.** `POST /api/financial/precheck` reads a held native file without
   writing anything: what accounts it is about, what period it covers, whether
   its control totals are present.
4. **Ingest.** `POST /api/financial/ingest` walks the reading into Postgres:
   `native_ingest_file.ingest_case_file` → `native_ingest.ingest_native_reading`
   → `transactions.record_transactions`. This is the only production path to a
   stored ledger row.
5. **A run** wraps that. Every ingest opens an `IngestionRun`, so a half-finished
   or dead ingest is visible rather than silent. A reaper closes runs whose
   process died (six hours stale, five minute loop).
6. **Proof class** is computed at parse time, per document, from the artifact —
   never from what the document says about itself and never set by a person.
   `assign_proof_class` is called from `camt053.py`, `bai2.py`, `mt940.py`,
   `nacha.py` and `documents.py`.
7. **Reconciliation** checks the balance identity per statement period: opening
   plus movement equals closing. It runs only when someone POSTs to
   `/api/financial/reconciliation/run`.
8. **Adjudication** records, append-only, every decision a person makes about the
   evidence: quarantining a row, releasing it, admitting a held file.
9. **Nothing after this point is wired.** Duplicates, correlation, projection to
   the graph, exhibit and export, tracing all exist as tested modules with no
   production caller.

---

## 4. The build plan, unit by unit, with verified status

Sixteen units in four phases, from `docs/loupe-wiring-plan.md`, committed as
`c88533f` on Neil's instruction: *"I need you to build everything. Have a think
about the best order and make this the plan and stick to it."*

**Do not reorder without a ruling from Neil.** If a unit turns out to depend on
something later in the list, stop and ask.

The plan was written after an audit that found the shape of the problem: the
financial package exported hundreds of symbols and only a handful were reached
from anywhere outside it. The subsystem was not unbuilt; it was **unwired**. The
plan is a wiring order, not a feature list. That framing still holds — most of
what remains is connecting capability that already exists and is already tested.

### Phase 1 — make rows exist. COMPLETE.

Before this phase, `financial_transactions` had **no production writer at all**.
`ingest_native_reading` was referenced only by its own export lines, and
`record_transactions` had exactly one caller, inside `ingest_native_reading`. So
the only path to a stored transaction ran through a function nothing called. A
held bank file had nowhere to go.

| # | Unit | Status |
|---|---|---|
| 1 | Precheck endpoint `POST /api/financial/precheck` | ✅ `a4eb3dc` |
| 2 | Ingest endpoint `POST /api/financial/ingest` | ✅ `43f8358` |
| 3 | The interface sends it (precheck dialog, "Send to ledger") | ✅ `17d94ac` |
| 4 | Mount the ledger screen | ✅ `4324b24` |

A bank file can now be sent to the ledger from seven places in the interface and
the rows it creates are visible.

### Phase 2 — make the rows trustworthy. Items 5–8 done, 9–11 not started.

| # | Unit | Status |
|---|---|---|
| 5 | Ingestion runs | ✅ backend `cde43c5`, notice `8924668`, attempts list `bc23570` |
| 6 | Quarantine | ✅ end to end, six commits ending `e64c2ca` |
| 7 | Reconciliation | ✅ `dfcef2b` — but see the flag below |
| 8 | Adjudication and proof class | ⚠️ three chunks done, **one control still owed** |
| 9 | Duplicates | ❌ not started |
| 10 | Suspect amounts and corrections | ❌ not started |
| 11 | Locators on ledger rows | ❌ not started |

**Item 7 carries a live limitation.** The balance identity runs only through the
API. Nothing in the interface calls either reconciliation endpoint, and nothing
triggers a recompute automatically — not ingestion, not adjudication. On a live
case **every period stays `not_attempted`** until somebody POSTs to
`/api/financial/reconciliation/run`. That is deliberate for the unit as built (a
recompute is an act a person takes), but do not read `not_attempted` everywhere
as a defect in the arithmetic. Whether ingestion should trigger a sweep at the
end of a run **is not decided**.

**Item 8 is the current unit and it is not finished.** Full detail in section 5.

### Phase 3 — make the ledger the source of the graph. Not started.

| # | Unit | Key functions | Production callers |
|---|---|---|---|
| 12 | Projection into Neo4j | `project_case`, `ProjectionPlan`, `PREFLIGHT_CYPHER`, `interpret_preflight`, `RECOMMENDED_CONSTRAINTS` | **zero**, verified |
| 13 | Continuity and coverage | `coverage_from_continuity` (`correlation.py:704`) | **zero**, verified |
| 14 | Linkage, correlation, flow | `correlate` (`:1312`), `correlate_all` (`:1449`), `apply_decisions` (`:1539`) | **zero**, verified |

### Phase 4 — get it out. Not started.

| # | Unit | Key functions | Production callers |
|---|---|---|---|
| 15 | Exhibit and export | `manifest_for` | **one**: `services/financial_export_service.py:519` |
| 16 | Tracing | `compare_doctrines` (`tracing.py:1278`), `Doctrine`, `TraceResult` | **zero**, verified |

Item 15 is the only later unit with any production reach at all, and it reaches
only the manifest, not the exhibit machinery in `exhibit.py`.

---

## 5. Item 8 in detail — where the work actually stands

This is the live unit. Three chunks are complete and a fourth thing is owed that
no chunk named.

### Chunk 1, the decisions surface — complete

`services/financial/decision_log.py` (`a40bb61`), `GET /api/financial/decisions`
on the **ledger** router (`2eefc4d`), `financialAPI.getCaseDecisions` and its
contract test (`0fa07d5`), `lib/decision-format.ts` (`71d859d`),
`use-case-decisions.ts` (`62ff2de`), and `DecisionsTable` + `DecisionsPanel` +
the seventh tab (`e655a0a`).

A user can read the record of what was decided about a case and on what grounds.
The page is bounded and says so: `total` and `truncated` are on screen precisely
so a reader cannot take a hundred rows for the whole record.

### Chunk 2, the admission path — backend complete, frontend owed

The rule, stated in `admission.py`: *the event is written before the file is
sent, or it is not sent.* Split in two because it is two halves.

**2a, the writing — complete, `5fa71a2`.** `services/financial/admit_file.py`
gives `record_admission` its first production caller.
`POST /api/financial/files/{file_id}/admit` on the adjudication router lets a
person reach it. A named person can overrule the router about one file, on the
record.

**2b, the enforcement — complete, `4e13821`.**
`services/financial/admission_gate.py` is called from `process_db_files`
immediately before the send. All three routes that reach it answer **409** naming
each held file and what was found in it. No held file reaches the document
pipeline without a named person having said on the record that it should.

**Still owed, and in no chunk: the control.** Neither 2a nor 2b touched
TypeScript. `POST /api/financial/files/{file_id}/admit` has **zero TypeScript
callers** in committed code. So:

> A file that arrives in a form the system cannot verify is held rather than
> processed. The way to overrule that hold exists on the backend and is enforced.
> But nothing on the screen calls the admitting route, so **a held file cannot be
> processed from the interface at all.** The refusal comes back carrying
> everything a person would need in order to admit it, and there is nothing that
> reads it and no button that acts on it. The backend is right and the door has
> no handle.

This is a frontend unit — a reader, a hook, and a control. No backend change. The
409 body is already the correct contract for it.

**It is not in the wiring plan, so it needs a ruling from Neil about where it
sits in the order.** The recommendation on record: build it now, because until it
exists a held file is stuck for good, which is a worse state than before the gate
landed. Do not resequence around it and do not fold it into another item.

**There is uncommitted work for it in the tree right now.** See section 8.

### Chunk 3, proof class and `requires_adjudication` — complete on the backend, and its frontend half is API-only

`services/financial/proof_standing.py` (`cbf163e`) gives `requires_adjudication`
its first production caller. `GET /api/financial/proof-standing` on the ledger
router answers with a census of every proof class: the document and row counts in
each, and the four things each class is licensed to do. `financialAPI.getCaseProofStanding`
and `api.proof-standing.test.ts` hold the contract.

**Correction to the build-state file, found this session.** That file says a user
can now see how much of a case rests on material nobody has ruled on. **They
cannot.** `getCaseProofStanding` has **zero consumers** — no hook, no component,
no panel renders it. Verified by grep across `frontend_v2/src`. The route exists,
the API method exists, the contract test exists, and nothing displays it. Per-row
proof class *is* on screen (`LedgerTable.tsx:298` reads it), but the case-level
census is not.

Treat this as a second frontend unit owed by item 8, alongside the admission
control.

### Two facts about item 8 worth carrying

**`assign_proof_class` was never dark code.** It has production callers in four
native parsers and three call sites in `documents.py`. Proof class has been
computed and stored at parse time all along. Chunk 3 was not "start computing
it"; it was the surface that reads it back.

**The plan named the wrong router, and only reading the source found it.** Both
the wiring plan and the build-state file called the adjudication router "the
natural home" for the proof-class work. That is right for a write and wrong for a
read: every route on the adjudication router resolves to `case:edit`
unconditionally, so putting a census there would make it demand permission to
*change* the ledger in order to *describe* it. Chunk 3 put its route on the
ledger router, where everything resolves to `case:view`.

**Plan a unit from the source files, not from the planning documents.**

---

## 6. What exists on each side, concretely

### The 29 financial HTTP routes

**`routers/financial.py` — 18 routes, all Neo4j-backed.** `GET ""`, `/entities`,
`/summary`, `/volume`, `PUT /categorize/{node_key}`, `/batch-categorize`,
`/from-to/{node_key}`, `/details/{node_key}`, `/batch-from-to`,
`GET`/`POST /categories`, `POST /auto-extract-from-to`,
`PUT /transactions/{node_key}/amount`, `POST /transactions/bulk-correct`,
`POST`/`GET /transactions/{parent_key}/sub-transactions`,
`DELETE /transactions/{child_key}/parent`, `GET /export/pdf`.

**`routers/financial_ledger.py` — 4 routes, all Postgres reads, all `case:view`.**
`GET /ledger`, `/runs`, `/decisions`, `/proof-standing`.

**`routers/financial_adjudication.py` — 3 routes, all writes, all `case:edit`.**
`POST /transactions/{id}/quarantine`, `.../release`,
`POST /files/{file_id}/admit`.

**`routers/financial_ingest.py` — 2 routes.** `POST /precheck`, `POST /ingest`.

**`routers/financial_reconciliation.py` — 2 routes.** `GET /reconciliation`,
`POST /reconciliation/run`.

The split matters and is enforced by a test: a route added to the adjudication
router inherits `case:edit` unconditionally, so whoever adds one has to justify
it. Reads belong on the ledger router.

### The seven tabs on `FinancialPage`

`ledger`, `quarantine` ("Held out"), `runs`, `decisions` — these four read
**Postgres**. `transactions`, `counterparties`, `trends` — these three read
**Neo4j**.

**Nothing on screen explains that the tab strip spans two stores.** That is
deliberate and already ruled; it is listed so it is not rediscovered as an
oversight. It stops being defensible at Phase 3 item 12.

### The frontend contract-test pattern, which you must follow

There are five committed `api.*.test.ts` files: `api.adjudication`,
`api.decisions`, `api.ledger`, `api.proof-standing`, `api.runs`. Each one
`readFileSync`s the actual backend Python file and asserts the TypeScript
interface against it, so the two languages cannot silently diverge. Every
interface is paired with a `*_FIELDS` const typed
`readonly (keyof Interface)[]`, which closes the contract in both directions.

**Any new API surface must be pinned this way.** It is the reason the frontend
and backend have not drifted despite being built in separate sessions.

---

## 7. Standing flags — real limitations, all deliberate, none secretly broken

**No live end-to-end run has ever been done.** This is the most important line in
the file. Every frontend test stubs the network. The backend suite uses SQLite in
a temp directory. No session has ever had a running backend, a real Postgres, a
Neo4j instance and a browser at the same time. **Green gates are not evidence
that the product works.** Neil has ruled that he will test a full working version
himself when the system is ready. Do not re-litigate it and do not present gate
results as proof of function.

**An admission is not consumed, and the schema cannot express consumption.** The
gate asks whether an `admit_financial_document` decision *exists* for a file in
this case, not whether an *unused* one does. So one recorded decision clears the
same file for every later send, while both the enum and `admit_case_file` say an
admission authorises **one** send. A `consumed` flag on the event would make an
append-only log mutable, which is the one property the table exists to have, so
that is the wrong fix. Closing it is a schema change and a unit of its own.
State it precisely: *no held file reaches the pipeline without a named person
having said on the record that it should; not every send is separately
authorised.*

**The engine has its own native-file refusal and no override channel.**
`evidence-engine/app/pipeline/orchestrator.py` independently fails any job whose
file it detects as native, and an admission recorded on the backend cannot reach
it. So a file admitted on the `native` outcome specifically is recorded, passes
the gate, is sent, and is then refused by the engine by name. Nothing is lost and
nothing is silent, but for that one outcome the override does not take effect.
**The engine requires Python 3.12 and this sandbox has 3.10, so it cannot be
built or tested from a session.** This needs Neil. Do not add it to the plan.

**`QuarantineBasis.from_proof` is unreachable from HTTP, by design** — computed
grounds must not be settable by a person. So on a live case every quarantined
row's reason reads `adjudicated`. The build-state file twice predicted item 8
would produce the second value; it did not and cannot, because chunk 3 turned out
to be a read and a read cannot quarantine anything. **This flag now has no owning
unit.** Producing a `from_proof` basis needs something that quarantines a row on
computed grounds at ingestion time, and nothing scheduled does that.

**`localisation.py` has no production caller except `_rescue`.** `localise_period`
and `current_identity` are reachable and tested and nothing in the product asks
them anything. Two units were expected to be its first caller and neither was.
There is no longer a unit expected to call it.

**`explain_balance_failure` has no production writer,** so a live case cannot yet
produce one and its absence from the decisions panel is not a defect in the
panel.

**A run whose process died is closed only by the reaper loop** — six hours stale,
five minute interval, threshold set by `FINANCIAL_RUN_STALE_AFTER_HOURS`. Until
it fires, a dead run and a live one are indistinguishable through the API,
deliberately: the read declines to guess.

**The ledger tab's totals exclude quarantined rows.** That is the point of
quarantine, but the held-out tab is the only place the excluded population is
visible, and nothing on the ledger tab says a total is net of anything.

**Corpus facts that will look like bugs and are not.** No row in the 30,570-row,
325-document corpus carries a running-balance column, so on real data every row
shows "No running balance". A period whose balances are absent reconciles
`unavailable`, not `unbalanced`, and on this corpus that will be the common
answer. **P0 is unreachable on the current corpus** — no document carries its own
control totals in a qualifying form. Eleven Capital One pages carry a full-page
white image XObject, most likely whole-page redaction.

**The alembic migration `20260902_evidence_table_geometry` has never been applied
to a real database** — the sandbox has no Postgres. First deployment needs
`alembic upgrade head` on Neil's side.

---

## 8. The working tree right now

Head is `8a29fd2`. **Two files are uncommitted and they are parked deliberately.**

- `frontend_v2/src/features/financial/api.ts` — modified
- `frontend_v2/src/features/financial/api.admission.test.ts` — new, untracked

This is chunk 1 of the admission control described in section 5. It adds
`FILE_ADMISSION_OUTCOMES`, `HELD_ROUTE_OUTCOMES`, the `FileAdmission`, `HeldFile`
and `UnadmittedFilesRefusal` interfaces with their `*_FIELDS` guards,
`UNADMITTED_FILES_ERROR`, `AdmitFileParams`, and the `admitFile` call. The
contract test is 20 tests and passes. **All four gates are green on it.**

It is uncommitted for one reason only: the build-state file records that this
control needs a ruling from Neil about where it sits in the build order, and that
ruling does not exist. It was written during a session that misread an
instruction.

**Do not commit it without asking Neil.** To discard it:
`git checkout -- frontend_v2/src/features/financial/api.ts` and delete the test
file.

One piece of it is worth salvaging regardless of the ruling: the test file
contains `indentedBlock` and `asDictKeys` helpers, needed because the existing
`pythonBlock` helper terminates at column 1 and `admission_gate.py` declares
`as_dict` twice.

**Untracked leftovers only Neil can delete** (the workspace denies `unlink`):
`backend/services/financial/export_manifest.py.bak`,
`backend/services/financial_export_service.py.bak`,
`frontend_v2/src/__probe.test.ts`, `backend/pytest-cache-files-7jhqubws`.

---

## 9. Defects raised and not ruled on

Small, real, none blocking. The ones with a direction attached should be fixed by
whichever unit next touches that code.

**`reconcile_period` mutates the period before it validates.** It assigns
`reconciliation_status` and then calls `_fits(...)`, which can raise
`LedgerOverflowError`, leaving a half-written verdict in the session.
`reconcile_case` defends against it with `session.expire(period)` and there is a
named test, so nothing is broken today, but it is a trap for the next caller.
**Direction: swap the order inside `reconcile_period` rather than making every
caller remember to expire.**

**The graph's correction path takes the new amount as a `float`**
(`services/neo4j/financial_service.py:599`). The ledger handles money exactly
through `Money`, so a corrected figure entered on the graph and a total computed
from the ledger can disagree at the cent. **Direction: fix as part of Phase 2
item 10.** If anything starts relying on graph corrections before then, fix it
immediately instead.

**`IngestionRunHandle.terminate()` does not check the row's stored status.** A
run the reaper closed as `failed` that then finishes will overwrite the status
with `completed` while leaving the reaper's abandonment text in `run.error`.
**If the six-hour threshold is ever lowered, fix this first.**

**`evidence:process` and `evidence:delete` are requested by routers and are not
defined in `postgres/permissions.py`.** Whether those routes are therefore open,
closed, or handled elsewhere was never established. Establish it before relying
on them.

Also outstanding, unranked: `execute_cypher_batch` takes unparameterised strings;
`get_financial_transactions` compares `n.date` as a string; `safe_float` does
`round(f, 2)` and defaults to `0`; append-only is not enforced at the database;
bulk processing above 50 files cannot work (`MAX_BATCH_SIZE = 50` against list
paging at 250); `merging_properties` is missing from `_ACTIVE_JOB_STATUSES` with
a silent fall-through in `_sync_db_record_from_job`; `RECOMMENDED_CONSTRAINTS`
and `RECOMMENDED_INDEXES` need out-of-band application;
`scripts/categorize_transactions.py:443` hardcodes `national telegraph`;
`ProcessConfirmDialog.tsx` contains dead code; the p3 early-return limitation;
`_get_dataset_metadata` uses all-or-nothing legacy detection; two defects in the
mutation harness; and one evidence-engine test
(`test_pdf_table_geometry.py::test_the_summary_agrees_with_the_payload_it_summarises`)
fails against current code because it asserts a key set without `by_table_source`,
which `geometry_summary` has emitted since `3784dbe`.

---

## 10. Where the planning documents are wrong

Both are kept in place as history. **Do not build from their sentences.**

**`docs/loupe-wiring-plan.md`:**

- Its premise for **item 6** is wrong. It says quarantined rows are written today
  and never shown. Nothing in production ever wrote one.
- Its premise for **item 7** is wrong in the same way. It treats reconciliation
  as something that runs and needs surfacing, when `reconcile_period` had no
  reachable production caller at all.
- Lines **117–123** are superseded by the work and by two rulings.
- It names `_cleanup_stale_chunks` as the loop shape to copy. That is the wrong
  precedent — it has no error handling. `poll_forever` is the right one.
- Its frontend audit says `LedgerPanel` is imported by nothing. **That is now
  stale**: `FinancialPage.tsx` imports it at line 45 and mounts it at line 534.
  Phase 1 item 4 fixed it.
- Its symbol count (676 exported) is now **741**.

**Assume the remaining items carry the same class of error.** The plan describes
intent; the source is what is true.

**`docs/loupe-build-state.md`:** its claim that a user can see the proof-standing
census is wrong, as established in section 5. Everything else in it was
consistent with the source when checked this session, but it is a ~200KB file
written incrementally and the same rule applies: verify before quoting.

---

## 11. Rules any agent working here must follow

From `CLAUDE.md`, which is binding and overrides default behaviour.

**Enterprise grade or don't ship it.**

**No assumptions.** If a claim can be checked by reading the source, read the
source. Never state a fact about the code from memory when the file is right
there. This rule exists because it was broken.

**Chunked work.** One unit at a time, finished, tested, committed. Commit each
completed unit as it lands rather than batching.

**Never invent a user story.** Do not assert what Alex, or anyone at Owl, thinks,
wants, asks, has experienced, or would have missed. If the value of a thing
cannot be stated as a fact about the system or the domain, ask Neil. This rule
exists because it was broken.

**Open with direction, never with questions.** A session opens by saying what it
is going to do and then doing it. If something is genuinely undecided, decide it:
read the source, take the defensible position, state it plainly along with what
would reverse it, and proceed. Escalate only when the unit actually turns on the
answer and the source cannot settle it, and then bring a recommendation, not a
menu.

**Orient Neil before asking him anything.** The build-state file is written for
the next session, not as a briefing for Neil, and he has not read it. Before any
question, say in plain language what the thing is, where it stands, and what is
missing. No internal vocabulary until defined in the same message. **A question
Neil cannot answer without opening a file is a badly asked question.** This rule
exists because it was broken repeatedly.

**Check before defending.** When Neil challenges something as wrong, verify it
against the source and report what is actually there, including when the answer
is that he is right.

### Design rules already settled

- Documents arriving together do not have to be related.
- Do not fall back to geometry-based table detection when nothing is found.
- **Do not hard-refuse a suspect amount.** Flag it, cite it back to its source,
  and let the analyst confirm or edit. This applies to all transactions and all
  fields.
- When a value is corrected, both the machine reading and the correction stay in
  the system and stay visible, but it must be obvious which is real, and **only
  the corrected value is used in money flows, sums, totals and searches.**
- **Proof class is computed, never set by hand, including by us.** A class a
  person can raise is an opinion. So a surface shows the class and shows what an
  adjudication changed; it never offers a control that sets one.

### After every commit, without being asked

1. Rewrite `docs/loupe-build-state.md`: new head and subject, what is now
   uncommitted, where the build order stands, anything newly parked, any question
   Neil has not ruled on, any defect found and not fixed.
2. Record anything a fresh session would otherwise have to rediscover: a command
   that failed and the form that worked, a fact established by reading source, a
   decision and its reasoning.
3. Commit the state file.
4. Tell Neil in bold that the state is written and this is a good point to start a
   new session, and say in one line what the next session should pick up.

### Case material and evidence files are never committed.

---

## 12. If you are picking this up cold, do this

1. Read `CLAUDE.md` in full. It is binding.
2. Confirm the real git tip: `git log --oneline -1`. Do not trust a head recorded
   in any document, including this one.
3. `df -h /dev/shm` before assuming anything can be installed. Borrow, do not
   install.
4. Read `docs/loupe-build-state.md` for the running detail, remembering section
   10 above.
5. Ask Neil for the ruling on the admission control before touching item 8. It is
   the single thing blocking that item from closing, the backend for it is
   finished and enforcing, and there is written frontend work parked in the tree
   waiting on his answer.
6. Plan whatever unit you take **from the source files**, not from the planning
   documents. Every time someone planned from the documents in this repo, the
   plan was wrong in a way only reading the modules caught.
