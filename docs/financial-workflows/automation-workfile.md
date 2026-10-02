# Financial automation — headless workfile

Working file for `automation-delivery-plan-2026-09-28.md`. Every session (headless or
interactive) reads this after `CLAUDE.md`, does the **▶ NEXT** unit and nothing else,
then rewrites ▶ NEXT and appends to the log before it exits.

STATUS: RUN

(Set the line above to `STATUS: HALT — <reason>` to stop the headless runner. A session
sets it itself only when it is genuinely blocked on Neil; see "Halt rules".)

---

## ▶ NEXT

**(2026-10-02 21:55) Wave 4 merged into `fin/release-1` (head after the workfile fold, see Log). NOT pushed.**
Release-1 now (corpus v4, 124 distinct periods): **93/124 ready without edits (75.0%)**, 93/107 recoverable (86.9%),
0 wrong admissions, 0 critical-field errors. v1–v3 subset 37/49 (unchanged); v4 additions 56/75 (was 28/75).
Suites: financial 5669 / all-tests 6060, only the 2 known `unassigned_statement` failures; tsc 0; vitest unit 295/295.

**Next wave (≤3 headless units, each a worktree from fin/release-1, ranked by recoverable periods still held):**
1. **`fin/c-image-fields`: BBVA and Capital One image pages** (5 periods). bbva-2024-07 image-only and bbva-2024-08
   skewed (both `balance`: BBVA image-only reason), bbva-2024-09 ocr amount digit (reading 1, balance 3),
   capital-one-2025-03 150 dpi+JPEG (every money cell confirmed; OCR reads the layout marker as
   "...detailed transactions**:**" and `statement_layout_context.py:80` matches the phrase exactly, so section and
   holder are lost), capital-one-2025-01 ocr amount digit. Safety gate unchanged; benchmark must exit 0.
2. **`fin/c-andrews-residue`: last Andrews holds** (4 periods). 2022-04 150 dpi #2 (minus read as `“`), 2022-05 100 dpi #2
   (crop rereads contradict page: 4 of 6 crops `61.28` vs page `-61.28`; `7,150.20` vs `7,180.20`), 2022-08 combined #2
   (one row not separated), 2020-12 OCR-lost lines with equal balances (no_activity). Any fix that admits must do so on
   printed values only; holding stays correct where readers disagree.
3. **`fin/c-mx-layouts`: Scotiabank with-movements + Monex peso-movements, and the benchmark pairing defect** (3 periods).
   **First commit: fix the harness pairing defect (Open defects)** — the two Monex 2024-03 zero-activity periods are now
   ADMITTED and the harness pairs them crosswise by currency, so their scoring is not trustworthy until it is fixed.
   The movements layouts were invented by a-corpus2: scaffold only, say so in notes.
Not in a unit: credit-one-6 (compensating misreads, held by design until an independent reader agrees);
merrick-two-statements#1 (earlier note: ground truth mislabelled — corpus fix, not pipeline).

**Open Neil decisions (nothing above waits on them; all have a recorded default):**
- **Live reader-recovery dry run + ledger audit (r-recovery) — NOT run.** The headless session was blocked from reading the
  service DB configuration and did not work around it. Both scripts are read-only (READ ONLY transaction, verified
  evidence hashes, private scratch dir). From `backend/` with the service env loaded:
  `OMP_THREAD_LIMIT=1 python3 scripts/financial_reader_recovery_estimate.py --case <case> --select-only` (seconds), then
  without `--select-only` and `--out /mnt/owl-data/fin-wt/r-recovery-estimate` (minutes per Andrews file);
  `OMP_THREAD_LIMIT=1 python3 scripts/financial_ledger_misread_audit.py --case <case> --out /mnt/owl-data/fin-wt/r-recovery-audit`.
  Then decide `LOUPE_FINANCIAL_READER_RECOVERY=1` (default OFF). Corpus simulation: 7 of 44 held periods became ready
  with 0 wrong (23 Sept engine); audit flagged all 5 wrong admissions, "disagrees" 4/4 true, "disputed now" 3–4 false of 4–5.
- **Disposable PostgreSQL on 127.0.0.1:55434** (or name an instance that may hold throwaway schemas). Without it the
  b-gate PG rows (two-worker exactly-once, save vs group confirmation, deadlock, removal, recovery prep ×6, concurrent
  `queue_import` lock order, audit triggers), b-unique's 4 new PG tests and r-recovery's PG-only paths (row locks,
  `SHOW transaction_read_only`) have never executed. Run both `backend/tests/*_postgres.py` files
  (`LOUPE_TEST_LOCAL_POSTGRES=1`) before deploying the migration below.
- **Migration `20261002_one_active_statement` runs at deploy** (`alembic upgrade`, single head, down_revision
  `20260924_statement_recovery`). Deferred EXCLUDE constraint: one active admitted statement copy per case + evidence
  file + statement id. Takes ACCESS EXCLUSIVE on `financial_source_documents` (~1k rows) briefly; refuses with an
  offender list (adds nothing) if duplicates exist. Live read-only check 18:40: 0 offenders among 937. Approved in
  principle by Neil; PG-semantic acceptance unproven (parsed only). Wave 4 added no migration.
- **Engine and backend must deploy together (c-image):** the engine now records scan preparation in the processing
  manifest; a backend without it rejects those records ("Stored table provenance is malformed").
- **c-image**: (1) geometry kept in the straightened frame, so highlights on turned pages sit up to ~9 pt (1°) / ~22 pt
  (2.5°) off near corners until the viewer applies the recorded `deskew_degrees` (not built); (2) words over blank paper
  dropped on prepared scans when confidence < 60 and no ink within 4 px (recorded as `ocr_inkless_words`); kill switch
  `PDF_SCAN_PREPROCESSING=false`. All numbers are on synthetic damage; real productions unmeasured.
- **c-mx-noactivity**: printed zero totals + equal printed balances count as source proof (basis `printed_zero_totals`,
  computed) — implemented yes; reverse if only printed counts of 0 qualify. Monex contracts with any movements page keep
  failing closed until a real page is seen. Layouts modelled from reader code, not real documents.
- **r-recovery**: system re-reads attributed to the batch owner (as the 25 Sept campaign did); files with any ready
  period are left alone.
- **Second reader (c-reader2)**: (1) glyph reader + Tesseract crop agreement + page reconciliation as independent
  evidence for admission (default ON; kill switch `STATEMENT_GLYPH_SECOND_READER=false`); (2) 4-of-6 crop contradiction
  instead of unanimous; (3) templates from non-money digits; (4) show repaired cells beside the machine reading in the UI
  (not built). No hosted vision model (private images).
- **a-corpus2**: route deposit receipts out of statement batches automatically?; Mexican zero-activity sections treated
  as `auto` in ground truth.
- **Carried**: Merrick start = previous closing + 1 stored `derived`; c-generic pinned-repair exception to "never
  substitute a crop value" (revert 13d03dbe to refuse); investigator-typed start recorded as `printed`;
  `unassigned_statement` (moved continuation pages don't carry balance rows; the only 2 suite failures); U2 Neo4j index
  auto-creation on first live run; check the suspected duplicate population (232 = 232) before the case's next import
  auto-projects it; re-read live Andrews sources through the current reader (now = the r-recovery campaign above).
- **Before pushing fin/release-1**: in the live checkout, move the untracked `docs/financial-workflows/automation-workfile.md`
  and `scripts/headless/` aside (they are tracked in release-1; the fast-forward fails otherwise), push, then copy
  the workfile back over the tracked one if it changed. After deploy: run the readiness refresh for the case.

---

## Queue (in order — move the head into ▶ NEXT when the current unit lands)

**U1 — Batch read performance (checkpoint A + E instrumentation).**
Live: `batch_status` for one 244-item batch takes ~230 s — the leading candidate for
the "Failed to fetch" reports, but unproven. Reproduce on a synthetic 250- and
1,000-item batch with a timing harness around `import_batches.batch_status` /
`checked_batch_items` (`backend/services/financial/import_batches.py`). Find what the
read path recomputes (comparison_sources, proposal reconstruction, per-item
reassessment). GET must not reparse PDFs or write state. Stored item summaries are
stale because read-time reassessment is never persisted — fix that at the write side
(assessment on save / worker), not by persisting from a GET. Target from the plan:
first useful list ≤3 s p95. Add request correlation id + server timing to the batch
endpoints so the live cause can be confirmed later. Harness code is committed;
private data never.

**U2 — Ledger → graph projection is never invoked.**
`services/financial/projection.py:project_case` has no production caller (only its
test). Live: 11,549 admitted transactions, 0 `FinancialTransaction` nodes, and the
reviewed identity graph sweep (`identity_graph.py` ~L165/L239) retries forever because
the payment nodes it waits for never appear. Wire projection into the admission/import
worker path (idempotent, after commit, failure isolated from the ledger write — graph
follow-up is validated separately from ledger completion per the plan). Bound the
sweep: missing-node retries back off and surface as a visible status, never a hot loop.
Provide the backfill as the same code path (a command that calls the worker's
projection for a case) — **build and test it; do not run it against live data.** Record
the command for Neil.

**U3 — Backend shutdown hang.**
Shutdown waits on "Waiting for background tasks" indefinitely; uvicorn 0.38 needs
SIGINT to force; unit `TimeoutStopSec=14500`. Find the background tasks that never
finish (likely the sweep from U2 and long-running import/reading tasks), make them
cancellable with a bounded shutdown, and make deploy's stop path write last-good + log
tail on timeout. **Code and tests only — no service restarts on this box.**

**U4 — Checkpoint A baseline harness.**
Per plan §1: repeatable benchmark over real extraction → catalog → proposal →
admission → batch preparation → import, on committed synthetic fixtures; records
attempts, readiness reasons, human actions needed, worker and wall time. Run current
code to produce the baseline report (`docs/financial-workflows/baseline-<date>.md`).
Then restate the ETA from measurements.

**U5 — Checkpoint B gate.** Prove plan §2 gate with the harness: save once → ready in
every view; independent batch edits intact; existing-draft upgrade repeatable; one
group confirmation imports the exact eligible set once; PostgreSQL concurrency tests
(loopback 55434, disposable schemas — check the port is actually available first).

After U5: continue with plan checkpoint C (repair ladder + date provenance), slicing it
into units here before starting it.

---

## Halt rules (headless)

Nobody answers questions in a headless run. Per `CLAUDE.md`, decide, record the
reasoning, proceed. Set `STATUS: HALT — <reason>` only when:

- the unit cannot proceed without changing live data, live services, or deployment
  configuration;
- the unit turns on a product decision the source cannot settle (write the
  recommendation next to the halt);
- the same unit has failed to land in two consecutive sessions;
- a checkpoint gate requires live acceptance by Neil or Alex.

## Box facts (verified 2026-10-02)

- Repo: `/home/conorbowles51/app-v3/owl-n4j`, branch `integration/evidence-main-reunion`.
  Pushing it triggers the guarded deploy to the live box.
- The plan's `data/local-runtime/backend-venv` / `engine-venv` do **not** exist on this
  box. Use the `CLAUDE.md` bootstrap (system `python3`).
- Live read-only probes: `PYTHONPATH=backend`, source `.env`, `.venv` python, and wrap
  in a READ ONLY transaction. Stored batch item summaries are stale — measure through
  `batch_status`, not raw DB counts.

## Open defects (found, not fixed)

- Benchmark pairing (`backend/benchmarks/statement_automation/harness.py` `_score`, ~L158): scores period end, share
  and row amounts but not currency, so two sections of one file that differ only by currency (Monex 2024-03 MXN/USD
  zero activity) tie and pair by item order. In release-1-w3 they paired crosswise: 2 false `currency_wrong` and 4
  extra simulated actions; ready/held outcomes unaffected. Fix: add a currency term to `_score`. Found 2026-10-02
  integrate-3. Still open after wave 4 (c-zero-totals was superseded by c-mx-noactivity, which did not take it); both
  Monex 2024-03 periods are now admitted and still pair crosswise. Assigned to `fin/c-mx-layouts` (first commit).

## Log

- 2026-10-02 — Workfile created with session prompt `scripts/headless/financial-prompt.md`
  (no runner script yet). Live findings above came from a read-only probe earlier the same day.
- 2026-10-02 (earlier interactive session, results recovered from its scratchpad, not re-run):
  - U0 partial: backend financial suite **Ran 5544, FAILED (failures=33, errors=6, skipped=12)**
    in 1189 s. By module: exports 22, identity_graph_integration 5, import_batches 3,
    unassigned_statement 2, statement_review_checks 2, statement_import_scotiabank 2,
    statement_row_assignment 1, pending_duplicates 1, batch_review_save_scope 1.
    Frontend `tsc -b` rc=0. vitest unit **72 failed / 1980 passed (17 of 295 files)** —
    StatementImportPanel 36, FinancialPage 17, FinancialSourceAudit 4, LedgerRowBrowser 2,
    13 other files 1 each. None of these failures are triaged or fixed yet.
  - U1 cause measured (live, read-only, cProfile): `batch_status` on the 244-item batch
    = 231.8 s, of which `statement_import_overlap.comparison_sources` = 224 s — it calls
    `statement_import.read_statement_import` for 250 statements (re-proposing PDFs) on every
    GET via `import_batches.checked_batch_items` → `read_pending`. Secondary: catalog 31 s,
    `review_upgrade.attach_upgrade` 20 s, BBVA `norm` 17 s (17.9M genexpr calls).
    Batch state: 53 ready / 191 attention. No fix written yet.
- 2026-10-02 (interactive, Neil present) — Order changed with Neil's agreement: U1 first, U0 alongside it.
  Three background subagents launched from interactive session app-v2-cd, each in its own worktree on
  `/mnt/owl-data/fin-wt/` (branches `fin/u1-batch-read`, `fin/u0-backend`, `fin/u0-frontend`, all from
  687da296). Agents commit locally and never push; the coordinator reviews, merges into
  `integration/evidence-main-reunion`, updates this file, then pushes. Next after these land: U2.
- 2026-10-02 (Neil: speed up without cutting corners) — U2 and U3 started in parallel too (branches
  `fin/u2-projection`, `fin/u3-shutdown` from 687da296). U3 owns sweep start/stop only; U2 owns sweep
  retry/backoff — expect a small merge in identity_graph.py. U1 ships on its own once verified (manual
  SIGINT stop if U3 not yet merged). U4 deferred until after Alex's first usable release. Target first
  usable release ~6–7 Oct. Ask Alex for her top 3 blockers.
- 2026-10-02 — **Neil: automation of system use is THE priority** (investigator should not open/correct
  statements). U4 (checkpoint A benchmark) is NOT deferred — started now on `fin/a-benchmark`. A read-only
  agent is ranking why the live batch's 191/244 items need attention (by reason × layout). U0–U3 continue as
  prerequisites (29 Sept automation code is untested; batch screen must load). When the ranking + baseline
  land: launch repair-ladder agents (checkpoint C) on the top-ranked reasons/layouts immediately, then D.
  The headline metric to report to Neil/Alex every release: % periods ready with zero human edits.

### ▶ RESUME AFTER SESSION LOSS (2026-10-02, Neil left for a flight)
The interactive session that ran 7 background agents was ended (SSH logoff, no tmux). Their work is on
branches in worktrees under `/mnt/owl-data/fin-wt/` — each has `WIP-NOTES.md` (if it got written) and WIP
commits: `fin/u1-batch-read`, `fin/u0-backend`, `fin/u0-frontend`, `fin/u2-projection`, `fin/u3-shutdown`,
`fin/a-benchmark`. The read-only live ranking (why 191/244 need attention) writes to
`/mnt/owl-data/fin-wt/live-ranking-PARTIAL.md`. To resume: for each worktree read `git log 687da296..HEAD`
+ WIP-NOTES.md, then relaunch one background agent per unfinished unit in the SAME worktree with the same
brief (briefs = Queue entries above + the 2026-10-02 log lines). Automation is the priority. Never push
(= live deploy) or run the graph backfill without Neil.

### Live ranking — why 191/244 need attention (read-only batch_status, 2026-10-02, counts only)
- ALL 191 blocked. One layout dominates: `andrews-share-statement` 232 items (179 blocked) + 12 `deposit_receipt` docs (all blocked).
- Display reasons (overlapping): reading 170 · balance 87 · holder 34 · assignment 23 · currency 12 (receipts).
  Per item: 76 one reason, 95 two, 20 three. Single-reason: reading 55, assignment 16, balance 5.
- Underlying problems → covered by built automation?
  amount unreadable ~152 → YES (29 Sept Andrews crop reread, reader v10) · running balance unreadable ~83 → YES (same) ·
  opening/closing balance unavailable 86 → partly · "confirm no activity" 74 → NO · holder missing 34 → grouped decision only ·
  assignment 23 → NO · date unreadable ~22 → NO · receipts in statement batch 12 → NO · balance/total mismatch 5 → NO.
- Absent here: missing account/bank/currency/dates, unprinted start, duplicates, conflicts — so those built features do nothing for this batch.
- **CAVEAT 1:** crop reread is inert until sources are RE-READ (batch read 23 Sept, before reader v10; live sources never reprocessed). Re-reading live sources = live data action → needs Neil.
- **CAVEAT 2 (check FIRST):** another batch in the same case already has 232 IMPORTED items = same count as the Andrews items here, yet none flagged duplicate/overlap. Possible undetected duplicate population — verify before automating or importing any of these.
- Top targets: (1) re-read Andrews through v10 [needs Neil ok]; (2) auto-detect no-activity periods (74); (3) Andrews opening/closing balance read (86); (4) auto-assign pages/rows to periods (23); (5) holder from same account's other periods (34) + route receipts out of statement batches (12).
- Fine per-item split not run (agent's script blocked by permissions); cached result in the old session scratchpad (batch_status.pkl / fine.py).

### U2 DONE on `fin/u2-projection` (commits 03d3e0c1, 4cab5406, fe80adf1, 4a2f65dc, 7f2bcc89) — not merged
- One hook: `confirm_statement_import` → `graph_followup.request_follow_up` after ledger commit (no I/O, can't fail ledger).
  Worker loop runs `follow_up_round` (debounce 20 s, max 300 s; backoff 30 s→30 min; one Neo4j txn; marker node per case;
  idempotent by digest; refuses empty plan). Status: `GET /api/financial/ledger-graph/status?case_id=`. Kill switch
  `LOUPE_FINANCIAL_GRAPH_FOLLOWUP=0`. Identity sweep backs off 60 s→30 min with `waiting_for_payment_nodes` status.
- Backfill (from backend/, .venv + .env): dry `python -m scripts.financial_graph_backfill --case <uuid>`; real `... --apply`.
  Est. 20–75 s for 11.5k txns WITH indexes (Neo4j write unmeasured).
- Tests: 22 + 8 new pass; targeted before 230 pass/2 fail → after 328 pass/2 fail (same 2 pre-existing).
- **Decisions for Neil before merge/deploy:** (1) it auto-creates Neo4j indexes on live first run (schema change) — approve, or make
  backfill-only; (2) next import into the 11.5k case will project the WHOLE case automatically (de facto backfill) — combine with the
  suspected-duplicate check above first; (4) legacy untagged amount nodes hide provenance — run dry-run first; (5) projected account
  `name` may override identity-graph labels, projected Document nodes appear in entity lists.
- Frontend text change in AccountIdentityReview.tsx not type-checked (no node_modules in that worktree) — run tsc at merge.

### U0 backend DONE on `fin/u0-backend` (d4a9725b, e69ce5f7, 60a50f42, a7916723, 32af0139, acf382a2, 5a4a03b1 + WIP-NOTES 2fa76584/f01f76ad — drop WIP-NOTES.md at merge) — not merged
- 37/39 fixed. Full suite in agent venv: Ran 5544, failures=2, errors=1 (`fitz` missing in env), skipped=29 (12 unexplained — env).
  Re-run in the normal env before recording a baseline. CLAUDE.md bootstrap fails on this box (Debian typing_extensions); needs
  venv + python-dotenv, pytest, PyMuPDF — update CLAUDE.md at merge.
- Code bugs fixed: 22 unregistered 29 Sept modules; KeyError on rows without id (review_arithmetic); restored duplicates still
  refused on save (pending_duplicates, 29 Sept regression). Others = tests encoding pre-24/29 Sept intent.
- **OPEN, Neil decision:** `unassigned_statement` (2) — moving a continuation page's payments doesn't move its balance rows, so a
  statement whose closing balance is on that page can never become ready. Recommend: assignment carries balance rows (or allow a
  source-referenced closing balance entry). Relevant to the 23 "assignment" items in the live ranking.

### Checkpoint A benchmark DONE on `fin/a-benchmark` (a4192fb4, d3113874, 54a85cd4; d87d76a9 WIP; drop WIP-NOTES.md at merge) — not merged
- Command: `LOUPE_BENCH_PYTHON=<repo>/.venv/bin/python scripts/run_statement_benchmark.sh [--out DIR]` (exits 1 on any wrong admission).
  Report: `docs/financial-workflows/baseline-2026-10-02.md`. Fresh-upload track, SQLite (55434 PG not listening), 26 periods, 3 identical runs.
- **Baseline: 12/26 (46%) ready with zero edits; 12/18 recoverable (67% vs 95% target). Human actions 34 one-by-one / 20 grouped.**
- **SAFETY FAIL: 1 period wrongly admitted** — Credit One scan, two OCR misreads cancel out (25.11→28.11, 18.79→15.79), reconciles with
  all printed controls → 2 wrong amounts saved. Endpoint-only card layouts can't catch compensating errors. Must fix before claiming
  automation is safe (likely live exposure too). 0 duplicate contributions; omitted-row periods held correctly.
- By family: Andrews 5/6 · Credit One 4/6 · Generic 3/10 · Merrick 0/4 (dates).
- Biggest levers: (1) Merrick: closing date recognised but bounds left empty → 13 of 34 actions; (2) no image reread for generic layouts;
  (3) valid-but-wrong readings never trigger reread (the safety fail); (4) genuine decisions (holder absent, quiet periods).
- Corpus gaps: Capital One, all Mexican families (BBVA, Scotiabank, Monex, Kapital, Intercam, Santander), receipts, MXN, ruled PDFs,
  missing pages, credit balances. Clean 200 dpi synthetic scans → repair rates are an upper bound.
- 2026-10-02 (Neil in flight; continuing per "automation is the priority") — started checkpoint C agents from `fin/a-benchmark`:
  `fin/c-safety` (catch compensating/valid-but-wrong OCR misreads; benchmark must exit 0) and `fin/c-andrews` (source-proven
  no-activity periods + dedicated Andrews opening/closing balance read; targets live 74 + 86 items). Both commit early.

### U1 DONE on `fin/u1-batch-read` (ac9e51f9, 54bec6f7, 743fac52, bfdd3025, 8829e5fe, fc4b1b83, 254699c1 notes) — not merged
- Batch list GET never reparses PDFs / never writes. Synthetic 250 items (old-style summaries like live): 19.6 s → 0.4–0.7 s;
  1,000 items: 68.6 s → ~3 s. Readiness computed write-side with an input fingerprint; stale items held as "Readiness being updated".
- Refresh: after every input-changing write; background pass every 60 s (20 s budget); backfill
  `backend/scripts/financial_refresh_batch_readiness.py` (`--dry-run`, `--case`, `--all`).
- X-Request-ID + Server-Timing on batch endpoints. 7 new equivalence tests vs frozen old implementation; no new failures.
- After deploy: old batches show "Readiness being updated" until refreshed (~4 min for the 244-item batch) — run the refresh
  for the case right after deploy. No frontend auto-refresh while items update (user reloads). Live check: Server-Timing total < 3,000 ms.

### U0 frontend DONE on `fin/u0-frontend` (14f34344, 042ab490; 896b46ca WIP-NOTES drop) — not merged
- Only 2 release-caused failures, both stale tests (standalone import now /queue-import + /confirm-result; retained check
  history hidden behind a button). Fixed. No component bugs from 29 Sept.
- Remaining ~70 failures = timeouts on the loaded shared box (load 5–10; 205/207 pass with --testTimeout=60000). Decision for
  Neil: raise unit testTimeout (~20000) in vitest.config.ts (recommended) or run on a quiet box. tsc -b rc=0.
- Possible real a11y bug (pre-existing, not 29 Sept): "Find in files" focus never reaches the "N matching files" heading
  (StatementFilesPanel.tsx ~L102, panel likely unmounts). Check in the real app.

### RELEASE CANDIDATE `fin/release-1` (worktree /mnt/owl-data/fin-wt/release-1, head 41e71707) — NOT pushed
- = origin/integration/evidence-main-reunion + fin/u0-backend + fin/u0-frontend + fin/u3-shutdown + fin/u1-batch-read +
  fin/u2-projection; WIP-NOTES.md dropped. Real conflicts resolved: confirm_statement_import now does graph follow-up request
  THEN file readiness refresh (inner fn `_write_statement_import`); worker loop runs graph follow-up alongside batch turns, then
  readiness sweep. One test updated for the merge (graph_followup duplicate-ignored test needs a real session factory).
- Targeted on the merge (live .venv python, loaded box): graph_followup 22 OK · batch_read_stored 7 OK · import_batches 88 OK ·
  exports 8 OK · statement_import 44 OK · pending_duplicates 20 OK · batch_review_save_scope 2 OK ·
  identity_graph_backoff + process_shutdown (pytest) 20 passed.
- NOT yet done: full backend suite, frontend tsc/vitest on the merge. Not including c-safety / c-andrews (still running).
- Before pushing (Neil): clear the deploy-checkout blocker; decide Neo4j index auto-creation (U2 risk 1); check suspected
  duplicate population before the case's next import auto-projects it; run readiness refresh for the case right after deploy.

### C-andrews DONE on `fin/c-andrews` (7bd0b31c, 509c7560, 1b9108be, e3ffe944, 39d8dcf3, 80966a73) — not merged, based on fin/a-benchmark
- Source-proven quiet Andrews periods become ready automatically (Previous + Ending Balance lines on the same page, equal,
  dated, adjacent with measured line spacing, nothing read between). Proof stored; admission basis source_verified /
  printed_zero_counts / investigator_confirmed. Unprovable → held with a specific reason; grouped "Confirm no activity" button.
- Endpoint balances carry provenance; endpoint cell crop reread on fully OCR'd pages. Never derived from arithmetic.
- Benchmark (corpus v2, 42 periods): ready w/o edits 52.4% → 61.9%; Andrews 68% → 86%; grouped actions 35 → 24; no new
  wrong admissions (the 1 Credit One case remains — c-safety).
- Live estimate: ~50–65 of 74 "confirm no activity" IF live layout matches fixtures — only after live sources are re-read (Neil).
- Corpus manifest will conflict with fin/c-safety — merge carefully.
- ⚠ TEST HYGIENE: the live .venv has chromadb → importing routers in tests connects to LIVE ChromaDB :8101. Always set
  `CHROMADB_PORT=1` for test runs on this host. (Add to CLAUDE.md Tests at merge.)

### C-safety DONE on `fin/c-safety` (0f75eddc, ae9981de, f9a754ec, a57a1bab, d056d571) — not merged, based on fin/a-benchmark
- Every money cell on image-derived pages is crop-reread (300+450 dpi × 3 thresholds, stacked: 6 Tesseract calls/page).
  ≥4/6 agreeing with the page reading across both resolutions → confirmed; anything else → disputed digits become `?` → held
  for a person. Crop value never substituted. Native digital text pages skipped. Reader revision → bank-payment-rows-v11.
- Benchmark corpus v2 (safety): OLD code had 4 wrong admissions / 7 wrong critical fields; NEW code 0 / 0, exit 0.
  Ready w/o edits 14/33 (only loss on v1 corpus = the wrongly admitted period). Human actions rise (held cells need edits,
  `?` amount loses its sign).
- Residual: same-engine shared misreads, amounts embedded in text cells, consistently-damaged print. Real noisy scans may be
  held more often — measure on held-out documents.
- Tesseract multi-threading under host load makes repair results load-dependent; OMP_THREAD_LIMIT=1 for all engine OCR is
  recommended (not yet changed).
- ⚠ Implication: the LIVE ledger may already contain admitted periods with compensating OCR misreads (scanned card statements
  with only endpoint controls). Worth an audit once v11 ships: re-read admitted image-derived periods read-only and diff.
- c-safety and c-andrews BOTH define "corpus v2" — merge by appending one set after the other; re-run benchmark after merge.

### fin/release-1 FULL SUITE: Ran 5579, FAILED (failures=2, skipped=17) in 709 s
- The 2 = `unassigned_statement` (open product decision: moved continuation pages don't carry balance rows). Nothing else.
- Isolation: run with CHROMADB_PORT=1 (VectorDBService confirmed on :1), but one unclosed-socket warning to 127.0.0.1:8101
  still appeared — something reads `CHROMA_PORT` (default 8101) separately. Future runs: set BOTH `CHROMADB_PORT=1 CHROMA_PORT=1`.

### 2026-10-02 14:47 — c-safety + c-andrews merged into fin/release-1; headless units launched
- Merge commit on fin/release-1: corpus.py conflict resolved (andrews_page takes ocr_lost/endpoint_ocr AND shifts;
  corpus v2 = v1 + c-andrews entries + c-safety entries), manifest regenerated (36 PDFs / 50 periods, v1 bytes unchanged).
- Benchmark on merge (OMP_THREAD_LIMIT=1): **25/49 ready w/o edits (51.0%), 25/40 recoverable (62.5%), 0 wrong admissions (exit 0)**.
  Actions 73 single / 51 grouped. Log: /mnt/owl-data/fin-wt/bench-runs/release-1-merged.log.
- Frontend on merge: tsc -b rc=0; vitest unit 287/295 files pass, 8 fail (mostly timeouts) → fe-triage.
- HEADLESS units (claude -p --permission-mode auto in detached screen, survive logoff; never push), each worktree
  /mnt/owl-data/fin-wt/<unit> on fin/<unit> from fin/release-1: `fe-triage`, `c-merrick` (Merrick dates, biggest lever),
  `c-generic` (generic-layout image reread, safety-gated). Prompts/logs/launcher: /mnt/owl-data/fin-wt/headless/
  (`screen -ls`, `<unit>.jsonl`, `<unit>.err`; each writes WIP-NOTES.md on exit). Relaunch: `headless/launch.sh <unit>`.

### 2026-10-02 16:20 — headless units merged into fin/release-1 (8fe5a376)
- All 3 headless runs exited 0. Merged fe-triage, c-merrick, c-generic (WIP-NOTES.md conflict → dropped from branch;
  notes archived at /mnt/owl-data/fin-wt/notes/<unit>.md).
- **Benchmark on merge: 30/49 ready w/o edits (61.2%), 30/40 recoverable (75.0%), 0 wrong admissions, 0 critical-field
  errors (exit 0).** Actions 54 single / 43 grouped (was 73/51). Log: bench-runs/release-1-r2.log.
- Targeted: statement_* discover 611 OK; closing_only/generic/merrick/exports 40 OK; engine 81 passed; tsc 0.
- fe-triage: vitest unit 295/295 twice on its branch (budget fix, no component bugs).
- Decisions for Neil (from notes): (1) Merrick start = previous closing+1 corroborated by printed balance match, stored
  `derived`; (2) c-generic pinned-repair exception to "never substitute a crop value" (revert 13d03dbe alone to refuse);
  (3) investigator-typed start recorded as `printed` (pre-existing); (4) unassigned_statement 2 failures (pre-existing).
- **Corpus v3 (b-commit on release-1 after 8fe5a376):** c-safety and c-andrews had both put an Andrews 123456789
  statement in 2020-09 with contradictory content → importer rightly held all 4 periods as conflicting; ground truth
  said auto. Compensating case moved to 2021-05 (other 35 PDFs byte-identical).
  **Benchmark corpus v3: 33/49 ready w/o edits (67.3%), 33/40 recoverable (82.5%), 0 wrong admissions.** Log
  bench-runs/release-1-v3.log. Remaining 7 recoverable holds: 5 compensating OCR misreads held by design (credit-one 6+7,
  merrick-08, andrews-2021-05#2, generic-11; jointly constrained, need an INDEPENDENT second reader to clear safely),
  andrews-2020-12#2 (OCR layer lost 2 rows, equal balances), merrick-two-statements#1 (ground truth mislabelled).
- Full backend suite on merged release-1: Ran 6016, 2 failures (known unassigned_statement decision) + 4 errors in
  graph_followup BackfillCommandTests = order-dependent `scripts` package shadowing (evidence-engine/scripts is a
  regular package). Fixed in the test (load by path); module 22 OK standalone and under shadowing. Suite otherwise green.

### 2026-10-02 16:48 — wave 3 launched headless (c-reader2, a-corpus2, b-gate)
- Worktrees from fin/release-1 @ 6335e4e8; common.md baseline updated to corpus v3 (33/49, 0 wrong).
- c-reader2 must not touch the corpus; a-corpus2 must not change pipeline code → no merge conflict expected.
- No external API for statement images (private data) — hosted-model reader only as a Neil decision.

### 2026-10-02 16:55 — deploy blocker 687da296 cleared (Neil: "clear it out if it's not needed")
- Live checkout reset --mixed to origin (no longer ahead; auto-deploy can fast-forward again). Commit is already in
  fin/release-1; also kept as branch `backup/687da296` + file copies in /mnt/owl-data/fin-wt/backup-687da296/.
- This workfile + scripts/headless/ are now UNTRACKED in the live checkout. **Before pushing fin/release-1** (which
  contains them), move these untracked copies aside (merge their newer content into release-1 first) or the deploy's
  fast-forward will fail with "untracked working tree files would be overwritten".

### 2026-10-02 18:44 — wave 3 recovered and relaunched
- c-reader2 + a-corpus2 had exited mid-wait (`-p` exits when the turn ends → background jobs killed). RUN RULE added to
  common.md + every prompt: never background-wait; nohup + foreground poll. Integrator was stopped before it could merge
  half-done units; re-armed to require WIP-NOTES from c-reader2, a-corpus2, b-unique.
- b-gate DONE (4 defects fixed; SQLite gate passes; PG rows UNPROVEN — no PG on 55434). Neil approved the uniqueness
  constraint → b-unique. Live read-only check: 0 violations among 937 admitted statement_review docs.
- v4 corpus (92 PDFs/124 periods) baseline on pre-reader code: 49.2% ready w/o edits, 57.0% of recoverable, 0 wrong.

### 2026-10-02 19:30 — wave 4 queued (Neil: "yes queue all three")
- `fin-wave4-launcher` waits for integrate-3 to exit cleanly, then branches r-recovery / c-image / c-mx-noactivity from the
  merged fin/release-1 and launches them (log headless/wave4.log). `fin-integrate-4` then merges them (integrate-4.md),
  benchmark release-1-w4, suites, STATUS-FOR-NEIL.md (overwrites wave-3's; wave-3 status stays in this Log).
- r-recovery = selective recovery campaign for today's readers (flag default OFF, Neil activates) + live READ-ONLY dry-run
  estimate of how many held items become ready + read-only ledger audit for compensating misreads.

### 2026-10-02 19:45 — wave 3 merged into fin/release-1 (headless integrate-3)
- Merged (no conflicts; WIP-NOTES.md dropped; notes archived /mnt/owl-data/fin-wt/notes/{c-reader2,a-corpus2,b-gate,b-unique}.md):
  `fin/c-reader2` (c6945a42), `fin/a-corpus2` (aa211905), `fin/b-unique` incl. `fin/b-gate` (0241dc5d). None refused:
  every unit's notes say landed and every unit benchmark exited 0. No merge fixes needed.
- **Benchmark on merge** (corpus v4 = 92 PDFs / 124 periods, OMP_THREAD_LIMIT=1, exit 0; bench-runs/release-1-w3):
  - v1–v3 subset: 33/49 → **37/49 ready w/o edits (75.5%)**, recoverable 33/40 → **37/40 (92.5%)**, 0 wrong. Actions
    51/43 → 30/22. By family: Andrews 21/24 (rec 21/22), Credit One 5/8 (5/6), generic 8/13 (8/8), Merrick 3/5 (3/4).
  - v4 additions: **28/75 (37.3%)**, recoverable 28/67 (41.8%), must-hold 8/8 kept, 0 wrong — unchanged vs a-corpus2's
    pre-reader run. Second reader: 4 repaired (v1–v3: andrews-2021-05#2, credit-one-7, generic-11,
    merrick-08, all saved values printed ones), 15 declined (credit-one-6 + all 14 v4 degraded/skewed pages it tried). By family: Andrews 7/22 (rec 7/21), BBVA 3/7
    (3/6), Capital One 4/7 (4/6), Credit One 2/2, generic 6/14 (6/12), Intercam 1/1, Kapital 2/4, Monex 0/4,
    Santander 3/8 (3/7), Scotiabank 0/4, deposit receipts 0/2 (held, correct).
  - All: 61/124 → **65/124 (52.4%)**, recoverable 57.0% → 60.7%, 0 wrong admissions, 0 critical-field errors.
  - Monex shows 2 `currency_wrong` proposals not in a-corpus2's run: harness artifact, not pipeline (see Open defects).
- Suites on merge: financial pattern (CLAUDE.md command, live .venv, CHROMADB_PORT=1 CHROMA_PORT=1) **Ran 5650,
  failures=2**; all-tests pattern `test_*.py` **Ran 6041, failures=2, errors=0** (was 6016 / 2 / 4). The 2 = known
  `unassigned_statement`. b-unique's 2 `recovery_preparation` failures under pytest did NOT reproduce under unittest.
  Frontend tsc -b 0; vitest unit **295/295 files, 2053 tests**. Logs: fin-wt/release-1-w3-{fullsuite,allsuite}.log,
  bench-runs/release-1-w3{,.log}, bench-runs/release-1-w3-vitest.log.
- Folded this workfile + `scripts/headless/` (financial-prompt.md identical) into fin/release-1. Live untracked copies
  left in place: **move them aside right before the push** (see ▶ NEXT).
- Plain-language status: /mnt/owl-data/fin-wt/headless/STATUS-FOR-NEIL.md.
- fin/release-1 head **1c840355** (workfile fold). The live workfile has changed only by this head line since that commit.

### 2026-10-02 21:55 — wave 4 merged into fin/release-1 (headless integrate-4)
- Merged, none refused (every unit's notes say landed; every unit benchmark exited 0; WIP-NOTES.md dropped; notes archived
  /mnt/owl-data/fin-wt/notes/{r-recovery,c-image,c-mx-noactivity}.md): `fin/r-recovery` (3f3057b3), `fin/c-image`
  (08a4cb3d), `fin/c-mx-noactivity` (9e215ee0; one conflict in `services/financial/__init__.py`, both sides appended an
  export, kept both). Merge fix b5ebfeb7: c-image changed `pdf_extraction.py`, so the wave-3 reader's digest
  (7bd84c16, `e6526e20…`) joins `AFFECTED_EXTRACTION_SHA256` as r-recovery's notes asked (current file `003d53a6…`
  stays excluded; 34 recovery/exports tests pass).
- **Benchmark on merge** (corpus v4, OMP_THREAD_LIMIT=1; exit status not captured, the script exits 1 only on a wrong admission and there were 0; bench-runs/release-1-w4{,.log}):
  - All: 65/124 → **93/124 ready w/o edits (75.0%)**; recoverable 65/107 → **93/107 (86.9%)**; 0 wrong admissions,
    0 critical-field errors (301 saved from 93 periods); held kept out 10/10. Actions 277/251 → 122/114. Gains are exactly
    additive: c-image +17, c-mx-noactivity +11, r-recovery 0 (no fresh-upload change).
  - v1–v3 subset: 37/49 → 37/49 (75.5%), recoverable 37/40, unchanged. Andrews 21/24, Credit One 5/8, generic 8/13, Merrick 3/5.
  - v4 additions: 28/75 → **56/75 (74.7%)**, recoverable 28/67 → 56/67 (83.6%). By family: Andrews 7 → 18/22
    (rec 18/21), generic 6 → 12/14 (12/12), Santander 3 → 7/8 (7/7), Kapital 2 → 4/4, Monex 0 → 2/4, Scotiabank 0 → 3/4;
    unchanged BBVA 3/7, Capital One 4/7, Credit One 2/2, Intercam 1/1, deposit receipts 0/2 (held, correct).
  - 14 recoverable still held → next wave in ▶ NEXT. 2 `currency_wrong` proposals = the Monex pairing artefact (Open defects).
- Suites on merge (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): financial **Ran 5669, failures=2**; all-tests **Ran 6060,
  failures=2, errors=0** (the 2 = known `unassigned_statement`); engine pytest (c-image's selection) 462 passed 8 skipped;
  tsc -b 0; vitest unit **295/295 files, 2053 tests**. Logs fin-wt/release-1-w4-{fullsuite,allsuite}.log,
  bench-runs/release-1-w4-vitest.log. r-recovery's pytest-only adjacent suites have 12 pre-existing `DetachedInstanceError`
  failures (identical on 1c840355, per its notes); not run here.
- r-recovery live dry-run estimate and live ledger audit: **NOT run** (no counts exist); see ▶ NEXT for the commands.
- Plain-language status: /mnt/owl-data/fin-wt/headless/STATUS-FOR-NEIL.md.
