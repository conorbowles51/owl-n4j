# Financial and ingestion workflow release verification

23 September 2026. This record supersedes the earlier “Planned” implementation
labels in the September 22 plan. It distinguishes completed local journeys from
live acceptance. The user has authorised committing and pushing the completed
code, and previously authorised deployment. Client evidence is excluded from Git.

Current deployment status: the user confirmed on 23 September that deployment
has happened. Deployment is complete; do not continue reporting it as pending.
The local test results below and outstanding independent live acceptance are
separate from that confirmation.

## Connected outcomes

| Investigator journey | Implemented and locally verified |
|---|---|
| Evidence → Financial → return to the original PDF | Internal reading copies with explicit same-case, same-byte lineage appear in the original file's reading history. Evidence search and pagination count the original once. Selecting a folder for Financial selects the current reading once. Independently uploaded originals stay distinct. Existing proven internal copies use this grouping immediately; no deletion or data migration is needed. |
| Upload → pause → leave/reopen → resume | Ordinary file uploads retain verified chunks and an atomic evidence-registration receipt. Reselecting the original file in a new browser session resumes missing chunks; a different file is refused. A lost completion response returns the same evidence record. |
| AI processing alongside Financial reading | Dedicated PDF queue/worker, per-request status reconciliation, independent job state and scoped subprocesses. Both start orders, failure and timeout of the other job preserve progress. Processing cards distinguish reading complete from transactions imported. |
| Processing → pause/interruption → resume | Durable page and work-unit checkpoints, exclusive run locks, active-worker heartbeat, queued/active pause and resume. A synthetic 1,928-page native PDF resumes after page 777 with every page read once. A real isolated Neo4j test interrupts after a committed chunk, reconnects and retries without duplicating entities or losing manual edits. |
| Statements → batch import → receipt → exact saved payments | Durable submission and per-statement outcomes explain queued, importing, saved, already present and failed work. Retry does not repeat completed imports. Files, batch status and individual review distinguish reading, import and outstanding checks. Incomplete records remain outside totals and retain their source. |
| Missing holder/account/dates or wrong currency → edit beside PDF → save/reopen | Direct pre/post-import controls share the saved statement writer. Changes update the account, dates, checks and current payment views. Currency correction preserves printed amounts, without FX conversion; unrelated sections remain separate. |
| Flagged statement → source → correction/review → next check | Actionable field/row destinations, saved edits, recomputed checks, retained unresolved issues and visible import receipts. A usable import can retain unresolved overlap/arithmetic checks; “imported” does not imply “reviewed.” Exact-source replay remains idempotent. |
| Multi-account/currency PDF → choose section → import/reopen | Kapital product/CLABE/currency blocks and Monex no-activity contract compartments remain separate. Small opposite postings are retained. BBVA scanned dates/headings use source-bound OCR observations; ambiguous results remain reviewable. |
| Account/payment → review common ownership → profiles/shared filters | Typed holder, controller, signatory and analysis-group links; source/page or investigator-knowledge basis; effective dates; joint holders; history and stale-edit refusal. Only reviewed holder links establish common ownership. Header identifier suggestions are reviewable and exclude bank-footer identifiers. |
| Select transfer entries → review both sources → save → follow receiving account | Persistent equal-value transfer pairs, one-sided referenced accounts and explicit FX hypotheses. Both actual statement entries remain. A separately reasoned partial/one-to-many onward allocation checks capacity across saved trails and shows opening-balance/imported-sequence context and uncertainty. Corrected sources mark earlier interpretations for review. |
| Company analysis → Follow money → Finding/Observation → Timeline | Shared reviewed holders drive filters and profiles. External-activity filtering excludes only current, reviewed internal pairs within the selected account scope. Internal movement is counted once, currencies kept separate. Follow money displays saved bank-to-bank links and supplier allocations. A transfer adds one Timeline event retaining both sources; the supplier payment remains a separate event. Earlier Timeline snapshots remain inspectable. |
| Release while colleagues work | Deployment defers when engine jobs or accepted Financial imports are active, or when state cannot be read. New workers have a graceful completion window. Migrations precede starting workers that need the new columns. No live job was cancelled, retried or moved in this verification. |

The earlier Transactions, category/bulk editing, Boolean search, shared multi-account
selection, tab continuity, Trends comparisons, Findings/Observations and Timeline
work remains part of the regression scope. The generated action inventory now
contains 1,508 controls across 160 financial components; it is a reference, not
proof that every possible state was exercised.

## Verification evidence

- Financial/backend regression run: **5,265 passed**. Subsequent targeted checks
  after strengthening save locks and the deployment guard: **13 passed**.
- Ingestion worker, checkpoint, upload-security, PDF-reader, queue-isolation and
  real local graph interruption suite: **62 passed**. Synthetic Redis/Neo4j
  instances were isolated from the normal development and live services.
- Frontend unit run: 1,867 initially passed; three stale test expectations failed.
  The corrected panel and citation tests then passed all 22 checks in those two
  files. The expectations now cover the current shared editor and PDF page viewer.
- Final connected Chromium run: **62 passed in 27 files**, covering Financial,
  Evidence and Timeline. The category test now creates a reusable category,
  reviews a single change, bulk-reviews all selected pages and verifies reopening.
  Dependency preloading prevents the test server replacing React mid-run.
- Production TypeScript/build passes. Release migrations run successfully from
  the previous schema to `20260923_money_trails` in disposable PostgreSQL.
- Generated screenshots and all real-PDF extraction/reconciliation artifacts are
  local-only and excluded from the release manifest. Source PDFs were not uploaded
  to another service or used for live test writes.

## Acceptance boundaries and live handoff

This is shared implementation for every case and future ingestion, not a BNB2
account/file patch. Synthetic tests and supplied-file local reconciliation do not
certify every bank layout or the entire client corpus.

- Monex verification covers the supplied no-activity layout. Other Monex movement
  products need representative evidence; they remain source-reviewable.
- Historical combined imports have an explicit separation/recovery workflow. It preserves current investigator corrections, assigns every current record exactly once, previews scope changes and retains source/citation history. Existing case recovery remains a reviewed live action.
- Resumable byte transfer now includes ordinary files, multi-file Financial uploads, folders and archives. Dedicated phone-report dispatch and ingestion checkpointing are included. Atomic registration itself finishes rather than pausing halfway through its commit; leaving retains its receipt.
- The long-PDF test establishes page extraction/recovery on a generated native PDF.
  Alex's large chat still requires a complete run through the actual providers and
  live host. The observed Neo4j timeout and historical import attempt cannot be
  attributed conclusively without their live logs.
- Deployment has happened, as confirmed by the user on 23 September. Earlier
  Google Cloud authentication failures describe this agent's access at the time,
  not the current deployment state. Independent live read-only verification is
  still outstanding in this record.
- A code push is not a deployment claim. Record the deployed revision and repeat
  source/history, saved statement, shared owner/trail and processing-status journeys
  when server access is restored. Client-case cleanup/import/reprocessing is not a
  demonstration action; retain the existing no-live-client-mutations boundary.


## Completion pass after the partial release

The [completion register](completion-register.md) and [connected flow reference](recovery-and-identity-workflows.md) supersede the implementation gaps recorded in the original release subset. Added code covers:

- Saved combined imports: reviewed account/currency separation, exact values, current edits, stale source checks, atomic retry receipts and original citation history.
- Retained folder/archive/file-group manifests, chunk verification, safe archive paths, complete registration receipts, and multi-PDF Financial uploads through the same recovery path.
- Phone ingestion dispatch/model/graph/media checkpoints, idempotent writes, safe pause acknowledgement and retained manual graph properties.
- Financial batch pausing at statement boundaries, retained pending imports and clear separately controlled PDF reading groups on the batch screen.
- Split/partial transfer principal, embedded/separate fees, remaining capacity, explicit FX comparisons, onward allocation, current internal/external totals and Timeline source preservation.
- Typed account aliases, referenced-only accounts, later-statement match suggestions, audited case-entity connections and retryable projection of reviewed ownership into the main graph.

The production build and the new migrations through `20260923_account_identity` pass locally. The migration check creates a disposable PostgreSQL database, upgrades from the prior baseline and removes only that test database. An isolated Neo4j check confirms idempotent shared identities, preserved manual names/notes, safe retraction and refusal of namespace collisions.

Broad tests found and repaired the new audit-decision vocabulary and route/package export contracts. Older file-list browser fixtures now explicitly include upload-activity responses. Resource-heavy tab-navigation tests use a per-journey time budget; assertions remain unchanged. Final test counts and publication/deployment status are recorded below after verification completes.

Deployment access returned `invalid_grant` during the local completion pass; this agent did not restart live services or change client records in that pass. The user subsequently confirmed deployment has happened. Remaining independent checks cover the running revision/health and the affected investigator journeys. The actual long chat and historical duplicate/import incident remain external acceptance work, not silently marked done by local tests.

### Verified checks for the completion pass

- Broad backend/Financial run: 5,325 passed and one opt-in graph check skipped. Its two new route/export-contract failures were repaired; the affected router/export/identity/recovery recheck passed all 90 tests. The final pause/identity/shutdown checks passed 78 tests, including the new safe-shutdown check. Existing graph editing checks passed six tests.
- Evidence-engine suite: 516 passed, 14 environment-gated checks skipped. The shared-identity opt-in check was run separately against isolated local Neo4j and passed, including retained manual edits, retraction and key-conflict refusal. Phone graph recovery had also passed on that isolated graph.
- Frontend affected suites cover 1,630 unit tests. Final broad run passed 1,629; the new audit vocabulary copy was completed and the 53 decision-contract/format checks passed afterward. Earlier upload-fixture failures and slow multi-tab test timing were repaired and rerun; tab retention passes with its assertions unchanged.
- Chromium: 70 financial/evidence/Timeline journeys covered. The two old upload-response fixtures were repaired; their six statement journeys plus batch pause and grouped-upload checks all pass (10 checks in the rerun). The other 68 broad-run checks passed, including saved import recovery, split transfer reopening and reviewed identity connections. Mobile screenshots were inspected locally.
- Final production TypeScript/Vite build passes. Scoped ESLint and diff whitespace checks pass. Migration upgrade to `20260923_account_identity` passes in disposable local PostgreSQL.
- The release file list was inspected explicitly: source, synthetic tests and workflow documentation only. Generated screenshots, source documents, case files and exports are excluded.

These are local release results, not a claim of live deployment or a completed
historical client-data audit. No production queue was interrupted by these checks.
