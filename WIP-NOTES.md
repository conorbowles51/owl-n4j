# c-image: reading degraded and tilted scans

Branch `fin/c-image`, based on `fin/release-1` at `1c840355` (after the wave-3 merge). This was a headless session. Nothing was pushed or merged, and the corpus was not changed.

## Landed

| Commit | What |
|---|---|
| `57613863` | New engine module `app/pipeline/scan_preprocessing.py`, wired into `pdf_extraction`. For a page that is one full-page raster image, it measures native dpi, paper and ink grey levels, and skew, then does only what those measurements show (details below). The full-page OCR, field rereads, money-cell crop check and glyph second reader all read the prepared image, which is placed on a same-size page at the same index in a separate in-memory document. Kill switch `pdf_scan_preprocessing` (default on) is passed to the PDF worker and is part of the page-checkpoint stamp. Reading revision is now `bank-payment-rows-v12`. The engine processing manifest fingerprints the new module and records the setting. |
| `1c81dc0d` | Backend `pdf_processing_manifest` validator accepts the new source inventory and an optional `pdf_scan_preprocessing` setting. Earlier records still validate. Also adds module tests. |
| `91e68aad` | On prepared scans, recognised words over blank paper are dropped (a phantom `=` was merging Andrews amount and balance columns). The contrast-stretch white point is set 10 levels below paper (JPEG halo). |
| `41e64eca` | The blank-paper filter is tightened: a word must be under confidence 60 **and** clear of ink by 4 px. Without this, a real colon on a straightened BBVA page was being dropped. |

### What preparation does (only when measured)
- **Resampling.** A scan below 200 dpi is rendered at its native dpi and Lanczos-resampled to 300 dpi. On 100 dpi pages this recovered every printed amount; MuPDF's own upscaling lost up to 2 of 5.
- **Contrast stretch.**
  - Measurement: paper is the median grey. Ink is the 5th percentile of pixels at least 30 levels darker than paper, after a 3x3 box blur.
  - Trigger: the stretch runs when paper minus ink is under 130. On the corpus, pale scans measure 88 to 107 and normal ones (including 100 dpi and JPEG) measure 167 or more.
  - How: the stretch is linear and clipped, from ink up to paper minus 10, so it never reverses the order of two grey levels.
- **Deskew.**
  - Search: projection-profile search over ±5° (coarse 0.25°, fine 0.05°).
  - Turned only if all of these hold: the angle is at least 0.2°, it is below 5°, and the rows sharpen by at least 5%.
  - Accuracy: it measured exactly -1.0, -2.5 and -1.2 on the 1°, 2.5° and 1.2° corpus pages.
- **Pages left alone.** Pages with nothing measured return `None` and are read exactly as before; all clean 200 dpi corpus scans are in this group. Rotated (`/Rotate`), blank, digital and mixed-content pages are never prepared.
- **What gets recorded.** Each prepared page records a `scan_preprocessing` refinement: steps, native dpi, levels, stretch points, measured angle and gain, plus the deskew angle and centre when the page was turned.
- **Pages that kept their embedded reading.**
  - Embedded text layer (OCR not used): if the page was turned, the crop check uses the original image, and the record says `used_for: not_used`.
  - Same frame (only resampled or stretched): the prepared image serves the crop rereads, recorded as `used_for: crop_rereads`.

## Numbers (corpus v4, 124 distinct periods, `OMP_THREAD_LIMIT=1`)

Final run: `bench-runs/c-image-final`, code `41e64eca`, **BENCH_EXIT=0**.

| | release-1-w3 baseline | c-image final |
|---|---|---|
| Ready without edits | 65/124 (52.4%) | **82/124 (66.1%)** |
| Recoverable ready | 65/107 (60.7%) | **82/107 (76.6%)** |
| v1–v3 subset | 37/49 | **37/49** (unchanged; floor kept) |
| v4 additions | 28/75 | **45/75** |
| Wrong admissions / critical-field errors | 0 / 0 | **0 / 0** |
| Valid-looking wrong values proposed | 4 | 2 (see note) |
| Human actions (single / grouped) | 277 / 251 | 148 / 124 |

On the valid-looking wrong values: the 2 that remain are both the Monex `currency_wrong` harness pairing artefact. That is a known open defect; the Monex files are digital and preparation never touches them, and run 2 had 0. Both of the baseline's other near misses are gone: the wrong date on the 1° Andrews scan and the wrong account on the 100 dpi generic scan.

**Per damage type, ready w/o edits, before → after:**

| Damage type | Before | After |
|---|---|---|
| skew | 0/10 | **8/10** |
| faint_print | 0/9 | **7/9** |
| low_dpi | 1/11 | **7/11** |
| jpeg_noise | 3/8 | **6/8** |
| image_only_scan | 10/35 | **24/35** |
| ocr_amount_digit | 3/7 | 5/7 |
| clean_scan_text_layer | 3/3 | 3/3 |

By family: Andrews went from 28 to 39 of 46 and generic from 14 to 20 of 26 (20/20 recoverable). BBVA, Capital One, Credit One, Merrick and Scotiabank are unchanged.

**Intermediate runs:**

| Run | Code | Result |
|---|---|---|
| r1 | | Crashed. The backend rejected the new manifest; fixed in `1c81dc0d`. |
| r2 | `1c81dc0d` | 79/124, 0 wrong. |
| r3 | `91e68aad` | 82/124, 0 wrong. |
| final | `41e64eca` | 82/124, 0 wrong, exit 0. |

**Cost.** Engine read wall time was 357 s on the baseline and 360 s on the final run (different host load). Prepared pages take about 1 to 1.5 s longer each, for preparation and PNG encoding.

### Degraded periods still held, and why
All of these are held, none admitted.

**Andrews** (reading disputes; holding them is the safety rules working):
- **andrews-v4-2022-04 (150 dpi) #2:** the page OCR read the minus as `“` (`“61.27`), so the amount is unreadable.
- **andrews-v4-2022-05 (100 dpi) #2:** the crop rereads contradict the page reading (`-61.28` against 4 of 6 crops reading `61.28`, and `7,150.20` against `7,180.20`).
- **andrews-v4-2022-08 combined #2:** one row is not separated.

**Other families:**
- **capital-one-2025-03 (150 dpi + JPEG):** every money cell is confirmed. OCR read the layout marker as "...detailed transactions**:**", and `backend/services/financial/statement_layout_context.py:80` matches that phrase exactly. So the section and holder are not recognised. This belongs to the queued `fin/c-layouts` (Capital One image reread); I did not touch it, to avoid overlapping that unit.
- **bbva-2024-08 skewed:** it is now read like the unskewed bbva-2024-07 image-only page and held for the same BBVA image-only reason (also c-layouts).
- **Scotiabank / Kapital / Santander no-activity:** the no-activity proof, out of scope (c-zero-totals / c-mx-noactivity).

## Tests actually run (final code unless noted)

**Engine** (`pytest`, live .venv python, `CHROMADB_PORT=1 CHROMA_PORT=1 OMP_THREAD_LIMIT=1`):
- `tests/ -k "ocr or pdf or statement or scan or merrick or generic or financial or checkpoint"` with `test_pdf_worker.py` deselected: **462 passed, 8 skipped**.
  - New `test_scan_preprocessing.py`: **16 passed**.
- `test_pdf_worker.py`: 4 failures (`test_interrupted_reading_exits_child_and_releases_its_slot[cancel|callback]`, `test_interrupting_one_pdf_never_kills_the_other_reader[ai|financial]`).
  - These are **pre-existing**. The same 4 fail on unmodified HEAD (`git archive HEAD` copy, 4 failed / 6 passed). They are spawn-process tests and are not related to this change.

**Backend** (unittest, same env):
- `discover -p 'test_financial_pdf_*.py'`: **110 OK**.
- `test_financial_pdf_processing_manifest` + `recovery_campaigns` + `expert_statement_support`: 11 OK.
- `test_financial_benchmark_corpus` + `recovery_campaigns` + `expert_statement_support` + `exports`: 19 OK.

**Test changes, and why:**
- One expectation in `test_pdf_extraction.py`: its 150 dpi fixture is now resampled and its span records that.
- `_ocr_page` stubs now accept keyword arguments.
- One stubbed-recogniser test reads its page unprepared, because its stub places words where nothing is printed.

## Not verified
- **Real productions.** All numbers are on synthetic degradations (uniform skew, Gaussian noise, linear fade). Real scans may need different limits: curled pages, non-uniform skew, coloured paper, stamps and photos.
- **Highlights on turned pages.** Rectangles on a turned page are in the straightened frame. The viewer does not yet apply the recorded rotation, so a highlight on the displayed page can sit about r·θ off: up to about 9 pt at 1° and about 22 pt at 2.5° near page corners, much less near the centre. Not built.
- **Full suites.** I did not run the full backend suite, frontend or vitest (shared box; no frontend change).
- **Colour.** Colour scans become greyscale when prepared. Nothing in the reading uses colour as far as I read, but this is not measured on real colour scans.
- **Rotated pages.** Pages with a `/Rotate` and scan text layers on a tilted image are not prepared.
- **Live data.** Live data was not touched. Live sources only benefit after they are re-read, the same caveat as earlier readers (r-recovery / Neil).

## Decisions for Neil
1. **Geometry frame on straightened pages (decided: straightened frame).**
   - Why: the backend's geometric proofs assume printed lines run along the axes. One example is the Andrews quiet-period check "nothing read between the opening and ending lines" (`statement_import_andrews.py` ~L726–758). On a tilted page the original-frame row extents widen, so that band check could miss a line.
   - What this leaves open: highlights on the displayed page are off until a viewer applies the recorded `deskew_degrees` / `rotation_centre`.
   - What would reverse it: you require rectangles on the displayed page now. Then map rectangle centres back at the end of `_read_ocr_page` and re-measure the benchmark. I expect turned pages to fall back to held, not to wrong admissions.
2. **Dropping recognised words over blank paper.** On prepared scans only, a word is dropped when its confidence is under 60 and no pixel within 4 px of its box is darker than grey 128. Every drop is recorded (`ocr_inkless_words`: text, confidence, box). This removes recognised text, but only text with no ink under it. To refuse it, call `_ocr_page` without `drop_inkless_words`; the 2 periods it fixed then go back to held.
3. **Deploy together.** The engine now writes `scan_preprocessing.py` and `pdf_scan_preprocessing` into the processing manifest. A backend without `1c81dc0d` rejects such records ("Stored table provenance is malformed"). Engine and backend must ship together. They are in the same repo; just do not deploy one side alone.
4. **Kill switch.** `PDF_SCAN_PREPROCESSING=false` (pydantic setting `pdf_scan_preprocessing`) returns every page to the as-scanned reading.
