# fin/alex-queue: one review queue per case (investigator feedback 2026-10-13)

Base: fin/alex-1013 (9bee2d9d = a15230a0 + copies named before opening + continue open batch). Not pushed, not merged.
Live numbers: read-only probes (every connection `default_transaction_read_only=on` plus an ORM flush guard), case
49494305 unless stated. Opaque ids only. Private per-file detail: /mnt/owl-data/fin-real/alex/queue-*.json.

## Findings before building (reproduced on live data, read-only)

Case 49494305 holds 19 active batches with 4,374 prepared items, but only 1,115 distinct statements (file bytes +
statement key): the same statement sits in up to 4 batches. Projected statuses: 2,111 attention, 1,009 ready,
689 imported, 564 copies set aside, 1 left unimported.

1. Queue not clear / imported items in it. Screen: batch review ("Decisions needed before import" reason groups,
   "Show statements", "Save and open next problem"). Cause: `next_problem`, `statements_with_issues`, `issues_count`
   and the reason groups (`matches_group(<reason>)`) all count any item with `problem_count > 0`, including imported
   statements whose import kept its check history. 668 imported items (172 statements) are reachable that way.
   There is no per-case list: each of the 19 batches is its own to-do list over overlapping files.
2. "53 good, 1 to check" file. Screen: Files register card -> opening the file. The register opens the whole file
   (`openStatement(file.id)`) at its default statement, not at the period with work. Example files: c4ab842e
   (50 statements: everything saved except one period whose reading is empty) and 9889c7a5 (49 copies + 1 empty
   reading). Nothing tells her which period is the one, or what is wrong with it, before opening.
3. "138 records not in the system" (incomplete records). Screen: Transactions -> "Imported records with missing
   values". The per-record status exists ("Check amount" / "Values complete, checks out" / "held outside totals"
   + hold reason) and "Add N records that check out to Transactions" exists, but after "Save correction" an admitted
   record silently closes the editor and jumps to the transaction; nothing says "now in the ledger". 120 imported
   statements in this case still carry open incomplete records.
4. Duplicates / duplicate batches in the queue. Copies set aside are already outside the default filter (previous
   unit), but overlapping batches are not: the default "unfinished" walk across the 19 batches is 2,980 items for
   765 distinct unsaved statements. Possible copies needing comparison (20 statements) sit in the same lists.
5. Select all -> review reprocesses. Trace: Files register "Review and save selected files together" ->
   `POST /batches` -> unless an existing batch has exactly the same files (or, since alex-1013, an unfinished batch
   holds them all), a NEW batch is created in status `preparing` and the worker re-prepares every file
   (`advance_batch` -> `prepare_reviews` -> `read_statement_import` for every statement; 4 files per 30 s turn), i.e.
   minutes for 100+ files although every reading is stored. Even when an existing batch is continued, the batch
   view took 19.5 s (probe): 17.4 s of it in one query (`batch_pending`) that joined the evidence row to each of
   3,128 prepared periods and decoded its metadata 3,128 times (~107 MB). Opening one statement (`GET .../items/{id}`)
   paid the same query: 16 s median over 25 sampled items.
6. No cross-case answer to imported / not imported / needs review. Alexandra's batches: 6 cases
   (d5b330d1 50 batches/24 active, 49494305 19, fdaf956c 4, 267842f3 3, f887b0d9 2, 1c75e65e 1).
7. Hamster wheel (phantom checks). Measured three live states counted or labelled as work with nothing actionable:
   - P1: "Save and open next problem" targets 2,779 items; 668 of them (172 statements) are imported statements
     (review shows "Already saved... do not import again"), 140 are possible copies (another flow).
   - P3: "Next unfinished statement" (the default walk) is 2,980 items; 1,009 of them (214 statements) have no
     problem at all (ready to save; nothing to fix when opened).
   - P2: Files register "Needs action": 1 of 109 flagged files has checks only from saved or note-only periods.
   Stored vs fresh reading: 25 of 25 sampled queue candidates re-read with the same problem count (staleness is not
   a cause).


## What landed (commits on fin/alex-queue)
- b5a94bd0 backend perf: the batch read's pending query loads each evidence row once (was one per prepared period).
- 1a4db743 backend: `services/financial/review_queue.py` + `GET /api/financial/statement-import/review/queue`
  (`?file_id=` repeatable), `/review/status`, `/review/cases`; `needs_decision` in batch_review_summary; Next problem,
  `statements_with_issues`/`issues_count`, reason groups and the register's `periods_with_checks` count only unsaved
  statements with an actionable problem (saved check history, copies and notes no longer count).
- b2547faf frontend: Review queue section + status line + "All financial cases"; queue entries with their sentence;
  open lands on the statement (row, or `page:N`, or detail field) with "To fix: ..."; client-side Next/Previous;
  plain save outcome; register "Review the selected files (N)" opens the filtered queue (no batch, no reading) when all
  are prepared; per-file "Review N statements with issues in this file"; batch "Next statement with something to fix".
- ea4912a4 records kept outside totals: one-line status per record, per-row "Add to ledger", result line after a fix
  ("Imported: now in the ledger" / "Saved but held: ... One more step: ..."); complete-record returns `admitted`.
- f6f43377 queue fix for statements saved outside batches (crashed on case fdaf956c in the live probe); batch read
  reuses the comparison's duplicate fingerprints.

## Before / after per point (live, read-only)
1. Queue = only decisions. 49494305: 4,374 batch items / 19 batches -> one queue of 436 statements, each with a
   sentence (currency 194, balance 100, bank 83, reading 33, holder 19, no activity 4, assignment 3). Imported 177,
   ready to save 214, copies 172 (152 set aside + 20 to compare), couldn't read 115 statements + 2 files, left
   unimported 1, unexplained 0.
2. One statement, not the PDF: each entry opens its own batch item (statement key) at its row/page; entries say
   "statement k of N in this file". A file with N-1 saved + 1 to check yields exactly one entry (c4ab842e: 1 entry,
   under Couldn't read since its reading is empty).
3. Phantom checks (opened as work, nothing to act on), before -> after:
   - Next problem targets that were saved statements or copies: 49494305 808 items (192 statements) -> 0;
     d5b330d1 161 -> 0; 267842f3 116 -> 0; 1c75e65e 53 -> 0; fdaf956c 16 -> 0; f887b0d9 7 -> 0.
   - Default "unfinished" walk with nothing to fix: 49494305 1,009 items (214 statements) -> 0 (button now walks
     needs_decision); f887b0d9 1 -> 0.
   - Register files flagged Needs action with nothing behind them: d5b330d1 74 -> 1, fdaf956c 7 -> 0,
     49494305 1 -> 0, f887b0d9 1 -> 0. (The one left in d5b330d1: a file whose register summary still has a check
     but whose queue projection has no entry; not investigated.)
   - Queue entries without an actionable problem: 0 in all six cases. Tests: test_financial_review_queue
     (`test_every_waiting_statement_has_an_actionable_problem_and_a_sentence`, exhaustive over problem combinations)
     and ReviewQueuePanel.test (every listed entry renders its issue).
4. Select ~100 files -> review. Before: a new batch re-prepares every file (measured ~1.2 s of reading per statement;
   a 51-statement file 60 s; the case's 1,115 statements ~21 min of reading alone, at 4 files per 30 s worker turn),
   or, when an existing batch was continued, the batch view took 19.5 s. After: no batch, no reading; the filtered
   queue (100 files) answers in 4.0-4.6 s cold and ~0.4 s when the case is unchanged since the last read (cache keyed
   by the register's row fingerprint); Next is instant (client-side). Batch view 19.5 -> 4.6 s; opening one statement
   16 s -> ~3 s. TARGET <2 s COLD NOT MET: the remaining ~4 s is the existing projection (pending comparison ~1 s,
   duplicate/geometry fingerprints ~1 s, projection ~1 s, summaries JSON ~1 s).
5. Fix outcomes: queue save says "Imported: now in the ledger (N payments)" or "Saved but held: K records ... One more
   step: ..." and the statement leaves the queue on refresh; records list states each record's status and offers
   per-row Add to ledger when it checks out. 120 imported statements in 49494305 still carry open records (unchanged;
   no admission rule touched).
6. Status line per case (same buckets as the queue) on Statements & accounts and in the queue; "All financial cases"
   lists cases with batches the user can view, each line loaded from /review/status. Live counts:
   49494305 imported 177 / waiting 436 / ready 214 / copies 172 / couldn't read 117; d5b330d1 480/156/0/37/232;
   f887b0d9 357/78/1/9/2; 267842f3 58/0/0/0/0; 1c75e65e 53/0/0/0/0; fdaf956c 14/0/0/0/0.
7. See 3.

## Tests run
- Backend (CHROMADB_PORT=1 CHROMA_PORT=1): review_queue 52, import_batches + batch_read_* + pending_duplicates +
  batch_duplicate_overview + batch_review_summary + batch_statement_summary + statement_file_status +
  duplicate_file_status: all pass (185 + 136 in the runs); statement_import_router 23; late_posted, record_withdrawal,
  statement_admission, optional_import_review 41.
- Frontend (run as conorbowles51, tsc -p with --incremental false so nothing is written to the shared node_modules):
  tsc app + node clean; vitest unit ReviewQueuePanel 6, ImportedRecordsPanel 10, FinancialBatchPanel,
  StatementFilesPanel, FinancialPage pass; full financial unit run 214 files / 1,687 tests pass; vite production build
  (to /tmp, as conorbowles51) passes. `npm run build` itself was not run because it writes tsbuildinfo into the shared
  live node_modules/.tmp and dist/ into this root-owned tree.

## Not done / not verified
- Not click-tested in a browser over the server IP. Browser project (FinancialBatchRecovery updated for the renamed
  button) not run.
- Cold queue read is ~4 s, not <2 s.
- Queue does not save ready statements itself: "Save N ready statements" opens their batch's ready filter.
- Currency entries are focused on the statement but the currency control is not auto-focused.
- One register/queue disagreement left in d5b330d1 (see 3).

## Decisions for Neil
1. Make "Review queue" the default section of Statements & accounts (today: Statement files stays default)?
2. Save ready statements straight from the queue across batches (needs a per-statement save path, not the batch's
   whole ready revision)?
3. Previous-unit decisions 1-4 still stand.

---

# Previous unit (fin/alex-1013) notes


Base: a15230a0 (deployed head). Not pushed, not merged.

## Commits
- 7936ec8f backend: batch `file_overview` + copies sort last + unfiltered Previous/Next skip copies; file register
  counts a system copy as ignored only while its stored readiness matches current inputs (same test as the batch
  read); `POST /batches/preview` (open batches sharing the files + copies: identical bytes, or statements already set
  aside); `create_batch(start_new=False)` continues an unfinished batch that holds every selected file.
- fca92081 frontend: "Copies found before review" section + per-statement "Copy of <file> p.N" badge in the batch
  review; file cards say "All N statements are copies of <file> — nothing to review" / "N of M are copies";
  `BatchStartChoice` before a batch starts (Files register + Choose from Evidence): continue is the default button,
  "Start a fresh batch with all N files" is separate; files the open batch lacks get their own batch; copies named,
  with "Leave the N files of copies out".
- (this commit) docs/financial-workflows/ingestion-simplification-2026-10-13.md + these notes.

Nothing is deleted or auto-rejected; a copy is only what the batch read already shows as `duplicate_ignored` with a
current ignored disposition. Outdated records stay work (test: new reading of the copy -> check again).

## Before / after (case 49494305, batch f6f7cd42, read-only probes)
- Batch default to-do ("unfinished"): 702 of 824 before and after (copies were already outside this filter).
- Unfiltered Previous/Next: stepped through 824 -> now 722 (102 copies skipped; still listed, still openable).
- File register, files of this batch flagged Needs action: 107 files / 833 prepared periods -> 106 / 780. The 53/53
  copy file (opaque 5c4cf2dd) was 53 "checks" with no investigator decision on file; it is now 53 ignored and leaves
  Needs action. The 49/50 file (9889c7a5) stays in Needs action for its one other period and its card now says
  "49 of 50 statements are copies of <file>".
- Batch overview: 107 files, 2 only-copies (53 + 49 statements), 0 partly-copied in this batch; copies sort last.
- Preview on the same 109-file selection: suggests open batch c77b6f54 (6 Oct, holds all 109, 401 unfinished);
  408aef0b holds 107/109; both copy files named ("statements_already_copies", retained file named).
- Timing (probe process, cold, same machine, before via stash vs after; absolute values are not comparable with the
  live server): batch view 16.0–17.7 s -> 15.3–19.6 s (noise, no extra queries: overview is built from projected
  items); register uncached 3.0–3.5 s -> 3.6–4.5 s (+~0.5 s for validating copy records of the copy files; the
  live register is cached by fingerprint); batch list code path untouched (17.9 s -> 18.0 s warm in the probe);
  preview 1.4 s.

## Tests run
- Backend (CHROMADB_PORT=1 CHROMA_PORT=1): new tests/test_financial_batch_duplicate_overview.py 8 passed; related
  modules 172 + 204 passed (import_batches, batch_read_stored, batch_read_projection, duplicate_file_status,
  statement_file_status, pending_duplicates, batch_review_summary, batch_statement_summary, file_intake,
  batch_import_history, checkpoint_b_gate, file_scope, graph_followup, import_removal, optional_import_review,
  statement_census, statement_currency, statement_import_bbva, statement_import_router, statement_overlap).
- Frontend: tsc -b clean; vitest unit project over src/features/financial 213 files / 1681 tests passed (incl. new
  picker, files-panel, batch-panel and card tests); `npm run build` passed.
- Browser project (PLAYWRIGHT_BROWSERS_PATH=/home/conorbowles51/.cache/ms-playwright): FinancialBatchNavigation,
  DuplicateRegister, FinancialBatchLoading pass; StatementDuplicateIntegration has 2 failures that fail identically
  on the base without these changes (pre-existing, not investigated).

## Not verified
- Not click-tested in a live browser over the server IP.
- Evidence-level exact-byte duplicates (case fcc9d6b9 social-media export) not touched.

## Decisions for Neil
1. Server default: `POST /batches` without `start_new` now continues an unfinished batch that holds every selected
   file (previously only an identical file set). Keep?
2. Save fully reconciled, check-free statements without a click (report rank 6)?
3. Currency proposal (report rank 1: printed code, then same account's saved statements, then case default) — 299 of
   532 blocked statements in the example wait only for currency.
4. Hide (not delete) batches whose files are all in a newer unfinished batch (report rank 4)?

## Next
Report ranks 2 (auto-start batch after upload reading) and 7 (automatic refresh/additional periods) are cheap.
