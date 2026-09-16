# Financial completion plan

15 September 2026. User deadline: a usable financial application tonight, Europe/Dublin. Five-minute continuation checks stayed active through 23:59 and were then paused at the agreed cutoff. The user explicitly rejected stopping at the earlier local ready checkpoint, and development continued through the remaining workflow checks. The larger-case work requested on 16 September is recorded below. User UI acceptance, independent extraction measurements and deployed-build verification remain open below. Earlier plans and their checked items remain as the development record. Completed work stays on this list.

The finished workflow is: upload statements and supporting payment documents, check flagged readings beside the originals, confirm a statement once, investigate the imported transactions, save observations and calculations, and produce a report another authorised investigator can reopen and check.

## 0. Larger-case work requested on 16 September

- [x] Increase single-statement review capacity, page the correction controls, and verify complete import without losing headings, source locations or edits.
- [x] Remove the 100-payment named-selection restriction, read source details in batches, and verify saving and reopening a large selection.
- [x] Remove the 1,000-payment graph restriction, combine repeated connections for drawing, and retain access to every underlying payment.
- [x] Remove the 20-finding combined-report restriction, load findings with bounded concurrency, and verify complete saved reports and downloads.
- [x] Verify the four paths together with large synthetic data, update the guide and record actual tested sizes and remaining resource bounds. One 167-page statement imported all 5,000 payments; one selection saved all 2,700 payments; the graph retained all 2,700; and a saved 50-finding report reopened and downloaded with every payment and three exact original PDFs. Focused checks cover the 25,000-transaction request boundary, 25,000 graph payments, 250 findings and 25 packaged PDFs. The compiled preview passed a read-only check with no JavaScript errors. See [the capacity release record](releases/2026-09-16-financial-capacity.md) for actual measurements and remaining size bounds.

## Daytime work, 16 September, ready for testing by 18:00 Dublin

Neil accepts daytime disruption so long as the application is ready again for the team's evening testing. The existing heartbeat is active every ten minutes through 18:00 Dublin. Begin final integration and deployment work by 17:00; do not start optional changes after that time. Verified fixes may be pushed under this instruction. Keep completed items checked and report any actual deadline risk promptly.

- [x] Push all completed work through 02a5a163. Remote matches the local branch; the server's public version now reports 02a5a16. This verifies the frontend deployment identifier, not an authenticated server investigation.
- [x] Remove the separate 100-payment person/business linking restriction. Support the larger case directory, exact history, complete selection, source access and atomic refusal if the records change. Check that larger linked groups reach totals and reports without a secondary restriction.
- [x] Verify failure and retry behaviour for the larger operations introduced today. Preserve edits and selections after refresh or a failed response; prevent duplicate imports/saves. Use isolated synthetic cases and do not repeat earlier successful writers.
- [x] Investigate specific remaining failures in difficult supplied statement sections, using retained captures and originals. Fix readable information that is missed or wrongly placed; retain explicit uncertainty for damaged or absent source information. Do not claim independent human extraction accuracy.
- [x] Prepare a short team testing checklist with expected outcomes, reporting instructions and known limitations, without replacing the detailed guide.
- [x] Complete focused checks and the production build for changed code, then push coherent verified fixes. Commit 2898f70e was pushed normally after fetching with no incoming changes.
- [x] Verify the deployed identifier and public assets after the automatic deployment poll. The daytime build reported afae084 with all five checklist assets matching. The final guide update reports f3ba2df at 17:24, with all six guide/test assets matching the checked local bytes. Authenticated live-case acceptance remains for the team.
- [x] Leave the deployed app available for evening testing, report completed work and remaining limits/acceptance, and pause the daytime schedule at 18:00. Closing public verification confirms f3ba2df and six exact guide/test assets. The three larger-case analysis improvements below remain open; this handoff does not mark the whole financial application complete.

Final-hour capacity finding: the existing 2,700-payment case passes totals, complete export, statement checks, coverage, graph and account-party reads. Unfiltered transfer, timeline and pattern reads refuse that scope under their separate existing analysis limits. The compiled UI shows each refusal and successfully reruns all three after selecting 2 January 2024 (87 payments). The filters survive refresh, with no financial writes or JavaScript errors. This does not prove whole-case transfer or pattern coverage. The testing checklist now describes the limits and steps.

Remaining development for complete analysis of larger cases, outside today's completed four capacity changes:

- [ ] Replace the 500-payment transfer comparison restriction and 1,000-pair/reference ceilings with complete, efficient matching and browsable results. Keep possible matches across date boundaries.
- [ ] Remove the separate 1,000-payment case timeline restriction while keeping payment and case-event dates distinct and every payment accessible.
- [ ] Rework pattern checking so larger cases and repeated-name groups do not require narrowing below 1,000 payments, 200 matches or 50 payments per name. Preserve complete results and explicit bounds on expensive cross-account searches.

These are capacity limitations, not failures of the local services. They remain open rather than being marked complete because narrower date checks work. No optional implementation starts after the agreed 17:00 cutoff.

Daytime evidence: 2,700 synthetic payments were linked in about 3.5 seconds, with all payment values and 2,700 decisions retained. Losing the successful save response preserved the draft, reloaded the changed records and blocked a stale retry. A failed 50-finding report download produced no incomplete package; retry returned every byte of the previously verified package. The existing 5,000-payment import survived refresh without another import. Focused checks additionally linked, cleared and relinked 5,001 records, retaining 15,003 decisions and complete analysis. The compiled build passed the larger group and last-page controls without writes or JavaScript errors.

The v16 Andrews reader handles spaces inserted into separate measured money cells and exact printed payment verbs. Comparison with the retained v15 capture covers 58 sections: three newly read amounts, nineteen balances and eleven payment directions, with all previous populated fields and source cells unchanged. The original PDF was checked for the demonstrated missed amounts and balance; four actual API sections match the new readings. This is a targeted consistency check, not an independent human accuracy measurement. The short [team checklist](user-guide/financial-team-checklist.md), two invented PDFs and downloadable pack have checked desktop/phone layouts, working links and exact file bytes. Public deployment is verified in the ignored daytime-deployed.json record. The scheduled evening handoff remains open.

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
- [x] Push only when explicitly requested. The authorised 16 September pushes are deployed through f3ba2df, with the public identifier and six guide/test assets verified.
- [ ] Verify a signed-in case workflow on the deployed server. Public deployment and asset checks do not complete this acceptance step.

Release evidence: [15 September release record](releases/2026-09-15-financial.md). One broad frontend run passed 1,146 tests. One broad backend run executed 4,583 tests and found missing package exports plus an ambiguous multi-period fixture; 43 affected tests passed after those fixes. Type checking, scoped lint, production build, clean backend startup and all fourteen local health/migration/case checks passed. The remote branch was fetched with no incoming changes. Private captures remain ignored and unrelated files remain untouched. The build is ready for the user's UI acceptance and an explicitly requested push. Independent human accuracy review and deployment acceptance remain unchecked.

## Continuing user workflow checks

- [x] Remove repeated holder/account segments from tracing account choices and retained captions. Verify selection through refresh and replace the guide's transfer and tracing entry screenshots with the current synthetic controls.

- [x] Require fresh transfer, pattern and tracing inputs after a case financial action refreshes payments. Hide older calculations, retain compatible drafts and saved findings, and refuse a response overtaken by another refresh. Sixteen focused checks and a four-tool browser check passed without financial writes.

- [x] Reopening an excluded statement copy shows its saved disposition, retained filename and original PDF without offering another import. The server refuses reimport, including a new reading of that source. A legitimate replacement reading still works; restoring the duplicate decision re-enables the existing import. Actual browser refresh and decision navigation preserved all six current synthetic payments with no financial writes.
- [x] Compare the final v15 reader with the retained v13 capture across all seven supplied sources. All 182 sections retained their candidate fields, balances, account details, source locations and issues; no financial records were imported. This consistency check does not replace the independent reference reviews still unchecked in section 5.

- [x] Refresh previously opened payment sources and related analysis immediately after duplicate exclusion or restoration, within the affected case. Show clear included/excluded labels and retained filenames. Verify that a real read-only member can open both originals without seeing unavailable exclusion/restore actions.

- [x] Complete native/scanned duplicate import, exclusion and restoration against the actual local PostgreSQL service. Fix the confirmed-PDF verification mismatch and missing stored group key; retain both original PDFs, exact verification status and all three decisions in the exported package. Add View source to both candidate cards. Final synthetic totals contain six payments once, with twelve readings retained in history.

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
- [x] Complete reachable secondary evidence category creation and assignment recovery. Verify failed saves, refresh, exact category assignment and comma-containing category report filters in the running app. Keep other-evidence summaries and charts separated by currency.
- [x] Retain source custody report fields and submission identity through panel closing and refresh. Browser recovery, unchanged retry, one linked correction, exact preserved original and exported history all verified.
- [x] Keep temporary profile-loading failures recoverable without deleting a valid sign-in; preserve expired-session and newer-login isolation. Browser checks verified retry to the same case, genuine expiry and login returning to the original financial page.
- [x] Finish the expanded other-evidence record view with recorded currencies, readable metadata and applicable controls. Linked originals open at their recorded page using server-rendered images; navigation uses the actual page count, supports retry and returns to the same record. The image and PDF both match the unchanged synthetic source.
- [x] Include timestamped records on the selected last day consistently in the table, list API and report. Reject invalid/reversed date bounds, preserve recorded calendar days and label unusable dates without inventing replacements. Exact synthetic record and one-record PDF verified.
- [x] Preserve unreadable amounts as unknown in Other financial records instead of returning numeric zero; verify applicable corrections, filters and reports. Browser checks restored a failed correction through refresh, saved an individual and CSV correction once, refused a stale retry and retained both original texts in the one-page report. The original nine bank payments remain unchanged.
- [x] Verify shared original-file viewing from imported payments and statement balances. Registered PDF pages render, page controls stop at the actual bounds, visible Close returns to details, and the two-payment search survives the round trip. Nine payments unchanged.
- [x] Allow an explicitly absent other-evidence amount to be corrected with an exact missing-value guard and retained original absence. Missing financial records stay visible; mixed legacy records preserve explicit classifications. Actual individual/file edits, refresh recovery, stale refusal, original absence after a later correction and the exact two-page report passed.
- [x] Prevent delayed original-source bytes from replacing a reopened preview or surviving a changed sign-in. A failed separate-file open keeps the current page and offers retry. Focused delayed-response checks and an actual exact-original download retry passed.
- [x] Retain payment search, currency, amount/direction/review filters, sort and table page across original-file navigation, Evidence, Back and refresh. Keep different account/date scopes separate. Seven focused checks and actual nine-/2,700-payment browser journeys passed with unchanged records.
- [x] Restore the correct financial tab after Workspace/Back and refresh, retain saved-work searches/pages and report selections, and retry failed finding/report loads in place. Nine new focused checks plus the surrounding page/store checks passed; actual saved work and nine payment records remained unchanged.
- [x] Retain the Other financial records dataset, filters, sorting, page and expanded records through original-file navigation and refresh, separately for each case/user. Restore its Evidence file-location link and clamp shortened table pages. Fifty-six focused checks and the actual two-case round trip passed with unchanged records.
- [x] Reopen an imported statement in its saved account with only that source’s payments, clear stale filters, retain separate selections and record the same source filter in the downloaded table. Twenty-seven frontend and nine backend checks plus browser/ZIP readback passed with all payments unchanged.
- [x] Identify selected payments that changed after correction, inspect both versions, remove only the old selection and save retained work. Eighteen focused checks plus real browser refresh/retry/save/readback passed. The original nine payments are unchanged.
- [x] Share selected payment IDs between analysis result lists and Transactions. Closing a result, changing tabs and refreshing retain the selection; individual removal updates both views. Six focused checks and the actual browser journey passed with unchanged payments.
- [x] Make statement/account scope visible and accurate: opening the whole account clears the statement restriction, displayed scope uses a recognised name, and account searches retain restored names and dates through failure/retry. Nineteen focused checks plus two browser journeys passed with unchanged payments.
- [x] Retry a failed transaction-details request in place without losing its payment, source action or table search. Thirteen focused checks and the real two-payment search/retry/return journey passed with all records unchanged.
- [x] Start the statement worker without optional AI credentials while retaining required database/storage/OCR checks. Ten focused checks and actual native/scanned PDF jobs passed on the isolated stack with no configured provider keys.
- [x] Correct scanned statements whose money headings and amounts use different alignment. Preserve original source cells and blank printed columns; ambiguous layouts remain flagged. Forty-eight focused backend checks, 27 frontend checks and the six-payment native/scanned browser comparison passed without importing financial rows.
- [x] Open a flagged statement line directly at its import choice and original PDF location. Twenty-two focused checks and actual exclusion/reason/refresh recovery passed; the six-payment confirmation was enabled without importing any rows. The compiled frontend also passed sign-in, original-file navigation, guide assets and saved-report reopening.
- [x] Continue remaining user workflow checks and address incoming UI feedback through tonight. Checks remained active through 23:59 Dublin, with the completed fixes and local verification recorded in the build state. No new feedback arrived during the closing review period. The schedule was paused at the agreed cutoff.
- [x] Refresh an open payment-claim comparison after case payments may have changed. Hide the previous result and its save/download controls, retain the quotation and search fields, and require a new comparison. Nine focused checks and a read-only browser recovery journey passed; all six synthetic payments remained unchanged.

Access verification: the UI uses separate case editing and evidence upload flags from the server. A temporary ordinary member passed read-only, edit-without-upload and upload-without-edit checks against the same synthetic case. Original PDF images loaded, the saved report reopened and downloaded, and no financial writes occurred. Removing membership denied the access endpoint. The temporary member was removed. Focused checks: 4 backend access tests, 11 provider tests included in 245 affected component checks, then 56 checks for the final changed controls. No broad suite repeated.

## Execution rules

Work in the numbered order, completing the current receipt path before moving to cross-feature acceptance. New defects found during those checks belong under the existing item they prevent from passing. Do not expand the scope into unrelated features. Do not stop after a small commit to ask whether to continue. Keep concise progress updates and this plan current. Full suites are reserved for the final integration milestone. Do not call the whole financial programme complete while required implementation or acceptance checks remain unchecked.
