# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 5 September 2026 (records the ledger data layer, `fd88318`)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `fd88318`
  (`fd8831809428f505a1d4f541ff1eb65f81865854`), "Frontend read path for the
  relational ledger", parent `2a4c12d`. **Confirm the real tip with
  `git log --oneline -5`** at the start of every session rather than trusting
  this line.
- **Nothing is pushed.** Push is blocked; Neil pushes.

### Uncommitted

Nothing tracked. The tree is clean.

Still untracked and still un-removable from a session (workspace denies
`unlink`) — Neil has to delete these from his side:

- `backend/services/financial/export_manifest.py.bak`
- `backend/services/financial_export_service.py.bak`
- `frontend_v2/src/__probe.test.ts` — a diagnostic left by the vitest
  investigation two sessions ago. It is **counted in the frontend baseline
  below** (it contributes 1 file and 1 test), so when it is deleted the unit
  numbers drop by one each and that is expected, not a regression.

### Scale

75 commits since `c4246c0` (27 August), counting `fd88318`.

Backend unchanged this session and these figures were measured last session:
`backend/services/financial/` **44 modules**, **32,452 lines**;
`backend/tests/test_financial_*.py` **47 files**, **3,057 tests**.

---

## What this session did

One build item: **the frontend read path for the relational ledger**, item 12's
first remainder. Committed as `fd88318`, 1,103 insertions across five files, no
deletions.

This is the **data layer only**. It is deliberately a unit on its own, because
the decisions in it are the ones that are expensive to get wrong, and the screen
that consumes it is a separate and much more mechanical piece of work.

### What landed

- `frontend_v2/src/features/financial/api.ts` — **+185 lines, purely
  additive.** The existing Neo4j-backed `Transaction` types are untouched above;
  the ledger block sits below a section comment saying plainly that these are
  two different stores. Adds the five closed-vocabulary arrays,
  `LedgerTransaction` (27 fields), `LEDGER_TRANSACTION_FIELDS`,
  `LedgerResponse`, and `financialAPI.getLedgerTransactions`.
- `frontend_v2/src/features/financial/lib/ledger-format.ts` — **new, 369
  lines.** Money scaling and vocabulary narrowing. The only module that knows
  how to turn a stored row into something a person reads.
- `frontend_v2/src/features/financial/hooks/use-ledger-transactions.ts` —
  **new, 47 lines.** The React Query read.
- `frontend_v2/src/features/financial/api.ledger.test.ts` — **new, 280 lines,
  16 tests.**
- `frontend_v2/src/features/financial/lib/ledger-format.test.ts` — **new, 222
  lines, 22 tests.**

### The three decisions, and why

Recorded here as well as in the commit message, because these are the ones a
later session is most likely to undo by accident.

**1. Money is scaled by cutting the digit string, never by dividing.**
`amount_minor` is an integer count of minor units, and how many minor units make
a major unit depends on the currency: none for yen, two for most, three for
Bahraini and Kuwaiti dinar. A blanket division by a hundred would report every
yen figure as a hundredth of itself and every dinar figure as ten times itself.
Separately, near the top of the safe integer range the gap between representable
floating-point numbers is wider than a cent, so dividing there silently loses the
last one; `9007199254740991` is a tested case. Cutting a digit string cannot
round anything.

The scale itself comes from `Intl.NumberFormat(...).resolvedOptions()
.maximumFractionDigits` — the runtime's own currency data — rather than a
hardcoded table that would go stale. When the code cannot be scaled at all, the
result carries `scaled: false` and the raw digits, so a caller has been told it
is not a real figure rather than being handed one that is a hundred times too
small.

Thousands grouping is **fixed en-US, not locale-derived**, so two people reading
the same case see the same figure.

**2. Closed vocabularies are typed `string` on the wire and narrowed at
runtime.** A backend one version ahead of the deployed bundle can legitimately
send a `ledger_status` this build has never heard of. A union type would let that
value through while claiming it had been checked, and it would arrive on screen
as an empty badge — which reads as *an answer* ("this row has no status") rather
than as this build being out of date. So `LedgerTransaction` types those fields
loosely on purpose, and `ledger-format.ts` narrows every one of them, returning
either the member's meaning or an explicit statement that we do not recognise it.
This follows the precedent already set by `use-route-checks.ts` for route-check
outcomes.

Each vocabulary also refuses members belonging to a *different* vocabulary:
`readProofClass("admitted")` narrows to null. Tested.

**3. The hook sits under the query key `["financial-ledger", ...]`, outside the
`["financial", ...]` prefix.** Verified by grep, not assumed: every mutation in
`use-financial-data.ts` invalidates `["financial", caseId]`. Those write to the
**Neo4j graph** and cannot change a Postgres ledger row — categorising a graph
transaction or correcting its amount there leaves the ledger exactly as it was.
Sharing the prefix would refetch the ledger on every graph edit, and worse, would
imply a relationship between the two stores that the write paths do not have.

### Cross-language guards, and proof that they bite

Four guards read backend Python source and fail if the two languages drift:

- the emitted field set against `TransactionView.to_json` in
  `backend/services/financial/transaction_query.py`;
- each of the five vocabularies against `backend/postgres/models/enums.py`;
- the extraction-layer range against the `extraction_layer BETWEEN 0 AND 3`
  CHECK in `backend/postgres/models/financial.py`;
- the endpoint's own parameter list and response envelope in
  `backend/routers/financial_ledger.py`.

Each Python block is located and **scoped to its own body** rather than searched
for anywhere in the file, following the note in `use-route-checks.test.tsx` that
a whole-file search once passed on a copy of a guard living elsewhere.

**These were mutation-tested this session, not just asserted.** Removing
`"bank_reference"` from `LEDGER_TRANSACTION_FIELDS` and `"superseded"` from
`LEDGER_STATUSES` produced exactly two failures with the right messages; the file
was then restored byte-identically from a backup and re-run green. A guard that
has never been seen to fail is not evidence of anything.

### Verification, all run this session

- Frontend unit project: **56 files, 323 tests, pass** (was 54 / 285; +2 files
  and +38 tests, exactly the new work).
- Frontend browser project: **2 files, 4 tests, pass**.
- `npx tsc -b`: 0. `npx eslint .`: 0.
- Commit verified by `git diff --stat HEAD <tree>` before the ref was written:
  exactly the five intended files, 1,103 insertions, no deletions. Tree
  tracked-clean afterwards.

Backend was not re-run; nothing backend changed.

---

## Durable facts, kept so no one rediscovers them

The bootstrap, the baselines, the `VITE_CACHE_DIR` requirement, the playwright
install, the storybook limitation and the git procedure all live in
**`CLAUDE.md`**. Deliberately not duplicated here.

### New this session

- **Any scratch file in `/tmp` needs a per-user name, not just the git index.**
  `/tmp` is sticky and the sandbox user changes every session, so a plain
  `/tmp/tsc.out` left by an earlier session is owned by another uid and a
  redirect into it fails with `Permission denied`. This cost a few minutes
  looking like a typecheck failure when the typecheck was fine. Use
  `/tmp/<name>-$(id -un).<ext>` for everything, the same way `CLAUDE.md` already
  requires for the index.
- **The house pattern for API tests** is in `src/features/cases/api.test.ts`:
  swap `globalThis.fetch` for a `vi.fn()`, resolve a hand-built `Response`,
  assert with `toHaveBeenCalledWith(url, expect.objectContaining({...}))`, and
  restore in `afterEach`.
- **No shared money formatter existed before this unit.** Every financial
  component reaches for `toLocaleString("en-US", ...)` on a float. Those are the
  Neo4j-backed `Transaction` rows, which carry floats, so they are not wrong
  today — but any new code touching `amount_minor` must use
  `formatLedgerAmount` and nothing else.
- **`backend/routers/financial_ledger.py` is reachable and tested.** Its five
  router tests ran for the first time last session and pass.

### Carried forward, still true

- **SQLAlchemy flush ordering does not follow raw ForeignKeys.** With no ORM
  `relationship()` between two mappers, commit the parent row first, then the
  dependent row in a second commit.
- **The full engine pytest suite cannot run on 3.10** — pre-existing
  `from datetime import UTC` in
  `evidence-engine/app/services/pipeline_run_state.py` is 3.11+ only.
- **The exports guard needs no edit for a new module**, as long as the module
  contributes names through `__init__.py` and has no module-level `__all__`.
- **The storybook vitest project cannot run here** and no story covers financial
  code. "vitest is green" only ever means the unit and browser projects. Off the
  critical path; do not investigate without a ruling from Neil.
- **`--reporter=basic` is not a valid vitest v4 reporter.** Use the default.
- **`chromadb` is deliberately absent from the bootstrap.** `VectorDBService`
  degrades and warns; the warning is expected output.
- **No live Postgres is needed for the financial suite.**
  `test_financial_transaction_query` builds SQLite in a temp directory.

---

## Build order

1–7. **Done.** Through the text-alignment tier and commit `3784dbe`.

8. **Done.** Financial subsystem description for Alex, delivered 1 September.

9. **Done.** Suspect-amount detection, `0910d9f`.

10. **Done.** Per-transaction source locator through the writers, `0d6b399`.

10a. **Done (1 September, no code).** Wiring investigation closed; triage out of
    the build.

11. Correction storage. **Still blocked on the correction-versus-re-ingestion
    question, below.**

12. Both halves of the "both stores" ruling are built — Neo4j by `de7ef21`,
    Postgres by `a9e0d29`. Remainders:
    - ~~**Frontend data layer for `GET /api/financial/ledger`.**~~ **Done,
      `fd88318`.**
    - **The ledger screen itself.** The next unit, and the obvious one to pick
      up. Nothing renders ledger rows yet: `getLedgerTransactions` and
      `useLedgerTransactions` have no caller outside their tests. Needs a
      component that lists rows and shows, per row, the amount through
      `formatLedgerAmount` and the narrowed status, proof class, direction,
      date source and extraction layer through the `read*` functions —
      including the "unrecognised" path, which must be visible rather than
      blank. Note the sequencing risk below: on real data it reads an empty
      table.
    - **Wiring `ingest_native_reading` into production.** The larger piece.
      Neil's ordering ruling was frontend first.

13. User-defined view tabs. Named snapshots of filter state, persisted,
    creatable, renameable, deletable. Also expose source document type onto the
    transaction row. (Two things, not one.)

### Parked (agreed with Neil, 1 September)

14. **Money movement over time.** No period-by-period series; every row carries
    `ordering_date`, so the data is there.

15. **Follow the money.** Chain across entities hop to hop. Distinct from
    doctrine tracing.

16. **Wire up tracing.** Built and tested, five doctrines, no caller, no route,
    no screen.

17. **Wire up exhibit tagging**, which needs an export path first.

---

## Open questions, waiting on Neil

**Correction versus re-ingestion.** Unchanged, still open, still blocking item
11. Proposal on the table (a correction triggers a genuine re-run of the balance
identity; only a re-run that closes moves the class), not accepted.

**Is content-hash de-duplication meant to be call-scoped only?** Still unruled.
`document_content_hashes` disambiguates duplicate content within one
`record_transactions()` call but not across two separate calls to the same
document.

**Capability with no route to the user.** `exhibit.py` and `tracing.py` remain
unrouted. Item 12's route-to-user gap is now half closed: the data layer exists,
the screen does not.

**Provenance of `exhibit.py`.** Unchanged: confirmed valuable, but it came from a
proposed build order, not a stated Owl requirement.

### Nothing new raised this session

No question arose during this unit that Neil has not already ruled on.

---

## Standing flags

- **The Postgres ledger has no production writer.** `ingest_native_reading` has
  no caller outside its own test file. The data layer committed this session is
  correct and tested, but against real data it will read an empty table until
  the wiring item lands. Neil was told this before the ordering ruling and ruled
  frontend first anyway; do not reopen it, but **do not let the empty screen be
  mistaken for a defect.**
- **P0 is unreachable on the current corpus.** No document carries its own
  control totals in a form that qualifies.
- **Half two has only ever run against synthetic ledgers.**
- **The item-1 geometry machinery IS reached in production** at the
  evidence-engine layer, verified end to end 1 September. Triage is out of the
  build by ruling; do not reopen without a new ruling.
- **No row in the corpus carries a running-balance column.** 30,570 rows across
  325 documents. Worth remembering for the screen: `running_balance_minor` is
  nullable and on this corpus will be null everywhere.
- **The alembic migration `20260902_evidence_table_geometry` has not been applied
  to any real database from a session** — the sandbox has no Postgres. First
  deployment needs an `alembic upgrade head` on Neil's side.

---

## Defects raised and not yet ruled on

Small, real, none blocking:

- `evidence-engine/tests/test_pdf_table_geometry.py::test_the_summary_agrees_with_the_payload_it_summarises`
  fails against current code: it asserts the summary's exact key set without
  `by_table_source`, which `geometry_summary` has emitted since `3784dbe`. A
  stale test, pre-existing.
- Model class is named `AdjudicationEvent`, not `Adjudication` (`ef9e33d`).
- Bulk processing above 50 files cannot work: `MAX_BATCH_SIZE = 50` against list
  paging at 250.
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
- The engine docstring in `evidence-engine/app/pipeline/pdf_extraction.py` claims
  table text is byte-identical to the pre-geometry path; false whenever the
  recovery pass replaces a `table_rectangle_only` reading.
- Recovered text-alignment chunks collapse empty cells in the `" | "` join and
  sweep footer prose into the table chunk. Geometry unaffected; full diagnosis in
  the `72d1b1a` revision of this file.
