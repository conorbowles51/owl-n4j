# t-visual-v15 — WIP notes (counts and opaque ids only)

Unit: visual ground truth for visual-queue shard v15 (`mt-bank`: 40 documents, 91 pages, case d5b330d1 production)
and the first BLIND measurement of this bank (no family reader; engine + the r4/r5 `mt-bank` institution profile,
untuned). Branch fin/t-visual-v15 from fin/release-1 28a09287. Not pushed. **No processor code changed** (benchmark
truth tooling only). Private detail: /mnt/owl-data/fin-real/truth/visual/PROGRESS-v15.md (conventions, per-document
status, blind-read findings with document ids), truth/visual/<doc>.txt|.json, tmp/v15/ (renders, tesseract typing
aid, contact sheets, chk/hdr/sheet helpers, mini-compare), logs/v15-*.log, truth-mini-v15, bench/v15-mini (blind
fresh read), bench/wave5-v15 (rescore copy; results-rescored.json / summary-rescored.md), audit-v15;
backups truth-backup-pre-v15/, compare-backup-pre-v15/.

## Landed (commits)

- 0fd5a12f — real_visual: `subcount <section> <n>` (a printed per-section item count must equal the section's rows)
  and `kind` inside a share (a line-of-credit statement mailed inside a deposit statement's envelope is a card-kind
  period). 2 synthetic tests (both fail on the old parser).
- (this commit) WIP-NOTES.md.

## Classification and truth (steps 1-3)

- Every page of all 40 documents read from rendered images (fitz, 110 dpi; 300 dpi crops where a digit sat at a
  redaction edge). Tesseract text was available as a typing aid only; every value was taken from the image.
  Non-first pages were classified on contact sheets, and every page carrying a value was read at full size.
- **Documents by final status: verified 40.** not_statement 0, duplicate 0, incomplete 0, unverified 0.
  Page kinds (91): statement pages 50 = 40 first pages + 8 continuation pages (3 with rows, 1 checks-paid summary,
  4 notice-only) + 2 line-of-credit pages; printed reverse sides (balancing instructions / credit terms) 41, all `skip`.
- **Periods: 41, all verified** (money market 14, checking 26, line of credit 1). Rows 415. Duplicates 0
  (no two documents carry the same printed period). Incomplete 0, unverified 0.
- Each verified period: opening + every row = closing to the cent; every printed daily balance matches the running
  balance; every printed section total AND count in the account summary matches its rows (deposits, checks paid,
  other debits, interest; line of credit: loans, payments, fees, interest). Checks-paid summaries (2 documents)
  restate the check rows exactly.
- Independent cross-check: per account, every pair of periods adjacent in date chains (opening = previous closing):
  18 adjacent pairs, all chain, 0 contradictions. The date gaps between them are statements not in this shard (v16 has 45 more).
- **Expected: auto 41, decision 0.** Holder name printed on every period, account number printed (last 4 digits),
  period dates and currency printed.
- **Redaction (counted per period, detail private):** 41/41 periods have the holder's address redacted (the name
  block is printed without an address); 41/41 print the account number as its last 4 digits only (2 show a clipped
  digit at the redaction edge). No fact a period needs is redacted, so no period is `decision` for redaction.
- **Statement documents final: 603/832 -> 643/832.** Status over 832: verified 618, settled 2, unverified 18,
  not_statement 5; pending needs_visual 173, needs_parser 13, partly_verified 3. Truth periods verified
  1,402 -> 1,443. visual-queue.json: **v15 done (40/40)**; queue done 108 -> 148.
- Conventions decided here (each reversible by editing the private transcriptions and recompiling):
  1. Joint holders: truth holder = the first printed name line (the comparison is a substring test; any reading that
     contains the primary holder agrees). Reverse: put all name lines in the holder.
  2. Account printed as its last 4 digits (the producer's redaction) counts as printed -> expected auto (as card
     statements printing "ending in"). Reverse: mark account unprinted -> 41 periods become `decision` (account).
  3. A line-of-credit statement in the same mailing is its own period, kind card (balance owed). 1 period.
  4. Printed reverse sides and notice-only continuation pages carry no values (skip / continuation without rows).

## BLIND processor measurement (step 5; code 0fd5a12f = fin/release-1 processor, no tuning)

Mini corpus truth-mini-v15 (40 PDFs, 41 periods), fresh read, run_real_benchmark --concurrency 2, OMP_THREAD_LIMIT=1,
compare into tmp/v15/mini-compare (private):
- **Ready 0/41. Wrong admissions 0.** Critical-field errors 0, valid-looking wrong values proposed 0, batch items
  matched to no truth period 0. Engine-served 0, library-served 0 (nothing ready; no family reader exists for this
  bank, so every reading is the general engine's).
- Held, with reasons (overlapping): holder 40, reading 15, balance 15, institution 11, account 1.
  Actions 600 single / 524 grouped (field edits 432, decisions 1, rows to add 63).
- **Identity against truth (all 41, field by field):** period start 41/41 equal, period end 41/41, currency 41/41,
  account 40/41 (1 unread), opening balance 36/41 (5 unread), closing 39/41 (2 unread), holder 0/41 (40 unread,
  1 differs). Rows: 415 in truth, 243 matched exactly, 0 differing; 172 missing / 161 extra all in 15 periods.
- **Two classes, both fail closed:**
  1. **26 periods: every field except holder and every row equal to truth -> held for the holder alone.** Root cause
     from source: `statement_engine.address_holder` (statement_engine.py:1255) takes the holder only from the top line
     of an address block that ends with a postal-code line (or from a label). The production redacts the address, so
     the printed name block has no postal line and no holder is read. One grouped holder confirmation per account
     (2 accounts) would admit these 26.
  2. **15 periods (14 documents): rows found but every row's date, amount and direction unread** (0 of those rows
     carry a value), with 5 openings and 2 closings unread. Not explained by document mode (image-only 8, mixed 7) or
     by the money-cell verification outcome. The reader unit should diff these against the 26 same-layout documents
     that read cleanly.
- Only 1 non-empty value disagrees with truth in all 41 periods: the line-of-credit period's holder was read as the
  bank's own remittance-coupon line. Held (its account and balances were unread too); not admitted.

## Rescore of the bench of record with the new truth (no re-read)

Copy bench/wave5-v15 of bench/wave5 (ef0877d6 readings), harness --rescore at 0fd5a12f, compare/ shared:
- **1,118/1,294 ready** (was 1,118/1,253: denominator +41 = the M&T periods, `not_detected` by absence because
  wave 5 never read them), recoverable 1,118/1,290, **wrong 0**, critical 0 (17,085 rows), held kept out 4/4, exact
  copies 148/151, unmatched items 18 (0 offered). Ready lost 0, gained 0.
- **Compare: statements compared 583 -> 623** (of 827 in compare's count), periods+items 1,442 -> 1,483, without
  disagreement 1,263 -> 1,263.
- The rescore re-paired 13 batch items (unmatched 5, andrews 3, bbva 2, monex 2, santander 1; **0 M&T**: wave 5 has no
  M&T items) and dropped their proposal checks and simulated corrections. This is the same rescore artefact
  t-visual-v17 isolated with a control run. So these secondary figures moved for a reason unrelated to this truth:
  actions 3,785 -> 3,022 single, 3,638 -> 2,885 grouped; rows to add 799 -> 461; valid-looking wrong values 68 -> 12.
  Control not re-run here (about 2 h at the current load). The headline figures (ready, recoverable, wrong, lost)
  do not depend on proposals and are unchanged.
- "Duplicate ledger contributions 1,180" is printed identically by bench/wave5 itself; not from this unit.

## Live ledger (read-only audit audit-v15; READ ONLY transaction; nothing written)

- **On v15 documents: 0 live admitted periods** (nothing from these 40 documents is in the live ledger), so 0
  disagree and 0 must be held.
- All truth documents: 813 admitted live periods: agrees 303, convention_only 413, disagrees 5 (the same 5 as
  wave 5), live_period_undated 91, no_truth_period 1. Same printed period admitted twice in a case: 0.

## Tests actually run

- test_financial_benchmark_corpus + real_compare + real_visual + real_truth + statement_census: **103 OK**
  (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1, pdfplumber from headless/real/pylib). 2 new (synthetic).
- Synthetic benchmark, run 1 (bench-runs/t-visual-v15-final, code 0fd5a12f): **104/125**, 0 wrong, 0 critical,
  holds 10/10, BENCH_EXIT=0. The one period below 105 (generic-11, damaged-OCR running-balance case): its
  second-reader repair was declined with "Tesseract process timeout" (load average 9.7-13 on 6 cores during the
  run); same input and same processor code as the 105 run (git diff vs 28a09287 touches only real_visual.py and
  its test). Held, never wrong.
- Synthetic benchmark, run 2 (bench-runs/t-visual-v15-final2, same code): **105/125**, recoverable 105/108, 0 wrong,
  0 critical (354 rows), holds 10/10, copies 1/1, **BENCH_EXIT=0**; generic-11 ready again (the timeout did not recur).
- Full financial suite not run: no processor module changed.

## Next units should continue with

- Reader unit for `mt-bank` (engine first): (1) holder from a name block printed without an address (26 periods
  wait on this alone); (2) the 15 periods whose rows are found but unread; (3) the line-of-credit page (holder taken
  from the remittance coupon). Measure against truth-mini-v15 (41 verified periods, 415 rows). Today 0/41, 0 wrong.
- Truth coverage: shard v16 (the other 45 M&T documents: the chain gaps above), v18 (wells-fargo fragment),
  v19 (navy-federal, 345 pages), then v01-v06, v09, v11/v12, v14.
- Integration: per-family tables gain mt-bank 41 verified periods; the headline denominator is 1,294 until the next
  full read covers them.
- Synthetic timing: the second reader's tesseract timeout under heavy shared load can cost a synthetic period
  (held, not wrong). Consider running the synthetic gate when the box is quiet, or a longer timeout for it.

## Decisions needed from Neil

- None blocking. Decided here with reasoning: a holder name printed without an address is still the printed holder
  (truth `auto`). The processor currently refuses it by design. Recommendation for the reader unit: accept a name
  block in the addressee position when the same block is reprinted on the statement's continuation pages, and keep
  the grouped confirmation as the fallback. Reverse: leave holder-only periods to the grouped confirmation (one per
  account).
