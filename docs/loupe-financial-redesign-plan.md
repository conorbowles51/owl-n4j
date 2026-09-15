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

- [x] Locate and inspect the exact Capital One layout shown by the user. The newly supplied 222-page collection was checked locally on 14 September; the screenshot period opens with its three correct transaction dates, amounts and directions.
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
- [x] Push the release. The user explicitly approved publication to the public repository `conorbowles51/owl-n4j`; commits `fee37455` and `9b5a6b5c` were pushed to `integration/evidence-main-reunion` on 11 September 2026.

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

- [x] Verify the exact Capital One account ending 8160 from the user's screenshot. The separate 222-page collection is now supplied and its screenshot page passed a fresh local preparation and browser review on 14 September. This resolves the missing-file check, not independent accuracy across the whole collection.
- Complex scans are not guaranteed to reconstruct every printed table. Damaged OCR and unassigned pages are shown for review. Original text and files remain available; no guess is silently substituted for the statement.
- Uploads that have not finished sending need the browser open. Unsaved form drafts are browser-tab work, not a shared server record. Saved notes, imports and calculations are case records available to authorised colleagues.
- Downloadable note reports and PDFs are available directly from Financial Findings. The separate platform Reports editor has not been replaced by this feature.
- The technical workflow checks do not substitute for the team's own usability review with their cases.

## Release checkpoint

The remote branch was fetched and matched the starting commit `424e859c`, so no incoming merge was required. The release includes the assessment, this completed checklist, application changes and updated guide. Private PDFs, local test records, unrelated documents, archives and temporary screenshots are excluded. No financial database migration is required. The existing server deployment follows a push to `integration/evidence-main-reunion`.

The implementation is committed as `fee37455`. Automatic approval review initially rejected publication and required destination-specific approval. The user then explicitly approved committing and pushing to this public repository in response to the destination-specific question. The push succeeded, moving the remote branch from `424e859c` to `9b5a6b5c`. The local and remote branches matched after the push. The existing auto-deploy can now pick up the release; server deployment completion has not been independently verified.

## Follow-up: reopen and revise saved indirect workpapers

- [x] Open existing workpapers from Findings with their saved amounts, checks, results and source files.
- [x] Create and calculate a revised copy without replacing the original saved work or another open draft.
- [x] Save new workpapers with their method definitions so the historical calculation can still be checked.
- [x] Verify existing-note compatibility, source/case checks and the save/reopen journey using focused checks.
- [x] Update the user guide and record the completed change.

Acceptance: reopened the existing synthetic net-worth workpaper saved before this viewer existed. Its result remained 40.00 GBP, and the original PDF and exact JSON download opened. A separate revised copy changed closing assets from 100.00 to 110.00 GBP, retained that edit across financial tab navigation, calculated 50.00 GBP, saved with the method definition and a link to the original note, and reopened after a reload. The original note body, links and version were unchanged. One synthetic Workspace entry was created; no ledger writes occurred.

The saved-workpaper HTML report was downloaded and rendered with its amounts, checks, result and source references. Fifteen focused checks cover arithmetic, historical compatibility, case/source isolation, altered bytes, changed method fields, retained copy behavior and report text escaping. Scoped lint passed. The guide includes the new viewer screenshot and instructions for saved and downloaded workpapers. Local acceptance record: `data/local-runtime/saved-workpaper-acceptance.json`.

Unsaved revised copies remain local to the open page. Financial tab changes and hiding/showing the copy retain edits; refreshing or leaving the case can discard unsaved changes. Saving creates a shared case note and retains its original workpaper link. Older saved workpapers without a method definition are checked against the current method; incompatible records remain saved and show an error rather than dropping fields.

## Follow-up: browser compatibility on the HTTP deployment

The user's deployment URL uses HTTP. A browser capability check on an intercepted HTTP origin confirmed that SubtleCrypto and randomUUID are unavailable there, although secure random bytes remain available. Financial calculations and downloads had assumed these APIs existed.

- [x] Keep all byte and digest checks working on HTTP using a shared SHA-256 helper, with native browser hashing where available and the pinned `@noble/hashes` implementation otherwise.
- [x] Use secure random bytes for request identifiers when randomUUID is unavailable.
- [x] Check hash vectors, changed data, exact byte ranges, and large-file chunking; exercise saved workpaper and supporting-file downloads in an HTTP browser context.
- [x] Run the affected financial checks, type/lint checks and one production build for this shared compatibility change.

Library import and supported input are documented in the [maintainer's README](https://github.com/paulmillr/noble-hashes). The compatibility fix does not provide transport encryption.

Acceptance: an HTTP-origin browser, with all traffic intercepted to the isolated local app, reported no SubtleCrypto or randomUUID. It still opened the saved workpaper, downloaded its report package, matched the included PDF's digest against the recorded reference, returned the standard SHA-256 result for `abc`, and generated a valid random version-4 request identifier. No financial or Workspace mutations occurred. Local record: `data/local-runtime/http-financial-acceptance.json`.

The 79 affected checks passed, including tracing, transfers, claims, source package verification, file downloads, custody request identifiers and native/fallback hashing. Type checking and scoped lint passed. The production build passed in 6.34 seconds with the existing large-chunk advisory. The guide's fifteen images decoded and its new workpaper sections rendered. The branch was fetched and had no incoming commits before publication.

## Account review follow-up, 11 September 2026

- [x] Separate **Upload and review statements** from **Review accounts** within Statements. Keep the upload form and account review mounted while switching views or financial tabs.
- [x] Open one account's statements from its account card. Show filenames, recorded periods, opening/closing balances, missing balances and differences before the detailed calculation controls.
- [x] Add account-scoped balance and coverage requests. Reject another case's account and mismatched account responses; paginate balance checks within the chosen account. Preserve the 500-period coverage limit and read-only calculations.
- [x] Display credit card amounts owed using the explicit convention retained in the reviewed source controls. Keep unknown conventions unchanged and preserve internal signed arithmetic in the detailed calculation.
- [x] Open the original statement and its balance/date references from balance checks, date coverage and a requested date-range result. Pass case and evidence context to the document viewer.
- [x] Check a chosen account's requested date range, including days before and after existing statements. Preserve the distinction between missing dates and dates that cannot be assessed.
- [x] Open account transactions for all dates, a statement period or the checked date range. Use the actual account/date filters; do not imply that a date range identifies one source file when statements overlap.
- [x] Refresh a repeated date-range check, retain dates across financial tab changes and returning to the same account, and clear the date result when choosing another account. Warn when edited date inputs have not yet been checked.
- [x] Update the beginner guide with the account workflow, a replaced statement-review screenshot and a new requested-date screenshot. Sixteen guide images now accompany the instructions.

Validation: 38 affected backend checks and 45 affected frontend checks passed, including the account/date isolation, exact arithmetic, credit-card presentation, source links, retained upload and navigation checks. Failed new fixture and test-selector assertions were corrected and only the affected checks repeated. Type checking, lint for the changed components, guide rendering and one successful production bundle build passed. No full test suite was run.

Browser acceptance used the existing synthetic Nexus case. It opened the account's statement, identified the uncovered January 2024 range, loaded the original PDF into the viewer with the same SHA-256 as its uploaded bytes, opened the account/date-filtered transaction request with a successful nonempty response, and retained the date range on returning to Statements. No financial writes occurred. Local evidence is retained in `data/local-runtime/account-review-acceptance.json` and is not published.

Limits: this is an account investigation workflow over existing imports, not new PDF extraction accuracy evidence. The unavailable Capital One 8160 source, independently reviewed extraction corpus and broader expert-report acceptance remain outstanding as recorded above. Agreement between balances and payments does not establish complete extraction. Account/date view choices are temporary and reset on a full browser refresh.

## Financial reports follow-up, 11 September 2026

- [x] Select up to 20 saved financial findings across search results and pages. Retain the selection, title and introduction in a user/case-specific browser-tab draft.
- [x] Choose a reading order and preview the actual included notes, payment values, source references and saved tracing or indirect calculations. Require an explicit selection update if a note changed before preview.
- [x] Save the exact previewed note versions as a shared casework report using the existing case permissions and entry history. Do not edit the original notes or discard a newer draft when an earlier save completes.
- [x] Reopen the report from Financial Findings and the main Reports page. Make New financial report open Findings; distinguish the older report types and their loading errors from financial reports.
- [x] Download readable HTML or a ZIP with the saved report data and file manifest. Optional original PDFs are deduplicated, size-limited and checked against their recorded bytes and payment/calculation references.
- [x] Show exact payment totals per note, account and currency. Do not add overlapping findings into a misleading report-wide total.
- [x] Preserve method definitions for older saved calculations when preparing a report. Reopening the saved report uses the captured definition and does not depend on the current catalog.
- [x] Add beginner instructions for selection, ordering, preview, saving, reopening and downloads, with two real screenshots of the local synthetic workflow.

Validation: 21 affected frontend checks passed, including exact large amounts, overlap handling, saved calculation sources, modified records, case separation, optional original bytes and save/draft races. The save-race check found and fixed a late response clearing a newer draft. Scoped lint, TypeScript, guide generation and the final production build passed. No full suite was run.

Browser acceptance selected two existing synthetic workpapers, retained the draft across financial tabs, changed their order, previewed the original 40.00 GBP and revised 50.00 GBP results, saved once and reopened from both Findings and Reports. Both original notes and links were unchanged. Downloads with and without PDFs succeeded; the shared PDF appeared once and all listed member sizes and hashes matched. No new ledger or extraction writes occurred. Local evidence is `data/local-runtime/financial-report-acceptance.json`; the synthetic case and this local receipt are not published.

Limits: this is a report of selected saved findings, not completion of the full expert packet. Historical note values remain historical even if later transactions are corrected. The original expert-packet acceptance and independently reviewed extraction corpus remain open. The unrelated older general-report API is unavailable in the local app; the financial report workflow uses the working shared casework API and remains accessible independently.

Report release: `8126f24e` was pushed after the user's explicit **push and continue** approval. The public server version endpoint returned `8126f24` on 11 September. The earlier push-review block is resolved.

## Completed: credit-card balances in automatic import, 12 September 2026

Reproduced against the first billing period in the supplied 108-page Capital One PDF. The original Account Summary prints 6,700.18 USD previous balance and 6,637.96 USD new balance. Automatic review finds the 180.00 payment, 61.62 purchase and 56.16 interest charge, but returns no balance controls. Original pages and stored imports have not been changed.

- [x] Recognise the exact summary balance labels and corresponding source cells without selecting the payment coupon or credit limit.
- [x] Show the printed amounts in statement review, retain corrections and cite the original values.
- [x] Store the explicit amount-owed convention and convert it for the existing signed ledger arithmetic at confirmation.
- [x] Reopen those retained controls from the imported statement, and show consistent balance checks and exports.
- [x] Verify the supplied statement read-only and a separate synthetic import through the browser. Update the guide and run only affected checks before release.

Validation: the supplied 108-page file was checked read-only; its first billing period now proposes the printed 6,700.18 opening and 6,637.96 closing amounts owed while keeping the same three transaction rows and the undated-interest exception. A separate two-page synthetic PDF was uploaded and confirmed through the local browser. Changing the opening amount produced a difference; restoring it removed the difference. The three imported transactions reconciled from 1,000.00 to 937.78 owed. Both retained balance buttons highlighted the correct account-summary cells, and the downloaded check retained the sign convention and exact values. No browser console errors. Private local evidence is retained in `data/local-runtime/card-balance-acceptance.json`.

The browser exercise also exposed a recognized-card case where missing section-layout context hid dated rows. These now remain visible as review exceptions, along with undated interest. Repeated summary balances are flagged rather than selected arbitrarily. Older imports are unchanged and can only acquire these controls through an explicitly reviewed replacement import.

Affected validation: 96 backend checks and 33 frontend checks passed across statement import, proposals/catalog, source citations, balances and processing provenance. TypeScript, scoped lint, guide generation and production build passed. No full suite was run. This change does not establish independent extraction accuracy across other issuers or complete the outstanding expert-packet acceptance.

## Completed locally: rereading damaged PDF text, 12 September 2026

Physical page 4 of the supplied Merrick PDF is legible, but the embedded text damages the statement date, summary labels and amounts. A read-only local OCR pass recovered the printed date and summary values from the page image. The existing reread control repeats automatic extraction and offers no way to replace this embedded text reading.

- [x] Add a plain-language choice between normal extraction and reading every page from its image using local OCR.
- [x] Retain the chosen method with the version request, engine job and processing record. Resuming an interrupted request must use the same method.
- [x] Preserve original bytes, earlier readings and current imports. Require review and explicit confirmation before replacement.
- [x] Check request recovery, source preservation, local processing and the browser controls. Update the guide and run affected checks.
- [x] Group OCR words into printed phrases and dates using their measured spacing, keeping adjacent numbers separate. Exclude complete statement-cycle headers from transaction proposals.
- [x] Keep a printed amount in its table when its text is slightly wider than a left-aligned Amount heading. Refresh the file list when opening a completed reading.

Validation: 82 affected backend checks, 47 engine checks and 8 frontend checks passed, plus type checking, scoped lint and the final production build. No full suite was run. The first browser check exposed individual-word cells; the corrected run recognised the two-page synthetic statement, its three transactions and both printed balances. Refresh restored the requested method, the original source opened on page 2, and the printed payment remained in the correct column. The original import and PDF bytes were unchanged; the new processing record validates and identifies both pages as OCR. Local records are `data/local-runtime/image-reread-acceptance.json` and `data/local-runtime/image-reread-proposal.json`.

Read-only follow-up on the supplied Merrick page recognised the printed 25 April 2021 statement date and the two purchases dated 22 and 23 April, for 14.00 and 100.00 USD. The earlier embedded date had been unreadable. No real statement import or original file was changed. This is a single-page comparison, not independent corpus validation. The guide was regenerated without opening documentation panels.

This does not claim automatic correction of every damaged document or add Merrick account-summary balance controls. The user still reviews the new reading. No external OCR service or AI provider is used.

## Completed locally: Merrick balances and OCR date conflicts, 13 September 2026

- [x] Read Previous Balance and New Balance from Merrick's Summary of Account Activity, using the adjoining Payment Information box to exclude repeated payment-coupon values. Keep zero, unreadable and negative values distinct.
- [x] Retain the printed amount-owed convention, original balance cells and corrections through confirmation and the imported statement source view. Missing or duplicate controls require review.
- [x] Read an account number split into OCR cells only when those digits follow the printed Account Number label. Do not repair uncertain characters or use unlabelled numbers.
- [x] Flag disagreement between Statement Date and Billing Cycle Closing Date. Withhold inferred transaction years until the user reviews them; do not infer a billing period from the statement date.
- [x] Check the supplied Merrick page read-only and complete a separate synthetic browser import, including a changed balance, restoration, confirmation and the imported balance check.

Validation: 35 affected backend checks passed in targeted runs. The browser imported exactly two synthetic purchases, retained 0.00 USD opening and 114.00 USD closing amounts owed, and showed Balances agree with a zero difference. No browser errors. The supplied page produced the same two balances and two purchases, while flagging the OCR date disagreement. No real PDF or real import was changed. The guide was regenerated without opening a documentation panel. Local evidence is data/local-runtime/merrick-summary-acceptance.json. No full suite or public push was run.

## Completed locally: report packages and full-document OCR follow-up, 13 September 2026

- [x] Prepare a review package from a saved ledger ZIP without requiring a tracing scenario. Optional scenarios and paired extraction-validation inputs remain available. Empty selections, other cases, damaged archives and failed audit recording are rejected.
- [x] Provide visible choose buttons, selected filenames and clear-selection actions for package files and verification. The verification screen accepts review packages as well as tracing audit packages.
- [x] Show retained ledger processing versions, import/review counts and attributed custody reports in the readable package index. Preserve source and ledger bytes. Missing historical fields remain unknown; source custody reports are not duplicated when wider case custody is present.
- [x] Show investigation transaction counts and exact per-currency totals alongside separately verified counts. Credit-card debits are explained as increasing amounts owed. Existing saved-package rebuilds retain their earlier index format through an explicit manifest option.
- [x] Run local OCR on the entire supplied 56-page Merrick document without changing its bytes or imports. The layout check recognised 42 statements and located both summary controls in each. It flagged 22 unreadable/suspect balance controls and 10 date conflicts among 235 proposed transaction-section rows. These are layout and exception counts, not independently measured extraction accuracy.
- [x] Treat OCR box-border brackets as decoration when locating the summary heading. Flag a missing dollar marker because OCR can read it as a leading 3. Never remove a leading digit to repair the value. Bump statement-review to v3 so an older open proposal requires reloading before confirmation.

Validation: the affected archive/router checks, 10 frontend package checks, focused OCR/import checks, type checking, scoped lint, guide generation and production build passed. No full suite was run. The local browser downloaded a ledger-only package from the synthetic Merrick case, verified its saved digest and rebuilt it successfully. Original ledger/source files were retained unchanged. The readable summary was inspected at desktop and mobile widths, including exact large-amount formatting and distinct investigation/verified counts. Local records: data/local-runtime/ledger-only-package-final-acceptance.json and data/local-runtime/merrick-document-layout-summary.json.

The independent reference corpus, exact Capital One 8160 source and working external provider acceptance remain unavailable. The package can carry linked measurements but cannot manufacture independent reviews or missing historical custody. These acceptance requirements remain open, and no public push has occurred.


## Completed locally: payment signs and unresolved import values, 13 September 2026

- [x] Read Merrick's trailing minus as part of the printed amount. A separately extracted minus must be beside that amount on the same measured line. Preserve all original cells and reject conflicting or misplaced signs.
- [x] Require the two printed decimal places on Merrick transaction amounts. Missing punctuation and unreadable digits require correction; never turn an OCR reading of 275 into an assumed 275.00 or insert a guessed decimal point.
- [x] Flag a card-payment description when its expected minus is missing. Retain the amount but leave Credit/Debit unresolved. Recognise digit-containing bank references split by OCR spaces without removing ordinary uppercase description words.
- [x] Keep unknown amounts and credit/debit choices blank in the review form and its saved draft. Require an explicit direction in the confirmation API, mark incomplete totals, and withhold the balance comparison until included amounts and directions are available.
- [x] Save the latest draft on page exit and when the page is hidden, so a quick refresh cannot outrun the delayed save timer. The immediate-refresh browser check exposed this defect before the fix.
- [x] Open balance corrections without exposing every statement heading as an empty editing row. Excluded source rows remain available through the explicit Show excluded rows control. Keep horizontal scrolling inside the correction table so focusing a balance does not clip the surrounding instructions.
- [x] Increment the proposal reader to statement-review-v4 so older open proposals require reloading. Existing imports and original PDFs are unchanged.

Validation: 40 affected backend checks and 18 frontend checks passed across focused runs, along with TypeScript, scoped lint, guide generation and the final production build. No full suite was run. The retained 56-page Merrick OCR results were reinterpreted locally, without another OCR run: 42 statements, 16 resolved detached payment minus signs, four missing-payment-sign exceptions and eight amount/decimal exceptions. Direct PDF inspection confirmed the separated minus and the printed 2.75 value previously read as 275. These checks are not independent accuracy measurements. Private receipt: data/local-runtime/merrick-payment-sign-check.json.

The local browser uploaded a new synthetic statement, recorded its trailing-minus 14.00 credit and 100.00 charge, confirmed once and showed 86.00 owed with agreeing balances. A separate, explicitly simulated missing-direction API response verified empty Credit/Debit fields, blocked incomplete confirmation, immediate-refresh draft recovery and corrected balance arithmetic, without altering saved extraction data or making a second import. Its receipt is data/local-runtime/unresolved-review-browser-acceptance.json. Original statement cells, PDFs and all real imports remain unchanged. User instructions were updated without opening documentation panels.

The independent reference corpus, missing exact Capital One 8160 file, working external provider acceptance and associated full expert-packet acceptance remain open. No public push was performed.


## Completed locally: readable fields and faithful printed columns, 14 September 2026

- [x] Retain a Merrick row's description, bank reference and readable amount when only its date is damaged. Require exact printed headers and matching page/row positions; keep the date blank and the row flagged until a reviewed correction.
- [x] Preserve the original damaged date and all original cells through a date-only correction and confirmed import. Increment the reader to statement-review-v5 so stale proposals require reloading.
- [x] Preserve the printed blank reference heading, split description text and separated amount sign. Each piece keeps its own PDF link. Keep damaged numeric dates under Date and leave conflicting amount pieces available for review.
- [x] Keep year-to-date summaries and following page text out of the transaction grid while retaining access under Other extracted page text.
- [x] Complete a synthetic upload, correction, import and balance check in the local browser, then read back the saved original/corrected values. Verify exact date, description and sign highlights and the final table layout. Update the user guide without opening documentation panels.

Validation: 36 affected backend checks and 18 frontend checks across targeted runs, TypeScript, scoped ESLint, guide generation and production build passed. No full suite. The synthetic statement deliberately printed O4/22: only the date was corrected, exactly two payments were imported and 86.00 USD owed reconciled. The original damaged reading, reference and amount remain recorded. Local receipt: data/local-runtime/merrick-date-acceptance.json.

The retained 56-page Merrick OCR comparison recognised 42 statements and kept 235 proposed rows. All 94 unresolved date rows now retain their descriptions; 88 also retain readable amounts. Previously supplied dates and fields are unchanged. All 7,466 nonblank source cells remain accessible in the printed-table check; transaction cells outside reconstructed tables fell from 443 to 9. These are layout-retention counts, not independent accuracy measurements. No further OCR or external-provider call, real-source edits or real imports occurred. Private checks: data/local-runtime/merrick-date-retained-check.json and merrick-printed-layout-check.json.

Independent reference labels, the missing exact Capital One 8160 document, external-provider acceptance and the remaining original expert-packet acceptance stay open. No public push was performed.


## Completed locally: Capital One fees and separate date corrections, 14 September 2026

- [x] Read Capital One fee tables with both Trans Date and Post Date, as well as the older Date layout. Keep both date sources, reject ambiguous headers, and leave undated interest flagged.
- [x] Retain the holder named in the selected card's printed section headings even when the statement contains only fees or interest.
- [x] Offer separate transaction, posting and value date corrections for date roles identified in the source. Preserve the main date's meaning, require reasons for changes or clearing an additional date, and retain original readings with the corrected ledger dates.
- [x] Save separate date edits in the browser-tab draft, including a cleared additional date. Confirmed correction history retains the distinct date changes. Reader version is statement-review-v6 so stale reviews must reload.
- [x] Verify a complete synthetic upload, posting-date edit, immediate refresh, confirmation and imported balance check. Update the guide and saved development state.

Validation: 40 affected backend checks and 17 frontend checks passed, plus TypeScript, scoped ESLint, guide generation and production build. No full suite. The final browser check imported one 25.00 USD fee, preserved transaction date 8 March, saved the deliberately corrected posting date 10 March and retained the original posting date 9 March. Draft recovery, exact posting-cell highlight and a zero balance difference passed. Read-only database verification confirms both original and corrected dates. Local receipt: data/local-runtime/capital-dates-final-acceptance.json. The first synthetic fixture had misaligned summary amounts; its missing-closing-balance result was preserved, and the corrected fixture was a new file and case.

The retained real-file comparison now fills four previously unresolved fee rows on pages 57, 81, 87 and 91. All earlier money/date readings are unchanged. The selected 27 statement periods still contain 42 proposed rows, including 19 undated interest rows requiring review. No date was guessed, no real import or PDF changed, and no further OCR/provider call occurred. This is not independent corpus validation. Local record: data/local-runtime/capital-fee-comparison.json. Broader acceptance requirements remain open. No public push was performed.


## Completed locally: readable tracing reports and supplied secured-card statements, 14 September 2026

- [x] Include a readable report for each selected tracing scenario in the review package, with saved reasons, payment order, transfer choices, per-method results, asset/resale allocations and links to captured payments and source references.
- [x] Retain original scenario bytes and separately hash the reports. Preserve older package rebuilds through an optional versioned report flag; reject unknown versions and identify altered derived reports.
- [x] Split other recorded funds from unidentified/unfunded asset portions in both readable report paths so the same money is not shown twice in additive categories.
- [x] Inspect the exact Capital One source from the earlier screenshot and verify its three transactions through a fresh local upload and browser review, without importing real payments.
- [x] Recognise exact Secured Card and Platinum Secured Card headings in both layout and period detection. The supplied collection now identifies 52 periods instead of 7. Preserve conflicting/damaged headers as unresolved.

Validation: 57 package/report/router backend checks, 21 statement checks, 13 frontend checks, TypeScript, scoped lint, guide generation and build passed. Browser package assembly, independent rebuild, desktop/mobile readable reports and the exact statement-page review passed. No full suite or public push. The supplied Andrews multi-share statements and buyer-wire document remain unsupported automatic formats; independent measurements and full original expert-packet acceptance remain open.


## Completed locally: Andrews savings and checking sections, 15 September 2026

- [x] Recognise supported Andrews savings/checking sections and group only supported continuation pages. Keep different shares and repeated statement copies separate.
- [x] Retain exact original fields and wrapped descriptions; read amounts/balances independently and flag OCR damage, uncertain date meanings, sign conflicts and balance differences.
- [x] Compare physical account sections for overlapping imports so separate accounts on one PDF page can both be imported. Preserve duplicate/replacement protection when a reread renumbers rows; require review when positions cannot be compared.
- [x] Record savings/checking account types and original balance sources. Save a statement without payments only when its opening/closing balances match; prevent empty imports from hiding proposed transactions.
- [x] Show unheaded original rows in measured positions with source highlights, without inventing headers. Retain unlocated text and keep dates/amounts on one line.
- [x] Check two-account persistence with synthetic data and the smaller supplied PDF through real upload, separate-share selection, source clicks and page navigation. Update the user guide.
- [ ] Extend supported source layouts beyond BASE SHARE SAVINGS and FREE CHECKING, and address the remaining unreadable/conflicting sections in the larger file.
- [x] Add a separate interpretation for the supplied wire-detail report, preserving its sending/receiving parties, value date and redacted references without treating it as an account statement. Completed in the wire-review work below.

Validation: 75 unique affected backend checks and 23 affected frontend checks passed, plus TypeScript, scoped lint, guide generation and production build. No full suite or public push. The local browser case shows 15 account/period choices and 7 first-savings payments; no real transactions were imported. A separate synthetic browser import saved a no-payment statement and opened Review accounts automatically. Native comparisons recognise 33 sections in the 99-page file and 15 in the 24-page file, with unresolved rows/coverage explicitly retained. These are not accuracy measurements. A two-page local OCR reread recovered one share heading but introduced other numerical errors, so it is not an unconditional improvement. Private receipts remain under data/local-runtime. Independent reviewed labels, measured release acceptance and applicable original expert-packet acceptance remain open.


## Completed locally: Andrews continuation coverage and printed page order, 15 September 2026

- [x] Continue an established statement when its next page has readable matching account/period details but no readable logo. Keep unidentified starting pages and conflicting headings separate.
- [x] Read spaces around signs and decimal points without changing digits or original text. Keep damaged letters and ambiguous monetary fields flagged.
- [x] Read complete, uniquely numbered page blocks in their printed order when the original PDF has those pages out of order. Save transaction order and original PDF locations separately. Do not invent missing page numbers.
- [x] Start review on the first statement page and explain original PDF navigation. Remove the misleading missing-position message from whole-page browsing.
- [x] Verify a fresh 99-page local upload, source highlighting, original page navigation and the December section. Confirm saved order and source pages with synthetic data; update the guide.

Validation: 21 focused backend and 19 source-view frontend checks, TypeScript, scoped lint, guide generation and production build passed. No full suite or public push. The larger supplied file now has 37 recognised sections and 1,950 proposed rows, up from 33 sections and 1,221 rows at the initial Andrews checkpoint. The smaller file retains 381 proposed rows, with additional amounts and balances read. No previously populated date, amount, direction or balance changed. The fresh browser case shows 95 October payments and 142 December payments in printed statement order. No real payments were imported. These are detection and local verification counts, not independent accuracy measurements. Unsupported account sections, documentary wire/receipt support and the existing independent acceptance requirements remain open.

## Completed locally: wire reports as supporting financial documents, 15 September 2026

The supplied Wells Fargo wire-detail PDF describes one payment and includes party details, a value date, process information and redacted/unreadable references. It is not a bank statement with a statement period and opening/closing balances. Do not force it through the statement transaction table or automatically add another payment to account totals.

Planned user process:
- [x] Recognise a supported wire-detail PDF when opened from the financial file list and show its original page beside labelled, editable details. Keep the original readings and highlighted PDF locations available.
- [x] Clearly flag unreadable currency, party labels, dates or references. Do not recover redacted values, substitute source digits or infer account ownership from the bank name.
- [x] Let the investigator save checked details and their observations as a financial finding, retaining original readings, corrections and reasons.
- [x] Offer matching imported payments by exact currency/amount and a bounded date window. Let the investigator choose a link and explain it. Matching suggestions never merge or add payments automatically.
- [x] Reopen the saved wire review and its original PDF from Findings, and carry the note and supporting links into the existing report process. Repeated saves with the same request must not create duplicate notes.
- [x] Keep case permissions, stale-source checks and private data boundaries intact. Check parser failures, persistence, matching/source links and the complete synthetic browser journey, then inspect the supplied PDF locally without adding real payments.

Implementation direction: reuse prepared PDF geometry and the existing Workspace entries/revisions for a saved finding. A wire evidence link holds the reviewed document; any linked payment uses its own original evidence link and financial transaction anchor so ledger exports remain consistent. Reuse existing source-view and report components. A dedicated document-review service/response avoids pretending the wire is an account statement. No new ledger transaction is created by saving a review.

Validation: 60 unique focused backend checks and 18 affected frontend checks passed, plus TypeScript, scoped lint, guide generation and the production build. No full suite or push. A fresh synthetic upload found a separate borderless-table defect: blank source cells shifted balances into payment columns. The v10 reader now uses printed column positions, retains original indices and flags ambiguous geometry. Known statement headings and balance controls are excluded from payments. A local browser import saved exactly one USD 120 payment with USD 100 opening and USD 220 closing balances.

The complete synthetic wire journey passed: upload, original PDF/highlight, currency and party correction reasons, explicit link to the existing payment, save in Findings, reopen, readable report and a ZIP with both byte-identical source PDFs. Database inspection confirms one ledger payment and one wire note with two separate evidence links. File-list review status and idempotent retry are covered. The supplied private wire was opened and inspected locally, with amount/date read and damaged currency/timestamp/party labels flagged; no real payment was imported and no real wire finding was saved. Other wire layouts, unreadable account sections, independent extraction measurements and applicable full expert-packet acceptance remain open.

## Completed locally: Andrews payment-share sections and closure notices, 15 September 2026

- [x] Recognise exact VISA PAYMENT share headings as a separate account, keeping its printed label and type Other. Do not identify it as a credit-card balance from its name.
- [x] Retain a matching printed closure notice and its date as account information, separate from transactions and balances. Reject a mismatched share or date.
- [x] Allow recording a no-payment closed account section while leaving an absent closing balance unknown. Retain its original closure source and make it visible again from the statement source. Prevent excluded payments from becoming a false empty statement.
- [x] Verify the additional sections in the supplied PDF and a complete synthetic closure save and source reopening. Preserve current savings/checking transactions and update the user guide.

Validation: 19 focused backend checks and 22 affected frontend checks passed, with three closure-specific backend checks repeated after final source-identity changes. TypeScript, scoped lint, guide generation and the production build passed. No full suite. The complete synthetic browser journey saved a no-payment account closure, reopened its original text and highlighted PDF location, and produced no console errors. Read-only database inspection confirms account type Other, opening balance zero, absent closing balance and zero transactions. The first browser attempt encountered a transient disabled login; the saved-account helper then needed the actual Review statements button before Open statement and balances. Reusing the saved synthetic case verified the final journey without duplicate imports.

The larger supplied Andrews PDF now has 43 recognised sections instead of 37, including six VISA PAYMENT sections. Its 1,950 proposed transaction rows and previously populated values are unchanged. The smaller PDF retains 15 sections and 381 proposed rows. The original page 83 closure notice was visually inspected, and the application displayed its 29 September 2021 closure date with a source highlight and no closing amount. No real payment or closure was imported. These are detection and source checks, not independent accuracy measurements. Private receipts stay under data/local-runtime. Other unsupported/damaged sections, independent reviewed extraction measurements and applicable original expert-packet acceptance remain open. No public push.

## Completed locally: spacing errors in Andrews headings, 15 September 2026

- [x] Accept extra OCR spaces within the fixed Account Statement and Previous Balance labels while preserving every original character and all numeric checks.
- [x] Keep a damaged share heading from assigning its rows to the previous account.
- [x] Verify the newly reachable continuation pages against the supplied PDF and check unchanged earlier readings.

Validation: 15 Andrews reader checks and 5 affected import checks passed. The guide regenerated; no frontend code changed, so no repeat frontend suite or production build was needed after the preceding successful build. No full suite. The larger supplied PDF now has 44 recognised account sections and 2,044 proposed payments, adding 94 rows with 93 readable amounts and 88 readable balances. All previously populated date/amount/direction/balance values are unchanged. The smaller PDF remains 15 sections and 381 rows. Seven sources in the larger PDF and six in the smaller still need classification or coverage review. Original cells are unchanged; these counts are not independent accuracy measurements.

Visual source checks compared 33 readable amount/balance pairs across pages 90 and 96. The application displays October's 80 payments, including 13 on its last page, and December's 96 payments across original pages 95 to 99. Source image/highlight and retained damaged-value flags passed with no console errors. Browser helpers were corrected after a development-server reload interrupted a read, and to select the original amount cell by its recorded column because the original text includes spaces. No real payments were imported and no further OCR or provider request was made. Private receipts remain under data/local-runtime. No push.
