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

5. **Make every financial view use the authoritative ledger — remaining**
   - [ ] Connect the graph and financial analysis screens to the reviewed ledger.
   - [ ] Ensure corrections and exclusions consistently update totals, searches and money-flow views.
   - [ ] Prevent older extracted graph values from being counted alongside reviewed transactions.

6. **Show missing periods and incomplete evidence — partial**
   - [x] Identify gaps and overlaps between recorded account statements with eligible printed bounds (8b6c9ad). Enclosing exports are included; oversized accounts are explicitly unavailable.
   - [x] Show which accounts and dates the recorded statement bounds cover, with exclusions and limits visible (8b6c9ad). This does not certify full transaction extraction or undated/unprocessed evidence.
   - [ ] Distinguish no matching transaction found from insufficient records to know.
   - [x] Explicit account/date filters on current ledger rows, draft/apply/clear behavior, bounded case-scoped account lookup and case-switch resets (a6ee80c). Requested-interval coverage remains.
   - [x] Empty ledger answers respect account/date filters, explain that no match does not establish absence of transactions, and retain response-count discrepancy warnings even for zero rows (e13375c). Quantified search coverage and filter controls remain.

7. **Connect transactions and explain money movement — remaining**
   - [ ] Link likely transfers between accounts and parties.
   - [ ] Avoid counting both sides of the same transfer as separate money movements.
   - [ ] Show the evidence supporting a match and distinguish exact matches from uncertain ones.
   - [ ] Connect comparisons between financial records and statements or claims about payments.

8. **Produce traceable reports and exports — remaining**
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
