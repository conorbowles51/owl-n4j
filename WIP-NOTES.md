# t-truth — WIP notes (real-document phase, unit 1)

Counts and opaque ids only. Real data lives under /mnt/owl-data/fin-real (mode 700).

## Landed (branch fin/t-truth, base a3691d2c = release 1)

- 7c7c7137 real_inventory.py, real_truth.py, harness private-corpus mode, run_real_benchmark.sh, tests
- 3901a1ee worker-turn cap scales with corpus size; outlined-text pages inventoried as vector_text
- fe72e4d1 real_ledger_audit.py (read-only) + unprinted dates (truth/harness/audit)
- cb2a5d64 ledger audit: pair by share and balances, report repeats and undated live periods
- 644b395b visual queue
- 208bffff WIP notes draft
- fe5d7dfd rescore mode, account-aware matching on real corpora, unmatched admissions judged only on complete truth
- (this commit) WIP-NOTES.md final

## How to run (from backend/, service env loaded)

pdfplumber is NOT in the service venv (deliberately not installed there). It is in a private target dir:
`PYTHONPATH=/mnt/owl-data/fin-wt/headless/real/pylib` (pdfplumber 0.11.7, pdfminer.six 20250506, pypdfium2 4.30.0,
installed with `pip install --no-deps --target`).

1. Inventory (read-only DB, copies originals, fast once copied):
   `python -m benchmarks.statement_automation.real_inventory --out /mnt/owl-data/fin-real`
2. Truth (pdfplumber words cached privately; a full rerun from cache takes ~2 min):
   `PYTHONPATH=…/pylib python -m benchmarks.statement_automation.real_truth --inventory /mnt/owl-data/fin-real/inventory.json --out /mnt/owl-data/fin-real/truth --cache /mnt/owl-data/fin-real/cache/words --jobs 2`
   Writes manifest.json (harness format), status.json, periods/<id>.json, visual-queue.json. Cache version `w2`
   (bump CACHE_VERSION when read_words changes; a cold rebuild takes ~40 min with 2 jobs).
3. Real benchmark: `OMP_THREAD_LIMIT=1 LOUPE_BENCH_PYTHON=<venv python> scripts/run_real_benchmark.sh --out /mnt/owl-data/fin-real/bench/<label>`
   (`--score verified,ocr_reconciled` for the secondary figure). Refuses --out outside /mnt/owl-data/fin-real.
   Engine reading is one document at a time; the full 485-document corpus takes ~4 h (scans dominate).
4. Ledger audit (read-only): `python -m benchmarks.statement_automation.real_ledger_audit --truth /mnt/owl-data/fin-real/truth --inventory /mnt/owl-data/fin-real/inventory.json --out /mnt/owl-data/fin-real/audit`

Gotcha: `pkill -f <pattern>` / `pgrep -f` kills the calling shell when the pattern is in its own command line
(exit 144). Kill by PID.

## Counts

Full counts-only report: /mnt/owl-data/fin-wt/headless/real/truth-summary.md. Private detail: /mnt/owl-data/fin-real/
(inventory.json, truth/{manifest,status,visual-queue}.json, truth/periods/, bench/baseline-release-1{,-ocr}/, audit/).

**Inventory:** 729 distinct documents (1,580 evidence files, 7,085 pages) behind every financial batch item and source
document in all 6 cases; 729/729 bytes match the evidence hash. Page make-up: mixed 298, digital 263, vector_text 125
(text drawn as outlines), image_only 37, scan_text_layer 6.

**Truth coverage (documents):** verified 474, partly_verified 6, ocr_reconciled 5, unverified 16, needs_parser 16,
needs_visual 207, not_statement 5. **Periods:** verified 906 (759 auto + 1 decision distinct, 146 exact repeats of a
printed period in another document), ocr_reconciled 182, unverified 117. By family (verified): BBVA 347, Monex 167,
Capital One 215, Citi 92, Santander 41, Intercam 30, Kapital 14; Andrews 162 ocr_reconciled. Benchmark manifest: 485
documents.

**Real baseline, release-1 code (scored = verified distinct periods), rescored after truth corrections:**
- **Ready without edits 484 / 760 (63.7%)**; recoverable 484 / 759 (63.8%).
- **Wrong admissions 0; critical-field errors 0** (10,484 transactions saved from 692 periods).
- Secondary (also scoring ocr_reconciled): 568 / 920 (61.7%), 0 wrong.
- By family: BBVA 333/344, Capital One 116/118, Intercam 22/30, Santander 9/41 (currency 24), Kapital 4/14,
  **Monex 0/166 (160 not detected), Citi 0/46 (not detected)**.
- Exact repeats of a printed period: 144, only 3 held; ~943 duplicated transactions imported from 106 of them.
- First pass reported 28 wrong admissions; all 28 were truth/matching artefacts (26 account identifier convention on the
  Kapital/Intercam layout, 1 sub-account pairing, 1 statement the OCR-layer truth had not found). Fixed in fe5d7dfd and
  rescored with `--rescore` (23 items re-paired).
- Run: engine reading 485 documents one at a time ~3.5 h, import ~3.7 h (each import rebuilds the catalogue of its
  whole document: O(statements x pages) on the 200-page card productions).

**Synthetic regression (must not drop):** 93/124 (75.0%), recoverable 93/107, 0 wrong, 0 critical — on 3901a1ee-era
harness and again on fe5d7dfd (bench-runs/t-truth-synthetic{,-final}). Unchanged from release 1.

**Live ledger audit (read-only), 771 admitted live periods on documents with truth:** agrees 251, convention_only 448
(Capital One balance owed kept negative; otherwise row for row equal), disagrees 5, live_period_undated 39,
no_truth_period 28 (Andrews shares whose truth is unverified). Disagreements = 3 printed statements:
de45aa4468c66#1 (Monex pesos: mis-read opening, 0 of 7 printed rows, live status unbalanced; visually confirmed),
d22e405327ccf#12 / df7e9c5f8cbb0#12 (Capital One statement printed twice in the file: rows doubled into one live period,
no balances), d22e405327ccf#2 / df7e9c5f8cbb0#2 (Capital One: printed purchase dated the day before the cycle start is
missing). Also 107 printed periods admitted twice within one case (~943 duplicated transactions).

**Visual queue:** 250 documents in 14 shards (v01-v14; <=40 documents / ~400 pages): BBVA 49 (v01-v02), Intercam 10
(v03), Kapital 24 (v04), Santander 68 (v05-v06), unknown-issuer image/vector documents 82 (v07-v09), Andrews 5 (v10,
confirm + read), Capital One OCR-layer pages 3 (v11-v12, confirm), Citi/Credit One/Merrick/Monex 7 (v13), 2 (v14).

**Tests run:** test_financial_real_truth 30 OK (3 end-to-end tests skip without pdfplumber); test_financial_benchmark_corpus
6 OK; pytest test_financial_ledger_misread_audit + test_financial_reader_recovery_estimate 8 passed. Full suites not run
(targeted only; no service code changed — only benchmarks/ and scripts/).

## Unverified / open

- Truth parsers missing: BBVA investment-fund statements (12 documents), Credit One (1, OCR text with every glyph doubled),
  Merrick (1), FirstCaribbean (1), Monex OCR scan (1). Santander online movement queries (13) unverified by rule.
- Andrews truth is OCR-layer only (162 ocr_reconciled, 94 unverified); needs the visual shard v10.
- 207 needs_visual documents (vector text 125, image only 37, no independent text 10, mixed image pages).

## Next units (suggested, ranked by scored periods)

1. Real Monex reader: 160 verified periods not detected (every document); the synthetic layout does not match.
2. Duplicate statements across differently produced files and inside one file: 141/144 imported; live 107 twice.
3. Citi card reader: 46 verified periods (0 today).
4. Santander currency decision on real statements: 24 periods blocked on currency.
5. t-visual-v01..v14 (truth for the remaining 250 documents).

## Decisions needed from Neil

- **Live data:** the 3 printed statements above (5 live periods) are wrongly admitted, and 107 printed periods are
  admitted twice in one case. Correcting live data is a live action: not done.
- Decision 1 below (OCR-layer readings unscored until visually confirmed) — keep, or score them.


## Decisions taken (each reversible in one line)

1. **OCR-layer readings are never `verified`.** A period read from a producer's OCR layer over a scan that reconciles is
   `ocr_reconciled`, unscored by default, queued for visual confirmation. Reason: on the synthetic corpus such a reading
   reconciled with a designed consistent misread (row amount + its balance + ending moved together) and with two lost
   lines netting to zero. Reverse: score them with `--score verified,ocr_reconciled` (harness) or mark them verified.
2. **Santander online movement query ("Consulta de Movimientos") is unverified**: its printed "Saldo Inicial" is the
   balance after the first movement, so printed opening + rows ≠ printed closing. Reverse: derive the opening.
3. **Monex: one period per currency section**; a section with no movement table counts as a zero-movement period only
   if it prints zero credits, zero debits and equal opening and closing (same as the c-mx-noactivity rule).
4. **BBVA: reconciled on operation balances**, row date = OPER date; the printed settlement closing is an extra control
   (operation closing − rows settling after the period = settlement closing). Prior-period settlement table excluded.
5. **Cards: balances are amounts owed** (corpus convention); transaction date before the cycle start allowed (≤60 days);
   interest lines print no date → truth date `None`, any recorded date accepted.
6. **"Estado de cuenta único" (Kapital and Intercam) share one parser**; family from the CLABE bank code (128/136).
7. Absent printed page 1 when everything else reconciles → `unverified` (cannot see whether it was the bank's insert),
   not `incomplete`.
