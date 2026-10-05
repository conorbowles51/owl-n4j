# t-visual-v10 — WIP notes (real-document phase, wave 1)

Counts and opaque ids only. Real data lives under /mnt/owl-data/fin-real (mode 700).
Branch `fin/t-visual-v10`, base `6b812436` (fin/release-1). Not pushed.

## Landed

- `ed98ed71` real_visual.py (reviewed visual truth: draft from the OCR layer, transcription, reconciliation,
  OCR-layer misread classes), real_truth merges complete reviews (`--visual`, default `<truth>/visual`), stable
  visual-queue shards (`done` per document and shard), mark_duplicates keyed by share, `incomplete` truth scored.
- `4dc35497` real_compare.py: per-statement comparison files (normal run and `--rescore`) + counts-only summary;
  real_ledger_audit judges incomplete truth and reports `must_be_held`.
- `40a21e44` **processor fix**: a second printed statement for the same account, holder and dates in one file
  (starting on another page) is held for comparison instead of skipped as an older reader's key.
- `6c96f7d1` rescore rebuilds not-detected entries from the current truth.
- `254b3988` harness pairing: closing date / account / printed share decide before shared amounts (each counted
  once); a fresh real run no longer reports false wrong admissions from mispaired shares.
- (this commit) WIP-NOTES.md.

## Shard v10 (Andrews share statements, 5 documents, 375 pages): DONE

Every page rendered (fitz) and read; transcriptions private under /mnt/owl-data/fin-real/truth/visual/
(`<doc>.txt` reviewed, `<doc>.ocr.txt` OCR-layer draft, `<doc>.json` compiled, PROGRESS.md).
visual-queue.json: v10 `done: true`, 5 documents done (shard numbers unchanged).

- Periods: **270 final** (the text-layer parse had 256; it merged or missed 14): **verified 268, incomplete 2,
  unverified 0**. Of the 268 verified, 2 are expected `hold` (a second printed statement for the same share and
  month that the real statement and the next opening contradict). Expected outcomes: auto 266, hold 4.
- Incomplete (must be held): 1 statement whose last page says it continues and the continuation is not in the file;
  1 month whose printed page 4 is absent (scan control numbers and running balance jump).
- Against the image, the earlier text-layer truth: **all 162 `ocr_reconciled` periods were exactly right**
  (0 consistent misreads); of 94 `unverified`, 82 needed values or lines the layer lost, 12 were right but held
  for continuation reasons.
- OCR-layer misreads found (counts by class, all 5 documents): lines lost 117; amount unread 80; balance unread
  80; ending line unread 15; amount misread 8; amount sign misread 7; statement header unread 6; share header
  unread 4; line misread 2; closing misread 1; opening unread 1; balance misread 1.
- Holder: 18 first pages carry the holder above the OCR layer's reading; read from the image strips.

## Real benchmark, rescored with the new truth (no re-read)

Run: /mnt/owl-data/fin-real/bench/wave0-v10 (links wave0's database read-only for proposals; results-rescored.json).
Batch outcomes are the wave-0 run's (code before this unit's processor fix).

| | wave 0 (STATE) | rescored with v10 truth |
|---|---|---|
| Scored periods | 761 | 1,031 (+270 Andrews) |
| Ready without edits | 484 (63.6%) | **585 (56.7%)** |
| Recoverable ready | 484 / 760 | 583 / 1,026 |
| Andrews ready | unscored | **101 / 270** (recoverable 99 / 266) |
| Wrong admissions | 0 | **2** (both the contradicting copies, `d0f81a5b856d7#13/#14`) |
| Critical-field errors | 0 | 0 (10,751 rows from 695 periods) |

Andrews blocking reasons: balance 103, reading 100, not_detected 41, holder 34, no_activity 7, assignment 5,
overlap 4. The 2 wrong admissions are fixed by `40a21e44` (verified on the Andrews mini-run below).

### Andrews mini-run, fresh read on this branch's code (after `40a21e44`)

/mnt/owl-data/fin-real/bench/andrews-v10 (5 documents, corpus /mnt/owl-data/fin-real/truth-mini-v10, compare
files in its own compare/). Engine read ~1.5 h + preparation/import ~2.2 h at load 4-7.
- Rescored (correct pairing): **ready 99 / 270** (recoverable 99 / 266), **wrong admissions 0**, critical-field
  errors 0 (267 rows from 99 periods), **holds kept 4 / 4** (the contradicting copies are now held), valid-looking
  wrong values proposed 19 (17 row dates, 2 amounts, all in held periods). Wave-0 counted 101 ready, of which 2
  were the wrong admissions: same 99 correct.
- The run's own summary showed 1 wrong / 65 critical / 79 wrong values: a harness pairing artefact (a ready
  share-0000 item judged against the share-0040 period), fixed by `254b3988` and checked by replaying the
  pairing on the run's database: all 224 items with a printed share pair with their own share and closing date.

## Per-statement comparison (Neil's goal step 1)

/mnt/owl-data/fin-real/compare/<doc id>.json for every manifest document + summary.md / summary.json (counts).
**Statements compared: 485 / 724 statement documents** (the rest have no final truth yet).
Truth periods and unmatched items compared 1,298; without any disagreement 543.
Top classes (occurrences): row_missing 1,935; row_extra 415; not_detected 321; not_ready 190; repeat_offered 101;
unmatched_item 95; holder_missing 74; holder_differs 54; closing_balance_missing 51; opening_balance_missing 46.
By family (periods showing the class), top: Monex not_detected 161; Andrews not_ready 124 / row_missing 95 /
row_extra 93; Capital One repeat_offered 101; Citi not_detected 98; BBVA holder_differs 54; Santander not_ready 31.

## Live ledger (read-only audit, /mnt/owl-data/fin-real/audit-v10)

771 admitted live periods on documents with truth: agrees 278, convention_only 448, **disagrees 5** (the same 3
printed statements as before; none Andrews), live_period_undated 39, no_truth_period 1.
**Andrews: 47 live periods agree with the visual truth, 0 disagree, 0 must_be_held**; 1 is a share recorded as
closed on its printed closing date (09/29) where truth uses the statement end (09/30): no rows, opening equal.
Same printed period admitted twice in one case: 102 (was 107; the share-aware duplicate key removed 5 false pairs).

## Tests actually run

- test_financial_real_truth + real_visual + real_compare: 59 OK (3 end-to-end skipped without pdfplumber; 47 of
  the truth/visual set also run OK with pdfplumber on the path).
- test_financial_statement_overlap: 59 OK.
- import_batches, batch_read_stored, batch_read_projection, batch_review_save_scope, statement_import,
  checkpoint_b_gate, recovery_preparation: 156 OK.
- Synthetic benchmark: before the processor fix 102/124, 0 wrong (bench-runs/t-visual-v10-final); after it
  102/124, recoverable 102/107, 0 wrong, holds 10/10 (bench-runs/t-visual-v10-samefile); after the pairing fix
  identical, pairing of all 124 items unchanged (bench-runs/t-visual-v10-pairing). Equal to wave 5.
- test_financial_real_truth + real_visual + real_compare + benchmark_corpus after the last change: 64 OK
  (3 skipped without pdfplumber).
- Full financial suite: not run (targeted only).

## Decisions taken (each reversible in one line)

1. `incomplete` truth is scored (harness default `--score verified,incomplete`): admitting a period with printed
   pages missing is a wrong admission. Reverse: drop `incomplete` from SCORED_TRUTH.
2. A printed statement contradicted by another printed statement of the same account and dates in the same file
   (and by the next opening) is truth `expected: hold`. Reverse: delete the `expect hold` lines in the private
   transcription.
3. A share the statement prints as "Closed" with no Ending Balance line: truth closing = the final running balance,
   period end = statement end. The processor/live ledger records the closure date instead (period_end differs).
   Reverse: transcribe the closure date as period end.
4. Same-file second statement rule keys on the printed start page; unknown or equal start page keeps the old skip
   (a re-keyed reading of the same statement). Reverse: restore the unconditional skip in coverage_review.

## Unverified / open

- BBVA `holder_differs` 54 periods (truth and processor holder share 2-4 words): not resolved whether the
  truth reader or the processor is right; needs a look at the pages before calling it a processor defect.
- Rescore uses the wave-0 batch outcomes; 171 items re-paired to the renumbered truth lose their proposal checks
  and simulated corrections (actions per 100 statements not comparable to wave 0 for Andrews).
- Andrews row dates: 17 proposed row dates differ from the first printed date (rows print two dates); not yet
  established whether the processor takes the second date or misreads. The compare files list them
  (row_date_differs).
- Andrews items without a printed share (reader splits, 35 items, all held) pair arbitrarily in both the run and
  the rescore; they never reach the ledger.

## Next unit should

- Re-run the full real benchmark on code including `40a21e44` and `254b3988` (expect Andrews wrong 0).
- Integration: `40a21e44` touches services/financial/statement_import_overlap.py (coverage_review) and
  import_batches.py (batch coverage request); r1-reproduced works on duplicate/reprint handling nearby. An
  identical in-file reprint (same rows) is now also held for comparison by this rule unless r1-reproduced sets it
  aside first; both outcomes keep it out of the ledger.
- Andrews readiness (99/270 correct): balance 103 and reading 100 are the big blockers; the compare files list every
  missing / extra / differing row per statement (row_missing 95 and row_extra 93 periods).
- Visual shards v01–v09, v11–v14 with real_visual (draft works for Andrews only; other layouts need a drafter or a
  blank transcription).

## Decisions needed from Neil

None for this unit. Live: the 5 disagreeing live periods and 102 double admissions are unchanged (no live writes).
