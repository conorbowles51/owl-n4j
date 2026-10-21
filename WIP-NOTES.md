# r13-andrews: work notes (counts and opaque ids only)

Branch `fin/r13-andrews`, base 48e58b67 (real wave 12 integrated). Nothing pushed, nothing deployed, nothing live
written.

## Landed

| Commit | What |
|---|---|
| 19a120ce | Engine, reading `bank-payment-rows-v25`. Held money cells on Andrews pages store `recognised_readings`, which is every reading a recogniser stated: the page reading or its glyph interpretation, then each distinct crop amount. They also store `page_glyphs_agree_with_crops`: look-alike glyphs read as digits that state exactly the amount on which at least 4 crops at both resolutions agree. Money-column cells of dated payment rows that no money reading parses are cropped in a stacked call of their own and recorded under `damaged_cells` (switch `CROP_DAMAGED_MONEY`). Page text is never changed, and the other cells' crop readings are byte-for-byte what they were. The v24 `pdf_extraction.py` digest joins the reader-recovery list. |
| ef32867d | Backend Andrews reader. The whole-period pinned pass also offers recognised readings and damaged cells, and pre-pins glyph agreement (switches `RECOGNISED_READINGS`, `DAMAGED_CELLS`, `GLYPH_AGREEMENT`); acceptance is unchanged: all or nothing, exactly one reading pinned per cell by the period's own controls. A closed share section with zero opening, exact opening label and an adjacent Closed notice dated inside the period is proven no-activity (`CLOSURE_PROOF`, reason `closed_without_activity`); admission accepts a closure date inside the period. A money-less notice row is excluded as statement information when the running balance is unbroken across it (`MONEYLESS_NOTICES`). A row whose date is printed with a space inside it opens a dated money row (`SPACED_ROW_DATES`). A share number with one speck or space between its four digits is read (`SHARE_ID_SPECK`). |
| 911b2ef6 | An Ending Balance line dated with a space inside the date closes its section (under `SPACED_ROW_DATES`). |

Every rule fails closed and is switchable in one place.

## Measured

Readings: copy of `readings-v24b` with a fresh v25 read of all 5 Andrews truth documents (0 errors, 9 damaged
cells recorded, 0 crop errors). The engine code of the read is exactly 19a120ce.

Whole set, code 911b2ef6, niced, 796 documents / 1,715 periods (see Corpus note). Before = bench/wave12.

| | Before | After |
|---|---|---|
| Ready without edits (product) | 1,404 / 1,524 | **1,428 / 1,524** (+24, all Andrews; 0 lost) |
| Andrews recoverable ready | 231 / 266 | **255 / 266** |
| Andrews must-hold kept | 4 / 4 | 4 / 4 |
| Wrongly admitted (product / generic-only) | 0 / 0 | **0 / 0** |
| Critical-field errors in saved rows | 0 (22,419) | **0 (24,481)** |
| Saved holder differs (outside BBVA same-entity) | 0 | 0 (same-entity 36, all BBVA, unchanged) |
| Exact copies saved | dcfc8ce1f2afc#1 only | dcfc8ce1f2afc#1 only (offered 1, saved 1, unchanged) |
| Valid-looking wrong values proposed before review | 4 | 3 (a subset; a merrick-card date proposal no longer appears; cause not investigated) |
| Generic-only ready | 1,037 / 1,524 | 1,037 / 1,524 (identical per period; the Andrews reader is product only) |
| Other families ready (per family) | | unchanged |

Actions per 100 statements (harness simulation `_period_effort`, all 796; single / grouped):

- Against bench/wave12/results.json (the given baseline): **244.5 / 234.0 -> 214.2 / 204.4**.
- Against bench/wave12/results-rescored.json (same manifest as this run, so like-for-like):
  224.4 / 214.4 -> 214.2 / 204.4.
- Andrews family actions (absolute): 520 / 506 (results.json) or 360 / 350 (rescored) -> **281 / 272**. So this
  unit removed 79 / 78 Andrews actions; the remaining 160 / 156 of the 520 -> 281 gap was removed by the wave-12
  truth rescore, not by this code.
- Generic-only: 693.7 / 665.5 before and after.

SAFETY exit 1 in every real run (before and after) is the known saved copy dcfc8ce1f2afc#1 plus one offered copy,
both unchanged since wave 12.

Run dirs (private): bench/r13a-whole-796, bench/r13a-whole-go-796, mini run tmp/r13a/mini2.log.

## Tests actually run

- evidence-engine: 7 modules incl. the new `test_andrews_recognised_readings` (15): **201 passed**.
- backend targeted: `test_financial_statement_*` 938 OK; admission 81 OK; andrews_no_activity 49 OK; Andrews
  modules 116 OK; reading_quality 21 OK; exports 8 OK; recovery 60 OK; pytest recovery_readers 18 passed.
- Full financial suite (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): **Ran 6566, FAILED (failures=2, skipped=20)**.
  The 2 are `test_financial_unassigned_statement` (batch_records_assignment_completion..., orphan_cannot_import...),
  known before this unit; nothing of this unit touches unassigned statements.
- Synthetic benchmark (bench-runs/r13-andrews-final, code 911b2ef6): **108/125, exit 0**, recoverable 105/108, 0
  wrong, 0 critical (366 rows), holds 10/10, copies 1/1, identical per period to real-wave12. The 1 saved holder
  that differs is the known generic-v4-2025-04-scan-100dpi.pdf#1 (pre-existing).

## Unverified / not done

- Live READ ONLY audit not run this unit (nothing deployed; the live state is unchanged by construction).
- Frontend not touched, so no frontend gates were run.
- Still held on Andrews (auto truth): d0f81a5b856d7 #7 #8 #11 #12 #15, d1db0b3c9ca54 #7 #8, d892131891936 #23
  #24, da162973a4fa0 #14 #32. Blocking reasons on Andrews after: duplicate 6, balance 4, reading 4, assignment 3,
  currency 1, not_detected 1.
- Work-order item 3 (file structure: assignment / duplicate / not_detected) was not attempted. After items 1 and 2
  the target was exceeded (255 >= 245), and the time left went to the whole-set measurement, which took about 9
  hours on this host. The fresh run's reasons are the starting point.
- Why d5a3ad9b75a08#8 (merrick-card) no longer shows a valid-looking wrong date proposal was not investigated. It
  is held both before and after.

## Corpus note

The truth corpus gained a 797th document (dfc15d7fbdc2c, 220 periods, truth_complete false) at 07:27 today, after
wave 12. No stored reading exists for it, so the harness refuses the full corpus. The whole-set runs used a private
copy of the manifest with the 796 wave-12 documents (`tmp/r13a/corpus796`, 1,715 periods, same as wave 12).

## Next unit

- Andrews duplicate (6) and assignment (3) holds: page-structure cases; start from the fresh run's per-period
  reasons.
- Andrews balance (4) and reading (4): cells where no recogniser stated the printed value (no reading to pin).
- A fresh engine read of dfc15d7fbdc2c before the next whole-set bench.

## Decisions for Neil (none blocking)

- `SHARE_ID_SPECK`: a share number with one speck or space between its digits is read as those four digits;
  a comma, or a point standing in for a digit, is still not read. An older test encoded the opposite for `004.0`
  and was updated. One line reverses it.
