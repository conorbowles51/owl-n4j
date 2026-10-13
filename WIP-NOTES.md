# fin/s-autostart: statements read without starting a batch (2026-10-13)

Base af76b2ac. Not pushed. Live numbers: read-only probes (READ ONLY transactions + ORM flush guard). Opaque ids,
counts only. Private detail (detector features per file, CLI dry-run): /mnt/owl-data/fin-real/alex/autostart/.

## The flow before (traced in code)
1. **Upload.** Evidence registers each file via `EvidenceDBStorage.add_files` (tus single uploads, upload groups,
   folder registration). Status `unprocessed`; nothing is read.
2. **"Is this a bank file?"** Only for *native* formats: `services/financial/route_check.py` (`/api/evidence/route-check`)
   and the engine backstop `app/pipeline/financial_route.py` sniff camt.053/BAI2/MT940/NACHA. **There was no PDF
   statement detector anywhere.** The only PDF statement signal was the investigator's choice: uploading in
   Financial (`statement-upload-queue.ts` -> `POST /api/evidence/process/background` with `preparation_mode=pdf_review`
   per file) or "Choose from Evidence" (`selection/include`, then the picker itself starts a batch).
3. **Batch.** The investigator ticks read files and presses "Review and save selected files together" / "Start batch
   check of N read files" -> `POST /statement-import/batches` -> `import_batches.create_batch` (continues an unfinished
   batch that covers the selection).
4. **Reading + preparation.** `run_batches_forever` (5 s loop, 2 batches at a time) -> `advance_batch`: `waiting` files
   go through `prepare_existing_financial_file` -> `process_db_files(pdf_review)` (admission gate
   `gate_document_processing`, engine PDF queue with max_jobs=2) -> `processing` -> when processed, `_review_file` /
   `prepare_reviews` writes batch items -> the review queue (`review_queue.py`) lists them.

## What changed (commits)
- 0ad45a05 `statement_detection.py`: first 3 pages' text layer (PyMuPDF), statement-engine vocabulary: opening/closing
  balance label + account label + issuer line (bank/FDIC/N.A./IPAB/CONDUSEF/...) + (2 movement columns, or period +
  totals). No OCR: scans are not recognised.
- 2fc027ef `auto_read.py` + hooks:
  - `add_files` writes a marker `financial_auto_read={state:pending}` on new PDFs (not Cellebrite). No I/O.
  - `/process/background` with `pdf_review` (Financial upload / Read button): exact copies (same bytes as a file
    already in Financial in this case, other than its own readings) are **not read**: marked `copy`, file history
    entry, returned as `copies` (upload panel says "Same file as X, already in Financial — not read again"). Others
    are marked `statement` and read as before.
  - Worker sweep every 10 s (inside `run_batches_forever`, own try/except): checks <=20 pending PDFs per round (8 s
    budget, skip-locked rows, skips files the Evidence pipeline is processing) -> `statement` / `not_statement` /
    `copy`; then adds `statement` files to the case's **automatic batch** under the case lock with a 2 s lock timeout
    (busy -> next sweep). Automatic batch = an ordinary batch, actor `System` (user_id = uploader or case owner,
    `auto_read: true`), rolling while it is still reading (new one once idle or at 300 files), per-file `auto_read`
    reason. Files whose original is already in a batch are left to that batch.
  - `advance_batch` (`_turn_candidates`): in a batch with automatic files, at most 2 automatic readings are queued or
    running; files already reading are polled first. Manually started batches unchanged.
  - Fix: batch actor built from name/email/user_id only (an extra key in `batch.actor`, e.g. the removal history,
    made `Actor(**actor)` raise).
- 68f485ff queue/status responses carry `reading` {files_total, files_done, files_reading, files_waiting_to_start,
  paused, unread_statement_files}; status line leads with "Reading 12 of 40 files…" / "Reading paused at …".
  `POST /statement-import/review/read-unread?case_id=` = the one action (case edit + evidence upload).
- ce57337d `scripts/financial_read_unread_statements.py` (dry run default; `--apply`, `--case`, `--evidence`).
- d70c6d31 UI (status-line area only): `ReadingProgress` beside the status line (CaseReviewStatus + ReviewQueuePanel):
  the progress sentence and "Read N unread statement files"; queue polls every 15 s while reading so statements
  appear as files finish; upload store names copies.

## Off / on
- `LOUPE_FINANCIAL_AUTO_READ_STATEMENTS` (default ON): everything above; `0` restores today's behaviour exactly
  (no markers, no sweep, copies read as before).
- `LOUPE_FINANCIAL_AUTO_DETECT_STATEMENTS` (default ON, `statement_detection.DEFAULT_ENABLED`): Evidence-upload
  detection only. Only files registered after deploy carry the marker, so nothing fires on deploy.
- Nothing is saved or admitted by this unit. Reversal: pause/remove the automatic batch, remove the file from Financial.
- Retroactive: never on deploy. Explicit button (Financial-library files) and CLI (`--evidence` for Evidence PDFs).

## Live numbers (read-only)
- "~108 not imported files" in 49494305: all 119 Financial files there are **read and prepared** (in batches); the
  111 without a saved statement are "not imported" because their statements wait in the review queue (436 waiting /
  214 ready), not because they were never read. Unread statement files in Financial: **0** in 49494305; 12 in
  267842f3 (10 read never prepared + 2 exact copies); 0 elsewhere. So the button shows only in 267842f3 today.
- Evidence PDFs never sent to Financial, checked by the detector (CLI `--evidence` dry run, 16.8 min wall on the
  loaded box): d5b330d1 1,538 checked -> **350 recognised statements + 232 exact copies of Financial files**;
  49494305 141 -> 0; b6fe7c6b 319 -> 0; fdaf956c 2 -> 1 (+1 copy). Not applied.
- Detector accuracy (2,022 unique PDFs, 6 cases): statements already in Financial with a text layer: 434 of 470
  recognised (92%); 272 of 742 Financial PDFs are scans (not recognised by design). Recognised among PDFs never in
  Financial: 286 (all d5b330d1); private sample 30/30 + 15/15 were bank/brokerage statements. The issuer rule removed
  5 care-home billing statements in 49494305 that the first rule matched (0 now). Cost: median 126 ms/file wall
  (I/O on pd-standard), ~23 ms CPU.
- 20-file synthetic run (sqlite fixture, stand-in engine, box at load ~27): detection 0.46 s CPU for 20 PDFs; peak
  automatic readings in flight **2**; worker turns 23; 20 statement items prepared; process heap peak 22.8 MB, RSS
  growth 73 MB; total 199 s CPU / 470 s wall, almost all in the existing `prepare_reviews` preparation (unchanged
  by this unit; sqlite + load make it slower than live's ~1.2 s per statement).
- Endpoint timings: `/review/queue` and `/review/status` add `reading_progress` (5-31 ms, live, every call) and
  `unread_statement_files` (cold only; cached with the queue by the same fingerprint): 8-97 ms on five cases,
  ~0.95-1.3 s on d5b330d1 (first version took 5-6 s; rewritten to exclude batch/saved files before loading rows).
  Whole cold queue before/after was measured but the box was at load ~27 and the numbers swing 30% run to run
  (e.g. 49494305 7.5-9.2 s before vs 8.1-10.6 s after; d5b330d1 22-23 s vs 24-29 s); the added work is the two
  numbers above. `/process/background` (pdf_review) adds one sha lookup per file.

## Tests
- Backend (CHROMADB_PORT=1): new test_financial_auto_read (9); review_queue + file_scope 82 pass; import_batches,
  batch_read_projection/stored, admission_gate, statement_import_router, resumable_upload_groups,
  cellebrite_evidence_db_storage, batch_duplicate_overview, pending_duplicates, batch_import_finalization: 223 pass.
- Frontend (as conorbowles51): tsc -b clean; vitest statement-upload-queue, ReviewQueuePanel, StatementFilesPanel,
  ReadingProgress (new), FinancialPage pass; `npm run build` passes.
- Not click-tested in a browser over the server IP.

## Decisions for Neil
1. Evidence-upload detection ON by default (measured above). Scans are not recognised (37% of today's Financial
   PDFs); OCR for detection would be a load decision.
2. d5b330d1 holds 350 recognised statements (+232 copies) that only exist in Evidence. Run
   `python3 scripts/financial_read_unread_statements.py --case <d5b330d1> --evidence --apply` when the queue can take
   them (they read at 2 at a time; statements then appear in the queue). Dry run first.
3. 267842f3: 10 read, never prepared statement files -> the queue button, or the CLI `--case ... --apply`.
4. Detected-only files stay ordinary Evidence (coordinator, before release): a file that reached the automatic batch
   only through Evidence-upload detection (or the CLI `--evidence` backfill) is read from an internal statement
   version (same bytes, hidden from Evidence listings; `auto_read.prepare_detected`), so the original stays
   `unprocessed` and the Evidence AI pipeline (search, entities) processes it as normal. An original the Evidence
   pipeline already processed is used as it is. Only files a person put in Financial (upload in Financial, Read
   button, unread-files action) are read themselves and then count as processed, as before.
   Tests: `EvidenceProcessingTests` (detected -> copy read, original unprocessed, `process_db_files` full mode still
   accepts it; chosen in Financial -> original read). Re-run: auto_read 11, import_batches, review_queue,
   batch_read_stored, admission_gate, file_scope: 206 pass.

## Coordination
UI touched only: ReadingProgress (new), one line each in CaseReviewStatus and ReviewQueuePanel (after
ReviewStatusLine), review-queue.ts (schema `reading`, poll while reading, `readUnreadStatements`), upload store.
`review_queue._entries` now returns (entries, unread); `status_line(counts, reading=None)` stays compatible.
