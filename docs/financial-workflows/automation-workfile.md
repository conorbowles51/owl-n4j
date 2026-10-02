# Financial automation — headless workfile

Working file for `automation-delivery-plan-2026-09-28.md`. Every session (headless or
interactive) reads this after `CLAUDE.md`, does the **▶ NEXT** unit and nothing else,
then rewrites ▶ NEXT and appends to the log before it exits.

STATUS: RUN

(Set the line above to `STATUS: HALT — <reason>` to stop the headless runner. A session
sets it itself only when it is genuinely blocked on Neil; see "Halt rules".)

---

## ▶ NEXT

**U0 — Establish whether the untested 29 September release is green.**

The 29 Sept work (`a48958e0` through `bb3ccef3`) was pushed with builds only, no tests.
Nothing after it can be trusted until that is known.

1. Backend bootstrap per `CLAUDE.md` → Tests (skip if the packages already import).
2. A full run already exists (see Log, 2026-10-02): 39 backend failures/errors and 72
   vitest failures, by module. Start from those modules — run each failing module alone,
   triage, fix — rather than re-running the whole suite first. Run the full backend suite
   (command in `CLAUDE.md`) once at the end to confirm. Previous `CLAUDE.md` baseline
   (3057 OK) predates the 29 Sept work; the suite is now 5544 tests.
3. Frontend: `tsc -b` and `vitest --project unit` (cache-path rules in `CLAUDE.md`).
4. Fix every failure that the 29 Sept code caused, each fix a separate commit with its
   targeted module re-run. A failure that needs a product decision → record it under
   "Open defects" with a recommendation and move on; do not halt for it.
5. Record the new baseline counts in this file and in `CLAUDE.md` → Tests.

Done when: suite and frontend checks are green (or every remaining failure is listed
under Open defects with a cause), committed, pushed.

---

## Queue (in order — move the head into ▶ NEXT when the current unit lands)

**U1 — Batch read performance (checkpoint A + E instrumentation).**
Live: `batch_status` for one 244-item batch takes ~230 s — the leading candidate for
the "Failed to fetch" reports, but unproven. Reproduce on a synthetic 250- and
1,000-item batch with a timing harness around `import_batches.batch_status` /
`checked_batch_items` (`backend/services/financial/import_batches.py`). Find what the
read path recomputes (comparison_sources, proposal reconstruction, per-item
reassessment). GET must not reparse PDFs or write state. Stored item summaries are
stale because read-time reassessment is never persisted — fix that at the write side
(assessment on save / worker), not by persisting from a GET. Target from the plan:
first useful list ≤3 s p95. Add request correlation id + server timing to the batch
endpoints so the live cause can be confirmed later. Harness code is committed;
private data never.

**U2 — Ledger → graph projection is never invoked.**
`services/financial/projection.py:project_case` has no production caller (only its
test). Live: 11,549 admitted transactions, 0 `FinancialTransaction` nodes, and the
reviewed identity graph sweep (`identity_graph.py` ~L165/L239) retries forever because
the payment nodes it waits for never appear. Wire projection into the admission/import
worker path (idempotent, after commit, failure isolated from the ledger write — graph
follow-up is validated separately from ledger completion per the plan). Bound the
sweep: missing-node retries back off and surface as a visible status, never a hot loop.
Provide the backfill as the same code path (a command that calls the worker's
projection for a case) — **build and test it; do not run it against live data.** Record
the command for Neil.

**U3 — Backend shutdown hang.**
Shutdown waits on "Waiting for background tasks" indefinitely; uvicorn 0.38 needs
SIGINT to force; unit `TimeoutStopSec=14500`. Find the background tasks that never
finish (likely the sweep from U2 and long-running import/reading tasks), make them
cancellable with a bounded shutdown, and make deploy's stop path write last-good + log
tail on timeout. **Code and tests only — no service restarts on this box.**

**U4 — Checkpoint A baseline harness.**
Per plan §1: repeatable benchmark over real extraction → catalog → proposal →
admission → batch preparation → import, on committed synthetic fixtures; records
attempts, readiness reasons, human actions needed, worker and wall time. Run current
code to produce the baseline report (`docs/financial-workflows/baseline-<date>.md`).
Then restate the ETA from measurements.

**U5 — Checkpoint B gate.** Prove plan §2 gate with the harness: save once → ready in
every view; independent batch edits intact; existing-draft upgrade repeatable; one
group confirmation imports the exact eligible set once; PostgreSQL concurrency tests
(loopback 55434, disposable schemas — check the port is actually available first).

After U5: continue with plan checkpoint C (repair ladder + date provenance), slicing it
into units here before starting it.

---

## Halt rules (headless)

Nobody answers questions in a headless run. Per `CLAUDE.md`, decide, record the
reasoning, proceed. Set `STATUS: HALT — <reason>` only when:

- the unit cannot proceed without changing live data, live services, or deployment
  configuration;
- the unit turns on a product decision the source cannot settle (write the
  recommendation next to the halt);
- the same unit has failed to land in two consecutive sessions;
- a checkpoint gate requires live acceptance by Neil or Alex.

## Box facts (verified 2026-10-02)

- Repo: `/home/conorbowles51/app-v3/owl-n4j`, branch `integration/evidence-main-reunion`.
  Pushing it triggers the guarded deploy to the live box.
- The plan's `data/local-runtime/backend-venv` / `engine-venv` do **not** exist on this
  box. Use the `CLAUDE.md` bootstrap (system `python3`).
- Live read-only probes: `PYTHONPATH=backend`, source `.env`, `.venv` python, and wrap
  in a READ ONLY transaction. Stored batch item summaries are stale — measure through
  `batch_status`, not raw DB counts.

## Open defects (found, not fixed)

- (none recorded yet)

## Log

- 2026-10-02 — Workfile created with session prompt `scripts/headless/financial-prompt.md`
  (no runner script yet). Live findings above came from a read-only probe earlier the same day.
- 2026-10-02 (earlier interactive session, results recovered from its scratchpad, not re-run):
  - U0 partial: backend financial suite **Ran 5544, FAILED (failures=33, errors=6, skipped=12)**
    in 1189 s. By module: exports 22, identity_graph_integration 5, import_batches 3,
    unassigned_statement 2, statement_review_checks 2, statement_import_scotiabank 2,
    statement_row_assignment 1, pending_duplicates 1, batch_review_save_scope 1.
    Frontend `tsc -b` rc=0. vitest unit **72 failed / 1980 passed (17 of 295 files)** —
    StatementImportPanel 36, FinancialPage 17, FinancialSourceAudit 4, LedgerRowBrowser 2,
    13 other files 1 each. None of these failures are triaged or fixed yet.
  - U1 cause measured (live, read-only, cProfile): `batch_status` on the 244-item batch
    = 231.8 s, of which `statement_import_overlap.comparison_sources` = 224 s — it calls
    `statement_import.read_statement_import` for 250 statements (re-proposing PDFs) on every
    GET via `import_batches.checked_batch_items` → `read_pending`. Secondary: catalog 31 s,
    `review_upgrade.attach_upgrade` 20 s, BBVA `norm` 17 s (17.9M genexpr calls).
    Batch state: 53 ready / 191 attention. No fix written yet.
