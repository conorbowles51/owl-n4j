# Loupe financial development checklist

Extended authorized window: 7 September 2026, until **13:00 Europe/Dublin
(12:00 UTC)**. Neil explicitly extended the deadline; the existing heartbeat is
ACTIVE every five minutes in this same task. Reserve the final 15 minutes for
verification and handoff. Neil requests mindful usage: targeted checks and reuse
of valid passing suites. Earlier 06:00/09:00 plans remain history.

Keep all ten features and their subitems visible. Mark verified completions [x];
never remove completed work. A feature is complete only when its complete user
workflow is connected and tested. Existing foundations are listed separately so
that progress is not confused with completion of the remaining feature.

Baseline: implementation 5d7279d; 3,570 financial tests passed. No entire remaining
feature below is complete at the start of this window.

1. **Import financial transactions from PDFs — partial**
   - [ ] Identify transaction rows and column meanings: dates, amounts, accounts and money coming in or going out.
   - [ ] Link each extracted value to its exact location in the original document, including verified stored PDF cells.
   - [ ] Handle digital PDFs and scanned documents while preserving uncertainty where the source is unclear.
   - [x] Foundation: bind nominated canonical-text rows to exact source spans and source/provenance revisions; keep every candidate pending. Verified in 5d7279d, including 21 new tests. Automatic extraction remains; geometry adapter completion is recorded below.

   - [x] Foundation: verify stored PDF table/cell identity and rectangles without guessed text offsets (5ab6931). Includes repeated amounts, provenance drift, malformed geometry and generated-PDF extraction tests.

   - [x] Deliberate source selection: inspect a stored PDF table, choose rows and assign proposed column meanings without automatic transaction classification (9ddfe63). Both real PDFs passed source-binding smoke checks; full transaction accuracy remains.

   - [x] Source-byte prerequisite: compare the current case-scoped file against the saved candidate digest, refusing missing/changed sources and observed changes during reading (43b2402; 11 new tests). This is a backend prerequisite; ledger admission remains unconnected.

   - [x] Column suggestion aid: propose exact supported labels from the first ten stored rows, require explicit acceptance, and preserve a separate transaction-date role (aac46b0). No automatic transaction classification or row selection is claimed.

2. **Review uncertain readings before they enter the ledger — partial**
   - [x] Save deliberately selected rows from stored PDF tables separately until they are ready for use (9ddfe63). Automatic extraction/nomination remains under feature 1.
   - [ ] Show questionable amounts, dates and account details alongside the source.
   - [x] Let the investigator confirm, correct or reject saved candidate readings, preserving the original and the reason for each decision (ee6edb4). Local UI verified; deliberate stored-PDF mapping is now connected. Automatic nomination and ledger materialization remain.
   - [x] Prevent retries or simultaneous candidate reviews from creating duplicate transactions in the deliberate saved-PDF workflow (27f8328, a2f4337). PostgreSQL competing writes and authenticated UI/HTTP retries preserve the original receipt and transaction IDs.
   - [x] Foundation: immutable in-memory pending candidate contract, with missing context representable (5d7279d). Persistent storage and review are now implemented below.
   - [x] Existing ledger corrections retain originals, history and reasons, with stale-review protection; manual source amount assessment is connected. These do not yet provide candidate review.

   - [x] Foundation: persist immutable candidate originals outside totals with atomic saves and same-mapping retry safety (826caee). Verified with PostgreSQL lock contention and overwrite-refusal triggers. UI completion is recorded below.

   - [x] Foundation: assess saved original amount cells through case-scoped read-only APIs, preserving uncertainty and source citations and refusing source drift (8d6425a). Verified through authenticated local HTTP; UI completion is recorded below.

   - [x] Foundation: append resolved/rejected/reopened review decisions with reasons, exact reading validation, immutable history and stale-review protection (c4ae63e). Case-scoped read/edit APIs and real PostgreSQL contention verified. Review screen completion is recorded below.

   - [x] Saved-reading UI: bounded batch/row lists, account search, original amount assessment with source image, exact review form and immutable history (ee6edb4). Creation API retries preserve original IDs.

   - [x] Provisional account setup: explicit document/currency-scoped label and reason, audit run, same-account retry protection and a guard against use from another PDF (dd7fc5b). Known-account identity/merge remains separate.

   - [x] Cross-batch source reuse review: detect repeated stored rows/overlapping source claims, expose uncomparable pairs and coverage limits, and open the affected readings (7ee220b). This is not database-enforced materialization deduplication.

   - [x] Truthful reading method: explicitly record investigator-reviewed readings without claiming native/template/model extraction or promoting their classification (08b1540). Storage, UI labels and PostgreSQL downgrade protection verified; candidate materialization remains.

   - [x] Incomplete coverage stays explicit: selected documentary financial rows remain outside verified totals even when subset arithmetic balances; reconciliation and corrections cannot silently promote them (ed656da). End-to-end admission remains.

   - [x] Durable finalization storage: keep permanent candidate/review/transaction links, refuse repeated sealed batches and later review/mapping changes, and protect source scope in PostgreSQL (f0ddde3). Atomic transaction creation and its concurrent retry acceptance remain.

   - [x] Atomic candidate writer: fresh review/account/source checks, exact whole-batch transactions, retained originals/rejections, one finalization receipt and safe retries (27f8328). PostgreSQL rollback and two competing requests verified; authenticated API and UI remain before this workflow is complete.

   - [x] Connected finalization UI: current preview, explicit coverage acceptance/reason, safe reload/retry behavior, refreshed ledger rows and source-image links (a2f4337). The larger automatic extraction and complete-statement workflows remain.

   - [x] Finalized review protection: keep originals/history and source assessment accessible, block later candidate/account edits, and verify a ledger correction preserves the receipt and original PDF citation (a7c231d). The replacement remains P3 outside verified totals.

   - [x] Source date assessment: display alternative numeric dates, unresolved years/centuries, invalid dates and original citations without selecting a reading (46a3417). Automatic date/context resolution and account uncertainty work remain.

3. **Complete financial accuracy checks — partial**
   - [ ] Complete checks of transaction totals against all supported printed controls.
   - [ ] Check running balances from one transaction to the next.
   - [ ] Repeat all affected checks after a correction, including native controls and running balances.
   - [ ] Explain all remaining discrepancies while keeping classification calculated by the system.
   - [x] Existing statement balance reconciliation and correction consequences are connected; proof class is computed. Broader checks remain.

   - [x] Correction running-balance diagnostics: compare before/after under both possible source-row orders, expose unchecked intervals and retain source-linked results in the correction audit (4b70844). Proven order/coverage and native-control revalidation remain; this does not promote classification.

   - [x] Historical running-balance diagnostics: show the saved comparison in correction history, preserve original source links, and distinguish historical results from current ledger state (42e42f1).

4. **Finish duplicate handling — partial**
   - [ ] Extend the existing same-case comparison to the remaining supported situations.
   - [ ] Show matching evidence in other cases only where the user has permission.
   - [ ] Make larger comparisons practical and clearly show what was checked.
   - [x] Preserve reasons for excluding or restoring a duplicate in the existing same-case workflow, including tested concurrent decisions.

5. **Make every financial view use the authoritative ledger — partial**
   - [x] Live exclusion acceptance across Transactions, Counterparties, Trends and export (5aff978): synthetic400GBP excluded, all totals2100→1700, restored with originals/history retained and export hashes verified. Broader correction/legacy graph propagation remains.
   - [x] Main documentary Counterparties displays ledger label groups with exact reconciled totals, scoped filters, paged source links and decision refresh (0fe3c69).35page/14panel tests and live source-dialog check pass; equal labels do not prove identity or transfers.
   - [x] Backend/API exact counterparty source-label totals share ledger eligibility, separate currencies and retain contributing transaction/source references (5cc894e).38 summary/package tests, route test and live HTTP parity pass. UI integration remains; no identity/transfer matching claimed.
   - [x] Main documentary Transactions uses current ledger readings, filters, exact summary and source/correction/decision controls independently of graph loading (b67e365).31 page tests and live bigint/decision-dialog check pass. Counterparties migration remains.
   - [x] Exact daily/monthly ledger totals display with paged contributing-reading source links and reconciliation to the summary (8582179). Legacy graph Trends remains separate.
   - [x] Daily/monthly exact ledger posting totals share summary eligibility and retain contributing transaction/source IDs (d40474a). Time-series display and legacy graph migration remain.
   - [x] Preserve full bigint money through individual ledger JSON, table and decision identity using exact strings, with safe numeric compatibility (19a8980).
   - [x] Backend/API exact ledger posting summaries, separate currencies, explicit excluded populations and a hard no-partial-total limit (0ae8242). Display and legacy-view replacement remain.
   - [ ] Connect the graph and financial analysis screens to the reviewed ledger.
   - [x] Main documentary Trends uses ledger analysis independently of graph loading; intelligence remains explicitly separate (9e0ec3a). Transactions/Counterparties graph migration remains.
   - [x] Current ledger summary display uses exact currency totals and included/excluded populations, with applied-filter scope and correction/adjudication refresh (b82d010). Legacy graph cards and other analysis views remain.
   - [ ] Ensure corrections and exclusions consistently update totals, searches and money-flow views.
   - [ ] Prevent older extracted graph values from being counted alongside reviewed transactions.

6. **Show missing periods and incomplete evidence — partial**
   - [x] Identify gaps and overlaps between recorded account statements with eligible printed bounds (8b6c9ad). Enclosing exports are included; oversized accounts are explicitly unavailable.
   - [x] Show which accounts and dates the recorded statement bounds cover, with exclusions and limits visible (8b6c9ad). This does not certify full transaction extraction or undated/unprocessed evidence.
   - [ ] Distinguish no matching transaction found from insufficient records to know.
   - [x] Display requested-date coverage alongside applied ledger account/date filters, explicitly distinguish unknown bounds from covered dates, retain exclusions and prevent stale scope results (982c530). Wider search and exact PDF-bound navigation remain.
   - [x] Backend/API requested account/date coverage counts outside tails, preserves currency groups and exact intersecting source-period references, and returns unknown/unavailable explicitly (036f700). Filter-screen integration remains.
   - [x] Explicit account/date filters on current ledger rows, draft/apply/clear behavior, bounded case-scoped account lookup and case-switch resets (a6ee80c). Requested-interval coverage remains.
   - [x] Empty ledger answers respect account/date filters, explain that no match does not establish absence of transactions, and retain response-count discrepancy warnings even for zero rows (e13375c). Quantified search coverage and filter controls remain.

7. **Connect transactions and explain money movement — remaining**
   - [ ] Link likely transfers between accounts and parties.
   - [ ] Avoid counting both sides of the same transfer as separate money movements.
   - [ ] Show the evidence supporting a match and distinguish exact matches from uncertain ones.
   - [ ] Connect comparisons between financial records and statements or claims about payments.

8. **Produce traceable reports and exports — partial**
   - [x] Primary Ledger and documentary Transactions export their applied filter scope directly, with case-switch reset and no misleading held-out-only export (51ebd77).44targeted tests and primary browser ZIP/hash checks pass.
   - [x] Format report money exactly in currency units while preserving minor units, and verify exported totals/exclusions against the summary API across case/account/date/empty scopes (96f3a3f).92 targeted tests and live HTTP/hash/layout checks pass; non-member access matrix remains.
   - [x] Bundle a readable HTML report derived from the exact captured snapshot, with scope, totals, included/excluded readings, source references and decision details; independently hash the report (8a1e051). Browser layout/download verified. Amounts use explicit minor units; polished exhibits and PDF pagination remain.
   - [x] Download the applied ledger scope as a ZIP with exact rows/totals, source references, relevant decision history and a byte-verifiable manifest (49f2b83). Browser download and digest verified; formatted reports and broader export workflow remain.
   - [x] Consistent PostgreSQL snapshot of relevant decision history plus exact JSON export manifest, with event/output bounds (001009d). Download/report UI remains; candidate-review history and fresh source-byte verification explicitly excluded.
   - [x] Internal immutable ledger snapshot captures exact rows/totals/source metadata and exclusions from one read, with stable content hash (1efe4ad). Decision history, manifest and download remain; snapshot explicitly not export-ready.
   - [ ] Connect existing export and exhibit components to reviewed results.
   - [ ] Include source references, correction history and relevant limitations.
   - [ ] Ensure exported totals agree with the application.
   - [ ] Record which evidence and decisions supported an exported result.

9. **Complete funds tracing — remaining**
   - [ ] Connect existing tracing calculations to reviewed transaction history.
   - [ ] Support comparison of the available tracing methods.
   - [ ] Explain how assumptions, missing records and transaction ordering affect the result.
   - [ ] Preserve the basis for each tracing result so it can be reviewed.

10. **Test the complete application locally — partial**
    - [x] Integrated post-migration baseline:3,827backend tests,1,032frontend unit tests,11Chromium tests, TypeScript and full ESLint pass (09c341c). Full real-PDF/AI journey and all broader features remain incomplete.
    - [x] Verify actual export membership permissions and immediate revocation with a temporary ordinary local user (cc96526): non-member/no-view denied, view-only allowed, revoked same-token denied, test user removed.
    - [ ] Exercise the full journey from document upload through review, analysis and export.
    - [ ] Validate external AI processing that has not yet been tested.
    - [ ] Test interrupted processing, retries, permissions and larger document sets across the completed workflow.
    - [ ] Finish repeatable startup and testing instructions for the full isolated workflow.
    - [x] Foundation: separate persistent backend/engine venvs, isolated services and synthetic HTTP/PostgreSQL/UI checks. Setup and repeatable partial-workflow scripts are documented in docs/local-application.md.

## Completion record for this window

- Schedule and retained checklist established. No new implementation has landed in
  this window yet. Earlier implementation details and test evidence are in
  docs/loupe-build-state.md. Add dated completed segments here with commit and test
  evidence, retaining all earlier entries.

- 7 September, overnight: **5ab6931** completed the stored PDF grid binding
  foundation under feature 1. All 3,596 financial tests, 895 unit tests, 11 Chromium
  tests, TypeScript and ESLint pass. Feature 1 remains partial; storage/review and
  automatic extraction are not claimed complete. Next: persistent candidates.

- 7 September, overnight: **826caee** completed candidate original storage under
  feature 2. 3,612 financial tests and all frontend gates pass. Live PostgreSQL
  contention produced one mapping/two candidates/zero ledger rows; both originals
  reject SQL updates. Next: review records and assessment, then endpoints/UI.

- 7 September, overnight: **8d6425a** connected saved-candidate amount assessment
  and read APIs under feature 2. 3,631 financial tests and all frontend gates pass;
  authenticated local HTTP returns exact original readings and their PDF rectangle.
  Candidate review decisions/UI remain next; no whole feature is newly complete.

- 7 September, overnight: **c4ae63e** completed review history and APIs under
  feature 2. 3,651 financial tests and all frontend gates pass. Real concurrent
  reviews return one 200/one 409; authenticated reopen/resolve retains history.
  Next: candidate listing/creation and review screens, then materialization.

- 7 September, overnight: **ee6edb4** connected saved-candidate review screens under
  feature 2 and mapping creation/list APIs. 3,657 financial tests, 905 unit tests,
  11 Chromium tests, TypeScript and ESLint pass. Live browser review retained five
  history events and displayed the original PDF image; authenticated creation retry
  returned original IDs. Source mapping creation UI and materialization remain.

- 7 September, overnight: **9ddfe63** connects deliberate PDF source selection under
  features 1/2. All 3,666 financial, 912 unit, 11 Chromium tests and TS/lint pass.
  Local UI save/retry preserves one pending row under the same mapping ID.
  Read-only real-PDF checks passed 153 tables/7,529 source rows; these are not
  transaction counts. Next: account setup and materialization/revalidation.

- 7 September, overnight: **dd7fc5b** adds provisional account setup under feature2.
  3,676 financial tests, 917 unit tests, 11 Chromium tests and TS/lint pass.
  Two real PostgreSQL lock waiters produced one account; browser account setup
  and candidate resolution passed without ledger admission. Next: materialization.

- 7 September, overnight: **7ee220b** adds cross-mapping source reuse checks under
  feature2. 3,685 financial tests, 922 unit tests, 11 Chromium tests and TS/lint pass.
  Live browser found one repeated source row across three compared pairs and opened
  its exact reading. Ledger materialization remains; fix account-audit run wording next.

- 7 September, overnight: **f94e347** corrects account-setup audit display. Setup
  failures stay visible without being mistaken for missing transaction imports.
  927 frontend unit tests, 11 Chromium tests, TS/lint and live UI pass; backend
  remains at the verified 3,685-test checkpoint.

## Morning handoff

Prepared 7 September 2026 before the 06:00 Dublin cutoff. The heartbeat
`continue-loupe-development` was paused through the app at approximately 04:42 UTC
(05:42 Dublin). The local application remains running. Completed work remains
checked above; none of the ten whole features is being marked finished prematurely.

| Feature | Overall status | Position at handoff |
| --- | --- | --- |
| 1. PDF import | Partial | Stored-table selection, exact source binding and real-PDF extraction checks work. Automatic import/nomination and complete transaction accuracy remain. |
| 2. Uncertain-reading review | Partial | Separate immutable originals, review/history UI, source assessment, provisional accounts and source-reuse checks work. Ledger materialization and database-enforced cross-mapping transaction deduplication remain. |
| 3. Financial accuracy checks | Partial | Earlier balance reconciliation/correction work remains connected. Broader printed controls and running-balance revalidation remain. |
| 4. Duplicate handling | Partial | Earlier same-case exclusion/restoration works. Authorized cross-case comparisons and larger-scale coverage remain. |
| 5. Authoritative ledger across views | Remaining | Graph and financial analysis still need the agreed ledger projection. |
| 6. Evidence coverage and missing periods | Remaining | Statement gaps/overlaps and coverage views remain. |
| 7. Transaction connections | Remaining | Transfer matching and explainable money movement remain. |
| 8. Reports and exports | Remaining | Connect existing components to reviewed results with matching totals and audit references. |
| 9. Funds tracing | Remaining | Connect calculations to reviewed history and expose assumptions/results. |
| 10. Full local testing | Partial | Isolated runtime and repeated synthetic HTTP/PostgreSQL/UI checks work. Upload-to-analysis/export and external AI acceptance remain. |

**Completed this window:** immutable stored PDF candidate originals and review
history, source amount assessment, row/column selection UI, provisional account
setup with recorded reasons, cross-batch source reuse checks and accurate audit
notices. Implementation commits and evidence are retained in the completion record.

**Verification:** 3,685 backend financial tests (zero skips), 927 frontend unit tests,
11 Chromium tests, TypeScript and full ESLint pass. Live synthetic checks cover
source images, exact amounts, case scope, stale reviews, immutable originals/history,
concurrent saves/reviews/account creation, retry reuse and navigation to source findings.
The last frontend-only wording change did not alter the backend test checkpoint.

**Real PDFs:** both supplied files remain byte-for-byte unchanged and outside Git.
164 pages were read locally, with 153 tables/7,529 source rows passing the source-binding
contract check; 11 pages render blank. Those source rows are not transaction counts.
No real-document database ingestion, external AI processing or transaction-accuracy
acceptance is claimed by this check.

**Local availability verified at 04:39–04:41 UTC:** frontend55174/backend58002,
engine58003, PostgreSQL55434, Neo4j57474/57687, Redis56379 and Chroma58101 respond.
Engine checks also confirm OCR/storage availability. Its OpenAI health flag only
checks that a key string exists; the isolated launcher uses a dummy key and external
AI processing is not verified. Local migration: 20260907_candidate_reviews.

**Try the new screens:** open Financial → Ledger → PDF readings in the synthetic
case `61272494-00de-4a97-8ba9-77fce4be2f24`. Select a saved batch to review readings or
check source reuse; Choose PDF rows opens deliberate source selection. The displayed
refused setup audit is an intentional stale-review test, not missing imported money.
The real PDFs have only been tested read-only, so they do not appear as ingested cases.

**Next development priority:** safely move complete reviewed candidates into the
ledger. This needs immutable candidate-to-transaction links, whole-document occurrence
handling, defensible source shape/extraction-layer provenance and reconciliation
coverage. Concrete constraints are in docs/loupe-pdf-ledger-bridge.md. No uncommitted
implementation is left. No pushes, merges or real-data changes were made.


### Extended-window checkpoint — 7 September 2026

Neil extended continuation to 09:00 Dublin, with the same five-minute schedule.
Source-byte verification foundation completed in 43b2402; 3,696 financial tests
pass with zero skips. The original ten-feature statuses remain unchanged: this
prerequisite does not yet make candidate-to-ledger admission complete. Next work
is truthful human-review provenance, followed by immutable ledger/source links
and transaction retry/concurrency protection.

Extended-window implementation08b1540 adds explicit investigator-reviewed origin.
Verified: 3,699 backend financial tests (zero skips), 927 frontend unit/11 Chromium,
TypeScript/full ESLint; local PostgreSQL constraints and downgrade guard checked.
Main feature statuses remain partial/remaining until the end-to-end work is done.

Extended-window implementationed656da preserves incomplete selected-row coverage
through computed classification, stored document metadata, reconciliation and
correction verification. 3,701 financial tests pass (zero skips); 927 frontend
unit/11 Chromium, TypeScript/full ESLint pass. Next: immutable finalization links
and source claims, then the atomic candidate-to-ledger writer.

Extended-window implementationf0ddde3 adds immutable whole-file finalization and
source/review/transaction linkage infrastructure. 3,707 financial tests pass with
zero skips; ten isolated PostgreSQL guard checks passed with all fixture rows
rolled back. End-to-end candidate admission is still incomplete: its writer,
preview, concurrent retry test and UI remain. All original features are retained.

Extended-window implementation27f8328 connects reviewed rows to the ledger at
the service layer. 3,721 backend financial tests pass (zero skips). Live synthetic
PostgreSQL confirms rollback, two contending requests, distinct equal-value rows,
one durable receipt, stable retries and sealed review history. API/UI integration
is next; incomplete-coverage P3 rows remain outside default verified totals.

Extended-window implementationa2f4337 completes the deliberate stored-grid review
to finalization UI/API connection. Verified3725 backend/934 frontend unit/11
Chromium tests, TypeScript/full ESLint and real-browser creation/retry/source
highlight checks. The original retry-protection subitem is now checked rather
than removed. Whole-feature statuses remain partial/remaining as broader automatic
extraction, uncertainty, controls/coverage and other listed capabilities still remain.

- 7 September, extended window: **a7c231d** makes finalized candidate screens
  read-only and refuses new provisional accounts before/after a racing finalization.
  All 3,728 backend financial, 937 frontend unit and 11 Chromium tests pass, plus
  TypeScript/ESLint. Synthetic browser correction replaces GBP12.34 with12.35,
  keeps P3, and retains the original highlighted source through its receipt.
  Features1/2 remain partial; no complete-application claim.

- 7 September, extended window: **46a3417** connects read-only source date
  assessment in saved candidate review. All 3,739 financial, 944 frontend unit and
  11 Chromium tests pass, plus TypeScript/ESLint. Live browser preserves both01/02
  interpretations and the missing year while highlighting the original PDF cell.
  Full automatic extraction/nomination and complete date/account review remain.

- 7 September, extended window: **aac46b0** adds explicit printed-label suggestions
  and transaction-date column support. All 3,741 financial, 950 frontend unit and
  11 Chromium tests pass, plus TypeScript/ESLint. A fresh synthetic PDF browser check
  saved only the chosen non-header row pending and preserved its mapping on retry.
  Full automatic row nomination/extraction remains; next focus is missing accuracy
  checks under feature3. Completed work remains visible above.

- 7 September, extended window: **4b70844** connects conditional running-balance
  correction diagnostics and persists the reviewed results. All 3,753 financial,
  952 frontend unit and 11 Chromium tests pass, plus TypeScript/ESLint. Synthetic
  browser/PG correction400→410 reports the introduced mismatch and retainsP3 plus
  original source navigation. Feature3 remains partial: complete controls and
  source-confirmed order/coverage are not claimed verified.

- 7 September, extended window: **8b6c9ad** connects case-scoped statement date
  coverage under feature6, now partial. All 3,763 financial,957 frontend unit and
  11 Chromium tests pass, plus TypeScript/ESLint. Synthetic browser shows the
  February gap and its absence where an enclosing export covers the same dates.
  Search integration and precise period-bound source navigation remain; no whole
  remaining feature is newly completed.

- 7 September, extended window: **42e42f1** exposes saved running-balance diagnostics
  in correction history.960 frontend unit/11 Chromium/TypeScript/ESLint pass; unchanged
  backend remains at3,763 passed financial tests. Read-only browser history/source
  check passes. Development now transitions to final verification and the morning
  handoff; all ten features and their completion marks remain above.


- 7 September, 08:53 Dublin: **e13375c** corrects scoped empty ledger answers
  and preserves incomplete-response warnings with zero returned rows.15 targeted
  unit tests, TypeScript and scoped ESLint pass; unchanged backend gates reused.
  Neil extended the ACTIVE five-minute heartbeat until13:00 Dublin (12:00 UTC).
  All ten features and earlier completion entries remain visible.


- 7 September, 09:04 Dublin: **a6ee80c** connects account/date controls to current
  ledger rows.20 targeted frontend tests, TypeScript/scoped lint and read-only
  authenticated synthetic Chromium pass: February gap returns0 rows, Clear
  restores10. No real evidence edited. Requested-interval coverage remains next;
  feature6 is still partial and every prior completed item is retained.


- 7 September, 09:16 Dublin: **036f700** adds requested-date coverage backend/API.
  Targeted coverage/router tests and authenticated synthetic HTTP pass (February
  gap28 versus enclosing export0). No source/evidence writes. The result panel is
  next; feature6 stays partial and the five-minute schedule remains ACTIVE to13:00.


- 7 September, 09:24 Dublin: **982c530** connects filtered coverage UI.15 targeted
  tests, TypeScript/scoped lint and read-only live browser pass. February0/28
  covered-day comparison and Clear behavior verified. Begin authoritative ledger
  analysis summary next; preserve source admission and computed classification.


- 7 September, 09:35 Dublin: **0ae8242** adds authoritative summary backend/API.
  37 targeted backend tests and read-only synthetic HTTP pass; exact GBP2100 and
  filtered GBP840 verified. Feature5 remains overall unfinished because no
  analysis screen is migrated yet. Next: exact summary display and invalidation.


- 7 September, 09:44 Dublin: **b82d010** connects authoritative ledger summary UI.
  43 targeted frontend tests, TypeScript/scoped lint and live synthetic exclusion/
  restoration pass (GBP2100→1700→2100). Feature5 now partial; graph views remain
  unmigrated. Status: partial1,2,3,4,5,6,10; remaining7,8,9; no whole feature complete.


- 7 September, 09:55 Dublin: **19a8980** closes individual ledger JSON precision
  loss.38 targeted backend and114 targeted frontend tests pass (contract test
  adjusted/rerun); TypeScript/scoped lint and real synthetic PostgreSQL→HTTP→UI
  bigint/negative-balance checks pass. API money fields now strings. Next: exact
  authoritative time summaries; no whole feature newly complete.


- 7 September, 10:03 Dublin: **d40474a** adds date-grouped ledger backend/API.
  32 targeted backend tests and read-only synthetic HTTP pass; date totals reconcile
  exactly with the summary and source IDs match. Next: display and contributing-row
  navigation. Feature5 stays partial; original ten-feature checklist retained.


- 7 September, 10:12 Dublin: **8582179** connects date totals/source navigation.
  21 targeted frontend tests, TypeScript/lint and live synthetic source-record check
  pass. No page-location claim for the fixture. Next scheduled unit consolidates
  accumulated changes with one full integration gate before further migration.


- 7 September, 10:21 Dublin: **421ad37** fixes integration-gate findings: missing
  package export and page query-provider/default-filter test setup. Final full
  backend3,791 pass; frontend1,001-test run had six page-test failures, all resolved
  by the24-test page rerun.11 Chromium, TypeScript/full lint pass. Next: migrate
  the top-level documentary Trends workflow to authoritative ledger data.


- 7 September, 10:31 Dublin: **9e0ec3a** migrates main documentary Trends to ledger
  analysis.36 targeted tests, TypeScript/lint and live source-linked Trends check
  pass. Feature5 stays partial; next work begins traceable authoritative exports.


- 7 September, 10:40 Dublin: **1efe4ad** adds internal deterministic snapshot
  foundation.47 targeted tests and single-SELECT proof pass. No export endpoint or
  completion claim; next is consistent decision history and accurate JSON manifest.


- 7 September, 10:50 Dublin: **001009d** captures export history under repeatable
  read with JSON-specific manifest.29 targeted tests covered/resolved and live
  synthetic concurrent-write consistency/digest checks pass; row restored. Next:
  authenticated attachment and browser download. Feature8 remains unfinished.

- Scoped export download checkpoint (49f2b83): backend31/frontend33 targeted tests,
  final six-button-test rerun, TypeScript/scoped ESLint and Chromium download pass.
  Saved ZIP independently verified: ten synthetic rows, four decisions, GBP2,100,
  matching digest/byte count. Feature8 now partial; no entire feature complete.

- Readable report checkpoint (8a1e051):32 targeted backend tests and scoped ESLint
  pass. Browser ZIP and both hashes verified, ten readings/four decisions rendered;
  screenshot inspected with no horizontal overflow. Feature8 remains partial.

- Exact report/scope checkpoint (96f3a3f):92 targeted tests, scoped ESLint and
  browser layout pass; live HTTP parity/hash checks cover five scopes. Anonymous,
  missing-case and reversed-date refusals verified. Feature8 stays partial.

- Export access checkpoint (cc96526): live four-state membership matrix passed;
  temporary user/membership removed. No ledger/evidence writes or production fix.
  Feature10 remains partial; next main documentary Transactions migration.

- Main Transactions checkpoint (b67e365):31 page tests, TypeScript/scoped ESLint,
  exact bigint/negative-balance browser check and decision dialog open/cancel pass.
  Feature5 remains partial; documentary Counterparties is the next migration.

- Counterparty-label backend checkpoint (5cc894e):38 tests plus route scope/errors
  and live case/account/empty summary parity pass. Main Counterparties UI remains.

- Counterparties UI checkpoint (0fe3c69 plus test-only lint fix):35page/14panel
  tests, TypeScript and scoped lint pass after correcting redundant test escapes;
  live totals/source dialog verified. Feature5 remains partial for broader graph,
  search and money-flow consumers. Integration suite is next.

- Integrated verification checkpoint (09c341c):all3,827backend/1,032unit/11browser
  tests passed, plus TypeScript/full ESLint. No regressions to fix. Existing probe
  test included but untouched. No full-feature completion is implied.

- Cross-view acceptance (5aff978): browser exclusion updates all three migrated
  views; exact restored snapshot, preserved original and both audit decisions
  verified. Synthetic fixture restored; now6decisions. No real evidence changes.

- Primary export checkpoint (51ebd77):44targeted tests, TypeScript/scoped ESLint
  and browser download/hash checks pass.10restored synthetic rows/6decisions;
  no evidence or ledger changes. Prepare final retained feature/demo handoff next.
