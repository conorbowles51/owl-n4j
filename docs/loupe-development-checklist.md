# Loupe financial development checklist

Authorized overnight window: 7 September 2026, until **06:00 Europe/Dublin
(05:00 UTC)**. Scheduled continuation every 5 minutes in the same task.

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

2. **Review uncertain readings before they enter the ledger — partial**
   - [ ] Save possible transactions separately until they are ready for use.
   - [ ] Show questionable amounts, dates and account details alongside the source.
   - [ ] Let the investigator confirm, correct or reject candidate readings, preserving the original and the reason for each decision.
   - [ ] Prevent retries or simultaneous candidate reviews from creating duplicate transactions.
   - [x] Foundation: immutable in-memory pending candidate contract, with missing context representable (5d7279d). Persistent storage is now implemented below; review remains.
   - [x] Existing ledger corrections retain originals, history and reasons, with stale-review protection; manual source amount assessment is connected. These do not yet provide candidate review.

   - [x] Foundation: persist immutable candidate originals outside totals with atomic saves and same-mapping retry safety (826caee). Verified with PostgreSQL lock contention and overwrite-refusal triggers. Review UI remains.

   - [x] Foundation: assess saved original amount cells through case-scoped read-only APIs, preserving uncertainty and source citations and refusing source drift (8d6425a). Verified through authenticated local HTTP; review UI remains.

3. **Complete financial accuracy checks — partial**
   - [ ] Complete checks of transaction totals against all supported printed controls.
   - [ ] Check running balances from one transaction to the next.
   - [ ] Repeat all affected checks after a correction, including native controls and running balances.
   - [ ] Explain all remaining discrepancies while keeping classification calculated by the system.
   - [x] Existing statement balance reconciliation and correction consequences are connected; proof class is computed. Broader checks remain.

4. **Finish duplicate handling — partial**
   - [ ] Extend the existing same-case comparison to the remaining supported situations.
   - [ ] Show matching evidence in other cases only where the user has permission.
   - [ ] Make larger comparisons practical and clearly show what was checked.
   - [x] Preserve reasons for excluding or restoring a duplicate in the existing same-case workflow, including tested concurrent decisions.

5. **Make every financial view use the authoritative ledger — remaining**
   - [ ] Connect the graph and financial analysis screens to the reviewed ledger.
   - [ ] Ensure corrections and exclusions consistently update totals, searches and money-flow views.
   - [ ] Prevent older extracted graph values from being counted alongside reviewed transactions.

6. **Show missing periods and incomplete evidence — remaining**
   - [ ] Identify gaps and overlaps between account statements.
   - [ ] Show which accounts and dates the available evidence covers.
   - [ ] Distinguish no matching transaction found from insufficient records to know.

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

## Morning handoff

Pending. Before the cutoff, record completed feature numbers, partial progress,
remaining work, test results, any blockers, and the local application's verified
availability. Do not infer current availability from yesterday's health checks.
