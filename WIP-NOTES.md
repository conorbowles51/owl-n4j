# r9-import-ops — WIP notes (counts and opaque ids only)

Neil's directive unit, continuation of r7-import-ops / r8-import-ops (item 3 of the seven was unfinished) and this
wave's step-removal unit. Branch `fin/r9-import-ops` from fin/release-1 cf932651. **Not pushed, nothing deployed, no
live write**: every live access was a READ ONLY transaction (`financial_reader_recovery_estimate.read_only`).
Private detail: `/mnt/owl-data/fin-real/tmp/r9io/` (probes, cost runs, run log, compare-final), real run
`/mnt/owl-data/fin-real/bench/r9io-final`, synthetic `/mnt/owl-data/fin-wt/bench-runs/r9-import-ops-{a14c9808,42775cc8}`,
frozen code `/mnt/owl-data/fin-wt/bench-code/r9io-{a14c9808,42775cc8}`.

## Landed

| commit | change |
|---|---|
| 9d3bc234 | item 1: `queue_save.sweep_save` — statements that become ready after their file's preparation, or whose automatic save failed, are saved as System by the batch worker's readiness round; harness runs the same sweep, imports its claims, reports `saved_by_sweep` |
| a14c9808 | items 2+3: the import writer adds the balance controls after the ledger snapshot's flush (source document written once after insert, not twice); one "Financial import timing" log line per import with every read and write step, SQL statements/writes and row-version reuse counts |
| 42775cc8 | item 1 cost: the sweep reads open statements through `row_versions.RowValues` (summaries decoded only for rows whose PostgreSQL row version changed) |

## Item 1 — step removal: ready after preparation is saved with no click

- `sweep_save(factory)` runs in `run_batches_forever` right after `refresh_stale_readiness` (every
  READINESS_SWEEP_SECONDS = 60 s). For each (batch, file) with open statements it runs the preparation-end save
  `_auto_save_once` unchanged: fill of automatically confirmed details as System, `save_statements(only_reconciled=True)`
  (same checks, same copy rule, actor System), switch `AUTO_SAVE_READY`.
- Only files prepared with automatic save on: preparation now marks the batch file entry (`AUTO_SAVE_MARK = 'auto_save'`,
  set in `advance_batch` after `_review_file`). Files prepared before this code carry no mark, so the existing backlog
  stays the explicit action ("Save all ready" / `scripts/financial_save_ready_backlog.py`), as the module's rule said.
  Reverse in one place: drop the mark check in `sweep_save`.
- A statement with a draft or saved review (an investigator's edit) is never saved by it (same `fully_reconciled` gate).
- Two workers: claims are compare-and-set under the existing case/batch/item/evidence locks; the loser gets the 409
  "saved meanwhile" or a lock error, saves nothing, and the next round looks again. A file whose open statements are
  unchanged since the last look is skipped (per-process signature); statements whose stored readiness already shows a
  check are not re-read.
- Live, READ ONLY count (2026-10-17): 1,046 statements ready in open batches of 6 cases, 1,042 with no check and no
  edit, **0 in a marked file** (expected: the mark is new). After a deploy the sweep therefore saves none of them; see
  decision 1.

**Counts**
- Synthetic (product default, 42775cc8 and a14c9808 identical): **108 / 125 ready, 0 wrong**, 108/108 saved by the
  system, **3 saved by the sweep** (was 105 / 125 at wave 8). The 3 are `decision` periods with the holder not printed
  (credit-one, generic-labelled, merrick); the system filled the holder from the case's automatically confirmed proposal
  (the same `field_proposals` fill the preparation-end save does) once the account's other statements were saved; all 3
  holders equal truth. Recoverable 105/108 (unchanged), holds 10/10, copy 1/1, copies offered/saved 0, critical 0,
  no safety failure (exit 0).
- Real whole set (`bench/r9io-final`, code a14c9808 frozen, wave 8's 703 documents frozen, `--readings bench/wave8`,
  product default): **1,252 / 1,397 ready (89.6%), 0 wrong**, 0 critical-field errors (19,074 rows / 1,262 periods),
  holds 4/4, copies held 159/165, **copies offered 0, saved 0**, duplicate ledger contributions 0, no safety failure
  (exit 0). **1,252 / 1,252 saved by the system** (wave 8: 1,250 / 1,252). Against bench/wave8 by truth id: **0 lost,
  0 gained.** **52 saved by the sweep**, all `auto`, all scored, in 4 files (citi 49, bbva 2, mt-bank 1): exactly the 4
  preparation-end automatic saves that failed on a SQLite database lock in this run (log), recovered in 2 sweep rounds.
  Statements that became ready only through the readiness refresh (45 pending -> 0 in 16 rounds): none needed a save
  this run (0 newly saveable).
- **"Save all ready" presses removed**: synthetic 1 press per case queue (covering 3 statements); real whole set 1
  press (covering 52 statements; at wave 8 the 2 left ready also needed one press). Live after deploy: one press per
  case each time a file's save fails or a statement becomes ready later; now 0.

## Item 2 — writes of one import (benchmarks/statement_import_cost.py, 217 periods, SQLite, load ~9)

Harness now counts SQL statements, rows and bound bytes per table for each import, and gives every period one
receipt (as the automatic save claims a file). Before = 9d3bc234, after = a14c9808, 5 imports each:

| per import (warm) | before | after |
|---|---|---|
| SQL statements / reads / writes | 53 / 42 / 11 | 52 / 42 / 10 |
| rows written | 13 | 12 |
| source document row: insert + updates | 1 + 2 (84 KB rewritten) | 1 + 1 (42 KB) |
| first import of the file (catalogue on the row) | 313 KB inserted + 626 KB rewritten | 313 KB + 313 KB |
| bytes bound, all writes | 552-558 KB | 510-516 KB |
| seconds per import | 0.82-2.83 | 0.72-1.82 |
| of which the write steps (account .. commit) | n/a | 0.03-0.17 |

Still not proportional (single JSON columns; splitting them is a schema change = migration, not done):
- the file's duplicate decisions (`financial_duplicate_dispositions`, ~360 KB at 217 periods) are rewritten when THIS
  period's decision changes. In the cost harness that happens because it edits rows (signature changes); an unedited
  automatic save writes no evidence-file row at all (verified on the synthetic overlap fixture).
- the receipt's outcome list (one entry per claimed period, ~46 KB at 217) is rewritten by each import.
- The time of an import is in its reads (accept read 0.16-0.69 s, writer read 0.17-1.0 s, duplicate decision
  0.22-0.54 s including the case comparison), not its writes.

## Item 3 — live figure

- Every import now logs: `Financial import timing (item <8-char id>, <outcome>): total N s: claim, accept_read,
  writer_locks, writer_read, existing_check, case_comparison (nested in duplicate_decision), duplicate_decision,
  checks, write_account, write_source_document, write_period, write_transactions, reconcile, commit, run_record,
  graph_request, own_readiness, writer_rest, record_outcome; sql N, sql_writes N, rows_reused N, rows_reread N`
  (`row_reads_unversioned` on SQLite). Fixed names and counts only. Switch `import_batches.IMPORT_TIMING`.
  Proven on SQLite (tests) and on the stub PostgreSQL session of the row-version tests (reuse counts reach the line).
- Live read path, READ ONLY probe on case 49494305 (opaque truth id dfc15d7fbdc2c), warm, a different period each round:

| | r8 (load ~10.5) | this unit, load 12.8 | load 9.5-11.7 | **load 3.9-4.0 (quiet)** |
|---|---|---|---|---|
| read path of one import (2 period reads + existing check + case comparison + own readiness) | 2.3-3.7 s | 2.6-4.0 s | 1.6-3.4 s | **1.23-2.54 s** (1.2-1.4 s without a full GC pass) |
| case comparison | 0.8-1.0 s | 0.8-2.2 s | 0.6-2.2 s | 0.43-1.39 s (1.39 s = 0.98 s full GC pass) |
| one period read | 0.5-0.8 s | 0.5-1.2 s | 0.4-1.0 s | 0.37-0.54 s |
| existing check / own readiness | 0.04-0.1 / 0.08-0.2 s | 0.05-0.07 / 0.03-0.15 s | 0.05-0.11 / 0.03-0.17 s | 0.04-0.05 / 0.03 s |

  The case comparison reuses all 2,418 prepared rows warm (`rows_reused 2418, rows_reread 0`); its slow rounds carry a
  full cyclic-GC pass of ~1.07 s over ~0.93 M tracked objects (probe process, measured with gc.callbacks). Not changed
  here (see next unit).
- **Is < 3 s warm shown? Projected, not shown end to end.** Quiet box (load ~4): warm read path 1.23-2.54 s. The writes
  were measured on SQLite only (write steps 0.03-0.17 s, plus claim, run record and outcome ~0.03-0.1 s); a live write
  was not made. Projected warm import of one period of the 217-period file: ~1.4-2.8 s, under 3 s in every measured
  round; under load 9-13 the read path alone reached 4.0 s. The first live import after a deploy prints the true
  end-to-end figure in its timing line.

## Item 4 — not done (finding only)

The remaining case-comparison cost when warm is dominated by full garbage-collector passes over the large long-lived
caches (readings, row values), not by SQL or decoding. A fix is a memory trade-off (e.g. gc.freeze after cache
warm-up in the worker, raising the gen-2 threshold) and was not made in this unit.

## Tests actually run

- New: tests/test_financial_sweep_save.py 10 (ready after preparation saved once as System; failed automatic save saved
  next round; locked round retried; unchanged file not re-read; two workers save once; investigator draft not saved;
  file prepared with the switch off left alone; switch off; byte copy and printed copy becoming ready saved once, the
  other shown set aside), tests/test_financial_import_timing.py 6, harness drain_sweep_save 2.
- Targeted: queue_save, import_batches, auto_save_copies, benchmark_harness, exports, reader_release 178 OK; timing,
  row_versions, batch_import_finalization, import_batches, sweep_save, auto_save_copies, exports 138 OK; sweep_save 10 OK
  after 42775cc8.
- Full financial suite (CLAUDE.md command, live .venv, CHROMADB_PORT=1 CHROMA_PORT=1, working tree at a14c9808 plus the
  42775cc8 edit): **Ran 6,453, failures=2, skipped=20** — only the 2 known unassigned_statement failures.
- Frontend: no frontend file changed; not run.

## Unverified

- PostgreSQL-only paths (row-version reuse in the sweep, two workers under real row locks) ran on SQLite and the stub
  only; there is no local PostgreSQL.
- The real run of record is a14c9808; 42775cc8 changes only how the sweep reads its candidates (same selection; tests
  and the synthetic run on 42775cc8 identical).
- End-to-end live import time (needs a live import; the timing line will report it).

## Next unit

- Read the first live "Financial import timing" lines after deploy: if total > 3 s, the steps say where.
- Item 4 (GC passes over long-lived caches) if the live line shows the case comparison above ~1 s.
- Duplicate decisions and receipt outcomes as per-period rows would make every write proportional; schema change.

## Decisions for Neil

1. **The live backlog of 1,042 ready, unedited statements (6 cases) is not saved by the sweep** (their files were
   prepared before this code, so they carry no mark); it stays one "Save all ready" press per case or
   `financial_save_ready_backlog.py`, as the existing rule says. Reverse: drop the mark check in `queue_save.sweep_save`.
2. **A `decision` period whose missing fact the system can confirm later is saved by the sweep** (synthetic: 3 holders
   not printed, all equal truth), exactly as at the end of preparation. Reverse: in `queue_save._auto_save_once`,
   skip the `_prepared_entries` fill when `stored_checks` is set (the sweep's call).
