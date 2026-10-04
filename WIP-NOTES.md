# r-census — WIP notes (unit complete)

Counts and opaque ids only. Opaque id = `<case prefix>:<original sha256 prefix>[.n for the n-th byte-identical copy]#<statement hash>`.
Shareable summary with the full ranking: `/mnt/owl-data/fin-wt/headless/real/census-summary.md`.
Private per-period detail: `/mnt/owl-data/fin-real/census/<case uuid>/` (`periods.jsonl`, `files.jsonl`,
`prepared-*.json`, `run.json`, `templates.json`, `report.json`, `audit/`); reading cache
`/mnt/owl-data/fin-real/census/readings/<engine tree>/<sha256>.json`; `invisible-text.json`, `double-admission.txt`.

## Landed (branch fin/r-census, not pushed, no product code changed)
- fb06e947 `backend/scripts/financial_statement_census.py`: all-files census (every batch file of a case, any live
  state), READ ONLY live inventory (the dry run's guard), current engine re-read in <= 2 processes with
  OMP_THREAD_LIMIT=1 and a resumable per-original cache, retained + new readings prepared with the current backend
  in one disposable SQLite batch per case, no investigator input, per-period join to the live state, ledger misread
  audit with the cached readings, counts-only `--summarize`. Estimate script: evaluation split into `scratch_batch`
  (period level) + unchanged counts.
- 37f44552 live periods counted once; system duplicate set-asides are an outcome, not a hold; `--rejoin`.
- af62dcc8 period identity = statement key, or account + printed dates (multi-account statements).
- 402cc2b4 each prepared side stored as it lands and reused by fingerprint; readings whose original is gone.
- 73180b52 empty statement key = the file's one undivided period on both sides.
- c84cccb0 summary labels only from source vocabulary; quoted cell text masked.
Defects in the census itself found on real data and fixed in those commits (all tested): legacy whole-file items and
dateless summaries double-counting live periods; multi-account statements merged by dates; undivided files unmatched;
crash on a retained reading without its original.

## Headline (census of current code; "ready" = pipeline readiness, NOT truth-checked)
- 960 originals listed across 6 cases (574 distinct by bytes), 901 re-read (0 engine errors), 59 gone from the case.
- **709 of 1,811 scorable periods ready with zero edits (39.1%)**; retained (older) readings through the same
  backend 738. Raw 709/2,264 (31.3%) before excluding 394 system duplicate set-asides and 59 unavailable.
- By case: 1c75e65e 53/53, 267842f3 58/58, fdaf956c 6/6, f887b0d9 191/353, d5b330d1 258/762, 49494305 143/579.
- Held pool 1,033. Top (family x reason, periods / only-reason): capital-one overlap 206/202 (4 originals, re-produced
  statements); no layout recognised 231/226 (214 Mexican "estado de cuenta" in unmodelled layouts); andrews reading
  131 + balance 127; merrick dates/balance/reading 126 (1 original); santander balance 96 / reading 77 / currency 24;
  credit-one reading 46 (1 original); kapital balance 42 / no_activity 23. Full table with 3 example ids each in the summary.
- Synthetic regression benchmark on this branch: 93/124 ready (75.0%), 0 wrong admissions, BENCH_EXIT=0
  (`/mnt/owl-data/fin-wt/bench-runs/r-census-final`), unchanged from release-1.

## Live findings (read-only queries; nothing written)
1. **Double admission in 49494305: 102 periods admitted twice from two different files with identical
   transactions; 929 transactions counted twice.** Pairs 49494305:22e405327ccf + f7e9c5f8cbb0 (52),
   568d90faff56 + 624d41045389 (50). Current backend holds such pairs as "overlap", which does not block a person's
   import. No other case affected; byte-identical copies are not double-admitted.
2. **Invisible producer OCR treated as born-digital (safety gap).** `services/financial/suspect_amounts.page_text_origin`
   calls a page `digital_text_layer` unless images cover >= 80% of it. 7 originals (145 pages) are small image tiles
   (~10% coverage) under an invisible (render mode 3) third-party OCR layer: no crop verification at admission, and
   the misread audit skips them. 360 live admitted statement reviews come from 6 of them. Confirmed by reading the
   engine source (no invisible-text handling) and one original (render types, coverage, a producer OCR date misread).
3. Misread audit: 937 considered, 276 skipped native, flagged 75 (all "disputed now" or row shifts), 95 "disagree"
   cells all in f887b0d9 (89 on 9a66ffec8137, 6 on a162973a4fa0). One spot-checked period = row-address shift between
   readings, not a demonstrated misread. Needs visual truth.

## Tests actually run
- `tests/test_financial_statement_census.py` 9, `test_financial_reader_recovery_estimate.py` 4,
  `test_financial_ledger_misread_audit.py` 4, `test_financial_recovery_readers.py` (+ the above) — 35 passed together
  (CHROMADB_PORT=1 CHROMA_PORT=1, live .venv). Census tests use the synthetic corpus read by the real engine.
- Not run: full backend suite (only scripts changed; product code untouched), frontend (untouched).

## Unverified / limits
- "Ready" is not correctness. Wrong admissions on real documents need t-truth's verified set.
- f887b0d9's report comes from af62dcc8 code (rejoined with the final join); its preparation inputs are unaffected
  by later fixes (no unavailable originals there).
- Live "imported" vs "imported_saved_review" is from the item's saved review only; it does not prove no edits.
- Preparation is slow at case scale (d5b330d1: ~62 min new + ~50 min retained, production code path); reading the
  case took ~3 h with 2 processes.

## Next unit should
1. Fix wave candidates in ranked order: re-produced statements (detect duplicate by identical transactions across
   files, set one aside) — also clears the live double count's root; Mexican layouts no reader matches (214);
   Andrews reading/balance; Merrick dates; Santander totals/amount format; invisible-OCR origin rule (safety first).
2. Rerun: `cd backend && OMP_THREAD_LIMIT=1 CHROMADB_PORT=1 CHROMA_PORT=1 python scripts/financial_statement_census.py
   --case <uuid> [--case ...] --out /mnt/owl-data/fin-real/census --workers 2 --chunk 4 --scratch /mnt/owl-data/fin-real/tmp`
   (cache reused while evidence-engine is unchanged; preparation reused while backend/services+scripts unchanged),
   then `--out /mnt/owl-data/fin-real/census --rejoin --summarize <file>`. The curated top of census-summary.md is
   hand-written; `--summarize` rewrites only the machine tables (prepend the curated part again).

## Decisions needed from Neil
1. **Double admission in 49494305 (102 periods, 929 transactions)**: recommend removing one copy of each pair through
   the product's removal path after checking with Alex which production is authoritative. Not touched (no live writes).
2. **Invisible-OCR pages**: recommend treating pages whose text is mostly invisible (render mode 3) as recognised
   text, so crop verification and the audit apply; then re-audit the 360 admitted statements. Reverse if Neil wants
   the 80% coverage rule kept.
3. Should an "overlap" between different files with identical transactions block import (as a duplicate) instead
   of only warning? Recommend yes.
