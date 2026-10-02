# U2 WIP notes (fin/u2-projection)

## Done
- `backend/services/financial/graph_followup.py`: the one projection code path
  (`project_case_graph`), whole-case snapshot -> `projection.project_case` -> one Neo4j
  transaction with a `FinancialLedgerProjection` marker (digest + ledger fingerprint) as lock.
  In-process request/coalescing (QUIET 20s, MAX_DEFER 300s), exponential retry 30s..1800s,
  stale-under-lock retry, stop flag between statements, empty-plan guard, drift check over
  already-projected cases every 300s, `follow_up_status`. Ensures (case_id,key) + digest indexes
  (live Neo4j has NONE on FinancialTransaction/FinancialAccount/FinancialStatementPeriod).
  Kill switch: env `LOUPE_FINANCIAL_GRAPH_FOLLOWUP=0`.
- `statement_import.confirm_statement_import` now wraps `_write_statement_import` and calls
  `request_follow_up(case_id)` after the ledger commit (not for duplicate_ignored).
- `import_batches.run_batches_forever` runs `follow_up_round` concurrently with batch turns.
- `identity_graph`: missing payment nodes -> marker `status=waiting_for_payment_nodes`,
  per-case backoff 60s..1800s in the sweep; exceptions also back off; projection wakes it via
  `payment_nodes_changed`; `identity_graph_status` returns `waiting_for_payments`.
- Router: GET `/api/financial/ledger-graph/status?case_id=`.
- Backfill: `cd backend && python -m scripts.financial_graph_backfill --case <id>` (dry run,
  default) / `--apply` (`--force`, `--no-graph`).
- Tests: `backend/tests/test_financial_graph_followup.py` (22 pass) + fake graph
  `backend/tests/financial_fake_graph.py`.

## Status: complete (commits split; see git log)
- Identity sweep backoff tests: `tests/test_financial_identity_graph_backoff.py` (8 pass).
- Targeted run after change: 328 passed, 5 skipped, 2 failed (both pre-existing, identical to baseline).
- Timing (SQLite, synthetic 11,550 txns): snapshot+plan 7-12 s; plan = 109 statements,
  11,553 nodes, 34,652 edges. Neo4j apply not measured (no isolated Neo4j on this box).

## Previously listed as next
- Re-run targeted modules: projection, identity_graph*, account_identity, identity_projection_lock_boundary,
  import_batches, batch_import_finalization, statement_import, exports. Baseline before changes:
  import_batches 1 fail (test_incomplete_progress_is_saved_but_cannot_enter_transactions),
  exports 1 fail; identity_graph_integration 5 skipped (needs LOUPE_TEST_LOCAL_GRAPH).
- Timing on synthetic 11.5k (plan build + fake apply); Neo4j apply not measurable here.
- Frontend AccountIdentityReview text for `waiting_for_payments` (optional).
- Split into separate commits.
