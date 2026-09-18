# DocuClipper research and Loupe processing benchmark

## Completed local development checkpoint, 18 September 2026

Local implementation and acceptance for A-E are complete, apart from verification on the deployed server. The approved investigator workspace is retained. The final production build and compiled browser check pass, including corrected payments, original PDF navigation and both updated guides. The significant combined regression and subsequent focused checks are recorded in [persistent state](loupe-build-state.md).

D's classification and review criteria are now closed against the supplied-file audit: observed non-payment candidates are excluded with their sources retained, recovered payment rows are available, and each remaining uncertain field has a correction or assignment route. The original checks found and fixed wrapped amounts, lost pages, repeated date context, missing names, lost card-payment signs and inconsistent interest readings. Every observed exception remains recorded in [the source audit](financial-information-page-audit-2026-09-17.md). These checks do not establish general OCR accuracy. Damaged scans still need investigator corrections, and team acceptance has not been claimed.

The 87 ready reviews were confirmed and retried in disposable databases, producing 339 payments exactly once. The final charge correction journey separately imported three synthetic payments and restored saved corrections without browser tab storage. No real case was modified by these tests. The deployed check below remains unchecked until observed on the correct Loupe server.

## Earlier local implementation checkpoint, 17 September 2026

The main statement register now shows imported-date gaps, overlapping periods and unknown dates. Account review opens the relevant originals and requested date range; duplicate exclusion and restoration update the register. This is browser-verified on synthetic January/March statements with a repeated March copy. Pre-import overlaps now require a recorded comparison or leaving a copy unimported.

Latest difficult-file audit: six split-description amounts and fifteen posting-anchored transaction dates are corrected in the supplied Capital One collection. Its 52 periods and 301 proposed entries are unchanged; 51 opening/closing checks now match and one is unavailable. A separate visual sample of 27 entries on four original pages matches counts and totals. Twenty-nine clearly labelled interest charges now retain no printed date and can import without an invented date. Only one earlier transaction without a separate posting date still needs a date review. The [audit record](financial-card-extraction-audit-2026-09-17.md) distinguishes that sample from full-document accuracy. This remains local and does not close the outstanding D/E items below.

The continuation schedule is active every 10 minutes. The latest local implementation adds shared server-side checks to individual and batch review, recalculates edited values, compares running balances beyond 1,000 rows, and supports explicit printed credit/debit totals where recognised. A genuine printed discrepancy can be retained with an explanation tied to the exact values checked. It is never relabelled a match.

Account and period controls are separate. Corrections open immediately under the selected printed row with the PDF alongside it. Batch reviews can save incomplete progress to the server, restore it after browser storage is cleared, and save before opening the next or previous statement needing attention. Original printed cells are retained.

A new synthetic local case verified saved mismatches, incomplete dates, server recovery, navigation across files and bulk import of 36 transactions from three statements. The initial read-only Capital One baseline found 52 periods and 301 proposed transactions, with 45 closing-balance matches and 7 unavailable checks. The later audit above improves those results. Recovery, reassignment and selected-row corrections are now checked below; remaining investigation connections are still open. Nothing here claims deployment.

Research date: 17 September 2026.

Purpose: make financial document processing straightforward for an investigator. Preserve the Loupe investigation workspace the user has accepted and improve the journey into it.

## Recommendation

Use DocuClipper as a benchmark for how little work a user must do to turn a folder of statements into usable transactions. Loupe already has substantial supporting functionality. The next development should bring that functionality together around a compact statement viewer, automatic checks and a short list of specific problems.

The required journey is:

1. Select files or folders in Evidence and choose **Send to Financial**.
2. Arrive in Financial while the system prepares those documents.
3. See how many files, accounts, statement periods and transactions were found.
4. Import all ready statements with one confirmation.
5. Open each remaining problem directly beside its original PDF, correct it and continue.
6. Start investigating the imported payments. Return to the source and make recorded corrections later when needed.

This is a proposed acceptance standard. It does not claim that every step already meets it on the deployed server.

## Research method and limits

I read DocuClipper's public product pages and detailed documentation for extraction, reconciliation, corrections, multiple accounts and periods, duplicates, coverage, transfers, categorisation, recurring payments, flow of funds, file handling, APIs, pricing and security. I also opened its public **Financial Investigator** demo and inspected transaction navigation, the PDF/table layout, coverage and an account-reference drill-down. The demo describes itself as a read-only sample environment. [Public demo](https://www.docuclipper.com/app/demo-entry/)

No Loupe documents were uploaded to DocuClipper. The demo cannot establish extraction accuracy, processing speed on the user's files, persistence of edits, or behaviour at case scale. Statements below distinguish documented capabilities from observations and recommendations.

For Loupe, I inspected the current local source and the running-state record. The intake, batch and review work through commit `23039a67` was pushed on 17 September. Later work remains local until the complete task is ready, as the user requested while Alex tests the platform. Previously recorded local browser checks are evidence about those particular journeys, not deployed acceptance or a general accuracy measurement.

## What makes the processing experience useful

### 1. The document, account and period remain clear

DocuClipper documents separate Document, Account and Period selectors. Reconciliation belongs to the selected account and period. Users can correct an account/period assignment rather than treating a whole PDF as one statement. Its reassignment controls support selected rows and creating a missing account/period. [Reconciliation](https://www.docuclipper.com/docs/how-reconciliation-works/), [account and period assignment](https://www.docuclipper.com/docs/how-to-assign-transactions-to-multiple-accounts-and-periods-in-docuclipper/)

**Loupe implication:** a file containing years of statements needs a short account selector and a searchable period selector. Each period needs its own status and transaction count. A problem in one period must leave the others available to import. The PDF page number and the statement's printed page number should remain distinguishable.

### 2. Checks identify a useful place to look

The documentation distinguishes opening/closing reconciliation from running-balance checks and comparisons with independently printed credit/debit totals. A running-balance break points to the affected row. A totals difference shows the amount of the discrepancy. Checks rerun after edits. The documented running-balance check accommodates reverse printing order. [Running-balance and totals checks](https://www.docuclipper.com/docs/review-transactions-balance-and-totals-checks/)

**Loupe implication:** present a short result such as **Balance differs by $21.19**, with **Show the difference**. Keep the calculation available on request. A missing printed balance needs a different status from an actual mismatch. A matching net balance must not silently clear an unreadable date, duplicated row or other unresolved field.

### 3. Reviewing a value and correcting it are close together

DocuClipper documents inline corrections, reversible exclusion, adding missing transactions, switching credits/debits and editing selected rows together. It says corrections are retained against the raw OCR reading. [Transaction review and editing](https://www.docuclipper.com/docs/matching-transactions/)

**Loupe implication:** retain the original statement's columns and blank cells, with a clear edit action at the value or row. An investigator should not have to locate a second table below the viewer. Show the original value and correction history when requested, and use a compact reason control when a correction is saved. Do not require a written reason for every unchanged, valid transaction.

### 4. Navigation follows the investigator's attention

The user's screenshots show a compact transaction navigator, PDF on the left and a transaction grid on the right. In the public demo, clicking **Next transaction** changed the counter from 1 of 2 to 2 of 2. I also observed the document/account/period controls, selected-row actions and per-column filters. These observations confirm the interface arrangement, not extraction performance. [Public demo](https://www.docuclipper.com/app/demo-entry/)

**Loupe implication:** keep previous/next transaction, previous/next issue and PDF page navigation distinct. Selecting a problem should select the transaction, reveal the relevant field and highlight its original location. Closing the review should return the user to the same place in the batch.

### 5. Processing connects to questions an investigator can answer

DocuClipper's coverage documentation describes an account-by-month view that distinguishes missing records, available statements and reconciliation status. Period dates drive the result, so correcting bad dates changes the coverage view. [Statement coverage](https://www.docuclipper.com/docs/date-gaps-analysis/)

In the demo, an account reference with no supplied statement opened a list of the payments mentioning it, with dates and totals. That is a useful model for turning extracted information into a request for further records. [Public demo](https://www.docuclipper.com/app/demo-entry/)

**Loupe implication:** after import, offer useful next actions: view payments, inspect missing periods, follow an account reference, compare related transactions or record a finding. A processed-file count alone is not the end result.

## Current Loupe position

These assessments concern the local working tree. “Present” does not mean every statement format has been independently measured or the change is deployed.

| Area | What is present locally | Work needed to reach the benchmark |
| --- | --- | --- |
| Evidence folders to Financial | Folder/file selection, descendant PDFs, deduplicated selection and automatic navigation | Keep this as one obvious entry point; present skipped and already imported files clearly |
| Background processing | Persistent server batches, per-file and per-period results, retry and worker leases | Improve the compact progress view and distinguish upload, reading and import status |
| Bulk import | One confirmation imports the displayed ready periods; unresolved periods stay separate | Keep the count and meaning of “ready” consistent everywhere; surface duplicate concerns before confirmation |
| Multiple statements per PDF | Recognised account/period sections, period dropdown, previous/next period | Separate file, account and period controls; make long collections easy to search and scan |
| PDF comparison | Original PDF, preserved printed table, measured highlights and page navigation | Put edits beside values; reduce vertical movement and repeated controls |
| Transaction navigation | Previous/next controls and source navigation | Add a continuous next-problem journey across periods and files; preserve focus throughout |
| Automatic checks | Opening/closing checks before bulk import; separate running-balance tools after import | Use one current check result across batch, viewer and import; connect row-level differences and printed subtotals |
| Corrections and recovery | Audited import/correction paths; batch reviews can be saved on the server with revision checks | Make save state obvious; extend durable draft behaviour consistently rather than relying on browser-tab drafts in other paths |
| Coverage and duplicates | Existing coverage, requested-period and duplicate services/tools | Bring the actionable results into the normal statement workflow |
| Investigation | Accepted Overview, Transactions, People and businesses, Follow money, Trends and Findings pages | Preserve these pages and open them with the imported accounts/periods already selected |

### Specific integration gaps found during the initial research

1. `statement_review_checks.py` checks opening balance plus selected movements against the closing balance. The batch service uses that result. It does not perform the complete running-balance chain or separate printed credit/debit subtotal checks in this path.
2. `statement-review-balance.ts` can additionally compare with the last printed transaction balance under particular ordering conditions. The server batch check requires an opening and closing control. These are different checks, so the screen must not describe them as equivalent results.
3. `correction_balances.py` already implements post-import running-balance diagnostics. It currently declines comparisons above 1,000 period rows. That limit needs to be handled in the proposed integrated checking work, not mistaken for a transaction-import limit.
4. The statement viewer retains a printed table plus separate correction controls. This preserves original readings, but the correction path still involves moving between representations.
5. The period selector combines bank, account, dates, pages and checking text into each option. That becomes difficult to scan when a file contains many periods.

Relevant files:

- [Batch processing and readiness](../backend/services/financial/import_batches.py)
- [Current pre-import checks](../backend/services/financial/statement_review_checks.py)
- [Shared review arithmetic](../backend/services/financial/review_arithmetic.py)
- [Current-value checks in the viewer](../frontend_v2/src/features/financial/hooks/use-statement-checks.ts)
- [Existing running-balance diagnostics](../backend/services/financial/correction_balances.py)
- [Statement review](../frontend_v2/src/features/financial/components/StatementImportPanel.tsx)
- [Period selection](../frontend_v2/src/features/financial/components/StatementSectionPicker.tsx)
- [Persistent progress and earlier validation](loupe-build-state.md)

## Proposed processing screen

The following is Loupe design guidance, not a claim about a DocuClipper screen.

**Top bar:** file selector, account selector, period selector, status and transaction count. Show dates and account identity without a long explanatory paragraph.

**Left:** original PDF, fit/zoom, page navigation and a clearly visible row highlight. Opening a period should start on its first transaction or first problem while keeping summary pages available.

**Right:** the extracted statement using its printed columns. Selecting a value locates it in the PDF. An edit action opens a small editor at that location. Edited values receive a visible marker with access to the original.

**Problem strip:** “2 items need attention”, with previous/next problem and a one-sentence instruction for the selected item. For example: “This date has no readable day. Enter the date printed on page 14.” Summary pages and ordinary issuer wording should not become review tasks.

**Footer:** save status and either **Import ready statements** or **Save correction and next problem**. A disabled action must name its blocker and provide the route to it.

**Batch view:** count files, periods and transactions separately. Show Processing, Ready to import, Needs attention and Imported. Checking status is separate: Balances match, Balance difference, or Balance check unavailable. This prevents “imported” from being mistaken for “all arithmetic checks passed”.

## Development order and completion criteria

Retain completed work in this checklist. Checked items include the local implementation checkpoint below. Unchecked items remain work to complete.

### A. Retain and finish the existing intake foundation

- [x] Select Evidence PDFs and nested folders, then navigate to Financial.
- [x] Process batches on the server and retain per-period status.
- [x] Confirm a ready batch once and preserve successful imports on retry.
- [x] Open a flagged row beside its PDF and save a batch correction on the server.
- [x] Apply the same clear progress, save and result language throughout the journey. Upload controls describe PDF reading, point ready files to the statement review and direct failures to processing details; saved drafts and batch imports retain their explicit state messages.
- [ ] Verify the deployed workflow after the local batch changes are published.

**Done when:** a user selects a parent folder, leaves the page, returns, imports the ready periods once and can see which records remain unresolved. Repeating an action must not add duplicate payments.

### B. Make automatic checks consistent

- [x] Create one server result for current proposed values, used by the viewer and batch list.
- [x] Include independent opening/closing arithmetic, running-balance intervals and separately printed credit/debit totals where supported.
- [x] Preserve debit/credit conventions for credit cards, currencies, source order and statement boundaries.
- [x] Identify the relevant rows or source totals for each difference.
- [x] Show unavailable checks without labelling them successful or creating an imaginary error.
- [x] Remove or safely replace the current 1,000-row running-balance diagnostic limit.
- [x] Recalculate after an edit, exclusion, restored row or reassignment. Moving selected extracted rows between recognised account/period reviews checks both statements and updates their saved bulk-review status.

**Done when:** the same proposed import produces the same status and figures in every view. Equal and opposite missing amounts must be caught where printed gross totals or running balances expose them, even when the final net balance matches.

### C. Simplify the statement workspace

- [x] Separate file, account and period selection, with search for long collections.
- [x] Show concise period status and counts in the selector.
- [x] Edit at the value or row while preserving the printed representation and original PDF.
- [x] Provide next/previous problem across the current batch, including movement to another period or file.
- [x] Show saved, saving, unsaved and conflicting edits. Individual and batch statement reviews save incomplete progress to the server, restore it without browser storage and refuse stale saves. Reprocessing comparisons are listed separately below.
- [x] Keep transaction navigation and PDF page navigation separate and keyboard usable.

**Done when:** an investigator can locate and correct an amount without searching another part of the screen, then move to the next problem without reopening the file. Switching periods, tabs or refreshing restores saved work.

### D. Reduce avoidable manual work on difficult files

- [x] Exclude recognised summary, disclosure and marketing sections from transaction candidates while retaining their source pages and useful totals. Original-page inspection and candidate comparisons are recorded in the source audit; actual payment histories and unknown forms remain available for review.
- [x] Distinguish uncertain transaction fields from harmless contextual text. Remaining observed flags concern actual payment fields, separately printed totals or uncertain account assignments. Direct problem links, inline corrections and saved recovery are verified; unreadable scan values are not guessed.

Earlier progress on these two items (retained below for the audit trail): recognised Capital One notices and Andrews fee-summary pages remain available without unnecessary coverage tasks. Seven misread Merrick headings and three Andrews non-payment rows no longer enter payment review. Damaged payment dates and missing fields remain flagged with readable fields retained. The seven-file comparison preserves every remaining payment's fields and original cells. The difficult Merrick/Andrews readings still have substantial flags, so the overall acceptance item remains open. See [the recorded comparison](financial-information-page-audit-2026-09-17.md).
Local follow-up: **Complete missing years** uses one investigator-checked Merrick closing date to preview missing transaction years while preserving each printed day/month. Existing dates and undated charges remain unchanged; unreadable or out-of-range days still require individual correction. A synthetic browser journey verified server recovery without browser storage and a two-payment bulk import. This reduces repetitive decisions; it does not resolve all difficult-file errors or invent missing statement-period coverage.

Further source comparison recovered missing Andrews pages and payment boundaries: the smaller collection now has 16 sections and 383 entries rather than 14/296; the larger retains 44 sections and gains 24 entries, reaching 2,065. Every added row's presence was visually checked on the relevant original pages/crops. Existing dates, amounts, signs and balances remain unchanged. Account forms and fee-only pages remain accessible information pages. The smaller collection's flags increase to 128 because missing payments have been recovered with genuine reading problems. These results are recorded in the audit and do not close D or establish full-field accuracy.

Subsequent measured date/money rereading reduces the smaller Andrews collection to 49 flagged entries and Merrick to 70, retaining original values and every recovery comparison. Twelve Merrick cover/form/notice/interest-calculation/records-request pages are now recognised information pages after original-page inspection. Two genuine payment-history pages remain available for review. All 42 Merrick sections and 230 entries are unchanged by this classification. These remaining flags and separate payment-history review still require the D acceptance checks.

The larger collection now also exposes ten payments from a continuation with a missing preceding page as an assignment-only review. Users can move them to the confirmed account without retyping; direct import is refused. An application and dividend-only summary no longer create coverage work. Inspection of its 113 flagged entries found no non-payment candidates, but did reveal readable amounts on wrapped credit-voucher lines that still need parsing. That layout defect is now fixed: eleven amounts/balances match inspected originals, with all 2,075 entries retained and flags reduced from 113 to 102. The smaller collection remains unchanged at 383 entries and 47 flags. D remains open pending the final combined acceptance check; the concrete wrapped-value defect is closed.

- [x] Offer selected-row correction for repetitive errors with a before/after preview, selection across pages, source links and a reason retained on every changed row. Checks recalculate after applying.
- [x] Permit selected extracted-row reassignment between recognised accounts/periods in the same PDF before import. Preview both statements, preserve source locations and each saved review's corrections, record reasons, refuse stale previews or imported periods, and recalculate both sets of checks. Creating new undetected periods and moving already imported payments are not offered by this control.
- [x] Recover individual and bulk saved reviews through earlier file versions, including unmatched periods and conflicting alternatives. Show old values separately; record a file-wide comparison before importing a changed reading, invalidate it when saved inputs change, and recheck unchanged batch periods. Current imports and original files remain retained.
- [x] Flag overlapping account/date coverage before individual or bulk import. Show the other original PDF and its import status; require a comparison reason to import both, or leave one unimported with a reason and restore it later. Keep originals, corrections and decision history. Browser-verified with two synthetic copies: one imported, one retained, three payments with no duplicate import.

**Done when:** the supplied multi-statement files produce a manageable, justified set of review tasks. A cleaner screen alone cannot close this item. Every false flag and missed transaction found in the benchmark must be recorded.

### E. Connect import to investigation

- [x] Open the imported transactions with their account/date range and exact batch source filter. Include all imported periods across list pages, provide a clear reset, and bind table downloads to the same source list. Reopening a single imported statement also retains its source filter.
- [x] Bring missing-period and overlapping-period checks into the main statement register. Show account details, unknown dates and per-page counts; open account-scoped coverage, requested dates, original statements and transactions. Duplicate comparison opens here and exclusion/restore refreshes the register. Browser-verified with synthetic January/March statements and a repeated March copy. Pre-import comparison is also completed under D.
- [x] List explicitly labelled account/card/share/IBAN references from current imported payments, with complete payment links and original PDFs. Distinguish no imported statement from a possible match, retain partial-reference warnings, and paginate/search groups.
- [x] Save a reference question directly to Findings with its supporting payments and proposed next action. Browser-verified on a synthetic two-payment reference, including PDF inspection and saved finding restored after refresh.

**Done when:** a user can go from a ready import to a source-backed investigation question in the ordinary workflow.

## How to judge whether we matched the ease of use

Measure the user's work as well as extraction accuracy. The following are acceptance targets, not measured results:

| Scenario | Expected user experience | Evidence to record |
| --- | --- | --- |
| Clean single statement | One import confirmation after processing; no per-row acceptance | Steps, transaction count and checked fields |
| Clean mixed folder | One confirmation for all ready periods | Expected files/periods/accounts, skipped files and duplicates |
| One misread value | Open the issue, compare source, edit, save; other periods remain usable | Click path, source highlight, recalculated checks |
| Multi-period card PDF | All recognised periods selectable; summary pages add no spurious transactions | Independent period inventory and row comparison |
| Equal-offset errors | Net match does not conceal failures visible in other controls | Separate opening/closing, gross-total and running checks |
| No printed balances | Clear unavailable status; valid records can follow the stated import policy | No invented opening/closing values or false success badge |
| Repeated upload/retry | No duplicate import from repeating the same confirmed operation | Row counts and source identifiers before/after |
| Navigation/restart | Saved edits and completed imports remain available | Close/reopen, refresh and worker recovery checks |
| Large period | No silent omission or successful badge for a skipped check | Expected row count, complete retrieval and check coverage |

For extraction, independently check transaction presence, date, description, amount, credit/debit placement, balance, account/period assignment and PDF location. Report results by document type and scan quality. Also measure time to usable import, manual interventions, false flags and incorrect records that were not flagged.

The real 222-page PDF already examined locally and the user's 201-page DocuClipper screenshot are different documents. Their counts cannot establish a like-for-like accuracy comparison. The local record of 52 recognised periods and 301 extracted transactions is an extraction result, not independently established ground truth.

## Broader capabilities worth learning from

**Duplicates:** their documentation describes exact-file detection before conversion and possible transaction overlap across sources, with a review prompt. Its looser account matching is a reason to retain human review of ambiguous duplicates. Loupe should keep source records and decisions visible. [Duplicate detection](https://www.docuclipper.com/docs/detecting-duplicate-statements-and-transactions/)

**Transfers:** matching uses opposite movements on different accounts, amount, dates and descriptions. The detailed workflow requires running detection and reviewing suggested matches. This supports proposing links automatically while keeping an investigator's decision separate. [Transfers](https://www.docuclipper.com/docs/transfers-analysis/)

**Trends and repeated payments:** chronological balance/cash-flow charts and recurring series link summaries to the transactions behind them. Loupe should preserve that connection in its accepted investigation design. [Cashflow](https://www.docuclipper.com/docs/cashflow-analysis/), [recurring payments](https://www.docuclipper.com/docs/recurring-transactions-analysis/)

**People and accounts:** the documented account model supports holder/role attributes and filtered flow diagrams. Manual account merging is explicitly described as not yet shipped in the tracing guide. A shared holder label is not a substitute for verified account identity. [Account tracing](https://www.docuclipper.com/docs/multi-account-tracing/)

**Flow of funds:** the documentation connects diagram selection, filtered transaction lists and exports. It describes a workbook with transactions, account-to-account totals and account summaries. This is useful evidence-linked navigation, although it does not by itself establish the identity or purpose of a payment. [Flow of funds](https://www.docuclipper.com/docs/flow-of-funds-analysis/)

**Categories:** the help article describes user-triggered keyword rules and recorded matching keywords. Marketing references to AI categorisation should not be taken as a precise description of that documented workflow. Categorisation, recurring detection and transfers are separate from automatic extraction/reconciliation. [Categorisation](https://www.docuclipper.com/docs/how-docuclipper-transaction-categorization-works/)

**Checks and other documents:** its cheque workflow can enrich a statement's cheque-number placeholder using a matching cheque image, and skips ambiguous matches. That is a later opportunity for Loupe, separate from completing statement intake. [Cheque extraction](https://www.docuclipper.com/docs/check-extraction-overview/)

**Document concerns:** metadata, document-template fingerprints and reconciliation contribute to a vendor-defined authenticity score. The documentation itself explains benign causes and says the score is not a final decision. Loupe should present any future document concerns as specific observations to investigate. [Fraud detection](https://www.docuclipper.com/docs/understanding-bank-statement-fraud-detection/)

## Limits and inconsistencies in the public evidence

- **Multi-period support is not unconditional.** The extraction quick-start recommends one period per PDF, while the account/period guide describes support and manual correction for combined files. The supplied screenshots demonstrate a successful combined-file example. Those facts do not establish reliable automatic segmentation for every pack. [Extraction guide](https://www.docuclipper.com/docs/extract-data-from-bank-statements/), [assignment guide](https://www.docuclipper.com/docs/how-to-assign-transactions-to-multiple-accounts-and-periods-in-docuclipper/)
- **Input quality still matters.** Their preparation guide recommends original PDFs, upright complete pages and normal single-page layouts; it identifies two-up scans as difficult. [File preparation](https://www.docuclipper.com/docs/preparing-files-for-best-results/)
- **Accuracy is a vendor claim.** The OCR page advertises 99.9% field-level accuracy and large-scale validation. I did not find a reproducible evaluation dataset or detailed scoring method on the reviewed pages. That percentage does not establish whole-statement accuracy or performance on Loupe's documents. [OCR product page](https://www.docuclipper.com/features/bank-statement-ocr/)
- **“Reconciled” is not proof of authenticity or complete extraction.** A final balance can agree despite offsetting mistakes. This is why the separate checking methods matter and why originals must remain available.
- **A read-only demo is not a production trial.** It confirms visible controls and sample navigation. I have not tested saving edits, processing the user's PDFs or exporting a real investigation through their service.
- **Do not copy destructive document cleanup.** Their document guide says deletion removes the source and associated transactions, tags and notes within the project. Loupe's requirement is to retain Evidence and recorded history when excluding a file from Financial. [Document management](https://www.docuclipper.com/docs/managing-project-documents/)

## API, cost and data handling

These findings are relevant if an external extraction service is considered later. The present recommendation is to use the workflow as a benchmark. No integration or subscription was started.

The API guide describes uploading documents, starting background jobs and retrieving grouped results or transactions. The documented flat transaction endpoint defaults to 1,000 rows, has a maximum of 10,000 and currently lacks an offset cursor; that particular endpoint should not be assumed to retrieve arbitrarily large cases. The guide also describes per-document reads and webhook use. Field-level PDF coordinates and complete correction-history portability would need explicit validation before an integration decision. [API recipes](https://www.docuclipper.com/docs/api-common-recipes/)

Public pricing is page based, with unlimited users advertised and advanced financial analysis associated with Business/Enterprise. The dynamic pricing page mixes currency/billing options in its text extraction, so this report does not quote a potentially misleading price. Successful blank and cover pages count if processed; rerunning conversion consumes pages again. [Pricing](https://www.docuclipper.com/pricing/), [page counting](https://www.docuclipper.com/docs/do-all-pages-count/), [overages](https://www.docuclipper.com/docs/credits-and-overages/)

The security page states SOC 2 Type II, encryption, a DPA on request and no training of third-party models using customer documents. This is a summary of vendor statements; I did not inspect its audit report. Its published subprocessor list identifies US hosting and external OCR/model providers. That list describes a broader set of processing activities than the security page's description of deterministic bank-transaction extraction. Exact document routing would need to be established for any integration. [Security](https://www.docuclipper.com/security/), [subprocessors](https://www.docuclipper.com/legal/subprocessors/)

Public retention descriptions are not consistent: the security page gives plan-specific periods, while the job-history article describes active-subscription retention with shorter exceptions for some users and automated ingestion. These need clarification before relying on the service as a long-term evidence store. [Retention statements](https://www.docuclipper.com/security/), [job history](https://www.docuclipper.com/docs/how-to-access-job-history-in-docuclipper/)

## Scope of this research change

This report records the benchmark and proposed development order. Application code, extraction settings, case data and deployment were not changed as part of the research. The existing unpushed development work remains intact.
