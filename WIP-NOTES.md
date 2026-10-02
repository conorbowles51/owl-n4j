# c-reader2: an independent second reader for disputed money cells

Branch `fin/c-reader2`, based on `fin/release-1` at `6335e4e8`. This is a headless session. Nothing was pushed or merged.

## Landed

| Commit | What |
|---|---|
| `e6f256ba` | Backend `statement_reading_quality.page_controls_reconcile(tables)` checks whether every printed control on one page reconciles. It uses the same family dispatch as the reading check (Credit One, Merrick, generic labelled, Andrews) plus the review's own `check_statement_rows`. Andrews pages are split per share statement via `andrews_catalog`. The page reconciles only if each statement's closing balance is printed on the page and matches, no check shows a difference and no row is flagged. `assess_statement_reading` was refactored to share the dispatch (`_page_statement_rows`) with no change in behaviour. Fixture: 2 synthetic corpus pages. |
| `7bd84c16` | Engine `app/pipeline/statement_glyph_reader.py` is the glyph template reader. `statement_money_verification.repair_with_second_reader` holds the decision rule and is wired into `pdf_extraction._verify_recognised_money` after the pinned repair. The switch is `STATEMENT_GLYPH_SECOND_READER` (default on). The commit also adds the tests and the evaluation script. |
| `fdb6751b` | Andrews endpoint-balance provenance names a second-reader repair (`second_reader_repair`) and keeps the page reading it replaced. |
| `9ae81ae0` | Evaluation script records the reader's own wrong reads, plus a `--kinds` option. Committed by the coordinator from my leftover change. |

## Reader choice (decided)

I built a **glyph template matcher from the statement's own page**. There is no new dependency (numpy is already imported by the engine) and no external service. Nothing about the statement leaves the box.
- **Templates.** Templates are glyphs cut from cells where the page reading and Tesseract crop rereads agree. That means confirmed money cells, plus digit-only text such as dates and account numbers, which are confirmed by the same 6-profile crop reread (4 or more of 6, at both resolutions).
- **Reading.** A disputed cell is split into glyphs by ink columns. Each glyph takes the label of the template it correlates with best, pixel by pixel, with a ±2 px shift.
- **Why it is a different reader.** The font and scan are the same, but the method is different. It has no language model and no learned weights. The only thing it shares with Tesseract is the confirmed labels of the templates.
- **When it abstains.** It returns no reading if:
  - the ink does not split into exactly the printed number of characters;
  - a character class has templates from fewer than 2 cells;
  - any template is not recognised as its own label by the page's other templates;
  - a glyph's best score is under 0.935, or it beats the next class by less than 0.05.
- **Where the thresholds come from.** Leave-one-out reads of 1,307 confirmed corpus glyphs. A glyph's own class never scored under 0.945 and never lost. With the glyph's own class withheld, the best other class never scored above 0.920. So 0.935 separates "this is a known character" from "this is the nearest character the page happens to offer". That open-set failure is real: without the threshold, a "6" read as "8" twice when the page had no "6" templates.
- **Alternatives rejected.** onnxruntime/torch would need a model to be brought in. easyocr, paddle and cv2 are not installed. A hosted model would mean sending private case images out. None of these was built.

### Admission rule (`repair_with_second_reader`), all or nothing per page
1. Every held cell is `contradicted`: at least 4 of the 6 crop readings, spanning both resolutions, agree on one other value, they are identical character for character, and **no** crop reading supports the page reading.
2. The glyph reader reads the **whole** cell and gives exactly the crop value.
3. At every position where the page reading and the crop reading differ, the page has templates for **both** characters.
4. With all values replaced, `page_controls_reconcile` passes.

Anything short of that keeps the page held as before, with a `declined` record and a reason. A repair records, per cell: the page reading, the held text, every crop reading and the glyph scores.

## Numbers

**Benchmark (corpus v3, unchanged, `OMP_THREAD_LIMIT=1`), exit 0 on both runs:**

| | release-1-v3 baseline | c-reader2 (`bench-runs/c-reader2-final`, code 9ae81ae0) |
|---|---|---|
| Ready without edits | 33/49 (67.3%) | **37/49 (75.5%)** |
| Recoverable ready | 33/40 (82.5%) | **37/40 (92.5%)** |
| Wrong admissions / critical-field errors | 0 / 0 | **0 / 0** |
| Valid-looking wrong values proposed | 0 | 0 |
| Human actions (single / grouped) | 51 / 43 | 30 / 22 |

- **What changed.** Exactly 4 periods changed, all to ready, and every saved value is the printed one: andrews-2021-05#2, credit-one-7, generic-11 and merrick-2021-08.
- **Still held: credit-one-6.** It prints 18.79, and no 7 or 9 is printed in any digit-only text on that page, so the reader declines.
- **Still held: the other 2 recoverable holds.** These are andrews-2020-12#2 (OCR lost rows) and merrick-two-statements#1 (ground truth mislabelled). Both are out of scope.
- **Cost.** The reader runs only on pages held entirely by contradictions: 5 pages in the corpus. Each took 1.8 to 2.7 s under load (6 extra stacked Tesseract calls plus the matching).

**Glyph reader accuracy and independence** (`backend/benchmarks/statement_automation/glyph_reader_evaluation.py`; reports in `bench-runs/c-reader2-glyph-eval{,2,3}.json`):

**Clean corpus** (leave-one-out templates, money cells only):
- Confirmed cells: 122 correct, **0 wrong**, 88 abstained.
- Disputed cells: 9 of 13 correct, **0 wrong**, 4 abstained. In production, with date templates added, 11 of 13 are read correctly and only credit-one-6's 2 cells are not.

**Degraded copies of every money cell** (10 conditions: blur 0.7/1.0, 180/150 dpi, JPEG q20, faded, noise σ15/30, heavy print, 150 dpi + JPEG):
- **Independence.** Tesseract produced 176 individual misreadings that parse as money. The glyph reader gave **the same wrong value 0 times**. It gave the true value 6 times and abstained 170 times. Tesseract's majority verdict was never wrong in these runs. The reader agreed with Tesseract on a wrong value **0 times**.
- **Glyph reader's own errors.** It made 4 wrong reads out of about 640 non-abstaining degraded reads. All four were 6/8 confusions: 851.36→851.38 (×2), 1,280.00→1,260.00 and 17,428.39→17,426.39. In every case Tesseract read the true value, so the readers disagree and the page would stay held.
- **Abstention rate.** The reader abstains heavily on degraded images: about 50% at blur 0.7, about 75% at 150 dpi, 100% at noise σ30 and heavy print. It is a safe tie-breaker but a low-yield one on poor scans.

## Tests actually run (all on the final code)

- **Engine** (`pytest`, `.venv`, `OMP_THREAD_LIMIT=1`): 110 passed.
  - New: `test_statement_second_reader` (16, real rasterisation and Tesseract). It covers the repair, refusal when the controls contradict the value, the kill switch, crop and glyph disagreement, a non-majority or one-resolution crop, a tolerated single dissenting crop, missing templates, the open-set guard, a mislabelled template, an unseparable cell, and corpus Merrick-08, Credit One 7 and Credit One 6.
  - Existing: `test_statement_money_verification`, `test_generic_statement_repair`, `test_pdf_extraction`, `test_native_card_cell_ocr`, `test_merrick_automatic_repair`.
- **Backend** (`CHROMADB_PORT=1 CHROMA_PORT=1`):
  - page_controls_reconcile (6 new), generic pinned, generic and merrick reading quality, exports: 32 OK.
  - `test_financial_statement_import*`: 240 OK.
  - `test_financial_*andrews*`: 50 OK (includes 1 new provenance test).

## Not verified

- **Real productions.** All numbers come from the synthetic corpus (Helvetica rendered at 200 dpi). Real scans have mixed fonts, skew and touching glyphs. The reader abstains when glyphs touch, so real-world yield is unknown. Safety should hold because of the abstentions and the reconciliation gate, but it has not been measured on held-out real documents.
- **Full suites.** I did not run the full backend suite, frontend or vitest (the box is shared). No frontend code changed.
- **Live data.** I did not touch live data. Live periods only benefit after their sources are re-read (same caveat as c-andrews).
- **Repaired cells in the UI.** The investigator's UI does not show second-reader (or pinned) repaired cells. The page reading is kept in the engine's refinement record, and Andrews endpoint provenance now names the repair. Transaction-level provenance for repaired amounts is not surfaced.
- **Rotated pages.** Pages with a PDF rotation are declined; this is untested on real rotated scans.

## Decisions for Neil

1. **Is the second reader acceptable as independent evidence for admission?** It requires the glyph reader and Tesseract to agree on the whole value, plus full page reconciliation. I judged yes. Its errors are uncorrelated with Tesseract's on every measurement here (0 of 176). If you say no, set `STATEMENT_GLYPH_SECOND_READER=false` or revert `7bd84c16`; `e6f256ba` is harmless on its own.
2. **Relaxed crop precondition.** Unlike the pinned rule (unanimous 6 of 6), this rule accepts a 4-of-6 contradiction as long as no crop reading supports the page reading. generic-11 needed this: one crop read 89.21 against five reading 85.21. I reasoned that the independent reader plus reconciliation carry the weight. To require unanimity, make `_contradicted` demand that all 6 observations are identical (generic-11 would then go back to held).
3. **Templates from non-money digit text** (dates, account numbers), confirmed by crop reread, were needed for Andrews-05 and Credit One-7. If you would rather templates came only from money cells, those two go back to held.
4. **Should repaired cells be shown to the investigator,** with the machine reading beside the accepted value, per the design rule on corrections? That is a UI and provenance unit; it is not built.
5. **Not built: a hosted vision model.** Using one would send private case images out. I did not pursue it.
