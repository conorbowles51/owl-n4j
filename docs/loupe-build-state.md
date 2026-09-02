# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 1 September 2026 (fifth rewrite this date; this one records
the geometry persistence + transaction join unit, both halves of the
`per_table` data path)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `d48f189`, "Persist table geometry and join
  transactions to it (persistence + join, one unit)". The commit carrying the
  current revision of this file sits one above that, so **confirm the real tip
  with `git log --oneline -5`** at the start of every session rather than
  trusting this line.
- **Nothing is pushed.** Push is blocked; Neil pushes.

### Uncommitted

- Two stray `.bak` files that should be deleted, not committed:
  `backend/services/financial/export_manifest.py.bak`,
  `backend/services/financial_export_service.py.bak`. **The session workspace
  denies `unlink` for workspace files, so they cannot be deleted from a session.
  Neil has to remove them from his side.** They are untracked and harmless
  meanwhile.

No tracked changes are outstanding. The tree is otherwise clean of build work.

### Scale, measured from git

67 commits since `c4246c0` (27 August), counting `d48f189`.
`backend/services/financial/` is 43 modules, 32,221 lines by `wc -l`.
`backend/tests/test_financial_*.py` is 45 files, 41,860 lines, **3,041 tests**.
Frontend unit suite unchanged this unit: **52 files, 277 tests** (not re-run
this session; no frontend file changed).

---

## What this session did: the persistence + join unit (`d48f189`)

### The survey, and a correction to the last two revisions of this file

The session opened on the item-12 data-path question. The survey read the
engine source before designing anything, and it disproved a claim the previous
two revisions of this file carried: that "the engine persists
`table_geometry.per_table` (cell locators) inside `ProcessedArtifact` metadata"
and that "the registry's wholesale metadata persistence keeps it live."
**Wrong.** The extraction module's own docstring
(`evidence-engine/app/pipeline/pdf_extraction.py`,
`_table_geometry_metadata`) says the dict is transient: it is passed to
`build_extraction_quality_report`, which reads named keys and keeps only the
summary counts, and is never written to a column. `per_table` died with the
job. There was no rectangle anywhere durable for a join to reach.

This was surfaced to Neil rather than silently worked around. Three rulings
came back, in order:

1. **Data path: "Both."** The viewer will be fed by a Postgres ledger read
   API AND a Neo4j `per_table` join. (This closes the "which store feeds the
   viewer" open question from the previous revision.)
2. **Order: the `per_table` join first** — join the transaction screen's
   existing Neo4j read path to cell locators.
3. **Unit reshape, after the transience finding:** since the join's premise
   (persisted geometry) did not exist, Neil ruled **"Persistence + join, one
   big unit"** — land durable persistence and the join in this one session,
   accepting the break in the one-unit-per-session rhythm to deliver a
   clickable path end to end.

### The unit that landed

Eleven files, one commit, 1,404 insertions. The commit message on `d48f189`
carries the full reasoning; the shape:

**Engine half — geometry now outlives the job.**

- `evidence-engine/app/services/evidence_table_geometry.py` —
  `group_per_table_by_page` (geometry-less entries counted not stored,
  malformed entries counted invalid not raised on) and
  `replace_evidence_table_geometry` (delete-then-insert in one commit, so the
  stored geometry always describes exactly one extraction run, including a run
  that found no tables). Returns `GeometryPersistenceResult` so orchestrators
  log what happened rather than inferring it.
- New table `evidence_table_geometry`: one row per (evidence file, page),
  JSONB payload of the geometry-bearing `per_table` entries whose table
  rectangle landed on that page. Per-page rows are the bounding the extraction
  docstring demanded before anything persisted `per_table`.
- **The backend alembic tree owns the schema**: new head
  `20260902_evidence_table_geometry` (file
  `backend/postgres/alembic/versions/20260902_add_evidence_table_geometry.py`),
  model in `backend/postgres/models/evidence.py` with a
  `page_number >= 1` check constraint. The engine model in
  `evidence-engine/app/models/job.py` is a write-only mirror, said so in its
  docstring.
- `orchestrator.py` and `batch_orchestrator.py` call the replace after the
  document-text upsert. Failure is logged and never propagates
  (auxiliary-not-fatal, same doctrine as the grouping). The shared-session
  orchestrator does `await db.rollback()` in its except so a failed geometry
  write cannot poison the session for the steps after it; the batch path uses
  its own `async with async_session()`.

**Backend half — the join the transaction screen reads through.**

- `backend/services/financial/transaction_locators.py`. There is no stored key
  from a transaction to a cell, so the join is textual and the module
  docstring says so plainly: a grid row is a candidate when at least
  `TRANSACTION_MATCH_MINIMUM_CELLS = 2` of its distinct non-empty
  whitespace-normalised cell texts occur inside the normalised
  `source_excerpt`; a candidate wins only by strictly beating every other
  candidate on the page. A tie refuses and degrades to `page_only` — the same
  refusal `locate_table` makes for overlapping cells. Fallback ladder, best to
  worst: union rectangle of the winning row's clickable cells; the owning
  table's own rectangle (matched by cell identity, not equality); `page_only`;
  `unlocated`. Case is deliberately not folded: the excerpt was built from
  these same cell texts, so a case difference is a real difference, and
  folding could only convert a safe fallback into a wrong highlight.
- `attach_transaction_locators(db, transactions)` mutates the router's dicts
  in place under `LOCATOR_PROVENANCE_KEY` — the same `"locator"` key the
  ledger writer uses, deliberately, so one reader serves both stores. Rows
  already carrying the key are left alone (an ingestion-time locator knows
  more than this join does). Non-UUID `source_document_id` (the filename
  fallback) gets the honest `page_only`/`unlocated` rather than nothing. One
  geometry query per evidence file, not per row.
- `backend/routers/financial.py` `GET /api/financial` now depends on the
  Postgres session and calls the attach inside try/except with
  `logger.exception`: the transaction list is the one thing this feature must
  never take down.
- Exports: `TRANSACTION_MATCH_MINIMUM_CELLS`, `attach_transaction_locators`,
  `locate_transaction` through `services/financial/__init__.py`. Exports guard
  passed unchanged, as its structural design predicts.

**Tests.** `backend/tests/test_financial_transaction_locators.py`, 22 tests in
four classes (pure-join wins, refusals, the full fallback ladder, and
sqlite-backed `attach` tests on the real model following the
`test_financial_admission.py` fixture template).
`evidence-engine/tests/test_evidence_table_geometry.py`, 7 pytest tests in the
house engine convention (AsyncMock session, compiled-SQL assertions,
delete-before-insert order, string-UUID coercion).

### Verification

- Backend financial suite: **`Ran 3041 tests, FAILED (errors=1)`, skipped=0
  (measured)** — exactly the old 3,019 plus the 22 new, and the single error
  was verified by traceback to be the documented `jose` ModuleNotFoundError in
  `tests.test_financial_router`, nothing else. This is the new fingerprint.
- Engine tests: the new file `7 passed` alone. The collectable engine subset
  (see the durable environment facts below for why it is a subset) ran
  **244 passed, 1 failed, 1 error**; the failure and the error are both
  pre-existing and are recorded below, neither is from this unit.
- Diffstat verified against HEAD before committing (11 files, 1,404
  insertions, nothing else); tree tracked-clean after the ref update.

---

## Durable facts from this and earlier sessions, kept so no one rediscovers them

### New this session

- **The commit procedure in CLAUDE.md is missing committer identity.**
  `git commit-tree` failed with "Committer identity unknown" — the documented
  env line sets only `GIT_AUTHOR_*`. The fix that respects "never modify git
  config": also set `GIT_COMMITTER_NAME="Neil Byrne"
  GIT_COMMITTER_EMAIL="thenofisamizdat@gmail.com"` on the same command.
  CLAUDE.md should gain this line; flagged for Neil below.
- **SQLAlchemy flush ordering does not follow raw ForeignKeys.** With no ORM
  `relationship()` between two mappers, a single flush has no insert-ordering
  constraint between them, and under SQLite `PRAGMA foreign_keys=ON` the
  child row can be inserted before its parent and fail with
  `FOREIGN KEY constraint failed`. Reproduced with `echo=True`. Fix: commit
  the parents first, then the dependent row in a second commit. The loader
  fixture in `test_financial_transaction_locators.py` carries a comment
  explaining this.
- **The full engine pytest suite cannot run on the 3.10 sandbox, and never
  could.** Pre-existing `evidence-engine/app/services/pipeline_run_state.py`
  line 4 does `from datetime import UTC` — Python 3.11+ only. That blocks
  collection of `test_pipeline_run_state.py`, `test_batch_dispatch.py`,
  `test_upload_security.py` directly and `test_chunk_publication.py`,
  `test_document_summary.py`, `test_pdf_extraction.py` transitively (they
  import the orchestrator chain), plus the `client` fixture of
  `test_service_auth.py` (imports `app.main`). Run the rest with
  `--ignore` for those six files; there is no documented full-engine-suite
  baseline and this environment cannot produce one.
- **Engine deps needed beyond the backend list** (all
  `pip3 install --break-system-packages`): `pytest>=8,<9`,
  `pytest-asyncio>=0.25,<1` (pyproject sets `asyncio_mode = "auto"`),
  `aiofiles`, `pydantic-settings`, `asyncpg`, `chromadb`, `arq`.
- **The sandbox was recycled mid-work**: every previously installed package
  vanished between the baseline suite run and the next one. Symptom:
  `ModuleNotFoundError: No module named 'sqlalchemy'` from a suite that
  passed an hour earlier. The repo's `backend/venv` is broken (python3.13
  symlinks to nonexistent binaries) — never use it. Reinstall from the
  selective list; `fastapi` resolved to 0.141.1 this time (the previous
  revision's 0.123.9 pin is not required, unpinned works). `passlib` and
  `redis` are also needed on the `test_financial_router` import chain, and
  installing them plus `neo4j==5.28.2` and `openai==2.9.0` is what walks that
  chain back to failing on `jose` — which is the documented state. **Still do
  not install python-jose.**

### Carried forward

- **`routers.evidence` cannot be imported in this environment, so its
  endpoints are tested statically.** The import chain reaches
  `services/auth_service.py` → `from jose import ...` → ModuleNotFoundError.
  House precedent: `tests/test_financial_route_check.py` (AST over router
  source). Note `routers.financial` imports fine — the sqlite-backed tests in
  `test_financial_transaction_locators.py` did not need it, but the
  distinction matters when testing endpoints.
- **PyMuPDF 1.28.2 facts, measured in this sandbox.** `get_pixmap` accepts a
  plain 6-tuple as `matrix`. Rotation is applied on both sides of the locator
  agreement (rotated page reports rotated `rect` and renders the same
  aspect), which is why neither `capture()` nor `render_page_png` contains
  rotation arithmetic.
- **The item-10 design ruling:** `TransactionDraft.locator` is required with
  no default; a caller with nothing to say passes
  `Locator(kind=LocatorKind.unlocated)` explicitly, so a forgotten call site
  stays distinguishable from a reader that tried and failed.
- **The writer owns the provenance key.** `record_transactions` serialises
  into `provenance["locator"]` (`LOCATOR_PROVENANCE_KEY`); caller-supplied
  values are refused at the draft. The join half now writes the same key on
  the Neo4j read path, and skips rows that already carry it.
- **Locator JSON shape, as `to_json` writes it**: `{"kind": ...}` plus `page`
  when known (omitted, not null), and for `page_rectangle` only `rect`
  `[x0,y0,x1,y1]`, `page_size` `[w,h]`, `units: "millipoints"`,
  `space: "pdf_displayed"`. US Letter is 612,000 × 792,000 millipoints.
- **Engine wiring (verified end to end, 1 September).**
  `evidence-engine/app/pipeline/pdf_extraction.py` wires
  `services.financial.pdf_tables.read_tables` in via `_load_table_reader()`.
  Verified on a real bank statement: 5 tables, 224 located values. The
  transience warning in `_table_geometry_metadata` is now half-superseded:
  the summary is still transient, but the geometry itself is persisted by
  this unit's engine half. Triage is **out of the build by Neil's ruling**.
- **Frontend verification trio**: from `frontend_v2/`, `npx vitest run`,
  `npx tsc -b`, `npx eslint .`. The browser project cannot run in the sandbox
  (no Playwright browsers); unit-project counts are the baseline. Eslint does
  not exempt underscore-prefixed unused destructures.
- Stale `/tmp/loupe*.index` files cannot be removed; pick a fresh index
  filename per commit (`/tmp/loupe_item13_geometry_join.index` this time).
- **The exports guard needs no edit for a new module**, as long as the module
  contributes names through `__init__.py` and has no module-level `__all__`.
  Passed unchanged again for `transaction_locators`.

---

## Build order

1–7. **Done.** Through the text-alignment tier and commit `3784dbe`.

8. **Done.** Financial subsystem description for Alex, delivered 1 September.
   The full text is not on disk; only the recorded shape survives (two working
   halves, then a separate "being built" section). If Neil pastes it, store it
   under `docs/`.

9. **Done.** Suspect-amount detection, `0910d9f`.

10. **Done.** Per-transaction source locator through the writers, `0d6b399`.

10a. **Done (1 September, no code).** Wiring investigation closed; triage out
    of the build.

11. Correction storage. **Still blocked on the correction-versus-re-ingestion
    question, below.**

12. **In progress — four units landed** (`d79199a` viewer, `530c3a6`
    page-render endpoint, and now `d48f189` carrying both the geometry
    persistence and the transaction join). The data-path ruling is in:
    **both stores**. What remains, in no ruled order:
    - **Wire `SourceHighlight` into `TransactionDetailPanel`.** The data now
      reaches it: `/api/financial` rows carry `locator` JSON, and the page
      image is served by the `530c3a6` endpoint. This is the natural next
      chunk — it closes the loop for the Neo4j path end to end.
    - **The Postgres ledger read API** (the other half of the "Both" ruling).
    - **Wiring `ingest_native_reading` into production** — the ledger still
      has no production writer. Whether this comes before or after the read
      API is unruled.

13. User-defined view tabs. Named snapshots of filter state, persisted,
    creatable, renameable, deletable. Also expose source document type onto
    the transaction row.

### Parked (agreed with Neil, 1 September)

14. **Money movement over time.** No period-by-period series; every row
    carries `ordering_date`, so the data is there.

15. **Follow the money.** Chain across entities hop to hop. Distinct from
    doctrine tracing.

16. **Wire up tracing.** Built and tested, five doctrines, no caller, no
    route, no screen.

17. **Wire up exhibit tagging**, which needs an export path first.

---

## Open questions, waiting on Neil

**Correction versus re-ingestion.** Unchanged, still open, still blocking
item 11. Proposal on the table (a correction triggers a genuine re-run of the
balance identity; only a re-run that closes moves the class), not accepted.

**Capability with no route to the user — narrowed again.** `exhibit.py` and
`tracing.py` remain unrouted. `suspect_amounts` plus the row locators now
have data flowing to the API row; the last gap on the Neo4j side is the
frontend wiring chunk of item 12.

**Should CLAUDE.md's commit procedure gain the committer-identity line?** The
procedure as written fails on a fresh sandbox (see durable facts). The state
file cannot be the durable home for a git rule; Neil should either amend
CLAUDE.md or say where it goes.

**Provenance of `exhibit.py`.** Unchanged: confirmed valuable, but it came
from a proposed build order, not a stated Owl requirement.

~~Which store feeds the viewer~~ — **ruled this session: Both.** Recorded in
the session narrative above; no longer open.

---

## Standing flags

- **P0 is unreachable on the current corpus.** No document carries its own
  control totals in a form that qualifies.
- **Half two has only ever run against synthetic ledgers.**
- **The item-1 geometry machinery IS reached in production** at the
  evidence-engine layer, verified end to end 1 September. Triage is out of
  the build by ruling; do not reopen without a new ruling.
- **No row in the corpus carries a running-balance column.** 30,570 rows
  across 325 documents.
- **The alembic migration `20260902_evidence_table_geometry` has not been
  applied to any real database from a session** — the sandbox has no
  Postgres. The sqlite tests exercise the model, not the migration. First
  deployment needs an `alembic upgrade head` on Neil's side.

---

## Defects raised and not yet ruled on

Small, real, none blocking:

- **(1 Sept, this unit's verification, new):**
  `evidence-engine/tests/test_pdf_table_geometry.py::test_the_summary_agrees_with_the_payload_it_summarises`
  fails against current code: it asserts the summary's exact key set without
  `by_table_source`, which `backend/services/financial/pdf_tables.py`
  `geometry_summary` (line 469) has emitted since `3784dbe`. A stale test,
  pre-existing, not from this unit; the fix is adding the key to the
  expected set on the engine side.
- Model class is named `AdjudicationEvent`, not `Adjudication` (`ef9e33d`).
- Bulk processing above 50 files cannot work: `MAX_BATCH_SIZE = 50` against
  list paging at 250.
- 11 Capital One pages carry a full-page white image XObject, most likely
  whole-page redaction.
- `merging_properties` missing from `_ACTIVE_JOB_STATUSES`, plus a silent
  fall-through in `_sync_db_record_from_job`.
- `safe_float` does `round(f, 2)` and defaults to `0`.
- The `7d8289b` commit message understates what the commit did.
- Append-only is not enforced at the database.
- The p3 early-return limitation.
- `_get_dataset_metadata` uses all-or-nothing legacy detection.
- `execute_cypher_batch` takes unparameterised strings.
- `get_financial_transactions` compares `n.date` as a string.
- `RECOMMENDED_CONSTRAINTS` and `RECOMMENDED_INDEXES` need out-of-band
  application.
- Two defects in the mutation harness.
- `scripts/categorize_transactions.py:443` hardcodes `national telegraph`.
- `ProcessConfirmDialog.tsx` contains dead code.
- `frontend_v2/node_modules/.__dom_probe_leftover` left behind.
- **(1 Sept, wiring verification):** the engine docstring in
  `evidence-engine/app/pipeline/pdf_extraction.py` claims table text is
  byte-identical to the pre-geometry path; false whenever the recovery pass
  replaces a `table_rectangle_only` reading. Doc fix on the engine side.
- **(1 Sept, wiring verification):** recovered text-alignment chunks collapse
  empty cells in the `" | "` join and sweep footer prose into the table
  chunk. Geometry unaffected; full diagnosis in the `72d1b1a` revision of
  this file.
