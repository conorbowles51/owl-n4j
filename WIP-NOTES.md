# r1-monex-citi — WIP notes (real wave 1)

Counts and opaque ids only. Private detail (per-statement diffs, dev tools, logs) is under
`/mnt/owl-data/fin-real/` (see "Private artefacts" below).

## Landed (branch fin/r1-monex-citi, based on fin/release-1 6b812436; not pushed)

| Commit | What |
|---|---|
| f6d62f4a | Monex reader fitted to the real layouts (landscape "Estado de Cuenta \| Banco" and portrait "CUENTA VISTA"), one period per currency section, movement tables, merged-cell splitting, JPY in whole units; truth tool reads yen sections; harness `--readings`; synthetic Monex corpus files regenerated from the real structure |
| 0d7bff3b | New Citi card reader (`citi-card`): multi-cycle PDFs, amounts owed, summary-component checks, two-line entries, split totals, printed-zero quiet-cycle proof |
| (this commit) | WIP-NOTES.md (this file) |

## Before / after

Real, verified truth, Monex/Citi/Kapital subset (79 documents), wave-0 engine readings reused
(`--readings`, backend-only change), truth = my corrected copy `fin-real/truth-r1mc-full`:

| | before (wave 0) | after |
|---|---|---|
| Monex ready without edits | 0 / 167 (160 not detected, 7 currency) | **171 / 171** (truth now has 171: +3 yen sections, +1 EUR period verified) |
| Citi ready without edits | 0 / 46 (not detected) | **45 / 46** in the subset run; the 46th (a quiet cycle) is ready in the full run after the printed-zero proof |
| Kapital not detected | 5 | 5 (different code path, listed for wave 2) |
| Subset ready | 4 / 227 | **220 / 231** (subset run before the quiet-cycle proof) |
| Wrong admissions (subset) | 0 | **0** |
| Critical-field errors in saved rows | 0 (52 rows) | 0 (1,257 rows from 271 periods) |

Independent field-by-field check (private `compare/r1-monex-citi/<doc>.json`, proposal vs verified truth):
Monex 70 documents, 171 / 171 periods exact (opening, closing, start date, account, every row's date, amount,
direction and running balance, no row issues). Citi 2 documents, every verified cycle exact including posting
dates; the one cycle with unverified truth (d9b89251845be#14 and its copy) was checked by hand against the page
text: the truth reader missed 9 purchases; the processor's reading agrees with every printed control.

Live disagreement **de45aa4468c66#1** (Monex pesos): now read correctly — opening, closing and all 7 printed rows
equal verified truth (was: mis-read opening, no rows).

**Full real benchmark** (all 485 documents, code 0d7bff3b, wave-0 engine readings reused, truth
`fin-real/truth-r1mc-full`, out `fin-real/bench/r1mc-full`, exit 0):

| | wave 0 (e07ff7bd) | after (0d7bff3b) |
|---|---|---|
| Ready without any edit | 484 / 761 (63.6%) | **701 / 765 (91.6%)** |
| Recoverable ready | 484 / 760 | **698 / 762** |
| Wrong admissions (scored) | 0 | **0** |
| Critical-field errors in saved rows | 0 (10,484 rows) | **0 (11,689 rows from 964 periods)** |
| Valid-looking wrong values proposed | 0 | 0 |
| Monex | 0 / 167 | **171 / 171** |
| Citi | 0 / 46 | **46 / 46** |
| Kapital not detected | 5 | 5 |
| Other families (BBVA 333, Capital One 116, Intercam 22, Kapital 4, Santander 9) | — | unchanged |
| Blocking reasons | not_detected 212, currency 31, ... | currency 24, reading 15, no_activity 13, balance 10, not_detected 6, ... |
| Batch items matched to no truth period | 102 | 37 (all Andrews, none offered) |
| Unscored periods admitted (not judged) | 116 | 122 (Andrews 101, Capital One 15, Citi 6) |
| Duplicate ledger contributions | 1,691 | 2,133 (+442: the exact copy of the Citi PDF; see "Not done") |
| Exact copies held automatically | 3 / 145 | 3 / 145 |
| Actions per 485 statements (single / grouped) | 2,645 / 2,493 | 2,215 / 2,087 |

The 6 unscored Citi admissions are the 3 cycles with unverified truth in each copy (#14, #23, #33); all three
were checked by hand against the page text and every printed control (the truth reader missed 9 purchases in
#14 and was confused by the rewards column in #23/#33).

Synthetic (regression, `bench-runs/r1-monex-citi-monex` and `-citi`): **104 / 124** (was 102), recoverable
104/107, 0 wrong admissions, 0 critical-field errors, held kept out 10/10, all 4 Monex periods ready.

## Tests actually run

- After the Monex commit: 332 targeted financial tests OK (3 skipped); Monex/no-activity/scaffold/truth OK.
- After the Citi commit: 451 targeted financial tests OK (3 skipped): every `test_financial_*` module matching
  statement_import, mexico, ownership, statement_currency, real_truth, benchmark, review_checks, exports, catalog,
  no_activity, admission (includes the new `test_financial_statement_import_citi`, 6 tests, and the rewritten
  `test_financial_statement_import_monex`, 16 tests).
- The full financial suite (~5,740) was NOT run in this unit.

## Decisions taken (each reversible in one place)

1. **Monex zero lines**: a movement line with no credit and no debit (interest net of its tax) is not a payment and
   its balance columns are not used (real statements print junk balances on such lines; the section's printed
   totals, table endpoints and every payment's running balance already fix the period). Reverse: re-enable the
   "line without a credit or debit changes the total balance" hold in `_propose_table`.
2. **Monex pages without a readable table** are accepted between two correctly numbered pages (a blank page
   printed only with its number); the review already lists such a page as needing a coverage check, and in the
   landscape layout every currency the peso summary lists must have its own section. Residual risk: a portrait
   statement whose currency section sits on a page the engine could not read would lose that period silently (it
   would not be admitted wrongly). Reverse: remove the `blank` branch in `_runs`.
3. **Monex merged cells**: when the six amounts of a line come from one merged cell, their printed order decides
   credit/debit (positions inside a merged cell are only estimates); a swap is caught by the printed totals and
   running balances. Exactly placed cells must also agree with the column headings.
4. **Citi dates are month first** (the layout prints its own billing period MM/DD/YY); a single-date line may
   resolve up to 31 days before the cycle start (payments posted on the previous closing day print in the next
   cycle). Reverse: narrow `start - timedelta(days=31)` in `_card_line`.
5. **Citi quiet cycle**: all six Account Summary movement components printed and read as zero, plus equal
   balances, prove no activity (shared printed-zero-totals proof with cited cells). Reverse: drop
   `citi_no_activity_evidence` from `statement_import.py`.
6. **Truth correction (private, not committed data)**: the tier-A truth reader skipped yen sections and counted
   yen in hundredths; fixed in `real_truth.py` and regenerated for the 71 Monex documents into
   `fin-real/truth-r1mc-full` (the shared `fin-real/truth` was NOT modified, other wave-1 units write to it).
   Ids changed for 3 documents (d33e6d1cf7cae, d379b1439fac3, db207f0acf6f6: a JPY period is now #1/#3).

## For the integration session

- Adopt the truth fix on the integrated truth directory (do not copy my directory over, t-visual-v10 writes
  there too). From `backend/` on the integrated branch:
  `PYTHONPATH=/mnt/owl-data/fin-wt/headless/real/pylib <venv python> -m benchmarks.statement_automation.real_truth --inventory /mnt/owl-data/fin-real/inventory.json --out /mnt/owl-data/fin-real/truth --cache /mnt/owl-data/fin-real/cache/words --jobs 2 --only $(cat /mnt/owl-data/fin-real/tmp/r1mc/monex-ids.txt)`
  (71 Monex document ids, private file).
- The harness now accepts `--readings <engine-readings.json>`: a full real rerun of backend-only changes can reuse
  `fin-real/bench/wave0/engine-readings.json` (engine reading was ~4 h of the 8 h wave-0 run). Only valid while
  the evidence engine is unchanged.

## Not done / for later units

- **Kapital, 5 verified periods not detected — different code path (Kapital product reader), wave 2.** Diagnosis:
  in d63b5a3d2220c the USD product section's row scope runs into the following "INVERSIÓN A PLAZO" block, whose
  "Moneda MN" adds a second currency, so the section is skipped (same shape likely for d2504121bb171#2,
  d3bf407c464a5#2, db3c05858cf3e#2); d0b014c25cde1 is not recognised at all (7 unclassified pages, cause not
  investigated).
- **Exact copies**: the second Citi document is an exact copy of the first (46 duplicate periods); both are now
  read, and the copies are offered for import like every other family's copies (duplicate ledger contributions
  in the subset run: 445). Holding them belongs to r1-reproduced (identical-transaction overlap = duplicate
  set-aside).
- **Truth holder for Monex landscape covers is the address line**, not the name (pdfplumber merges the name with
  the marketing text beside it). Affects only simulated corrections (a spurious "holder edit"), not readiness or
  wrong-admission scoring. Fix in `real_truth._monex_holder` in a truth unit.
- Citi cycles without a "Page 2 of N" page (a one-page cycle) are not recognised; none exist in the real set.
- The landscape/portrait Monex readers were validated on 70 real documents of 3 holders; a Monex investment
  ("inversiones") section with a non-zero balance has not been seen (Saldo total vs Saldo vista mismatch is held).

## Decisions needed from Neil

None for this unit's code. (Open live decisions in STATE.md are unchanged; de45aa4468c66#1 can now be corrected by
re-reading it once this code is deployed.)

## Private artefacts (`/mnt/owl-data/fin-real/`, mode 700)

- `truth-r1mc-full/` corrected full truth copy; `truth-r1mc/` subset manifest (Monex/Citi/Kapital).
- `bench/r1mc-before`, `r1mc-a1..a4` (subset runs), `bench/r1mc-full` (full run).
- `compare/r1-monex-citi/<doc>.json` per-statement field diffs (Monex 70, Citi 2).
- `tmp/r1mc/`: dev tools (`dev.py` sources/catalog/read/why/unres, `compare.py`, `citi_unres.py`), text dumps, logs.
