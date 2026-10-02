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
