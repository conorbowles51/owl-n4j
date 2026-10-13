# r6-synchrony — WIP notes (real wave 6) — INTERIM (whole-set run in progress)

Counts and opaque ids only. Private detail (dev tools, surveys, frozen code, run databases, per-statement
comparisons) under `/mnt/owl-data/fin-real/tmp/r6s/` and `/mnt/owl-data/fin-real/bench/r6s-*`.
Branch `fin/r6-synchrony`, based on fin/release-1 fb8abfdf. Not pushed, nothing merged, no live data touched,
no services touched. Backend only: no evidence-engine change, no reading-revision bump (wave-5 readings reused).

## Landed

| Commit | What |
|---|---|
| eea33ee0 | General engine: one-cell movement tables read line by line; side-by-side summary/payment boxes read box by box (payment box never a control); net summary lines and NEW PURCHASES; section totals as controls (proof + review-scoped fee/interest totals); year-to-date block excluded; closing date + days-in-billing-period periods with the start stored DERIVED (case-level agreement with the previous statement); pages unread only after the table's printed end; unlocated rows hold only when they could be a movement/control; holder from an own-cell postal line / payment stub; `synchrony-card` institution profile (data) |

## Measured so far

- Synchrony mini corpus (truth-mini-v17, 16 documents, 16 verified periods, v17 readings), code eea33ee0's tree:
  **ready 0/16 -> 16/16**, wrong 0, critical-field errors 0 (47 saved rows from 16 periods), rows equal to
  truth 47/47 (date, amount, direction), balances 16/16, compare 16/16 without disagreement. Stored periods:
  start `derived` / end `printed` / balanced 16/16; start agreed with the previous statement in the case 15,
  first cycle by the printed day count alone 1. Rows inverted 0.
- Engine-served 16, library-served 0 (no Synchrony library reader written: step 4 not needed).
- Generic-only (family readers skipped, profiles applied): 16/16, 0 wrong. Plain engine without the profile:
  2/16 (closing date day <= 12 in every cycle; only the two cycles whose date reads the same in both orders).
- Engine survey of all 583 truth documents (wave-5 readings), base fb8abfdf vs eea33ee0: no engine-proved
  statement lost in any family; gained bbva 1, capital-one 4, monex 1, synchrony 16; identity of proved
  statements unchanged outside Synchrony; held statements: prefilled rows on 3 (citi 2, merrick 1), hold reason
  changed on 9 (credit-one).
- Routing survey (card families + changed documents): 4 Capital One periods move from library-served to
  engine-served (library reading did not reconcile; engine reading equal to truth in opening, closing and every
  row); bbva 1 and monex 1 gain an engine/library agreement only.
- Synthetic: 105/125, recoverable 105/108, 0 wrong, 0 critical (354 rows), holds 10/10, copies 1/1, 0
  valid-looking wrong values, BENCH_EXIT=0 (rescore of bench-runs/r6-synchrony-eea33ee0).
- Whole set (583 documents, `--readings` wave5): RUNNING (bench/r6s-full, frozen eea33ee0, corpus snapshot
  bench/r6s-corpus = the same 583 documents / 1,424 periods as bench/wave5).

## Tests actually run

- New: 13 engine tests (BoxedCardTests; 11 fail on fb8abfdf, 2 are guards), 5 closing-only tests (DayCountPeriodTests).
- Engine/import/admission/review modules: 475 OK.
- Full financial suite on eea33ee0: Ran 6,107, failures 2 (the known `unassigned_statement` pair, also failing on
  fb8abfdf), errors 1 (`public_timestamp_opt_in` subprocess timeout under load; passes alone), skipped 20.

## Live (read-only question)

The investigator's two hand-entered live periods (d43853a185720#1, d7f1c8c31414c#1) are both in the mini
corpus: this code reads both ready and equal to truth (every direction right). A re-read is a live write: not
done here (open decision for an interactive session).
