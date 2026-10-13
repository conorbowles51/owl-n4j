# fin/s-queue-actions: queue as the one work list, save from the queue, auto-save, hidden old batches (2026-10-13)

Base af76b2ac; fin/s-inference merged in (65e23d00), its WIP-NOTES.md dropped (see its own worktree). Not pushed.
Live numbers: read-only probes (connections `default_transaction_read_only=on` + ORM flush guard; the backlog
CLI's dry run uses `SET TRANSACTION READ ONLY`). Opaque ids only; private detail in
/mnt/owl-data/fin-real/alex/s-queue-actions/. Timings were taken on a shared box at load average 9-14 on 6 cores,
so absolute seconds are high; compare within a row.

## Commits (in release order)
1. 303824c3 Review queue is the DEFAULT section of Statements & accounts. Files list: Needs action, ready count,
   "checks to review" and per-file links count from the queue (`queueFileWork`); a prepared file is flagged only when
   the queue lists work for it (waiting, couldn't read, ready); "Review N waiting in the queue". Opened batch: banner
   with the queue's counts for its files + "Review N in the queue"; from a batch statement, "Next statement with
   something to fix" continues in the queue over the batch's files. Batches stay viewable as history. Queue response
   also lists `ready`.
2. b3725081 Save from the queue: `POST statement-import/review/save` (`services/financial/queue_save.py`,
   `save_statements`) + `GET review/save-result`. Same admission as the batch save (fresh projection,
   `validate_reviews=True, reading='all'`, `import_available`), one receipt per batch (`claim_ready`, factored out of
   `queue_import` unchanged), the batch worker imports as after a batch save (strict writer under the case lock,
   existing bounded retry for temporary failures). Held with a plain reason: already saved / being saved through
   another batch, requested twice, paused or removed batch, anything the checks hold (the queue sentence). Idempotent
   per request id. UI: "Save N ready statements" and "Save all N ready statements" (status line) save in chunks of 10
   and end with one line "N imported, M held: reasons". Files list ready box saves from the queue (no new batch).
3. 2d8bdf20 AUTO_SAVE_READY (`queue_save.AUTO_SAVE_READY`, env `FINANCIAL_AUTO_SAVE_READY=0` turns it off; default
   ON): when a file's preparation ends (`_review_file`), its statements that are ready under the batch save's
   admission with NO check at all (not even a note) and no investigator edit or draft are claimed with actor System
   (ordinary import receipt; reversible with the existing import removal). Fires only from preparation, so nothing
   read before deploy is touched on deploy. Backlog: `backend/scripts/financial_save_ready_backlog.py` (dry run
   default, read-only; `--check` runs the full admission read-only; `--apply` claims as System in chunks; `--case`;
   `--fill`; idempotent). Test suite runs with the flag off (tests/conftest.py) except its own tests.
4. 203033f0 Superseded batches hidden: `batch_supersession.superseded_batches` flags a batch whose statements
   (bytes + key) are all in a newer batch or already saved, not preparing/saving, files all covered; list hides
   them behind "Show N older batches". Nothing deleted.
5. 50c7b21c Single-field issues focus their control: queue entries for currency and bank now carry `field`
   (currency/institution); a currency entry opens and focuses the currency choice, a bank entry the Bank input.
6. 966ff6e2 The d5b330d1 Files-list vs queue mismatch (below), fixed in the register.
7. 109fc6da (coordinator) queue save and AUTO_SAVE_READY call `apply_confirmed_proposals(apply=True)` first:
   `POST review/fill` (queue `filled` + waiting entries with confirmed proposals), ready-after-fill statements join
   the save; the auto-save fills confirmed details of the just-prepared file (the worker's own lease is not a
   conflict: `bulk_statement_details.save(owned_batch_id=...)`). A System fill is not an investigator edit
   (`system_filled_only`: saved review authored by System and equal to the item's request).
8. 21376fa7 (coordinator) status line "Details filled automatically N" opens its list: each statement shows the
   value(s) and source, "Open to change"; included in "Save all N".
9. ecb27ef4 (coordinator) one-click proposal ("Proposed: USD (source)" + "Use USD") in the single-statement currency
   control (focused on open for a currency issue) and in BatchCurrencyEditor ("Use USD for N statements", focused
   when it opens, saves through the existing currency save).
10. 5e659849 Queue cold load: cache fingerprint fix + precompute after writes (below).

## Before / after (live, read-only)
- Queue as default + one work list: Files "Needs action" for prepared files now equals queue work by construction;
  per-file count text = the queue's count.
- Save from the queue, 49494305: before, "Save N ready" opened each of the ready statements' batches (214 ready
  statements across several batches, one batch save each). After: one action. Admission cost measured on 20 ready
  statements: 47.9 s (2.4 s/statement at this load) -> chunk size 10 (~25 s per request, locks held briefly);
  all 20 still ready, all 20 fully reconciled, 0 with edits.
- Backlog dry run (all cases): ready 215 (49494305 214, f887b0d9 1 [the f887 case's batches have since disappeared
  from the live DB, see below]); candidates (no stored check, no edit) 214; `--check` full admission on 49494305:
  would save 214, hold 0. Nothing applied.
- Superseded batches flagged: 49494305 13 of 19, d5b330d1 5 of 24, fdaf956c 3 of 4, 267842f3 3/3 and 1c75e65e 1/1
  (fully imported; already hidden as completed). Check cost 0.1-0.6 s on the batch list read.
- d5b330d1 mismatch: register files with a check and no queue work: 15 -> 14 after the fix; the 14 remaining are
  possible copies that need a comparison (the queue lists them under Copies, the register as a check) - a
  deliberate difference; the Files list no longer uses the register's check count for prepared files.
- Queue load (case_review_queue through the cache):
  - repeat opens BEFORE: d5b330d1 open after open 17.3 s (cache missed); fingerprint sampled 7x over 140 s with no
    data change differed 3 times. AFTER: 49494305 6.1 s first then 0.15-0.56 s; d5b330d1 18.1 s first then
    0.18-0.52 s (six opens 10 s apart each).
  - cold build (a real change): unchanged, 6-11 s (49494305) / 18-44 s (d5b330d1) at this load; previous unit measured
    ~4 s on 49494305 on a quieter box. Profile (49494305, 11.2 s): pending comparison inputs 2.4 s (every pending item
    and its JSON), stored-readiness fingerprints 1.8 s, comparison 2.6 s, duplicate context 1.0 s, JSON decode 2.1 s
    overall. TARGET <2 s COLD NOT MET; mitigated by precompute: the batch loop's 60 s sweep rebuilds (20 s budget)
    the cache of cases opened in the last 15 min whose fingerprint changed (`review_queue.PREWARM`), so an open after
    background work is normally a hit. A save by the investigator still makes the next refresh cold; the queue keeps
    the previous list on screen meanwhile (keepPreviousData).

## Off by default / switches
- AUTO_SAVE_READY: ON for statements prepared after deploy; off with `FINANCIAL_AUTO_SAVE_READY=0`.
- Backlog: never runs by itself (CLI dry run default; the queue button is an investigator click).
- PREWARM: ON (`review_queue.PREWARM = False` turns it off).
- s-inference flags unchanged (LOUPE_FINANCIAL_CURRENCY_PROPOSALS / LOUPE_FINANCIAL_DETAIL_PROPOSALS).

## Tests run
- Backend (CHROMADB_PORT=1 CHROMA_PORT=1): new tests/test_financial_queue_save.py (21: save, idempotency, one
  statement once, held reasons, paused batch, only-reconciled, automatic save via the real preparation hook,
  switch, never raises, System fill vs investigator review, queue fill, backlog CLI apply idempotent, superseded
  batches + list, prewarm); targeted modules (review_queue, import_batches, statement_import_router,
  statement_file_status, duplicate_file_status, bulk_statement_details, field_proposals, batch_read_*,
  pending_duplicates, batch_duplicate_overview, batch_review_summary, batch_import_history): 341 passed.
- Frontend (as conorbowles51): tsc clean; `npm run build` (tsc -b + vite) passed; vitest unit over
  src/features/financial: 1,693 of 1,695 passed in the full run; the 2 failures (FinancialPage "retains the selected
  PDF...", LedgerRowBrowser "selects every matching payment...") were timeouts under load (78 s / 118 s) and pass
  when rerun alone (51 passed). New/updated: ReviewQueuePanel (save across batches, filled list),
  StatementCurrencyControl (focus, one-click proposal), BatchCurrencyEditor (proposal), FinancialBatchPanel
  (older batches toggle), statement-file-state (queue-driven needs action), FinancialPage (queue default).
- Not run: browser project (BulkStatementDetails.browser expectation text updated, not executed); no click test over
  the server IP.

## Priority additions after release of 2689d01a (coordinator, Alex's case first)
- 64f6872d (B) Every queue item names ALL its blockers: the summary sentence stays, then "also: ..." (entry
  `reasons` + `also`), in the list and in the statement's "To fix" banner. A statement waiting for its currency is
  not checked further by the reader, so its empty bank / holder / account number are named too. `fix_makes_ready`
  is true only when the proposal covers the one and only blocker; otherwise the currency control says "This fills
  the currency only. Still to fix: ..." and the batch currency editor says how many become ready.
- 2f873f4a (A) "Waiting for a reader fix": a file with >= 5 statements (copies excluded) where >= 50% are blocked by
  reading/identity problems (reading, incomplete, count, couldn't read, bank, holder, account, dates) and none would
  be ready after one field fix becomes ONE line outside "Waiting for you": "Loupe can't read this file reliably yet
  (N statements). No need to review it by hand; it will be re-read when the reader is fixed." Status line "Waiting
  for a reader fix N"; its statements stay listed (expandable) and openable; no data change. Constants
  READER_MIN_STATEMENTS / READER_SHARE in review_queue.py; tests ReaderCollapseTests, AllBlockersTests.
- Live 49494305 (read-only, use_cache=False): waiting 436 -> 150; waiting for a reader fix 286 (one file,
  6e611846, 286 of its 287 statements); waiting with blockers beyond the sentence 193 (of 436) -> 101 (of 150), all
  now shown; statements claiming a one-click fix that would make them ready 194 -> 0 (the 194 currency statements
  also lack bank/holder/account). Remaining waiting by file: 41, 29, 25, 24, 21 (the Andrews OCR files: under the
  50% reading/identity threshold or with single-fix statements, so they stay work). d5b330d1: waiting 146
  unchanged, 15 entries truly one click from ready.
- Tests: review_queue + queue_save 78 passed; ReviewQueuePanel / StatementCurrencyControl / BatchCurrencyEditor
  vitest passed; tsc clean; `npm run build` (tsc -b + vite) passed as conorbowles51; no root-owned files in node_modules/.tmp.

## Observations for the coordinator
- Case f887b0d9: its batches (2 at 20:40) are gone from financial_import_batches (no rows at all, not 'removed') by
  21:30. Not caused by this unit (every probe read-only). Worth checking who deleted them.

## Decisions for Neil
1. AUTO_SAVE_READY default ON for new preparations (strict: zero checks, no investigator edit). Keep?
2. Run the backlog for 49494305 (214 statements, dry run + full admission: 214 would save, 0 held):
   `python3 scripts/financial_save_ready_backlog.py --case <49494305 uuid> --apply` (or Alex presses "Save all").
3. Should "possible copies needing comparison" count as Needs action in the Files list? Today (queue-driven) they
   are reached through the queue's Copies list only.
4. Cold queue build stays 4-10 s+; the next step is precomputing per-statement projections on write (a stored
   readiness row per statement), a larger change than this unit.
