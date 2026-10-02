# b-unique: database uniqueness guarantee for saved statements (headless session, 2026-10-02)

Branch `fin/b-unique`, based on `fin/b-gate` head `58a63dfc` (itself on `fin/release-1` `6335e4e8`).
Nothing was pushed. No services, live databases, case data or evidence were touched, and the
migration has **not** been run against any database.

## What landed

| Commit | What |
|---|---|
| `c2151c61` | Migration `20261002_one_active_statement` (down_revision `20260924_statement_recovery`, the single head). Same constraint on the model. Losing-commit mapping in the statement writer (which also covers the batch worker), duplicate restore and recovery split. SQLite tests and PG tests. |

### The constraint (exact DDL as the migration runs it)

```
ALTER TABLE financial_source_documents ADD CONSTRAINT ex_financial_source_documents_one_active_statement
EXCLUDE USING btree (case_id WITH =, evidence_file_id WITH =,
  (coalesce(metadata ->> 'statement_import_statement_id', '')) WITH =)
WHERE (document_type = 'statement_review' AND status = 'admitted' AND NOT (metadata ? 'financial_import_removal'))
DEFERRABLE INITIALLY DEFERRED
```

- **Upgrade** runs `LOCK TABLE financial_source_documents IN ACCESS EXCLUSIVE MODE`, then a grouped query
  over the same predicate. If any group has more than one row it raises `RuntimeError` naming every case,
  evidence file, statement id and document id, and adds nothing. Otherwise it adds the constraint.
  Coordinator's live read-only check at 18:40 found 0 offenders among 937 admitted statement_review docs.
- **Downgrade** runs `DROP CONSTRAINT IF EXISTS`.
- **Model:** the same `ExcludeConstraint(...).ddl_if(dialect="postgresql")` in
  `FinancialSourceDocument.__table_args__`, with name/key/predicate as module constants. It is on the model
  because the PG test fixtures build their schema with `Base.metadata.create_all`. With `ddl_if`, SQLite
  `create_all` omits it (tested). A test asserts the model-compiled clause equals the migration DDL.
- **Syntax validation without a server:** the DDL, the offender query, LOCK, DROP and the model's full
  `CREATE TABLE` were parsed with `pglast` 8.4 (libpg_query, the real PostgreSQL parser), installed only
  into `/tmp/pglast-<user>`. The parser reads it as an exclusion constraint: btree, deferrable, initially
  deferred, 3 elements. Parsing does not prove planning or semantic acceptance (see Unproven).

### Code paths checked against the constraint

- `statement_import._write_statement_import_once` (was `_write_statement_import`). This is the only
  writer of `statement_review` docs other than recovery (checked: the only constructors are
  `documents.record_source_document` and `saved_statement_recovery.save_recovery`).
  - A new import inserts one doc. A same-file reread or replacement inserts the new doc (~L950) and then
    `_supersede`s the old one (~L1010) in the same transaction. That is fine because the check is deferred.
  - All three commits now go through `_commit_statement`. On SQLSTATE 23P01 with this constraint name, it
    rolls back and raises `_ConcurrentAdmission` (a `RunAborted`). The run is recorded **aborted** with
    "Another save of this statement committed first. Nothing was written by this run." `_write_statement_import`
    then retries once. The retry reads the committed copy: the same request returns its receipt with
    `created=False`, and a different request gets the existing 409 "already has imported transactions".
    If the retry also loses, the result is a 409 "committed at the same time", never a 500.
- Batch worker `import_batches._import_item`: unchanged. `created=False` already maps to `already_present`,
  and a `PdfMappingError` message already maps to `attention`. Tested end to end.
- `saved_statement_recovery.save_recovery`: inserts sections (distinct ids =
  `_digest(recovery_source, key)`, and keys are validated unique, L108) before setting the parent
  superseded (L363). This is fine because the check is deferred. A violation now maps to a 409 (it is
  serialized by the Case lock and the receipt check anyway).
- `duplicate_decisions.decide_duplicate` restore: restoring an excluded copy re-admits it. If that would
  make a second active copy, it is now a 409 `DuplicateDecisionError` instead of the router's 500.
- `import_removal` sets `status='rejected'` and the removal marker, so it only ever reduces active copies.
  `duplicates.restore_document` has no callers in services/routers/scripts. Nothing else rewrites
  `statement_import_statement_id` (grep).

## Numbers

Benchmark at `c2151c61` (`/mnt/owl-data/fin-wt/bench-runs/b-unique-final{,.log}`) **exit 0**, identical to
the `release-1-v3` baseline:
- 33/49 periods ready with no edits (67.3%)
- 33/40 recoverable periods ready (82.5%)
- **0 wrong admissions**, 0 critical-field errors, 0 duplicate ledger contributions

## Tests actually run (pytest, `CHROMADB_PORT=1 CHROMA_PORT=1`)

- New `tests/test_financial_one_active_statement.py`: **14 passed**. SQLite stands in for the constraint
  with a `before_commit` hook that refuses exactly the deferred constraint's condition and raises the same
  SQLSTATE and constraint name. The race is reproduced deterministically: the loser's first writer attempt
  reads as if the winner had not committed.
  - A control test shows that without the guarantee the stale writer admits a **second** copy (the b-gate finding).
  - With the guarantee: the loser returns the winner's receipt and writes nothing, and its runs are
    completed/aborted/completed with 12/0/0 rows. The batch worker records `already_present`, and a rerun
    is a no-op. A different request gets a 409. A writer that keeps losing gets a 409. Other integrity
    errors are not swallowed. Restore and recovery mappings give a 409.
  - Also tested: model DDL equals migration DDL, single alembic head, SQLite omits the constraint, upgrade
    lists every offender and adds nothing, upgrade/downgrade statements.
  - Mutation check: with `active_statement_conflict` forced to False, the 4 losing-writer tests fail.
- Targeted run of 24 modules (the new module, batch import finalization/history/lock-PG, checkpoint B gate,
  cross-case and pending duplicates, documents, duplicate decisions, duplicates, exports, import batches,
  import removal, recovery preparation (+PG), review recovery, runs, statement import (+router, andrews,
  card, merrick), statement recovery, saved statement recovery): **615 passed, 20 skipped (PG), 2 failed**.
  - Both failures are in `test_financial_recovery_preparation`
    (`test_concurrent_recovery_winner_invalidates_older_preparation_without_duplicate`,
    `test_retained_reading_without_processed_status_does_not_loop`, `DetachedInstanceError` on
    `EvidenceFile`).
  - They fail identically on an untouched `git archive` of `58a63dfc`, so they predate this unit and were
    not investigated.
- The checkpoint B gate module (12) is inside that run and passed.
- The full financial suite and the frontend were not run (no frontend change).

## Unproven without PostgreSQL

Four new PG tests were appended to `tests/test_financial_batch_import_lock_postgres.py`, in the existing
style: opt-in via `LOUPE_TEST_LOCAL_POSTGRES=1`, the fixture hard-asserts `127.0.0.1:55434/loupe_local`,
and each runs in a disposable schema. They **skip cleanly here and have never executed**:
1. The constraint exists as `contype='x'`, deferrable and initially deferred.
2. A second active copy is refused at commit with a 23P01 that `active_statement_conflict` recognizes.
   Insert-then-supersede commits. A removed copy and a different statement id coexist.
3. A real-constraint loser in the batch worker gives `already_present`, one active copy and 12 payments.
4. The migration refuses existing duplicates (listing both ids), then applies, then downgrades.

Only their row-cloning helper was smoke-run, on SQLite. Also unproven:
- that PG accepts the DDL semantically (expression immutability, btree `=` on uuid/text, the partial
  predicate in an EXCLUDE);
- that psycopg exposes `sqlstate`/`diag.constraint_name` exactly as assumed (they are documented psycopg 3
  attributes);
- that the existing `test_two_workers_confirm_once_and_keep_first_durable_outcome` still holds with the
  constraint present;
- the migration's run time and lock under live load (ACCESS EXCLUSIVE for a ~1k-row index build).

## Needs Neil

1. **A disposable PostgreSQL on 127.0.0.1:55434** (same ask as b-gate) to run the PG files. Without it, the
   PG rows above stay unproven. Recommendation: run both `*_postgres.py` files before deploying this migration.
2. Before the deploy that runs `alembic upgrade`, nothing else is needed: the upgrade refuses cleanly with
   the offender list if the data changed since 18:40.

---

# Previous unit on this base: b-gate notes (unchanged)

# b-gate: U5 / checkpoint B gate (headless session, 2026-10-02)

Branch `fin/b-gate`, based on `fin/release-1` head `6335e4e8`. Nothing pushed. No services,
live databases or case data touched.

## What landed

| Commit | What |
|---|---|
| `541b15b9` | **Defect fixed.** After a standalone save, the case's batch list ("N statements ready to import", `GET /batches/list`) still said 0 while every other view said ready. `refresh_file_readiness` skipped items it could project without a PDF read, so their stored status never changed. It now stores every item of the touched period whose readiness record is not current. Gate tests for save once, ready everywhere. |
| `55a0797c` | Gate tests: independent edits across statements and batches, plus simultaneous saves. No code change. |
| `fdd4946f` | **Defect fixed.** Existing drafts saved before `541b15b9` stayed "0 ready" in the list for good. Neither the background readiness sweep nor `refresh_batch_readiness` repaired them; only "refresh statements" (a full re-preparation) did. `refresh_case_readiness` and `refresh_file_readiness` now share `_store_current_readiness`. Gate tests show all three update paths are repeatable. |
| `43181a34` | **Defect fixed (hardening).** Three simultaneous group confirmations each created their own import job for the same statements. This reproduced 3/3 on SQLite. The frontend sends a fresh random `request_id` per click. `queue_import` now claims statements with a conditional `UPDATE ... WHERE status IN ('ready','attention')` and refuses (409) if any claim fails. On PostgreSQL the batch row lock already serialises these, and behaviour there is unchanged. Gate tests for exact set, exactly once. |
| `1ca60a6c` | **Defect fixed (pre-existing on base).** The batch list ignored the read-time overlap and duplicate holds: two readings of one account and period showed "2 ready" in the list and 0 in the batch. Import refused them correctly, so nothing wrong was admitted. New `project_list_items` runs the list's importable items through the batch detail's projection (stored readings only, no write). |

## Gate table

All tests are in `backend/tests/test_financial_checkpoint_b_gate.py` (12 tests) unless named otherwise. The database is SQLite throughout.

| Property | Test | Result |
|---|---|---|
| One standalone save → ready in batch detail, opened batch statement, batch list, case file list, individual review | `test_one_standalone_save_makes_the_period_ready_in_every_view` | **PASS** after `541b15b9`; failed before (list said 0) |
| One batch save → ready in all five views | `test_one_batch_save_makes_the_period_ready_in_every_view` | **PASS** |
| Draft saved before the batch existed → ready when the batch is prepared | `test_draft_saved_before_the_batch_existed_is_ready_when_the_batch_is_prepared` | **PASS** |
| Batch list and batch detail agree when read-time holds apply (overlapping readings) | `test_batch_list_applies_the_same_overlap_hold_as_batch_detail` | **PASS** after `1ca60a6c`; failed on base (2 vs 0) |
| Independent edits on different statements and batches all kept; same file in two batches follows the shared save; a stale editor is refused, not allowed to overwrite | `test_independent_edits_to_different_statements_and_batches_are_all_kept` | **PASS** |
| Simultaneous saves of different statements: neither lost | `test_simultaneous_saves_of_different_statements_never_lose_either` | **PASS on SQLite** (both accepted, 5/5 runs; serialised by SQLite, not PG row locks) |
| Existing-draft upgrade via background sweep: ready everywhere, three repeats byte-identical | `test_background_readiness_sweep_upgrades_existing_drafts_repeatably` | **PASS** after `fdd4946f`; failed before |
| Same via `refresh_batch_readiness` | `test_batch_readiness_refresh_upgrades_existing_drafts_repeatably` | **PASS** after `fdd4946f`; failed before |
| Same via refresh statements + worker | `test_refresh_statement_list_upgrades_existing_drafts_repeatably` | **PASS** (passed before too) |
| One confirmation imports exactly the eligible set (ready + ready-after-save; not blocked, not skipped); repeat → same job; second click → refused; re-confirm after import → receipt, no new rows; later fix → only that one imports | `test_group_confirmation_imports_exactly_the_eligible_set_once` | **PASS** |
| Concurrent confirmations (2 request ids + repeat) → one job, exact set, imported once | `test_concurrent_group_confirmations_queue_one_job` | **PASS on SQLite** after `43181a34` (fails 3/3 without it, passes 5/5 with it) |
| Worker stopped after the ledger write → rerun records `already_present`, no second import | `test_worker_interrupted_after_the_ledger_write_imports_once_on_rerun` | **PASS** |
| Two workers writing the same accepted statement at once → one ledger entry | `tests/test_financial_batch_import_lock_postgres.py::test_two_workers_confirm_once_and_keep_first_durable_outcome` | **UNPROVEN** (PG only). On SQLite this produces a second source document. Exactly-once rests entirely on the `Case ... FOR UPDATE` lock in `_write_statement_import`, with no database uniqueness constraint behind it. |
| Standalone save racing a group confirmation, without losing edits (PG) | `test_standalone_save_and_group_confirmation_serialize_without_losing_edits` (same PG file) | **UNPROVEN** (not run) |
| No item/evidence application deadlock (PG) | `test_concurrent_save_cannot_form_item_evidence_application_deadlock` | **UNPROVEN** |
| Removal after admission, no resurrection (PG) | `test_removal_after_admission_commits_before_finalizer_without_resurrection` | **UNPROVEN** |
| Recovery preparation under PG locks (6 tests) | `tests/test_financial_recovery_preparation_postgres.py` | **UNPROVEN** |
| Concurrent `queue_import` under the real PG lock order (batch lock, item `FOR UPDATE`, then the new conditional claim) | none exists | **UNPROVEN**, no test written |
| Item final status and job receipt outcomes when workers finish concurrently (PG batch and operation row locks in `_import_item` / `record_outcome`) | none on SQLite (lost updates are a SQLite artefact) | **UNPROVEN** |
| Saves and queue acceptance with the existing audit triggers (plan §2 says "in PostgreSQL with existing audit triggers") | none | **UNPROVEN** |

**PostgreSQL availability.** Loopback 55434 is **not listening**. The listeners are 5432 and 5434, both behind `docker-proxy`. I treated those as live or shared and did not connect. The PG test fixture also hard-asserts `127.0.0.1:55434/loupe_local`. No PG test was executed this session.

## Numbers

- Statement benchmark at `43181a34` (`/mnt/owl-data/fin-wt/bench-runs/b-gate-final{,.log}`), exit 0. The results are identical to the `release-1-v3` baseline:
  - 33/49 periods ready with no edits (67.3%)
  - 33/40 recoverable periods ready (82.5%)
  - **0 wrong admissions**, 0 critical-field errors, 0 duplicate ledger contributions
  - `1ca60a6c` only touches the list route, which the benchmark does not use, so it was not re-run.
- Batch list timing on the U1 synthetic harness (group=4, after refresh, median of 3), before → after `1ca60a6c`:
  - 250 items: 0.06 s → 0.24 s (`batch_status` 0.26 s)
  - 1000 items: 0.18 s → 1.50 s (`batch_status` 1.41 s)
  - The old list claimed 250 and 1000 ready where the batch said 1.

## Tests actually run

- Gate module: 12 tests OK, run repeatedly (5 or 6 times for the concurrent ones).
- Final combined run at `1ca60a6c`: 38 modules, **Ran 659, FAILED (failures=2)**. Both failures are in `test_financial_unassigned_statement`. They fail identically on the untouched base `6335e4e8` (checked by swapping `import_batches.py` back), so they predate this unit and were not investigated further.
- Earlier per-commit runs: 315 OK, 331 OK, 143 OK.
- The full 5544-test financial suite was **not** run (the box is shared; targeted runs only).
- The frontend is unchanged and was not run.

## Unverified / notes for the next session

- Every PG-only row in the table above.
- `scripts/financial_refresh_batch_readiness.py --dry-run` still counts only items held as pending, not stale stored summaries of the `fdd4946f` kind. The real run fixes both.
- After deploy, the first sweep writes a readiness record once for every active item that lacks one. Writes are bounded by the sweep's 20 s budget per pass.
- Not a gate defect: two **byte-identical** synthetic copies built by the test fixture (cloned text and geometry, bypassing intake) both show as ready in batch detail. On import the second fails cleanly ("already has imported transactions") and only one ledger copy exists. In the benchmark, the real-pipeline exact copy is held at preparation (1/1).

## Needs Neil

1. **A disposable PostgreSQL on 55434** (or say which existing instance may hold throwaway schemas) to run the PG suite and close the UNPROVEN rows. Recommendation: run the two existing PG files as they are, then add one PG test for concurrent `queue_import` with distinct request ids.
2. **Decision, recommended yes:** add a database uniqueness guarantee for "one active admitted source document per evidence file and statement key". Today only the Case row lock prevents a second ledger copy when two workers race (this was demonstrated on SQLite). What would argue against it: legitimate superseded or replacement chains, which would need a partial index that excludes `superseded`.
