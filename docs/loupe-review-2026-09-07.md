# Loupe review — 7 September 2026

The financial application runs locally in separate Python virtual environments.
The reviewed ledger now drives the main documentary Transactions, Counterparties
and Trends screens. You can filter the ledger and download its rows, totals,
source references and relevant decisions, together with a readable report.

**The whole financial piece is not finished.** Of the original ten features,
eight are partial and two remain unconnected. None is complete end to end.
The detailed [development checklist](loupe-development-checklist.md) retains every
original feature and completed subitem; checked work has not been removed.

## Try the local application

Open [Loupe locally](http://127.0.0.1:55174). Login:
`loupe-local@example.com` / `Loupe-local-test-2026`.
These are development credentials for the isolated synthetic-data stack.

1. [Transactions, totals and export demo](http://127.0.0.1:55174/cases/e0da5581-a1ac-4db5-a3a9-e17021fb807a/financial)
   - Open **Transactions**, using **Ledger postings** mode. Ten included readings
     total **2,100.00 GBP**. All synthetic exclusions used during testing were restored.
   - Apply an account or date filter. The summary and download use the applied
     scope, rather than unfinished edits to the filter form.
   - Open **Counterparties**, then **Read ledger counterparty totals**. This fixture
     has no recorded counterparty labels; the screen says so. Expand contributing
     readings to open a source reference. Equal labels never establish identity.
   - Open **Trends**, then **Read ledger date totals**. Switch daily/monthly and
     inspect the supporting readings. These are account postings, not transfer-netted flows.
   - **Download ledger snapshot** saves a ZIP containing a readable HTML report,
     exact JSON snapshot and verification manifest. Open `ledger-report.html`.
     The report carries its limitations and keeps exact minor units beside money.
   - This fixture has source references but no original PDF files to highlight.
     Use the correction demo below to inspect an actual generated PDF image.

2. [Saved PDF review demo](http://127.0.0.1:55174/cases/5adf884c-aede-4a8d-923e-c3f240d2f708/financial)
   - On **Ledger**, choose **Open PDF readings**, **Open readings**, then a source
     row. The finalized original reading is read-only and retains its review history.
   - Two deliberately selected PDF rows were finalized; one subsequently received
     a ledger correction. The original and replacement are preserved.
   - The current summary includes zero rows and excludes three stored readings.
     Selected rows do not establish complete statement coverage; these readings
     are not promoted into verified totals merely because they were reviewed.

3. [Correction history and PDF source demo](http://127.0.0.1:55174/cases/5675421f-0860-4048-abe1-902241a1feec/financial)
   - Open **Decisions**, expand **Original and replacement readings** for the
     recorded correction, then **Running-balance comparison**.
   - The saved comparison includes the expected **410.00 GBP** against printed
     **400.00 GBP**. It is a historical diagnostic, not a claim that all checks passed.
   - **View source: row-0001** opens the preserved original and generated PDF image.
     The corrected document remains outside verified totals pending broader checks.

The demo links and current ledger counts were verified through the local API.
All three cases are synthetic. Your two real PDFs remain inspection inputs,
not accepted end-to-end transaction extraction fixtures.

## Original ten features

1. **Import financial transactions from PDFs — partial**
   - [x] Select stored PDF rows, map columns deliberately and preserve exact source references.
   - [x] Inspect both real PDFs and verify stored source binding.
   - [ ] Finish automatic row/column extraction and scanned-document handling with accuracy acceptance.

2. **Review uncertain readings before they enter the ledger — partial**
   - [x] Persist original candidates, review with reasons, and finalize deliberately reviewed rows safely.
   - [x] Preserve sealed originals and guard retries, concurrent writes and source reuse.
   - [ ] Complete the broader automatically extracted uncertainty-review journey.

3. **Complete financial accuracy checks — partial**
   - [x] Statement reconciliation, correction consequences and historical running-balance diagnostics.
   - [ ] Prove row order/coverage and recheck all supported printed/native controls after correction.

4. **Finish duplicate handling — partial**
   - [x] Same-case comparison, exclusion/restoration reasons and concurrent-decision protection.
   - [ ] Broaden supported comparisons, authorized cross-case sightings and larger-scale coverage.

5. **Make every financial view use the authoritative ledger — partial**
   - [x] Main documentary Transactions, Counterparties and Trends now use ledger readings.
   - [x] Exact totals, source links and tested exclusion propagation across these screens and export.
   - [ ] Migrate remaining graph-wide, search and money-flow consumers and verify every correction path.

6. **Show missing periods and incomplete evidence — partial**
   - [x] Printed statement gaps/overlaps and requested account/date coverage, with unknowns explicit.
   - [ ] Carry evidence sufficiency through wider searches and exact PDF-bound navigation.

7. **Connect transactions and explain money movement — remaining**
   - [ ] Connect transfer matching, supporting evidence and uncertainty to reviewed ledger data.
   - [ ] Avoid counting both sides of a matched transfer as separate money movement.
   - [ ] Connect comparisons with statements or claims about payments.

8. **Produce traceable reports and exports — partial**
   - [x] Consistent captured ledger/history, exact scope/totals, JSON and readable HTML report.
   - [x] Verification manifest, case permissions and direct downloads from primary ledger views.
   - [ ] Complete polished exhibits/PDF pagination, broader review-history inclusion and source-file packaging.
   - [ ] Fresh source-byte verification at export is not implemented; recorded ingestion hashes are labelled accordingly.

9. **Complete funds tracing — remaining**
   - [ ] Connect the existing tracing methods to reviewed transactions and compare their results.
   - [ ] Explain assumptions, missing records and ordering, and preserve each result's supporting basis.

10. **Test the complete application locally — partial**
    - [x] Persistent isolated services/venvs and repeatable synthetic HTTP, database and browser checks.
    - [x] Integrated baseline: **3,827 backend tests, 1,032 frontend unit tests,
      11 Chromium tests**, TypeScript and full ESLint passed.
    - [x] Later primary export wiring: **44 targeted tests**, TypeScript, scoped ESLint
      and browser download/hash checks passed.
    - [ ] Complete the real-PDF/AI journey, larger and interrupted processing cases, and full application acceptance.

## Limits and next development

AI extraction, embeddings, chat and transcription were not validated. The local
launcher deliberately uses invalid provider credentials. Source hashes in exports
are recorded ingestion hashes, not fresh checks of bundled PDFs. Structured PDF
candidate-review history is not embedded in the export; the preserved provenance
and finalization references remain. Counterparty groups are verbatim labels, not
resolved people or proven transfers. Net postings are not bank account balances.

The next substantial development should focus on completing extraction/accuracy
acceptance and authoritative ledger consumers before connecting transfer matching
and tracing. The [running state](loupe-build-state.md) records the exact next step,
implementation references and current test fixtures. [Local application instructions](local-application.md)
cover startup and repeatable checks. Changes are committed locally; nothing was pushed or merged to main.

Local readiness checked at **12:36 Dublin time**: frontend, backend and evidence
engine responded successfully; the synthetic ledger is restored. Both real PDFs
still match their original hashes, with no matching copies ingested into the
isolated database. This is a preservation check, not extraction-accuracy acceptance.
