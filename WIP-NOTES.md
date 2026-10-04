# t-truth — WIP notes (real-document phase, unit 1)

Counts and opaque ids only. Real data lives under /mnt/owl-data/fin-real (mode 700).

## Landed (branch fin/t-truth, base a3691d2c = release 1)

- 7c7c7137 real_inventory.py, real_truth.py, harness private-corpus mode, run_real_benchmark.sh, tests
- 3901a1ee worker-turn cap scales with corpus size; outlined-text pages inventoried as vector_text
- fe72e4d1 real_ledger_audit.py (read-only) + unprinted dates (truth/harness/audit)
- cb2a5d64 ledger audit: pair by share and balances, report repeats and undated live periods
- 644b395b visual queue
- (this commit) WIP-NOTES.md

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

RESULTS_PLACEHOLDER

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
