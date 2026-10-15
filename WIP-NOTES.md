# r7-import-ops — WIP notes (counts and opaque ids only)

Neil's directive unit (2026-10-15): make large statement files import fast and safely; close the operational gaps
from the live Navy Federal production (case 49494305, truth id dfc15d7fbdc2c, live file 6e611846).
Branch `fin/r7-import-ops` from `fin/release-1` e066836b. **Not pushed, nothing deployed, no live write.**
Longer notes: `/mnt/owl-data/fin-wt/notes/r7-import-ops.md`. Private detail: `/mnt/owl-data/fin-real/tmp/r7io/`.

## Base (read before merging)
fin/release-1 lacks the live branch, and this unit is written against its import-speed commits. They are
**cherry-picked** here (`-x`, identical patches): 526a8950→b873d2e7, e8e942f8→6a2f9c8e, ae782113→87e91f30,
d966e990→ff3a9c39, 09539513→3c14259b. **fcb78072 skipped** (its engine half needs r-subpoena's engine rules, not in
this base). Merging the live branch later should see these as already applied.

## Landed
| # | commit | change |
|---|---|---|
| 1 | f6db9c0f | Statement catalogue stored once per file and digest: a saved period keeps its own choice + `statement_import_catalogue_sha256` + `statement_import_original_full_sha256`; `statement_import_original_sha256` = digest of what is stored (all integrity checks unchanged); `statement_catalogue.full_original/saved_catalogue` rejoin and prove. Backfill `scripts/financial_statement_catalogue_backfill.py` (dry run default, READ ONLY; `--apply` = live write, Neil). |
| 2 | ab276693 | One preparation per file: only the newest batch holding a file prepares it; older batches wait, then adopt (retire untouched copies to `superseded_reading`); exact fallbacks to preparing. Switch `import_batches.SHARED_PREPARATION`. Imports get half a turn while files wait; >=1 file per turn. |
| 3 | 0c9f4564 | Per-import cost: readiness depends only on relevant admissions (same statement, shared page, recovery section, retained copy; switch `RELEVANT_ADMISSIONS_ONLY`); one case comparison per import; copy guard fingerprints only what it reads; identity plan reads links from columns. Harness `benchmarks/statement_import_cost.py`. |
| 3b | 2fa38e42 | Case comparison: saved records' statement id/first page memoised per record id; account identity cached. |
| fix | efe4f832 | Found by the full suite: display_link session lookup only for account links (3 payment-inference errors from 0c9f4564); catalogue functions exported. |
| 4 | 0bc96e32 | Worker stalls = GC passes (measured). Engine reading cache pickled + 2 live; `gc.freeze()` after startup. Killed-worker lease path tested. |
| 5 | 1c9e49e2 | Deploy gate: queued imports reported, not blocking; live batch turns waited for (2 s poll, 120 s); `/health` reports `commit`/`commit_clean`; deploy.sh records a healthy clean running commit as last-good. Script sandbox tests repaired (11/12 failed on unchanged scripts). |
| 6 | 3ed7677f | The 3 failing tests: caused by the shared reading (526a8950) outliving a patched reader inside a test; tests isolate (`forget_shared_readings`). Also fixed: shared `checks` keyed on resolved currency but computed with the request's. |
| 7 | — | Navy Federal residue: analysis only (below). |

## Before / after (counts)
- Synthetic import harness, 120 periods (SQLite, load ~10-13): sweep after an import 17.0-32.3 s (re-reading 117-119
  periods) → 0.08-0.19 s (0); one import 0.6-2.3 s → 0.5-1.2 s; copy check in the import 1.0-1.6 s → 0.19 s.
- Live, READ ONLY: backfill dry run on the case: **692/694 records would be compacted, 0 fail verification**, saved
  metadata 261 MB → 96 MB. One period's reading 5.4-6.9 s today, ~5.8 s of it the two duplicate checks the backfill
  shrinks. Case comparison 7.8 s before; 3.8-8.1 s after (host load 11-21, not comparable).
- GC (live file, read-only probe): full pass 0.8 s for the app alone, 2.3-2.9 s after reading the file; engine cache
  entries 142k objects each (up to 8 before, 2 live now); freeze removes the app's ~700k objects from every pass.
- **Not measured: the live < 3 s per import target** (an import is a live write). Expect it only after the backfill,
  and the case comparison likely still dominates on this case.

## Synthetic benchmark (3ed7677f, FINANCIAL_AUTO_SAVE_READY=0 as wave 6)
`bench-runs/r7-import-ops-3ed7677f`: **105/125 ready (= baseline), recoverable 105/108, 0 wrong, 0 critical-field
errors (354 saved), held 10/10, copies 1/1, 0 unmatched; exit 0.** Real whole-set bench not run (this unit changes
no reader; reading revision unchanged).

## Navy Federal residue (item 7, read-only)
Live newest batch: 14 held; the live code re-routed on the stored reading reproduces the same 14.
- 12 lines of credit 2020-05..2021-04 (11 not_reconciled, 1 no_geometry on the redacted first statement): truth
  **unverified** for all 12 (principal-only balance; opening outstanding not printed; rows without amounts). Correctly
  held; need a person. Queue wording is generic; a precise message needs engine recognition of a principal-only line.
- Checking 2023-05-17..06-16, pages 191-193: truth verified (54 rows). Reader gap: all 53 movement lines arrive with
  date/description/amount/balance merged in one cell. Provable by the printed running balance.
- Line of credit 2023-06-17..07-16, pages 198-199: truth verified (quiet). Reader gap: "No Transactions This Period"
  and the equal ending balance are on the page after the section heading; the printed-quiet proof is not applied
  across the page break.
- Both gaps are rules in r-subpoena's engine (not in this base): not fixed here (+2 periods available).

## Tests actually run
- 47 affected modules: 875 passed, 15 skipped, 3 failed (the 3 item-6 tests, failing before item 6).
- Item 6 modules (bbva/santander/scotiabank) 44 passed; engine 137 passed; deployment 46 passed; runtime 2 passed;
  duplicate/overlap/queue/file-status/import 341 passed (after 2fa38e42).
- Full financial suite (CLAUDE.md command, `unittest discover`, FINANCIAL_AUTO_SAVE_READY=0):
  on 3ed7677f 6,287 run, 11 failures + 6 errors (3 errors mine → fixed in efe4f832; 1 failure = new module not
  exported → fixed; 3 errors in extraction_release/public_timestamp are order-dependent and also fail on e066836b);
  **on the final head efe4f832: 6,294 run, 10 failures, 0 errors, 20 skipped = the 10 known before this unit**
  (8 package-export entries for interactive modules, 2 unassigned_statement).
- Under pytest only (pass under unittest discover): test_financial_deployment_recovery (9) +
  test_financial_recovery_preparation (2), DetachedInstanceError, identical on e066836b. Not touched.

## Unverified
- Live import time after these changes (needs a live import). Live effect of the backfill (needs `--apply`).
- PostgreSQL-specific paths of the new queries (JSON path selects, catalogue holder lookup) ran only on SQLite here
  and read-only on live PostgreSQL (the backfill dry run, comparison probe, `_admitted_sources`).
- Frontend untouched (no frontend command run).

## Next unit
1. On a base with the live branch merged: the two Navy Federal engine rules (+2 periods, prove 0 wrong on the whole
   set) and principal-only line-of-credit wording for the 12 held.
2. Case comparison: batch items' summaries by columns, copy-decision context only for files that need it → live
   < 3 s per import.
3. Merge note: `fin/r7-autosave` touches the same import/queue code; `_shared_preparation` and the auto-save at the
   end of `_review_file` interact (an adopted older batch does not auto-save; the newest batch's preparation does).

## Decisions for Neil
1. **Run the catalogue backfill live** (live write): dry run, then `--apply` when no import is running. Each changed
   record gets a new integrity digest; a detail edit opened before the run asks to reload; the audit trigger records
   each update. Default: not run.
2. **Queued imports no longer block a deploy** (gate change). Reverse: put `pending_financial_imports` back out of
   `QUEUED_CATEGORIES`. A deploy that changes the reader turns queued imports of changed statements into "review the
   new reading" (fail closed), never into wrong saves.
3. **Older batches adopt the newest batch's preparation** of a shared file (`SHARED_PREPARATION`). Reverse: switch off.
