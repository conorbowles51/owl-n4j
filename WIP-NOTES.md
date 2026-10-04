# c-image-fields: BBVA and Capital One image pages

Branch `fin/c-image-fields`, based on `fin/release-1` at `73cbc888` (after the wave-4 merge). This was a headless session. Nothing was pushed or merged, and the corpus was not changed.

## Landed

| Commit | What |
|---|---|
| `17c30506` | **Capital One layout marker.** The sentence "Visit capitalone.com to see detailed transactions." now matches when OCR changes only its final punctuation: a colon, semicolon or comma, or no punctuation, optionally after one space. Every word, the domain, the case and the word order must still be exact. A second marker or a continuation statement still refuse the layout, and the cycle and card heading are still required. 3 new tests, about 25 cases, most of them negative. |
| `796bbe05` | **BBVA balance labels.** Tesseract's English model has no `ó`. It read "Saldo de Operación Inicial" as `Operacidn` or `Operacidon`, and Liquidación as `Liquidaci6n`. The closing label was read correctly, so the operational basis was chosen, but its opening label was never found. `control_norm` now accepts one or two non-space glyphs, other than N, in the `ó` position of the four labels that carry one. Every other letter, plus Inicial/Final and the "/ Abonos (+)" suffix, must still be read exactly, so one label can never be taken for another. Only labels are affected; amounts are untouched. 3 new tests: 9 positive cases, 14 negative cases, and a full proposal. |
| `cc9c6224` | **Unreadable money cell reread for BBVA and Capital One.** Before this, `statement_reading_quality` did not assess these layouts, so a text-layer scan with `12,75O.59` or `$3B.74` was never offered a reread. It now assesses two kinds of page. (1) A BBVA page that prints its own period; continuation pages are not assessed. (2) A branded Capital One page with exactly one card ending and one cycle. A card interest charge's missing printed date is no longer counted as unreadable; without this, every digital Capital One page with interest would be sent for full-page OCR. `refine_statement_native_cells` gets the same two layouts. For BBVA, the target is the Cargos/Abonos cell. For Capital One, it is the Amount cell the layout cites. The Capital One reread accepts `$` and must keep the printed sign: it may supply digits only, never payment versus purchase. Every existing gate is unchanged: 6 readings, at least 4 agreeing across both dpis, no disagreement, known fields kept, unreadable count reduced, then the money-cell crop verification of every cell. `PDF_READING_REVISION` is now `bank-payment-rows-v13` (page-checkpoint stamp). As the comment in `recovery_campaigns.py` instructs, the previous `pdf_extraction.py` digest (`003d53a6…`, 41e64eca) was added to `AFFECTED_EXTRACTION_SHA256`. New tests: 7 backend, 5 engine. |

## Per period, before (release-1-w4) → after (c-image-fields-final, code cc9c6224)

| Period | Before | After | Why |
|---|---|---|---|
| bbva-2024-07 image-only | held: balance | **ready** | Opening label read through the `ó` fix |
| bbva-2024-08 skewed | held: balance | **ready** | Same as 2024-07 (`Operacidon`) |
| bbva-2024-09 OCR amount digit | held: reading 1, balance 3 | **ready** | Cell reread to `12,750.59`, 6/6 agreeing, then confirmed by the money-cell verification |
| capital-one-2025-01 OCR amount digit | held: reading 1, balance 1 | **ready** | Cell reread to `$38.74`, 6/6 agreeing, then confirmed |
| capital-one-2025-03 150 dpi + JPEG | held: reading 4, holder 1, balance 1 | **ready** | Marker with a colon is now recognised, so sections and holder are found |

No other period changed status or reasons. I diffed every period of release-1-w4 against the final run. Saved ledger rows for all 5 periods have 0 critical-field errors.

## Numbers (corpus v4, 124 distinct periods, OMP_THREAD_LIMIT=1)

| | release-1-w4 | c-image-fields-final |
|---|---|---|
| Ready without edits | 93/124 (75.0%) | **98/124 (79.0%)** |
| Recoverable ready | 93/107 (86.9%) | **98/107 (91.6%)** |
| v1–v3 subset | 37/49 | 37/49 (floor kept) |
| v4 additions | 56/75 | 61/75 |
| BBVA / Capital One | 3/7, 4/7 | 6/7, 6/7. The remaining one in each family is the missing-page period, which must stay held, and it is held. |
| Wrongly admitted / critical-field errors | 0 / 0 | **0 / 0**. Held periods kept out: 10/10. **BENCH_EXIT=0** |
| Valid-looking wrong values proposed | 2 | 2 |

The 2 valid-looking wrong values are the known Monex `currency_wrong` harness pairing artefact. It comes and goes between runs: it was 0 in my intermediate run `c-image-fields-full1`.

Engine read time was 410 s wall, against 313 s for the baseline. Host load differed (5–6 here) and the two runs are not comparable. The real extra work is one full-page OCR plus one 6-reading cell reread on each of the 2 digit-damaged pages.

Runs, all under `/mnt/owl-data/fin-wt/bench-runs/`:
- `c-image-fields-sub0`: BBVA + Capital One subset. It picked up the marker fix mid-run because backend modules are imported lazily.
- `c-image-fields-sub1`: subset with all fixes, 12/14 ready, 0 wrong.
- `c-image-fields-full1`: 98/124, exit 0, on uncommitted code without the revision bump.
- `c-image-fields-final`: 98/124, exit 0, clean commit `cc9c6224`.

The subset runs used a filtered copy of the manifest (`/tmp/sub-<user>-cimg`), passed with `--corpus`. The committed corpus was not touched.

## Tests actually run

- **Backend financial suite**, `discover -p 'test_financial_*.py'`, live .venv, `CHROMADB_PORT=1 CHROMA_PORT=1`: **Ran 5682, failures=2, skipped=17**. The 2 failures are the known `unassigned_statement` pair (open product decision). The baseline was 5669; the difference is my 13 new tests. This run was before the revision bump.
- **After the revision bump:**
  - `test_financial_recovery_readers` (pytest): 18 passed.
  - recovery_campaigns + pdf_processing_manifest + exports + new reading-quality tests: 21 OK.
  - `test_financial_pdf_*`: 110 OK.
- **Engine pytest**, c-image's selection plus `bbva`/`capital`, with `test_pdf_worker.py` deselected: **467 passed, 8 skipped** (462 before plus 5 new). After the bump: revision/checkpoint/manifest/bbva/capital/native selection, 65 passed.
- **Not run:** the full all-tests pattern, frontend (no frontend change), and `test_pdf_worker.py`, which has 4 pre-existing spawn failures per c-image's notes.

## Not verified / known limits

- **Descriptions on BBVA image pages are OCR text.** Examples: `SPE!`, `$39`, `SPE]`, `120` for `T20`. The harness pairs rows by description, so bbva-2024-07/08 still show `extra_row 4 / missing_row 4` in their proposal checks. Amounts, dates and directions are all correct (0 critical-field errors in the ledger). The descriptions are what OCR read from the page; nothing was invented to "fix" them.
- **BBVA image pages lose the printed movement counts** ("2", "5"). As a result the Depósitos/Retiros totals rows are not used as controls on those pages; they need the count cell. The periods reconcile on opening, closing and the running-balance chain, with every money cell crop-confirmed. Accepting a total without its count would add a control. I did not build that, to keep the change narrow.
- **Synthetic corpus only.** Real BBVA scans may misread the `ó` as three glyphs or something else; those stay held, which is safe. Real Capital One scans may damage other words of the marker; those also stay held.
- **page_controls_reconcile now claims BBVA and Capital One pages too,** because it shares `_page_statement_rows`. This lets the second-reader repair consider these pages, still under its reconcile-only gate. No benchmark period exercised it.
- **Live data was not touched.** Live sources only benefit after they are re-read (reader recovery, Neil's decision).

## Decisions for Neil

1. **The `ó` tolerance in BBVA labels.** Decided: one or two non-N glyphs in that position only.
   - Why: OCR has no `ó`, and the readings observed were `d`, `do`, `6` and `é`.
   - What would reverse it: you want an explicit list of observed misreadings instead of a pattern. Then real scans with a new misreading stay held until each one is added.
2. **Reread of the Capital One `$` cell.** Decided: allow `$` in the reread and require the printed sign to be kept.
   - Why: without `$` in the character set, a `$` can come back as a digit, for example `538.74`.
   - What would reverse it: you prefer that card cells are never reread. Revert the Capital One branch of `cc9c6224`, and capital-one-2025-01 returns to held.
3. **Deploy together.** `refine_statement_native_cells` (engine) imports the new backend functions `bbva_page_statement` and `capital_one_page_statement`.
   - What happens if the engine ships without the backend: the import fails inside the reread. `pdf_extraction` catches it ("Native statement cell reread unavailable"), so the cell reread is skipped for every layout, including Credit One, Merrick, generic and Andrews. Pages stay held; nothing is wrongly admitted, but repairs are lost.
   - Both sides are in the same repo, so ship them together and never deploy one side alone.
