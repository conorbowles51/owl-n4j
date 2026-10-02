# U3 shutdown hang - notes (complete)

Status: done on fin/u3-shutdown (commits 53a77ffa, 2888a653, 210c19b9 + this one).
Not deployed; nothing live touched.

Measured (real uvicorn 0.38 subprocess, hung request + stuck atomic thread):
- before (old lifespan, no uvicorn timeout): did not stop within 30s (unbounded)
- old lifespan + --timeout-graceful-shutdown only: still hangs (lifespan gather)
- after, production defaults, 2 workers: 31.0s
- after, no uvicorn timeout (watchdog only): 45.1s
- after, test bounds (2s request / 1s lifespan): 3.3s

Tests: backend/tests/test_process_shutdown.py (12, OK);
test_financial_import_batches new shutdown test passes (1 pre-existing failure on
base too: test_incomplete_progress_is_saved_but_cannot_enter_transactions);
deploy/tests/test-backend-stop.sh, test-ingestion-shutdown.sh pass; shellcheck -S warning clean.

This file can be dropped before merge.
