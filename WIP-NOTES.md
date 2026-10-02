# a-corpus2 — WIP notes (headless, 2026-10-02)

## Landed (branch fin/a-corpus2, from fin/release-1 6335e4e8; nothing pushed)
- 90346e10 — generator + harness: corpus.py render() gains optional scan degradation
  (dpi/skew/faint/noise/JPEG) and drawn rules (v3 path unchanged); corpus_v4.py (new families);
  harness fixes: compare transaction date not posting date (Capital One false "11 wrong dates"),
  `not_statement` outcome counted as must-hold, unmatched batch items no longer inflate the
  denominator, `--corpus DIR`, metrics/summary by defect and by corpus version.
- 80e1509c — corpus v4: 56 new PDFs / 75 periods, regenerated manifest; new test
  backend/tests/test_financial_benchmark_corpus.py.
- (this commit) — report docs/financial-workflows/baseline-v4-2026-10-02.md + these notes.
- No pipeline code changed.

## Numbers (run /mnt/owl-data/fin-wt/bench-runs/a-corpus2-v4, exit 0)
- v1–v3 subset: 33/49 ready w/o edits (67.3%), 33/40 recoverable, 0 wrong — identical to release-1-v3.
- v4 additions: 28/75 (37.3%), recoverable 28/67 (41.8%), must-hold kept out 8/8, 0 wrong.
- All: 61/124 (49.2%), recoverable 61/107 (57.0%), 10/10 held, 0 wrong admissions, 0 critical-field errors.
- No wrong admission. Near misses (held only because other fields also failed): wrong date
  proposed on 1°-skewed Andrews scan; wrong account number proposed on 100 dpi generic scan.

## Ranked levers (v4 recoverable periods unlocked)
1. Degraded-image OCR (low dpi / faint / JPEG): 12 (15 incl. combined). Faint print holds even a correct text layer.
2. No-activity proof for Scotiabank/Santander/Kapital/Monex printed zero totals: 11 (admission only accepts
   printed counts of 0 or Andrews evidence; Scotiabank's zero_activity_evidence never reaches admission).
3. Deskew before OCR: 7 (10 incl. combined); every skewed scan fails, 2.5° Andrews not detected.
4. Unsupported Scotiabank/Monex movements layouts: 3 (layouts invented; confirm on real documents).
5. Image reread for BBVA / Capital One damaged digits: 2.  6. BBVA image-only OCR: 1.

## Tests actually run
- tests.test_financial_benchmark_corpus: Ran 6, OK (incl. all 92 PDFs regenerate to manifest bytes) — live .venv python, CHROMADB_PORT=1 CHROMA_PORT=1.
- Full benchmark once on the committed corpus (above), plus per-family dev runs while modelling.
- Not run: the full backend suite (no service/pipeline code changed).

## Unverified
- v4 layouts are modelled from reader code/tests, not real documents; the Scotiabank and Monex movements layouts are invented.
- Degradations are synthetic (uniform skew, Gaussian noise); real scans differ.
- Single benchmark run on v4 (v3 runs were stable across 3 runs; v4 OCR-heavy cases not repeat-checked).

## Decisions needed from Neil
1. Do printed zero totals + equal opening/closing balances (Scotiabank chart, Monex/Kapital/Santander totals)
   count as source proof of no activity? Recommend yes, stored with basis printed_zero_totals (11 periods).
2. Receipts in statement batches are kept out but stay as "attention" items; route them out automatically?
3. Ground truth treats Mexican zero-activity sections as `auto` (consistent with Andrews source-proven quiet periods).
