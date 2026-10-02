# U3 shutdown hang - WIP notes

## Findings
- journald owl-backend-v2, 2026-10-02 09:41:06 -> 10:12:36: both workers stuck in
  uvicorn's request-task phase ("Waiting for background tasks to complete"), no
  "Waiting for connections" => in-flight HTTP tasks whose connections were gone.
  Lifespan shutdown never ran (forced exit at 10:12:36 skipped it). The access log
  cannot name the request (lines are written at response start).
- Live unit has no --timeout-graceful-shutdown, so uvicorn waits forever.
- Lifespan exit then did cancel + unbounded gather on recovery / identity sweep /
  batch loops, each of which awaits an uncancellable worker thread (_finish_atomic,
  run_identity_graph_forever `await work`).
- deploy.sh restart blocked in `systemctl restart` (log ends at "Restarting services"),
  no last-good written.

## Done (uncommitted -> committed as WIP)
- backend/services/process_shutdown.py: shutdown event, signal-chained watchdog
  (hard deadline 45s, diagnostics at 25s naming pending tasks incl. request path),
  stop_background_tasks (cancel + bounded wait 10s, abandon + log).
- main.py lifespan uses it; import_batches should_stop + recovery loop + evidence WS
  loop observe shutdown_requested(). identity_graph.py untouched.
- tests/test_process_shutdown.py: 12 tests; 11 pass, describe_task innermost-await
  assertion fails (cr_await chain stops at sleep; fix the test expectation or walk).
  Uvicorn e2e: old variant never stops (>8s), fixed single worker / 2 workers stop
  within bound, watchdog-only path stops at deadline.

## Next
- Fix describe_task test; time each e2e precisely for the report.
- Add import-batch shutdown test in test_financial_import_batches.py.
- deploy: new deploy/backend-stop.sh (bounded stop: stop --no-block, wait 60s,
  journal tail, SIGINT all, 20s, SIGKILL, 10s), EXIT/TERM trap writing outcome
  block to the log; use in deploy.sh + rollback.sh; drop-in -> TimeoutStopSec=90 +
  Environment=UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=20; setup-server.sh unit same;
  update test-ingestion-shutdown.sh + README; new deploy/tests/test-backend-stop.sh;
  shellcheck.
