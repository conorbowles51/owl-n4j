# Financial completion plan

15 September 2026. User deadline: a usable financial application tonight, Europe/Dublin. Five-minute continuation checks remain active through 23:59 today. The user explicitly rejected stopping at the earlier local ready checkpoint. The user will begin UI testing after travelling home. This is the current plan for finishing the financial work. It replaces the changing list of small next steps as the execution order. Earlier plans and their checked items remain as the development record. Completed work stays on this list.

The finished workflow is: upload statements and supporting payment documents, check flagged readings beside the originals, confirm a statement once, investigate the imported transactions, save observations and calculations, and produce a report another authorised investigator can reopen and check.

## 1. Finish the supplied statement and receipt formats

- [x] Read the supplied Capital One and Merrick layouts with their distinct dates, charges, credits and statement balances. Preserve damaged readings for review.
- [x] Read Andrews savings, checking and payment-share sections separately. Follow supported continuation pages and preserve original PDF locations and printed page order.
- [x] Preserve blank columns, account closure notices and statements with no payments without creating false transactions or balances.
- [x] Review the supplied Wells Fargo wire report separately, save checked details in Findings and optionally link an existing payment.
- [x] Finish the Andrews deposit receipt inside a multi-document PDF: selection, separate dates and balances, masked account reference, saved finding, optional payment link, original source and report inclusion. Verified with the supplied receipt on PDF page 42 and a synthetic statement plus two receipts; separate drafts, refresh, same-file payment link, saved source and exact-PDF report passed.
- [x] Account for every page in the eight supplied files: statement section, supporting receipt, application/terms, repeated copy, or an explicit unresolved page. Recorded all 567 pages (511 unique-file pages) in the private inventory and summarised them in loupe-supplied-statement-checks.md. Unresolved account/continuation pages remain explicit.
- [x] Check the remaining damaged account headings and missing continuation sequence. The local OCR retry recovers the smaller Andrews file's September savings section and two payments; damaged dates still need checking. Its processing request survived refresh. The larger file's missing predecessor remains flagged, opens at page 13 and has source/reprocessing/manual review controls. Use existing correction/reprocessing controls where they suffice; fix any path that loses original readings or leaves the user unable to finish the review. Unreadable identifiers remain unknown until the original supports a correction.

Done when: all supplied files can be opened; each recognised section can be reviewed independently; every remaining unreadable or missing item has a visible next action; source-only checks and synthetic imports prove that receipts, headings, balances and duplicate copies do not inflate transactions. This is not a promise that illegible source text can be recovered automatically.

## 2. Finish a complete investigation in one case

The following features are implemented. Final acceptance checks must use the same case so their interactions are checked rather than assuming separate tests prove the whole workflow.

- [x] Upload multiple PDFs, navigate the file list and pages, edit proposed values, confirm once and open Transactions.
- [x] Search/filter/select transactions; inspect the PDF; correct a value; exclude or restore a transaction; retain the history.
- [x] Inspect account holders, statement periods, missing dates and balances.
- [x] Investigate people/businesses, compare transfers, inspect patterns and trends, follow the graph and compare case events.
- [x] Save named transaction selections, notes, comparisons and tracing calculations in Findings.
- [x] Repeat the full journey after the new document support, including one correction propagating to totals, analysis and reports, and one receipt linked to an existing payment without duplication. One synthetic case covers nine payments, two accounts, three PDFs, a retained correction, failed-save recovery, selections, paired transfer, single/cross-account tracing and a five-finding report. Exact original PDFs verified.
- [x] Verify that an authorised second case member can reopen the saved work and original sources and that a read-only member cannot change it. The second member reopened/downloaded the same report; edit attempts and revoked reads returned 403. Temporary user removed.

Done when: an investigator can move from original evidence to a recorded observation and report without resorting to internal processing screens or losing their place.

## 3. Finish persistence and recovery checks

- [x] Separate statement review from the investigation table. Keep review state during financial tab changes.
- [x] Retain original readings and explained corrections; save confirmed imports, notes and calculations with the case.
- [x] Check unsaved and saved states for every active form: statement correction, receipt/wire review, transaction note, selected payments, transfer comparison and tracing inputs. Check financial tab changes, refresh and reopening a saved case.
- [x] Check interrupted upload/processing, failed saves, retry, reprocessing and replacement imports through the current UI. Reuse existing targeted failure tests, adding tests only for a newly exposed defect.
- [x] Fix misleading save messages, accidental reset, duplicate-save behaviour or missing recovery actions found in this pass.

Done when: a failed action preserves the user's work and gives a useful retry; a successful action remains available after reopening. Any unsaved browser-only state is clearly identified.

Recovery evidence: correction, receipt/wire, note, selection, transfer, single/cross-account tracing and indirect-workpaper drafts retain their values in browser-tab storage. Confirmed work reopens from the case. Same-case browser checks included a failed note save and refresh, changed transfer inputs, reprocessing and exact report reopening. The final frontend regression includes the targeted upload, retry and replacement-import failure tests. Browser-only drafts remain labelled; their calculations must be rerun after refresh.

## 4. Complete reports and the original evidence-package requirements

- [x] Build and reopen shared reports from saved findings and calculations, with selected transaction values and source references.
- [x] Include checked original PDFs, correction history, available source custody records, processing versions and saved tracing assumptions/results in the existing export paths.
- [x] Verify downloaded file hashes and replay supported tracing calculations from the saved inputs.
- [x] Map each original expert-package requirement to the actual exported field/file and its verification. Use a finite requirement table; do not treat historical checkpoint wording as a new feature request.
- [x] Implement any missing capture or report link revealed by that table. Include the new receipt review and distinguish original, corrected and unknown values.
- [x] Verify one combined package from the final case independently of the page that created it. Confirm selected scope, exact amounts, evidence links, retained versions and accessible readable output.

Verified mapping: [Financial export acceptance](loupe-financial-export-acceptance.md). The combined report retains five findings and three exact PDFs; the review package independently rebuilt eleven members and both tracing scenarios without changes. Missing historical and independent-review material remains explicitly unavailable.

Done when: every applicable requirement is either present and verified or explicitly records unavailable historical/source information. Software must not invent earlier custody, software versions or independent measurements that were never recorded. Genuine missing implementation stays unchecked.

## 5. Finish extraction validation and the release gate

- [x] Validate and reconcile two reader records, retain disagreements, bind predictions to source hashes and calculate exact extraction measurements.
- [x] Compare a measured run with an earlier run without substituting test counts for source accuracy.
- [x] Check the actual reader/prediction workflow against the supported formats and make the final run reproducible from its private input inventory and reader version.
- [ ] External acceptance: run the release check with approved independent reader records and a retained real baseline. The capture, reconciliation, pin checks and regression failure paths are implemented and tested. The seven-source private capture is ready, but no approved reader records or baseline are available. Do not substitute automatic proposals for those records.
- [x] Link available measurements into the evidence package with their real reviewer status and extraction versions.
- [ ] Obtain independent human reference reviews for a representative real corpus and run the resulting measurement. This is external acceptance work, not a reason to stop implementing the application or its validation tools.

Capture evidence: all seven distinct supplied PDFs captured using statement-review-v13 in a read-only transaction. Output file sizes and hashes verified; a pinned source rerun reproduced the same proposals and predictions. No payments imported. The release check now supports completely reviewed documents with no transactions, and fails when a candidate invents a payment on one. Eight focused capture/release tests passed before the final regression.

Done when: the software can run, retain and export the measured result reproducibly; the release record states exactly which real-source measurements are independently reviewed. External AI/provider validation remains separately identified if its configured credentials cannot authenticate. Local PDF and investigation development continues regardless.

## 6. Final user interface and documentation pass

- [x] Keep Statements, Transactions and Findings separate, with visible original-document actions and usable upload buttons.
- [x] Keep the Financial guide available in a modal and closed unless the user opens it.
- [x] Walk every financial area in the final case at laptop width with the right-hand file list both open and closed. Check page navigation, long values, errors, empty results and actionable controls.
- [x] Remove remaining internal terminology from the main workflow. Each screen must explain what it shows and the next useful action.
- [x] Update the step-by-step guide and synthetic images to the final buttons and process. Do not publish private statement screenshots.

Verification: all fourteen areas opened at 1440px with the file list open and closed (28 views), without JavaScript errors or page overflow. The final changed labels were captured again. Patterns, original-source dialogs, payment graph and timeline used the corrected nine-payment case. The guide has 22 synthetic images and passes all-tab visibility, contents, image, mobile, focus-return and unchanged-form checks.

Done when: every primary tab gives a recognisable investigation task, saved work can be found again, and the guide's instructions match the actual screen.

## 7. Final integration and ready-to-push checkpoint

- [x] Finish all required code changes from sections 1 to 6 and mark them with verification evidence in this plan.
- [x] Run the affected integration checks and one broad financial regression run at this final milestone. Fix failures and rerun only affected checks unless a new systemic concern justifies more.
- [x] Run type checking, scoped lint, the production build and migration/startup checks appropriate to the final diff.
- [x] Review exact changed paths, preserve unrelated work and exclude private PDFs, local records and credentials.
- [x] Commit with detailed explanations, record release notes and leave a verified build ready to push. The existing server deploys from the repository; there is no separate deployment implementation blocker.
- [ ] Push only when explicitly requested, then verify the deployed build through the user-visible workflow where server access permits.

Release evidence: [15 September release record](releases/2026-09-15-financial.md). One broad frontend run passed 1,146 tests. One broad backend run executed 4,583 tests and found missing package exports plus an ambiguous multi-period fixture; 43 affected tests passed after those fixes. Type checking, scoped lint, production build, clean backend startup and all fourteen local health/migration/case checks passed. The remote branch was fetched with no incoming changes. Private captures remain ignored and unrelated files remain untouched. The build is ready for the user's UI acceptance and an explicitly requested push. Independent human accuracy review and deployment acceptance remain unchecked.

## Continuing user workflow checks

The prior checked items stay as evidence. The user instructed continuous work after the local checkpoint; keep the schedule active until tonight or an explicit stop.

- [x] Make read-only financial controls match the server's exact case edit/upload permissions while preserving inspection, analysis and downloads.
- [x] Check the revised permissions with a real temporary read-only member and with separate edit/upload permissions.
- [x] Retain file, period, currency and page after refresh. The 222-page PDF check kept corrections separate between periods and original/reprocessed file versions, restored its source image and made no financial writes.
- [x] Add account/date/page search for large section lists. The supplied 52-section file can be narrowed to the requested period without changing PDF order.
- [x] Finish the large Andrews statement/receipt switching and unresolved-page review using the revised controls. Its 45-section chooser, missing continuation page 13, separate receipt page 42, refresh, search restoration and return to the statement passed without importing real transactions.
- [x] Check expired sessions and changing signed-in members while financial data is cached. Login/logout now clear the prior session cache; delayed old responses cannot clear a new token or replace a new user. Real membership revocation hid the open case, restoration reopened it, and simulated expiry led through sign-in back to Financial. Temporary member removed.
- [x] Check a larger synthetic imported case for pagination, complete totals, account/currency filters and source links. Three 31-page synthetic PDFs imported 2,700 payments across three accounts and two currencies. Every date, amount, direction, balance, account, currency and source page matches the generator. Browser pagination, last-page source, 87-payment account/date scope and full export passed. All three exported PDFs are byte-identical; all 2,700 rows are in HTML and JSON.
- [x] Fix the concrete volume defects: metadata consuming the payment limit, page counters becoming payments, unsafe PDF thread concurrency, repeated source JSON in totals queries and a whole-case export limit. Focused verification passed; record the detailed local commit.
- [x] Save 100 payments across accounts, table pages and currencies; change financial tabs and refresh; reopen the finding and its original source; save and download its report. Exact selection, per-account/currency totals, note version and three byte-identical PDFs verified independently. Make the 100-payment selection limit visible and keep deselection available.
- [x] Check large-case trends, graph and pattern results. Monthly totals include all 2,700 payments. The graph requests a smaller scope above 1,000; a 900-payment account loads in about 1.2 seconds. Selecting a name now focuses both the graph and payment list; search and return to all connections are available. All 62 same-day EUR 50 threshold groups match the generated payments exactly.
- [x] Preserve unfinished payment-name and account-owner links through refresh. Retain selected records, names, explanations and captured revisions. Require review before an older draft can replace changed links; explain selected records that are no longer current. Real browser checks include a failed save, exact three-payment grouping in separate currencies, two saved account-owner links and a 176-payment account group with exact totals. Original names, identifiers and payments remain unchanged.
- [x] Preserve claim-comparison source, quote, ranges and interpretation separately per account, plus the response, explanation and supporting payments for the exact claim. Recalculate after refresh and explicitly review changed results or unavailable selected payments. Actual browser recovery, original PDF viewing, download hash and one saved note with its exact source passed.
- [x] Preserve individual duplicate-decision and payment exclusion reasons for their specific document versions or payment status. Correct the other-evidence amount editor's initial value, transaction isolation, currency display and save failure handling; retain drafts and prevent repeated submission while saving. Focused checks passed.
- [x] Finish the advanced candidate-review draft check. Individual values, separate date roles, account, counterparty and reason survive refresh for the same review version. Provisional-account drafts are separate by currency and version. Finalization retains its explanation but requires fresh confirmations and explicit review of changed rows or controls. Existing statement-control draft saving is preserved. Real browser recovery passed without writing accounts, reviews or transactions; 34 focused checks passed.
- [x] Put matching claim payments first in the results and supporting-payment selection, with readable dates, amounts and descriptions. Keep all compared payments available and put per-field reasoning under **Why this result?**. The local browser retained all seven compared payments and placed the matching USD 900 payment first. No new review saved.
- [x] Correct amounts in other evidence individually or from CSV/TSV with an actual template, exact record IDs, currency, strict full-file validation, changed-value protection and explicit per-record results. Browser checks saved and reopened both workflows; concurrent edits preserved the first save and originals.
- [x] Correct other-evidence report currencies, signs, totals, source/correction details and filter parity. Verify actual failed-download recovery and exact PDF contents, with a visually inspected final one-page layout.
- [ ] Inspect the remaining secondary evidence editor save/error controls and address any reachable failed-save or lost-draft path.
- [ ] Continue remaining user workflow checks and address incoming UI feedback through tonight; do not pause the schedule at this checkpoint.

Access verification: the UI uses separate case editing and evidence upload flags from the server. A temporary ordinary member passed read-only, edit-without-upload and upload-without-edit checks against the same synthetic case. Original PDF images loaded, the saved report reopened and downloaded, and no financial writes occurred. Removing membership denied the access endpoint. The temporary member was removed. Focused checks: 4 backend access tests, 11 provider tests included in 245 affected component checks, then 56 checks for the final changed controls. No broad suite repeated.

## Execution rules

Work in the numbered order, completing the current receipt path before moving to cross-feature acceptance. New defects found during those checks belong under the existing item they prevent from passing. Do not expand the scope into unrelated features. Do not stop after a small commit to ask whether to continue. Keep concise progress updates and this plan current. Full suites are reserved for the final integration milestone. Do not call the whole financial programme complete while required implementation or acceptance checks remain unchecked.
