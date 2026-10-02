# c-merrick: Merrick card statements become ready without edits

Branch `fin/c-merrick`, based on `fin/release-1` (64db6a5f). Not pushed, not merged.

## What landed

| Commit | What |
|---|---|
| `3a1d9a52` | New `services/financial/closing_only_period.py`. A Merrick statement reading now carries `period_dates`: `period_end` = the printed statement date, and `period_start` taken from the previous statement only when the source shows it. The batch initial request fills only the dates the printed header left empty. Admission names the specific reason when the start is held. At import, the start is stored as `derived` (end `printed`) only if it equals the start re-derived from source in the same transaction. When a file with Merrick statements is prepared, Merrick items in the batch that were held waiting for their previous statement (and have no saved edits) are prepared again. |
| `290a5fb2` | Review panel: empty period dates are pre-filled from `period_dates` and are not counted as detail edits. Adds the batch-order test (later statement prepared first: held, then ready). |
| `5c9cd297` | Exports `closing_only_period_dates` (required by the package-surface guard). |

### Rule for the start date (all conditions must hold)
- The same full card number (13 to 19 digits). A partial `****` reference never qualifies.
- An earlier statement whose closing date is 27 to 35 days before this one. There must be exactly one such closing date, and no other statement for the same card may close in between.
- The earlier statement's printed **New Balance** exactly equals this statement's printed **Previous Balance**. Both are read from the activity-summary cells, and a value whose dollar sign was not read is never used. Exact copies of the previous statement must agree with each other.
- Start = previous closing date + 1 day. Card billing cycles are contiguous, so this is a fact taken from source documents, not arithmetic on rows.
- Otherwise the start stays empty with a hold code and message: `no_previous_statement`, `several_previous_statements`, `balance_unreadable` or `balance_mismatch`. The blocker stays in the `dates` category, and the existing "start not printed" decision still works.
- The evidence (previous file and statement, both balance cells) is kept in `statement_import_original.period_dates` on the source document.

### Design decisions (each with what would reverse it)
- **`period_dates` sits outside the review revision**, like `printed_closing_date_iso`. Putting it in `metadata` would have changed the statement revision of every existing Merrick review and invalidated saved work. The derived start also depends on other files, which must not churn this file's revision. Reverse if Neil wants the derivation bound into the revision.
- **No request field marks the start as derived.** The frontend builds its request from an explicit field list and would drop such a flag. The server decides provenance at import by comparing the submitted start with its own re-derivation, in line with "provenance is computed, not asserted". A start the investigator types keeps the existing treatment (recorded as `printed`; that is unchanged behaviour, see open points).
- **Cycle window 27 to 35 days.** Monthly cycles vary with month length and closing-day shifts. A skipped statement would make the gap at least about 55 days. Reverse if real Merrick data shows other cycle lengths.

## Numbers (benchmark, synthetic corpus v2)

| | Before (release-1-merged) | After (`290a5fb2`, run `bench-runs/c-merrick-final`) |
|---|---|---|
| Ready without edits | 25/49 (51.0%) | **27/49 (55.1%)** |
| Recoverable ready | 25/40 (62.5%) | 27/40 (67.5%) |
| Merrick ready | 0/5 | 2/5 |
| Merrick "dates" holds | 5 | 1 |
| Human actions, one statement at a time | 73 | 62 (Merrick 20 → 9) |
| Human actions, grouped | 51 | 51 |
| Wrong admissions | 0 | **0 (exit 0)** |

The benchmark database confirms the two admitted Merrick periods are 2021-04-26 to 2021-05-25 and 2021-05-26 to 2021-06-25, each with start `derived` and end `printed`.

The other Merrick periods are held for reasons outside this unit:
- `merrick-two-statements#1` (closes 2021-04-25): the corpus has no earlier statement, so it is correctly held with `no_previous_statement`. It is still one grouped "start not printed" decision. The ground truth calls it `auto`, but no source in the corpus establishes its start.
- `merrick-2021-07`: no holder is printed. That is a genuine decision.
- `merrick-2021-08`: OCR misread amounts that still add up (cancelling errors). That is a reading problem; its start *is* derived from 07.

## Tests actually run
- `tests.test_financial_closing_only_period`: 14 tests, OK (new; rule cases, database read → assess → import provenance, revision stability, removed previous file, typed start, batch order refresh).
- merrick, merrick_reading_quality, statement_import, statement_admission, bulk_statement_details, pending_duplicates, periods: **218 OK**.
- import_batches, batch_review_save_scope, statement_review_checks: **93 OK**.
- exports, review_upgrade, statement_information, statement_overlap, statement_progress, statement_row_assignment, unassigned_statement, saved_statement_recovery, closing_only_period: 211 run. The exports failure was fixed in `5c9cd297` (re-run: 22 OK). **2 failures in `test_financial_unassigned_statement` also fail identically on base 64db6a5f** (exported base tree in /tmp), so they were not caused by this work and were not fixed here.
- Frontend: `tsc -b` 0, eslint 0 on both changed files. `StatementImportPanel.test.tsx`: 67/67 pass with `--testTimeout=60000`. With the default 5 s timeout, 3 to 26 tests time out depending on box load (load average about 11.7; 2 of them also time out in the release-1 baseline log). The new pre-fill test passes.
- The full backend financial suite was **not** run (shared box; only targeted modules).

## Unverified / open points
- **Performance on live data, not measured.** Each Merrick statement read queries the case for files whose text contains `MERRICK BANK`, then reads those files' catalogs. A process-level memo (512 entries, keyed by file, text hash, engine job and currency) means each file is parsed once per process, but the query runs on every read. List reads do not reach this code (`read_statement_import` only), but any path that re-reads many statements does (U1's `comparison_sources`, if still present). Worth timing on the live Merrick case with a read-only probe.
- **Stale readiness across files.** If the previous statement is later removed or changed, an item already stored as ready keeps that state until its own inputs change. Import is still safe: the start is re-derived at confirm, and if it no longer matches, the batch request's start is treated as an investigator-entered date. That last part is a provenance weakness only for items whose stored request (not the initial request) carries an auto-filled start. Items without a saved request use the fresh initial request at import.
- Only the Merrick layout is covered. Other closing-only layouts would need their own corroborating balance cells.

## Needs Neil
1. **Is `previous closing + 1 day`, corroborated by a printed balance match, acceptable as "source evidence" for admission?** I proceeded on the basis that it is: cycles are contiguous and the balance match excludes a missing statement. It is stored as `derived`, never `printed`, so continuity checks do not treat it as printed. If not acceptable, revert `3a1d9a52` lines in `initial_request`; the printed closing date would still be useful on its own.
2. **A start typed by an investigator is still recorded as `printed`.** That is existing behaviour, not changed here. Arguably it should be a separate "investigator" source; that needs an enum or schema change.
3. **The benchmark ground truth calls the first Merrick statement `auto`,** but nothing in the corpus establishes its start. Consider re-labelling it `decision` or adding an earlier statement to the corpus.
