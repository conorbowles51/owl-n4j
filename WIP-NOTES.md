# c-generic: generic-layout OCR repair (headless session, 2026-10-02)

Branch `fin/c-generic`, based on `fin/release-1` at `64db6a5f`. Not pushed, not merged.

## Landed

| Commit | What |
|---|---|
| `e2a48b6d` | Reread generic labelled statements whose money cells are unreadable |
| `13d03dbe` | Accept a disputed crop reading only when agreed printed balances pin it |

### 1. Why generic layouts got no reread (`e2a48b6d`)

`services/financial/statement_reading_quality.assess_statement_reading` decides whether a
page's embedded text merits an image reread. It only recognised Credit One, Merrick and
Andrews and returned `None` for every other page. With `None`, `pdf_extraction` never
queues the quality reread, and `refine_statement_native_cells` (the per-cell crop
reread) returns immediately. Money verification could not help either, because a damaged
cell such as `8S.13` does not parse, so it is never a verification target. Result:
generic-03 and generic-04 were held for a manual amount or balance edit.

Fix:
- The reading check has a generic labelled branch, used only when no named layout claims
  the page. Its identity is every header fact the review reads from labelled lines:
  bank, holder, account number, currency, and the period parsed to dates. OCR splits
  "Statement Period: ... - ..." into two cells, so each row is read as one printed line.
  A page with no account number and period of its own, or with no labelled payments
  table, is not assessed. Rows that fit no printed column count as unreadable payments,
  so an image reading that gains, loses or garbles a row is refused. The existing rule
  that every readable fact must be identical still applies.
- The native-cell crop reread targets generic credit, debit, amount and running-balance
  cells by their printed column.
- `printed_label` / `printed_period` were moved from `statement_import` to
  `statement_import_proposal`, so the review and the reading check share one parser.
  `statement_import` imports them under the old private names.

### 2. Held c-safety cases (`13d03dbe`)

Crop evidence recorded for every held cell (benchmark run, all six profiles):

| Case | Page reading → crop (6/6 unless noted) | Pinned? |
|---|---|---|
| generic-10 | 1,380.00 → 1,350.00 | **yes**: opening and first running balance both confirmed |
| generic-11 | 88.21 → 85.21 (5/6, one 89.21); 30,845.87 → 30,848.87; 140.20 → 143.20 | no: 3 disputed cells, 2 equations; not unanimous either |
| credit-one 6 | 28.11 → 25.11; 15.79 → 18.79 | no: the two amounts are fixed only through their sum |
| credit-one 7 | 11.11 → 17.11; 36.62 → 30.62 | no: same |
| merrick 2021-08 | 18.48 → 15.48; 100.34 → 103.34 | no: same |
| andrews 2020-09 | 1,530.00 → 1,500.00; its balance and the ending balance | no: amount, running balance and ending balance disputed together |

In every case the crops read the true value. That alone is not enough. Where the
misreads compensate, both readings reconcile, so arithmetic cannot choose between them,
and one engine agreeing with itself is not independent proof (the c-safety rationale,
which stands).

The rule adopted is a crop value is accepted only when it is **pinned**. To be pinned, a
printed control equation must contain it as the only disputed cell, and the page reading
and the crops must read every other cell of that equation identically. The control
equation is one of:
- previous balance + payment = running balance
- last balance = closing balance
- the payments in one direction sum to the labelled total

The page reading then contradicts both the image and the agreed balances. The crop
reading satisfies both. Arithmetic corroborates a value the image shows; it never
creates one.

The rule is all or nothing per page. Every non-confirmed cell must be "contradicted", not
"unconfirmed". Each must be read identically by all 6 profiles (both resolutions),
parse as money, and be pinned. The whole opening-to-closing chain must reconcile, the
page must be one table with a labelled identity, and no row may carry an issue.
Anything else leaves the page held exactly as before. Each accepted cell is recorded as
`statement_money_pinned_repair` with the page reading, held text, all crop readings and
the pinning cells.

It is implemented for generic running-balance tables only:
`statement_reading_quality.pinned_running_balance_values` (backend) and
`statement_money_verification.repair_pinned_cells` (engine), called from
`pdf_extraction._verify_recognised_money` after verification. If the repair raises, it is
logged and the page stays held.

## Numbers (benchmark, corpus v2, exit 0 every run)

| Run | Ready w/o edits | Recoverable ready | Wrong admissions | Critical-field errors |
|---|---|---|---|---|
| baseline `release-1-merged` | 25/49 (51.0%) | 25/40 (62.5%) | 0 | 0 |
| after `e2a48b6d` (`bench-runs/c-generic-reread`) | 27/49 (55.1%) | 27/40 (67.5%) | 0 | 0 |
| after `13d03dbe` (`bench-runs/c-generic-pinned`) | **28/49 (57.1%)** | **28/40 (70.0%)** | **0** | 0 |

Per-period diff against the baseline: only generic-03, generic-04 (both `image_selected`,
then `all_confirmed`) and generic-10 (pinned repair) changed, all to ready. Every other
held case is unchanged. Human actions (single/grouped) fell from 73/51 to 68/46 after
the first commit. The 3rd-run log is `bench-runs/c-generic-pinned.log`.

## Tests actually run

- Backend (`.venv` python, `CHROMADB_PORT=1 CHROMA_PORT=1`):
  - new `test_financial_generic_reading_quality` (7) and `test_financial_generic_pinned_repair` (7),
    plus `test_financial_merrick_reading_quality` (4): 18 OK.
  - `discover -p 'test_financial_statement_import*.py'`: Ran 240, OK (run after both commits).
  - `test_financial_exports`: OK.
- Engine (`pytest`, `OMP_THREAD_LIMIT=1`):
  - new `tests/test_generic_statement_repair.py`: 21 passed. Includes real-Tesseract crop
    recovery, the full extraction reread path, and real verification followed by pinned repair.
  - `test_statement_money_verification`, `test_pdf_extraction`, `test_native_card_cell_ocr`,
    `test_merrick_automatic_repair`, `test_financial_amount_ocr`,
    `test_financial_endpoint_balance_ocr`, `test_ocr_geometry`, `test_pdf_text_origin`:
    149 passed.
  - `test_financial_bbva_ocr`, `_date_ocr`, `_santander_ocr`, `_transaction_date_ocr`, plus
    the new file again: 131 passed.

## Not verified

- The full backend financial suite and the frontend were not run (the box is shared;
  targeted modules only). No frontend code changed.
- Generic statements spanning several pages: a continuation page with no labelled account
  and period of its own is not assessed, so it still gets no reread. That is
  deliberate, and the corpus has no such case.
- Live data were not touched. How often real generic productions meet the pinned
  conditions is unmeasured.

## Decisions for Neil

1. **The pinned-repair exception to "never substitute a crop value"** (`13d03dbe`). I
   judged the evidence overwhelming: a unanimous crop reading at two resolutions, plus
   printed balances that both readings agree on and that fix the value exactly. The
   compensating corpus stays held. If you want c-safety's absolute rule kept, revert
   `13d03dbe` alone. `e2a48b6d` does not depend on it.
2. **Extending pinning to other families.** None of the held Credit One, Merrick or
   Andrews cases would pass it, because their disputed cells are only jointly
   constrained. Andrews prints running balances, so a single-cell Andrews misread could be
   pinned the same way. I did not extend it, because no current corpus case needs it.
