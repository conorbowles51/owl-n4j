# Financial completion plan

15 September 2026. This is the current plan for finishing the financial work. It replaces the changing list of small next steps as the execution order. Earlier plans and their checked items remain as the development record. Completed work stays on this list.

The finished workflow is: upload statements and supporting payment documents, check flagged readings beside the originals, confirm a statement once, investigate the imported transactions, save observations and calculations, and produce a report another authorised investigator can reopen and check.

## 1. Finish the supplied statement and receipt formats

- [x] Read the supplied Capital One and Merrick layouts with their distinct dates, charges, credits and statement balances. Preserve damaged readings for review.
- [x] Read Andrews savings, checking and payment-share sections separately. Follow supported continuation pages and preserve original PDF locations and printed page order.
- [x] Preserve blank columns, account closure notices and statements with no payments without creating false transactions or balances.
- [x] Review the supplied Wells Fargo wire report separately, save checked details in Findings and optionally link an existing payment.
- [x] Finish the Andrews deposit receipt inside a multi-document PDF: selection, separate dates and balances, masked account reference, saved finding, optional payment link, original source and report inclusion. Verified with the supplied receipt on PDF page 42 and a synthetic statement plus two receipts; separate drafts, refresh, same-file payment link, saved source and exact-PDF report passed.
- [ ] Account for every page in the eight supplied files: statement section, supporting receipt, application/terms, repeated copy, or an explicit unresolved page. Record a source-by-source result and do not call a missed page complete.
- [ ] Check the remaining damaged account headings and missing continuation sequence. Use existing correction/reprocessing controls where they suffice; fix any path that loses original readings or leaves the user unable to finish the review. Unreadable identifiers remain unknown until the original supports a correction.

Done when: all supplied files can be opened; each recognised section can be reviewed independently; every remaining unreadable or missing item has a visible next action; source-only checks and synthetic imports prove that receipts, headings, balances and duplicate copies do not inflate transactions. This is not a promise that illegible source text can be recovered automatically.

## 2. Finish a complete investigation in one case

The following features are implemented. Final acceptance checks must use the same case so their interactions are checked rather than assuming separate tests prove the whole workflow.

- [x] Upload multiple PDFs, navigate the file list and pages, edit proposed values, confirm once and open Transactions.
- [x] Search/filter/select transactions; inspect the PDF; correct a value; exclude or restore a transaction; retain the history.
- [x] Inspect account holders, statement periods, missing dates and balances.
- [x] Investigate people/businesses, compare transfers, inspect patterns and trends, follow the graph and compare case events.
- [x] Save named transaction selections, notes, comparisons and tracing calculations in Findings.
- [ ] Repeat the full journey after the new document support, including one correction propagating to totals, analysis and reports, and one receipt linked to an existing payment without duplication.
- [ ] Verify that an authorised second case member can reopen the saved work and original sources and that a read-only member cannot change it.

Done when: an investigator can move from original evidence to a recorded observation and report without resorting to internal processing screens or losing their place.

## 3. Finish persistence and recovery checks

- [x] Separate statement review from the investigation table. Keep review state during financial tab changes.
- [x] Retain original readings and explained corrections; save confirmed imports, notes and calculations with the case.
- [ ] Check unsaved and saved states for every active form: statement correction, receipt/wire review, transaction note, selected payments, transfer comparison and tracing inputs. Check financial tab changes, refresh and reopening a saved case.
- [ ] Check interrupted upload/processing, failed saves, retry, reprocessing and replacement imports through the current UI. Reuse existing targeted failure tests, adding tests only for a newly exposed defect.
- [ ] Fix misleading save messages, accidental reset, duplicate-save behaviour or missing recovery actions found in this pass.

Done when: a failed action preserves the user's work and gives a useful retry; a successful action remains available after reopening. Any unsaved browser-only state is clearly identified.

## 4. Complete reports and the original evidence-package requirements

- [x] Build and reopen shared reports from saved findings and calculations, with selected transaction values and source references.
- [x] Include checked original PDFs, correction history, available source custody records, processing versions and saved tracing assumptions/results in the existing export paths.
- [x] Verify downloaded file hashes and replay supported tracing calculations from the saved inputs.
- [ ] Map each original expert-package requirement to the actual exported field/file and its verification. Use a finite requirement table; do not treat historical checkpoint wording as a new feature request.
- [ ] Implement any missing capture or report link revealed by that table. Include the new receipt review and distinguish original, corrected and unknown values.
- [ ] Verify one combined package from the final case independently of the page that created it. Confirm selected scope, exact amounts, evidence links, retained versions and accessible readable output.

Done when: every applicable requirement is either present and verified or explicitly records unavailable historical/source information. Software must not invent earlier custody, software versions or independent measurements that were never recorded. Genuine missing implementation stays unchecked.

## 5. Finish extraction validation and the release gate

- [x] Validate and reconcile two reader records, retain disagreements, bind predictions to source hashes and calculate exact extraction measurements.
- [x] Compare a measured run with an earlier run without substituting test counts for source accuracy.
- [ ] Check the actual reader/prediction workflow against the supported formats and make the final run reproducible from its private input inventory and reader version.
- [ ] Connect an approved private corpus run to the release checks. Missing inputs must be explicitly unavailable, not a fabricated pass; a measured regression must fail the check.
- [ ] Link available measurements into the evidence package with their real reviewer status and extraction versions.
- [ ] Obtain independent human reference reviews for a representative real corpus and run the resulting measurement. This is external acceptance work, not a reason to stop implementing the application or its validation tools.

Done when: the software can run, retain and export the measured result reproducibly; the release record states exactly which real-source measurements are independently reviewed. External AI/provider validation remains separately identified if its configured credentials cannot authenticate. Local PDF and investigation development continues regardless.

## 6. Final user interface and documentation pass

- [x] Keep Statements, Transactions and Findings separate, with visible original-document actions and usable upload buttons.
- [x] Keep the Financial guide available in a modal and closed unless the user opens it.
- [ ] Walk every financial area in the final case at laptop width with the right-hand file list both open and closed. Check page navigation, long values, errors, empty results and actionable controls.
- [ ] Remove remaining internal terminology from the main workflow. Each screen must explain what it shows and the next useful action.
- [ ] Update the step-by-step guide and synthetic images to the final buttons and process. Do not publish private statement screenshots.

Done when: every primary tab gives a recognisable investigation task, saved work can be found again, and the guide's instructions match the actual screen.

## 7. Final integration and ready-to-push checkpoint

- [ ] Finish all required code changes from sections 1 to 6 and mark them with verification evidence in this plan.
- [ ] Run the affected integration checks and one broad financial regression run at this final milestone. Fix failures and rerun only affected checks unless a new systemic concern justifies more.
- [ ] Run type checking, scoped lint, the production build and migration/startup checks appropriate to the final diff.
- [ ] Review exact changed paths, preserve unrelated work and exclude private PDFs, local records and credentials.
- [ ] Commit with detailed explanations, record release notes and leave a verified build ready to push. The existing server deploys from the repository; there is no separate deployment implementation blocker.
- [ ] Push only when explicitly requested, then verify the deployed build through the user-visible workflow where server access permits.

## Execution rules

Work in the numbered order, completing the current receipt path before moving to cross-feature acceptance. New defects found during those checks belong under the existing item they prevent from passing. Do not expand the scope into unrelated features. Do not stop after a small commit to ask whether to continue. Keep concise progress updates and this plan current. Full suites are reserved for the final integration milestone. Do not call the whole financial programme complete while required implementation or acceptance checks remain unchecked.
