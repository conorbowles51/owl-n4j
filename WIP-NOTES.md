# c-andrews-residue: the last four held Andrews periods

Branch `fin/c-andrews-residue`, based on `fin/release-1` at `73cbc888` (after the wave-4 merge). This was a headless session. Nothing was pushed or merged, the corpus was not changed and no live data was touched.

All four target periods now import without a human edit. Every saved value is the printed one: the benchmark ledger check shows 0 errors on all four. Every recoverable Andrews period in the corpus is now ready (43/43). The three Andrews periods still held are meant to be: one omitted row, one missing page, and one quiet section split by a page break, which needs a person's decision.

## Landed

| Commit | What |
|---|---|
| `2ad173df` | **A held Andrews money cell takes the printed reading that its confirmed neighbours fix.** This fixes 2022-04 (150 dpi), 2022-05 (100 dpi) and 2022-08 (combined damage). |
| `3f00cf5d` | **Scans: printed lines that the embedded OCR layer left unread are read from the page image.** This fixes 2020-12 (OCR-lost lines with equal balances). |
| (this file) | Notes. |

### `2ad173df`: what was wrong, and the rule

**What the reader saw on each page:**
- **150 dpi.** The page reading had `“61.27`: the minus sign was read as a curly quote. The crop check (six rereads of each money cell from the page image) had never looked at this cell, because it only targeted text that already parses as an amount. All six crops read `-61.27`.
- **100 dpi.** The page reading had `-61.28` and `7,150.20`, and both are the printed values. Four of the six crops dropped the minus and read `7,180.20`. So the crop majority was wrong, and the earlier rules (which only ever accept a crop reading) could not have admitted this page safely.
- **Combined damage.** The minus was again read as `“`, and all six crops read `61.31` with no sign.

**The rule, in plain terms.** An Andrews statement prints a running balance on every payment. So each payment is one equation: previous balance + amount = new balance. The section also ends with one more: last balance = ending balance.
- **Candidate readings.** A held cell offers only readings that a recogniser actually produced from the print:
  - the page reading, if at least two crops (at both resolutions) also gave it;
  - the crop reading that at least four of six crops agree on;
  - for a garbled sign, the agreed digits with either sign.
- **When a reading is accepted.** All of these must hold:
  - one of those equations contains the held cell as its *only* disputed cell;
  - every other cell in that equation was confirmed by the page and the crops agreeing;
  - the equation holds with that reading, and with no other candidate;
  - after every held cell is filled, the whole page reconciles.
- **All or nothing.** It is all or nothing per page.
- **What is recorded.** Every repair keeps the page reading, the held text, all six crop readings, which reading was taken and the cells that fixed it. The opening and ending balances' record of where they came from now names this repair.
- **Compensating misreads still hold.** Two misread values that cancel each other out always share an equation, so this rule declines them. Corpus 2021-05 is that case: it still declines here and is repaired by the glyph second reader exactly as before (there is a corpus test for this).
- **Only Andrews pages.** Pages that no Andrews layout claims get no record from this rule at all.

**Code:**
- Engine: `statement_money_verification.py` has `sign_garbled_money`, `_printed_readings` and `repair_pinned_readings`. It is wired into `pdf_extraction._verify_recognised_money` after the generic pinned repair and before the second reader.
- Backend: `statement_reading_quality.pinned_andrews_values` holds the Andrews equations.
- The reading revision is now `bank-payment-rows-v13`.
- The previous `pdf_extraction.py` digest (41e64eca, `003d53a6…`) joins the reader-recovery list, following the b5ebfeb7 precedent.

### `3f00cf5d`: what was wrong, and the rule

**What was wrong.** 2020-12 is a scan carrying an invisible OCR text layer. That layer lost two printed lines, a 50.00 deposit and a 50.00 withdrawal. The checking section therefore read as 2,300.00 → 2,300.00 with nothing between. It was rightly held, because equal balances are not proof of no activity. But nothing ever read the lines that the image prints.

**Detection.** On a scan page with an OCR text layer, which a statement layout claims and which has no unreadable field, the engine renders the page once at 100 dpi. It then looks for text-line-shaped ink bands that no embedded word covers. To count, a band must:
- be 0.6 to 1.6 times the page's median line height;
- break into at least six separate ink runs, so a ruled line or a smudge does not count;
- lie between the first and last embedded word.

If any band qualifies, the page goes to the full-page image reading.
- **Measured cost and reach.** About 20 ms per page. Across all 25 text-layer scan pages in the corpus, only 2020-12 fires.

**Acceptance.** The image reading replaces the text layer only if all of these hold (`statement_reading_quality.recovers_unread_lines`):
- it is the same statement, with the same balance lines;
- every field of both readings is readable;
- every row of the text layer is present, unchanged and in the same order;
- each added row is a complete payment (date, amount, direction, running balance), and every cell of it lies inside one unread band.

If any of these fails, the text layer is kept exactly as before, and the record now notes the unread bands. An accepted image reading then goes through the normal crop check: all 10 money cells were confirmed on 2020-12. It must also reconcile downstream like any other reading.

## Numbers (corpus v4, 124 distinct periods, `OMP_THREAD_LIMIT=1`)

| | release-1-w4 baseline | after `2ad173df` (`bench-runs/c-andrews-residue-u1`) | after `3f00cf5d` (`bench-runs/c-andrews-residue-u2`) |
|---|---|---|---|
| Ready without edits | 93/124 (75.0%) | 96/124 (77.4%) | **97/124 (78.2%)** |
| Recoverable ready | 93/107 (86.9%) | 96/107 (89.7%) | **97/107 (90.7%)** |
| v1–v3 subset (floor 37/49) | 37/49 | 37/49 | **38/49** |
| v4 additions | 56/75 | 59/75 | 59/75 |
| Andrews (recoverable) | 39/46 (39/43) | 42/46 (42/43) | **43/46 (43/43)** |
| Wrong admissions / critical-field errors | 0 / 0 | 0 / 0 | **0 / 0** |
| Benchmark exit | (0) | **0** | **0** |
| Human actions (single / grouped) | 122 / 114 | 109 / 101 | 104 / 96 |

- **What changed.** In both runs, exactly the target periods changed; nothing else moved, by a per-period diff against release-1-w4. The saved ledger shows 2020-12#2: 2 rows; 2022-04/05/08#2: 5 rows each; all with 0 errors.
- **Proposals.** In the u2 run, valid-looking but wrong values proposed before review were 0 (the baseline had 2, from the known Monex pairing artefact; that harness artefact varies between runs).
- **Engine time.** Engine reading took 405 s wall in u1 and 348 s in u2, under host load around 6 that differed between runs.

## Tests actually run (final code unless noted)

**Engine** (`pytest`, live .venv, `CHROMADB_PORT=1 CHROMA_PORT=1 OMP_THREAD_LIMIT=1`):
- New and existing modules together, **162 passed**:
  - new: `test_andrews_pinned_reading` (29) and `test_unread_printed_lines` (7), which include real Tesseract runs on the four corpus pages and on 2021-05;
  - existing: `test_statement_money_verification`, `test_generic_statement_repair`, `test_statement_second_reader`, `test_pdf_extraction`, `test_native_card_cell_ocr`, `test_merrick_automatic_repair`, `test_scan_preprocessing`.
- An intermediate run had 2 failures in `test_statement_second_reader`: a declined record from the new rule appeared on generic pages. That was fixed by emitting no record for pages that no Andrews layout claims, before `2ad173df` was committed.

**Backend** (unittest, same env):
- New: `test_financial_andrews_pinned_reading` (8) and `test_financial_unread_lines` (6), OK.
- `discover -p 'test_financial_*andrews*.py'`: 58 OK (run after `2ad173df`; re-run after `3f00cf5d`, OK).
- `*reading_quality*`: 11 OK.
- `test_financial_statement_import*`: 240 OK.
- page_controls_reconcile + generic_pinned_repair + exports + pdf_processing_manifest + benchmark_corpus (+ unread_lines): OK.
- `pytest test_financial_recovery_readers.py`: 18 passed.

## Not verified

- **Real productions.** All numbers come from the synthetic corpus. Two cases in particular are untested on real scans: a real OCR layer that drops lines next to stamps, signatures or logos, and the sign look-alike glyph set (`“”„"‘’'`´~—–‒―‐‑_=`).
  - What is known: a false unread band only costs one extra page OCR; the image reading is then refused and the page is read as before.
- **Full suites.** I did not run the full backend suite, the frontend or vitest. The box is shared, and no frontend code changed.
- **The investigator's view.** The investigator's UI does not yet show cells repaired by this rule (the same gap as the earlier pinned and second-reader repairs). The page reading is kept in the engine's record, and the endpoint balance provenance names the repair.
- **Live data.** Live sources only benefit after they are re-read: the reader-recovery campaign, Neil's switch.
- **Recovery digest at merge.** If this merges after another change to `pdf_extraction.py`, then whoever changes that file next must add this branch's digest (`6d388613…`) to `AFFECTED_EXTRACTION_SHA256`.

## Decisions for Neil (each already decided; how to reverse)

1. **A sign that no reader named (2022-08).** The digits `61.31` were read identically by the page and all six crops. The page shows a mark in the sign position that no reader could read as a sign, and the printed word is "Withdrawal". I accept `-61.31` only because two confirmed balances fix it and the positive value is refused (a positive "Withdrawal" contradicts its verb).
   - Why I accepted it: the magnitude and the direction are both printed; only the minus glyph is unreadable.
   - To refuse it: drop the `crop_digits_signed_by_controls` candidate in `_printed_readings` (one `append`). 2022-08 then goes back to held.
2. **The page reading can beat the crop majority (2022-05).** This happens only when crops at both resolutions also read the page value and the confirmed neighbours fix it.
   - Why: a majority of one engine's rereads is not evidence of the print, and on this page it was wrong twice.
   - To refuse it: drop the `page_reading` candidate. 2022-05 then goes back to held.
3. **An image reading may replace an embedded OCR layer by adding lines.** It may do so only lines where the layer left printed ink unread, and only when every existing row is reproduced exactly.
   - To refuse it: remove `or unread` from the routing condition in `_extract_pdf_sync`. 2020-12 then goes back to held.
