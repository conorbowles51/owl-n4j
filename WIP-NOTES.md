# fin/aq-c-others: WIP notes (unit C, BNB2 waiting queue)

These notes hold counts and opaque document ids (sha prefixes) only. Real values and transcriptions are kept
under /mnt/owl-data/fin-real/aqc (mode 700).

## Scope

There are 72 targets: 56 are outside the truth corpus and 16 are in truth but held by the bench. The Santander
Consulta and Intercam/Kapital brokerage layouts belong to unit A, and the pipeline/re-read path to unit B.

## Measured on real bytes (mini corpus of 65 docs, base f2a52eae vs branch, readings reused)

The ready count went from 13 to 22 of 72. Wrong admissions were 0 in both runs, and critical-field errors were
0. No target and no admitted period was lost. The scored set has truth for 30 files: 17 tier-A, plus 13
t-visual transcriptions written for this unit and compiled VERIFIED.

| family (as resolved) | targets | ready before | ready after | what changed / why held |
|---|---|---|---|---|
| Monex (2022+ sideways, 2021 portrait) | 15 | 2 | 9 | profile names the 4 balance columns and the guarantee column |
| BBVA | 17 | 4 | 6 | OCR stroke between day and month (q51, q52). Held: 3 scans missing printed pages, 6 fund statements (not ledgers), q43 (OCR '141/JUL' day), q44 (currency) |
| Santander (B) | 21 | 5 | 5 | not reached in this unit |
| other (C) | 14 | 1 | 1 | Held: 9 BBVA scans missing printed pages (q61-q69), 2 brokerage currency (unit A), q38 balance, q58 |
| Kapital / Intercam | 4 | 1 | 1 | MXN sections not reconciled (amount columns) |
| Scotia | 1 | 0 | 0 | not reached |

The newly ready targets are q23, q24, q29, q30, q31, q35 and q39 (Monex), and q51 and q52 (BBVA). Every one is
scored against truth: the visual transcriptions cover docs dcefebd5, d89be099, deb1e564, d51c9120, d497c025,
d7849892, d4e0e81b, daf7e54f and d6b93449. The transcriptions of d5097dee, d4cc6be4, d4cb7388 and d532fd63 are
also VERIFIED and score their held sections.

Monex targets still held:

- q32 and q48 (EUR section, blank currency). The OCR reads the summary's opening label with a stray word, so
  the section splits after the currency heading.
- q33 and q27 (balance/reading).
- q45 and q46 (balance/reading).

## Engine: outline reading on sideways pages

Outline (vector glyph) reading previously ran only at rotation 0. Pages now OCR'd at 90, 180 or 270 read their
outlines in the turned frame (TurnedPage). The switch is TURNED_PAGES in vector_glyph_reading.py.

Across 21 truth docs with turned vector pages, the content changed in 17. Bench results on the 35 truth periods
from those docs:

- Product: base 28, branch 29, r14s-whole 28. Lost 0; gained df191ae7#1.
- Generic-only: the same, against r14s-whole-go. Lost 0.
- Wrong admissions: 0 in both modes.

On the aqc mini, new readings for the 8 sideways Monex docs changed nothing in the outcome.

## Regression

The Monex profile was checked by catalog equivalence on 87 truth docs, comparing base and branch in product and
generic-only modes. Ignoring routing seconds and layout fingerprint, the material catalog changes are:

- Product: df191ae7 (now proved), plus d23eb18d and dc0eacc0 (engine now agrees with library; served unchanged).
- Generic-only: those 3 docs.

The date-stroke rule's tokens occur in none of the 815 truth readings, so the truth catalog is unchanged by
construction.

## Tests

- New backend tests: DateSlashStrokeTests, and the Monex profile column roles.
- New engine tests: tests/test_turned_page.py, and the sideways glyph test in test_vector_glyph_reading.py.

## Gates (measured)

- Synthetic benchmark (branch): 0 wrong admissions; held 10/10.
- aqc mini, product and generic-only: 0 wrong admissions; 0 lost; generic-only ready 13 -> 22.
- Truth runs on 21 turned-page docs and 3 Monex docs: no period lost against r14s-whole or r14s-whole-go.
- Backend: 423 targeted tests pass. The wider financial suite shows the same 22 failures on base f2a52eae and on
  the branch (recovery/scheduler/re-read environment tests).
- Engine container: 117 passed and 50 skipped (the skips need a font). On the host, the font-dependent glyph
  tests (56) pass.
