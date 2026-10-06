# t-visual-v07 — WIP notes (counts and opaque ids only)

Unit: visual ground truth for visual-queue shard v07 (40 unknown-issuer documents, 251 pages), plus the
document-status fix for settled documents. Branch fin/t-visual-v07 (from fin/release-1 8338cebe). Not pushed.
Private detail: /mnt/owl-data/fin-real/truth/visual/<doc>.txt|.json, PROGRESS-v07.md, tmp/v07/, audit-v07/,
logs/v07-*.log, backups truth-backup-pre-v07/, bench/wave1-pre-v07/, compare-backup-pre-v07/.

## Landed (commits)

- 96c80a0e — real_visual transcription for any issuer: document lines `issuer <family> <institution>`,
  `currency` (document default, or per section after its share line), `kind card`, `form not_statement <reason>`;
  `share -` for statements without a share number; rows dated YYYY-MM-DD; rows with no printed running balance
  (`-`); `control` lines for printed totals and counts (credits_/debits_total, credits_/debits_/rows_count),
  checked by the existing reconcile(). Andrews behaviour unchanged.
  Item 5: `real_truth.document_status` (used by the text-layer reader and the visual merge). Verified + incomplete
  periods = `settled` from any reader; after a complete visual review an unverified period is final too, so
  verified + unverified = `settled`; from a text layer that stays `partly_verified` (could be the truth reader's
  own gap) and queued. `FINAL` = verified, settled, unverified, incomplete, not_statement; summarise() reports
  `documents_final`.
- c77f3cc8 — harness._rematch (rescore re-pairing) also weighs currency. Without it, rescoring wave 1 swapped the
  currency sections of Monex files (same closing date and contract) and reported 63 wrong admissions / 630
  critical-field errors that the run never made. Scoring only; processor untouched.
- (this commit) WIP-NOTES.md.

## Coverage (counts)

- v07: 40/40 documents final, all `verified`. Pages read 251/251.
- By issuer found: bbva-mexico 13, santander-mexico 9, monex-mexico 8, intercam-mexico 4, kapital-mexico 2,
  scotiabank-mexico 2, first-caribbean 1 (new family), intercam-brokerage 1 (new family: Casa de Bolsa cash ledger).
  0 not_statement, 0 duplicate (mark_duplicates found none against the rest of the truth).
- Periods: 54 verified (expected auto 54), 0 incomplete, 0 unverified. Every one reconciles opening + rows =
  closing to the cent and matches every printed total/count recorded (credit/debit totals, BBVA movement counts,
  running or end-of-day balances). Largest: 182, 157, 133, 129 rows (BBVA cash management).
- Statement documents final: 499/729 -> **541/729** (+40 v07, +2 Andrews documents d0f81a5b856d7 and
  da162973a4fa0 now `settled`). Status counts: verified 518, settled 2, unverified 16, not_statement 5;
  pending needs_visual 168, needs_parser 15, partly_verified 5 (2 Citi + 3 Capital One, as before).
- Truth periods: verified 1,178 -> 1,232; incomplete 2; ocr_reconciled 20; unverified 22 (unchanged classes).
- visual-queue.json: v07 marked done by real_truth (done documents 5 -> 45).

## Rescore of the wave-1 real benchmark (bench/wave1, no re-read; copy kept in bench/wave1-pre-v07)

- With c77f3cc8: ready without edits **800/1,089** (was 800/1,035; the 54 new periods count as not detected),
  recoverable 797/1,082, **wrong admissions 0, critical-field errors 0** (10,622 rows), held kept out 4/4, copies
  145/145. Compare files: statements compared 485 -> 525 of 724; periods+items 1,290, without disagreement 868.
- The v07 documents were not in the wave-1 run (it uploaded only the 485 documents that had truth then), so in
  the rescore all 54 periods are `not_detected` by absence, not by a reader verdict. Reader behaviour on them
  comes from the census (wave-1 code, cached readings, census-wave1):
  - 24 documents `no_statement_found` (no layout recognised): held with currency 14, reading 9, balance 1.
  - 5 documents found by a family reader but held: Intercam product statement 3, Kapital product statement 2
    (reasons balance, reading, no_activity, holder).
  - 11 documents not in the census population (no census period at all).
  - Ready periods 0; so wrong admissions 0. Ranking for r2-any-layout / fix units: BBVA cash management
    (8 docs, 4 with 129-182 rows), Monex sideways pages (8 docs, peso + euro sections), Santander
    certified-copy scans (7), Intercam/Kapital unico statements (6), BBVA business credit line (5).
- Synthetic regression (bench-runs/t-visual-v07-final, code 96c80a0e tree; harness/benchmark tooling only):
  **105/125**, recoverable 105/108, 0 wrong, 0 critical, holds 10/10, copies 1/1. The exit code was not captured
  (a second launch truncated the log); the harness exits non-zero only on a wrong admission and there were none.

## Live ledger (read-only audit, audit-v07; READ ONLY transaction)

- 778 admitted live periods on documents with truth (was 771): agrees 280, convention_only 448, disagrees 5
  (the same 5 as wave 1), live_period_undated 44, no_truth_period 1, must_be_held 0. Same printed period admitted
  twice: 102 (unchanged).
- On v07 documents: 7 live periods: agrees 2 (first-caribbean), live_period_undated 5 (intercam 3, kapital 2;
  admitted without period dates, so not comparable). 0 disagree, 0 must be held.

## Tests actually run

- tests.test_financial_real_visual + real_truth + real_compare + test_financial_benchmark_corpus: 84 tests OK
  (3 skipped), live .venv, CHROMADB_PORT=1 CHROMA_PORT=1. New: 11 transcription/document-status/merge tests, 1 rematch
  test (fails on the old pairing, passes on the fix).
- The full financial suite was not rerun: only benchmark tooling (real_visual, real_truth, harness rescore pairing)
  changed; no processor module.

## Truth conventions decided here (each reversible by editing the private transcription and recompiling)

1. Account per family as the tier-A readers record it: BBVA last 4 of No. de Cuenta (credit line: last 4 of the
   credit number); Santander full digits; Kapital/Intercam last 4 of the CLABE; Monex last 4 of the contract.
2. BBVA business credit line (2 docs with activity: d54d8089ff171, d74c42f5a4199): ordinary interest and its IVA
   are printed only in the summary, not in the movement table; recorded as rows at the cut date so the period
   reconciles. Reverse: drop those rows and mark the period unverified with the reason.
3. BBVA cash management where the settlement final differs from the operation final (d75c7c3d33ce1): closing =
   operation final (= opening + printed totals); the difference is an item settling after the cut.
4. Intercam brokerage statement (d37df4b5e3403): the period is the cash (EFECTIVO) ledger; fund-unit positions are
   not cash rows; the front-page movement summary excludes fund trades, so it is not used as a control.
5. One Monex contract: two months (d271f879e5594, d5fbea6e9bf00) print a different company as holder from the
   other months of the same contract; recorded as printed. Relevant to holder decisions and batching.

## Next unit should continue with

- Shard v08 (second half of the unknown-issuer group, 40 documents, 247 pages) with the same tooling; the private
  helpers in /mnt/owl-data/fin-real/tmp/v07 (r.py band render, rr.py rotated render, sheet.py contact sheet,
  check.py running-balance check) work for every layout seen here.
- Integration: STATE.md per-family tables should take the new truth (families first-caribbean and
  intercam-brokerage are new); the headline denominator is now 1,089 periods.
- A fresh read including the 40 v07 documents is needed to score them for real (the census says 0/54 ready).

## Decisions needed from Neil

None blocking. Conventions 2-5 above are recorded with how to reverse them.
