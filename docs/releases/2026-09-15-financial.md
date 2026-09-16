# Financial release: 15 September 2026

The financial implementation is available locally for user acceptance. The latest code commit is `1a987cb2`. It has not been pushed or deployed. A read-only check of the server's public version file at about 23:44 Dublin reported `40fdf65`, matching the last fetched remote commit. The server already deploys from the repository; no new deployment system is required.

The [completion plan](../loupe-financial-completion-plan.md) keeps completed work checked off. The [build record](../loupe-build-state.md) retains the detailed changes, failures, corrections and verification results. This release note describes the resulting application.

## What investigators can do

1. **Add and review statements.** Open a case, choose Financial, then Statements. Select Upload PDFs to add several files. Use the right-hand file list to switch statements and follow processing. Open a recognised account and period beside its original PDF. Move between pages, inspect highlighted values, correct a misreading with a reason and confirm the import once. The investigation table is separate from this review.
2. **Investigate payments.** In Transactions, search descriptions and names, choose accounts and dates, filter amounts or currency and select payments. Open a transaction to see its original document, add a note, correct an imported value or explain an exclusion. Original readings and the history of changes remain available. Reopening an imported statement can show just its payments or the whole account.
3. **Check accounts and statement coverage.** Inspect holders, account numbers, statement periods and printed balances. Separate shares remain separate accounts. Missing pages, conflicting controls and unreadable account details are shown for review. A balance is not imported as a payment.
4. **Follow people and money.** People and businesses groups payment names and supports explained links to a person or organisation. Transfers compares possible payments between accounts. Patterns and Trends show payments behind their results. More financial tools contains Payment graph, Trace funds and Payments and case events. Open contributing payments to inspect their sources or add them to the shared selection.
5. **Record and share the investigation.** Save notes, named payment selections, transfer comparisons and tracing calculations. Reopen saved work in Findings and include selected findings in a report. Another authorised case member can open the same saved work and supporting sources. Payment-claim responses are saved as Workspace notes with the quotation, explanation and selected payments.
6. **Review other financial documents.** Supported wire reports and deposit receipts have a separate review. Save their checked details in Findings and optionally link an existing payment. Other financial records support individual or CSV/TSV amount corrections, categories, original-document viewing and filtered reports. Unknown amounts remain unknown until an explained correction is saved.
7. **Export the work and its sources.** Download selected reports or transaction packages. They retain the applicable original PDFs, original and corrected readings, decisions and recorded source history. Tracing packages retain calculation inputs, methods and results. Open Financial guide for the full instructions and 27 synthetic illustrations.

## What happens when work is interrupted

- Statement review, correction, note, selection, identity-link and calculation drafts remain in this browser tab for the same user and case. Financial tab changes and refresh retain supported drafts. Save completed work to retain it with the case; an unsaved browser draft is not shared work.
- Payment searches, filters, table position and the selected financial view return after original-document navigation, Back and refresh. Saved-work searches and report selections also return.
- Failed saves retain their explanation and show the applicable retry. Changed records require review before an older draft can replace them. Unavailable selected payments remain visible until removed.
- Transfer, pattern, tracing and payment-claim results are hidden when case payments may have changed. The screen names the button to reload or recalculate. Compatible draft assumptions return; existing saved findings and reports stay unchanged.
- Excluded statement copies retain their original PDF and the name of the retained copy. They cannot be imported again through a rereading. Import review provides the recorded decision and explicit restoration.
- Temporary sign-in/profile failures can be retried. An expired session returns through sign-in to the case. Case access and editing/upload permissions are enforced separately.

## Verification completed locally

| Area | Result |
| --- | --- |
| Complete investigation | One case contains nine payments, two accounts and three PDFs, including an explained correction from USD 120 to USD 125. Money in is USD 1,975 and money out USD 900. The original reading remains available. A transfer, two tracing calculations, a linked receipt and a five-finding report were checked together. |
| Original evidence and reports | The report contains five findings and three byte-identical original PDFs. Its review package independently rebuilt eleven files and both tracing calculations. A second authorised member reopened and downloaded saved work; denied and revoked access checks passed. |
| Larger documents | Three 31-page synthetic PDFs contain 2,700 payments across three accounts and two currencies. Every generated date, amount, direction, balance, account and source page matched the imported records. Pagination, scope filters, page 31, a 100-payment selection, trends and complete export passed. Local timings were about 1.8 seconds for the table and 1.6 seconds for the whole-case export; these are not server performance guarantees. |
| Native and scanned duplicates | Six payments were imported from each of two synthetic source copies. Explicit exclusion, restoration and exclusion returned the current table to six payments while retaining twelve historical readings, three decisions and both original PDFs. Reopening the excluded copy cannot start another import. |
| Recovery | Actual browser checks covered interrupted saves, refresh, source opening, changed selections, current-result reloads and retained explanations. The latest claim-comparison check made no financial writes and left its six payments unchanged. |
| Supplied PDFs | All 567 pages across eight filenames were accounted for, representing seven unique PDFs and 511 unique-file pages. The final reader capture retained all fields, balances, source locations and issues across 182 sections compared with the earlier automatic capture. This is regression consistency, not independent extraction accuracy. |
| Local startup | All fourteen final service/case checks passed, including migration head, worker heartbeat, sign-in, local OCR, summaries, exports and analysis endpoints. Native and scanned PDF preparation worked without AI provider credentials. Actual AI operations still require their configured provider credentials. |
| Compiled frontend | Sign-in returned to the case; payment search survived source viewing; guide images loaded; the five-note report reopened and downloaded; Findings survived refresh. Nine payment records stayed unchanged, with no failed assets or JavaScript errors. |

One broad frontend run passed 1,146 tests. One broad backend run executed 4,583 tests and exposed nine failures. Missing public exports and an ambiguous multi-period fixture were corrected, and all 43 affected checks passed. The broad backend suite was not rerun and is not recorded as entirely passing. Subsequent changes used focused checks. The latest TypeScript project check, scoped lint and production build passed. The build retains the existing large-JavaScript-chunk warning.

The [export requirement mapping](../loupe-financial-export-acceptance.md) and [supplied statement checks](../loupe-supplied-statement-checks.md) explain the detailed evidence and source limitations. Private originals, extracts, credentials and browser records are excluded from release commits.

## Limits users need to understand

- Damaged dates, unclear account identifiers and missing pages still require inspection, correction or better source evidence. The system does not fill them from a neighbouring account or balance calculation merely to complete an import.
- Original layout and source locations are preserved where the reader identifies them. Ambiguous scanned credit/debit columns remain flagged. A supported sample does not establish accurate reading of every bank layout.
- Independent human reference reviews and an approved real baseline have not been supplied. Extraction accuracy against those references remains unmeasured. The retained 2,955 automatic candidate rows include unresolved readings and are not 2,955 verified transactions.
- Analysis uses the selected accounts, dates, currency and payment population. A match or pattern is a reason to investigate. It does not establish the payer's identity, intent or that every statement has been supplied. Printed balances and net payment totals have separate meanings.
- The 16 September capacity follow-up replaces the earlier count limits: statement reviews allow 25,000 possible transactions, named selections and combined reports use 32 MB saved-data bounds, and graphs retain all matching payments within the shared 100,000-row and 64 MB calculation bounds. The former 100-payment, 1,000-graph-payment and 20-finding restrictions are removed. See [larger-case verification](2026-09-16-financial-capacity.md) for measured checks.
- Missing earlier custody records, independent opinions, signatures and optional external timestamp/provider acceptance are not created by this build. Packages identify what is present and what is unavailable.

## Next release steps

1. Review the local application. The compiled frontend runs at `http://127.0.0.1:55175`; the development frontend is at `http://127.0.0.1:55174`. Use a test case for imports and changes.
2. After an explicit push request, check the working tree and fetch the branch again, then push the verified commits. The last fetch at about 23:26 Dublin found no incoming commits. At `1a987cb2`, 56 local commits are ahead of remote `40fdf650`.
3. Wait for the existing deployment poll and confirm the server's commit/build. The deployment script installs dependencies, builds the frontend and Docker services, runs migrations and restarts the application. A successful local build does not prove that the server deployed it.
4. On the deployed version, complete a test-case journey: upload a statement, inspect and correct a value beside its original, confirm once, open its payments, save a finding and download a report. Verify the original PDF and reopen the saved work after refresh.
5. Complete independent human reference review and the extraction measurement with those approved records. Keep that acceptance separate from software regression results.

User UI acceptance, independent extraction measurements and deployed-build verification remain open. The implementation and local verification described above are complete. The compiled local preview serves code commit `1a987cb`. The five-minute continuation schedule stayed active through 23:59 Dublin and was then paused at the agreed cutoff.
