# t-visual-v13 — WIP notes (counts and opaque ids only)

Unit: visual ground truth for visual-queue shard v13 (card + Monex residue: 7 documents, 395 pages).
Branch fin/t-visual-v13 from fin/release-1 d36fd235. Not pushed. No processor code changed (benchmark truth
tooling only). Private detail: /mnt/owl-data/fin-real/truth/visual/<doc>.txt|.json, visual/PROGRESS-v13.md,
tmp/v13/ (renders, drafting helpers), logs/v13-*.log, audit-v13/, bench/wave2-v13 (rescore), bench/v13-mini
(fresh read), tmp/v13/mini-compare; backups truth-backup-pre-v13/, compare-backup-pre-v13/.

## Landed (commits)

- 12750c8e — real_visual: `patch <n,...>` (a review that replaces only the named text-layer periods; complete
  once its own pages are done; document final once every non-verified period was read from the images) and
  `group <name>` / `subtotal <name> <signed total>` (a card's printed section totals checked against the rows
  transcribed under each section).
- 14f96206 — real_truth: Monex holder read from the cover page (the page listing the contract type) instead
  of page 1 only (one production puts a notice page first; its 3 verified periods were labelled `decision`
  though the holder is printed). Visual queue: a queued document whose truth is settled by any reader is done.
- 67544f0f — visual truth for statements that print only their closing date: header `stmt - <closing>`;
  note `period start not printed` (real_truth.START_UNPRINTED); reconcile does not require a start; the
  manifest records start_printed=False (the synthetic corpus convention for Merrick). All 50 existing private
  transcriptions re-parsed and compiled identically.
- cbaf890e — fix to 14f96206: a text-layer `unverified` document stays queued (the first regeneration had
  marked 16 such Santander/BBVA documents done; rerun: queue done 52 = v07 40, v10 5, v13 7).
- (this commit) WIP-NOTES.md.

## Coverage (counts)

- v13: 7/7 documents final, all `verified`. Pages read: Citi 7 of 131 per file (patch), Credit One 54/54,
  Merrick 56/56, Monex 6/6 and 6/6; db207f0acf6f6 not re-transcribed (already verified; holder now read).
- Periods by family:
  - credit-one-card (first truth): 53 verified (53 cycles; one cycle spans 2 pages), 0 incomplete,
    0 unverified. Every cycle also matches its printed payments / other credits / purchases / cash advances /
    fees / interest totals. Expected auto 53.
  - merrick-card (first truth): 42 verified, 0 incomplete, 0 unverified (5 statements have an interest-table
    second page; pages 1-3 and 51-56 are a cover letter, application record, payment history and subpoena
    papers, not statements). Expected auto 42, start not printed on all 42. The card number changes once
    (2 accounts: 16 + 26 statements).
  - citi-card: 6 periods newly verified (3 per file); the two files are the same printed pages (only the
    production stamp differs), so the second file's 49 periods are `duplicate` (mark_duplicates).
  - monex-mexico: 4 newly verified (2 documents x peso + euro sections, no movements, printed zero totals);
    3 existing verified periods relabelled decision -> auto (holder now read).
- Statement documents final: 541/729 -> **547/729** (db207f0acf6f6 was already final). Status counts:
  verified 524, settled 2, unverified 16, not_statement 5; pending needs_visual 167, needs_parser 12,
  partly_verified 3 (Capital One).
- Truth periods verified 1,232 -> 1,337 (+105); incomplete 2; ocr_reconciled 20; unverified 16.
- visual-queue.json: v13 done (7/7).

## Processor on the new truth (0 wrong admissions anywhere)

- Rescore of wave 2 (copy bench/wave2-v13, no re-read, code cbaf890e): **824/1,191 ready** (was 821/1,089;
  +3 = the newly verified Citi periods, already admitted by the processor and equal to truth row for row),
  recoverable 824/1,187, **wrong 0, critical-field errors 0** (11,531 rows), held kept out 4/4, exact copies
  148/148. Citi 49/49 ready; second Citi file 49/49 held as exact copies. db207f0acf6f6 3/3 ready.
  Merrick 42, Credit One 53 and the 2 Monex documents (4) were not in the wave-2 run: `not_detected` by absence.
  Compare: statements compared 525 -> 529 of 724; periods+items 1,401, without disagreement 893.
- Fresh read of those 4 documents (mini corpus truth-mini-v13, run_real_benchmark --concurrency 2,
  REAL_EXIT=0):
  - credit-one-card: **17/53 ready, 36 held** (reading 33, balance 31; overlapping), **0 wrong**.
    Rows 280 truth / 280 read: 228 match, 32 amounts misread, 20 dates differ.
  - merrick-card: **0/42 ready, 42 held** (dates 42, balance 42, reading 41), **0 wrong**. Rows 224 truth /
    257 read, 53 match; opening and closing balance not found on any statement; closing date missing on 38.
  - monex-mexico (the 2 new documents): 0/4 ready; peso sections held (reading, balance), euro sections not
    detected. 0 wrong.
  - 12 valid-looking wrong values proposed, all in held periods.

## Live ledger (read-only audit, audit-v13; READ ONLY transaction; nothing written)

- All truth documents: 909 admitted live periods (wave 2 audit: 778): agrees 305, convention_only 510,
  **disagrees 6** (wave 2: 5), live_period_undated 87, no_truth_period 1, must_be_held 0. Same printed
  period admitted twice in a case: 102 (unchanged).
- On v13 documents: 108 live periods. Credit One 53 convention_only (rows equal to truth; sign convention
  only). Merrick 9 convention_only, 41 undated (admitted without period dates: not comparable),
  **1 disagrees: d5a3ad9b75a08#5** (case 49494305: closing differs from the printed closing, 3 of 8 rows,
  does not reconcile; the same printed statement admitted in case f887b0d9 agrees). Monex 2 agree,
  2 undated. Citi files: no live periods. Must be held: 0.

## Tests actually run

- test_financial_benchmark_corpus + real_compare + real_visual + real_truth + statement_census: **92 OK**
  (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1, pdfplumber from headless/real/pylib so the end-to-end reader
  test runs). 8 new tests (synthetic).
- Synthetic benchmark (bench-runs/t-visual-v13-final, code cbaf890e): **105/125**, recoverable 105/108,
  0 wrong, 0 critical (354 rows), holds 10/10, copies 1/1, **BENCH_EXIT=0**.
- Full financial suite not run: no processor module changed (only benchmark truth tooling).

## Truth conventions decided here (each reversible by editing the private transcription and recompiling)

1. Merrick start date: not printed (only statement date and days in cycle): start empty, start_printed=False,
   expected auto (synthetic corpus convention). Reverse: write `stmt <closing - days + 1> <closing>`.
2. Card rows dated by the printed transaction date (Credit One, Merrick: as their processor readers record
   it); Citi rows with no transaction date by the post date (tier-A Citi reader). Zero-amount interest lines
   are not rows. Interest lines are printed with the closing date on all three issuers, so no undated rows.
3. Credit One sections: payments = PAYMENT lines; rewards and merchant credits = other credits; a positive
   charge printed inside the "Payments, Credits and Adjustments" block counts as a purchase (the printed
   purchases total includes it: 2 cycles). Balance transfers on Merrick count in purchases (printed total).
4. Merrick card-number change: the first statement on the new number repeats a payment and a purchase already
   on the old number's last statement (different accounts, so not duplicates); both recorded as printed.
5. A credit balance (printed with a trailing minus) recorded as a negative amount owed.
6. Monex sections with no movement table: printed zero credit/debit totals as controls, as the tier-A reader.

## Next unit should continue with

- A fix unit for merrick-card (0/42 ready on verified truth; balances never found, rows mostly misread on the
  scanned OCR layer) and credit-one-card (17/53; 32 amount misreads, 20 date misreads). Both are now scored,
  with first truth for each family; the census (merrick 0/126, credit-one 34/106 ready) is consistent.
- Remaining visual shards: v08 (40 unknown), v01/v02 BBVA, v03 Intercam, v04 Kapital, v05/v06 Santander,
  v09, v11/v12 Capital One confirm, v14 Monex/Scotiabank. Tooling here (patch, group/subtotal, unprinted
  start) and the private helpers in tmp/v13 (r.py band render, draft_c1.py / draft_mer.py drafts from the
  text layer, chk.py per-period check, setpage.py / setsub.py / mk.py block editors) apply.
- Integration: per-family tables gain merrick-card 42 and credit-one-card 53 verified periods; the headline
  denominator is now 1,191 distinct periods (4 documents in it were never read in wave 2: read them in the
  next full run).

## Decisions needed from Neil

- One more live period disagrees with verified truth (d5a3ad9b75a08#5, case 49494305; Merrick). Recommend
  re-reading it with the other 5 after deploy (no live writes made). Nothing in this unit waits on it.
