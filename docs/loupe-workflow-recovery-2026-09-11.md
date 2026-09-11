# Financial workflow: requirements recovery and implementation audit

11 September 2026. Inspected against commit 7ea627a5. This is a source-code and
saved-requirements audit, not a new browser acceptance result. No server case or
financial record was changed during this audit.

## What governs the correction

Neil asked for the existing requirements to be recovered rather than another
invented product proposal. His latest clarification is that the original statement
comparison is valuable, but it offers no apparent action. The review must let the
investigator do something with the displayed values.

The following sources have different authority:

- `CLAUDE.md`, Design rules already settled, and `docs/financial-handoff.md`,
  Design rules already settled: recorded user directions. Flag suspect fields, show their source,
  allow confirmation or correction, preserve both values and use the correction
  in calculations. Do not invent relationships between documents delivered together.
- `bundle/docs/10-loupe-integration-and-store-design.md`, sections 8 and 12:
  recorded decisions. The user controls grouping and filtering; the record retains
  verification information. Postgres holds the financial record, with graph views
  derived from it. This supersedes the recommendations in document 09.
- `bundle/docs/11-v1-learnings-into-loupe.md`, sections 1 and 6: the saved analysis
  of capabilities worth retaining, including entity perspective, incoming/outgoing
  charts, review before applying proposed changes and safe re-extraction.
- `bundle/docs/13-target-state-financial-forensics.md`, sections 4, 5 and 10:
  the detailed target for extraction, balance checks and analytical views. Its
  introduction explicitly says it is an unconstrained target, not a schedule.
  Do not present every sentence as a verbatim instruction from Neil.
- `bundle/docs/14-gap-analysis-and-roadmap.md`: original dependency sequence.
  `docs/loupe-wiring-plan.md` and the later handover record subsequent wiring work.
- `docs/loupe-ui-acceptance.md`: later implementation checklist. Its checked boxes
  describe local and often synthetic checks. They do not override the requirements
  or establish that the whole application works for a new user and a fresh statement.

## What went wrong

A manual, selected-row PDF recovery workflow became the normal statement workflow.
An investigator must operate several intermediate representations before the
application has transactions to analyse. The analytical features were then tested
with prepared or separately populated cases. Those checks established useful
individual capabilities but did not close the gap between uploading a statement
and investigating its complete contents.

The current source confirms the distinction:

1. `PdfReviewIntake.tsx` uploads and prepares a PDF, then opens source selection.
2. `CandidateSourcePicker.tsx` starts with no rows selected and no column meanings.
   It saves only explicitly selected rows as a mapping. Clicking source cells
   highlights them; it does not edit their interpreted transaction values.
3. `PdfCandidatesPanel.tsx` lists saved batches. A user opens a batch and then an
   individual reading to reach `CandidateReviewForm.tsx`.
4. That form has editable amounts, direction, dates, description and counterparty,
   account selection, and resolved/rejected/reopened decisions. These capabilities
   exist, but are separated from the first comparison table and use internal terms.
5. `CandidateFinalizationPanel.tsx` is a further operation. The backend's
   `candidate_materialization.py` explicitly describes selected rows with
   unverified whole-file coverage and prevents later additions after finalization.
   The preview reports P3 and exclusion from default verified totals. This is not
   a complete-statement import contract.
6. `FinancialPage.tsx` puts proof status, document comparisons and PDF preparation
   above the ledger. `CorrectableLedger.tsx` then puts coverage, two summaries,
   export and trends before the transaction table. This explains the long screen
   of controls in Neil's screenshot.
7. Ledger and Transactions both mount `CorrectableLedger`. Counterparties, trends,
   transfers and patterns each have separate controls and scopes. The user is
   responsible for connecting these views and their selections.

The screenshot's single candidate is evidence of a one-row saved batch. It does
not establish that only one row was extracted, nor that the whole file has been
imported. The interface must make those counts distinct without requiring the user
to understand mappings, candidates or finalization.

## Requirement compared with current implementation

| Requirement | What exists | Gap to close |
| --- | --- | --- |
| Process a complete statement into reviewable transactions | PDF preparation, source cells, row suggestions, saved readings | No single complete-statement workflow joining these stages. Account details, controls and all transaction pages need a common review result. |
| Act on a value while comparing it with the original | Measured highlights and a separate review form | Put editable transaction fields and clear Save correction, Confirm and Exclude actions in the same review. Keep original text unchanged. Explain why an action is unavailable. |
| Correct omissions and non-transaction rows | Manual row selection and rejection | Make excluded headings/balances visible as such; provide a source-linked route for missed transactions. Do not treat opening balance as money received. |
| Check statement completeness and arithmetic | Statement scopes, balance checks, coverage and reconciliation services | Integrate checks with the review and show the actual discrepancy. A balanced subset must not be called a complete statement. |
| Begin investigation with a useful financial view | Filterable ledger and source links, summary/trend components | Make transactions and account context the main working area. Keep preparation and detailed history available without putting them ahead of every investigation. |
| Select parties and see money in, out and internal movement | Source-label/identity charts and explicit account-transfer scenarios | The saved design calls for a shared entity perspective. Account-pair scenarios are not a complete substitute. Selection and population need to follow the user across relevant views. |
| Follow connections and inspect supporting evidence | Posting graph, paired account diagram, source dialogs | Preserve these capabilities and connect them to the current account/party/transaction selection. Do not infer that an extracted label proves identity or ownership. |
| Investigate patterns and relate transactions to case events | Bounded pattern screens, saved theories and case timeline | These are useful partial implementations. They do not establish the full target pattern catalogue or a connected workflow from a newly imported statement. |
| Export the investigation being viewed | Ledger reports, captured scenarios, source/history packages | Verify a report produced from the same reviewed statement and filters through the ordinary UI. Separate capture mechanics from the main investigation controls. |
| Reprocess without destroying work | Preserved source bytes and review histories; preparation skips processed files | A safe new extraction version with comparison and explicit replacement remains needed. Re-uploading into another case is a workaround, not completion. |

## Correction order and acceptance

These are implementation steps derived from the recovered requirements. They are
not assertions that Neil approved a new visual mockup. Preserve the existing Loupe
shell and persistent Financial guide modal.

1. [x] Complete statement review in one place.
   - Prepare a statement and open a transaction table beside its original PDF.
   - Show account, currency, period, opening/closing controls and page coverage.
   - Offer proposed column meanings and transaction rows for review. Preserve
     uncertainty; no bank-specific assumption based only on the Nexus fixture.
   - Edit/confirm fields, exclude non-transactions and recover missed rows within
     this review. Show what was saved and the next unresolved issue.
2. [x] Connect review to the financial record.
   - Show complete transaction count, exclusions, balance check and unresolved
     problems before committing the import.
   - Preserve original readings and individual changes with actor and reason.
   - Prevent duplicate additions and partial success being described as complete.
   - Do not promote verification merely to make totals appear.
3. [x] Make the financial record the main investigation screen.
   - Put the table, understandable account names, dates and money totals first.
   - Provide visible account/date/search/reliability filters and source actions.
   - Move preparation, detailed verification history and document comparison into
     appropriate secondary panels while retaining their functionality.
   - Remove the confusing duplication between Ledger and Transactions.
4. [x] Connect the analytical views to that record and selection.
   - Reuse the existing charts, transfers, graph, timeline and tracing calculations.
   - Carry account/party/date scope and verification selection consistently.
   - Restore the saved incoming/outgoing/internal entity perspective behaviour.
   - Check corrections flow through every applicable calculation and export.
5. [x] Add safe reprocessing of an existing statement.
   - Keep the previous extraction and review history, compare versions, and make
     replacement explicit. Do not overwrite finalized source mappings in place.
6. [x] Prove the whole journey through normal application controls.
   - Fresh Nexus PDF: all 12 payments, six credits, six debits, all 13 printed
     balances; header and opening balance excluded from transaction counts.
   - Deliberately correct a field and verify original/history preservation.
   - Import, reload and see the same transactions; chart and export the same scope.
   - Repeat on the supplied real multi-page documents in isolated copies.
   - Include a missing-row/balance discrepancy and interrupted/resumed import.
   - No database seeding or direct API review scripts may substitute for the
     acceptance of the user-facing journey.

## What is retained

The extraction repair, exact monetary calculations, source rectangles, review
history, correction handling, reconciliation, analytical components and export
checks are existing work to reuse. Their tests remain valuable regression checks.
They are not evidence that the workflow items above are complete.

No new completion date is inferred from test counts or number of components.
The first acceptance boundary is the ordinary statement-to-investigation journey,
not another isolated control or a screenshot of a pre-populated case.

## Active recovery implementation, 11 September 2026

Work remains local and is not ready to push. The revised workflow is being tested through actual user controls, rather than judged from separately populated analysis fixtures.

Completed checks in the current implementation:

- [x] Nexus PDF uploaded in an isolated UI-created case, automatically prepared, reviewed with the PDF visible, and imported with one confirmation. All 12 transactions survive reload.
- [x] An existing active import cannot be imported twice through the review screen.
- [x] Reprocessing creates retained source history. The existing import stays active until explicit replacement. Browser replacement test leaves exactly 12 active transactions after reload.
- [x] Editable dates, descriptions, amounts, directions, balances and explanations are part of the import review. A missed row can be added with an original page citation.
- [x] Transactions is the initial financial tab. Compact account/date filters and totals precede the transaction table; download options follow it.
- [x] 1,022 financial frontend tests passed before the subsequent statement-collection changes. The later changes require a new run.
- [x] The real 108-page PDF is recognised as 27 separate printed billing periods. Unknown pages remain separately identified.
- [x] The first real card period yields its payment, purchase and undated interest charge. The missing interest date remains an explicit exception. No real-fixture import was performed.
- [x] A persistence test imports two periods from one PDF separately and checks idempotent retries and six stored transactions.

Remaining acceptance work includes collection review in the browser; the second real PDF layout; missing/unclassified page handling; credit-card interpretation and balance controls; durable review recovery; source corrections after import; counterparties, transfers, patterns, notes and report continuity; permission tests; guide revisions; and the final complete regression/build checks. Earlier test counts do not establish completion of these items.

Local fixture references for safe continuation: `data/local-runtime/statement-import-acceptance.json` records the new synthetic case and reprocessed version. Do not rerun writers against the older real PDF fixtures. `scripts/check_local_statement_import.cjs` and `scripts/check_local_statement_reprocessing.cjs` have repeat guards for the isolated synthetic case.

### Integration progress at 05:50 Dublin, 11 September

The list above is retained as the earlier checkpoint. Subsequent completed work:

- [x] Full transaction corrections after import retain original readings and append the replacement. The browser check changed a synthetic description, checked it, and restored it through another recorded correction; 12 current payments remained throughout.
- [x] Investigator notes save through Workspace and reopen from their transaction link. Notes and linked source references are included in exported reports.
- [x] The supplied 56-page scanned PDF was freshly uploaded through normal controls in an isolated case. Its 42 statement choices appeared; the first two dated payments were confirmed once and survived reload. Unassigned pages and unclear printed dates remain visible.
- [x] Account/date selection follows Transactions, Counterparties, Trends, Posting graph, Patterns and Case context. Transfers shares dates while explicitly retaining all accounts for two-sided comparison.
- [x] The Statements account directory displays holder, number, bank and currency. Browser acceptance confirmed that its account action opens all 12 synthetic payments.
- [x] Statement balance checks and date coverage load on opening Statements. Both requests succeeded in the browser acceptance case.
- [x] Reprocessing stores its request and job in the current browser tab. A real UI reread was interrupted by refreshing, resumed the same job, opened replacement review and left all 12 current transactions unchanged without confirmation.
- [x] Reprocessing refuses a reading overlapping multiple active imports rather than choosing one replacement and potentially double-counting the remainder.
- [x] Opening and explicit closing controls are retained separately from payment rows. A persistence check confirms that an explicit closing balance does not increase the payment count.
- [x] The revised beginner guide opens from the persistent modal. Browser checks resolved every contents anchor and guide image.
- [x] Current synthetic report archive passed all declared-member digest checks, including the bundled original source PDFs. Initial report pages were rendered and visually inspected.

Still in progress at this checkpoint:

- [x] Finish the freshly uploaded 108-page card journey, including the undated charge decision and retained source. Completed through normal controls; two dated payments retained after reload, undated interest excluded with a recorded reason.
- [x] Verify the final report table presentation after aligning its credit, debit and printed-balance columns with the investigation screen. Final archive verified and rendered table inspected.
- [x] Finish remaining account-group, missing-row/discrepancy and interruption edge-case review against the recovered requirements. Account group and analysis population survive tab changes; live balance feedback and a source-cited manual replacement were exercised through normal controls.
- [x] Review all source changes together, update screenshots where needed, and run the final build and regression checks at readiness. Build, scoped lint and the recorded regression/acceptance checks passed.
- [x] Commit the completed work with detailed explanations. Backend: a643c742; manual sequence safeguard: cf9e2798; investigation UI: df902b31. Guide and completion record are included in the accompanying documentation commit. Nothing has been pushed.

Significant integration checks in this segment: 55 related frontend checks passed after updating one expectation for automatic loading; 41 backend import/catalog/report checks passed. These checks supplement the browser journeys; they are not a claim that the whole financial work is complete. Tests are being reserved for meaningful integration points in line with the user's instruction.


### Ready-for-push verification, 11 September 2026

The six correction steps are now marked complete against the recovered practical workflow. This closes the workflow gap identified in Neil's screenshots, not the unconstrained target catalogue in bundle document 13. Earlier checkpoints above remain as dated history.

- [x] Synthetic statement: 12 current transactions, six credits, six debits, all printed running balances, separate opening balance, unchanged original PDF.
- [x] Fresh 56-page scanned file: 42 statement choices; selected period's two dated payments imported and retained after reload.
- [x] Fresh 108-page file: 27 printed statement periods; selected period's two dated payments imported, with the undated interest charge excluded and its reason retained. Reopening the statement displays that recorded decision rather than presenting its original proposal as the current import.
- [x] Manual-row recovery: excluded one synthetic extraction and re-entered the same printed payment with a page citation and reason. Replacement retained exactly 12 current payments and the expected balance after reload.
- [x] Changing selected payments recalculates the comparison with available opening/ending controls immediately. A difference stays visible before confirmation. This is not a completeness guarantee.
- [x] Shared account/date selection, account-group selection and working/verified analysis selection retain their documented scope across tabs. Transactions remains the full current record with its own table filters.
- [x] Final report table shows dates, descriptions, separate credits/debits, printed balances and source references. Notes and retained original/version history remain in the export. File-member digests checked and rendered layout inspected.
- [x] Production frontend build passed. Financial frontend regression: 117 files, 1,038 checks passed. The final shared-analysis adjustment passed its 11 affected checks and browser navigation check.
- [x] Backend financial regression ran 4,428 checks. Six failures were obsolete report heading/punctuation expectations; corrected expectations and 105 affected import/report checks passed. The whole backend suite was not repeated for wording changes.
- [x] Combined changed financial frontend files passed ESLint. Remote fetch completed; no remote commits were missing locally.

Persistent acceptance records are under data/local-runtime: statement-import-acceptance.json, statement-field-correction-acceptance.json, statement-investigation-acceptance.json, fresh-real-statement-upload.json, fresh-capital-one-upload.json, statement-reprocessing-recovery.json and manual-row-acceptance.json. Real originals and older acceptance cases were retained.

Known product boundaries remain explicit: statements with unreadable dates or unassigned pages need review; a multi-statement PDF is reviewed one printed statement at a time; automatic review is bounded to 500 pages and 1,000 prepared rows per statement and refuses excess rather than truncating it. Browser-tab recovery does not survive closing that tab. No external AI key is required for this local PDF preparation/review/import flow. These boundaries are not silently labelled complete extraction or independently verified financial evidence.

No deployment has been triggered. Local commits are prepared separately from the push that starts the user's server deployment.


Final review safeguard: manually entered rows carry a page citation, not a confirmed printed row position. Sequential running-balance comparisons now return that explicit limitation instead of treating append order as source order. Transaction totals and the review's aggregate balance comparison remain available. All 15 correction/statement balance checks passed after this safeguard. This is documented in the user guide.

### User test corrections, 11 September, morning (local, not deployed)

The user's live test exposed failures in presentation and navigation that the earlier readiness record did not cover adequately. These reopen UI acceptance rather than erase the earlier checks.

- [x] Replace the native unstyled file picker with a proper Choose PDF button, selected filename, and Change PDF action. Put fresh upload before existing-file discovery.
- [x] Keep the transaction workspace mounted when switching financial tabs and modes, with inactive content hidden. Key statement review to the case so another case does not inherit it. This preserves the File object, upload job, selected statement and mounted corrections during these transitions.
- [x] Display the original PDF by default beside a table built from stored source cells. Preserve printed text, dates, currency formatting, column indices, blank cells and row order. Keep the opening balance visible in this source view without importing it as a payment.
- [x] Move corrections and import choices into separate controls. The printed source table does not show inferred counterparties or internal direction fields. Correction controls use Credit and Debit amounts.
- [x] Move the source comparison ahead of account forms and import summaries so it is visible near the start of review.
- [x] Local browser acceptance on the existing synthetic case, with API writes blocked after login: PDF loaded beside the extracted printed table; selected statement retained after visiting Statements and returning to Transactions. Screenshot: /tmp/loupe-printed-review.png.
- [x] FinancialPage checks: 38 passed, including selected File preservation across tabs and transaction modes. Printed table and statement review checks: 7 passed. Intake checks: 3 passed before the final button appearance change. TypeScript passed after final layout formatting. Full suite not run.
- [ ] Deploy these corrections and repeat the user's live journey. No deployment of this batch has occurred.

Report work was interrupted to prioritize the user's defects. The local expert-support index now describes captured statement confirmations, checks their stored hashes, and exposes source custody reports. Expanding a separate outer ledger index remains unfinished; the trial addition was removed because historical partial captures need explicit compatibility handling. Do not mark the whole expert packet complete.

### Report support continuation after 22e73b7d (local, not deployed)

- [x] Expose the original saved ledger expert-support JSON directly from assembled review packages. Copy its bytes unchanged and retain the entire original ledger ZIP. Older exports without support remain accepted without inventing an index.
- [x] Validate the support file's internal case and snapshot binding as well as its declared member hash before reuse. Separate original capture scope from newly selected tracing scenarios.
- [x] Surface the PDF processing manifests already retained by normal statement imports in expert-support versions. Validate nested manifest hashes, preserve missing historical manifests as not recorded, and show saved Python/PDF/OCR versions in the readable scenario report.
- [x] Update the beginner guide for Choose PDF, printed statement comparison, separate corrections, Credit/Debit inputs, and saved package support links. Replace the previous review screenshot with the checked synthetic printed-layout screen. Rebuilt portable HTML and in-platform guide: 13,194 words, 12 image uses, no em dashes.
- [x] Relevant integration checks: 31 export comparison, archive support and statement provenance checks passed. No full suite run.
- [ ] Finish original expert-packet acceptance against applicable case custody/decision scope and independently reviewed extraction measurements. These improvements do not establish independent ground truth or complete historical records.

### Statement file workspace requested during live testing (local, not deployed)

- [x] Add a visible Edit import values action above the viewer. Already-imported statements have an Edit imported transactions action leading to current ledger correction controls; original source readings remain separate.
- [x] Add Previous page, Next page and direct page selection. PDF and extracted printed table use the same page. Start at the selected statement's own first page, retain page choices during the session, and explain when a page has no extracted rows in that selected statement.
- [x] Replace the empty Details view in the financial right-hand panel with Statements, including searchable PDF filenames, creation identifiers, processing status and direct viewer selection. Other case sections retain Details. A Statement files button opens the panel.
- [x] Add bulk selection of up to 20 PDFs. Upload and request local preparation per file, retain per-file failures without automatic duplicate retries, and keep queue state outside the mounted panel. Stop unsent work if the signed-in user changes. Each import still requires its own review/confirmation.
- [x] Keep user/case/file statement-period choices separate. Flush the review draft when leaving a file so switching within the former 300 ms debounce does not lose an edit. Restore the draft on returning to the same statement revision.
- [x] Local browser acceptance created isolated case 0230dbcb-d5a0-4e1a-a3d2-3e285788398c with two synthetic PDFs from one selection. Both reached ready status, both opened from the sidebar, and an unconfirmed description correction survived switching files and returning. No financial import was confirmed. Persistent acceptance: data/local-runtime/statement-file-list-acceptance.json.
- [x] Read-only existing 108-page PDF acceptance: choose the first statement and its recorded USD currency, open at page 3, next to page 4, previous to page 3, and return from another financial tab with page 3 retained. The initial automation timeout was caused by skipping the required currency choice, not a page-navigation failure.
- [x] 47 affected checks passed at integration; after adding pagination coverage and opening imported originals directly, all seven statement-review checks passed. TypeScript, scoped ESLint and production build passed. Existing bundle-size warning remains. No full suite run.
- [x] Update the beginner guide for bulk uploads, file-list switching, page controls and visible editing actions. Queue/page choices are session state, not resumable after closing the browser; uploaded files remain server records.
- [ ] Push and verify this new file-workspace batch on the deployed server.

### Existing statement reading recovery

- [x] Add Read statement for existing unprocessed PDFs in the Statements sidebar.
- [x] Add Retry reading for failed PDFs, reusing the existing file ID instead of uploading a duplicate.
- [x] Disable reading while the request is pending; refresh file status after success or failure. Do not automatically retry uncertain requests.
- [x] Keep processing/queued files unavailable for restart from the sidebar.
- [x] Stop polling merely because an idle unprocessed file exists. Continue polling active jobs and files queued by the upload workspace.
- [x] Update the beginner guide and regenerate its in-app and portable copies.
- [x] Focused validation: three file recovery UI tests, TypeScript and scoped ESLint passed. Full suite not run for this change.
- [ ] Push this follow-up and verify deployed recovery with a failed or unprocessed statement. These changes are local at this checkpoint.

### Product-wide assessment after user testing

- [x] Recorded findings for all 13 tabs and cross-cutting statement intake, notes, reporting, navigation and help in `docs/loupe-financial-product-assessment-2026-09-11.md`.
- [x] Opened every tab in the local synthetic case; exercised read-only transfer/pattern/graph/timeline loading and note/correction entry points.
- [x] Reproduced lost pattern settings on tab change and discarded unsaved note text on dialog close.
- [x] Identified separate imported/graph datasets, hidden actions, disconnected findings/report workflow and raw text presented as faithful statement layout.
- [x] Recorded user requirement to separate statement review/confirmation from the investigation workspace.
- [ ] Check exact complex Capital One page shown by user against its proposed transaction import. A different local real-file proposal was inspected; it is not verification of that page.
- [ ] Implement the product corrections and complete the investigator acceptance script in the assessment. Earlier implementation checklist completion is not proof this script passes.

Provisional copy/layout changes were backed up under `/tmp/loupe-provisional-ui-backup-20260911` and removed after hash verification. No redesign changes were pushed. Existing local statement-file recovery work remains intact. Read-only audit results are in `/tmp/loupe-financial-audit.json` and `/tmp/loupe-financial-actions-audit.json`.


## Financial redesign release checkpoint, 11 September

The user requested a proper redesign plan and implementation. Read `docs/loupe-financial-redesign-plan.md` for the checked completion list, acceptance evidence and remaining real-PDF limits. Statements and Transactions are now separate workspaces. Findings saves payment selections, observations, transfer comparisons and tracing calculations; reports can include verified original PDFs. Main analysis results open the actual payments. Saved file import counts and periods are read from the case, rather than browser drafts.

Fresh local journeys covered import, correction, notes, selections, transfer comparison, single-account and three-account tracing, case-event links, report packages, another case member's access, and multipage navigation. The exact Capital One account ending 8160 from the screenshot is still unavailable; the supplied file ends in 3539. Scanned Merrick headings and dates with damaged OCR remain flagged for review. Do not describe that PDF as automatically reconstructed without errors.

The broad financial regression was run once at the integration milestone, with focused follow-ups for final changes. Do not restart the old development plan or rerun the full suite for ordinary copy edits. No database migration or private case-data upload is part of this release.

Release state, updated after explicit user approval: implementation commit `fee37455` and release-state commit `9b5a6b5c` were successfully pushed to the public `conorbowles51/owl-n4j` repository on `integration/evidence-main-reunion`. The user approved this exact destination after the automatic review requested explicit public-publication approval. Git confirmed the remote advanced from `424e859c` to `9b5a6b5c`, with local and remote synchronized. The earlier publishing block is resolved. Auto-deploy may now pick up the changes; server deployment completion has not been independently verified.
