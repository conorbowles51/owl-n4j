# r7-alex-queue: Alex's feedback on case d5b330d1 (2026-10-15)

Branch fin/r7-alex-queue (base fin/release-1 e066836b). Not pushed, not merged. Counts and opaque ids only;
private detail under /mnt/owl-data/fin-real/alex/r7/ (probe scripts, queue dumps, readings, sub-corpus runs).
Live numbers: read-only probes (every connection read only + ORM flush guard). "Live code" = the live checkout
e47c25c5. The unit's prompt counts (03:00) had moved by the time it ran: Alex started a 1,452-file batch at
06:07 that was still preparing all day (1,232 of 1,452 read at 17:40).

## What landed (commits on fin/r7-alex-queue)

- 1f75fd8a carry the live queue filter (frontend of e47c25c5: ReviewQueuePanel + BulkStatementDetails) onto this
  branch; both files were unchanged on the base, so the integration merge sees the identical change. Its
  docker-compose.yml hunk (deploy config) is NOT carried.
- b4e98687 queue (item 2): failed preparations of files removed from Financial ('removed'), no longer in the case
  ('gone') or whose identical bytes were read from another upload ('copy') leave "Couldn't read"; new counts
  removed_files / copy_files, list set_aside_files with a plain sentence each; status line "Files removed from
  Financial N" / "Files already read from a copy N"; collapsed section in the Couldn't read list.
- 5d66173a evidence engine (item 4): job-status writes and the stored reading retry a deadlock / serialization
  failure (db_retry.retry_transient, 5 attempts, backoff); a progress write that still loses is skipped. A page
  whose OCR times out is kept unread (ocr_status 'timeout', no text) instead of failing the file; other OCR errors
  still fail it. Backend unread_pages: statements whose pages could include an unread page are held with "Page N of
  this PDF could not be read in time ... Read the file again" (page inside another statement: only that one;
  between statements: both neighbours; no known statement: all).
- 5ff6a462 item 3: a saved batch draft from an earlier, incompatible reading is no longer checked row by row
  (that raised the misleading "A manually added transaction needs a page from this PDF"). assess() checks the new
  reading as read, keeps the earlier statement details (holder, account, bank, dates; never rows), holds it with
  kind 'earlier_reading_review' -> queue reason saved_review. The statement view shows a batch draft from an
  earlier reading in the existing "The reading changed after this review was saved" comparison ("I have compared"
  required), as individual reviews already did.
- 7b877d0b engine (item 1): a vector-text page whose character outlines run left to right is read at rotation 0
  without orientation detection (vector_glyph_reading.drawn_upright: >= 50 left-to-right steps, >= 2x either
  vertical direction, >= 10x right-to-left). Reading revision bank-payment-rows-v19.
- 02c56c3d general engine: a bare currency code in a section heading must be printed in capitals ("Ci cad de
  Mexico" was proposing CAD for a peso statement; "SA DE mn" folded to MN).
- 0e4dad26 engine: Santander closing-box reread ignores a trailing page-edge mailing mark ('*') in its crops.
- dd37b077 engine: outline labels learn from OCR words with an extra end mark (column rule read as ')'), and an
  amount whose comma gap exceeds SPACE_GAP_SHARE stays one word within AMOUNT_JOIN_GAP (Kapital).
- 85767b79 engine: money-cell crops on a shaded band (paper < 230) scale the ink thresholds to the cell's paper
  tone (90th-percentile luminance); white/off-white cells unchanged; 4-of-6 rule unchanged (Santander grey
  'SALDO FINAL DEL PERIODO ANTERIOR' band, paper 164).

## Findings (live, read-only)

1. Missed balances. Live code lacks waves 5/6 (r6-vector-text etc.); most balance-blocked Santander/BBVA/Kapital
   files are vector-outline pages. On fresh readings four engine causes remained: (a) orientation detection turned
   upright vector pages 90/180 degrees (63 pages in 48 of Alex's balance files; 27 pages / 20 docs in the wave-6
   truth set), skipping the outline reading and losing the Santander closing box; (b) the closing-box reread
   rejected crops ending in the page-edge mailing mark; (c) the Santander opening on a grey band could never be
   confirmed by the money check; (d) Kapital amounts against a column rule read as '...)' left the page's figures
   unlabelled.
2. Every stored "Statement not found in this case" failure (126 across 10 batches) and every "restart source
   unavailable" one (207 at 12:00) belongs to a file removed from Financial in September (2026-09-22/23) that an
   older batch still lists or that the 06:07 batch swept in.
3. "A manually added transaction needs a page" (16 live entries): stale batch drafts of an earlier reading (4,896
   excluded rows the new reading no longer has; 15 genuine manual rows, all with valid pages).
4. "PDF source preparation failed": all 31 in the PDF worker's log (24 h; 30 in the earlier 72 h window) are Postgres
   deadlocks on the per-case audit advisory lock during the large batch, not OCR. No OCR-timeout failure is logged
   since the worker started. Pages with a usable digital text layer are never OCR'd (4,324 + 84 such pages in the
   two reading sets, all native); "suspicious_text_layer" OCR is only for layers with >2% broken characters.

## Before / after (counts)

- Item 1, d5b330d1 live balance-blocked statements (noon dump): 104 (93 "opening or closing balance not read").
  After this branch + re-read, per statement: ready 49, held for another reason 14, still missing a balance 41.
  Of the 49, 30 are already ready with fin/release-1's readers at reading v18 (waves 5/6, not deployed); 19 come
  from this unit. Still blocked 41: Santander 18 (both balances now read on 11; held by unreadable payment rows,
  worded as a balance problem), BBVA fund statements / annotated scans 15 (general engine does not prove them:
  'FONDOS DE INVERSION' holdings statements and scans with handwritten ticks over a right-cut summary), Santander
  holder 6, other 11.
- Across all cases (live, 17:40): balance-blocked d5b330d1 122 (111 not read), 49494305 111 (Andrews 89, Navy
  Federal 12, Credit One 7; not in this unit's bank list, not measured after), other 4 cases 0.
- Alex's 98 balance-blocked files (151 statement choices), this branch's reader: v18 readings 46 ready / 80
  balance-missing -> final readings 81 ready / 51 balance-missing. Santander movements ready 5 -> 37. Without truth
  (needs_visual): 43 month-to-month chain pairs with a ready side, all closing = next opening, 0 disagree; 3
  statements checked by eye against the printed page-1 summary, all equal.
- Item 2, d5b330d1 queue (this branch, live data 12:20): unreadable_files 228 -> 11; removed_files 212, copy_files 6.
- Item 3: 16 entries; the new wording appears when each statement is next assessed (stored summaries are not
  recomputed by a version bump; opening the statement re-assesses it).
- Item 4: the 31 deadlock failures retry instead of failing; per-page timeout keeps the file (no live timeout case
  to count).

## Verified

- Truth (every truth document whose reading the engine changes can alter: vector-text docs, Santander OCR docs,
  rotation-affected, shaded money cells: 106 docs, 224 periods), wave-6 readings vs new readings, both scored with
  this branch's code, FINANCIAL_AUTO_SAVE_READY=0: ready 133 -> 134, 0 previously ready lost, 0 wrong admissions,
  0 critical-field errors (1,414 rows), valid-looking wrong values 4 -> 3. Other truth documents' readings cannot
  change (deterministic OCR, code paths untouched); the heading-currency change was checked on the 3 truth docs
  with a non-capital code line: d22e6c134f682 3/3 still ready, the other two are in the measured set.
  Projected whole set: 1,146 -> 1,147 / 1,294, 0 wrong.
- Synthetic (bench-runs/r7-alex-queue-final, code 93d2843e = 85767b79 minus a test-only rewrite, FINANCIAL_AUTO_SAVE_READY=0): 105/125, 0 wrong, holds
  10/10, copies 1/1, 0 valid-looking wrong values (unchanged).
- Tests (backend CHROMADB_PORT=1 CHROMA_PORT=1 FINANCIAL_AUTO_SAVE_READY=0): review_queue 59, import_batches 91 + 2
  new, statement_import + batch_review_summary + reading_retry 51, unread_pages 6, statement_engine 134,
  queue_save/field_proposals/auto_read/statement_admission/statement_file_status/batch_statement_summary/
  optional_import_review 181 together, statement_import_router 23; final rerun on the final code:
  import_batches + review_queue + unread_pages + statement_engine 291 OK.
  Engine (pytest): prepare_pdf_review 9, chunk_publication+document_summary+ingestion_isolation 18,
  pdf_extraction 36, vector_glyph_reading 26, financial_santander_ocr 17, statement_money_verification 30.
  Frontend (as conorbowles51, tsc --incremental false): tsc 0; vitest unit ReviewQueuePanel 10,
  StatementImportPanel + FinancialBatchPanel 104; eslint on changed files: 2 errors, both pre-existing
  (ISSUE_LABELS export from e47c25c5, test `location` reassignment). No root-owned files left in node_modules.

## Not verified / open

- Not click-tested in a browser; browser vitest project not run.
- Live effect needs deploy + re-read of the affected files (engine reading revision v19); live readings are v17/v18.
- Remaining Santander holds (11 with both balances, unreadable payment rows) are worded "Enter one opening and one
  closing balance ... and complete every selected payment": next unit should split that sentence so a row problem
  is not shown as a balance problem, and look at the rows.
- BBVA 'FONDOS DE INVERSION' statements need a holdings-statement reader (units x price); not built.
- The 16 stale-draft entries keep their stored wording until reassessed.
- The queue cold read takes ~25-47 s on d5b330d1 at 2,000+ statements (not addressed here).

## History note

The branch history was rewritten once before any push (it never left this machine): two tests and two commit
messages had carried real amounts and a word of a real company name from Alex's statements; they now use synthetic
values. Non-test code is byte-identical to what was measured (old head 93d2843e, new head 85767b79).

## Decisions taken (each reversible in one place)

1. Removed / gone / copy failures are set aside, not hidden: listed with their original error. Reverse:
   review_queue._failed_files ignores set_aside.
2. Stale drafts: new reading checked as read + held, earlier details kept (rows never). Reverse:
   import_batches.EARLIER_READING_FIELDS / the earlier_reading branch in assess.
3. Upright rule thresholds (50 / 2x / 10x) from 515 + 391 measured vector pages. Reverse: drawn_upright -> False.
4. Shaded paper limit 230. Reverse: GREY_PAPER = 0.
5. Reading revision bumped to v19 (engine output changes on vector and shaded pages).

## Needs Neil

1. Deploy waves 5/6 + this branch and re-read d5b330d1's Santander/BBVA/Kapital files (live write): 49 of the 104
   balance-blocked statements become ready on this measurement.
2. The 1,452-file batch swept in 207 files removed from Financial; whether a folder selection should skip removed
   files (r7-import-ops area) is a product decision.
