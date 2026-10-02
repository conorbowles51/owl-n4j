# U1 batch read performance - WIP notes (fin/u1-batch-read)

## Done (committed)
- ac9e51f9 harness `backend/scripts/financial_batch_read_benchmark.py` (synthetic only).
- 54bec6f7 BBVA `norm` cache + ASCII fast path; `attach_upgrade` serialises snapshot once (equivalence tests added).
- WIP commit (this one): stored-projection batch reads.
  - `checked_batch_items(..., reading='stored'|'targets'|'all')`; default 'stored' never re-reads PDFs.
    Needs-a-reading items use a fingerprinted `summary['readiness']` record written by the write side,
    else are held (`readiness_pending`, problem kind `readiness_pending`, reason `readiness_update`).
  - `comparison_sources` defers legacy hydration (`ReadingDeferred`), marks `unhydrated`; targets held (`comparison_pending`).
  - Write side: `hydrate_comparison_inputs`, `refresh_readiness`, `refresh_case_readiness`, `refresh_batch_readiness`,
    `refresh_file_readiness` (hooks: save_review, save_progress, worker _review_file, _import_item),
    background `refresh_stale_readiness` sweep every 60 s in `run_batches_forever`.
  - queue_import: displayed = stored, checked = validate + reading='all'. Single item GET = reading='targets'.
  - `services/financial/request_timing.py`: stage timers + `FinancialTimingMiddleware` (X-Request-ID, Server-Timing) registered in main.py.
  - test_financial_batch_read_projection rewritten for the new contract (passes).

## Measurements (synthetic, SQLite, before = 687da296 code)
- legacy 250: batch_status median 19.57 s (250 PDF re-reads, comparison_sources 17.3 s)
- current 250: 0.39 s
- legacy 1000: 68.6 s (1000 re-reads); current 1000: 1.76 s
- after change (20-item smoke): legacy 0.029 s held, refresh 0.47 s, after refresh 0.022 s, results match old counts.

## Next
- New focused tests: old-path equivalence (frozen reference impl), GET no read/no write, middleware headers, sweep.
- Run harness 250/1000 after; run targeted modules (baseline: import_batches 1 fail, save_scope 1 fail, pending_duplicates 1 error).
- Backfill CLI script (`refresh_case_readiness` per case, dry-run via `readiness_backlog`).
