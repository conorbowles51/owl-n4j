# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 2 September 2026 (records the item-12 frontend wiring unit:
`SourceHighlight` into `TransactionDetailPanel`, closing the Neo4j-side loop
end to end)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `de7ef21`
  (`de7ef212623d4751ec3a1f5f2da334216e64b9a1`), "Wire SourceHighlight into
  TransactionDetailPanel (frontend, one unit)", parent `b3d1c48`. **Confirm
  the real tip with `git log --oneline -5`** at the start of every session
  rather than trusting this line.
- **Nothing is pushed.** Push is blocked; Neil pushes.

### Uncommitted

- Two stray `.bak` files that should be deleted, not committed:
  `backend/services/financial/export_manifest.py.bak`,
  `backend/services/financial_export_service.py.bak`. **The session workspace
  denies `unlink` for workspace files, so they cannot be deleted from a session.
  Neil has to remove them from his side.** They are untracked and harmless
  meanwhile.
- **New this session, same restriction:** `frontend_v2/src/__probe.test.ts`.
  Created to check whether this sandbox's jsdom implements
  `URL.createObjectURL` (it does — see durable facts below), then could not be
  removed by `rm`, `mv`, `git clean -f`, or Python `os.remove()`, all
  "Operation not permitted." Overwritten with a harmless always-passing test
  and a comment asking Neil to delete it from a normal shell. Deliberately
  left out of the commit. **Now three files in this category**, all needing a
  session-external delete.

No tracked changes are outstanding. The tree is otherwise clean of build work.

### Scale, measured from git

69 commits since `c4246c0` (27 August), counting `de7ef21`.
`backend/services/financial/` is unchanged this unit: 43 modules, 32,221
lines by `wc -l`; `backend/tests/test_financial_*.py` unchanged: 45 files,
**3,041 tests** (no backend file touched this unit, so not re-run).
Frontend unit suite, re-run this session: **54 files, 285 tests**, 0
failures — up from 52 files / 277 tests: +2 files exactly accounts for the
new `TransactionSourceHighlight.test.tsx` and the stray `__probe.test.ts`
(the new `.tsx` component itself is not a test file), and +8 tests is the
7 in the new suite plus the probe's 1.

---

## What this session did: wire `SourceHighlight` into `TransactionDetailPanel` (`de7ef21`)

### The unit

Confirmed with Neil at the start of the session (item 12's first remaining
sub-bullet): the data to close the Neo4j-side loop already existed in two
separate places — `/api/financial` rows carry `locator` JSON since `d48f189`,
and `GET /api/evidence/{id}/page/{n}/image` can render the page it points at
since `530c3a6` — but nothing on the frontend read both together. This unit
is entirely that reading-together: five files, one commit, 277 insertions,
0 deletions.

- `frontend_v2/src/features/financial/api.ts` — `BaseFinancialRecord` gained
  an unparsed `locator?: unknown` field. Left unparsed deliberately:
  `readLocator` in `features/financial/lib/locator.ts` is the one place that
  reads it, so this side of the contract never guesses at a shape the backend
  didn't commit to.
- `frontend_v2/src/features/evidence/api.ts` — `evidenceAPI.getPageImageUrl`,
  mirroring the existing `getFileUrl`.
- `frontend_v2/src/features/financial/components/TransactionSourceHighlight.tsx`
  (new). The gate in front of the existing `SourceHighlight`: runs the same
  `readLocator` parse `SourceHighlight` uses internally to decide whether a
  locator kind (`page_only` or `page_rectangle`) needs an image at all, so the
  two components never disagree about what kind a payload is. Only then does
  it fetch — an authenticated blob via the existing house
  `useProtectedObjectUrl` pattern from `frontend_v2/src/lib/protected-file.ts`
  (the image endpoint sits behind the same auth as every other evidence file,
  so a bare `<img src>` could not have carried the token). `not_positional`,
  `unlocated`, and any payload `readLocator` refuses cost no network call,
  and neither does a `page_only`/`page_rectangle` locator with no
  `sourceDocumentId` on the row. `SourceHighlight` itself is unchanged — its
  own docstring already said the image arrives as a prop because no
  page-render endpoint existed yet, and that held exactly as written.
- `TransactionDetailPanel.tsx` — wired to render the new wrapper in place of
  the bare locator sentence.

**Tests.** `TransactionSourceHighlight.test.tsx`, 7 tests: the three no-image
locator kinds never fetch; a page-needing kind with no `sourceDocumentId`
never fetches; a `page_only` fetch shows the loading state then the resolved
image with no box; a `page_rectangle` fetch draws the highlight box and the
accessible label once resolved; a failed fetch falls back to
`SourceHighlight`'s own no-image sentence rather than erroring.

### Verification

- Full frontend suite: **54 files, 285 tests, 0 failures** (up from 52/277 —
  see Scale above for exactly what accounts for the difference).
- `npx tsc -b`: clean. `npx eslint .`: clean.
- One unrelated, non-blocking artifact during the vitest run: an "Unhandled
  Error" `EPERM: operation not permitted, unlink
  '.../node_modules/.vite/vitest/.../deps/@tanstack_react-query.js'` — Vite's
  own dependency-cache cleanup hitting the same sandbox unlink restriction
  documented elsewhere in this file, not a test failure, not from this unit's
  code.
- Diffstat verified against HEAD before committing (5 files, 277 insertions,
  0 deletions, nothing else); tree tracked-clean after the ref update.

---

## Durable facts from this and earlier sessions, kept so no one rediscovers them

### New this session

- **`Response` mocks in vitest/jsdom need a string body, not a `Blob`.**
  `new Response(new Blob(["x"], { type: "image/png" }), { status: 200 })`
  fails with `TypeError: object.stream is not a function` — jsdom's `Blob`
  is not stream-capable in the way Node's native `Response` constructor
  expects. Fix: `new Response("fake-png-bytes", { status: 200, headers: {
  "Content-Type": "image/png" } })`, matching the existing pattern in
  `frontend_v2/src/lib/protected-file.test.ts`. Anything mocking a fetched
  binary response should use this shape.
- **jsdom in this sandbox implements `URL.createObjectURL` and
  `URL.revokeObjectURL` as real functions**, so both can be `vi.spyOn`'d
  directly in a test without replacing the `URL` global. Confirmed with a
  disposable probe test (see next point for why that was a mistake to leave
  behind).
- **A self-created file can hit the same unlink restriction as the
  pre-existing `.bak` files.** This is not limited to files that were
  already in the tree: a throwaway probe test created and then no longer
  wanted (`frontend_v2/src/__probe.test.ts`) could not be removed by `rm`,
  `mv`, `git clean -f`, or Python's `os.remove()` — all "Operation not
  permitted." **Lesson for future sessions: don't create a scratch file in
  the workspace tree at all for a quick check like this** — there is no
  guaranteed way to remove it afterward. If one is created by mistake,
  overwrite its content to something harmless and clearly labeled rather
  than leaving it in whatever half-finished state the check left it in, and
  record it here and in Uncommitted so it isn't mistaken for product code.

### Carried forward

- **The commit procedure in CLAUDE.md is missing committer identity.**
  `git commit-tree` fails with "Committer identity unknown" — the documented
  env line sets only `GIT_AUTHOR_*`. The fix that respects "never modify git
  config": also set `GIT_COMMITTER_NAME="Neil Byrne"
  GIT_COMMITTER_EMAIL="thenofisamizdat@gmail.com"` on the same command.
  Used again successfully this session. CLAUDE.md should gain this line;
  flagged for Neil below.
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
  filename per commit (`/tmp/loupe_sourcehighlight_wire.index` this time).
- **The exports guard needs no edit for a new module**, as long as the module
  contributes names through `__init__.py` and has no module-level `__all__`.
  Passed unchanged again for `transaction_locators`. (Not exercised this
  session — no backend module was added.)

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

12. **In progress — five units landed** (`d79199a` viewer, `530c3a6`
    page-render endpoint, `d48f189` geometry persistence + transaction join,
    and now `de7ef21` wiring `SourceHighlight` into `TransactionDetailPanel`).
    The data-path ruling is in: **both stores**. The Neo4j side of item 12 is
    now closed end to end: a transaction with a locator, opened in the
    detail panel, shows its source page with the value highlighted on it.
    What remains, in no ruled order:
    - **The Postgres ledger read API** (the other half of the "Both" ruling).
      Nothing on the frontend reads the ledger yet.
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
`tracing.py` remain unrouted. The Neo4j-side gap in item 12 is now closed
(`de7ef21`); the only remaining route-to-user gap on the financial screen is
the Postgres ledger half of item 12, which has no frontend at all yet.

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
