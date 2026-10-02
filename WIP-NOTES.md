# WIP notes — checkpoint A statement automation benchmark (branch fin/a-benchmark)

## Done
- `backend/benchmarks/statement_automation/corpus.py`: deterministic synthetic corpus generator
  (generic labelled, Credit One, Merrick, Andrews families; digital / scan-with-OCR-layer /
  image-only modes; defects: OCR amount/balance digit, start not printed, holder/account not
  printed, omitted row, exact duplicate copy, no-activity, multi-period PDFs). Ground truth in
  manifest. NOT yet generated/committed (`python -m benchmarks.statement_automation.corpus` from backend/).
- `engine_read.py`: reads PDFs with the engine's real extract_text + canonical text + geometry grouping
  in a subprocess (needs `if __name__ == '__main__'` — spawn re-imports main).
- `harness.py`: full fresh-upload run on disposable SQLite (add_files → create_batch → advance_batch
  with process_files hook persisting engine reading → batch_status → simulated corrections via real
  `assess` → queue_import → ledger verification vs ground truth). Written, NOT yet executed.

## Verified so far
- Prototype (scratch) proved the path end to end: a digital generic labelled statement read by the
  engine (~11 s/PDF incl. process spawn) → batch status `ready`, can_import true, balances match.
- Loopback PostgreSQL 55434 is NOT listening on this box → SQLite.
- Interpreter: system python3 (3.13) lacks deps; `/home/conorbowles51/app-v3/owl-n4j/.venv/bin/python`
  (read-only use, PYTHONDONTWRITEBYTECODE=1) has backend + engine deps (fitz, pytesseract).

## Next
1. Generate corpus, run harness, iterate on family layouts until clean variants are recognised
   by the catalog (Credit One / Merrick / Andrews geometry may need x/y tuning).
2. Add `scripts/run_statement_benchmark.sh` one-command wrapper.
3. Run baseline, write `docs/financial-workflows/baseline-2026-10-02.md`.
