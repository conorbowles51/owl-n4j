# WIP notes: r7-autosave (fin/r7-autosave, base e066836b = fin/release-1 2089d9fd + workfile)

Counts and opaque ids only. Private detail: /mnt/owl-data/fin-real/tmp/r7as/ (live audit scripts and output,
import-turn replay), /mnt/owl-data/fin-real/bench/r7-autosave (real whole set), bench-runs/r7-autosave-*.

## Landed (commits on fin/r7-autosave, not pushed, not merged)

| commit | what |
|---|---|
| 86b2e3bd | tests: auto-save default OFF in `tests/__init__.py` (both runners), conftest.py removed; 8 interactive modules exported |
| f944288b | financial: a byte copy uploaded separately is set aside as a linked copy, never shown as saved (statement_import lineage rule) |
| 3dfc8a24 | benchmark: product default (auto-save on) measured; System saves count as ready; ledger counted per saved statement; exit 1 on any copy |
| a801e8de | financial: prepared files re-prepared automatically after a reader release (reader_release.py); both refresh buttons removed |
| 2f740350 | benchmark: drain outlasts a stale batch lease (SQLite lease race explained), pauses on quiet turns |
| 5b9e2f90 | financial: the release sweep re-prepares every changed file of a batch together; release replay script |
| 90f2d762 | financial: reader stamp leaves out import_batches.py |
| 229197f7 | benchmark: "saved twice" = the truth's same printed statement (a copy is its original), not equal values |

## Item 1: "auto-save saved an exact copy" (integrate-6 finding), established from source and the run database

- What actually happened (bench-runs/real-wave6-autosave-on/benchmark.db, read-only): the ledger held the period
  ONCE (105 admitted statements, 354 rows; the harness reported 106 / 359). The copy's batch item read `imported`
  pointing at the ORIGINAL's source document, so the harness counted those 5 rows twice and the copy was never set
  aside. No second contribution reached the ledger.
- Mechanism: `read_statement_import` finds an earlier import by file bytes (sha256) case-wide, so a separately
  uploaded byte copy took the original's import as its own (`current_import`), was assessed `imported`, and never
  reached the duplicate decision. Auto-save made it visible: the original is saved at the end of its own
  preparation and imported (next turn) before the copy is prepared. The same happens without auto-save to any copy
  uploaded in a LATER batch (pre-existing).
- Fix (f944288b): an earlier import is the file's own only within its reading lineage (`source_lineage.lineage_id`).
  A separate upload goes through the duplicate decision: `duplicate_ignored`, basis `identical_bytes`, linked to the
  saved statement, as the import writer already decides under the case lock.
- Defence in depth: the import writer already refuses a second contribution (re-runs the duplicate decision under
  the case lock; coverage duplicate hold; one-active-statement constraint on PG). Proven by tests (two claims racing,
  byte copy and printed copy in other bytes). `save_statements` already held same-bytes+key claims in flight.
- Tests (tests/test_financial_auto_save_copies.py, 6): later-batch byte copy and original-imported-before-copy
  FAIL on f234fa56 ('imported' != 'duplicate_ignored'); one-turn, side-by-side batches, two racing claims (x2) held
  already on f234fa56 (reported honestly: the writer was already safe).

### Counts
- Synthetic, copies saved by auto-save: before (old code + new harness, bench-runs/r7-autosave-before) 1 copy shown
  as saved, exit 1; after 0, copies 1/1, exit 0 (bench-runs/r7-autosave-final at 2f740350 and r7-autosave-final2 at
  229197f7, the final gate).
- Duplicate ledger contributions (rows through a second saved statement of the same printed period): before 0
  (the reported 5 were the double count), after 0.
- Live (READ ONLY, all 5 cases, 1,304 saved statements, 417 saved by System): same bytes saved twice 0; same printed
  period (account + dates + both balances) saved twice 0 (108 periods lack printed dates or balances and cannot
  establish equality; a first count without that filter showed 7 spurious groups). Copies saved by auto-save live: 0.
- Live, the pre-existing mislabel: 396 batch items in ONE case read `imported` through another upload's import (all
  byte copies uploaded separately, 0 by System, 328 flagged duplicate at upload). The ledger holds each once. A
  repair would touch those 396 batch items only (status `imported` -> set aside as linked copy); no source document
  or ledger row. After this branch deploys, opening such a copy's individual review shows it not saved (the writer
  sets it aside if imported). Re-preparation does NOT change them (prepare_reviews keeps imported items): a one-off
  repair is a live write -> Neil.

## Item 2: harness

- Product default measured (auto-save ON); `FINANCIAL_AUTO_SAVE_READY=0` still works for comparison.
- Synthetic (reusing wave-6 engine readings): auto-save on 105/125 (105 saved by System), recoverable 105/108,
  holds 10/10, copies 1/1, duplicate contributions 0, 0 wrong, exit 0. Off: 105/125, 1/1, 0, exit 0.
- Exit 1 now on: wrong admission, printed period saved twice, copy offered/saved/shown saved (`safety_failures`).
- Drain bounded by progress (STALL_TURNS 40 and STALL_SECONDS 420), not by turns.
- Import turn count (2,711 vs 658): NOT slower imports (33.5 s/import vs 34.5 s). The wave-6 run database ended with
  the batch owned by no worker but leased 5 min past its last write: advance_batch's heartbeat runs extend_lease in a
  thread that cancellation does not stop; on SQLite (no row locks) a renewal can commit after the release, and every
  turn for 5 min then does nothing (the harness spun ~1,660 empty turns). PostgreSQL serialises renewal and release
  on the batch row: no product slowdown, no product change. (If ever wanted: a compare-and-set lease update.)

## Item 3: rank 7 (refresh steps removed)

- reader_release.py: stamp of READER_MODULES (one list) + REVIEW_MODEL + proposal VERSION, recorded per batch file at
  preparation; sweep every 120 s from the batch loop (never a GET), 25 files / 20 s per round, resumable (stamps).
  "Differs" = the current reader's reading of the file differs from what its statements store (statement set,
  reading revision, review model). Unchanged files only get the stamp. Left alone (counted): nothing open, saved review
  conflict, unreadable. Switch FINANCIAL_RECHECK_AFTER_RELEASE / RECHECK_AFTER_RELEASE, default ON.
- Queue: statements of a file being prepared again are `rechecking`. Batch view says in plain words what runs.
- Frontend: "Refresh batch" and "Check for additional statement periods" removed; queue also polls while rechecking
  or saving. Server route refresh-statements kept for diagnosis.
- Clicks removed per batch, upload -> saved statements: before 2 buttons + 1 press per batch per release; after 0.
- Synthetic release replay (benchmarks/statement_automation/release_replay.py, auto-save on): before the release 16
  ready/saved, 109 waiting; after 105 saved by System, 20 waiting; 89 moved with no click; 81 files re-prepared,
  7 unchanged, 5 nothing open.
- Live scope of the first pass after deploy (read only): 54 review batches, 1,484 checked files, 894 to compare,
  2,903 open statements read once. The sweep runs inside the batch loop (awaited): up to ~20 s (+ one file) per 120 s.

## Item 4: test runner
- Suite (CLAUDE.md command, NO env override, head 5b9e2f90; later commits touch reader_release, its tests and the
  harness only, re-run in their modules: reader_release 9, exports 8, benchmark_harness 10, all OK): Ran 6,257, failures=2 (the 2 known
  unassigned_statement), skipped 20. (First run at f944288b: same 2 + 6 errors in test_financial_extraction_release,
  its 20 s subprocess timeout at load ~14; 4/4 alone.)
- test_financial_exports 8/8.

## Tests actually run
- Backend full suite x2 (above). Targeted: auto_save_copies 6, benchmark_harness 10, reader_release 9, exports 8,
  plus review_queue, queue_save, import_batches, pending_duplicates (222 together, OK).
- Frontend (runuser conorbowles51, VITE_CACHE_DIR=/tmp/vite-cache-conorbowles51-r7-autosave): tsc -b 0; eslint on
  changed files 0; vitest unit 2,118/2,120 (route-check limit test, known; FinancialPage load timeout, 39/39 alone).
  Browser project NOT run (the two browser test files were edited: "Refresh batch" clicks replaced by a focus
  refetch); storybook not run.

## Real whole set
bench r7-autosave (private: /mnt/owl-data/fin-real/bench/r7-autosave), code 2f740350 (+ uncommitted release_replay.py,
not on the harness path), bench/wave6's 623 documents (a private manifest of the current truth limited to them: the
45 M&T documents added since have no wave-6 reading), wave-6 engine readings reused, PRODUCT DEFAULT auto-save ON.
- First judged with the 3dfc8a24 gate: exit 1, "16 printed periods saved twice (0 rows)": all 16 were pairs of
  distinct truth periods (15 quiet sections of one member with equal account, dates and balances; 1 with one payment
  each), not copies -> gate fixed in 229197f7, run re-judged with --rescore (no re-read): **exit 0**.
- **Ready without any edit 1,146 / 1,294, all 1,146 saved by System with no click** (bench/wave6, auto-save off:
  1,146); recoverable 1,146 / 1,290; **0 lost, 0 gained** against bench/wave6 (by truth id).
- **0 wrong admissions; 0 critical-field errors in 17,940 saved rows from 1,156 statements** (= wave6-cont);
  holds kept 4/4; **exact copies held 148/151, copies saved 0, offered 0; printed statements saved twice 0;
  duplicate ledger contributions 0**; unmatched items offered 0; valid-looking wrong values 6 (currency 3, date 3),
  0 in ready periods (as wave 6).
- Per-statement compare (private, own directory, the shared one was not touched): 623 statements; periods without
  disagreement 1,289 vs 1,288 for bench/wave6 rescored against the same manifest (2 periods changed, both to fewer
  disagreements, neither ready-relevant).
- Timing: preparation (now including every import, saved by System) 835 turns, 48,294 s; group import queued 0.
  wave 6: preparation 6,718 s + import 35,164 s (+150 turns finished on a copy).
- Observation for r7-import-ops (advance_batch fairness, not changed here): with auto-save on, a turn runs queued
  imports before preparing files, and one ~67 s import of a large multi-statement file fills the 30 s turn, so file
  preparation stood still for ~2.5 h while one file's 129 automatically saved statements imported. The live branch's
  526a8950 (file-level reading cache) should shorten those imports; fairness is r7-import-ops' unit.

## Next unit
- Integration: this branch merges cleanly with the live branch except the 3 known engine files (integrate-6's open
  decision); the r7-import-ops change to advance_batch must keep the one-line reader stamp where a file becomes checked.
- Run the browser project (Chromium install) for the two edited browser tests.
- Optional, product: make extend_lease a compare-and-set update (only matters on SQLite; PG is already serialised).

## Unverified / for the next unit
- Browser tests edited, not executed.
- PG-only behaviour of the release sweep (row locks) is unexercised (SQLite tests only), like the rest of b-gate.
- The sweep blocks the batch loop while it compares (bounded). If r7-import-ops makes sweeps concurrent, move it.
- Merge with the live branch: only the 3 known engine-file conflicts (git merge-tree); my files merge cleanly.

## Decisions for Neil
1. Repair of the 396 live items shown as saved through another upload's import (live write; state only, no ledger rows).
2. Recommendation (no decision needed to proceed): keep FINANCIAL_AUTO_SAVE_READY ON once this branch is deployed
   (synthetic and real: 0 copies saved, 0 duplicate rows). Until then the live code can show a byte copy as saved
   through its original's import (ledger unaffected; live audit: 0 such items saved by System so far).
