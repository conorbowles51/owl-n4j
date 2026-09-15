# Financial release: 15 September 2026

The local build is ready for UI acceptance and an explicitly requested push. It has not been deployed. The server's existing repository deployment process remains the route to release. There is no separate deployment implementation task.

## What investigators can do

1. Open a case, choose Financial, then Statements. Use Upload PDFs to select several statements. The right-hand file list shows their progress and lets you reopen each file.
2. Review each recognised statement period beside the original PDF. Move between pages, correct flagged values or account details, and confirm the import once. Statements with multiple shares keep those accounts separate. Original readings and reasons for changes are retained.
3. Use Transactions to search, filter and select payments. Each row identifies its account. Open a payment to inspect the original, record a note, explain a correction or change its inclusion. Import review is separate from the investigation table.
4. Use People and businesses, Transfers, Patterns and Trends to investigate payments. More financial tools contains Payment graph, Trace funds and Payments and case events. Open the payments behind a result to check their sources.
5. Save notes, payment selections, transfer comparisons and tracing calculations in Findings. Reopen them later or select them for a report. Another authorised case member can reopen the same saved work and supporting documents.
6. Build a report with selected findings and original PDFs. The separate transaction export retains original/corrected versions and recorded history. The tracing review package retains selected calculation inputs, methods, results and verification records.
7. Open the Financial guide when needed. It contains step-by-step instructions and 22 synthetic screenshots and closes without resetting the current form.

Supported wire-detail reports and deposit receipts open a separate review. Their checked details can be saved in Findings and linked to an existing payment. They do not create a second payment merely because a statement records the same deposit or transfer.

## What changed in this completion pass

- Preserved unboxed account summaries, printed card balances and source locations when a PDF also contains drawn tables.
- Completed the supplied Andrews shares, payment-share headings, account closure notice and embedded receipt workflows. Reprocessing retains the prior reading. Missing source pages and damaged identifiers stay visible for review.
- Kept correction, selection, note, transfer and tracing work through financial tab changes and browser refresh. These drafts are specific to the user/case and this browser tab; save completed work in Findings to retain it with the case.
- Checked one complete investigation containing nine payments, two accounts, three PDFs, a correction, a linked receipt and a shared five-finding report.
- Added reproducible capture of the actual statement reader for the existing extraction measurement tools. No reference labels are generated. The release comparison can now detect invented payments on independently reviewed documents that contain no transactions.
- Clarified remaining tracing, pattern, graph and empty-result text. Updated the guide and current screenshots.

## Verification

The same synthetic case produced money in of USD 1,975 and money out of USD 900 after a USD 120 payment was corrected to USD 125. The original reading stayed in its history. A USD 300 transfer was paired and two tracing scenarios were checked. The report retained five saved findings and three exact original PDFs. The larger review package rebuilt eleven files and both calculations without differences. A read-only second member could read and download but could not edit, and access was denied after membership removal.

All fourteen financial areas were checked at laptop width with the file list open and closed. Live pattern, source, graph and timeline controls used the corrected payments. The guide passed its all-tab, contents, desktop/mobile, image-loading, focus and unchanged-form checks.

One broad frontend run passed 1,146 tests. One broad backend run executed 4,583 tests and identified missing public module exports plus an ambiguous multi-period test fixture. The exports were added; the fixture now verifies refusal of conflicting page context and independent import from separate pages. All 43 affected checks passed after those corrections. Type checking, scoped lint, production build, clean backend startup, migration head and all fourteen local service/case checks passed. The build retains the existing large-JavaScript-chunk warning.

The remote branch was fetched before this checkpoint and had no incoming changes. Local commits and private verification records are retained. Private PDFs, extracts, credentials and unrelated user files are excluded from the release commits.

## Remaining acceptance

Damaged scans can still require correction or a better source copy. The supplied-page checks and synthetic case journey do not establish independent extraction accuracy across all bank formats. The seven unique supplied PDFs have a retained prediction capture, but independent human reference reviews and an approved baseline have not been supplied. The application records those measurements as unavailable.

Unavailable earlier custody, an expert's opinion or signature, and optional external provider/timestamp acceptance are not generated or certified by this build. The export states which material is present. See [the export requirement mapping](../loupe-financial-export-acceptance.md).

User UI acceptance and deployed-build checks follow this local checkpoint. After an explicit push request, push the verified branch through the existing repository process, wait for the deployment poll, and confirm the server has the new commit. Then open Financial in a test case and repeat upload, source review, import, correction, saved finding and report download. Do not infer deployment from the local build.
