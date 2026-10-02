# U0 backend triage — WIP notes (2026-10-02)

Env: system pip blocked by Debian typing_extensions; used a venv with
--system-site-packages + bootstrap pins + python-dotenv + pytest.

## Done (each commit's module re-run green)
- d4a9725b exports (22): 22 new 29-Sept modules registered in services/financial/__init__.py (code).
- e69ce5f7 statement_review_checks (2): review_arithmetic KeyError 'id' on id-less rows, from d9a04e8a (code).
- 60a50f42 identity_graph_integration (5): pytest.mark.skipif ignored by unittest -> unittest.skipUnless; now 5 skips (test harness).
- a7916723 statement_import_scotiabank (2): legacy seeding via confirm_legacy; 62f7db3a admission gate is deliberate (test).
- 32af0139 statement_row_assignment (1): typed balance exception no longer bypasses reconciliation by policy -> confirm_legacy (test).
- acf382a2 batch_review_save_scope (1) + import_batches (1): expect batch_review_revision token from a48958e0 (test).
- 5a4a03b1 pending_duplicates (1): save_review refused restored duplicates (stored status lags restore); now refuses only while decision is current 'ignored' (code + test).
- import_batches: only 1 failure reproduced in isolation (baseline said 3); module now OK.

## Open (not fixed — product decision)
- unassigned_statement (2): after assigning orphan continuation-page rows, the destination
  cannot reconcile because the orphan page's printed Ending Balance (a balance row) is not
  reassignable (only transaction/unresolved rows move). 62f7db3a reconciliation gate then
  blocks 'ready'. Predates 29 Sept. Recommend: let assignment carry balance-control rows
  from the orphan page (or allow investigator-entered closing balance); else update fixture.

## Next
- Full suite run was in progress (log /tmp/u0out-root/full.log); record counts.
  Expected: 2 failures (unassigned_statement), skipped=17.
