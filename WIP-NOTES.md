# t-visual-v19 — WIP notes (counts and opaque ids only)

Unit: ground truth for visual-queue shard v19 (navy-federal: 1 document dfc15d7fbdc2c, 345 pages; the live production
of the Navy Federal case), then the BLIND measurement of fin/release-1 after integrate-12 (48e58b67, no tuning), the
rescore of a copy of the bench of record, and the read-only live ledger audit. Branch fin/t-visual-v19 from 48e58b67.
Not pushed. **No processor code changed**: three truth/audit tooling fixes under backend/benchmarks/, with tests.
Private detail: /mnt/owl-data/fin-real/truth/visual/PROGRESS-v19.md, truth/visual/dfc15d7fbdc2c.txt|.json,
tmp/v19/ (renders, crop/sheet helpers, periods-list.json, mini-compare*, ledger-audit-before-share-fix.json),
truth-mini-v19, bench/v19-mini (fresh read, product), bench/v19-mini-generic-only, bench/wave12-v19 (rescore copy),
audit-v19, logs/v19-*.log, logs/audit-v19*.log; backups truth-backup-pre-v19/, compare-backup-pre-v19/.

## Landed (commits)

| commit | change |
|---|---|
| 903763fa | truth: `--only` runs re-read every document whose cached status is `needs_parser` (root cause, below) |
| 1c1a8795 | truth: visual transcription line `keep <n> <outcome> <reason>`: a text-layer period that no reading of the images could verify is kept as read once checked, its status becomes final, the expected outcome is recorded; refused unless the period exists, is not verified and all its pages are on `done` |
| f29fe6d7 | audit: real_ledger_audit pairs a live share printed as the account's four digits with a truth section named by product (Navy Federal); four-digit shares (Andrews) unchanged |
| (this) | WIP-NOTES.md |

The audit and the rescore ran at 23fa3bac, which differs from f29fe6d7 only by a docstring example (a real account
number replaced by an invented one before it was committed for good; history rewritten locally, never pushed).

## Step 1 — why the shared truth said `needs_parser` / issuer unknown

Not issuer detection and not the inventory hint: the current reader names the issuer `navy-federal` on 345/345 text
pages. The shared truth is refreshed with `real_truth --only <ids>`, and every other document reuses its cached
`periods/<id>.json`. This document's cache was written by a full run before 511fe673 (no reader then) and was carried
forward by every later `--only` run, so the reader never met it. Tooling defect, fixed in 903763fa (a cached
`needs_parser` result is read again on every run; test drives `main` end to end and fails under the old rule).

## Step 2 — shared truth regenerated (this document only; backups taken first)

- 220 periods = 55 statements x 4 sections (checking, membership savings, money market, checking line of credit).
  **verified 205, unverified 15. Identical field by field to truth-r-subpoena (all 220 periods: status, reasons,
  rows, opening, closing, holder, pages)**, so counts by status agree with no difference to explain.
- No other document's status or periods changed (832 periods files compared with the backup).

## Step 3 — visual confirmation (fitz renders under tmp/v19, read with the Read tool): COMPLETE

- The 15 unverified periods (18 pages): every value the text layer read equals the image. Two text-layer gaps with
  no effect on status (the credit-line rule keeps both unverified anyway): one payment and one payoff transfer
  printed over two lines are not in the reading (#14, #42).
- Redactions (21 pages carrying filled dark boxes): the first statement (summary page and its 4 section pages: each
  section's beginning balance and first rows) is the only place a ledger value is redacted. Elsewhere the boxes cover
  only the year-to-date dividend column, year-to-date fee/interest totals, the year-to-date tax box, an identity
  number on the signature card and an online balance snapshot. **No redaction touches a verified period's row,
  balance or summary figure.**
- Pages outside every statement (66): cover letter, fax cover, subpoena (2), certificate of service, custodian
  certification, signature card, member record screen (pages 2-7 are the producer's OCR-layer pages), a teller
  deposit listing (2 pages, no balances), 55 check-image pages, an online balance snapshot, a call report. None is a
  statement.
- Summary pages 55/55: 165 account lines, every previous / deposits / withdrawals / ending figure equals the text
  layer (651 figures; 9 redacted on the first). **0 disagreements.**
- Sample: 21 verified periods (all 4 account types, every year 2020-2024, the 54-row period over 3 pages, quiet
  sections split across a page break, the money market closure), 178 rows: every date, amount, direction, running
  balance, beginning and ending equals the image. **0 disagreements.** Holder and account digits match on every
  sampled page.
- **Headline: the text layer and the images agree everywhere checked; no period changed status.**

## Step 4 — final status of the 15 (and the 12 principal-only credit lines)

Recorded with `keep` in the private transcription; the document is now `settled` (final).
- 11 line-of-credit periods with movements or accrued interest: **unverified**, reason class "opening amount owed
  (principal plus accrued interest) not printed in the period; the ledger's balance column is principal only and the
  interest-charge row prints no amount". Expected **decision** (the opening amount owed; printed only on the previous
  statement).
- 4 first-statement sections (checking, credit line, savings, money market): **unverified**, reason "beginning
  balance and first rows redacted in the production". Expected **hold**.
- r8's "12 principal-only credit lines" = the 11 above + the redacted first credit line (counted under hold here).
- Copies: render hash at 40 and 60 dpi and page_identity.py (unchanged since 10-18; table tmp/v04/allhash.json built
  10-19) against all 832 documents: no page shared with any other document, no page repeated inside it, no shared
  identity. **The two methods agree: 0 copies.**

Truth coverage after: **statement documents final 828 -> 829 / 832** (verified 790, settled 3 -> 4, unverified 18,
not_statement 17; pending partly_verified 3 = the Capital One confirm shards v11/v12; needs_parser 1 -> 0).
**Verified periods 1,692 -> 1,897 (+205)**; unverified periods 18 -> 33 (+15). Visual queue: v19 done; 349 -> 350 of 353.

## Step 5 — BLIND measurement (code 23fa3bac = fin/release-1 48e58b67 + tooling only; no tuning)

Mini corpus truth-mini-v19 (1 PDF, 220 periods, 205 scored, all expected auto). Fresh read, run_real_benchmark
--concurrency 2, OMP_THREAD_LIMIT=1, product default (automatic save ON), niced, compare into tmp/v19/mini-compare.
- **Product: ready 205/205 (100%), WRONG 0**, all 205 saved by the system with no click; critical-field errors 0 (925
  rows saved); duplicate ledger contributions 0; valid-looking wrong values proposed 0; batch items matched to no
  truth period 0. **Engine-served 205, library-served 0** (every admitted choice is the generic engine layout).
- Identity against truth, 205 ready periods: start, end, currency, account, **holder**, opening, closing and every row
  equal truth (comparison: 205/205 periods without any disagreement; holder differs 0).
- The 15 unverified: 0 offered, 0 admitted. 12 held as attention with the principal-only reason; 3 (redacted first
  statement deposit sections) not detected as statements. Disagreement classes appear only on these 15.
- **Generic-only (LOUPE_FINANCIAL_GENERIC_ONLY=1, same readings, reused per engine-read.log): ready 205/205, WRONG 0**,
  925 rows, 0 critical, holder differs 0, 205/205 without disagreement, engine 205; the 15 unverified 0 offered, 0
  admitted. Identical to the product, as expected: no Navy Federal family reader exists, so the general engine (with
  the profiles) serves this bank blind at 100% on its first scored truth.
- Read time: engine 983 s wall; batch preparation 2,934 s over 63 worker turns; total 5,056 s (host load 6-10,
  other units running).

Rescore of a copy of the bench of record (bench/wave12-v19, harness --rescore, compare/ shared, backup taken):
- **1,404/1,729 ready** (was 1,404/1,524: +205 Navy Federal periods, all `not_detected` because bench/wave12 never
  read this document), recoverable 1,404/1,724, **wrong 0**, critical 0 (22,419 rows), held kept out 5/5, copies held
  168/171, unmatched items 16. **Ready lost 0.** Exit 1 only for the known saved copy dcfc8ce1f2afc#1 (open decision).
- **Statements compared 796 -> 797 / 815**; periods+items 1,731 -> 1,951; without disagreement 1,551 (unchanged);
  only class change not_detected 3 -> 223 (this document's 220 periods).
- The next whole-set run will read this document: expect +205 ready if the bench agrees with this blind run.

## Step 6 — live ledger (read-only audit-v19; READ ONLY transaction verified `on`; nothing written)

- Before f29fe6d7 the audit reported all **203** live admitted periods of this document as "no truth period" (share
  vocabulary mismatch, above). After: **203 agrees** (rows, opening, closing, holder), 0 disagrees, 0 admitted twice,
  0 admitted on an unverified period. 2 of the 205 verified periods are not admitted live.
- All truth documents: agrees 711 -> 914, convention_only 314, disagrees **6 (the same 6 ids)**,
  live_period_undated 106; same printed period admitted twice 1 (the known one); holder differs 3 (the same Kapital
  periods). No entry for any other document changed with the fix.

## Tests actually run

- test_financial_benchmark_corpus + real_truth + real_visual + real_compare + statement_census: **117 OK** (live
  .venv, CHROMADB_PORT=1 CHROMA_PORT=1, pdfplumber from headless/real/pylib). New: 2 rerun tests, 3 keep tests, 1
  audit share test; the rerun main test was confirmed to fail under the old rule.
- Synthetic benchmark not run: no processor code and no harness code changed.
- Neil decisions 2026-10-09 (Andrews sign, late-posted card charges): not touched (no processor code).

## Next units should continue with

1. Truth coverage: only v11/v12 remain (3 Capital One documents, 20 OCR-reconciled periods to confirm) = 832/832.
2. Navy Federal 11 credit-line periods expected `decision`: the opening amount owed is printed on the previous
   statement (Total Outstanding Balance). A chain proposal (previous statement's printed total, cited) would make it a
   one-click grouped confirmation; today they are held with the principal-only wording.
3. The integration session: merge the three tooling commits (no processor change); the shared truth on disk already
   carries this unit's result.

## Decisions needed from Neil

- None blocking. Decided here (reversible in one line of the private transcription): line-of-credit periods whose
  opening amount owed is not printed are expected `decision` (reverse: `keep <n> hold ...`); redacted first-statement
  sections are expected `hold` (no one can supply a redacted value from this production).
