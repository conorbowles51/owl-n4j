# t-visual-v02 — WIP notes (counts and opaque ids only)

Unit: visual ground truth for visual-queue shard v02 (`bbva-mexico`: 9 documents, 76 pages; 8 vector-outline documents
with no usable text layer, 1 investment-fund statement with no parser), then the BLIND measurement of fin/release-1 after
integrate-11 (d53e0915, no tuning) on every new verified period, the rescore of a copy of the bench of record, and the
read-only live ledger audit. Branch fin/t-visual-v02 at d53e0915. Not pushed. **No code changed at all** (processor or
tooling): the existing real_visual format covered every page.
Private detail: /mnt/owl-data/fin-real/truth/visual/PROGRESS-v02.md (per-document status, copies, chain, blind, live
audit), truth/visual/<doc>.txt|.json, tmp/v02/ (renders, tesseract typing aid, draft/fix/chain/source helpers,
mini-compare, mini-compare-go, rescore-compare), logs/v02-*.log and audit-v02.log, truth-mini-v02, bench/v02-mini and
bench/v02-mini-generic-only (blind fresh read), bench/wave11-v02 (rescore copy), audit-v02; backups
truth-backup-pre-v02/, compare-backup-pre-v02/.

## Landed (commits)

- (this commit) WIP-NOTES.md only. Truth itself is private (never committed).

## Classification and truth (steps 1-3)

- Every page of the 8 vector documents rendered with fitz (100-110 dpi; 150-220 dpi crops for the summary box, movement
  lines and one disputed amount) and read with the Read tool. Tesseract (OMP_THREAD_LIMIT=1, 2 processes) was a typing
  aid only: a draft per document, then every row, running balance and summary figure checked against the page image.
  Draft errors corrected from the images: 7 rows the draft missed or could not parse (typed from the images), 1 amount,
  1 day, 2 summary figures (a credit total and a credit count). Trailing pages (summary chart, notices, glossary,
  fiscal receipt, investment listings) checked on contact sheets.
- The fund document: page images read (positions, ISR, movements, valuation); the text layer only to confirm the
  contract and period are the same series as v01's 11 fund statements.
- **Copies: 0.** Render hash at 40 and 60 dpi of every page of all 832 statement documents, and the release page-identity
  rule (services/financial/page_identity.py), both from tmp/v04/allhash.json (computed over all 832 by t-visual-v04):
  no v02 document is a copy of any other document by either method; **no disagreement** between them. Pages a v02
  document shares with others are boilerplate only (generic-RFC notice, notices page, glossary).
- **Documents by final status (9): verified 8, not_statement 1.** duplicate 0, incomplete 0, unverified 0.
  - dcefa65727c7b is `not_statement`, the same test as t-visual-v01: it is the one missing month (Dec 2025) of the same
    fund contract as v01's 11 fund statements. Its peso figures are market valuations of fund shares (titles x closing
    price); opening value + movements does not reach the closing value without the share-price revaluation, which is
    printed per position only; the movements settle in the associated cheques account. Reverse in one line: replace
    the form line with a fund period whose revaluation is a printed control.
- **Periods (8): verified 8** (EUR cash management 5: 1 with no movements; MXN cash management 2 with 138 and 184 rows;
  MXN small-business account 1). Rows 336. Each verified period: opening + every row = closing to the cent; every
  printed operation balance matches; printed deposit and withdrawal totals and counts (Total de Movimientos) equal the
  rows and the summary box.
- Both printed dates of each row: the row date is the OPER column (the convention of all existing BBVA truth); the LIQ
  column date is recorded on every row as a trailing `# LIQ yyyy-mm-dd` comment in the private transcription (the
  format has one date field). 4 of 336 rows print a LIQ date later than OPER.
- **Expected: auto 8, decision 0, hold 0, duplicate 0.**
- **Statement documents final: 809/832 -> 828/832** (this unit +9, to 818; t-visual-v03's 10 Intercam documents had
  already been written). Status over 832 after both: verified 790, settled 3, unverified 18, not_statement 17,
  partly_verified 3, needs_parser 1. bbva-mexico: verified 402 -> 410, not_statement 11 -> 12, unverified 5, pending 0.
  Truth regeneration (`--only` the 9 ids, `--jobs 2`): manifest 788 -> 796 files, only the 8 v02 statement documents
  added, no other file changed. visual-queue.json: **v02 done (9/9)**; queue done 349 of 353 (left: v11, v12, v19).

## BBVA chain (independent cross-check, all BBVA truth)

- Verified + unverified: 407 -> 415 periods (409 distinct; the 6 repeated printed periods are older, none v02) over 19
  printed accounts. **Adjacent pairs 361 -> 374 (13 with a v02 side), 0 contradictions, 0 overlaps. Gaps 21 -> 16.**
  **Every v02 period chains on both sides** (opening = previous closing, closing = next opening).
- Verified only: pairs 355 -> 368, 0 contradictions, 0 overlaps, gaps 23 -> 18.

## BLIND processor measurement (step 5; fin/release-1 d53e0915 after integrate-11, no tuning)

Mini corpus truth-mini-v02 (8 PDFs, 8 periods, 8 distinct, 0 copies, all expected auto). Fresh read,
run_real_benchmark --concurrency 2, OMP_THREAD_LIMIT=1, product default (automatic save ON), niced, compare into
tmp/v02/mini-compare (private). Load 2.7 before reading, 5.7 after.
- **Product: ready 8/8 (100%), all saved by the system with no click. Wrong admissions 0.** Critical-field errors 0
  (336 rows saved; 336/336 equal to truth: 0 missing, 0 extra, 0 differing), valid-looking wrong values 0, duplicate
  ledger contributions 0, batch items matched to no truth period 0.
- **Engine-served 3** (general engine: db1c525785a55#1, db246a9a5a748#1, df24f459449bc#1), **library-served 5**
  (bbva-mexico-cash-management).
- **Generic-only** (`LOUPE_FINANCIAL_GENERIC_ONLY=1`, same readings): **ready 8/8, all engine-served, wrong 0,
  critical 0** (336 rows). 1 batch item matched to no truth period, held (`currency`), not offered: df1da793b288e
  yields an empty page-1 fragment (0 rows, no account, no currency) beside its real period. Fails closed; product mode
  does not produce it.
- Identity against truth (8 periods, field by field): period start 8/8, end 8/8, currency 8/8, account 8/8, opening
  8/8, closing 8/8. **Holder 6 equal, 2 differ** (db1c525785a55#1, db246a9a5a748#1, both engine-served, both saved):
  the name as printed on the fiscal-receipt page (receiver name, without the legal-form suffix) instead of the address
  block. Same entity; the same class t-visual-v01 reported for 11 BBVA periods, not a different person or company.
- Reading v23 (r11-bbva-vector) on vector-outline pages no unit tuned on: 336/336 rows and every balance read right.

## Rescore of the bench of record with the new truth (no re-read)

Copy bench/wave11-v02 of bench/wave11 (the integrate-11 bench of record), harness --rescore at d53e0915 against the
current truth manifest (which holds both this unit's and t-visual-v03's new truth), compare into a private copy of
compare/ (see Coordination); about 52 minutes niced at load 4-7.
- **1,388/1,524 ready** (was 1,388/1,506: denominator +18 = this unit's 8 bbva-mexico periods + t-visual-v03's 10
  intercam-brokerage periods, all `not_detected` by absence because wave 11 never read these documents), recoverable
  1,388/1,519, **wrong 0**, critical 0 (21,930 rows), held kept out 5/5, exact copies 168/171 (unchanged), unmatched
  items 16 (0 offered), valid-looking wrong values 4 (unchanged). **Ready lost 0, gained 0** (per period).
- Exit 1, **not caused by this truth**: "2 exact copies offered or saved instead of set aside" is the same line in
  bench/wave11/summary.md itself (dcfc8ce1f2afc#1, open decision 2).
- **Compare: statements compared 778 -> 796** (+18: this unit's 8 and v03's 10), statement documents 816 -> 815
  (dcefa65727c7b is now not_statement), periods+items 1,713 -> 1,731, without disagreement 1,532 -> 1,530.
  The 2 fewer are not this truth: no truth of an existing compare file changed. The rescore re-paired items
  between periods #11-#14 of d0f81a5b856d7 (andrews-share), the rescore re-pairing artefact earlier units describe
  (the harness drops batch outcomes for the 11 items whose truth pairing changed). d1db0b3c9ca54 and d5a3ad9b75a08
  (the known artefact files) changed with their no-disagreement counts unchanged.

## Live ledger (read-only audit audit-v02; READ ONLY transaction; nothing written)

- **On this unit's documents: 8 live admitted periods on 8 documents: agrees 8, disagrees 0, must be held 0** (rows
  the same, balances and account agree). The fund document has 1 live file and 0 admitted periods.
- All truth documents (796): 1,137 live admitted periods: agrees 711, convention_only 314, live_period_undated 106,
  **disagrees 6 (the same 6 ids as wave 11)**. Same printed period admitted twice: 1 (the known d5b330d1 pair).

## Tests actually run

- test_financial_benchmark_corpus + real_compare + real_truth + real_visual + statement_census: **110 OK**
  (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1, pdfplumber from headless/real/pylib). No code changed in this unit.
- Synthetic benchmark not run: no code changed (processor or tooling), so it cannot move.
- Neil decisions 2026-10-09 (Andrews sign, late-posted card charges): not touched (no processor code; BBVA only).

## Coordination / housekeeping

- t-visual-v03 was rescoring into the shared compare/ while this unit's rescore ran, so this unit's rescore wrote its
  compare into a private copy (tmp/v02/rescore-compare, copied from compare/ first) instead of racing on compare/.
  compare/ itself was backed up (compare-backup-pre-v02) and not written by this unit. v03's rescore used the truth
  manifest after this unit's regeneration, so the shared compare/ it writes covers the v02 documents too.
- A `chmod 600` meant for this unit's transcriptions was applied to every transcription in truth/visual. The 250 files
  that were 644 in the pre-v04 backup were restored to 644; 87 files stay 600 (newer than that backup), inside a 700
  directory, so nothing became more readable.

## Next units should continue with

1. Holder convention (now 13 BBVA periods across v01 and v02 blind, same entity): either the reader prefers the
   address-block name, or the comparison treats the fiscal-receipt receiver name of the same statement as equal.
2. Generic-only: the empty page-1 fragment on df1da793b288e (held, never offered). The general engine should not
   emit an item with no rows, account, currency or balances when a full period from the same pages exists.
3. Truth coverage: 4 statement documents remain without a final status, all very long (v11/v12 Capital One confirm,
   v19 Navy Federal).

## Decisions needed from Neil

- None. Decided here with reasoning (private transcription, reversible in one place): dcefa65727c7b is not_statement
  (fund-share valuations, no reconcilable ledger), exactly as v01's 11 statements of the same fund contract.
