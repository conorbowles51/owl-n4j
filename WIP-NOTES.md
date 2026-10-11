# t-visual-v17 — WIP notes (counts and opaque ids only)

Unit: ground truth for visual-queue shard v17 (`synchrony-card`: 16 documents, 66 pages, case 49494305) and the first
BLIND measurement of this card issuer. Branch fin/t-visual-v17 from fin/release-1 b484f376. Not pushed. **No processor
code changed** (benchmark truth tooling only). Private detail: /mnt/owl-data/fin-real/truth/visual/PROGRESS-v17.md
(real wording for the reader unit), tmp/v17/ (text dumps, renders, dev.py / diag.py, cached engine sources,
mini-compare, ctl-compare), logs/v17-*.log, truth-mini-v17, bench/v17-mini (blind fresh read), bench/wave4-a152-v17
(rescore with the new truth), bench/wave4-a152-ctl17 (control rescore with the pre-v17 truth), audit-v17;
backups truth-backup-pre-v17/, compare-backup-pre-v17/.

## Landed (commits)

- 0e45c622 — real_truth: tier-A Synchrony card reader `parse_synchrony` (pdfplumber only) + issuer mark
  `synchrony-card` (last in ISSUER_MARKS, so a bank statement naming a card payment keeps its own issuer on a tie).
  Summary box read left of the "Payment Information" box (which shares its lines and repeats the new balance); rows by
  section (main / fees / interest) across "continued" pages; parentheses = credit; reference column kept apart; wrapped
  description lines joined; zero-amount lines not rows. Controls: payments, new purchases, net credits/fees/adjustments,
  net interest, printed fee total and interest total; any money line without a date fails closed. Start unprinted
  (START_UNPRINTED, Merrick convention of t-visual-v13). 4 synthetic tests.
- (this commit) WIP-NOTES.md.

## Classification and truth (step 1-3)

- Issuer screen: all 617 text-layer documents in the inventory screened; 18 mention the issuer; the detector's result
  changes on exactly the 16 shard documents (unknown -> synchrony-card), on no other document.
- Each document = one printed statement: printed page 1 (summary + start of the transaction table), an image page
  (the printed reverse-side terms: no statement values; checked on renders), printed page 2 (transactions continued,
  promotional summary, interest calculation), printed page 3 (blank on 15; cardholder news continued on 1); one
  document carries 2 extra printed pages of a change-in-terms notice (printed 4-5 of 5). No missing printed pages.
- **Documents by final status: verified 16** (not_statement 0, duplicate 0: 16 distinct closing dates, one per month
  across 16 consecutive cycles, one card account).
- **Periods: verified 16, incomplete 0, unverified 0, duplicate 0.** Expected auto 16 (holder, account, closing date,
  currency all printed; start date not printed -> start_printed=False, as Merrick). Rows 47.
- Every period reconciles to the cent (previous balance + rows = new balance, card sign) AND matches all six printed
  controls. Independent cross-check: each cycle's previous balance equals the prior cycle's new balance across all 16.
- Visual check against rendered page images, value by value (summary box and every transaction row): 3 documents
  (d9b3ebe92356f, d52ac63ec8451, d9e2ef6a2900b): all equal to the text layer. No text/image disagreement found.
- **Statement documents final: 587/832 -> 603/832.** Status over 832: verified 578, settled 2, unverified 18,
  not_statement 5; pending needs_visual 212, needs_parser 14, partly_verified 3. Truth periods verified 1,386 -> 1,402.
- visual-queue.json: **v17 done (16/16)**; queue done 92 -> 108.
- Late-posted rule (Neil ruling 2), measured on this family's truth: 0 of 47 rows dated before the cycle start
  implied by the printed days-in-cycle, 0 after the closing date. Synchrony gives the ruling nothing to act on.

## BLIND processor measurement (step 4; code 0e45c622 = deployed reader code, no tuning)

Mini corpus truth-mini-v17 (16 PDFs, 16 periods), fresh read, run_real_benchmark --concurrency 2, OMP_THREAD_LIMIT=1,
compare into tmp/v17/mini-compare (exit 0):
- **Ready 0/16. Wrong admissions 0.** Critical-field errors 0, valid-looking wrong values proposed 0, batch items
  matching no truth period 0. Engine-served 0, library-served 0. Held 16/16 (first blocking reason: currency 16).
- What the processor read per statement: account number only (16/16); holder, institution, currency, period dates,
  balances: none; transactions 0 (47 truth rows). Harness simulation: 190 single actions / 130 grouped
  (field edits 48, decisions 32, rows to add 47); still blocked after every field edit: 16.
- **Why the reading is empty (from the processor's own reasons, replayed on the run's engine sources):**
  - Library (family readers): no reader claims any page: 0 statements, every table unclassified (16/16).
  - General engine: `no_period` 14, `no_geometry` 2. The printed period is a closing date only plus "days in billing
    period" (no start-end range): the engine finds no period (16/16 print no start).
  - Table geometry: the transaction table is a drawn box with header cells but NO row rules, so the engine source
    holds the entire transaction list (all sections, section totals and the year-to-date block) as ONE cell of
    newline-separated lines (16/16). The account summary box is likewise one cell of label/amount lines, with the new
    balance and days-in-cycle in a second cell (16/16).
  - So: "no period found" + "no table recognised" (rows not separated) + "summary layout the engine has no vocabulary
    for". The live label "layout not supported yet" is the generic empty-reading label for a text-layer file.

## Rescore of the bench of record with the new truth (no re-read)

Copy bench/wave4-a152-v17 of bench/wave4-a152 (a15230a0 readings), harness --rescore at 0e45c622 (compare/ shared):
- **1,034/1,253 ready** (was 1,034/1,237: denominator +16 = the Synchrony periods, `not_detected` by absence because
  wave 4 never read them), recoverable 1,034/1,249, **wrong 0**, critical 0 (13,804 rows), held kept out 4/4, exact
  copies 148/151. No ready period lost.
- **Compare: statements compared 567 -> 583** (of 827 statement documents in compare's count), periods+items
  1,445 -> 1,461, without disagreement 1,150 -> 1,150.
- CONTROL (bench/wave4-a152-ctl17: same copy, same code, rescored against truth-backup-pre-v17, compare to a private
  dir): 1,034/1,237, recoverable 1,034/1,233, wrong 0; the rescore re-pairs the SAME 30 batch items there too (none
  Synchrony: unmatched 11, santander 8, andrews 5, monex 3, merrick 2, bbva 1) and drops their proposal checks and
  simulated corrections. So the rescore's secondary figures differ from the original wave-4 run (actions 5,637 ->
  4,489, valid-looking wrong values 73 -> 9) for a reason unrelated to this truth (open for the integration session).
  **Attributable to the v17 truth, control vs new:** distinct periods 1,237 -> 1,253, not_detected 8 -> 24, actions
  4,489 -> 4,505 single / 4,330 -> 4,346 grouped (one per not-detected period), compared 567 -> 583; ready, recoverable
  ready, field edits, decisions, rows to add, valid-looking wrong values, unmatched items, ledger: identical;
  ready lost 0, gained 0.

## Live ledger (read-only audit audit-v17; READ ONLY transaction; nothing written)

- All truth documents: 813 admitted live periods: agrees 303, convention_only 412, **disagrees 6**,
  live_period_undated 91, no_truth_period 1, must_be_held 0. Same printed period admitted twice in a case: 0.
- **On v17 documents: 2 live periods (the investigator's two hand reconciliations), both `disagrees`:**
  d43853a185720#1 (2 rows) and d7f1c8c31414c#1 (4 rows). Both balances, every amount and every date equal truth;
  **every row's direction is inverted** (payment recorded as a debit, fees and interest as credits), i.e. the card's
  amount owed was kept as if it were a deposit balance. Money flows from these two periods run the wrong way.
  Re-checked row by row today in a separate READ ONLY transaction (6 of 6 rows inverted). The same card number is
  held in 2 live accounts (two institution labels). Row detail: private (tmp/v17/live-synch.txt).
- The previous 4 disagreeing periods (other families) are unchanged.

## For the wave-6 Synchrony reader (counts; real wording in PROGRESS-v17.md)

- Identity: issuer + holder on one printed line (holder in the right column), full card number after a labelled
  "account number" field, a labelled closing date. Start date never printed (16); days in cycle printed (16).
  Recommended start convention: as Merrick (start unprinted, closing-only period; `closing_only_period` exists).
- Summary box (16): 6 labels = previous balance, + new purchases, - payments, +/- credits/fees/adjustments (net),
  +/- interest (net), new balance; then credit limit, available credit, overlimit amount (11), days in cycle.
  The payment box to its right shares printed lines and repeats the new balance (16); past-due variant adds two
  more right-box lines (7). In engine sources the summary is one multi-line cell.
- Transaction table (16): header cells tran date / post date / reference / description / amount; body = one cell with
  newline-separated rows; sections main (payments, purchases), fees, interest; printed totals for fees and interest
  (16 each); a year-to-date block (3 money lines) inside the same cell that is NOT rows (16). Continued from printed
  page 1 to printed page 2 across the reverse-side image page (5).
- Sign: credits in parentheses, debits plain (16). Rows: payment 9, card-security fee 14, late fee 10, interest 13,
  purchase 1 (description wraps 3 lines). Zero interest line printed in 3 cycles (not a row). Cycles with no payment 7.
- Not rows: promotional purchase summary (7; prints a transaction date and dollar amounts), interest charge calculation
  table (16), payment coupon (16), change-in-terms notice pages (1 document, 2 pages).
- Controls the reader can prove against: all six summary lines + two section totals (every period).

## Tests actually run

- test_financial_benchmark_corpus + real_compare + real_visual + real_truth + statement_census: **101 OK**
  (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1, pdfplumber from headless/real/pylib). 4 new (synthetic).
- Synthetic benchmark (bench-runs/t-visual-v17-final, code 0e45c622): **105/125**, recoverable 105/108, 0 wrong,
  0 critical (354 rows), holds 10/10, copies 1/1, **BENCH_EXIT=0**.
- Full financial suite not run: no processor module changed.

## Next unit should continue with

- Wave-6 Synchrony reader (engine first, library fallback): measure against truth-mini-v17 (16 verified periods, 47
  rows). Must: closing-only period, one-cell row splitting by line, summary vocabulary, section totals as controls,
  year-to-date and promotional blocks excluded. Today 0/16 ready, 0 wrong.
- Remaining visual shards: v18 (wells-fargo fragment), v19 (navy-federal, 345 pages), v15/v16 (mt-bank), v01-v06,
  v09, v11/v12, v14.
- Integration: per-family tables gain synchrony-card 16 verified periods; the headline denominator is 1,253 until the
  next full read covers them.

## Decisions needed from Neil

- The 2 live Synchrony periods (case 49494305; live ids 717dc96d, 720217e5) have every transaction direction inverted
  against the printed statement (amounts, dates and balances are right). Recommend: re-enter or re-read them once the
  Synchrony reader lands (a live write: interactive session), and merge the card's two live accounts. Nothing in this
  unit waits on it.
