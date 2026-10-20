# t-visual-v03 — WIP notes (counts and opaque ids only)

Unit: visual ground truth for visual-queue shard v03 (`intercam-mexico` in the inventory: 10 documents, 68 pages, all
"the independent reader finds no text on any page"), then the BLIND measurement of fin/release-1 after integrate-11
(d53e0915, no tuning) on every new verified period, the rescore of a copy of the bench of record, and the read-only live
ledger audit. Branch fin/t-visual-v03 from d53e0915. Not pushed. **No code changed at all** (processor or tooling): the
existing real_visual format covered every page.
Private detail: /mnt/owl-data/fin-real/truth/visual/PROGRESS-v03.md (per-document status, copies, chain, audit, blind),
truth/visual/<doc>.txt|.json, tmp/v03/ (renders, typing-aid draft `bdraft.py`, write/check/chain/stack helpers,
mini-compare), logs/v03-*.log and audit-v03.log, truth-mini-v03, bench/v03-mini (blind fresh read), bench/wave11-v03
(rescore copy), audit-v03; backups truth-backup-pre-v03/, compare-backup-pre-v03/.

## Landed (commits)

- (this commit) WIP-NOTES.md only. Truth itself is private (never committed).

## Classification and truth (steps 1-3)

- **The shard is not bank statements.** All 10 documents are brokerage statements printed by the predecessor bank's
  brokerage house (Casa de Bolsa, landscape pages), so the family is `intercam-brokerage` by the printed issuer (the
  t-visual-v04 convention; the existing intercam-brokerage truth is the same contract). Two contracts: 9 documents of
  one, 1 of the other (whose later statements are under `kapital-brokerage`). Because of this, these periods are NOT a
  blind figure for the Kapital bank layout outside the Kapital shard (none of them is a bank statement).
- Why "no text": pdfplumber returns 0 characters on every page; PyMuPDF (fitz) returns a full text layer. The fitz
  text was used only as a typing aid (a draft per document, tmp/v03/bdraft.py, private); every value (each row's net
  amount and settlement day, every printed end-of-day balance, opening, closing, summary figures) was checked against
  the page image rendered with fitz (100-150 dpi crops) and read with the Read tool. Trailing pages (position detail,
  tax-receipt parties, fund rating lists, tax receipt) checked on contact sheets.
- Convention (as intercam-brokerage d37df4b5e3403 and t-visual-v04): one period per statement = the cash ledger:
  opening = printed opening line, each movement's net amount dated by its settlement day, the printed end-of-day
  balance on that day's last row, closing = printed closing line. Account = contract last 4; holder = the name line
  exactly as printed (one document prints the legal-form suffix, the other nine do not).
- **Documents by final status (10): verified 10.** not_statement 0, duplicate 0, incomplete 0, unverified 0.
- **Copies: 0.** Render hash at 40 and 60 dpi of every page of all 832 statement documents (t-visual-v04's table) and the
  release page-identity rule (services/financial/page_identity.py, unchanged since v04): no page of a v03 document is
  shared with any other document; **the two methods agree**.
- **Periods (10): verified 10**, rows 132 (5 periods carry only the stamp fee and its refund). Each verified period:
  opening + every row = closing to the cent; every printed end-of-day balance matches; the first-page summary
  (deposits, withdrawals, repo premiums, tax withheld) equals the rows, and the first-page cash figures (previous month,
  current) equal opening and closing where printed.
- **Expected: auto 10 (MXN), decision 0, hold 0.** As t-visual-v04's brokerage decision (reverse: `expect decision`).
- Decided here (reversible in one line of the private transcription): one 2022 statement prints no opening line and
  its previous-month column is blank; this layout leaves zero values blank, the previous-month position is blank for a
  holding bought during the month, and the first printed end-of-day balance equals 0.00 plus that day's two rows, so
  the opening is 0.00 and the period is `verified`. Reverse: add `unverified opening not printed` (the precedent for an
  opening that is printed only after the first movement is `unverified`).
- **Statement documents final: 809/832 -> 819/832** (+10). Status over 832: verified 782, settled 3, unverified 18,
  not_statement 16; pending needs_visual 8 (shard v02), needs_parser 2, partly_verified 3. Truth periods verified
  1,674 -> 1,684. Only the 10 shard documents changed status. visual-queue.json: **v03 done (10/10)**; queue done
  330 -> 340 of 353.

## Chain (independent cross-check, all Kapital and predecessor-bank truth, bank and brokerage)

- 117 periods, 117 distinct (0 repeated printed periods), 20 printed accounts. **Adjacent pairs 70 -> 76 (6 with a v03
  side), 0 contradictions, 0 overlaps. Gaps 17 -> 21** (the one long brokerage gap of the main contract is split into
  four by the new periods, plus one new gap before the second contract's later statements; 5 gaps border a v03 period:
  months with no statement in the productions). Verified-only identical.

## BLIND processor measurement (step 5; fin/release-1 d53e0915 after integrate-11, no tuning)

Mini corpus truth-mini-v03 (10 PDFs, 10 periods, 10 distinct, 0 copies, all expected auto). Fresh read,
run_real_benchmark --concurrency 2, OMP_THREAD_LIMIT=1, product default (automatic save ON), niced, compare into
tmp/v03/mini-compare (private). Load 2.4 before reading, 3.2 after.
- **Ready 0/10. Wrong admissions 0.** Saved 0, critical-field errors 0, duplicate ledger contributions 0, batch items
  matched to no truth period 0, valid-looking wrong values 0.
- **Engine-served 0, library-served 0**: no reader produced a ledger on any period (0 transactions read; the only
  "row" is the no-movements placeholder on d243eb0f0e749#1).
- Held 10: currency only 9; d243eb0f0e749#1 reading + holder + account + institution + balance.
- Identity against truth (10 periods): period start 10/10, end 10/10, currency 1/10 (9 unread), holder 0/10, account
  0/10, opening 0/10, closing 0/10 (all unread); **0 values differ. No saved period, so no saved holder at all.**
- Root cause class (from the read and the compare): the brokerage cash ledger is not read, same class as the 4
  kapital-brokerage periods and the 1 earlier intercam-brokerage period (r12-kapital's brokerage scope). Rows on held
  periods: 132 in truth, 0 read. pdfplumber sees no text in these files but the engine's fitz text layer holds every
  value, so a reader for this ledger can work from text (no OCR needed).

## Rescore of the bench of record with the new truth (no re-read)

Copy bench/wave11-v03 of bench/wave11 (the integrate-11 bench of record), harness --rescore at d53e0915, compare/
shared (backup compare-backup-pre-v03/; about 50 minutes niced at load 4-7). **The manifest it read also holds
t-visual-v02's truth**: v02 regenerated the shared truth at 18:53, four minutes after this unit (its run kept this unit's
10 documents verified), so the rescore reflects both shards (10 periods here, 8 from v02).
- **1,388/1,524 ready** (was 1,388/1,506: denominator +18 = 10 new distinct auto periods from this unit + 8 from v02,
  all `not_detected` by absence because wave 11 never read these documents), recoverable 1,388/1,519, **wrong 0**,
  critical 0 (21,930 rows), held kept out 5/5, exact copies 168/171 (unchanged), unmatched items 16 (0 offered).
  **Ready lost 0, gained 0.**
- Exit 1, **not caused by this truth**: "2 exact copies offered or saved instead of set aside" is the same line in
  bench/wave11/summary.md itself (dcfc8ce1f2afc#1, open decision 2).
- **Compare: statements compared 778 -> 796** (+10 this unit, +8 v02), statement documents 816 -> 815 (v02's fund
  statement is now not_statement), periods+items 1,713 -> 1,731, without disagreement 1,532 -> 1,530. The -2 is the
  known rescore re-pairing artefact, not new truth: on d0f81a5b856d7 (andrews-share; its truth file is byte-identical
  before/after) the rescore swapped the items paired to two pairs of repeated printed periods (#11<->#13, #12<->#14);
  all four were not ready before and after. d1db0b3c9ca54 and d5a3ad9b75a08 were rewritten with unchanged counts.

## Live ledger (read-only audit audit-v03; READ ONLY transaction; nothing written)

- **On this unit's documents: 0 live admitted periods** (none of the 10 documents has an admitted period live).
- All truth documents (788): 1,129 live admitted periods: agrees 703, convention_only 314, live_period_undated 106,
  **disagrees 6 (the same 6 ids as waves 10-11)**. Same printed period admitted twice in a case: 1 (d7d1158e6b261#2, the
  known double admission across two ledger accounts, open decision 3). Live counts grew since wave 11 (898 periods on
  778 documents) because more periods are admitted live; no new disagreement.

## Tests actually run

- test_financial_benchmark_corpus + real_compare + real_visual + real_truth + statement_census: **110 OK**
  (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1, pdfplumber from headless/real/pylib). No code changed in this unit.
- Synthetic benchmark not run: no code changed (processor or tooling), so it cannot move.
- Neil decisions 2026-10-09 (Andrews sign, late-posted card charges): not touched (no processor code; brokerage only).

## Next units should continue with

1. Brokerage cash-ledger reader (now 15 distinct periods: intercam-brokerage 11, kapital-brokerage 4; 0 ready): the
   ledger prints opening, every movement's net amount with operation and settlement day, end-of-day balances and the
   closing; the text layer is complete on the intercam files. Currency: the position table prints the currency per
   holding; the cash ledger itself does not print a currency word.
2. Truth coverage: 13 documents remain non-final: needs_visual 8 (v02, BBVA), needs_parser 2, partly_verified 3; then
   v11/v12 Capital One confirm and v19 Navy Federal.

## Decisions needed from Neil

- None blocking. Decided here with reasoning (private transcription, reversible in one place): family by printed issuer
  `intercam-brokerage`; expected `auto` MXN as the existing brokerage truth; the one statement without a printed opening
  line is verified with opening 0.00 (reverse: `unverified opening not printed`).
