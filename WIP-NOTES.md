# fin/alex-1013 — duplicates told up front, continue open batches, ingestion steps report

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
