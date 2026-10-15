# t-visual-v16 — WIP notes (counts and opaque ids only)

Unit: visual ground truth for visual-queue shard v16 (`mt-bank`: 45 documents, 118 pages, case d5b330d1 production),
the second and last M&T shard, and the BLIND measurement of the current processor on it (fin/release-1 e066836b, no
tuning). Branch fin/t-visual-v16 from fin/release-1 e066836b. Not pushed. **No code changed at all** (processor or
tooling): the existing real_visual format (incl. `subcount` and per-period `kind` from t-visual-v15) covered every
page. Private detail: /mnt/owl-data/fin-real/truth/visual/PROGRESS-v16.md (per-document status, conventions, chain,
redaction, blind findings), truth/visual/<doc>.txt|.json, tmp/v16/ (renders, contact sheets, chk/chain/mk/loc helpers,
mini-compare), logs/v16-*.log, truth-mini-v16, bench/v16-mini (blind fresh read), bench/wave6-v16 (rescore copy),
audit-v16; backups truth-backup-pre-v16/, compare-backup-pre-v16/.

## Landed (commits)

- (this commit) WIP-NOTES.md only. Truth itself is private (never committed).

## Classification and truth (steps 1-3)

- Every page of all 45 documents classified; every page carrying a value read at full size from fitz renders
  (110 dpi). Non-first pages first classified on contact sheets, then every continuation, checks-paid,
  notice-only and line-of-credit page read at full size. Tesseract text was started as a typing aid but not used:
  every value was typed from the image, and every period's printed section totals and counts were typed separately
  from its rows so the check stays independent.
- **Documents by final status: verified 45** (one of them, d8b425ad12475, holds only duplicates, see below).
  not_statement 0, incomplete 0, unverified 0.
  Page kinds (118): deposit statement first pages 45; deposit continuation pages 10 (rows 2, checks-paid summary 3,
  notice only 5); line-of-credit pages 12 (6 statements x 2); printed reverse sides (balancing instructions) 45 and
  line-of-credit terms pages 6, all `skip`.
- **Periods: 51, all verified** (money market 10, checking 35, line of credit 6). Rows 480. Incomplete 0,
  unverified 0. **Duplicates 2**: both periods of d8b425ad12475 are the same printed periods as v15 d57ebfca9e262
  (re-read from this document's own images; every value equal), marked `duplicate` by real_truth.
- Each verified period: opening + every row = closing to the cent; every printed daily balance matches the running
  balance; every printed section total AND count in the account summary matches its rows (deposits, checks paid,
  other debits incl. service charge rows, interest; line of credit: loans, payments, fees, interest). Checks-paid
  summaries (8 periods) restate the check rows exactly.
- **Expected: auto 49, decision 0, duplicate 2.** Holder, account (last 4 digits), dates and currency printed on
  every period.
- **Redaction (counted per period, detail private):** 51/51 periods print no holder address (45 deposit periods
  print a zero placeholder line in the address block; 6 line-of-credit periods print the name only); 51/51 print
  the account as its last 4 digits; 1 period shows a visible redaction mark at the account cell. No fact a period
  needs is redacted, so no period is `decision` for redaction. 5 periods carry a third holder line (custodial);
  convention 1 from v15 applies (holder = first printed name line).
- Conventions 1-4 from t-visual-v15 applied unchanged. Two notes added (private, reversible in the transcription):
  the money-market "interest earned for statement period" figure is an accrual, not a section total (it differs
  from interest paid on several statements), so it is not used as a control; on one line-of-credit statement the
  printed summary counts two fee waivers (printed under the Fees heading) inside Payments & Credits, and the
  transcription groups them that way so every printed column total is checked.
- **Statement documents final: 643/832 -> 688/832.** Status over 832: verified 663, settled 2, unverified 18,
  not_statement 5; pending needs_visual 128, needs_parser 13, partly_verified 3. Truth periods verified
  1,443 -> 1,494. mt-bank: 85 documents, 92 verified periods. visual-queue.json: **v16 done (45/45)**;
  queue done 148 -> 193.

## M&T chain across v15 + v16 (independent cross-check)

- 92 periods over 3 accounts. **87 adjacent pairs, all chain (opening = previous closing), 0 contradictions,
  0 date gaps.** The only overlap is the duplicate pair above (identical values). Every account is now continuous
  over its whole span in the production: money market 24 periods, checking 61, line of credit 7.
- The line-of-credit advances on one statement equal the checking statement's credit-line transfer rows (same
  amounts, effective one day later): a second independent agreement across documents.

## BLIND processor measurement (step 5; fin/release-1 e066836b, no tuning)

Mini corpus /mnt/owl-data/fin-real/truth-mini-v16 (45 PDFs, 51 periods; 49 distinct + 2 duplicates), fresh read,
run_real_benchmark --concurrency 2, OMP_THREAD_LIMIT=1, FINANCIAL_AUTO_SAVE_READY=0, compare into
tmp/v16/mini-compare (private). **The wave-8 M&T reader unit (r7-mt-engine) should measure on truth-mini-v15 AND
truth-mini-v16 (92 periods, 85 documents).**
- **Ready 0/49. Wrong admissions 0.** Critical-field errors 0, valid-looking wrong values proposed 0, batch items
  matched to no truth period 0. Engine-served 0, library-served 0 (nothing ready; no family reader exists for this
  bank). The 2 duplicates were not held as exact copies because their originals (v15) are not in this mini corpus.
- Held, with reasons (overlapping): holder 44, reading 16, balance 16, institution 8, account 3, not_detected 2.
  Actions 661 single / 574 grouped (field edits 552, decisions 2, rows to add 53).
- **Identity against truth (49 detected periods, field by field):** period start 49/49 equal, period end 49/49,
  currency 49/49, account 45/49 (4 unread), opening 44/49 (5 unread), closing 45/49 (4 unread), holder 0/49
  (45 unread, 4 differ). Rows: 470 in truth on detected periods, 270 matched exactly, 0 differing; 200 missing /
  196 extra, all in 18 periods.
- **The same classes as v15, all failing closed:**
  1. **31 periods: every field except holder and every row equal to truth -> held for the holder alone.** Same root
     cause v15 found (statement_engine.address_holder needs a postal-code line; the production redacts the
     address). One grouped holder confirmation per account would admit them.
  2. **18 periods: rows found but unread** (the v15 class), incl. the 2 no-activity money-market periods (the
     beginning-balance line taken as a row) and 4 line-of-credit periods.
  3. **Line of credit: 2 of 6 not detected at all** (dd0c53276dda0#2, dd416e4cd1f54#2); the other 4 read the bank's
     remittance-coupon line as holder (the only non-empty values that differ from truth, 4/49) with account unread.
     Held, not admitted.
  4. **New observation: institution read as a different bank name on 14 periods** (10 deposit periods and 4
     line-of-credit periods read the logo as another bank's name), 10 more unread. Only 8 are
     blocked for institution; the others are held by holder/reading. When the reader unit fixes holder, this
     becomes the next blocker and must not be admitted as a wrong institution.

## Rescore of the bench of record with the new truth (no re-read)

Copy bench/wave6-v16 of bench/wave6 (the integrate-6 bench of record), harness --rescore at e066836b, compare/
shared (written 2026-10-15 14:57; backup compare-backup-pre-v16/):
- **1,146/1,343 ready** (was 1,146/1,294: denominator +49 = the new distinct M&T periods, `not_detected` by absence
  because wave 6 never read these 45 documents), recoverable 1,146/1,339, **wrong 0**, critical 0 (16,566 rows),
  held kept out 4/4, exact copies 148/153 (+2 = the v16 duplicate pair, unread), unmatched items 16 (0 offered).
  **Ready lost 0, gained 0.**
- **Compare: statements compared 623 -> 668** (of 827 in compare's count), periods+items 1,481 -> 1,532,
  without disagreement 1,290 -> 1,288.
- The -2 is not this truth: the rescore re-paired 10 batch items between same-shaped periods in 3 documents that
  this unit did not touch (2 andrews-share, 1 capital-one-card; 0 M&T), the rescore artefact t-visual-v15/v17
  already describe. Secondary figures moved with it and with the 51 new unread periods: actions 1,828 -> 1,850
  single, 1,668 -> 1,693 grouped; field edits 756 -> 725; decisions 34 -> 34; rows to add 452 -> 452;
  valid-looking wrong values 6 -> 6. The headline figures (ready, recoverable, wrong, lost) do not depend on
  pairing of those items and are unchanged.

## Live ledger (read-only audit audit-v16; READ ONLY transaction; nothing written)

- **On v16 documents: 0 live admitted periods** (and 0 on any M&T document), so 0 disagree and 0 must be held.
- All truth documents: 822 live admitted periods: agrees 425, convention_only 301, disagrees 5 (the same 5 ids as
  v15/wave 6), live_period_undated 91. Same printed period admitted twice in a case: 0.

## Tests actually run

- test_financial_benchmark_corpus + real_compare + real_visual + real_truth + statement_census: **104 OK**
  (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1, pdfplumber from headless/real/pylib). No code changed in this unit.
- Synthetic benchmark not run: no code changed (processor or tooling), so it cannot move; the box was at load
  12-15 on 6 cores with other units reading.
- Full financial suite not run: no module changed.

## Next units should continue with

- r7-mt-engine (wave 8): measure on truth-mini-v15 + truth-mini-v16 (92 periods). Priorities from both shards:
  (1) holder from a name block printed without an address (57 periods wait on this alone: 26 v15 + 31 v16);
  (2) rows found but unread (15 v15 + 18 v16 periods); (3) line-of-credit statements inside a deposit mailing
  (7 periods, 6 distinct: 2 not detected, 5 read the remittance coupon as holder); (4) institution name read from the logo
  as another bank (14 v16 periods) and the 2 no-activity money-market periods.
- Truth coverage: v18 (wells-fargo fragment), v19 (navy-federal, 345 pages), then v01-v06, v09, v11/v12, v14.
- Integration: per-family tables gain mt-bank 92 verified periods (90 distinct); the headline denominator grows by
  the 49 new distinct v16 periods until the next full read covers them.

## Decisions needed from Neil

- None. Decided here with reasoning (private transcription, reversible in one place): the money-market accrual
  line is not a control; fee waivers are grouped as the printed summary counts them.
