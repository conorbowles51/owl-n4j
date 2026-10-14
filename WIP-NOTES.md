# r6-vector-text — WIP notes (headless unit, 2026-10-13/14)

Counts and opaque ids only. Private detail (tools, readings, per-statement comparisons, run databases) is under
`/mnt/owl-data/fin-real/tmp/r6v/` and `/mnt/owl-data/fin-real/bench/r6v-*`.

## Landed (branch fin/r6-vector-text, on fb8abfdf)

| Commit | What |
|---|---|
| 101d0ca4 | Vector-outline pages classed `vector_text` and read from their character outlines (new `evidence-engine/app/pipeline/vector_glyph_reading.py`); money cells confirmed from the outlines; OCR words over blank paper dropped; reading revision **v18**; v17 `pdf_extraction` digest added to the reader-recovery list. Routing: on engine/library agreement the library period takes the holder/institution it left unread from the engine (`AGREEMENT_FILLS_IDENTITY`). Harness: file-level best-first pairing (`pair_file`). |
| db6f91cc | Printed amounts OCR skipped altogether on vector pages are added from their outlines (`unread_words`, grouped two-decimal amounts only). |
| (this file) | WIP-NOTES.md |

## What was found (census, read-only; bench/wave5 readings, all 583 truth documents, 5,991 pages)

- Pages by physical class: native text 5,185; image 392; **vector outlines 343**; empty/sparse 71.
- The 343 vector-outline pages sit in **49 documents**: BBVA 21 docs (166 pages), Monex 15 (98), Intercam 6 (30),
  Kapital 3 (17), Intercam brokerage 1 (6), Santander 1 (5), unmatched 2 (21).
- **The engine classed every one of them `no_native_text`, none `vector_text`**: the empty-text test ran before the
  vector test, and the vector test counted paths (>= 1,000) while these producers draw a whole printed line as one
  path (84-180 paths, ~33,000 segments per page): 232 of the 343 pages would have failed the path test anyway.
  Weak-text, non-image pages split cleanly: < 300 segments or >= 4,066.
- On those 49 documents in bench/wave5: 47 periods ready, **29 held carrying 2,010 simulated actions** (of the
  2,866 per-period actions on the whole set).
- Root causes on the long BBVA cash-management statements:
  1. Digit misreads (5 read as 9, 2 as 0...) on a crisp outline: **reproduced at 300, 600 and 800 dpi; 400 dpi
     was worse**. Higher resolution is not the fix, so `_render_dpi` was left alone.
  2. The crop check held correct cells too (crop readings of this narrow font disagree among themselves): about
     one held cell per page.
  3. OCR invented words over blank paper (`—-` between the two date columns) and characters (`O2/IMAY`, `21/DIC_`),
     so movement lines did not parse as dated lines ("unplaced money line", the `additional` reason).
  4. OCR skipped some printed amounts altogether.
  5. One producer snaps outline points to a 600 dpi grid (0.12 pt), so instances of one character are not
     identical (856 "shapes" for 1,909 characters on one page with exact keys; 158 with tolerance).

## What the reader does (general, keyed on the page class, never an issuer)

Characters = filled contours grouped by overlap; shape identity = same contour structure, points within 0.25 pt.
Labels = the page's own OCR majority per shape (>= 3 votes from >= 2 words, >= 60% and >= 2x any other reading;
measured vote purity 99.8%). Words re-read: aligned words change only figures/money marks (letters keep OCR);
unaligned words only if every character is labelled and the reading reconciles with OCR (OCR-added characters
dropped, at most two inside, only marks at the ends). Inkless words dropped. Skipped grouped amounts added.
Money cells: outline reading equal to the page reading confirms; a complete different outline reading holds.
Everything recorded per page in the `vector_glyph_reading` refinement (labels, changed, dropped, added words).

## Measured

### Mini corpus: every truth document with a vector-outline page (49 documents, fresh engine read, v18)

| | bench/wave5 (v17) | **after (db6f91cc readings, r6v-vt5)** |
|---|---|---|
| Ready periods | 47 / 76 scored | **59 / 75** (the unmatched d0ef item now pairs with its period) |
| Previously ready lost | — | **0** |
| Wrong admissions / critical-field errors | 0 / 0 | **0 / 0** (1,062 saved rows) |
| Simulated actions on these documents | 2,010 | **96** |
| Truth row amounts present in the reading | 98.70% (1,142/1,157) | **99.57% (1,152/1,157)** |
| Batch items matched to no truth period | 2 | 1 (0 offered) |

Gained (12): d0ff8ec956097#1, d75c7c3d33ce1#1, d9070f8ff7b5c#1, dac6c1cdc6525#1 (the four long cash-management
statements), d0ef7d86f3916#1, d16ceb8770641#1, d6758908451e5#1 (BBVA), d4ad0bf2dfae7#1, #2, da1e62b9932e9#1, #2
(Intercam), da7fed7c4528e#2 (Kapital). Intermediate runs: r6v-big1 (8 BBVA documents), r6v-vt1..vt4.

### Whole truth set (583 documents, bench/wave5 readings with the 49 vector documents re-read fresh; truth
snapshot = the 583-document truth of bench/wave5, `tmp/r6v/truth-583`; code frozen db6f91cc; bench/r6v-whole)

(The shared truth gained 40 M&T documents from t-visual-v15 during this unit; they are outside this comparison.)

| | bench/wave5 (fb8abfdf/ef0877d6) | **after (db6f91cc)** |
|---|---|---|
| Ready without any edit | 1,118 / 1,253 (89.2%) | **1,130 / 1,253 (90.2%)** |
| Recoverable ready | 1,118 / 1,249 | **1,130 / 1,249 (90.5%)** |
| Previously ready periods lost | — | **0** (12 gained: exactly the 12 of the mini corpus) |
| Wrong admissions (scored) / critical-field errors | 0 / 0 (17,085 rows) | **0 / 0 (17,893 rows, 1,140 periods)** |
| Must-hold kept out / exact copies held automatically | 4/4, 148/151 | **4/4, 148/151** |
| Batch items matched to no truth period | 18 (0 offered) | 16 (0 offered) |
| Valid-looking wrong values proposed | 68 (amount 27, date 37, currency 4) | 6 (date 3, currency 3); see below |
| **BBVA ready** | 355 / 371 | **362 / 371** |
| Investigator actions, harness headline (one at a time / grouped) | 3,785 / 3,638 = **649 / 624 per 100 statements** | 1,423 / 1,279 = **244 / 219 per 100 statements** |
| Per-period simulated actions (scored) | 2,865 (BBVA 1,923) | **870** (BBVA 52) |

Attribution of the action drop: the 49 vector-outline documents 2,010 -> 96 (the reading); Andrews 384 -> 303
(-81), entirely the corrected pairing of one held item (d1db0b3c9ca54, which the old greedy pairing judged
against a different truth period of the same file: 27 amount and 28 date "wrong values" and its row edits); the rest of the headline
drop sits in items not paired with a scored period (the unmatched d0ef7d86f3916 item is now its period; other
unmatched items now pair). Valid-looking wrong values: 55 Andrews + 1 Monex were that pairing artefact; 6 Kapital
date misreads are fixed by the outline reading.

Pairing changes against bench/wave5 (statement ids compared): 15 items, every one to an equal or better fit
(period end, currency, account) or from unmatched to its period; two Andrews swaps are equal-score ties, now
deterministic; none touches a ready period.

Rows read vs truth on vector-outline pages (truth row amounts present in the reading, 49 documents): 98.70% ->
**99.57%**.

The four long BBVA cash-management statements (d0ff8ec956097#1, d75c7c3d33ce1#1, d9070f8ff7b5c#1, dac6c1cdc6525#1:
1,624 of 2,866 per-period actions in wave 5) are ready with 0 actions; the other BBVA reading holds named in the
unit: d6758908451e5#1 and d16ceb8770641#1 ready, d0ef7d86f3916#1 ready (185 actions before), d088a2299c363#1
still held (next unit item 1).

### Synthetic (frozen db6f91cc, bench-runs/r6-vector-text-db6f91cc)

**105/125**, recoverable 105/108, 0 wrong, 0 critical (354 rows), holds 10/10, copies 1/1, 0 valid-looking wrong
values, **BENCH_EXIT=0** (also 105/125 on 101d0ca4).

## Tests actually run

- New `evidence-engine/tests/test_vector_glyph_reading.py`: 24 (synthetic outline pages drawn from Liberation
  Sans with fontTools; skipped if the font is absent), including an end-to-end `_extract_pdf_sync` read with real
  Tesseract and a grid-jitter test.
- Evidence engine, 25 modules around the change (pdf_extraction, money verification, text origin, unread lines,
  second reader, Merrick, card cells, native reread, sign/crop marks, scan preparation, BBVA/amount/date/
  transaction-date/Santander/endpoint OCR, Andrews cells, manifest, generic repair, geometry): **498 passed**.
  `test_pdf_worker` not run (known sandbox failure).
- Backend: test_financial_statement_engine 120 OK (+3 routing tests), test_financial_benchmark_corpus 13 OK (+1
  pairing test), recovery readers/campaigns 25 OK.
- Full financial suite once on db6f91cc (live .venv, CHROMADB_PORT=1): **Ran 6,093, failures=2, skipped=20**: the
  2 known `test_financial_unassigned_statement` failures only.
- Frontend not touched.

## Decisions taken (each reversible in one place)

1. **Outline reading instead of higher dpi** for vector pages: misreads reproduce at every dpi tried; the outline
   is the print itself. Reverse: route `vector_text` back to plain OCR by dropping `vector_text=True` in
   `_read_ocr_page` (the page class stays recorded).
2. **Vector page class** = weak/empty text, < 50% image, >= 1,000 paths or >= 3,000 path segments
   (`_vector_text_page`, `MIN_VECTOR_SEGMENTS`). No truth page changes native/OCR routing by it (all 343 were OCR'd
   already).
3. **Shape tolerance 0.25 pt** (`SHAPE_TOLERANCE`): 0.25-0.3 only reunite instances of one character, 0.4 merges
   letters.
4. **Labels from the page's OCR majority** (`MIN_LABEL_*`); letters never rewritten in aligned words
   (`FIGURE_CHARACTERS`); unaligned words only via `_reconciled`.
5. **Outline confirmation of money cells** (`_outline_status` in statement_money_verification): the outline is the
   print, not an image; a complete outline reading that differs holds the cell. Fail-closed reconciliation is
   unchanged. Reverse: pass `outline_reading=None`.
6. **Skipped amounts added** only as grouped two-decimal amounts with every character labelled and no character
   under an OCR word (`unread_words`). Reverse: drop the `unread_words` call in `_read_vector_outlines`.
7. **Processing manifest not extended** with `vector_glyph_reading.py`: the backend validator accepts only known
   source inventories, so a new engine would fail validation on an older backend; `statement_money_verification.py`
   is not listed either. The reading revision (v18) and the `pdf_extraction` digest record the change.
8. **Routing: agreement fills holder/institution only** (`AGREEMENT_FILLS_IDENTITY`, `AGREEMENT_FILLS`). Measured
   first with all identity fields: a quiet Monex section took another section's currency, so currency and account
   are never filled.
9. **Harness pairing made order-independent** (`pair_file`, best-first over the file, ties by statement id/truth
   id; the `--rescore` path already paired this way via `_rematch`). The batch lists equal-dated sections in random
   item-id order and the old greedy pairing judged a quiet USD section equal to its truth in every field as a wrong
   admission in one run and right in the next (df191ae7b7240, r6v-vt3 vs r6v-vt1). This changes no processor
   output. Reverse: restore the per-item `pair_truth` call in `run`.
10. Whole-set run uses bench/wave5 readings for the 534 documents without a vector-outline page: v18 changes
    nothing on a page not classed vector_text, and the census found no such page outside the 49.

## Not verified / caveats

- `run_real_benchmark.sh` mini runs and the whole-set run used readings made before the last comment-only edit of
  pdf_extraction.py (v18 note), so their manifests carry a pdf_extraction digest one comment older than db6f91cc.
- The census was not re-run (cached readings cannot show an engine change; only the truth documents were re-read).
- Live: nothing changes until deploy + re-read (reading revision v18; reader recovery stays off).

## What the next unit should continue

1. **Pool shape labels across a document's pages.** Short vector pages have too few words to label letters, so
   date cells keep OCR noise (`22/IDIC`) and a skipped heading word (`ABONOS`) is not recovered: d088a2299c363#1
   (16 actions) is held for that. Needs a document-level pass (OCR all vector pages, then label, then verify).
2. Remaining held periods on the 49 documents: 16 (Kapital d0333603efa6b#2, d2ace8cb3baac#1, da7fed7c4528e#1;
   Intercam d2db12b342f03#1, d5975dbaa4344#1, ded55a9f9e81b#1; BBVA d088a2299c363#1, d54d8089ff171#1,
   d74c42f5a4199#1, ddbf23dd65ecf#1 (duplicate copy), d997ce75a70a6#1 (currency); Monex df191ae7b7240#1, #3;
   Santander d3112ed58e525#1 (holder); brokerage d37df4b5e3403#1), 96 actions in total.
3. M&T truth (t-visual-v15) arrived during this unit: 40 documents, not in this unit's comparison basis.

## Decisions needed from Neil

None to continue. Decision 9 changes the benchmark's pairing (not the processor); it is the fix r5-any-layout's
decision 6 left to "whoever owns the harness", made here because the random pairing produced a false wrong
admission inside this unit's own acceptance run.
