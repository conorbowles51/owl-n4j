# Financial and ingestion workflow release verification

23 September 2026. This record supersedes the earlier “Planned” implementation
labels in the September 22 plan. It distinguishes completed local journeys from
live acceptance. The user has authorised committing and pushing the completed
code, and previously authorised deployment. Client evidence is excluded from Git.

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
- A historical combined import is never silently split, rewritten or stripped of
  investigator corrections. Wrong labels in a known scope can be corrected in
  place. Ambiguous scope changes require source comparison/reprocessing; original
  readings and existing findings/Timeline citations remain retained.
- Resumable byte transfer covers ordinary evidence files, including PDFs. Existing
  folder/archive and dedicated Cellebrite import routes retain their own workflows.
  This release does not claim checkpoint recovery for those separate ingestion types.
- The long-PDF test establishes page extraction/recovery on a generated native PDF.
  Alex's large chat still requires a complete run through the actual providers and
  live host. The observed Neo4j timeout and historical import attempt cannot be
  attributed conclusively without their live logs.
- Deployment and live read-only verification are pending renewed Google Cloud
  authentication (`invalid_grant` at the release check). The user has been asked to
  renew the login; no new deployment permission is required. Before the first
  transition from old workers, inspect active work and drain safely. Do not bypass
  the release gate or treat an unknown queue state as idle.
- A code push is not a deployment claim. Record the deployed revision and repeat
  source/history, saved statement, shared owner/trail and processing-status journeys
  when server access is restored. Client-case cleanup/import/reprocessing is not a
  demonstration action; retain the existing no-live-client-mutations boundary.
