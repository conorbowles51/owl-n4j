# Financial investigation redesign

Approved scope: 11 September 2026. The user requested a proper plan and implementation of the product assessment. This plan keeps original evidence and recorded decisions intact while replacing the disconnected user workflow.

## Product rules

- Statements is the workspace for upload, extraction review, corrections before import and import confirmation.
- Transactions is the workspace for investigating imported payments. It does not embed an open statement import editor.
- Every payment opens useful details, its original source, notes and correction history. Technical evidence classifications belong in secondary details, not the main table.
- A selected set of payments can be saved with a name and an observation, then reopened from Financial. Use existing casework storage and source anchors rather than a second notes database.
- Account/date scope, table filters and selected totals must be understandable and must not silently imply the same scope when they differ.
- Analysis results lead to recognisable payments and existing saved findings. Selecting a chart is not a save action.
- Drafts survive ordinary navigation. Local drafts are explicitly distinguished from saved case records.
- Original text and edited import values remain distinguishable. A generic OCR grid is not advertised as a faithful statement table.
- No push until a coherent, verified improvement is ready. Preserve earlier user authorisation and existing deployment process; do not invent a deployment blocker.

## 1. Separate statement preparation and investigation

- [x] Move the full upload/review workspace to Statements and keep it mounted while another financial tab is in use.
- [x] Route the sidebar file list into Statements.
- [x] Keep only a clear Add statements action in Transactions.
- [x] Confirmation closes the review and opens investigation; identify the imported account/statement without silently losing another scope.
- [x] Organise account/period checks beneath the statement workspace.
- [x] Browser acceptance: upload/reopen, switch tabs, confirm once, open source from imported payment.

## 2. Make transactions usable

- [x] Compact investigation table with selection, date, description, money in/out and balance. Put technical fields under an explicit details control.
- [x] Open a transaction to inspect its values and source, add a note, correct a mistake or review its history.
- [x] Keep actions accessible with the statement sidebar open at ordinary laptop width.
- [x] Show totals for the filtered/selected payments, separately by currency.
- [x] Preserve unsaved notes and clearly state where they are saved.
- [x] Browser acceptance: find a payee, inspect a payment, record a note, correct a value, leave and return.

## 3. Save investigation work and produce reports

- [x] Save a named set of selected imported payments with an observation in existing casework storage.
- [x] Findings view in Financial lists saved work and reopens linked transactions/originals.
- [x] Clear report entry point with an inclusion preview. Distinguish selected findings/payments from wider supporting history.
- [x] Existing saved notes remain accessible; no data migration that drops links.
- [x] Browser acceptance: save/reopen selection and note, export readable result, verify scope and references.

## 4. Connect every analysis area

- [x] People/businesses: totals, payments, source, name linking and saved finding in one understandable path.
- [x] Transfers: compare both sides, record rationale, preserve choices and reopen results.
- [x] Patterns: explain each supported check, preserve settings, show payments and save a finding. Explicitly assess variable-amount recurring relationships.
- [x] Trends: date-specific chart guidance and transaction drill-down.
- [x] Graph: readable accounts/names and selection details connected to payments.
- [x] Case events: compare payments/events and save the observation with both sources.
- [x] Advanced tracing: guided inputs and saved/reopenable assumptions; check each method separately.

## 5. Verify real statement interpretation

- [ ] Locate and inspect the exact Capital One layout shown by the user.
- [x] Compare proposed transactions with the original, independently of what the reconstructed text grid shows.
- [x] Reconstruct separate transaction sections using their positions and headings. Do not place advertising and page headers inside transaction tables.
- [x] Retain raw extracted text for diagnosis without presenting it as accurate layout.
- [x] Verify dates, signed amounts, totals, cardholders and blank cells across supplied PDFs. No original files or existing imports overwritten.

## 6. Finish the whole workflow

- [x] Consolidate import status, errors, exclusions and history under task-based navigation.
- [x] Rewrite visible text based on actual actions. No raw backend caveats in primary guidance; retain meaningful limitations where needed.
- [x] Update beginner guide and screenshots after the workflow is stable.
- [x] Run targeted integration checks, then the broad regression suite once at the final integration milestone.
- [x] Complete the nine-step investigator acceptance script in the product assessment, including another user's ability to retrieve saved work.
- [x] Review final diff, record outstanding limitations and commit the verified implementation.
- [ ] Push the release. Automatic approval review requires explicit permission to publish this commit to the verified public repository `conorbowles51/owl-n4j`.

## Implementation notes

The starting point includes unpushed statement-file retry controls and the assessment. Provisional copy/layout edits from the assessment were backed up and removed. Do not treat those experiments as completed redesign work.

## Earlier implementation checkpoint, 11 September, morning

Historical checkpoint, superseded by the integration evidence below:
- Local browser: saved transaction note and named two-payment selection, reopened both from Findings, opened a person's payments, and retained a pattern window across navigation. The original synthetic case and evidence remain intact.
- Separate Statements workspace and Transactions workspace verified in the browser. Final import handoff and correction acceptance remain to be exercised after integration.
- Capital One supplied PDF, physical page 3: printed cardholder payment, purchase, fees and interest sections render separately. The advertisement is available as other page text and does not become a table column. This is account ending 3539, not the user's screenshot ending 8160. The exact screenshot file has not been located among the three supplied PDFs.
- 53 focused frontend tests passed for navigation, payment selections, HTML reports and section geometry. 20 backend source/query tests passed. Additional analysis and account-context changes followed these checks and require the next focused integration run.
- The new saved-note HTML report includes only the chosen note, attached payment snapshots and references. It does not yet package original PDFs. Full report acceptance remains open.

The paragraphs above record the earlier checkpoint, not the final implementation. The checked list reflects the integration evidence below. Outstanding items remain visible.


## Integrated implementation and verification, 11 September

### Delivered behavior

- Statements owns upload, reading, original comparison and confirmation. Transactions owns investigation. Confirmation closes the review, identifies the imported statement and opens Transactions. A control can show that account without silently changing existing filters.
- The statement file list reads saved import counts and account periods from the server. Excluded and replaced payments are not counted as current imports. Existing failed files can be read again without uploading duplicates. Upload bytes still require the browser to remain open; queued server processing survives navigation.
- Transactions supports search, scope, selection, exact totals, original source, notes, corrections and exclusion. Card charges and credits are distinguished from bank cash movements. Corrected records retain the original and link forward to the replacement.
- Findings reopens saved notes, named selections, transfer comparisons, payment/event observations and single-account or cross-account tracing calculations. Calculations preserve their saved assumptions, source references and results. Existing Workspace records are used without a database migration.
- People, trends, graphs, transfers and pattern results open recognisable payments, then the same source/note workflow. Repeated names across separate dates are included even when amounts vary. Pattern suggestions remain hypotheses until investigated.
- Reports contain a chosen note and its attached payment snapshots. A separate inclusion preview lists the complete supporting PDFs before downloading a ZIP. Each PDF is checked against its recorded digest. The package warns that whole statements can contain other transactions.
- Main navigation separates daily investigation from further analysis and processing history. Technical detail remains available under named disclosures. Working forms and results remain mounted during financial tab changes; unsaved note drafts are scoped to the user and case in browser-tab storage.
- The beginner guide now matches the workflows and includes fourteen images. Its always-visible button, modal, images and contents navigation were checked in the running application.

### Acceptance evidence

| Task | Observed result |
| --- | --- |
| Fresh statement import | Created a separate synthetic case, uploaded Nexus PDF, reviewed twelve transactions, changed tabs, confirmed once and landed in Transactions. Original PDF bytes unchanged. |
| Source, note and correction | Opened payment source, saved an observation, corrected a transaction, reloaded and found the replacement with retained history. |
| Saved payment selection | Named two payments, saved an observation, reopened both payment links in Findings. |
| People and patterns | Opened the person's underlying payments; retained pattern settings/results; variable-amount repeated-name checks returned both synthetic relationships. |
| Transfers | Selected paired payments, calculated totals, saved the reason and comparison, reopened saved figures and linked sources. |
| Single-account tracing | Calculated and saved a synthetic scenario, reopened its assumptions/results, verified the report, then changed an assumption and confirmed old results were cleared. |
| Three-account tracing | Selected two transfer links across three accounts. FIFO, LIFO and pro rata returned expected remaining amounts of 80, 100 and 90 GBP. Saved/reopened the calculation and checked that editing assumptions cleared stale results. |
| Case events | Saved an observation with both payment and case-event links, then reopened it in Findings. |
| Report with sources | Downloaded and rendered the selected-note HTML report. Opened its ZIP and compared its included Nexus PDF byte-for-byte with the original. |
| Another case member | A temporary local read-only member opened another author's saved finding and linked payment. Non-members, revoked membership and attempted edits were denied. Temporary account removed. |
| Complex statements | Compared the supplied Capital One physical page 3 and scanned Merrick page 4 with the extracted candidate rows. Capital One sections are separated from its advertisement. Merrick's damaged headings/date remain explicitly flagged; two payment rows are retained for checking. Page navigation and saved file status were checked. |

Machine-readable local records are in `data/local-runtime/redesign-*-acceptance.json`; they are local test evidence and are not deployment data. Screenshots use synthetic cases except the private, read-only real-PDF inspection images under `/tmp`.

### Regression milestone

One broad financial regression run returned 1,059 frontend passes with nine obsolete UI expectations, and 4,441 backend passes with one outdated account-context fixture. The affected checks were corrected without weakening amount, scope or history assertions. Follow-up runs passed 42 frontend and 28 backend checks. Subsequent focused checks cover the final saved-summary, card/bank separation, user-draft isolation, source-package validation, statement-status and correction-link changes. Final type checking and scoped lint passed. The production build passed with the existing large-bundle advisory. Final focused checks passed: 60 core frontend checks, 12 file/selection checks, 29 correction/adjudication checks, 3 note checks, and the new backend file-status/identity checks. A local HTTP check also confirmed the new file-status endpoint respects case permissions. No repeated whole-suite run is being used for small copy changes.

### Limits kept visible

- [ ] Verify the exact Capital One account ending 8160 from the user's screenshot when that file is available. The supplied Capital One file ends in 3539. Do not claim those are the same document.
- Complex scans are not guaranteed to reconstruct every printed table. Damaged OCR and unassigned pages are shown for review. Original text and files remain available; no guess is silently substituted for the statement.
- Uploads that have not finished sending need the browser open. Unsaved form drafts are browser-tab work, not a shared server record. Saved notes, imports and calculations are case records available to authorised colleagues.
- Downloadable note reports and PDFs are available directly from Financial Findings. The separate platform Reports editor has not been replaced by this feature.
- The technical workflow checks do not substitute for the team's own usability review with their cases.

## Release checkpoint

The remote branch was fetched and matched the starting commit `424e859c`, so no incoming merge was required. The release includes the assessment, this completed checklist, application changes and updated guide. Private PDFs, local test records, unrelated documents, archives and temporary screenshots are excluded. No financial database migration is required. The existing server deployment follows a push to `integration/evidence-main-reunion`.

The implementation is committed as `fee37455`. Automatic approval review rejected the push twice: first because the destination was unverified, then because the verified GitHub repository is public and the reviewer requires explicit approval for this public disclosure. GitHub confirmed WRITE access. No push occurred. Do not retry through another transport or workflow; obtain the required destination-specific approval.
