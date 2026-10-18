# t-visual-v01 — WIP notes (counts and opaque ids only)

Unit: visual ground truth for visual-queue shard v01 (`bbva-mexico`: 40 documents, 323 pages; 26 vector-outline
documents with no usable text layer, 11 investment-fund statements with no parser, 3 digital documents whose text-layer
truth was `unverified` with "printed page 1 absent; the rest reconciles"); then the BLIND measurement of fin/release-1
after integrate-9 (f2b80e45, no tuning) on every new verified period. Branch fin/t-visual-v01 from f2b80e45. Not
pushed. **No code changed at all** (processor or tooling): the existing real_visual format covered every page.
Private detail: /mnt/owl-data/fin-real/truth/visual/PROGRESS-v01.md (per-document status, chain, live audit, blind
findings), truth/visual/<doc>.txt|.json, tmp/v01/ (renders, tesseract typing aid, draft/fix/save/chain helpers,
mini-compare), logs/v01-*.log and audit-v01.log, truth-mini-v01, bench/v01-mini (blind fresh read), bench/wave9-v01
(rescore copy), audit-v01; backups truth-backup-pre-v01/, compare-backup-pre-v01/.

## Landed (commits)

- (this commit) WIP-NOTES.md only. Truth itself is private (never committed).

## Classification and truth (steps 1-3)

- Every statement page of the 26 vector documents rendered with fitz (100 dpi; 110 dpi where a figure needed it) and
  read with the Read tool. Tesseract (OMP_THREAD_LIMIT=1) was a typing aid only: a draft per document, then every row,
  running balance and summary figure checked against the page image (OCR misreads corrected from the
  images: amounts, balances, dates, one opening/closing pair, transaction codes). Printed controls (the
  "Total de Movimientos" block: debit/credit totals and counts, equal to the summary box) typed separately from the
  rows. Conventions as t-visual-v08 (OPER date, SALDO OPERACION balance, Saldo de Operacion Inicial/Final; the
  "Inversiones Vigentes" listing is not a period).
- For the 3 digital documents and the 11 fund statements the pdfplumber text layer was the typing aid; the images agree
  with it value for value (every row of the 3 digital documents, 146 rows, checked against the page image).
- **Copies: 0.** Render hash at 40 and 60 dpi against 518 BBVA-related documents: no document of the shard is a pixel
  copy of another (shared pages are boilerplate notices only). None of the 6 repeated printed periods in BBVA truth
  involves a v01 document.
- **Documents by final status (40): verified 26, not_statement 11, unverified 3.** duplicate 0, incomplete 0.
  - The 11 fund statements (all of one fund contract, monthly) are `not_statement` (form line, one per
    document): the peso values are market valuations of fund shares that move with price, the movements settle in the
    associated cheques account, and the per-position figures do not form a ledger that reconciles. Reversible in one
    line per transcription.
  - The 3 digital documents: see below.
- **Periods (29): verified 26, unverified 3 (reason class: printed page absent), incomplete 0, duplicate 0.** Rows
  transcribed 1,139 (vector 993, digital 146); 6 verified periods have zero movements (summary prints 0 / 0.00 and equal
  balances). By currency: MXN 11, USD 12, EUR 3 verified.
- Each verified period: opening + every row = closing to the cent; every printed running balance matches; printed
  debit and credit totals and counts equal the rows.
- **Expected: auto 26, decision 0, hold 0, duplicate 0** (the 3 unverified periods are not scored).
- **The 3 digital `unverified` documents: the visual reading does not settle them.** All three start at printed page 2
  of 7/15/7 with the complete summary box, and every present page matches the text layer and reconciles (including
  printed counts and totals). In this shard, all 11 statements whose summary is on printed page 2 have, as printed
  page 1, the bank's unnumbered fiscal-ID notice insert (no ledger facts); the other 15 print the summary on page 1. All
  three periods also chain on both sides (opening = previous closing, closing = next opening). That is strong evidence
  the absent page holds no ledger fact, but the page is not in the file and cannot be seen, so they stay `unverified`
  (reason: printed page 1 of the statement is not in the file; every present page reconciles). The visual review is
  recorded, so the queue counts them done.
- **Statement documents final: 748/832 -> 785/832** (+37: 26 verified + 11 not_statement; the 3 unverified were
  already final). Status over 832: verified 748, settled 3, unverified 18, not_statement 16; pending needs_visual 42,
  needs_parser 2, partly_verified 3. Truth periods verified 1,604 -> 1,630. bbva-mexico documents: verified 376 -> 402,
  not_statement 11, unverified 5, needs_visual 8, needs_parser 1. visual-queue.json: **v01 done (40/40)**; queue done
  266 -> 306 of 353. Only the 37 shard documents changed status.

## BBVA chain (independent cross-check, all BBVA truth)

- Verified + unverified periods: 407 (401 distinct printed periods; 6 repeated, none from this unit) over 19 printed
  accounts. **361 adjacent pairs, all chain (opening = previous closing), 0 contradictions, 0 overlaps** (37 pairs have
  a side from this unit). **Gaps 26 -> 21** (8 of the 21 border a v01 period: months with no statement in the
  productions).
- Verified only: 355 pairs (31 with a v01 side), 0 contradictions, 0 overlaps, 23 gaps.

## BLIND processor measurement (step 5; fin/release-1 f2b80e45 after integrate-9, no tuning)

Mini corpus truth-mini-v01 (26 PDFs: every document of this unit with a scored period; 26 periods, 26 distinct, 0
copies, all expected auto; the 3 unverified and 11 not_statement documents are not in the manifest). Fresh read,
run_real_benchmark --concurrency 2, OMP_THREAD_LIMIT=1, product default (automatic save ON), compare into
tmp/v01/mini-compare (private), BENCH_EXIT=0. **The box was NOT quiet** (load 16.3 before reading, 12.9 after; other
units reading alongside): the time-budgeted money-cell consensus can lose a repair under load (held, never wrong), so
the ready figure is a floor.
- **Ready 15/26 (57.7%), all saved by the system with no click (1 by the worker's sweep save). Wrong admissions 0.**
  Critical-field errors 0 (422 rows saved from 15 periods), duplicate ledger contributions 0, batch items matched to
  no truth period 0. Valid-looking wrong values proposed before review 13, all on held periods.
- **Engine-served 3 (general engine), library-served 12 (bbva-mexico-cash-management).**
- Held 11 (exact reason sets): currency only 3 (d0294824e4694#1, d2bcc3e71e2b8#1, d6d2d26fac5f4#1: the three euro
  statements, currency unread); reading 5 (d1398a6f10ccc#1, d21fec4270dd1#1, d2ad6c671870d#1 and, with balance,
  d6e938a4fe751#1; da0bbb3011253#1 with balance + count); balance only 3 (d5b9be5531e71#1, d61e9751f750a#1,
  dae1da5b86444#1).
- **Identity against truth (26 periods, field by field): 0 values differ.** period start 26/26, period end 26/26,
  account 26/26, currency 23/26 (3 unread), opening 22/26 (4 unread), closing 23/26 (3 unread). Holder 15/26 exact;
  the other 11 are the name as printed on the statement's fiscal-receipt page ("receiver name") instead of the address
  block: 7 without the legal-form suffix, 4 with the suffix punctuated (the punctuated form is already in 26 saved
  BBVA periods of the bench of record). Same entity in all 11, 5 of them saved.
- Rows: 993 in truth, 985 matched exactly, 2 missing / 1 extra, 6 differing (4 dates, 2 amounts), all on held
  periods. Two of the date differences re-checked on the image: both printed dates are the truth date.
- Classes (all fail closed): (1) euro statements: currency unread (3); (2) reading: rows missing or misread on 3 long
  cash-management statements (110-221 rows) and 2 small dollar statements (11-17 rows); (3) balance unread or not proved on
  small dollar statements (3).

## Rescore of the bench of record with the new truth (no re-read)

Copy bench/wave9-v01 of bench/wave9 (the integrate-9 bench of record), harness --rescore at f2b80e45, compare/ shared
(backup compare-backup-pre-v01/; about 75 minutes at load 12-16):
- **1,315/1,462 ready** (was 1,315/1,436: denominator +26 = the 26 new distinct auto periods, `not_detected` by
  absence because wave 9 never read these documents), recoverable 1,315/1,457, **wrong 0**, critical 0 (20,306 rows),
  held kept out 5/5, exact copies 164/171 (unchanged), unmatched items 16 (0 offered). **Ready lost 0, gained 0.**
- Exit 1, **not caused by this truth**: "2 exact copies offered or saved instead of set aside" is the same line, with
  the same 164/171, in bench/wave9/summary.md itself (the wave-10 r10-copies item).
- **Compare: statements compared 728 -> 754** (+26 files, all this unit's scored documents), statement documents
  827 -> 816 (-11: the fund statements are now not_statement), periods+items 1,643 -> 1,669, without disagreement
  1,468 -> 1,468. The only existing compare file that changed is d1db0b3c9ca54 (andrews-share), the rescore re-pairing
  artefact earlier units describe (one item id re-paired; its no-disagreement count is unchanged, 30 of 34).

## Live ledger (read-only audit audit-v01; READ ONLY transaction; nothing written)

- **On this unit's documents: 11 live admitted periods on 11 documents: agrees 10, disagrees 1, must be held 0.**
  The disagreement is d6d2d26fac5f4#1 (zero-movement EUR statement): the live period's opening and closing both differ
  from truth. The image (re-read at 110 dpi) prints the truth value for both, and the previous statement's closing
  chains into it, so truth stands and the live period is wrong on its balances (rows agree: none on either side).
- All truth documents: 885 live admitted periods: agrees 469, convention_only 314, live_period_undated 96, disagrees 6
  (the same 5 ids as waves 5-9, plus d6d2d26fac5f4#1). Same printed period admitted twice in a case: 0.

## Tests actually run

- test_financial_benchmark_corpus + real_compare + real_visual + real_truth + statement_census: **109 OK**
  (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1, pdfplumber from headless/real/pylib). No code changed in this unit.
- Synthetic benchmark not run: no code changed (processor or tooling), so it cannot move.
- Full financial suite not run: no module changed.
- Neil decisions 2026-10-09 (Andrews sign, late-posted card charges): not touched (no processor code; BBVA only).

## Next units should continue with

- BBVA reader work, measured on truth-mini-v01 (26 distinct periods, 15 ready today, 0 wrong): (1) currency on the
  euro cash-management statements (3 periods, currency alone blocks them); (2) rows on long vector-outline
  cash-management statements (3 periods, 110-221 rows) and two small dollar statements; (3) balances on small dollar
  statements (3). Re-run the blind read at low load before quoting the figure as final.
- Holder convention: the reader takes the fiscal-receipt receiver name; truth takes the address block. Same entity in
  every case seen; a comparison rule (or a reader preference for the address block) would make 11 more periods equal.
- Live ledger: d6d2d26fac5f4#1 is admitted live with opening and closing that the image contradicts (zero-movement
  euro statement). It is the 6th live disagreement; it needs the same treatment as the other 5 (no live write here).
- Truth coverage: v02 (BBVA, 9 documents), v04 (Kapital, 24), v03 (Intercam, 10), v11/v12 (Capital One confirm),
  v19 (Navy Federal, 345 pages). 9 BBVA documents remain pending, all in shard v02 (8 needs_visual, 1 needs_parser).

## Decisions needed from Neil

- None. Decided here with reasoning (private transcription, reversible in one place): the 11 fund statements are
  not_statement (market valuations of fund shares, no reconcilable ledger; reverse: drop the form line and transcribe
  the cash movements as a period); the 3 digital documents with printed page 1 absent stay unverified although every
  present page reconciles and both neighbours chain (reverse: drop the unverified line, they then compile verified).
