# Ingestion reliability and interruption recovery

Status: local development and verification. The user's later instruction to finish,
commit, push and deploy all relevant implementation supersedes the earlier hold.
The release must preserve active ingestion jobs and pass the remaining gates below.

## Incident evidence

- The live BNB2 Processing panel shows six chat PDFs failing with the same Neo4j transaction timeout and the same displayed duration (57m18s); another file completed.
- This is consistent with one failure in a shared batch stage. It does not establish that all six source files are defective, or identify the exact failing query.
- A local Neo4j EXPLAIN confirms the existing unlabelled entity lookup uses AllNodesScan. A category-labelled lookup with compound case/id indexes uses NodeIndexSeek. The unlabelled query predates the latest financial releases.
- A server stack trace and load metrics have not been obtained. SSH was blocked because the host identity was not verified. No live jobs have been retried, cleared or moved.
- The requested large chat contains 1,928 pages, below the configured 2,000-page ceiling. This is not proof that the entire processing path can complete it reliably.

## Agreed investigator journey

1. Select files and destination. Upload progress counts bytes acknowledged by the server, not merely bytes sent. Pause retains accepted chunks. Resume sends missing chunks only. After reopening the browser, reselect the original file if browser access was lost; verify content before resuming.
2. Complete upload once. A lost response or repeated completion request must return the same evidence record. An incomplete upload must never appear as fully uploaded or begin ingestion.
3. Start ingestion. Save completed text/OCR, extraction chunks, resolution and graph publication work durably. Checkpoints belong to the source, case, job and processing version; changed inputs must not reuse stale output.
4. Pause from Processing. Show Pausing while an active safe unit finishes, then Paused. Explain when the operation controls a shared batch. Paused work must release worker capacity and survive browser closure and service restart.
5. Resume the same run. Retain identities, source citations and completed results. Prevent simultaneous resumes and repeated graph/ledger publication. Completed files stay completed when another file fails.
6. Failure recovery retains checkpoints and identifies the failed stage. Resume retries unfinished work; it must not silently spend another hour re-extracting completed chunks. Existing runs from before checkpoint support cannot retrospectively recover unsaved intermediate output.
7. Publish results and mark completion only after required writes succeed. The original evidence and investigator corrections remain intact.

## Acceptance gates

- Interrupted transfer, duplicate chunk, wrong chunk hash, lost completion response, cross-user/case access, refresh/reselect and concurrent resume.
- Pause queued/active jobs; pause during OCR, AI extraction and graph writes; process exit and service restart; automatic stale-job checks must leave paused jobs alone.
- Inject timeout after partial graph writes; resume without new IDs, duplicate entities/relationships or loss of manual edits.
- Sub-100-page, approximately 270-page and synthetic 1,928-page PDF coverage; no assertion of real-document acceptance without the original document and a complete verified run.
- General and financial preparation jobs make progress concurrently. A paused run does not occupy a processing slot.
- Browser validation of upload → pause → reopen → resume → processing → pause → resume → completed results, including clear error/recovery states.
- No push, deployment or live recovery action until explicitly authorised.

## Starting Financial while AI ingestion is running — 22 September

User report: an AI run appears to stop when financial preparation starts. This
must work for every case and for both start orders. Starting, finishing, failing,
pausing or resuming one batch must not cancel a different batch or replace its
progress. On returning to Processing, both runs must remain identifiable.

Confirmed locally:

- The baseline uses shared ARQ capacity. Pending local changes give PDF review a
  dedicated queue and worker. Job IDs, progress channels, checkpoints and PDF
  subprocess groups remain scoped to their individual jobs/batches.
- A reproduced status race exists during engine handoff: `mark_processing` clears
  the old job link, but a case-wide reconciliation can rediscover the previous
  attempt by source file ID and restore its failed/completed status before the new
  engine upload returns. Starting another ingestion performs that reconciliation.
  The fix persists the current request ID before handoff and accepts updates only
  from that request. Older records without a request marker retain the existing
  compatibility path. A lost upload response can still recover the matching job.
- The pending checkpoint wrapper unnecessarily required graph indexes even for
  PDF review. Index preparation now belongs to the AI pipelines only. Financial
  preparation works with the graph unavailable, including single-job resume.
- Processing cards distinguish AI ingestion from Financial statement reading.
  A completed reading says Ready for review and explains that payment import is
  the next step in Financial; it no longer implies completion via zero AI entities.

Validation:

- A regression test first reproduced the historical-status overwrite, then
  passed after the request guard. Tests also cover lost upload acknowledgements
  and unrelated AI/PDF source records (10 passes). A further 40 admission and
  Evidence explorer regressions pass.
- Eight real local Redis checks pass, including six scenarios using separate
  spawned ARQ worker processes: AI first and Financial first, with the second run
  completing, failing or timing out while the first continues producing heartbeats
  and completes. These are synthetic job bodies, not external AI-provider calls.
- Actual PDF subprocess tests confirm simultaneous reads retain their contents
  and interrupting either reader leaves the other child alive. Engine worker tests
  cover PDF preparation while graph access fails. The scoped engine suite passes
  33 tests, including dispatch, source preparation, PDF workers, upload security
  and chunk publication. Two additional single-reader failure/cancellation checks
  confirm that only that job is marked failed.
- Chromium at a 1280×900 viewport verifies both job cards, one run failing and
  resuming without changing the other, completion wording, and reopening the
  Processing panel. API responses are synthetic fixtures. Typecheck passes.

Still open: live timestamps, worker logs/exit codes, memory/CPU pressure and the
actual failure stage for Alex's run. No explicit cross-job cancel was found in the
traced start paths. The status race does **not** establish the cause of a genuine
worker/process termination, nor does queue isolation guarantee host capacity.
Real AI-provider overlap, restart/load testing and the 1,928-page end-to-end run
remain release acceptance gates. Nothing in this investigation has been deployed,
and no live jobs have been restarted, retried or moved.

## Recovery verification — 23 September

- Eight isolated HTTP/database/file-storage checks now cover paused transfers,
  retained chunks, duplicate chunk acknowledgements, repeated completion returning
  one evidence record, wrong data/hash, missing chunks, unsafe filenames and another
  user's access. A corrupt saved chunk is invalidated so resume can actually resend
  it. Upload reads no longer hold a row lock while waiting for network bytes.
- Persistent work-unit checks cover queued pause, interruption after saved units,
  retry without repeating earlier work, exclusive scope locks, changed model policy
  invalidating outer stage caches, and visible failure on a damaged checkpoint.
  Queued jobs and jobs paused before their first unit remain resumable. A live-worker
  heartbeat prevents the stale-job janitor mistaking a long active unit for a dead
  process; individual operation timeouts remain in effect.
- Native PDF pages now retain their text, table text and source rectangles in
  atomic page checkpoints, alongside existing OCR checkpoints. An actual generated
  1,928-page native PDF was interrupted at page 777 and resumed; every page remained
  present, in order, and each native page was read exactly once. This establishes
  page extraction/recovery for a synthetic document, not completion of Alex's chat
  through external AI providers, graph publication and live hosting limits.
- Chromium covers upload → pause → leave/reopen → resume and recovery after the
  server saved an evidence receipt but its response was lost. It also repeats the
  concurrent AI/Financial failure/resume journey. These use synthetic API responses
  and browser-native file objects; the server writer has the separate HTTP/SQL
  checks above. Pending uploads no longer display the contradictory empty activity
  state. Broader reselect, restart, graph publication and live acceptance gates are
  still to be completed; no deployment or live-case recovery is claimed here.

## Final local release checks — 23 September

Fresh-session file reselection now passes: a different file is rejected, the original sends only missing chunks, and a lost completion response returns the saved receipt. The isolated real Neo4j interruption/reconnect test passes after a partially committed publication, retaining manual edits and stable entity identities. Both queue orders and failure/timeout isolation pass in spawned workers. The combined scoped ingestion suite passes 62 tests; the Financial/Evidence/Timeline Chromium suite passes 62 tests in 27 files. See [the release record](financial-workflows/release-verification-2026-09-23.md) for supported paths and live acceptance boundaries. Server deployment is authorised but awaits renewed Google Cloud login.
