# Financial automation — headless workfile

Working file for `automation-delivery-plan-2026-09-28.md`. Every session (headless or
interactive) reads this after `CLAUDE.md`, does the **▶ NEXT** unit and nothing else,
then rewrites ▶ NEXT and appends to the log before it exits.

STATUS: RUN

(Set the line above to `STATUS: HALT — <reason>` to stop the headless runner. A session
sets it itself only when it is genuinely blocked on Neil; see "Halt rules".)

---

## ▶ NEXT

**(2026-10-22 04:40) REAL-DOCUMENT wave 13 integrated into fin/release-1 (headless integrate-13). Regular merges of
t-visual-v19 f58d6dbf (truth and audit tooling only), r13-andrews ab5c16ef and r13-merrick 3e8e7f06, on 48e58b67;
WIP-NOTES.md dropped; no conflicts. NOT pushed or deployed by this session. Running state, counts and history in
/mnt/owl-data/fin-wt/headless/real/STATE.md (counts only).**
Real headline (bench/wave13 = a fresh whole-set run of frozen 3e8e7f06, 797 documents, 1,729 distinct verified periods,
reading v24 with v25 on the Andrews documents; product default, automatic save ON): **1,645/1,729 ready without edits
(95.1%), recoverable 1,645/1,724 (95.4%)**, all saved by the system with no click; on wave 12's 796 documents
**1,440/1,524 (was 1,404)**; **0 wrong admissions, 0 critical-field errors (25,489 rows), 0 duplicate ledger
contributions**, must-hold 5/5, 0 lost, 241 gained (Navy Federal 205 on its first scored truth, engine only; Andrews
231 -> 255; Merrick 23 -> 35). Saved holder differs 0. **Generic-only 1,242/1,729, 0 wrong.** New, reported (not a wrong
admission): 3 Andrews closed share sections saved without a closing balance (truth 0.00, no money moves). Copies held
168/171; REAL_EXIT=1 still only for dcfc8ce1f2afc#1 (Neil rule). Actions per 100 statements **137 / 128** (wave 12 under
the same re-read simulation: 172 / 159). Truth final 829/832 (+1, +205 verified periods), compared 797/815. Live
(read-only audit-wave13): identical to audit-v19 (the same 6 disagreeing periods, 1 double admission, 3 Kapital holders).
Synthetic 108/125, 0 wrong. Suites: financial Ran 6,597, only the 2 known unassigned_statement failures after a rerun of
two load-timeout modules (19 OK) and the known intermittent page-identity test; tsc 0; vitest unit 2,130/2,130.
**Wave 14 (headless/real/wave14.units, prompts headless/real/units/):** `t-visual-v11` and `t-visual-v12` (the last 3
Capital One confirm documents, 832/832 final; v12 also brings the 18 all-unverified documents into the comparison,
815/815), `r14-santander` (the 3 Andrews closed-section closings first; Santander 18 held, 393 actions; target >= 138/146).
Acceptance for every unit: 0 wrong admissions real (product; generic-only must not add any) and synthetic, no new copy
saved, synthetic >= 108/125, no ready period lost against bench/wave13.
**Live:** the reunion ca059a42 (deployed 2026-10-17, engine v19). Deploy of fin/release-1 recommended now (STATE.md open
decision 1).
**Everything below in this section is the synthetic track (wave 5 state), parked behind the real waves.**
Release-1 now (corpus v4, 124 distinct periods, bench-runs/release-1-w5, exit 0): **102/124 ready without edits (82.3%)**,
102/107 recoverable (95.3%), 0 wrong admissions, 0 critical-field errors (347 saved), 0 valid-looking wrong values
proposed, held kept out 10/10. v1–v3 subset 38/49 (was 37); v4 additions 64/75 (was 56). Baseline was 93/124 (75.0%);
c-mx-layouts' corrected-pairing rerun of that baseline is also 93/124, 93/107, 37/49, with 0 false `currency_wrong`.
Suites: financial 5710 (only the 2 known `unassigned_statement` failures; 3 load timeouts rerun OK, see Log); engine
selection 167 passed; tsc 0; vitest unit 295/295 after the route-check fix 41a306a8.

**Next synthetic wave (≤3 headless units from fin/release-1, ranked by recoverable periods still held; only 5 remain):**
1. **`fin/c-mx-real-fit`: Scotiabank with-movements + Monex peso-movements on REAL pages** (3 periods:
   scotiabank-2024-06-with-movements, monex-2024-04 #1 and #2). The c-mx-layouts scaffolds (switch
   `LOUPE_FINANCIAL_MX_MOVEMENT_SCAFFOLD`, default OFF) were written against invented layouts; switched on they admit
   scotiabank-2024-06 only, which proves nothing. Launch only once the real-document census (r-census) has located a
   real Scotiabank statement with movements or a real Monex contract with a movements page; fit the readers to it and
   regenerate the two invented corpus files from it. Without a real page this unit does not run.
2. **`fin/a-merrick-truth`: merrick-two-statements #1** (1 period, `dates 2`, period_start_unprinted). Earlier note says
   the ground truth is mislabelled. Verify against the PDF; fix the corpus truth if so (scoring only), the pipeline if not.
3. **`fin/c-cancelling-reader`: credit-one-cycle-6** (1 period, compensating misreads). Held by design until an
   independent reader agrees; the glyph second reader declines it. Only admit on agreement of an independent reading
   with the printed values; holding stays correct otherwise.
Correctly held and not in a unit: 10 must-hold (omitted rows, missing pages, deposit receipts) and 7 genuine decisions
(holder/account not printed, no activity, quiet section across pages).

**Open Neil decisions (nothing above waits on them; all have a recorded default):**
- **Deployed: a15230a0 is live** (Neil's interactive session, 2026-10-10): real waves 1-4 without r4-any-layout, plus the
  investigator-feedback work. Never deploy a head containing 435a6514 without its r5-any-layout fix (fin/release-1 carries both since
  780b31a1; wave 5 is measured 0 wrong and not deployed).
- **Live double admission: resolved.** The read-only audit on 2026-10-11 finds 0 printed periods admitted twice (was 102);
  the set-aside was applied live (not by the headless runner).
- **5 live periods disagree with verified truth** (opaque ids in headless/real/STATE.md, audit 2026-10-13): 3 that the
  current code reads equal to truth (re-read them), and the investigator's 2 hand-entered Synchrony periods with every
  row's direction inverted (set the card account's type, or re-read after r6-synchrony; live writes, interactive).
- **Route-check: deployed.** a15230a0 (live) carries the route-check fix 41a306a8 (no more 500 from the missing
  `MAX_BATCH_SIZE`) and upstream 4309cb5f, which removed the route-check file limit itself; our frontend unit test still
  asserts that limit (the one vitest failure). Recommend aligning that test with the server.
- **Engine and backend deploy together (wave 5 and c-image).** The engine's money-cell reread imports new backend
  functions (`bbva_page_statement`, `capital_one_page_statement`); an engine without the matching backend skips the
  cell reread for every layout (held, never wrong, but repairs lost). The engine also records scan preparation, which an
  older backend rejects.
- **Live reader-recovery dry run + ledger audit (r-recovery) — NOT run.** Both scripts are read-only (READ ONLY
  transaction, verified evidence hashes, private scratch dir). From `backend/` with the service env loaded:
  `OMP_THREAD_LIMIT=1 python3 scripts/financial_reader_recovery_estimate.py --case <case> --select-only`, then without
  `--select-only` and `--out /mnt/owl-data/fin-wt/r-recovery-estimate`;
  `OMP_THREAD_LIMIT=1 python3 scripts/financial_ledger_misread_audit.py --case <case> --out /mnt/owl-data/fin-wt/r-recovery-audit`.
  Then decide `LOUPE_FINANCIAL_READER_RECOVERY=1` (default OFF). Live sources gain nothing from waves 3–5 until re-read.
  Wave 5 added c-image-fields' engine file (f0afcaf9) to `AFFECTED_EXTRACTION_SHA256`; the current file (6d388613) is
  absent by design.
- **Disposable PostgreSQL on 127.0.0.1:55434** (or name an instance that may hold throwaway schemas). Without it the
  b-gate PG rows (two-worker exactly-once, save vs group confirmation, deadlock, removal, recovery prep ×6, concurrent
  `queue_import` lock order, audit triggers), b-unique's 4 PG tests and r-recovery's PG-only paths (row locks,
  `SHOW transaction_read_only`) have never executed: they are UNPROVEN. Run both `backend/tests/*_postgres.py` files
  (`LOUPE_TEST_LOCAL_POSTGRES=1`) before deploying the migration below.
- **Migration `20261002_one_active_statement` to apply at deploy** (`alembic upgrade`, single head, down_revision
  `20260924_statement_recovery`). Deferred EXCLUDE constraint: one active admitted statement copy per case + evidence
  file + statement id. Takes ACCESS EXCLUSIVE on `financial_source_documents` (~1k rows) briefly; refuses with an
  offender list (adds nothing) if duplicates exist. Live read-only check 2 Oct: 0 offenders among 937. Approved in
  principle; PG-semantic acceptance unproven (parsed only). Waves 4 and 5 added no migration.
- **Wave 5 reader rules (each decided; reverse in one place):**
  - c-image-fields: BBVA labels accept one or two non-N glyphs where `ó` prints (reverse: an explicit list of observed
    misreadings); Capital One `$` cell reread allowed, printed sign must be kept (reverse: drop the Capital One branch of
    cc9c6224; capital-one-2025-01 returns to held).
  - c-andrews-residue: (1) a sign no reader named is accepted only when two confirmed balances fix it and the verb is
    "Withdrawal" (reverse: drop `crop_digits_signed_by_controls` in `_printed_readings`; 2022-08 held); (2) the page
    reading may beat a 4-of-6 crop majority when crops at both dpis also read it and confirmed neighbours fix it
    (reverse: drop the `page_reading` candidate; 2022-05 held); (3) an image reading may replace an embedded OCR layer by
    adding lines only where the layer left printed ink unread and every existing row is reproduced exactly (reverse:
    remove `or unread` from the routing condition in `_extract_pdf_sync`; 2020-12 held).
  - c-mx-layouts: keep `LOUPE_FINANCIAL_MX_MOVEMENT_SCAFFOLD` OFF in production until fitted to a real page; do not quote
    the switch-on 94/124 as a release number.
- **c-image**: geometry in the straightened frame (highlights up to ~9 pt / ~22 pt off near corners on turned pages until
  the viewer applies `deskew_degrees`, not built); inkless words dropped on prepared scans (`ocr_inkless_words`); kill
  switch `PDF_SCAN_PREPROCESSING=false`. Synthetic damage only.
- **c-mx-noactivity**: printed zero totals + equal printed balances count as source proof (`printed_zero_totals`);
  reverse if only printed counts of 0 qualify.
- **r-recovery**: system re-reads attributed to the batch owner; files with any ready period are left alone.
- **Second reader (c-reader2)**: glyph reader + crop agreement + page reconciliation as independent evidence (default ON;
  kill switch `STATEMENT_GLYPH_SECOND_READER=false`); 4-of-6 crop contradiction; templates from non-money digits; show
  repaired cells beside the machine reading in the UI (not built, now also for the wave-5 Andrews pinned repairs).
- **a-corpus2**: route deposit receipts out of statement batches automatically?; Mexican zero-activity sections treated
  as `auto` in ground truth; regenerate the invented Monex/Scotiabank movement corpus files from real pages.
- **Carried**: Merrick start = previous closing + 1 stored `derived`; c-generic pinned-repair exception to "never
  substitute a crop value" (revert 13d03dbe to refuse); investigator-typed start recorded as `printed`;
  `unassigned_statement` (moved continuation pages don't carry balance rows; the only 2 suite failures); U2 Neo4j index
  auto-creation on first live run; check the suspected duplicate population (232 = 232) before the case's next import
  auto-projects it.
- **After the next deploy:** readiness refresh for the case; close matching error-register items with Alex.

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

- **AUTO_SAVE_READY saves an exact copy** (2d8bdf20, default ON): synthetic run with the product default saved the byte
  copy generic-01-copy-of-clean.pdf#1 (copies 0/1, 5 duplicate ledger rows); with FINANCIAL_AUTO_SAVE_READY=0 it is set
  aside (1/1). Likely: the save fires per file before the batch compares files. Wave 7 r7-autosave. Found integrate-6.
- **CLAUDE.md suite command runs with auto-save ON**: `unittest discover` never loads tests/conftest.py (its only job is
  FINANCIAL_AUTO_SAVE_READY=0): 63 failures + 60 errors. Until fixed, prefix the command with
  FINANCIAL_AUTO_SAVE_READY=0 (then only the 2 known + 8 test_financial_exports failures for the interactive modules
  auto_read, batch_file_overview, batch_selection_preview, batch_supersession, field_proposals, queue_save, review_queue,
  statement_detection). Wave 7 r7-autosave. Found integrate-6.
- **Benchmark import turn budget**: on fin/release-1 the harness group import used all 2,711 turns and left 105 ready
  items pending (660 turns before the interactive queue/save work). Wave 7 r7-autosave. Found integrate-6.
- `tests.test_financial_extraction_release` (3 of 4 tests) spawns `scripts/check_financial_extraction_release.py`
  with a 20 s subprocess timeout; each spawn takes ~14 s at load 5–6 and times out at load ~13 (full suite during a
  benchmark, integrate-5). Reruns alone OK. Not a code fault; raise the timeout or run the suite without a concurrent
  benchmark. Found 2026-10-04 integrate-5.
- (closed) Benchmark pairing by currency: fixed by c-mx-layouts 78acd7b5, merged 3b125433. Monex 2024-03 now pairs
  #1→MXN, #2→USD; false `currency_wrong` 2 → 0.
- (closed) `/route-check` NameError on `MAX_BATCH_SIZE` after merge 97878ff8: fixed 41a306a8 on fin/release-1; live until
  pushed.

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

### 2026-10-04 10:40 — wave 5 launched headless
- `fin/c-image-fields`, `fin/c-andrews-residue`, `fin/c-mx-layouts` (worktrees /mnt/owl-data/fin-wt/<unit>, from
  fin/release-1 @ 73cbc888) via headless/launch.sh (now also appends run-rule.md). Prompts headless/<unit>.md.
- `fin-integrate-5` watcher (headless/after-wave5.sh) runs integrate-5.md when all three exit with WIP-NOTES.md:
  merge, benchmark bench-runs/release-1-w5, suites, rewrite ▶ NEXT, STATUS-FOR-NEIL.md. Never pushes.

### 2026-10-04 — release 1 pushed (Neil)
- Merged origin `7d04cb24` (remove 50-file ingestion batch caps, Conor) into fin/release-1 (97878ff8, clean).
- Live checkout's untracked workfile + scripts/headless moved to /mnt/owl-data/fin-wt/live-untracked-aside-20261004
  (now tracked; the copies here are authoritative). fin/release-1 pushed to `integration/evidence-main-reunion`.
- From now on the workfile is TRACKED in the live checkout: never edit it there (a dirty tree blocks deploy.sh).
  Edit it in /mnt/owl-data/fin-wt/release-1 and commit on fin/release-1.
- After deploy: readiness refresh for the case; close matching error-register items with Alex.

### 2026-10-04 11:25 — REAL-DOCUMENT phase launched (Neil: "use all statements… completely comprehensive")
- Every number so far was on the SYNTHETIC corpus. From now on the headline is measured on ALL of Alex's real statements
  (6 cases, ~1,030 source documents, ~4,000 batch items): per-statement comparison of processor output vs independent
  ground truth, fixes in the processor, residual manual work as batch workflows (Neil's goal, quoted in real-common.md).
- Self-driving chain in screen `fin-real-driver` (headless/real/driver.sh) + `fin-real-cont` (waves 11–40):
  wave 0 = r-census (re-read every file in every case with current code, read-only) + t-truth (inventory, pdfplumber
  tier-A truth, private real benchmark, live-ledger disagreement audit, visual-reading queue) → integrate-0 (waits for
  wave-5 integration) → planner writes waveN.units + units/*.md → units → integrate-N … until the planner's STOP rule.
- Private data only under /mnt/owl-data/fin-real (700). State: headless/real/STATE.md; log headless/real/driver.log.
  Stop it: `touch /mnt/owl-data/fin-wt/headless/real/STOP`. Never pushes or deploys.

### 2026-10-04 12:00 — wave 5 merged into fin/release-1 (headless integrate-5)
- Merged, none refused (every unit's notes say landed; every unit benchmark exited 0; WIP-NOTES.md dropped; notes archived
  /mnt/owl-data/fin-wt/notes/{c-image-fields,c-andrews-residue,c-mx-layouts}.md): `fin/c-mx-layouts` (3b125433),
  `fin/c-image-fields` (560a10de), `fin/c-andrews-residue` (7a89e656). One conflict, in `recovery_campaigns.py`: both
  units bumped `PDF_READING_REVISION` to `bank-payment-rows-v13` and rewrote the digest comment. Neither v13 file was
  deployed (live is v12), so v13 stays. c-image-fields changed `pdf_extraction.py` only by that bump (its engine work
  is in `financial_amount_ocr.py`), so the merged file is byte-identical to c-andrews-residue's (`6d388613…`) and stays
  off `AFFECTED_EXTRACTION_SHA256`; c-image-fields' file `f0afcaf9…` joins it. recovery_readers 18 passed.
- **Merge breakage fixed, 41a306a8:** vitest `use-route-checks.test.tsx` failed: `MAX_BATCH_SIZE` no longer declared in
  `backend/routers/evidence.py`. Cause is NOT wave 5: merge 97878ff8 (origin 7d04cb24, remove 50-file ingestion caps)
  deleted the constant while our `/route-check` still uses it, so every non-empty route-check request raised NameError
  and returned 500. **This is in the pushed release.** Restored the constant scoped to route-check only (processing
  stays uncapped). Backend route_check tests (33) never call the endpoint, which is why only the frontend guard caught it.
- **Benchmark on merge** (corpus v4, OMP_THREAD_LIMIT=1, **BENCH_EXIT=0**, bench-runs/release-1-w5{,.log}; code 7a89e656):
  - Baseline: wave-4 93/124 (75.0%). c-mx-layouts corrected the harness pairing; its rerun of the same code
    (bench-runs/c-mx-layouts-harness) restates the baseline identically: 93/124, 93/107, v1–v3 37/49, 0 wrong, but 0
    (not 2) valid-looking wrong values proposed.
  - All: 93/124 → **102/124 ready w/o edits (82.3%)**; recoverable 93/107 → **102/107 (95.3%)**; 0 wrong admissions,
    0 critical-field errors (347 saved from 102 periods), held kept out 10/10, valid-looking wrong values proposed 0.
    Actions 122/114 → 59/51. Gains exactly additive, per-period diff vs release-1-w4 shows only the 9 target periods
    moved: c-image-fields +5 (bbva-2024-07, -08, -09; capital-one-2025-01, -03), c-andrews-residue +4 (2020-12#2,
    v4 2022-04/05/08 #2), c-mx-layouts 0 (scaffold off by default).
  - v1–v3 subset: 37/49 → **38/49 (77.6%)**, recoverable 37/40 → 38/40 (andrews-2020-12). Andrews 22/24 (rec 22/22), Credit One 5/8 (5/6),
    generic 8/12 distinct (8/8; earlier logs said 8/13, counting the exact copy), Merrick 3/5 (3/4).
  - v4 additions: 56/75 → **64/75 (85.3%)**, recoverable 56/67 → 64/67. By family: Andrews 18 → 21/22 (rec 21/21), BBVA
    3 → 6/7 (6/6), Capital One 4 → 6/7 (6/6); unchanged generic 12/14, Santander 7/8, Kapital 4/4, Monex 2/4,
    Scotiabank 3/4, Credit One 2/2, Intercam 1/1, deposit receipts 0/2 (held, correct).
  - All families: Andrews share 43/46 (rec 43/43), BBVA 6/7, Capital One 6/7, Credit One 7/10 (7/8), generic 20/26
    (20/20), Merrick 3/5 (3/4), Monex 2/4 (2/4), Santander 7/8, Scotiabank 3/4 (3/4), Kapital 4/4, Intercam 1/1.
  - 5 recoverable still held: credit-one-6 (by design), merrick-two-statements#1, scotiabank-2024-06-with-movements,
    monex-2024-04 #1/#2 (invented layouts). Engine read 722 s wall at load up to 13 (not comparable).
- Suites on merge (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): financial **Ran 5710, failures=2, errors=3, skipped=17**;
  the 2 = known `unassigned_statement`; the 3 errors = `test_financial_extraction_release` 20 s subprocess timeouts at
  load ~13, module rerun alone **4 OK** (Open defects). Engine pytest (wave-5 + reader modules, 10 files) **167 passed**.
  tsc -b 0; vitest unit 294/295 with the route-check guard failing, fixed by 41a306a8 (that file 12/12 after). Logs
  fin-wt/release-1-w5-fullsuite.log, bench-runs/release-1-w5-vitest.log. All-tests pattern not run.
- Plain-language status: /mnt/owl-data/fin-wt/headless/STATUS-FOR-NEIL.md (overwrites wave 4's).

### 2026-10-05 07:30 — REAL-DOCUMENT wave 0 merged into fin/release-1 (headless integrate-0)
- Merged, none refused (both units' notes say complete; diffs are benchmark/script code and tests only, scanned for real
  identifiers: none; WIP-NOTES.md dropped; notes archived /mnt/owl-data/fin-wt/notes/{t-truth,r-census}.md):
  `fin/t-truth` (423f8003: real_inventory, real_truth tier-A pdfplumber reader, harness private-corpus mode with
  `--rescore`/`--score`, real_ledger_audit, scripts/run_real_benchmark.sh) and `fin/r-census` (e07ff7bd:
  scripts/financial_statement_census.py, all-files read-only census). No conflicts; harness.py auto-merged with wave 5.
- **Real benchmark on merge** (verified truth, 485 documents, OMP_THREAD_LIMIT=1, REAL_EXIT=0,
  /mnt/owl-data/fin-real/bench/wave0; engine read 3.9 h + import 2.9 h): **484/761 ready w/o edits (63.6%)**, recoverable
  484/760, 0 wrong, 0 critical-field errors (10,484 rows from 695 periods), 0 valid-looking wrong values (the baseline's
  38 `account_wrong` came from proposal checks the rescore does not recompute), exact repeats held 3/145, duplicate
  ledger contributions 1,691. Baseline release-1 rescored 484/760: wave 5 moved nothing on real statements (5 periods
  changed state, none to ready or wrong). Monex 0/167 and Citi 0/46 not detected; Santander 9/41 (currency 24).
- Live ledger audit rerun read-only (/mnt/owl-data/fin-real/audit-wave0): unchanged — 5 disagree, 107 printed periods
  admitted twice in one case. Census not rerun (r-census figures on a3691d2c: 709/1,811 = 39.1%).
- Synthetic (bench-runs/real-wave0, BENCH_EXIT=0): 102/124, 102/107, 0 wrong — equal to wave 5.
- Suites (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): financial **Ran 5740, failures=2** (known unassigned_statement),
  skipped 20; tsc -b 0; vitest unit 2052/2053 — LedgerTracingWorkbench failed under benchmark load, alone 7/7, no
  frontend change in this wave. Logs fin-wt/release-1-realw0-fullsuite.log, bench-runs/real-wave0-frontend.log.
- Decided (reversible in one line; recorded in headless/real/STATE.md): identical-transaction overlap between files =
  duplicate set-aside; mostly-invisible text pages = recognised text whatever the image coverage.
- Wave 1 planned: r1-reproduced, r1-monex-citi, t-visual-v10. STATUS-FOR-NEIL.md rewritten.

### 2026-10-06 04:10 — REAL-DOCUMENT wave 1 merged into fin/release-1 (headless integrate-1)
- Merged, none refused (all three notes say complete, 0 wrong admissions on real and synthetic; diffs scanned for every
  holder/account token in the private truth: one hit, the generic contract-type word on synthetic Monex covers, no real
  data; WIP-NOTES.md dropped; notes archived /mnt/owl-data/fin-wt/notes/{r1-reproduced,r1-monex-citi,t-visual-v10}.md):
  `fin/r1-reproduced` (04eb0037), `fin/r1-monex-citi` (4f566f1c), `fin/t-visual-v10` (ae9486ca). Conflicts in harness.py
  (`--readings` + `--compare`, both kept) and statement_import_overlap.coverage_review (masked same-printed-period copy
  is an exact match AND the same-file second-statement hold applies); 12 targeted modules 294 OK before committing.
- Shared truth: Monex regenerated with r1-monex-citi's yen fix (171 verified); backup truth-backup-pre-int1.
- **Real benchmark, fresh read** (bench/wave1, REAL_EXIT=0, read 3.7 h + import 8.2 h): **800/1,035 ready w/o edits
  (77.3%)**, recoverable 797/1,028, 0 wrong, 0 critical (10,622 rows), holds 4/4, copies held 145/145. Wave-0 run
  rescored on the same truth (bench/wave0-int1): 585/1,035, 2 wrong, holds 2/4, copies 3/145. Compare files 485/724.
- Census rerun on all 6 cases with r1-reproduced's reading cache (engine tree identical): 1,017/1,896 (53.6%).
- Live ledger audit (read-only, audit-wave1): unchanged — 5 disagree, 102 printed periods admitted twice.
- Synthetic (bench-runs/real-wave1, BENCH_EXIT=0): 105/125, 105/108, 0 wrong.
- Suites (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): financial **Ran 5807, failures=2** (known unassigned_statement),
  skipped 20; tsc -b 0; vitest unit 295 files 2054/2054. Logs bench-runs/real-wave1-{suite,tsc,vitest}.log.
- Wave 2 planned (Neil directive): r2-any-layout, r2-admitted-duplicates (existing prompts, untouched), t-visual-v07.
  STATUS-FOR-NEIL.md rewritten.

### 2026-10-07 02:50 — REAL-DOCUMENT wave 2 merged into fin/release-1 (headless integrate-2)
- Merged, none refused (all three notes say complete, 0 wrong admissions on real and synthetic; added lines scanned
  for every holder/account token in the private truth and every inventory file name: only generic bank legal-form
  words; WIP-NOTES.md dropped; notes archived /mnt/owl-data/fin-wt/notes/{t-visual-v07,r2-admitted-duplicates,
  r2-any-layout}.md): `fin/t-visual-v07` (eddfefbd), `fin/r2-admitted-duplicates` (80645846), `fin/r2-any-layout`
  (080664d2). One conflict: services/financial/__init__.py export blocks, both kept; 10 targeted modules 278 OK first.
- Not merged into the shared truth: r2-any-layout's 9 visually read periods (holder printed but untranscribed, labelled
  decision; documents stay in shard v08).
- **Real benchmark** (bench/wave2, REAL_EXIT=0; wave-1 readings for 485 documents, evidence-engine tree unchanged,
  plus a fresh read of the 40 v07 documents; import 6.8 h): **821/1,089 ready w/o edits**, 821/1,035 on wave-1 truth
  (was 800), recoverable 818/1,082, 0 wrong, 0 critical (11,514 rows), holds 4/4, copies 145/145; v07 0/54 ready.
  Compare files 525/724.
- Census rerun on all 6 cases (cached readings, census-wave2): 1,038/2,343 (44.3%); ready +21, denominator +447.
- Live ledger audit (read-only, audit-wave2): unchanged — 5 disagree, 102 printed periods admitted twice.
- Synthetic (bench-runs/real-wave2, BENCH_EXIT=0): 105/125, 105/108, 0 wrong.
- Suites (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): financial **Ran 5866, failures=2** (known unassigned_statement),
  skipped 20; tsc -b 0; vitest unit 296 files 2058/2058. Logs bench-runs/real-wave2-{suite,tsc,vitest}.log.
- Wave 3 planned: r3-any-layout, r3-andrews, t-visual-v13. STATUS-FOR-NEIL.md rewritten.

### 2026-10-08 13:55 — REAL-DOCUMENT wave 3 merged into fin/release-1 (headless integrate-3)
- Merged, none refused (all three notes say complete, 0 wrong admissions on real and synthetic; added lines and
  commit messages scanned for every holder, account, inventory file name and large amount in the private truth: only
  generic bank legal-form words and a synthetic fixture; r3-andrews and r3-any-layout had rewritten their own
  histories to remove real values before notes; WIP-NOTES.md dropped; notes archived
  /mnt/owl-data/fin-wt/notes/{t-visual-v13,r3-andrews,r3-any-layout}.md): `fin/t-visual-v13` (4d9cfdff),
  `fin/r3-andrews` (0a20fe1f), `fin/r3-any-layout` (d07ed24c). No conflicts; statement_import_andrews.py and
  pdf_extraction.py auto-merged (disjoint hunks); 14 backend modules 299 OK and 3 engine modules 111 passed first.
- **Real benchmark, full fresh read** (bench/wave3, REAL_EXIT=0; read 2 h 52 min, import about 13 h): **977/1,191
  ready w/o edits**, recoverable 977/1,187, 0 wrong, 0 critical (13,464 rows), holds 4/4, copies 148/148, 0 lost
  against wave 2; 67 valid-looking wrong values, none in a ready period. Compare files 529/724 (1,047 of 1,393
  without disagreement).
- Census rerun on all 6 cases (earlier reading cache; census-wave3): 1,100/2,386 (46.1%). It found 107 originals in
  live batches that the truth inventory (4 Oct) does not list, one of them a 345-page production with 287 engine
  periods.
- Live ledger audit (read-only, audit-wave3): 6 disagree (5 known + d5a3ad9b75a08#5), 102 printed periods admitted
  twice.
- Synthetic (bench-runs/real-wave3, BENCH_EXIT=0): 105/125, 105/108, 0 wrong.
- Suites (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): financial **Ran 5,922, failures=2** (known
  unassigned_statement), errors=1 (test_financial_extraction_release subprocess timeout under load; alone 4/4 OK),
  skipped 20; tsc -b 0; vitest unit 297 files 2,060/2,060. Logs bench-runs/real-wave3-{suite,tsc,vitest}.log.
- Found, not fixed (planned): 46 Monex periods whose truth holder is not a holder (truth defect); BBVA holder drops
  the printed legal form on 30 periods; one Capital One copy-pairing scoring artefact.
- Wave 4 planned: r4-any-layout, r4-cards, t-visual-v08. STATUS-FOR-NEIL.md rewritten.

### 2026-10-10 14:15 — REAL-DOCUMENT wave 4 merged into fin/release-1 (headless integrate-4)
- All three notes say complete with 0 wrong; all three SQUASH-merged (history carried real values): `fin/t-visual-v08`
  (3512460d; one fixture company name replaced), `fin/r4-any-layout` (435a6514; 11 real amount literals in tests and
  comments replaced by same-shape synthetic figures), `fin/r4-cards` (8f9258c8; unit had scrubbed its tree, intermediate
  commits quoted real values). Private scan of added lines + messages clean after scrub. WIP-NOTES.md dropped; notes
  archived /mnt/owl-data/fin-wt/notes/{t-visual-v08,r4-any-layout,r4-cards}.md. No conflicts. Merge checks: 94, 128,
  178 OK backend; 285 passed evidence engine.
- **Real benchmark, full fresh read on 8f9258c8** (bench/wave4, 3 h 20 min read, ~14 h import): 1,050/1,237, **REAL_EXIT=1:
  1 wrong admission** (r4-any-layout; see ▶ NEXT). **Reverted 2a9ba3ab**; replay confirms; whole set re-run on 2a9ba3ab
  with the wave-4 readings (bench/wave4-final, ~11 h): **1,034/1,237, 0 wrong, 0 critical, 0 lost**, exit 0.
- Census (8f9258c8, cached readings, census-wave4): 1,118/2,466 (45.3%); currency-only holds 344 -> 241.
- Live ledger audit (read-only, audit-wave4): unchanged.
- Synthetic 105/125, 0 wrong, BENCH_EXIT=0 on both heads (bench-runs/real-wave4, real-wave4-final).
- Suites: financial **Ran 5,948, failures=2** on 2a9ba3ab (5,976 on 8f9258c8, same 2); tsc -b 0; vitest unit 2,070/2,071
  (use-route-checks batch-limit test fails since upstream 4309cb5f removed the server limit; pre-existing, not changed).
  Logs bench-runs/real-wave4{,-final}-{suite,tsc,vitest}.log.
- Neil's rulings of 2026-10-09 (Andrews sign, late-posted card charges) not implemented by wave 4: in r5-andrews-cards.
- Wave 5 planned: r5-any-layout, r5-andrews-cards, t-visual-v15. STATUS-FOR-NEIL.md rewritten.

### 2026-10-11 15:30 — integrate-4 continued: investigator-feedback branches merged, deployed head measured
- Neil's integrate.md addition (2026-10-09 evening, read late in the session): fin/alex-1009 must be in fin/release-1
  before measuring; r5-alex-feedback (finished, notes say so; no real benchmark had been run on it) merged. Merged
  02c1e7cb (alex-1009) and 6e9bc80a (r5-alex-feedback): clean privacy scan, only conflict the unit's WIP-NOTES.md
  (dropped; notes already archived). alex-1009 brought 4 tsc errors (three browser-test waits that had become calls on
  the previous statement, one unused parameter): fixed 14423877 as merge breakage.
- While the first measurement ran, Neil's interactive session merged fin/alex-release (alex-bulk, alex-lock, alex-rows:
  saved late-posted card dates ec6fca0b, entered-row flip on account type change 3b9babac, row withdrawal) into this
  branch (00bce7c1, a15230a0) and deployed a15230a0. That run (bench/wave4-alex) mixed code and is superseded; the head
  was re-measured from a frozen git-archive copy (bench/wave4-a152): 1,034/1,237, 0 wrong, 0 critical, 0 lost, exit 0;
  synthetic 105/125; financial 5,985 (2 known failures; 3 artefact errors that pass in the worktree); tsc 0; vitest
  unit 2,093/2,094 (route-check limit test).
- Live audit after deploy (read-only, audit-wave4-post): 811 admitted periods on truth documents, 4 disagree (current
  code reads all 4 equal), 0 printed periods admitted twice.
- Wave 5 third slot changed to t-visual-v17 (Synchrony, all 16 read empty live) from v15 (M&T; prompt kept). Wave 5:
  r5-any-layout, r5-andrews-cards, t-visual-v17. STATUS-FOR-NEIL.md rewritten.

### 2026-10-13 19:50 — REAL-DOCUMENT wave 5 merged into fin/release-1 (headless integrate-5)
- All three notes say complete with 0 wrong on real and synthetic; none refused. Private scan of the net diffs, every
  intermediate commit and every message against truth holders, words, accounts, inventory file names and non-round
  amounts: clean (only the round synthetic figure 100,000.00). Regular merges, WIP-NOTES.md dropped, notes archived
  /mnt/owl-data/fin-wt/notes/{t-visual-v17,r5-any-layout,r5-andrews-cards}.md: `fin/t-visual-v17` (65c13e2c),
  `fin/r5-any-layout` (780b31a1), `fin/r5-andrews-cards` (ef0877d6). Disjoint files, no conflicts.
- Merge breakage fixed (e3649edb): t-visual-v17 inserted its tests between the pdfplumber skip decorator and
  SyntheticCorpusTruthTests, so that class failed without pdfplumber (the service venv) and the Synchrony tests were
  skipped. Decorator moved back; module 43 OK with and without pdfplumber.
- **Real benchmark, full fresh read** (bench/wave5, frozen ef0877d6; read 3 h 23 min, 0 reading errors; import 11 h;
  REAL_EXIT=0): **1,118/1,253**, recoverable 1,118/1,249, 0 wrong, 0 critical (17,085 rows), holds 4/4, copies
  148/151, 0 lost, 84 gained; 68 valid-looking wrong values, none in a ready period; 18 unmatched items, 0 offered.
  Compare 583/827 statements (1,263 of 1,442 without disagreement; in ready periods only BBVA holder punctuation 24).
- Live ledger audit (read-only, audit-wave5): 813 admitted periods on truth documents, 5 disagree (3 earlier + 2
  hand-entered Synchrony periods with inverted directions), 0 printed periods admitted twice.
- Census not re-run (census-r5 on this wave's engine: 1,165 ready of 3,154 raw periods).
- Synthetic (bench-runs/real-wave5, BENCH_EXIT=0): 105/125, 105/108, 0 wrong.
- Suites (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): financial **Ran 6,089, failures=3** (2 known unassigned_statement
  + the test-placement failure fixed in e3649edb), skipped 21; tsc -b 0; vitest unit 300 files 2,093/2,094
  (route-check limit test, pre-existing). Logs bench-runs/real-wave5{,-suite,-tsc,-vitest}.log.
- Wave 6 planned: r6-synchrony, r6-vector-text, t-visual-v15 (prompt updated: the M&T institution profile is back).
  STATE.md and STATUS-FOR-NEIL.md rewritten.

### 2026-10-15 12:00 — REAL-DOCUMENT wave 6 merged into fin/release-1 (headless integrate-6)
- All three notes say complete with 0 wrong on real and synthetic; none refused. Private scan of the net diffs, every
  intermediate commit and every message against truth holders, words, accounts, inventory file names and non-round
  amounts: clean (0 hits). Regular merges, WIP-NOTES.md dropped, notes archived
  /mnt/owl-data/fin-wt/notes/{t-visual-v15,r6-synchrony,r6-vector-text}.md: `fin/t-visual-v15` (9a9a9fcb),
  `fin/r6-synchrony` (b64a75ee), `fin/r6-vector-text` (f234fa56). No conflicts, no merge breakage.
- **Real benchmark, full fresh read** (bench/wave6, frozen f234fa56; read 4 h 10 min at v18, 0 reading errors; REAL_EXIT=0):
  **1,146/1,294** (1,146/1,253 on wave 5's documents), recoverable 1,146/1,290, 0 wrong, holds 4/4, copies 148/151,
  0 lost, 28 gained; 6 valid-looking wrong values, none in a ready period; 16 unmatched items, 0 offered. The group import
  hit the harness turn limit (2,711 turns, 105 ready items pending); finished on a copy of the run database
  (bench/wave6-cont, harness advance_batch + verify_ledger): every ready period imported, 0 critical errors in 17,940 rows.
  Compare 623/827 statements (1,290 of 1,481 without disagreement; in ready periods only BBVA holder punctuation 26).
- **AUTO_SAVE_READY finding**: the first run (product default, auto-save ON) scored synthetic 0/125 "ready" because System
  had already saved 106 periods, and it saved the exact copy generic-01-copy-of-clean.pdf#1 (copies 0/1, 5 duplicate
  rows). All figures are measured with FINANCIAL_AUTO_SAVE_READY=0; r7-autosave fixes the copy and the harness.
- Live ledger audit (read-only, audit-wave6): 568 admitted periods on truth documents, 5 disagree (same as wave 5), 0
  printed periods admitted twice, 0 live periods on M&T documents.
- Census not re-run (census-r5: 1,165 ready of 3,154 raw periods).
- Synthetic (bench-runs/real-wave6, auto-save off, BENCH_EXIT=0): 105/125, 105/108, 0 wrong, copies 1/1.
- Suites (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): financial Ran 6,234: CLAUDE.md command failures=63 errors=60
  (auto-save ON in unittest: tests/conftest.py is pytest-only); with FINANCIAL_AUTO_SAVE_READY=0 failures=10 (2 known
  unassigned_statement + 8 test_financial_exports for interactive modules). Evidence engine vector glyph 24 passed.
  tsc -b 0; vitest unit 303 files 2,117/2,119 (route-check limit; FinancialPage load timeout, 39/39 alone).
  Logs bench-runs/real-wave6{,-autosave-on}/ and real-wave6{,-suite,-suite-noautosave,-tsc,-vitest}.log.
- Wave 7 planned: r7-autosave, t-visual-v16, plus Neil's directive units r7-import-ops and r7-alex-queue (prompts his);
  r7-mt-engine ready for wave 8. A merge of the live branch into fin/release-1 conflicted in three engine files and was
  aborted (not permitted to resolve here). STATE.md and STATUS-FOR-NEIL.md rewritten.

### 2026-10-16 15:40 — REAL-DOCUMENT wave 7 merged into fin/release-1 (headless integrate-7)
- All four notes say complete with 0 wrong on real and synthetic; none refused. Private scan of the net diffs, every
  intermediate commit and every message against truth holders, words, accounts, inventory file names and non-round
  amounts: clean (0 hits); r7-alex-queue's pre-rewrite history is unreachable. Regular merges, WIP-NOTES.md dropped,
  notes archived /mnt/owl-data/fin-wt/notes/{t-visual-v16,r7-autosave,r7-import-ops,r7-alex-queue}.md:
  `fin/t-visual-v16` (acb4873d), `fin/r7-autosave` (4124f12a), `fin/r7-import-ops` (f0bf00f4), `fin/r7-alex-queue`
  (3a043d56).
- Conflicts (r7-import-ops over r7-autosave): services/financial/__init__.py keeps both export blocks;
  import_batches.advance_batch keeps the shared-preparation branches and records the reader stamp on both paths that mark
  a file checked (own preparation and adoption). 209 targeted tests OK. Merge breakage 0c112612: unread_pages (new in
  r7-alex-queue, masked there by the 8 export failures r7-autosave fixed) exported; 14 OK.
- **Real benchmark, full fresh read** (bench/wave7, frozen 0c112612; read 3 h 07 min at v19, 0 reading errors;
  preparation + import 5 h 35 min; product default auto-save ON; REAL_EXIT=0): **1,147/1,343** (1,147/1,294 on wave 6's
  documents), recoverable 1,147/1,339, all 1,147 saved by the system, 0 wrong, 0 copies saved, 0 duplicate
  contributions, holds 4/4, copies 148/153, 0 lost, 1 gained; 5 valid-looking wrong values, none in a ready period;
  16 unmatched items, 0 offered. Compare 668/827 statements (1,291 of 1,532 without disagreement; in ready periods only
  BBVA holder punctuation 26). 35 held periods were scored while their readiness refresh was still pending (none held by
  that alone): handed to r8-import-ops.
- Generic-only (bench/wave7-generic-only, same readings): 749/1,343, 0 wrong.
- Live ledger audit (read-only, audit-wave7): 826 admitted periods on truth documents, 5 disagree (same as waves 5-6),
  0 printed periods admitted twice.
- Census not re-run (census-r5: 1,165 ready of 3,154 raw periods).
- Synthetic (bench-runs/real-wave7, product default, BENCH_EXIT=0): 105/125, 105/108, 0 wrong, copies 1/1, all saved by
  the system. The first run (beside the suite and vitest, load ~13) read 104/125: bisected over every merge commit on the
  same readings (all 104), engine code identical to r7-alex-queue's; the loaded engine reading lacked one
  tesseract_native_statement_cell_consensus refinement, whose six crop reads run under a 5 s / 60 s wall-clock budget.
  Fails closed; recorded in STATE.md as a finding.
- Suites (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): financial Ran 6,348, failures=2 (known unassigned_statement),
  errors=6 (extraction_release subprocess timeout under load; 4/4 alone), skipped 20; tsc -b 0; vitest unit 304 files
  2,121/2,122 (route-check limit test). Logs bench-runs/real-wave7{,-loaded,-rerun}/ and real-wave7{,-suite,-tsc,-vitest}.log.
- Live branch: 30 commits not on fin/release-1, a read-only trial merge conflicts in 13 files (integrate-6: 3). Not merged.
- Wave 8 planned: r8-import-ops (mandatory continuation), r8-mt-engine, t-visual-v05. STATE.md and STATUS-FOR-NEIL.md
  rewritten.

### 2026-10-17 13:40 — REAL-DOCUMENT wave 8 merged into fin/release-1 (headless integrate-8)
- All three notes say complete with 0 wrong on real and synthetic; none refused. Private scan of the net diffs, all 33
  intermediate commits and every message against truth holders, words, accounts, inventory file names and non-round
  amounts: clean (0 hits). Regular merges, WIP-NOTES.md dropped, notes archived
  /mnt/owl-data/fin-wt/notes/{r8-import-ops,r8-mt-engine,t-visual-v05}.md: `fin/r8-import-ops` (6972fbc6),
  `fin/r8-mt-engine` (e5396bee), `fin/t-visual-v05` (3648e776).
- Conflicts (r8-mt-engine over r8-import-ops' carried live engine rules) in statement_engine.py (4 hunks),
  statement_engine_profiles.py and the engine test file, each resolved keeping both behaviours (accrual ranges + day-month
  order; appendix + mailed-statement segments, mailed flag read with .get; file-numbering drop after ordered page facts;
  holder heading before the stricter institution rule; profile tie-break: furniture when it names exactly one profile,
  else the must-all specificity rule). 187 engine/exports/recovery/cache tests OK; no separate breakage fix.
- **Real benchmark, full fresh read** (bench/wave8, frozen 3648e776; read 4 h 10 min at v20, 0 reading errors;
  preparation + import 6 h 50 min; product default; REAL_EXIT=0): **1,252/1,397** (1,236/1,343 on wave 7's documents),
  recoverable 1,252/1,393, 1,250 saved by the system, 0 wrong, 0 copies saved, 0 duplicate contributions, holds 4/4,
  copies 159/165, 0 lost against wave 7, 105 gained; 4 valid-looking wrong values, none in a ready period; 16 unmatched
  items, 0 offered; 0 periods scored while a readiness refresh was pending. Compare 703/827 statements (1,393 of 1,598
  without disagreement; in ready periods BBVA holder punctuation 26 and 5 holders supplied by the detail proposal).
- Against t-visual-v05's blind run (pre-wave-8 code, v19): 18 Santander v05 periods lost to an unread closing balance.
  A/B on truth-mini-v05: merged code + v19 readings 28/54; pre-wave-8 code + v20 readings 12/54. Cause: the v20 reading
  (r8-mt-engine 7c215ef1), measured by that unit on documents that did not include v05. Kept; wave 9.
- Generic-only (bench/wave8-generic-only, same readings): 868/1,397, **2 wrong** (Citi d9b89251845be#5, #9: printed
  posting date missing on 7 rows; the engine emits no posting date). Product unaffected (Citi library reader admitted with
  posting dates). Wave 9.
- Live ledger audit (read-only, audit-wave8): 842 admitted periods on truth documents, 5 disagree (same as waves 5-7),
  0 printed periods admitted twice.
- Census not re-run (census-r5: 1,165 ready of 3,154 raw periods).
- Synthetic (bench-runs/real-wave8, product default, BENCH_EXIT=0): 105/125, 105/108, 0 wrong, copies 1/1, all saved by
  the system.
- Suites (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): financial Ran 6,435, failures=2 (known unassigned_statement),
  errors=0, skipped 20; tsc -b 0; vitest unit 304 files 2,127/2,129 (route-check limit test; FinancialPage under load,
  39/39 alone). Logs bench-runs/real-wave8{,-suite,-tsc,-vitest,-vitest-fp}.log.
- Wave 9 planned: r9-import-ops (mandatory continuation + step removal), r9-engine-santander, t-visual-v06. STATE.md and
  STATUS-FOR-NEIL.md rewritten.

### 2026-10-18 16:40 — REAL-DOCUMENT wave 9 merged into fin/release-1 (headless integrate-9)
- All three notes say complete; none admits a wrong period on real or synthetic data, none commits real data. Private
  scan of each branch's net diff and every message: 0 hits except one code comment in r9-engine-santander (49ac4c82)
  quoting a real statement amount, so that branch is SQUASHED (581ee837) with the figure replaced by an invented one;
  r9-import-ops (992c3cde) and t-visual-v06 (0883184a, notes only) are regular merges. Merged head scan: 0 hits.
  WIP-NOTES.md dropped; notes archived /mnt/owl-data/fin-wt/notes/{r9-import-ops,r9-engine-santander,t-visual-v06}.md.
- No conflicts over the reunion base e646121c. Targeted at merge: 272 (sweep save, import timing, queue save, import
  batches, copy model, review queue, row versions, finalization, harness, exports, reader release) OK; 208 (engine,
  currency, exports, recovery) OK; 67 evidence-engine reading tests passed.
- **Real benchmark, full fresh read** (bench/wave9, frozen 0883184a; read 4 h 13 min at v21, load 3-7; whole run 11 h
  07 min; product default): **1,315/1,436** (1,290/1,397 on wave 8's documents), recoverable 1,315/1,431, all saved by
  the system (1 by the sweep), 0 wrong, 0 critical (20,306 rows), 0 duplicate contributions, holds 5/5, copies held
  164/171, 0 lost, 63 gained; **REAL_EXIT=1: 1 copy saved** (dcfc8ce1f2afc#1, values equal to truth, original held
  unpaired). The unit's proposal to score such a copy as safe was not taken. Compare 728/827 (1,468 of 1,643 without
  disagreement; in ready periods BBVA holder punctuation 26, 6 holders from the detail proposal, the 1 copy).
- Generic-only (bench/wave9-generic-only, same readings, run in parallel): 896/1,436, 0 wrong (was 2), same copy saved.
- t-visual-v06's 25 new documents: 12/38 blind on cf932651 -> 25/38 on the merged code.
- Live ledger audit (read-only, audit-wave9): 874 admitted periods on truth documents, 5 disagree (same as waves 5-8),
  0 printed periods admitted twice.
- Census not re-run (census-r5: 1,165 ready of 3,154 raw periods).
- Synthetic (bench-runs/real-wave9, product default, BENCH_EXIT=0): 108/125, 105/108, 0 wrong, copies 1/1, all saved by
  the system (3 by the sweep).
- Suites (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): financial Ran 6,466, failures=2 (known unassigned_statement),
  errors=0, skipped 20; tsc -b 0; vitest unit 304 files 2,130/2,130. Logs bench-runs/real-wave9{,-suite,-tsc,-vitest}.log.
  A chown of 15 root-owned cache entries in the live node_modules (from 2026-10-17, not this session) was refused by
  the sandbox: left for Neil.
- Wave 10 planned: r10-copies, r10-engine-residue, t-visual-v01. STATE.md and STATUS-FOR-NEIL.md rewritten.

### 2026-10-19 21:10 — REAL-DOCUMENT wave 10 merged into fin/release-1 (headless integrate-10)
- All three notes say complete; none admits a wrong period on real or synthetic data in its own runs; none commits real
  data. Private scan of each branch's net diff and every message, and of the merged head against 060d7470: 0 hits (test
  fixtures use invented names). Regular merges onto 060d7470: `fin/r10-copies` (335820ab), `fin/r10-engine-residue`
  (a9938dc9; conflict in test_financial_statement_engine.py where fin/layer-guard's LayerGuardTests and the unit's tests
  were both appended at the end; both kept; 230 engine/page-identity/exports tests OK), `fin/t-visual-v01` (a9e6c1ab,
  notes only). WIP-NOTES.md dropped; notes archived /mnt/owl-data/fin-wt/notes/{r10-copies,r10-engine-residue,
  t-visual-v01}.md. No separate breakage fix.
- **Real benchmark** (bench/wave10, frozen a9e6c1ab, readings of bench/rel1-060d7470 reused: no evidence-engine file
  changed, reading v22 in both, truth unchanged since that read; product default; 8 h 06 min niced): **1,351/1,462**
  (1,332/1,436 on wave 9's documents), recoverable 1,351/1,457, all saved by the system, 0 wrong, 0 critical (21,356
  rows), 0 duplicate contributions, holds 5/5, copies held 168/171, 0 lost against 060d7470, 18 gained; REAL_EXIT=1 for
  the same saved copy dcfc8ce1f2afc#1. Compare 754/816 (1,500 of 1,669 without disagreement; in ready periods BBVA holder
  spelling 34, 6 holders from the detail proposal, the 1 copy).
- Generic-only (bench/wave10-generic-only, same readings, in parallel): 984/1,462, **1 wrong** (d1398a6f10ccc#1: one
  row dated three days after its printed operation date). A/B on truth-mini-v01 (bench/int10-ab-v01-gen-{base,merged}):
  060d7470 and a9e6c1ab both admit it, so it predates this wave; the product holds it. Owned by wave 11 r11-bbva-vector.
- Live ledger audit (read-only, audit-wave10): 885 admitted periods on truth documents, 6 disagree (the 5 of waves 5-9 +
  d6d2d26fac5f4#1 found by t-visual-v01), audit's own double-admission count 0; r10-copies' read-only census found one
  printed period admitted twice across two ledger accounts (case d5b330d1) that the detector and audit both miss:
  wave 11 r11-copy-audit; the live fix is Neil's.
- Census not re-run (census-r5: 1,165 ready of 3,154 raw periods).
- Synthetic (bench-runs/real-wave10, product default): 108/125, 105/108, 0 wrong, copies 1/1, no safety failure.
- Suites (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): financial Ran 6,503, failures=2 (known unassigned_statement),
  errors=1 (checkpoint_b_gate under load, AttributeError on a None batch item; 12/12 alone x3; also seen on
  r10-engine-residue's branch), skipped 20; tsc -b 0; vitest unit 304 files 2,130/2,130 (as the app user). Live
  node_modules: 0 root-owned entries now. Logs bench-runs/real-wave10{,-suite,-tsc,-vitest}.log.
- Wave 11 planned: r11-bbva-vector, r11-copy-audit, t-visual-v04. STATE.md and STATUS-FOR-NEIL.md rewritten.

### 2026-10-20 19:00 — REAL-DOCUMENT wave 11 merged into fin/release-1 (headless integrate-11)
- All three notes say complete; none admits a wrong period on real or synthetic data; none commits real data except one
  figure equal to a real statement amount in r11-bbva-vector (an evidence-engine test, a code comment, one commit
  message), so that branch is SQUASHED (24593077) with an invented figure; test_vector_glyph_reading 47 passed after the
  edit. r11-copy-audit (15c1e89c) and t-visual-v04 (e3d1fed7, notes only) are regular merges; no conflicts, no breakage
  fix. Private scan of each branch and of the merged head against cdb9e2b9: 0 hits after the squash. WIP-NOTES.md
  dropped; notes archived /mnt/owl-data/fin-wt/notes/{r11-bbva-vector,r11-copy-audit,t-visual-v04}.md.
- **Real benchmark** (bench/wave11, frozen e3d1fed7, readings tmp/int11/readings-w11.json: r11-bbva-vector's v23
  readings of the 754 documents + a fresh read of the 24 v04 documents by the frozen code; v23 changes only
  vector-outline reading; product default; 7 h 48 min niced): **1,388/1,506** (1,356/1,462 on wave 10's documents),
  recoverable 1,388/1,501, all saved by the system, 0 wrong, 0 critical (21,930 rows), 0 duplicate contributions, holds
  5/5, copies held 168/171, 0 lost against bench/wave10-v04, 37 gained (kapital 29 + intercam 3 on the new documents,
  bbva 5); REAL_EXIT=1 for the same saved copy dcfc8ce1f2afc#1. Valid-looking wrong values 4 (all held). Compare 778/816
  (1,532 of 1,713 without disagreement). In ready periods: BBVA holder spelling 34, **Kapital wrong holder 5** (an address
  line; library reader), 6 holders from the detail proposal, the 1 copy.
- Generic-only (bench/wave11-generic-only, same readings, in parallel): 1,023/1,506, **0 wrong** (d1398a6f10ccc#1 held),
  0 critical; 991/1,462 on wave 10's documents.
- Live ledger audit (read-only, audit-wave11): 1,129 admitted periods on truth documents (live files now also matched by
  bytes), 6 disagree (same ids as wave 10), same printed period admitted twice **1** (the split-account pair in case
  d5b330d1, now found by the audit).
- Census not re-run (census-r5: 1,165 ready of 3,154 raw periods).
- Synthetic (bench-runs/real-wave11, product default): 108/125, 105/108, 0 wrong, copies 1/1, no safety failure.
- Suites (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): financial Ran 6,533, failures=2 (known unassigned_statement),
  errors=0, skipped 20; tsc -b 0; vitest unit 304 files 2,130/2,130 (as the app user); live node_modules 0 root-owned
  entries. Logs bench-runs/real-wave11{,-suite,-tsc,-vitest}.log.
- Wave 12 planned: r12-kapital, t-visual-v02, t-visual-v03. STATE.md and STATUS-FOR-NEIL.md rewritten.

### 2026-10-21 08:00 — REAL-DOCUMENT wave 12 merged into fin/release-1 (headless integrate-12)
- All three notes say complete; none admits a wrong period on real or synthetic data; none commits real data except one
  figure equal to a real statement amount in r12-kapital (an engine docstring and an engine test), so that branch is
  SQUASHED (2a6df8be) with an invented figure; engine, Kapital reader and harness tests 263 OK after the edit.
  t-visual-v02 (f1ebc56d) and t-visual-v03 (c835bdc8) are regular merges of notes only; no conflicts, no breakage fix.
  Private scan of each branch and of the merged head against d53e0915: 0 hits after the squash (8 hits on a common
  Spanish word inside an invented test name). WIP-NOTES.md dropped; notes archived
  /mnt/owl-data/fin-wt/notes/{r12-kapital,t-visual-v02,t-visual-v03}.md.
- **Real benchmark** (bench/wave12: copy of r12-kapital's bench/r12k-whole, frozen 6d1d021d, readings
  tmp/r12k/readings-v24b.json, rescored by frozen c835bdc8 against the unchanged truth manifest; compare/ rewritten, backup
  compare-backup-pre-w12): **1,404/1,524**, recoverable 1,404/1,519, all saved by the system, 0 wrong, 0 critical (22,419
  rows), holds 5/5, copies held 168/171, saved holder differs 0 (same entity 36), 0 lost against bench/wave11-v02, 16
  gained (kapital 7, intercam 1, bbva 8 on the v02 documents); REAL_EXIT=1 for the same saved copy dcfc8ce1f2afc#1. The
  rescore reproduces every headline count of the run; Andrews actions differ (re-pairing artefact), so actions are
  quoted from the run. Compare 796/815 (1,551 of 1,731 without disagreement).
- Generic-only (bench/wave12-generic-only, same method): 1,037/1,524, **0 wrong**, 0 critical.
- Live ledger audit (read-only, audit-wave12): 1,137 admitted periods on truth documents, 6 disagree (same ids), same
  printed period admitted twice 1 (the d5b330d1 split-account pair); holders: 986 agree, 42 same entity, 3 differ (the
  Kapital address-line holder, live code).
- Census not re-run (census-r5: 1,165 ready of 3,154 raw periods).
- Synthetic (bench-runs/real-wave12, frozen c835bdc8, product default): 108/125, 105/108, 0 wrong, copies 1/1, no safety
  failure; 1 saved synthetic holder differs (100 dpi OCR letter; pre-existing).
- Suites (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): financial Ran 6,550, failures=2 (known unassigned_statement),
  errors=0, skipped 20; tsc -b 0 (as the app user); vitest unit NOT run (the permission layer refused it twice; no
  frontend change since wave 11). Logs bench-runs/real-wave12{,-suite,-tsc}.log.
- Wave 13 planned: t-visual-v19, r13-andrews, r13-merrick. STATE.md and STATUS-FOR-NEIL.md rewritten.

### 2026-10-22 04:40 — REAL-DOCUMENT wave 13 merged into fin/release-1 (headless integrate-13)
- All three notes say complete; none admits a wrong period on real or synthetic data; none commits real data (private
  scan of each branch and of the merged head against 48e58b67: 0 hits). Regular merges t-visual-v19 (f58d6dbf; truth
  and audit tooling, no processor code), r13-andrews (ab5c16ef), r13-merrick (3e8e7f06); no conflicts, no breakage fix.
  WIP-NOTES.md dropped; notes archived /mnt/owl-data/fin-wt/notes/{t-visual-v19,r13-andrews,r13-merrick}.md.
- **Real benchmark** (bench/wave13: fresh whole-set run, frozen 3e8e7f06, readings tmp/int13/readings-w13.json =
  r13-andrews's readings + t-visual-v19's Navy Federal read; product default; 9 h 35 min niced): **1,645/1,729**,
  recoverable 1,645/1,724 (95.4%), all saved by the system, 0 wrong, 0 critical (25,489 rows), holds 5/5, copies held
  168/171, saved holder differs 0 (same entity 36), 0 lost against bench/wave12-v19, 241 gained (navy-federal 205,
  andrews 24, merrick 12); REAL_EXIT=1 for the same saved copy dcfc8ce1f2afc#1. Valid-looking wrong values 3 (the fourth
  was a truth error, corrected). 3 ready Andrews closed sections saved without a closing balance (reported; r14-santander
  item 1). Compare 797/815 (1,789 of 1,950 without disagreement); the 18 never compared are the all-unverified
  documents, which real_truth leaves out of the manifest.
- Generic-only (bench/wave13-generic-only, same readings): 1,242/1,729, **0 wrong**, 0 critical; 0 lost.
- Live ledger audit (read-only, audit-wave13): identical to audit-v19: 1,340 admitted periods on truth documents, 914
  agree, 6 disagree (same ids), 1 printed period admitted twice, 3 Kapital holders differ.
- Census not re-run (census-r5: 1,165 ready of 3,154 raw periods).
- Synthetic (bench-runs/real-wave13, frozen 3e8e7f06): 108/125, 105/108, 0 wrong, copies 1/1, no safety failure.
- Suites (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): financial Ran 6,597, failures=3, errors=2, skipped 20 under the
  load of both benches; the 2 errors (extraction_release subprocess timeouts) and the page-identity failure pass on a
  rerun of their modules (19 OK); the 2 known unassigned_statement failures remain. tsc -b 0 and vitest unit 304 files
  2,130/2,130 (as the app user). Logs bench-runs/real-wave13{,-suite,-suite-rerun,-tsc,-vitest}.log.
- Wave 14 planned: t-visual-v11, t-visual-v12, r14-santander. STATE.md and STATUS-FOR-NEIL.md rewritten.
