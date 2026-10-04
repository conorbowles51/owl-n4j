# c-mx-layouts — WIP notes (headless, 2026-10-04)

Branch `fin/c-mx-layouts` from `fin/release-1` 73cbc888. Nothing pushed, nothing merged.

## Landed
- **78acd7b5 — benchmark pairing fix (harness only, first commit as required).**
  `harness._score` now returns `(content score, currency match)`. Currency only breaks ties, so it can never
  outweigh period end, share or row amounts. A section whose currency is misread therefore still pairs by its
  rows and is still reported as `currency_wrong`. Pairing is factored into `harness.pair_truth()`.
  3 unit tests in `tests/test_financial_benchmark_corpus.py` (`PairingTests`). No corpus change.
- **c4c8c58a — Scotiabank and Monex movement-table readers: SCAFFOLD, off by default.**
  Switch `LOUPE_FINANCIAL_MX_MOVEMENT_SCAFFOLD` (new module `statement_movement_scaffold.py`, exported).
  Default off: a movement table still refuses the Scotiabank statement and the whole Monex contract, exactly as
  before. **Both layouts were invented by a-corpus2** (modelled on the zero-activity readers, not on real
  statements). `processing-capabilities.md` and `bank-layout-acceptance.md` say these tables must not be labelled
  supported by extrapolation, and this change does not do so. No fail-closed rule is relaxed while the switch is off.
  - Scotiabank (new layout id `scotiabank-mexico-movements`). Requires:
    - the complete three-page frame, with one "Detalle de tus movimientos" heading directly over the six column
      headings, every dated or movement-like line inside that table, and no unplaced cell;
    - chart-line Saldo inicial/final equal to the summary lines;
    - printed Depósitos and Retiros as the credit and debit totals, with interest, fees and taxes printing exactly
      zero, so that those two totals are the whole activity.

    Admission is unchanged: it checks the rows against the closing balance, both printed totals and the running
    balance.
  - Monex: a summary with nonzero totals is accepted only when the very next numbered page is that same currency's
    "Movimientos <label>" table, and that page holds nothing else (contract line, heading, five column headings,
    dated rows, footer). Quiet sections in the same contract keep their existing printed-zero proof.
  - Rows whose amount or columns cannot be placed become unresolved payments, so the period is held. They are never
    dropped.
  - Wiring: `statement_import.py` (asset balance, dispatch, snapshot key `scotiabank_movements_scaffold_v1`),
    `statement_currency.py` (Mexican issuer), `statement_review_checks.py`.

## Numbers (corpus v4, OMP_THREAD_LIMIT=1)
| Run | Ready w/o edits | Recoverable | v1–v3 | Wrong admissions | Exit |
|---|---|---|---|---|---|
| release-1-w4 (old baseline) | 93/124 | 93/107 | 37/49 | 0 | 0 |
| c-mx-layouts-harness (pairing fix only) = **corrected baseline** | 93/124 | 93/107 | 37/49 | 0 | 0 (inferred: 0 wrongly admitted) |
| c-mx-layouts-off (c4c8c58a, switch off, default) | 93/124 | 93/107 | 37/49 | 0 | 0 (captured) |
| c-mx-layouts-scaffold-on (c4c8c58a, switch on) | **94/124 (75.8%)** | 94/107 | 37/49 | 0 | 0 (captured) |

Run dirs: `/mnt/owl-data/fin-wt/bench-runs/c-mx-layouts-{harness,off,scaffold-on}`.

- Pairing fix: per-period outcomes are identical to release-1-w4. Monex 2024-03 #1 now pairs with MXN and #2 with
  USD, where before they were crosswise. False `currency_wrong` went 2 → 0, and "valid-looking but wrong values
  proposed" went 2 → 0. The ready numbers do not move: the defect only affected scoring.
- Switch off: per-period identical to the corrected baseline (status, can_import, proposal checks).
- Switch on: the only change is scotiabank-2024-06-with-movements, attention → ready. Its 4 rows were saved, with
  301 → 305 saved rows overall and 0 critical-field errors.
- monex-2024-04 (both periods) stays not_detected even with the switch on. The engine reads that invented page with
  its tight columns merged ("Fecha Concepto", "Abonos Cargos Saldo", "22,500.00 24,645.50"). I deliberately did not
  split merged cells: placing those amounts in a column would mean guessing from geometry, and taking the direction
  from the balance arithmetic would mean the printed column was never read. The quiet USD section of that contract
  also stays refused, because the contract's refusal is all-or-nothing (c-mx-noactivity's decision, unchanged).

## Tests actually run (live .venv python, CHROMADB_PORT=1 CHROMA_PORT=1)
- `tests.test_financial_benchmark_corpus`: Ran 9, OK.
- New `tests.test_financial_mexico_movement_scaffold`: Ran 11, OK. Covers:
  - the switch parsing;
  - both readers refusing while the switch is off;
  - Scotiabank and Monex reconciling with all four checks `matches`;
  - a misread amount caught by closing, debit-total and running checks;
  - 10 Scotiabank and 6 Monex refusal variants (fee line nonzero, missing total, summary/chart disagreement, header
    changed, dated line outside the table, unplaced cell, missing page, negative total, merged header, wrong-currency
    heading, extra row, missing movement page, quiet section with activity but no page);
  - double-amount and merged-cell rows becoming unresolved;
  - the zero layout unchanged when the switch is on.
- Targeted set of 22 modules, run twice (switch off and switch on): **Ran 477, 1 failure** each time. The failure
  was the exports guard (the new module was not exported). After the fix, exports + scaffold: Ran 19, OK in both
  switch states. The 22 modules: bulk_statement_details, admission, admission_gate, batch_review_save_scope,
  batch_review_summary, benchmark_corpus, exports, import_batches, mexico_movement_scaffold, mexico_no_activity,
  statement_admission, statement_checks, statement_currency, statement_import, statement_import_{bbva,kapital,monex,
  proposal,santander,scotiabank}, statement_review_checks, saved_statement_recovery.
- After the exports fix, the same 477 re-run with the switch off (committed state): **Ran 477, OK** (rc=0).
- Not run: the full backend suite, and the frontend (no frontend change).

## Unverified
- Both movement readers are fitted to invented layouts. A real Scotiabank statement with movements almost
  certainly differs: more pages than "PAGINA 1 DE 3", continuation tables, OCR'd summary column (the real
  zero-activity sample's summary amounts are often unread). The scaffold fails closed on all of those, so it would
  hold rather than admit, but its real yield is unmeasured (likely zero until fitted to a real page).
- The Scotiabank scaffold was exercised on the digital corpus page only. No image-only or degraded movement page
  exists in the corpus.
- One benchmark run per configuration.
- Workfile (`docs/financial-workflows/automation-workfile.md`) not edited, to avoid conflicts at integration. The
  integrator should close the "Benchmark pairing" open defect (fixed in 78acd7b5) and quote the corrected baseline.

## Needs Neil
1. **Real samples.** One real Scotiabank statement with movements and one real Monex contract with a movements
   page are the only way to validate or rework these scaffolds. Until then keep
   `LOUPE_FINANCIAL_MX_MOVEMENT_SCAFFOLD` off in production (the default). I recommend not quoting the switch-on
   94/124 as a release number: the extra period exists only because the reader was written against the same
   invented layout it is scored on.
2. Corpus question (no change made): the invented Monex movements page prints columns so tight that the engine
   merges them, and the invented Scotiabank layout counts a fee row under Retiros while printing Comisiones cobradas
   $0.00. Both are artefacts of invention. Once real pages exist, regenerate those two corpus files from them.
