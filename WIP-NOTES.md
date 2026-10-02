# c-mx-noactivity — WIP notes (headless, 2026-10-02)

## Landed (branch fin/c-mx-noactivity, from fin/release-1 1c840355; nothing pushed)
- 537af44b — source-proven no-activity for Santander, Kapital, Monex and Scotiabank.
  - New `services/financial/statement_printed_no_activity.py` (`zero_totals_evidence`, method
    `printed-zero-totals-v1`, basis `printed_zero_totals`). Proof requires ALL of: exactly one opening and one
    closing balance, readable, equal; a printed deposit total and withdrawal total each read exactly `0`
    (Scotiabank: the five printed activity-chart amounts, re-read from the page and cited with locators);
    period dates printed; review currency == printed section currency; no payment candidate; family guard passes.
  - Family guards: Santander = lines in printed order opening / column heading / TOTAL / closing, heading and TOTAL
    adjacent on one page, no dated line in the section. Kapital = no CONCEPTO/FOLIO/movement heading, no Total line,
    no day+folio line in the product section. Monex = no line starting with a date on the currency summary page
    (on top of the catalog's existing whole-contract movement refusal). Scotiabank = catalog checks + chart re-read.
  - Admission (`statement_admission.source_proves_no_activity`): proof additionally bound to its cited zero-total
    rows (must stay excluded with balance 0) and its currency. Editing any cited balance/total/period date/currency
    → basis falls back to the investigator. `no_activity_basis` = evidence `basis` (Andrews unchanged: `source_verified`).
  - Anything short of proof returns `verified=False` with a specific reason/message (controls_missing,
    control_unreadable, totals_not_zero, endpoints_differ, period_dates, currency_differs, dated_line,
    rows_between_heading_and_total, section_lines, movement_table, payment_line, chart_unreadable).
  - Exported `zero_totals_evidence` from `services/financial/__init__.py` (exports guard).

## Numbers (corpus v4, OMP_THREAD_LIMIT=1, exit 0; run /mnt/owl-data/fin-wt/bench-runs/c-mx-noactivity-full)
- All: 65/124 (52.4%) → **76/124 (61.3%)** ready w/o edits; recoverable 65/107 (60.7%) → **76/107 (71.0%)**.
- v1–v3 subset: 37/49 → 37/49 (unchanged). v4 additions: 28/75 → 39/75.
- Safety: 0 wrongly admitted, 0 critical-field errors (237 saved from 76 periods), held kept out 10/10.
- Per family (before → after, ready w/o edits): Santander 3/8 → 7/8 (only remaining = the must-hold missing-page
  period); Kapital 2/4 → 4/4; Monex 0/4 → 2/4 (remaining 2 = not_detected, see below); Scotiabank 0/4 → 3/4
  (remaining = with-movements layout, currency block, no reader); Intercam 1/1 unchanged. All other families identical.
- Mexican-only subset runs (same code): before /mnt/owl-data/fin-wt/bench-runs/c-mx-noactivity-sub-before (6/21),
  after c-mx-noactivity-sub-v1 (17/21). Subset corpus copy: bench-runs/c-mx-noactivity-subset-corpus (corpus unchanged).

## Tests actually run (live .venv python, CHROMADB_PORT=1 CHROMA_PORT=1)
- New tests.test_financial_mexico_no_activity: 19 tests OK (positive proof + held variants + edit-binding per family).
- Targeted set, **Ran 377, OK**: mexico_no_activity, statement_import_{scotiabank,monex,kapital,santander},
  andrews_no_activity, statement_admission, admission, admission_gate, exports, bulk_statement_details,
  batch_review_summary, import_batches, statement_checks, saved_statement_recovery, benchmark_corpus.
- Not run: full backend suite, frontend (no frontend change).

## Decisions taken (reversible)
- No "SIN MOVIMIENTOS"-style printed-phrase route: no family in code, tests or corpus prints such a phrase, so there
  is nothing to anchor a specific pattern to. Reverse by supplying a real page that prints one.
- Equal balances are required in every case (the brief's "printed zero totals AND equal balances").
- Monex detection NOT changed: a contract with any movements page still fails closed for every currency
  (monex-2024-04 stays not_detected, 2 periods). Admitting the zero USD section beside an unread peso movements page
  would trust a movements layout the corpus invented (a-corpus2 notes). Reverse with a real Monex movements page.

## Unverified
- Layouts for Santander/Kapital/Monex were modelled by a-corpus2 from reader code, not real documents; guards may
  hold real quiet sections that print extra lines (e.g. interest or average-balance lines inside a Santander
  section) — that fails safe (held), but the live yield is unmeasured.
- Single full benchmark run.

## Needs Neil
1. Confirm printed zero totals + equal balances count as source proof (basis `printed_zero_totals`), as
   a-corpus2 recommended. This branch implements yes.
2. Monex contracts with a movements page: keep failing closed (current) until a real page is seen?
