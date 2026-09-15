# Financial release: 15 September 2026

The local build is ready for UI acceptance and an explicitly requested push. It has not been deployed. The server's existing repository deployment process remains the route to release. There is no separate deployment implementation task.

## What investigators can do

1. Open a case, choose Financial, then Statements. Use Upload PDFs to select several statements. The right-hand file list shows their progress and lets you reopen each file.
2. Review each recognised statement period beside the original PDF. Move between pages, correct flagged values or account details, and confirm the import once. Statements with multiple shares keep those accounts separate. Original readings and reasons for changes are retained.
3. Use Transactions to search, filter and select payments. Each row identifies its account. Open a payment to inspect the original, record a note, explain a correction or change its inclusion. Import review is separate from the investigation table.
4. Use People and businesses, Transfers, Patterns and Trends to investigate payments. More financial tools contains Payment graph, Trace funds and Payments and case events. Open the payments behind a result to check their sources.
5. Save notes, payment selections, transfer comparisons and tracing calculations in Findings. Reopen them later or select them for a report. Another authorised case member can reopen the same saved work and supporting documents.
6. Build a report with selected findings and original PDFs. The separate transaction export retains original/corrected versions and recorded history. The tracing review package retains selected calculation inputs, methods, results and verification records.
7. Open the Financial guide when needed. It contains step-by-step instructions and 27 synthetic screenshots and closes without resetting the current form.

Supported wire-detail reports and deposit receipts open a separate review. Their checked details can be saved in Findings and linked to an existing payment. They do not create a second payment merely because a statement records the same deposit or transfer.

## What changed in this completion pass

- Preserved unboxed account summaries, printed card balances and source locations when a PDF also contains drawn tables.
- Completed the supplied Andrews shares, payment-share headings, account closure notice and embedded receipt workflows. Reprocessing retains the prior reading. Missing source pages and damaged identifiers stay visible for review.
- Kept correction, selection, note, transfer and tracing work through financial tab changes and browser refresh. These drafts are specific to the user/case and this browser tab; save completed work in Findings to retain it with the case.
- Checked one complete investigation containing nine payments, two accounts, three PDFs, a correction, a linked receipt and a shared five-finding report.
- Added reproducible capture of the actual statement reader for the existing extraction measurement tools. No reference labels are generated. The release comparison can now detect invented payments on independently reviewed documents that contain no transactions.
- Clarified remaining tracing, pattern, graph and empty-result text. Updated the guide and current screenshots.

## Verification

An open payment-claim comparison now refreshes after transactions may have changed. The previous result and save/download controls disappear until the investigator selects Find matching payments again. The quotation and search settings remain. Nine focused checks and an actual browser recovery check passed with no financial writes and all six test payments unchanged. The latest TypeScript project check and production build passed; the guide contains 27 synthetic images and instructions for this recovery.

The same synthetic case produced money in of USD 1,975 and money out of USD 900 after a USD 120 payment was corrected to USD 125. The original reading stayed in its history. A USD 300 transfer was paired and two tracing scenarios were checked. The report retained five saved findings and three exact original PDFs. The larger review package rebuilt eleven files and both calculations without differences. A read-only second member could read and download but could not edit, and access was denied after membership removal.

All fourteen financial areas were checked at laptop width with the file list open and closed. Live pattern, source, graph and timeline controls used the corrected payments. The guide passed its all-tab, contents, desktop/mobile, image-loading, focus and unchanged-form checks.

One broad frontend run passed 1,146 tests. One broad backend run executed 4,583 tests and identified missing public module exports plus an ambiguous multi-period test fixture. The exports were added; the fixture now verifies refusal of conflicting page context and independent import from separate pages. All 43 affected checks passed after those corrections. Type checking, scoped lint, production build, clean backend startup, migration head and all fourteen local service/case checks passed. The build retains the existing large-JavaScript-chunk warning.

The remote branch was fetched before this checkpoint and had no incoming changes. Local commits and private verification records are retained. Private PDFs, extracts, credentials and unrelated user files are excluded from the release commits.

## Continued case access work

Financial controls now follow the server’s exact case editing and file upload permissions. Read-only members can inspect original PDFs, explore payments and download saved work. Editing and upload controls are unavailable when their particular permission is absent. Access is checked again while the page is open; a failed check removes editing controls and offers an explicit retry.

A temporary ordinary member passed the actual UI under three combinations: read-only, editing without upload, and upload without editing. All three opened payment sources, loaded the original statement image and reopened the saved report. The read-only member downloaded its PDFs. No financial records changed. Revoked membership was denied and the temporary member was deleted. Four backend checks and focused frontend checks passed; the earlier broad suites were not repeated.

## Continued large-statement recovery

Refreshing now restores the open file, statement period, currency and PDF page in the same browser tab. Draft corrections remain tied to their source reading. A section search can find an account, date, year or PDF page and retains PDF ordering. Searches are separate for each user, case and file.

The supplied 222-page PDF passed correction retention across periods, file versions, tabs and refresh, with the original image loaded. Search located the requested period among 52 sections. The 99-page Andrews file passed switching among 45 sections, the unassigned continuation page and its separate receipt, including refresh. No real payments were imported and no financial records changed. Twenty-seven focused checks, type checking and scoped lint passed.

## Continued session recovery

Signing in or out clears cached case queries, and delayed responses from an earlier session cannot clear a newer token or replace its profile. Expired financial access offers Sign in again. A denied case hides its contents and offers Open cases or a deliberate access recheck.

Twenty-two focused checks and the production build passed. A real temporary member lost and regained access while the financial case stayed open. A simulated expired-session response then led through sign-in back to Financial. The temporary member was removed. No financial records changed.

## Continued volume and batch work

Three 31-page synthetic PDFs now import 2,700 payments into three accounts. The review retains headings and page counters without treating them as payments. A statement allows 1,000 possible transactions plus its retained page text; large drafts survive refresh.

PDF files run in separate processes. This fixes corruption and missing tables when the PDF library was used concurrently in threads. Progress, configured limits, worker crashes and cancellation are checked, including real OCR in a child process. Cancellation also stops the job's OCR process group on macOS/Linux.

Ledger summaries no longer fetch each complete source reading once per payment. The 2,700-row financial table opened in 1.8 seconds locally. Pagination, both currencies, account/date filtering to 87 expected rows and source page 31 passed. All 2,700 dates, amounts, directions, balances, account links, currencies and source pages match the generated statement data.

The whole-case export completed in 1.6 seconds locally. Its 18 MB JSON keeps every original reading and confirmation; its compact HTML lists all 2,700 payments. All three included PDFs match their originals byte for byte. Full ledger snapshots support 64 MiB and complete ZIPs remain bounded to 128 MiB, with the same bounds enforced on saved-file verification. Smaller report, scenario and PDF limits remain independent.

Focused verification: 44 statement checks, six browser-draft checks, 47 PDF/OCR/geometry checks plus six final worker checks, 65 summary/snapshot checks and 39 affected export checks. These are overlapping focused groups, not a newly repeated full suite. Private synthetic acceptance records and captures are retained locally.

## Continued saved-work and graph checks

Continued investigation checks: a selection of 100 payments across three accounts survived table pages, account filters, financial tabs and refresh. It saved in five seconds, reopened from Findings and produced a saved report with exact selected values and three unchanged original PDFs. The selection limit is now explained and further checkboxes are disabled until a payment is deselected.

The large-case graph revealed that choosing a name narrowed its payment list but left the graph crowded. Choosing a name now focuses both. Search can find an account or name, and Show all connections restores the complete applied range. Large graphs hide small name labels until zoomed in. All 2,700 payments appear in monthly trends; a 900-payment graph and 62 exact same-day threshold groups passed local browser checks. Four focused graph tests, seven selection/table checks, two graph source/boundary checks, type checking and scoped lint passed. No broad suite repeated.

## Continued identity draft recovery

Payment-name and account-owner link drafts now retain selected records, names, explanations and the revision originally reviewed. Refresh and reloading records preserve the draft. Changed records require an explicit review of the latest version before saving. Replaced payment selections remain visible as unavailable until removed. Account-link saves also verify that the response contains the requested links before announcing success.

The real browser workflow retained a three-payment draft through refresh and a failed save, then saved exactly three links with unchanged original fields. Grouped totals remain EUR 4.14 and USD 2.07 separately. Two account-owner links survived refresh and saved with their history; selecting that owner produced the exact 176-payment account group, EUR 554.70 incoming and EUR 1,079.54 outgoing. Twelve focused payment/account directory tests, type checking and scoped lint passed.

## Review decisions and evidence corrections

Claim source, quotation, amount/date ranges and interpretation now survive refresh separately for each account. The response, reason and supporting-payment selections return for the same claim inputs. Recalculated results require review before saving, and unavailable selections must be removed explicitly. Duplicate reasons stay tied to the exact compared document versions; exclusion reasons stay tied to the payment and its status.

The other-evidence amount editor now opens with the selected value, displays the recorded currency and retains unfinished edits separately by record. A missing original amount stays unknown. Failed saves preserve the draft, and repeated Enter or Close cannot interrupt or duplicate a pending save.

Local browser acceptance restored all claim fields and the response, opened the original payment PDF, verified the downloaded comparison hash and read back exactly one saved review with its selected payment and quotation. Note 917c963e-f40c-4b0f-a79a-86e93b6b1ec5 is in the existing synthetic completion case. The focused decision, editor and surrounding financial-page checks passed. No real financial data was changed and no broad suite was repeated.

Advanced manual reading edits now survive refresh for the same saved review version, including separate booking/value/transaction dates, account and explanation. Provisional-account drafts stay separate by currency and reading version. Finalization retains the reason but requires fresh confirmations after reloading, and changed previews require explicit review. The actual synthetic browser check restored every edited field and source image without recording any financial or review changes. All 34 affected advanced-review checks passed.

Claim results now put matches first, followed by amount differences, incomplete comparisons and nonmatches. Supporting-payment choices show dates, amounts and descriptions. Field-by-field explanations remain available under Why this result. Eight focused claim checks and the real seven-payment result check passed. The production frontend build passed in 7.17 seconds, with the existing chunk-size warning. No broad suite repeated.

## Remaining acceptance

Damaged scans can still require correction or a better source copy. The supplied-page checks and synthetic case journey do not establish independent extraction accuracy across all bank formats. The seven unique supplied PDFs have a retained prediction capture, but independent human reference reviews and an approved baseline have not been supplied. The application records those measurements as unavailable.

Unavailable earlier custody, an expert's opinion or signature, and optional external provider/timestamp acceptance are not generated or certified by this build. The export states which material is present. See [the export requirement mapping](../loupe-financial-export-acceptance.md).

User UI acceptance and deployed-build checks follow this local checkpoint. After an explicit push request, push the verified branch through the existing repository process, wait for the deployment poll, and confirm the server has the new commit. Then open Financial in a test case and repeat upload, source review, import, correction, saved finding and report download. Do not infer deployment from the local build.

## Continued evidence correction checks

Correction files now use exact record keys, reject invalid or rounded amounts and display per-record saved/failed results. A downloadable CSV template supplies the current list's keys and amounts. Invalid replacement files clear older previews, overlapping reads cannot replace newer files and pending saves are locked. Expected-amount checks refuse stale previews before writes and protect each database update with a write lock. Individual amount correction is reachable from Other financial records, uses the recorded currency and retains the original amount and latest explanation. Read-only users cannot invoke these edits.

Validation: 31 focused frontend checks, nine backend request/result checks, type checking, scoped lint and a production build passed. The isolated synthetic browser case 6d3092a5-3077-42f4-8f03-a362c0eb5fff downloaded a three-record template, rejected an invalid replacement, refused a changed batch without changing its other record, saved two exact-key corrections despite identical names and reopened the saved values. An individual correction saved EUR 130.50 while retaining EUR 100.00 as its original. Two simultaneous database updates using the same expected amount produced one save and one refusal; the failed update did not increment the stored revision. Currency-formatted original values remained intact and displayed correctly. No real financial records were changed. Private evidence: data/local-runtime/correction-case.json and /tmp/loupe-correction-*.log.

## Continued other-evidence report checks

The Other financial records report now retains amount signs, identifies each currency and groups totals separately. Missing currencies or amounts are not totalled. Original corrected amounts and latest explanations are included. Automatic dollar signs, inferred money-in/out labels and an unsupported default privilege stamp were removed. Report downloads carry the current case name and all supported filters, including amount limits and category/entity names containing commas. The browser shows pending/error states, permits retry, supports the printable-HTML fallback and discards stale case/session responses. Downloads are bounded to 64 MB.

Validation: 44 distinct focused backend checks across rendering, manifests and report filters; five download lifecycle checks; TypeScript and scoped lint passed. Actual local browser failure/retry retained the 100-to-250 amount limits and downloaded four records. Read-back verified EUR 356.00, USD -150.00 and an unknown-currency 175.00 excluded from totals, with the original EUR 100.00 correction retained. The final layout fits all four records on one landscape page and was rendered and visually inspected. Private evidence: data/local-runtime/evidence-report-download.json, evidence-filtered-report.pdf, evidence-filtered-report-rows.json and /tmp/loupe-report-*.log. The seven unique real PDFs were not changed or imported. No broad suite or new deployment.

## Continued categories and other-evidence chart checks

Continue without pausing or pushing. Categories now retain unfinished names and colours by signed-in user and case, prevent duplicate submissions and report failed saves. Per-record assignment is available to case editors in Other financial records, waits for the confirmed record/category response and shows failures beside the record. Invalid category names and colours are rejected by the API. Unconfirmed responses trigger a fresh read. Transaction-only grouping remains separate from other-evidence claims.

Other-evidence summaries keep currencies and signs separate with exact integer arithmetic. Missing or unsafe amounts are not totalled. Charts select one currency, retain category names safely, use recorded UTC date boundaries and explain that bars compare amount sizes. Unknown currencies and unusable amounts remain in Transactions. The misleading dollar fallback and duplicate dataset buttons were removed. Guide rebuilt with step-by-step category and chart instructions, 22,053 words and 23 synthetic images.

Validation: 11 distinct focused frontend helper/editor checks, three category API checks, 38 FinancialPage checks across the initial run and affected-label rerun, scoped lint and production build passed (7.01 seconds, existing chunk-size warning). Browser creation failure retained the name and colour after refresh; assignment failure displayed an error, then saved on retry. A category containing a comma filtered an actual PDF to one EUR 130.50 record. The running summaries match EUR 666.00 and USD 350.00 while unknown currency stays excluded. EUR/USD charts rendered without JS errors or page overflow. Private evidence: evidence-charts-ui.json, correction-case.json, evidence-category-report.pdf and /tmp/loupe-category-*.log. The final browser recheck was initially rejected because automatic approval review was at capacity; an explicitly reviewed read-only retry succeeded. No real source changes, broad suite or deployment.

## Continued source custody recovery

Categories and currency charts are committed locally as f00a13b4. Source custody now retains every unfinished field, certification choice, correction target and retry identifier separately per signed-in user, case and source. A changed registered file hash needs explicit review before the draft can be reused. An unavailable correction target cannot be submitted. Pending submits are locked, a confirmed response must match the submitted details, and only that confirmed draft is cleared. Selecting a correction fills in the earlier details while requiring a fresh reason. History labels and field names are readable and consistent.

Eleven focused component checks, scoped lint and TypeScript passed. Real local browser recovery retained the full form through closing and refresh, saved a synthetic receipt, simulated a lost server response and verified retry returned the same ID. A separate correction retained its target and fields through refresh, saved once and preserved the original report exactly. The original retry was checked through the saved API request after a redundant helper navigation interrupted sign-in restoration. No duplicate record was created. The downloaded transaction ZIP contains both exact report records and both explanations in its readable HTML. No real evidence changed and no broad suite or new deployment.

## Source viewing, dates and sign-in recovery

A temporary profile request failure now keeps the sign-in while hiding private pages until Retry connection succeeds. Expired/refused sessions still sign out. Logging in returns to the exact requested internal case route. Thirteen focused auth checks and real browser temporary-failure/expiry/return checks passed.

Other financial records expand from their name or arrow into readable details, with the actual currency, source, page and existing notes. Unused selection and editing controls are hidden. Linked originals open at their recorded page. Visual checking exposed a blank native PDF panel, so the shared viewer now renders authenticated PDF page images for registered evidence. It supports zoom, retry and first/last-page bounds using the server page count; stale responses cannot replace a new source. Browser checks verified the exact page-2 image against the local original render, byte-identical PDF, all three page positions, temporary page failure/retry and return to the same record. Synthetic record 57799b74-6671-5676-af8b-a857294f1357 in case 95081ef8-8ffe-475a-bc32-fc77aa1bd0e6 is a separate receipt claim, not another bank payment. Do not reseed it.

The table, list API and report now include timestamps anywhere on the selected last calendar day. Impossible/incomplete dates are not normalized into invented dates; active filters exclude them, and the table labels them for review. Invalid/reversed API date bounds return 422. Seventeen focused date/filter/amount helper checks, six record-detail checks, six PDF-viewer checks and seven backend date/report checks passed. The API list and actual one-record PDF contain the same exact synthetic receipt key, USD 120 and recorded timestamp. Scoped lint, TypeScript and production build passed (7.33 seconds, existing chunk-size warning). Guide rebuilt: 22,410 words, 24 synthetic images. No broad suite or deployment.

## Unreadable evidence amounts and correction recovery

A confirmed read-only check found that "not stated" became zero in Other financial records. It now stays null with the exact original text. Supported decimal/thousands/currency formats retain their sign and cents, including valid zero and parentheses; ambiguous text, ranges, invalid/nonfinite values and amounts that cannot be stored exactly require review instead of stripping characters or rounding.

The list, details, currency summaries, charts and numeric filters retain unknown values correctly. Individual correction starts empty, displays the source text, retains the draft through failure/refresh and carries that exact text into the database change check. File-based correction previews and result verification use the same guard. A stale original is refused while the write lock is held. Confirmed responses must identify the requested record and replacement amount. Original text remains in the API, editor and report after correction, including nonfinite historical values that cannot be returned as JSON numbers.

Forty-seven distinct focused frontend checks and forty-seven backend checks passed across the affected groups and failure reruns. Scoped lint, TypeScript and production build passed (7.37 seconds, existing chunk warning). Actual local browser checks showed both deliberately unreadable receipt values, opened their original PDF, retained a failed individual correction through refresh, saved it once and saved a second correction from CSV. Retrying the old first request returned 409 without changing the saved record. Reports retain both exact keys and original text; totals change from Not totalled to USD 290.00. The final API download is one readable page. A column-width defect found during read-back was fixed so source descriptions and explanations do not collapse into a narrow strip. The nine bank payments remain unchanged.

### Original files from imported payments

The transaction detail dialog now uses the registered PDF page renderer and actual page count. The shared viewer has a visible Close action that returns to the previous details. Browser checks verified a one-page payment source and a three-page statement, page bounds, the same retained search and unchanged payment records. Fourteen focused unit checks and one Chromium component check passed, plus scoped lint, TypeScript and production build. Guide instructions now name the actual source, page and Close controls.

### Missing amounts remain reviewable

Explicit financial records remain visible when no amount was saved. Individual and file-based corrections compare that exact absence before changing it, and later corrections preserve the originally missing value. An older record in a mixed case no longer overrides another record's explicit financial classification. Fifty focused backend checks and thirty-three frontend checks passed, plus scoped lint, TypeScript and production build. Real browser recovery and edits, a stale-request refusal and exact two-page report read-back passed. Nine bank payments remain unchanged.

### Source-preview and separate-file recovery

Delayed responses can no longer replace a reopened original-source preview or expose its object URL after the signed-in session changes. File reads recheck cancellation/session before returning bytes. A failed separate-file open leaves the current PDF visible and provides a retry, with repeat pending requests locked. Eighteen distinct focused checks passed, plus scoped lint, TypeScript and production build. A local browser failure/retry downloaded the exact original SHA-256, retained the visible page and returned to transaction details without changing any payment.

### Returning to the same payment view

Payment table filters, sorting and pagination now survive opening the original file, visiting its location in Evidence, returning to Financial and refreshing. Settings remain separate for each signed-in user, case and applied account/date view. Changing a filter starts at the first matching page; clearing filters leaves selected payments intact. Seven focused checks and actual nine-payment and 2,700-payment browser journeys passed, along with TypeScript, scoped lint and the production build. No payment records changed.

### Returning to saved findings and recovering failed lists

The active financial tab is retained in its URL, so refresh and browser Back return to Findings after opening a note in Workspace. Findings searches/pages and report-list pages remain separate for each user and case in the current browser tab. Failed loads offer retry buttons without clearing the search or report selection. Fifty-one focused navigation, list, page and store checks passed, with two final affected page checks after correcting duplicate React keys. The running browser verified the actual return and failure/retry workflows without changing saved notes or payment records. TypeScript, scoped lint and production build passed.

### Retaining the other-record investigation view

Other financial records now remains selected after refresh. Searches, category/person/date/amount filters, ordering, table page and expanded records survive the trip from an original PDF to Evidence and back. Each case and signed-in user has separate browser-tab settings. Reset all retains the cleared view; selecting the current dataset does not collapse records. Pagination stays within the available results after a reload. Original-file viewers in this area now offer Open file location. Fifty-six focused checks, TypeScript, scoped lint and production build passed. The actual two-case browser check retained views and compared all five/six supporting records and nine bank payments unchanged.

## Open imported statements in the right account

Open imported transactions now applies the statement's saved account and shows only payments from that imported source. Its filename is visible above the table, with Clear statement filter to include other statements again. Old searches and date filters cannot silently hide the opened statement. Refresh retains this view and existing selected payments remain selected. Table downloads record the same source restriction and filename while preserving the wider account history separately.

Twenty-seven focused frontend and nine backend checks, TypeScript, scoped lint and production build passed. The real browser opened six checking-statement payments from a previously selected savings account, kept a selected payment and retained its view through refresh. The downloaded ZIP contains those six exact IDs and the saved correction; nine case payments are unchanged. The remote was fetched with zero incoming commits. No push or broad suite was performed.

## Recover a selection after a payment changes

Review selected payments lists the payments chosen across accounts and filters. It shows their source files and identifies corrected or excluded entries. Open a payment to inspect its original and current values; remove just that entry from the unfinished selection without affecting other choices, transactions or saved findings. Failed checks offer retry without treating a connection problem as an exclusion. Saving identifies the changed payment and retains the note.

Eighteen focused checks, the actual TypeScript project build and scoped lint passed. The browser verified both versions, individual removal, refresh, retained note, one saved selection and readback of its exact payment ID. A temporary source-check failure retried without losing either selection. Nine bank payments remain unchanged. The guide now includes a synthetic example of this review. No broad suite, real financial write or push.

## Keep analysis selections when changing views

Payments selected through analysis results now join the same selection as Transactions. Hiding the result list, changing tabs and refreshing preserve the chosen IDs. Each result explains how many choices lie elsewhere, and its review can remove individual choices. Saving includes the whole selection. Read-only result lists omit Add note.

Six focused checks, TypeScript project checking, scoped lint and production build passed. The actual counterparty-to-Transactions journey retained a selection, combined a second choice, restored both through refresh and shared an individual removal back to Transactions. All nine payments remain unchanged.

## Readable account scope and account-search recovery

The applied payment scope names the account and explains date bounds. The import notice matches the actual statement restriction. Show this account's payments includes its other statements again. Searching the account chooser retains the previously selected account's name; failed searches keep the account and dates with a direct retry.

Nineteen focused checks, TypeScript project checking, scoped lint and production build passed. Browser checks expanded the six-payment statement to the seven-payment account, retained an empty date filter through refresh and retried an account search without changing its selection. All nine bank payments are unchanged. No broad suite or push.

## Retry transaction details in place

A failed transaction-details request now offers Try loading this transaction again. It retries the same payment without closing the source dialog or changing the table search. Incorrect source references continue to be refused. Thirteen focused checks, scoped lint and the TypeScript/production build passed. The actual browser recovered the expected payment and source action, then returned to its two-payment search. All nine records are unchanged.

## Statement worker startup

Local PDF reading and OCR no longer require an OpenAI environment key to pass engine readiness. Missing database, storage, OCR or other required runtime services still prevent the worker from starting. Actual AI operations continue to use their configured provider credentials. The isolated local launcher clears every provider key. Ten focused health/credential checks, a clean local restart and real native/scanned PDF preparation passed without AI credentials; no transactions were imported.

## Scanned statement columns

Scanned statement proposals now compare the positions of amounts across each printed section when money headings and amounts use different alignment. Ambiguous credit/debit assignments remain flagged. The viewer follows those source-column references and keeps printed values and blank cells. The actual native/scanned synthetic pair matched all six payments, opening and closing controls, and original balance highlights without importing financial records. The synthetic footer remains a separate unresolved line.

## Resolve flagged rows directly

Review this row opens the corresponding import checkbox and correction fields beside the original PDF. A user can correct the reading or exclude non-payment text with a reason. The actual synthetic footer exclusion and explanation survived refresh, leaving exactly six payments ready to confirm. Existing imported statements retain their transaction correction route.

## Confirmed statement duplicates

Duplicate review now accepts a confirmed PDF import as the retained copy without upgrading its verification status. An exclusion still cannot remove the last verified occurrence of a payment or retain a copy with payments already set aside or corrected. Fresh duplicate references are saved with the confirmed decision, fixing a database refusal for newly imported statements. Comparison itself remains read-only.

Each candidate has View source, including previously excluded copies. The guide explains how to inspect both PDFs, select the retained file, record the reason and restore an exclusion. The actual native/scanned test moved from twelve payments to six, back to twelve and finally six. The downloaded package retained all twelve readings, the three decisions and both byte-identical source PDFs; only the six current payments appear in its table. Thirty-seven focused backend checks, nineteen frontend checks, scoped lint, TypeScript and the production build passed. No broad suite was repeated and nothing was pushed.

## Duplicate review continuation

Previously opened payment details, related analysis and statement status now refresh after a duplicate decision. The change is limited to the affected case. Candidate cards name the retained file and say whether each copy is included in Transactions; internal identifiers are available on expansion. Read-only members can compare and open both originals without being shown unavailable exclusion or restore buttons. Twelve focused checks and a real temporary member verified this behaviour, with no financial writes. The guide includes a matching synthetic screenshot. TypeScript, scoped lint and the production build passed.

## Reopen an excluded statement safely

An excluded PDF now opens with its saved disposition and retained filename. Its original remains visible, while import, reread and editing invitations are removed. Review duplicate decision opens Import review. The server refuses another import of the excluded source, including a new reading in its file history. Normal replacement imports and explicit duplicate restoration remain available. Duplicate decisions also refresh previously loaded statement reviews.

Thirty-three distinct backend checks passed across the focused run and affected reruns, including refusal, same-source reread, ordinary replacement and restoration. Twenty-five focused frontend checks, TypeScript, scoped lint and the production build passed (13.54 seconds, existing chunk warning). The actual browser reopened the excluded scanned PDF, decoded its original image, refreshed, followed the decision link and compared all six current payments unchanged. No financial writes or JavaScript errors. The final reader capture also preserved all fields, balances, account details, source locations and problems in 182 sections from seven supplied files. This is a regression comparison, not an independent accuracy measurement.

## Refresh calculated results after financial decisions

An open transfer comparison, pattern search or tracing calculation now asks for its payments to be reloaded after a financial action refreshes the case. The old result cannot be saved or downloaded from that form while it needs reloading. Each tool keeps its own reload state, even if another tool has already refreshed. Compatible unfinished assumptions return on reload; saved findings and reports are unchanged. A payment refresh during loading also refuses that unfinished input response.

Sixteen focused checks, TypeScript, scoped lint and the production build passed (13.02 seconds, existing chunk warning). A four-tool browser check simulated an interrupted duplicate decision, verified the notices and draft recovery, and compared the six existing payments unchanged. Every financial POST was intercepted, so this check made no financial writes. Earlier actual two-account calculations and reports remain separately verified. The guide now gives the exact reload actions and current transfer/pattern field labels.

## Clearer account choices and current guide images

Tracing and other tools using account search now show each holder, account number, bank and currency once. The selected caption also cleans up older saved labels while keeping the same account ID. Three existing account-filter checks and scoped lint passed; a real browser selection and refresh kept the six current payments unchanged. The guide's transfer and tracing entry screenshots now match their visible controls. TypeScript and production build passed (13.21 seconds, existing chunk warning).
