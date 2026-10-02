# U1 batch read performance - notes (fin/u1-batch-read)

Status: code complete on branch, not pushed, not deployed. Coordinator owns the workfile.

## Commits
- ac9e51f9 synthetic timing harness `backend/scripts/financial_batch_read_benchmark.py`
- 54bec6f7 BBVA `norm` cache + ASCII fast path; `attach_upgrade` serialises the snapshot once
- 743fac52 stored-projection batch reads + write-side refresh + sweep + Server-Timing/X-Request-ID (was WIP)
- bfdd3025 refresh hooks on every input-changing write; JSON copy instead of deepcopy
- 8829e5fe equivalence tests vs frozen pre-change implementation (`tests/financial_legacy_batch_read.py`)
- fc4b1b83 backfill command `backend/scripts/financial_refresh_batch_readiness.py` (not run on live)

## Timings (synthetic SQLite, box load avg 10-18, so +/-2x noise)
| scenario | before | after |
|---|---|---|
| legacy 250 (needs re-read, like live) | 19.6 s median, 250 PDF reads | 0.39 s, 0 reads (items held) |
| legacy 250 after write-side refresh | n/a | 0.71 s, 0 reads; refresh itself 25 s once, in worker |
| current 250 | 0.39-1.6 s | 0.8-1.3 s (A/B interleaved: no regression) |
| legacy 1000 | 68.6 s, 1000 reads | 3.1 s held / 3.3 s after refresh |
| current 1000 | 1.8-9.2 s | 3.8-4.8 s |

## Test baseline (targeted modules) unchanged
Pre-existing, before and after: import_batches test_incomplete_progress (1), batch_review_save_scope (1),
pending_duplicates test_batch_only_correction (1 error), unassigned_statement (2), recovery_followup (3, pytest),
exports (22). No new failures. New: test_financial_batch_read_stored (7 tests) passes.
