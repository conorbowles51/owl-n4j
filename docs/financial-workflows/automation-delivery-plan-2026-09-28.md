# Statement automation delivery plan — 28 September 2026

## Required outcome

The user and Alex require time-saving automation, not a faster manual correction screen. A successful investigator journey is: select sources once → background reading and bounded automatic repair → clear summary of ready statements, retained duplicates and genuine exceptions → confirm the eligible group once → durable progress and receipt → investigate payments with original-source links. Opening or correcting every statement is a failed acceptance result.

This is the current delivery priority. Stop the repeated individual-import audit loop. Preserve the existing Final Test work and resume the investigation after the automated journey passes. The earlier queued large-batch reliability work is now a prerequisite for this journey, not a reason to postpone its repair. No active team ingestion may be interrupted. Code publication, deployment and live acceptance remain separate.

## Findings from the implementation dive

| Finding | Evidence | Consequence / certainty |
|---|---|---|
| Individual progress and batch drafts diverge | `statement_progress.save_progress` saves EvidenceFile metadata; `import_batches` separately uses Item.review_request and Item.summary; `statement_file_status` uses prepared summary.can_import | **Reproduced with actual services and disposable synthetic DB:** missing-holder batch blocked; standalone correction passes admission; reopened batch still has blank holder and can_import=false. Not proof that this is the sole live zero-ready cause. |
| The automatic quality-triggered reread has limited layout coverage | `statement_reading_quality.assess_statement_reading` handles Credit One and Andrews; otherwise returns None. `pdf_extraction` schedules a native-image alternative only if quality reports unreadable fields | Merrick has a parser but does not receive this particular repair path. Other layout-specific OCR helpers exist; do not claim all fallback is absent. |
| “Readable” is narrower than “correct” | Quality assessment counts missing fields; `prefer_image_reading` requires identical identity, physical row counts and balance counts | Syntactically valid wrong dates/amounts, omitted rows and failed identity extraction need separate detection/recovery. Matching arithmetic alone cannot establish correctness. |
| Recognized closing date is not a complete automation path | Merrick identity records statement_date but initializes both period bounds empty; E25 allows explicitly confirmed unprinted start | Current manual confirmation is repeated per period. Add source-derived date provenance and scoped group handling, without inventing starts or claiming full-month coverage. Preserve statement IDs. |
| Retry is not an automatic repair coordinator | `reading_recovery.inspect_completed_reading` can detect missing readings/zero extracted rows despite activity; otherwise returns review_required | There is no general bounded statement-level repair ladder covering unresolved fields and control discrepancies before escalating to the investigator. |
| Single and bulk import have different recovery contracts | Standalone StatementImportPanel sends synchronous /confirm with 120-second timeout and shows error; batch import_operations has immutable submitted scope and durable outcomes | Use durable operations for both. The browser should recover outcomes after lost responses itself. No blind replay of writes. |
| Large reads can do substantial evaluation work | `checked_batch_items` calls comparison_sources and may reconstruct proposals; file status and batch summary use different projections | Profile representative cases before choosing optimizations; snapshot/assessment reuse needs explicit freshness rules. Existing code alone does not prove the observed fetch-failure cause. |
| Live response failures remain unexplained | Several GETs and individual confirms returned Failed to fetch; some subsequent requests succeeded; captured browser logs were empty | Investigate client, proxy and backend with correlation/timing. Do not label this a login problem, assume timeout, increase timeouts as the fix, or restart services speculatively. |
| Tests overrepresent recovery by human editing | Existing suites include synthetic parsers, actual-service persistence, selected browser journeys; some substitute auth/PDF rendering | Add fresh-upload, real reader/worker, held-out source, scale and human-effort acceptance. Passing these existing suites is not proof of useful automation. |

The synthetic reproduction was run on 28 September against the current local code using the existing BatchImportTests fixture and actual save_progress/assess_admission/batch_status services. Results: before can_import=false, corrected standalone can_import=true, reopened batch can_import=false. No client source or live records were involved. A preliminary save-to-batch patch was withdrawn before testing/publication: synchronizing future saves alone would not repair existing drafts, resolve conflicts or prove the complete journey.

## Product contract

- Selecting Financial starts reading/preparation, not ledger admission. Automate routine preparation and repair; retain one explicit group import confirmation.
- Every source section has a stable identity independent of a corrected amount, name or date. Preserve source hash, version, page/section, reader version, candidate values and investigator revision.
- One effective review feeds the individual screen, file count, batch list, batch detail and final admission. Competing investigator edits become an explicit conflict; newest timestamp alone never wins.
- States distinguish queued, reading, automatically checking/repairing, ready, needs a decision, duplicate retained, importing, saved and failed. “Read successfully” does not mean ready or complete.
- The exception queue contains current unresolved decisions. Historical extraction warnings remain accessible as history and do not masquerade as new tasks.
- Unknown is a valid recorded fact where supported. No invented dates, zero balances or transaction values. No calculated digit substitutions to force reconciliation.
- Shared remedies have a preview of affected periods, evidence basis and exclusions. A bank/account/currency decision must not spill into a different source section. Per-period dates and balances remain distinct.
- Reading repair never silently overwrites investigator edits or existing admitted payments. Existing-data reconciliation is a previewed, version-checked upgrade of unimported work; previously saved records remain linked and stable.

## Delivery sequence and concrete work

### 1. Establish a reproducible baseline and durable diagnostics

Build a repeatable benchmark harness around actual PDF extraction, catalog, proposal, admission, batch preparation and import services. Record original bytes/hash, expected periods/rows/controls, parser versions, automatic attempts, readiness reasons, edits/clicks, worker time and elapsed wall time. Private originals and ground truth stay ignored; commit only synthetic fixtures and harness code. Run current code before any repair to expose the baseline.

Add request/operation correlation through frontend API client, proxy/backend and worker. Measure queue wait, reading, reconciliation, lock wait, response time and render time separately. Record sanitized identifiers/status/timing, never credentials or full financial payloads. Reproduce lost request, lost acknowledgement and failed polling separately. Inspect supported ordinary service diagnostics without changing live service state.

Deliverable: baseline report and classified failure evidence; no guessed cause for Failed to fetch.

### 2. Make saved work and readiness consistent, including existing drafts

Change `statement_progress.py`, `import_batches.py`, `statement_file_status.py` and shared review resolution, with versioned fingerprints rather than independent readiness rules.

- Resolve the effective request from original proposal, standalone draft and batch draft. Reuse exact shared revision; safely adopt a standalone draft when batch work is untouched. Distinct edited values require comparison.
- Propagate a save to matching pending batch reviews or invalidate their assessment through a durable revision mechanism. Preserve skipped/ignored/removed/pending-import/imported dispositions.
- Reassess only changed periods in a worker, outside long case locks. Store assessment with source/reader/review/policy and relevant duplicate-scope revisions. GET counts do not reconstruct whole PDFs or write state.
- Provide one resumable “Update readiness from saved reviews” operation for existing unimported work. Preview scope and conflicts; no OCR restart, repeat import or requirement to open each period. Reuse existing jobs where possible.
- Final queue admission rechecks current revisions and duplicate protection. A ready summary is never authority to bypass admission.
- Ensure save/reopen/file-list/group-summary counts and navigation agree. Query invalidation must refresh all affected views and label stale results.

Gate: synthetic reproduction now yields ready in all views; multiple independent batch edits remain intact; existing-data upgrade is repeatable; one group confirmation imports the exact eligible set once. Test simultaneous saves/queue acceptance in PostgreSQL with existing audit triggers, not only SQLite.

### 3. Automate source repair before requesting human work

Extend the existing shared quality assessment and extraction hooks, starting with Merrick and the highest-frequency observed defects, then every registered layout in the benchmark. Avoid a separate one-off parser for Final Test or filename-based rules.

Repair ladder, bounded by attempt count, region/page budget and wall time:

1. Parse native text and geometry with the recognized layout; classify headers, transactions, totals, interest illustrations and supporting pages.
2. Check identity, page continuity, dates, row completeness, printed credit/debit/fee/interest controls, running balances and endpoint balances.
3. For a specific failed field/region, reread original image crops at suitable resolutions; retain all candidate observations and locations. Try a full page only when segmentation/omitted rows demand it.
4. Resolve candidates only when supported by source evidence, identity/section continuity and independent controls. An equation may detect a problem but may not manufacture its solution. Repeated OCR agreement from one engine is supporting evidence, not independent proof.
5. When the evidence is still ambiguous, escalate that exact issue with original crop, attempted readings and the reason it could not be resolved.

Handle valid-but-wrong values and missing rows explicitly. A recovered extra row needs source-location/coverage verification and all controls; do not simply relax the equal-row-count safeguard. Damaged identity needs a separate identity-recovery phase rather than guessing an account from adjacent statements. Any model-assisted reader must be evaluated against the same ground truth and provenance rules; confident prose is not a transaction value.

Date handling: recognize printed closing-only layouts and retain explicit source-derived provenance (not a fabricated reviewer checkbox). Group confirmation is the fallback when absence cannot be established automatically. Missing OCR is not equivalent to unprinted. Preserve historic statement keys and draft compatibility when reader metadata improves.

Gate: baseline defects resolve from source bytes without per-row human transcription; unsupported/ambiguous cases remain exceptions; hold-out documents improve without silent regressions or case-specific rules.

### 4. Make the investigator work on exceptions and shared decisions

Change StatementFilesPanel, FinancialBatchPanel, batch reason summaries, bulk statement details and StatementImportPanel as one journey.

- Main summary: statements ready, auto-repair in progress, duplicates retained, decisions required, saved. Clear distinction between files, periods and transactions.
- Eligible statements are selected as a group without opening their PDFs. Present count/amounts by account and currency, source coverage limitations and excluded exceptions before confirmation.
- Group recurring exceptions by cause and safe scope. Preview and apply one shared resolution across matching statements; show which periods are excluded and why. Never apply one balance or date to all months.
- A single exception opens its source crop and current candidate values immediately. Saving returns to the same filtered queue and updates counts; no lost position or repeated review.
- Supporting pages can retain a source-bound disposition; card migration/internal repeated sections remain explicit source/transaction duplicate decisions. Reuse E26/E27 work rather than hiding these as generic warnings.
- Original warning history stays collapsed; resolved original warnings do not make reconciled statements look unfinished.

Gate: clean collection needs zero statement openings; one repeated known metadata problem needs one scoped decision, not N statement edits; genuine missing-page and conflicting-value cases require only their actual decisions. Verify desktop and narrow layouts, source copy/open and return.

### 5. Unify durable import and connection recovery; make scale a release gate

Reuse `import_operations.py`/batch worker receipts for a single statement as well as a group. Persist a client request identity and immutable submitted scope before execution; acknowledge promptly, run in worker, expose status and per-period outcomes. On uncertain response, look up the same operation before offering any resubmission. Retry a known failed item, not the successful population. Editing the scope requires a new reviewed request.

Keep last confirmed progress visible during failed reads with explicit staleness. Refresh read-only status with bounded backoff. Reopening another tab/device reconstructs the operation from server state. Validate graph/index follow-up separately from ledger completion.

Serve paginated materialized summaries first; evaluate changed statements asynchronously with bounded concurrency and fair scheduling across cases. Profile source parsing, duplicate comparisons, SQL/audit locks and browser rendering; fix the measured bottlenecks. Do not trade performance for stale admission decisions.

Gate: lost acknowledgement, refresh, browser close/reopen, worker restart in isolation and concurrent cases all finish with the same intended ledger set, retained edits and usable navigation. No live worker interruption for these tests.

## Test population and measurable acceptance

Freeze the benchmark manifest before optimizing; distinguish baseline, development set and held-out periods/scans. Include every currently supported family, digital and scanned sources, damaged OCR, multiple accounts/currencies, year boundaries, credit balances, true quiet periods, closures with money owed, absent dates, continuations, missing pages, exact copies, internal repeated sections and legitimate equal-valued transactions. Keep irrecoverable cases in the denominator as separately labelled exceptions, not silently dropped “unsupported” files.

Three independent tracks:

1. **Fresh upload:** no cached readings, saved corrections or prior admissions. This measures automation, not reuse of manual work.
2. **Existing work:** saved and partially imported collections, conflicts, duplicates and version changes. This measures preservation/recovery without redoing edits.
3. **Scale and interruption:** 100, 500 and 1,000 periods, at least one 200+ page collection, two concurrent cases, network interruption and isolated worker failures. Render source PDFs in the real browser and run actual worker/API/database paths. Mock-only browser suites are supplemental.

Initial release targets (targets, not achieved measurements):

- Clean supported benchmark: 100% eligible without opening/editing each statement; one group confirmation.
- Held-out supported recoverable population: at least 95% of periods ready without field edits. Publish both period and field accuracy plus the exact denominator; below target means more engineering, not manual rescue disguised as automation.
- Zero known incorrectly auto-admitted critical fields in the acceptance corpus: amount, direction, currency, account attribution and date. Zero duplicate ledger contributions and zero lost investigator edits. A finite test set is not a universal accuracy guarantee.
- Every intentionally ambiguous/missing-source case remains visible and correctly held; no invented start dates or false no-activity classifications.
- At least 80% reduction in measured human actions against the same baseline population, counting uploads, decisions, edits, retries and navigation. Report active human time separately from processing wait.
- Healthy-network p95: operation acknowledgement <=2s; first useful list/summary <=3s; cached statement review <=5s; refreshed saved result visible <=5s. Measure warm/cold and workload explicitly; OCR throughput target set from the initial hardware baseline, not invented now.
- Three consecutive full scenario runs with identical expected counts/totals/provenance and successful recovery, followed by guarded live acceptance. Failures and manual interventions appear in the report.

Independent verification compares exact expected rows and controls, not just matching closing balances. Include negative tests where two wrong values cancel out. Verify no cross-currency totals, source links for every saved transaction, honest account/month coverage and original-file access from the final ledger. After admission, select payments → append to an existing observation without duplicating it → reopen source/observation (E28), retaining the overall investigation objective.

## Execution checkpoints

| Checkpoint | Work delivered | Must be demonstrated before moving on |
|---|---|---|
| A | Baseline harness, durable diagnostic evidence, readiness regression | Measured manual burden and reproducible failure; no production mutations |
| B | Shared review/readiness and existing-draft refresh | Save once, group-ready once, conflicting edits protected, group import/reopen |
| C | Automatic repair ladder and date provenance | Fresh sources reach readiness without copying prior manual answers; held-out accuracy |
| D | Exception-first UI plus shared decisions | Investigator completes representative mixed collection with only genuine decisions |
| E | Durable import, large-batch performance and failure recovery | Actual-browser scale/interruption matrix and independent persisted results |
| F | Guarded release and live acceptance; resume investigation | Served revision verified, existing work preserved, affected journeys pass, source/investigation gaps honestly reported |

B and a first-layout C slice form the first useful vertical delivery; E instrumentation starts at A so throughput failures are visible throughout. Do not declare the automation objective complete after B alone. Estimate calendar completion after A establishes repair success and the measured network/scale cause; provide evidence at each checkpoint rather than repeated unsupported short ETAs.

## Current status

### 28 September implementation checkpoint (local, not released)

The user resumed implementation while leaving the recurring schedule paused. The earlier withdrawn experiment remains withdrawn; the following is new connected implementation:

- A shared resolver lets untouched batch work follow the standalone draft, including existing drafts through the background statement refresh. Independent edits remain conflicts. Batch editing of an existing shared draft updates that draft and keeps its history; review tokens include the shared revision, so an older editor cannot overwrite it. Conflict-resolution presentation and all bulk-edit paths still need acceptance.
- Saved assessments feed file and batch readiness without reparsing each PDF on ordinary list refresh. Stale retained-source duplicate markers undergo coverage comparison instead of treating the source as its own duplicate. Ignored copies remain held. Group confirmation validates the displayed scope and current source before queuing; new edits invalidate an old confirmation. Standalone edits cannot change a queued statement.
- Merrick now participates in automatic quality-triggered image rereading. The crop fallback targets a damaged money cell only when the printed column geometry identifies it, retains the original reading and coordinates, and uses bounded repeated OCR agreement. The selector preserves readable payment facts, printed controls, identity and physical row counts. Complete conflicting values are not replaced to balance arithmetic. Reader cache revision advanced to `bank-payment-rows-v9`.
- Real Tesseract recovered a damaged synthetic amount from its original rendered image. The extraction-path regression deliberately loses a payment in the page-level alternative and verifies that original rows survive while the crop repair succeeds. This is source-crop/extraction-path evidence, **not full fresh-upload or held-out acceptance**.

Verification checkpoints: 221 backend tests passed before the final shared-edit token extension; the affected batch/shared-review suite then passed 95 tests, and 22 router checks passed. The 15 engine tests include real OCR. Four isolated PostgreSQL concurrency tests passed again after the final token changes, including a standalone save racing group confirmation. The old general `.venv` lacked test dependencies; use `data/local-runtime/backend-venv` and `data/local-runtime/engine-venv`. Test databases are synthetic; PostgreSQL tests use disposable schemas on loopback port 55434.

Still open: full fresh-source preparation-to-group-import browser proof, automatic date provenance, recovery of valid-but-wrong readings/omitted rows, shared exception decisions, single-import durable recovery, real scale/performance measurements, held-out accuracy and human-effort targets. Local application sign-in was checked, but it does not verify these changes: the existing local backend does not hot reload. No client import, live deployment or automation-goal completion is claimed. Do not resume manual per-period clearing or the paused schedule.

### 29 September release instruction

The user explicitly requested building and pushing the pending automation implementation without further test runs to conserve usage, then continuing development. The code-only E31/E32 release follows that instruction. The verification above predates this request; full browser, held-out and scale acceptance remain open. Push triggers the normal guarded deployment; successful publication alone does not establish deployment or live acceptance. The recurring schedule remains paused.

Release `a48958e0` was committed and pushed to `integration/evidence-main-reunion` after the requested production build passed. No additional tests ran. Deployment and live acceptance have not been checked.

Continued development extends the same effective review to grouped account-detail decisions: known predecessor drafts no longer create false conflicts, including corrected currency; grouped saves retain cached readiness and revision ancestry; superseded readings are excluded and ignored duplicates require explicit restoration. A first batch save now creates shared progress so the individual view can reuse it too. These follow-up changes have not been tested, following the user's instruction. They do not complete automatic date handling, the repair coordinator, durable single-import recovery or scale acceptance.
