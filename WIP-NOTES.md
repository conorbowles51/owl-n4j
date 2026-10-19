# t-visual-v04 — WIP notes (counts and opaque ids only)

Unit: visual ground truth for visual-queue shard v04 (`kapital-mexico`: 24 documents, 167 pages; 20 "the independent
reader finds no text on any page", 4 image-only scans), then the BLIND measurement of fin/release-1 after integrate-10
(cdb9e2b9, no tuning) on every new verified period, the rescore of a copy of the bench of record, and the read-only live
ledger audit. Branch fin/t-visual-v04 from cdb9e2b9. Not pushed. **No code changed at all** (processor or tooling): the
existing real_visual format covered every page, including the brokerage statements.
Private detail: /mnt/owl-data/fin-real/truth/visual/PROGRESS-v04.md (per-document status, copies, chain, live audit,
blind findings), truth/visual/<doc>.txt|.json, tmp/v04/ (renders, tesseract typing aid incl. upright renders of the
sideways brokerage pages, draft/write/chain helpers, allhash.json, mini-compare), logs/v04-*.log, audit-v04,
truth-mini-v04, bench/v04-mini (blind fresh read), bench/wave10-v04 (rescore copy); backups truth-backup-pre-v04/,
compare-backup-pre-v04/.

## Landed (commits)

- (this commit) WIP-NOTES.md only. Truth itself is private (never committed).

## Classification and truth (steps 1-3)

- Every statement page rendered with fitz (100 dpi; 110-130 dpi crops where needed; the brokerage pages rendered
  upright) and read with the Read tool. Tesseract (OMP_THREAD_LIMIT=1, at most 2 processes) was a typing aid only;
  every row, running balance, day-end balance and summary figure was checked against the page image. Printed controls
  (the Total line: deposits and withdrawals, equal to the summary box) typed separately from the rows. Trailing pages
  (blank box page, abbreviations, two fiscal-receipt pages, information page) checked on contact sheets.
- **Documents by final status (24): verified 24.** not_statement 0, duplicate 0, incomplete 0, unverified 0.
  - 20 bank statements ("estado de cuenta unico", one period per account section, peso and dollar): 18 under Kapital
    (bank code 128), 2 printed by the predecessor bank (bank code 136) and recorded as `intercam-mexico`, exactly as the
    text-layer truth of the same account already does.
  - 4 brokerage statements (Casa de Bolsa, pages printed sideways): one period each = the cash ledger, the convention
    of the existing intercam-brokerage truth (the same contract under its earlier name): opening = printed opening,
    each movement's net amount dated by settlement date, the printed end-of-day balances as running balances. Family
    slug `kapital-brokerage` (new slug; the printed issuer is the brokerage, not the bank).
- **Copies: 0.** Render hash at 40 and 60 dpi of every page of all 832 statement documents, and the release
  page-identity rule (services/financial/page_identity.py, computed over all 832): the two methods give identical copy
  groups (11 groups / 22 documents, none containing a v04 document); **no disagreement**. The only page a v04 document
  shares with another document is the bank's information boilerplate (last page).
- **Periods (44): verified 44** (bank 40: 20 peso sections with movements, 20 dollar sections with none; brokerage 4).
  Rows 627 (bank 436, brokerage 191). Each verified period: opening + every row = closing to the cent, every printed
  running balance (bank) or end-of-day balance (brokerage) matches, printed deposit/withdrawal totals equal the rows;
  brokerage first-page summaries (deposits, withdrawals, repo premiums, tax withheld) equal the rows.
- **Expected: auto 44, decision 0, hold 0, duplicate 0.** Decided here: the brokerage cash ledger does not print a
  currency word; it is pesos by the market sections and matches peso transfers in the bank statements, and the existing
  brokerage truth is `auto` MXN, so these are `auto` too (reverse: `expect decision` on the 4 brokerage share lines).
- **Statement documents final: 785/832 -> 809/832** (+24). Status over 832: verified 772, settled 3, unverified 18,
  not_statement 16; pending needs_visual 18, needs_parser 2, partly_verified 3. Truth periods verified 1,630 -> 1,674.
  Only the 24 shard documents changed status. visual-queue.json: **v04 done (24/24)**; queue done 306 -> 330 of 353.
- Independent cross-checks between documents: the bank transfers to and from the brokerage contract in Nov and Dec 2025
  equal the brokerage ledger's deposits and withdrawals in the same months.

## Kapital chain (independent cross-check, all Kapital and predecessor-bank truth, bank and brokerage)

- 107 periods, 107 distinct (0 repeated printed periods), 20 printed accounts. **Adjacent pairs 28 -> 70 (42 with a
  v04 side), 0 contradictions (opening = previous closing in every pair), 0 overlaps. Gaps 18 -> 17** (5 of the 17
  border a v04 period: months with no statement in the productions). Verified-only identical.

## BLIND processor measurement (step 5; fin/release-1 cdb9e2b9 after integrate-10, no tuning)

Mini corpus truth-mini-v04 (24 PDFs, 44 periods, 44 distinct, 0 copies, all expected auto). Fresh read,
run_real_benchmark --concurrency 2, OMP_THREAD_LIMIT=1, product default (automatic save ON), niced, compare into
tmp/v04/mini-compare (private). Load 6.2 before reading, 7.4 after (other units running): the ready figure is a floor.
- **Ready 32/44 (72.7%), all saved by the system with no click. Wrong admissions 0** (harness definition).
  Critical-field errors 0 (242 rows saved from 32 periods, every one equal to truth), duplicate ledger contributions 0,
  batch items matched to no truth period 0.
- By family: kapital-mexico 29/36, intercam-mexico 3/4, kapital-brokerage 0/4.
- **Engine-served 23** (general engine: kapital 20, intercam 3), **library-served 9** (kapital-mexico-product-statement).
- Held 12 (exact reason sets): brokerage currency 4 (the cash ledger is not read at all: 0 of 191 rows; held, never
  wrong); kapital balance 2, balance+reading 4, reading 1 (d01f8012f48f4#1, d4faaa1aac35b#1, d775f15e3cfb9#1,
  d99ba504ad26c#1, d99c80af5979d#1, d9e96a68c0dce#1, dd4615dbd7c5f#1); intercam balance+reading 1 (dc5c69b6b30a0#1).
- Identity against truth (44 periods, field by field): period start 44/44, end 44/44, currency 40/44, account 40/44,
  opening 40/44, closing 40/44 (the 4 unread are the brokerage periods); **holder 30 equal, 4 unread, 10 differ.**
- **Headline finding: 5 SAVED periods carry a wrong holder** (d01f8012f48f4#2, d4faaa1aac35b#2, d775f15e3cfb9#2,
  d9e96a68c0dce#2, dd4615dbd7c5f#2: the zero-movement dollar sections of one account holder; 5 more held periods of the
  same holder have the same value). The harness does not count holder as a critical field, so these are not "wrong
  admissions" by its definition, but the saved statement names an address line as the account holder. Root cause from
  source: `statement_import_kapital.kapital_catalog` takes as holder the topmost cell of the left address block that
  matches `[A-Z...][A-Z... &.,]{2,180}`, a pattern with no digits; this holder's printed name contains a digit, so the
  name is skipped and the third address line (the first digit-free one) is taken. Same failure would hit any Kapital or
  predecessor-bank customer whose name contains a digit.
- Rows on held periods: kapital 151 truth rows: 10 missing, 4 extra, 8 dates differ; intercam 43: 3 missing, 3 extra.

## Rescore of the bench of record with the new truth (no re-read)

Copy bench/wave10-v04 of bench/wave10 (the integrate-10 bench of record), harness --rescore at cdb9e2b9, compare/
shared (backup compare-backup-pre-v04/; about 2 h 10 min niced at load 7-13):
- **1,351/1,506 ready** (was 1,351/1,462: denominator +44 = the 44 new distinct auto periods, `not_detected` by
  absence because wave 10 never read these documents), recoverable 1,351/1,501, **wrong 0**, critical 0 (21,356
  rows), held kept out 5/5, exact copies 168/171 (unchanged), unmatched items 16 (0 offered). **Ready lost 0, gained 0.**
- Exit 1, **not caused by this truth**: "2 exact copies offered or saved instead of set aside" is the same line in
  bench/wave10/summary.md itself (dcfc8ce1f2afc#1, open decision 2 of wave 10).
- **Compare: statements compared 754 -> 778** (+24, all this unit's documents), statement documents 816 (unchanged),
  periods+items 1,669 -> 1,713 (+44), without disagreement 1,500 -> 1,500 (the new periods are unread in wave 10's
  readings). Existing compare files that changed: d1db0b3c9ca54 (andrews-share, the known rescore re-pairing artefact)
  and d5a3ad9b75a08 (merrick-card, same items); both keep their no-disagreement counts (30/34, 30/42).

## Live ledger (read-only audit audit-v04; READ ONLY transaction; nothing written)

- **On this unit's documents: 13 live admitted periods on 12 documents: agrees 3, live_period_undated 10 (no rows, no
  period dates), disagrees 0, must be held 0.**
- All truth documents (778): 898 live admitted periods: agrees 472, convention_only 314, live_period_undated 106,
  **disagrees 6 (the same 6 ids as wave 10)**. Same printed period admitted twice in a case: 0. The audit does not
  compare holders, so it cannot see the holder defect above in the live ledger.

## Tests actually run

- test_financial_benchmark_corpus + real_compare + real_visual + real_truth + statement_census: **109 OK**
  (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1, pdfplumber from headless/real/pylib). No code changed in this unit.
- Synthetic benchmark not run: no code changed (processor or tooling), so it cannot move.
- Neil decisions 2026-10-09 (Andrews sign, late-posted card charges): not touched (no processor code; Kapital only).

## Next units should continue with

1. Kapital holder (above): accept a printed name with digits in the address-block holder rule, keeping the
   topmost-line choice; prove on truth-mini-v04 (10 periods become equal) and the whole set (0 wrong, no holder lost).
   A holder check in the harness/compare (holder differs on a saved period) would have caught this; consider adding it.
2. Kapital brokerage cash ledger (4 periods, 191 rows, plus the 1 intercam-brokerage period): nothing reads it today.
3. Kapital bank residue (7 kapital + 1 intercam held: balance/reading on statements whose rows span 2-4 pages).
4. Truth coverage: 18 needs_visual remain (v02 BBVA 8, v03 Intercam 10), needs_parser 2, partly_verified 3; v11/v12
   Capital One confirm; v19 Navy Federal.

## Decisions needed from Neil

- None blocking. Decided here with reasoning (private transcription, reversible in one place): brokerage statements are
  statements (their cash ledger is the period), family slug `kapital-brokerage`, expected `auto` MXN as the existing
  brokerage truth (reverse: `expect decision` on the 4 share lines, or `form not_statement`).
