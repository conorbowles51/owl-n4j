# Loupe financial user guide

Step-by-step instructions for reviewing financial records, investigating payments and preparing reports.

**Edition: 11 September 2026.** This guide describes the financial screens in the local application. A server may show an older version until it is deployed. Screenshots use a development case with synthetic transactions. They illustrate the controls, not findings about a real person.

## Contents

1. [Start here](#start-here)
2. [Find your way around](#find-your-way-around)
3. [Add a PDF](#add-a-pdf)
4. [Check the extracted statement](#check-the-extracted-statement)
5. [Correct problems before import](#correct-problems-before-import)
6. [Confirm the statement import](#confirm-the-statement-import)
7. [Read a statement again](#read-a-statement-again)
8. [Record how a source was received](#record-how-a-source-was-received)
9. [Read and filter transactions](#read-and-filter-transactions)
10. [Correct a reading or change its inclusion](#correct-a-reading-or-change-its-inclusion)
11. [Check statements and missing periods](#check-statements-and-missing-periods)
12. [Review duplicates](#review-duplicates)
13. [Investigate names, accounts and trends](#investigate-names-accounts-and-trends)
14. [Compare possible transfers](#compare-possible-transfers)
15. [Review patterns and payment claims](#review-patterns-and-payment-claims)
16. [Trace funds in one account](#trace-funds-in-one-account)
17. [Trace funds between accounts](#trace-funds-between-accounts)
18. [Record asset purchases and resale assumptions](#record-asset-purchases-and-resale-assumptions)
19. [Prepare an indirect financial workpaper](#prepare-an-indirect-financial-workpaper)
20. [Download reports and supporting records](#download-reports-and-supporting-records)
21. [Compare and check saved packages](#compare-and-check-saved-packages)
22. [Stop work and return later](#stop-work-and-return-later)
23. [Solve common problems](#solve-common-problems)
24. [Complete your case review](#complete-your-case-review)
25. [Words used in Loupe](#words-used-in-loupe)
26. [Advanced manual review](#advanced-manual-review)

## Start here

### Open this guide while working

Select **Financial guide** above the financial tabs. The button stays visible while you scroll a financial screen or switch tabs. The guide opens in a modal, which is a panel over your current screen. Select a contents link to jump to a procedure, or select **Guide contents** to return to the list. Select **Close** or press Escape to return to the case. Opening the guide does not save or discard the form underneath it.

### What you need

Ask your administrator for the Loupe address, your own sign-in details and access to the case you will work on. Reading a case and editing it are separate permissions. If you can view records but cannot save a decision, ask for editing access to that case.

Keep the original files supplied to you. Work from the evidence registered in the correct case. A file on your computer is not available to colleagues until it has been uploaded to their Loupe server. Local development cases are not copied to the server by a software deployment.

You do not need an AI connection for the normal statement upload and review process. Optional AI proposals in the advanced review tools require a provider configured by your administrator.

### Your first complete task

Practise with a test statement in a test case first. Follow sections 3 to 6: upload the PDF, inspect the extracted transactions, correct any flagged errors and confirm the import once. You can then investigate the payments directly in Transactions.

The normal order of work is:

1. Upload the statement and wait for its extracted account details and transactions.
2. Check highlighted problems against the original PDF and correct what is wrong.
3. Confirm the import once, after checking the number of transactions being added.
4. Search and filter the transactions, examine their sources and investigate counterparties and transfers.
5. Save notes and download reports with the supporting statement references.

### Understand which payments are included

**All imported payments** includes the current payments you confirmed from statements. **Verified payments only** is a narrower view based on the application's verification checks. A PDF you checked and imported can appear in the first view while remaining outside the second. Use **All imported payments** for the normal investigation of imported statements.

Totals are kept separate by currency. In Transactions, bank payments and credit-card entries are also totalled separately. Bank money in increases funds held; a card credit reduces money owed. The difference between credits and debits is not the account's closing balance.

Older manual reviews may use terms such as candidate, resolved reading or finalization. Those are explained in **Advanced manual review**. The normal statement import handles those internal steps for you.

## Find your way around

1. Open the Loupe address supplied by your administrator.
2. Enter your username and password, then select **Sign in**.
3. Open the case you will work on. Check its name before uploading or recording anything.
4. Select **Financial** in the case navigation.
5. Use the main tabs for everyday investigation. Open **More financial tools** for further analysis and history.

![Transactions with filters, payment totals and investigation actions](images/14-investigation-transactions.png)

*Each payment has an Open transaction button and an Add note action. The table contains imported payments; statement preparation has its own workspace.*

| Main tab | What you can do |
|---|---|
| Transactions | Search payments, inspect original statements, correct values and save selected payments with a note. |
| Statements | Upload one or several PDFs, check their readings, confirm imports and check account balances or missing periods. |
| Findings | Reopen saved notes, payment selections and calculations. Download a note and its supporting records. |
| People and businesses | Compare how much each name paid or received, open its payments and record name links. |
| Transfers | Compare the outgoing and incoming sides of possible transfers and save your explanation. |
| Patterns | Find repeated names or amounts, quick movements and smaller payments that add up to a chosen amount. |
| Trends | Compare payments by day or month and open the payments behind a total. |

| Under More financial tools | What you can do |
|---|---|
| Payment graph | See connections between accounts and recorded payment names. Open connected payments. |
| Trace funds | Compare rules for allocating withdrawals to funds you have identified, or prepare an indirect financial calculation. |
| Payments and case events | Compare payment dates with wider case events and save an observation linked to both. |
| Import review | Inspect older manual PDF reviews, duplicate documents and technical verification records. |
| Excluded transactions | Inspect payments left out of the current totals and reconsider their inclusion. |
| Processing history | Find statement-reading attempts and see why one stopped or failed. |
| Change history | Read who changed a transaction, what changed and why. |

**Imported statement payments** and **Other financial records** are separate sets of information. Use the first for the statement workflow in this guide. The second contains information extracted from other evidence. An amount mentioned in a letter or interview is not automatically a bank transaction. Use the payment-claim comparison in Patterns to compare such a statement with recorded payments.

## Add a PDF

### Upload a bank or credit-card statement

1. Open the correct case and select **Financial**. The **Transactions** tab opens first.
2. Select **Add statements** to open Statements. Select **Import a statement** if the review is closed, then **Upload a statement**.
3. Select **Choose PDF** and choose your statement from your computer. Use **Change PDF** if you picked the wrong file.
4. Check its filename, then select **Upload and read statement** once.
5. Wait for Loupe to read the pages. Scanned statements take longer because their letters and numbers must be read from images.
6. The statement review opens when reading is complete. Loupe fills in the account details and transaction fields it can identify.
7. If the PDF contains several statements, choose the account and period you want to import. The page numbers help you identify the right statement.
8. If asked, choose the currency printed on the statement. Do not choose a currency merely because it is your usual working currency.

You do not need to assign columns, select every payment, save a batch or finalize readings in the normal import process. Those tasks happen within the system. Nothing enters the transaction totals until you confirm the import in section 6.

![The normal statement review, using a synthetic statement](images/11-statement-review.png)

*The original PDF opens beside its extracted printed table. Printed columns and blank cells remain visible. Corrections and import choices are separate below the table.*

### Upload several statements and switch between files

1. In **Bank statements**, select **Statement files**. The right-hand panel opens on **Statements**.
2. Select **Upload statements** and choose up to 20 PDFs in one selection.
3. Keep the browser tab open while Loupe uploads them. Each file shows its own progress. A failed request stays visible; other files can continue.
4. Wait for a file to show **Ready to review**, then select its filename. It opens in the main statement viewer.
5. Select another filename to switch files. Use **Search filenames** to narrow the list. The added time and short identifier distinguish files with the same name.
6. Return to a file to continue its review. Changes are saved when you switch; its selected statement period and page are remembered during this session.
7. Check and confirm each statement separately. Bulk upload does not automatically confirm transactions.

If a file has not been read, select **Read statement** beside its name. If reading failed, select **Retry reading**. These actions read the PDF already in the case; you do not need to upload it again. Wait for **Ready to review**, then select the filename. Files being processed cannot be started again from this panel.

A file with saved imports shows its current imported payment count, account and recorded periods. This count is read from the case and remains available after reopening your browser. A PDF can contain other periods that have not been imported yet. Open the file to check those periods; the count does not mean the whole PDF is complete. Replaced or excluded payments are not included in this count.

If a request fails, select **Refresh files** and inspect what arrived before uploading another copy. A connection failure can occur after the server received a file. Closing the browser tab can stop uploads that have not yet been sent. Refreshing the page clears the in-memory upload queue and page selections; uploaded files remain in the case, and saved review drafts can be restored by reopening the same statement and period in the same browser tab.

![Statement file list, page controls and separate corrections using synthetic PDFs](images/13-statement-files.png)

*Choose a ready filename on the right to open it. Edit import values opens the correction controls while the original PDF stays visible.*

### Open a statement already uploaded

1. Select **Statement files** and select a ready filename in the right-hand panel.
2. Alternatively, select **Import a statement** and choose the file under **Or open an uploaded statement**.
3. If several versions share a filename, compare their added times and the short identifier beside each name.
4. Choose a statement period and currency if requested.
5. If the statement was already imported, select **Open imported transactions** to return to the investigation view. Do not upload another copy to make it appear again.

If a file has not finished processing, wait for its status to complete. If reading failed, use **Retry statement review** or the reprocessing controls described in section 7. Repeated uploads create separate source records and make duplicate review harder.

## Check the extracted statement

### Check the account and transaction count

1. Compare **Account holder**, **Account number** and **Bank** with the statement header. A beneficiary account mentioned in a transfer is not necessarily the account that issued the statement.
2. Check the statement currency and any recorded **Period start** and **Period end**.
3. Read **Check statement details** if it appears. It explains missing or unclear account details, dates or page coverage.
4. Read the number beside **transactions to import**. Compare it with the payment rows on the original statement.
5. Check the credit and debit totals. For a bank account, credits usually represent money in and debits money out. For a credit card, debits increase the amount owed and credits reduce it.

Where a printed opening balance and an ending balance are available, the review recalculates the balance using your selected payments. Excluding a payment or changing its amount can show **Selected movements leave a balance difference**. Inspect the compared balance and check missing rows or corrections before confirming. Agreement is an arithmetic check, not proof that every payment was supplied.

A manually added transaction has a page citation but does not establish its position among the printed rows. Loupe therefore explains when it cannot perform the sequential running-balance check. Check that payment against the PDF and compare the statement totals.

An opening balance, closing balance, column heading or disclosure paragraph is not a payment. Loupe excludes recognised examples from the proposed transaction count. The extracted printed table still shows these source rows. To inspect their import treatment, open **Show corrections and import choices**, then select **Show excluded rows**.

### Compare a field with the PDF

1. In **Extracted statement**, select the printed value you want to inspect.
2. Read the original PDF alongside it. The table uses the printed column headings, order and blank cells where they can be identified. It does not replace Credit and Debit with a Direction column.
3. Compare the date, description, credit or debit amount and balance. The PDF remains the original evidence if its extraction differs.
4. Use zoom and **Fit source width** to read small print. **Show highlighted value** returns you to the selected location.
5. If the page has no exact highlight, inspect the whole cited page. A page link is less precise than a field highlight.

On a complex page, transaction tables are shown as separate sections. Advertisements and other page text are available under **Other extracted page text**. Rows needing a layout check stay visible. Compare them with the PDF before deciding whether anything is missing.

Select **Edit import values** above the viewer, then select **Show problems and edits only** to concentrate on rows that need attention. Turn it off again to inspect all proposed transactions. This filter only changes what you see; it does not remove rows from the import.

### Check a PDF containing several statements

Use **Previous page**, **Next page** or the **Page** selector above the viewer to move through the original PDF. The PDF and extracted table change together. A page with no extracted rows still remains available as a PDF page; inspect it for anything missed. The viewer starts at the first page of the chosen statement.

Each choice identifies a printed account and statement period or date. Select **Choose another statement period** to return to the list. Confirm each statement separately so its account and dates stay attached to the correct payments.

Open **Inspect another page of the original PDF** when pages are listed as needing a coverage check. Choose **Original PDF page**, then **Show selected page**. Read unassigned pages for missed transactions and continuation tables. Loupe does not treat an unassigned page as proof that it contains no payments. If you find a payment for the selected account and period, add it as described below.

A masked card ending is only a partial account reference. Do not use a matching four-digit ending alone to conclude that two statements belong to the same account or person.

## Correct problems before import

### Fix a misread value

Before confirmation, use **Edit import values**. For a statement already imported, **Edit imported transactions** opens the current transaction workspace; use the transaction's correction action there. Corrections to the current record are separate from the unchanged original extraction.

1. Select the printed value to inspect its source, then select **Edit import values** above the viewer. It opens the correction controls below the printed table.
2. Change only the fields that disagree with the printed statement. Dates need a full day, month and year. Amounts use a decimal point without thousands separators.
3. Enter the positive amount in **Credit** or **Debit**, matching the printed statement. Entering an amount in the other column moves this transaction to that column. The unchanged extracted table stays above the corrections so you can compare your change with the source.
4. Enter a printed balance only if one is shown. Leave it empty when the statement does not supply one. A missing value is not zero.
5. Enter the row's correction reason, explaining what you changed and where you checked it.
6. If you corrected the holder, account, bank or period, complete **Reason for detail corrections** too.
7. Resolve any remaining required-field message before confirming.

For example, if the PDF prints `61.62` and Loupe reads `61.26`, enter `61.62` and explain that you checked the printed amount on the cited page. The original extraction and your correction are both retained with the import.

### Remove a heading or other non-payment

1. Find the row and inspect its source.
2. Clear **Use** for that row.
3. Enter the reason if requested, for example, “Opening balance, not a payment”.
4. Check that the transaction count and totals now exclude it.

The row remains in the saved review history. Clearing Use does not alter the PDF.

### Add a missed transaction

1. Open the source page containing the missed payment.
2. Select **Add a missed transaction**.
3. Check the new row's source page. Select the correct original page if needed.
4. Fill in its full date, description, amount and direction. Add the printed balance and counterparty only when the source supplies them.
5. Explain why you added it and where it appears on the original page.
6. Check the revised transaction count and totals.

Do not guess an unreadable year, amount or direction to make the button available. Inspect the source or read it again. If you exclude an unresolved row, record why and remember that your imported transactions will not include that payment.

## Confirm the statement import

1. Review the final account details, included transaction count and any remaining warnings.
2. Check the original pages when coverage is uncertain. A matching total alone does not show that every payment was recovered.
3. Select **Confirm import of [number] transactions** once.
4. Wait for the confirmation. Loupe records the statement, included transactions, original extraction and your corrections together.
5. You return to **Transactions**, where the imported payments appear in the table and working totals.
6. Use the account and date filters, open a transaction's source, or move to **People and businesses**, **Trends**, **Transfers** or **Patterns** to investigate.

![Imported transactions ready for investigation](images/12-imported-transactions.png)

*After one confirmation, the synthetic statement's payments appear in the investigation table. Open View source to return to the statement or Add note to record a question about a payment.*

If confirmation reports that the source or review changed, reload the review and check the current version. If the outcome is uncertain, inspect **Transactions** and reopen the statement before trying again. An already imported statement shows its current transaction count and **Open imported transactions**. Expand **Recorded import decisions** to see reasons for exclusions and corrections made at import. **Inspect the original extraction** shows the initial reading, which can differ from the corrected transactions now in use.

Working totals include the reviewed PDF transactions. The separate verified-only view can show fewer transactions because it applies additional source and verification rules. Confirming an import records your review; it does not certify that the bank statement is genuine or complete.

## Read a statement again

Use this when extraction missed or misread substantial parts of a PDF. For a single error in an imported transaction, use **Correct transaction**, described in section 10.

1. Select **Import a statement** and open the affected uploaded file.
2. Expand **Read the statement again**.
3. Read the explanation, then select **Reprocess statement**.
4. Wait for processing to complete. Loupe creates a separate reading of the same source bytes and keeps the earlier version.
5. Review the new statement, including its account details, transactions and any corrections needed.
6. If this replaces an imported statement, check the displayed replacement count, select **Replace the previous import when I confirm** and enter the reason.
7. Confirm the replacement import once.
8. Check **Transactions**. The earlier version remains in history, but the replacement supplies the current transaction totals. The two versions should not be counted together.

If you refresh the page while processing, reopen the same uploaded statement in the same browser tab. Loupe checks the saved processing job. Select **Open new reading** when it is ready. If the request was interrupted before a response arrived, select **Reprocess statement** to resume the same request. Closing the browser tab can discard this saved progress.

Do not repeatedly reprocess without checking the result. OCR can repeat the same error; correcting a readable value against the source may be the appropriate next step.

The older page-by-page review tools remain available under **Import review** for existing batches and exceptional layouts. They are described in the [advanced manual review appendix](#advanced-manual-review). They are not required for a normal statement import.

## Record how a source was received

Custody records describe how a source came into the case and any reported transfers. They are separate from transaction review.

1. Open a source from PDF selection, **View source**, or a statement source control.
2. Expand **Source custody records**.
3. Read any existing reports before adding another.
4. Choose the **Report type**: Receipt, Transfer or Additional information.
5. Enter the reported event time if known, including its timezone. The example format `2026-09-10T14:30:00+01:00` means 14:30 with an offset one hour ahead of UTC. Leave the time blank if unknown.
6. Enter **Received from** where known and **Received by** for receipt or transfer reports.
7. Choose **How obtained**, such as Client supplied or Document production. Explain Other in the details.
8. Record **Native file availability**: Provided, Requested, Unavailable or Unknown. A native file is the original data format supplied by its system, rather than only a PDF rendering.
9. If you have a supporting certification, select **Choose a certification file from this case** and choose the correct uploaded file.
10. Enter **Details and reason**, then select **Record custody report**.
11. Reload custody history and confirm the report appears with the signed-in author and recorded time.

To correct a report, select **Correct this custody report**, enter the corrected account and reason, then save. The correction adds a record; it does not erase the earlier one. “No custody reports recorded” means earlier custody is unknown, not that custody was verified or uninterrupted.

## Read and filter transactions

### Choose the records to examine

1. Open **Transactions**.
2. Choose an account in **Account**, or leave **All accounts** selected. Expand **Search accounts or check which dates are used** if the account you need is not listed.
3. Enter **From** and **To** when restricting dates. Both endpoints are included.
4. Select **Apply**, or **Reset** to return to all accounts and dates.
5. The applied account and dates follow you between Transactions, Counterparties, Trends, Posting graph, Patterns and Case context during this visit. Read the scope displayed above the answer. Unsaved filter edits do not change the current result.
6. Check working and verified totals separately, by currency.

An ordering date is the date Loupe uses to place a reading in sequence. For some undated items it can be the statement end, not a known transaction date. Read the row's date basis before relying on exact timing.

![Transactions in a synthetic case](images/12-imported-transactions.png)

*Use the table and population labels to understand which readings the view contains. Example amounts in this guide are synthetic.*

### Search and sort payments

1. Type a description, name or reference into **Search payments**.
2. Choose **Currency** if you want one currency.
3. Open **More filters** to enter a minimum or maximum amount. Choose a currency first. Both amount limits are included.
4. Use **Money in or out** to show credits or debits. For a credit card, check the row's card explanation before interpreting these as cash movements.
5. Use **Sort payments** to change the order. Amount sorting needs one currency.
6. Use **Previous ledger rows** and **Next ledger rows** when there are more than 50 matches.
7. Select **Clear payment filters** to remove the search, currency, amount and sort settings. The account and date filters above remain as you applied them.

The total labelled **Payments matching your filters** covers all matching table pages. It changes when you search. It does not include unprocessed PDFs. Changing currency clears the previous amount range.

### Open a payment and its source

1. Select a payment's description or **Open transaction**.
2. Read its date, amount, recorded payer or payee and bank reference.
3. Use the source controls to open the original document. Where a precise location is available, the relevant value is highlighted.
4. Use **Correct a value** if a recorded field is wrong, or **Add investigation note** to record a question or observation.
5. Close the detail panel to return to the same payment list.

### Record an investigation note

1. Select **Add note** beside a transaction, or **Add investigation note** in its details.
2. Type your observation in **Your transaction note**.
3. Select **Save investigation note** and wait for **Note saved**.
4. Open **Findings** to reopen it, or use the link to Workspace to edit it.

Unfinished note text stays in this browser tab when you close and reopen the details. Save it before closing the browser tab. A saved note is linked to the transaction and its statement. Later corrections do not rewrite the source reference you were discussing.

### Save several payments together

1. Tick the checkbox beside each payment you want to discuss together. You can select up to 100.
2. Alternatively, use **Select matching payments (up to 100)** after searching.
3. Read the selected-payment totals. If selected payments fall outside the account/date range now displayed, the screen tells you how many will still be included.
4. Select **Save selection with a note**.
5. Enter **Name for this selection**, such as “Payments to supplier in March”.
6. Under **What did you notice?**, explain the question or observation.
7. Select **Save payments and note**. Wait for the saved confirmation.
8. Open **Findings** and find your title. Select a linked payment to inspect its source again.

The saved selection keeps the payment values as they were when saved. Opening a linked payment shows its current record or correction history. A colleague with access to the case can read the saved note; your unfinished browser draft is not shared.

![Saved notes and payment selections](images/15-financial-findings.png)

*Use Findings to return to investigation work. Each entry keeps its note and supporting records together.*

## Correct a reading or change its inclusion

### Correct a transaction

1. Locate the payment in **Transactions**.
2. Select **Open transaction** and compare it with its original statement.
3. Select **Correct a value**. Its current fields are filled in. Correct the printed date, description, counterparty, reference, transaction type, amount, direction or balance as needed. Leave an unprinted date or balance empty; at least one date is required.
4. Select **Preview correction**.
5. Read **Changes to record** and compare the before and after statement controls. Read any warning that the document will be excluded from verified totals or the replacement remains held out.
6. Enter **Reason for correction**, identifying the source and the error.
7. Select **Record correction** in the preview.
8. Read the saved outcome, then inspect **Change history** and the original/replacement readings.
9. Reload the affected ledger and analysis views before using their totals. Recalculate any saved scenario you intend to use with the new readings.

For example, correcting a misread `61.26` to printed `61.62` creates a replacement. The original reading, source and reason remain available. Do not treat a saved export made before the correction as a current report.

### Hold a row out or restore it

1. In a transaction's details, select **Exclude from totals**. To restore one, open **More financial tools**, then **Excluded transactions**, and use the inclusion action beside the row.
2. Read the current status and proposed action.
3. Inspect its source and previous decisions.
4. Enter the reason for the permitted action and confirm it.
5. Read whether anything was actually changed.
6. Check both the ledger and **Excluded transactions** after refreshing.

Restoring a row does not automatically make it verified. A correction or another exclusion may still affect its eligibility. If the application says someone changed the record since you opened it, reload and reassess the current record instead of resubmitting a stale form.

### Read the decision history

Open **Change history**. Expand the relevant decision to inspect the reason, actor, time and affected records. For corrections, use **Original and replacement readings** and the available balance comparisons. Historical checks describe the records at that time; inspect current **Statements** for the latest checks.

## Check statements and missing periods

The top of **Statements** lists the accounts recorded in this case, with their holder, account number, bank and currency. Use **Find an account** to search those details. Select **View all transactions** on an account to open its payments across all recorded dates. Missing account details are shown as not recorded.

1. Open **Statements**. Balance checks and date coverage load automatically.
2. Read each period's account, currency and recorded bounds.
3. In **Statement balance checks**, compare opening balance plus money in minus money out with the recorded closing balance.
4. Expand **Recorded check and source details** for the period.
5. Open the printed balance and date sources. Compare running balances and direction totals where available.
6. If a difference appears, inspect candidate causes and their source rows. Treat suggestions as places to look, not automatic corrections.
7. Correct an actual reading error through the ledger. Refresh the checks afterward.
8. Use **Previous statement checks** and **Next statement checks** to inspect all periods.
9. If retaining the displayed checks, select **Download this page of statement checks**. Repeat for additional pages you need; that download contains the displayed page, not every statement.

![Statements controls in the development case](images/07-statements.png)

*The Statements tab separates balance checks from date coverage. Results load when you open the tab; use **Refresh balance checks** and **Refresh statement coverage** to refresh them after changes.*

A balanced period only establishes agreement for the recorded controls and rows. Missing equal-value incoming and outgoing transactions could leave a balance unchanged. Continue checking source coverage.

### Inspect native bank-file checks

If native bank-file records have been loaded through a supported ingestion process, select **Recheck native bank-file controls** and inspect the current results. These checks concern the available native source and its recorded structure. They do not manufacture missing native evidence from a PDF. Ask the administrator about loading native formats; the PDF upload control is not a general bank-file importer.

### Inspect gaps, overlaps and requested coverage

1. Inspect the loaded coverage results, or select **Refresh statement coverage** to refresh them. Read the account entries and use the coverage pagination to reach the account you need.
2. Inspect the recorded periods, gaps and overlaps.
3. Open the period's source dates to verify that the bounds were recorded correctly.
4. For a specific question, apply the relevant account and date range in the ledger and read its requested-coverage result.
5. Record periods that are missing, unknown or unavailable before interpreting an empty transaction search.

An overlap may reflect repeated statements or deliberately overlapping records. A gap in recorded periods is a reason to seek or inspect evidence. Neither result proves the presence or absence of every individual transaction.

## Review duplicates

### Compare documents in this case

1. On **Import review**, find **Duplicate candidates** and select **Compare documents**.
2. Inspect the compared account and period coverage, source hashes and stored readings.
3. Open both original sources. Check whether the documents represent the same evidence and whether one has information the other lacks.
4. Read matching source hashes across different or missing coverage separately. Identical bytes do not make two differently reviewed scopes interchangeable.
5. If excluding a duplicate is justified, use the available exclusion action and give a reason identifying the copy you are retaining.
6. Check the decision confirmation, current ledger totals and **Change history**.

For a bulk exclusion, inspect every selected document before confirming. Keep at least the intended retained evidence and read the affected counts. Do not exclude candidates solely because their amounts match.

### Restore a duplicate exclusion

Open the recorded duplicate decision and its restore action. Read which rows can return, enter the reason and confirm. Only rows held out by that particular exclusion return. Corrected or separately held-out rows are not automatically restored. Both copies may count afterward, so recheck the ledger.

### Compare with another case

1. Expand **Compare with another case**.
2. Select **Choose comparison case**, then choose a different case you can view.
3. Run the comparison using the offered control.
4. Inspect matching sources and recorded coverage in each case.
5. Use **Open comparison case financial review** to inspect the other case when necessary.

A cross-case match does not merge cases or give access to restricted records. If the case is absent from the list, ask the case owner about access rather than copying data into a different case to bypass it.

## Investigate names, accounts and trends

### Compare people and businesses

1. Open **People and businesses**.
2. Apply the account and dates for your question. The totals load for that selection.
3. Read the totals and choose a currency for the chart if necessary.
4. Select **View payments** beneath a name, or select that name's payment button in the chart.
5. The payment list shows dates, descriptions and amounts. Open a payment to inspect its source or add a note.
6. Select payments and use **Save selection with a note** to keep your observation in Findings.

The same printed name can refer to different people. Different spellings can refer to the same person. Open **Link different names for the same person or business** when you have evidence for a link. Additional choices, including **Verified payments only**, are under **Analysis settings, statement coverage and downloads**.

### Link accounts to a reviewed person or organisation

1. In **Transfers**, load the comparison, scroll to **Money entering and leaving an account group** and select **Review account-to-party links**. This opens **People and organisations linked to accounts**.
2. Reload the links and inspect existing decisions.
3. Select the accounts you intend to link.
4. Choose an existing party or **A new person or organisation**.
5. Enter the new name if applicable and **Reason and supporting evidence**.
6. Select **Save account links**.
7. Reload and inspect the saved links and history.

To undo a link, select the accounts, choose **Remove the existing links**, provide a reason and save. The original printed names and identifiers remain unchanged.

### Link payment readings to a reviewed identity

1. Open **Review people and organisations on payments**.
2. Search names, descriptions or references.
3. Inspect the sources of the readings you want to link.
4. Select those readings explicitly.
5. Choose an existing reviewed party or enter a new party name.
6. Enter **Reason and supporting source interpretation**.
7. Select **Save payment identity links** and inspect the saved history.
8. In counterparty analysis, select **Combine names I have linked to the same person or business** if you want totals grouped by those decisions.

Name suggestions help find possible links. Check each suggestion's explanation and competing identities before selecting it. Links apply to the selected readings, not automatically to every future payment with a similar name. Use **Remove the selected links** with a reason when undoing them.

### Inspect the payment graph

1. Open **More financial tools**, then **Payment graph**.
2. Apply the account and dates you need.
3. Select **Show connections** if they have not loaded.
4. Select an account or name in the graph, or use **Choose an account or name**.
5. Open its connected payments. Select individual payments to inspect their statements or save them with a note.

Each arrow represents a recorded payment. The outgoing and incoming sides of a transfer can therefore appear separately. Use Transfers when you want to compare them as one movement.

### Read trends

1. Open **Trends** and apply the account and date filters.
2. Choose daily or monthly under **Group payments by**.
3. Select **Show totals** if the results have not loaded.
4. Compare credits and debits for the selected currency. Select a period's payment button in the chart to inspect that period.
5. Open a payment, or select several and save a note explaining the change you want to investigate.

Check Statements for missing periods before interpreting a peak or fall. A large transfer can also change a period's totals without representing income or spending outside the account group.

### Compare payments with case events

1. Open **More financial tools**, then **Payments and case events**.
2. Apply the account and dates. The account selection limits payments; the date selection also limits case events.
3. Select **Load payments and case events**. If events fail to load, payments remain available and a message explains the failure.
4. Use **Search this timeline** and **Show** to narrow the display.
5. Select **Open payment** or the event's button to inspect its evidence.
6. Tick the payments and events you want to discuss. Select at least one payment.
7. Select **Save this analysis with a note**, enter a title and observation, then select **Save payments and note**.
8. Reopen the entry in **Findings**. Its payment and case-event references are both attached.

Nearby dates do not prove a connection. Events with unusable dates may be absent from the ordered list. The timeline download retains those original records for inspection.

## Compare possible transfers

### Find and inspect possible pairs

1. Open **Transfers**.
2. Enter **From ordering date** and **To ordering date**.
3. Choose working or verified readings.
4. Set **Date tolerance** to the number of days appropriate for the comparison you want to test.
5. Select **Find possible transfers**.
6. Inspect each proposed outgoing and incoming pair. Open both source readings.
7. Compare the amount, currency, account, actual date basis and any payment-reference evidence.
8. Inspect competing partners for a posting before selecting a pair.

![Transfer comparison controls](images/04-transfers.png)

*Set the dates, population and tolerance before finding possible transfers. Matching values are candidates for inspection.*

Matching amounts and compatible dates suggest a possible pair. They do not prove that one funded the other. Supported identifier comparisons show their scope; an identifier match outside a supported date or format should not be treated as stronger evidence than the screen reports.

### Calculate a separate pairing scenario

1. Select the pairs you want to test. A posting can be used only once.
2. Under **Why do you think these payments are transfers?**, explain the supporting evidence and any uncertainty.
3. Select **Compare totals using these transfers**.
4. Read the conditional movement totals and exclusions.
5. Select **Save this analysis with a note** to keep the selected payments, comparison and your explanation in Findings.
6. Use **Download scenario with source references** when you also need the calculation file.

The selected pair counts once in this scenario. The original incoming and outgoing ledger postings remain unchanged.

### Examine money entering and leaving an account group

1. In the scenario's **Money entering and leaving an account group**, select the accounts to examine together.
2. If using saved party links, check exactly which linked accounts are present in the loaded scope.
3. Read internal movements separately from external incoming and outgoing amounts.
4. Inspect unpaired postings that could still be internal transfers.
5. Select **Download account perspective and assumptions**.

Your account group stays selected when you move between financial tabs. Accounts with no transactions in the current date range are listed as outside that range and do not contribute to its totals. Use **Clear account group** to start another selection. Refreshing the browser clears this temporary selection; saved account-to-party links remain recorded.

Only selected pairs inside the chosen account group are treated as internal. An unidentified internal movement can remain in the external comparison until reviewed.

The working or verified selection follows you between Trends, Counterparties, Posting graph, Transfers, Patterns and Case context. The Transactions tab remains the full current transaction record, with its own visible table filters; switching an analysis to verified-only does not remove imported records.

## Review patterns and payment claims

### Screen patterns

1. Open **Patterns**, then **Review patterns** if the claim comparison is showing.
2. Choose the population and apply the account/date scope.
3. Set **Screening window days**.
4. For a split-payment check, enter **Threshold amount** and **Threshold currency**. Leave the amount blank to omit this check.
5. Enable **Screen paths between accounts** if you want to inspect the supported short transfer paths.
6. Select **Find patterns**.
7. Inspect every relevant candidate's source readings, timing and alternative explanations.
8. To retain a theory, enter **Theory title** and **Reasoning and alternative explanations**, then select **Save explanation and supporting payments**.
9. Select **Open Workspace** to confirm the theory and supporting attachments were saved.

![Pattern review controls](images/06-patterns.png)

*The optional amount threshold is your chosen search criterion. The result is a set of readings to investigate.*

Repeated-name results include payments with different amounts. They require at least three payments to or from the same recorded name, in the same account and currency, on at least three dates. The short day window applies to the other related-payment checks.

Repeated names, equal amounts, quick incoming/outgoing movements and split payments can have ordinary explanations. A threshold you choose is not automatically a reporting threshold, and a candidate is not a finding about intent.

### Compare a stated payment with the records

1. In **Patterns**, select **Compare payment claim**.
2. Find and select one account, then apply the account selection. The claim form supplies the date range for this comparison.
3. Copy the person's exact words into **Original quotation**.
4. Use the source picker to attach the document containing those words and its location.
5. Enter the amount and date ranges supported by the quotation. Preserve uncertainty, such as “about 500” or “during March”.
6. Choose **Claim currency** and record your interpretation of the account holder and payment direction in the available fields.
7. Enter **Basis for the ranges and account interpretation**.
8. Choose the comparison population and any additional tolerance. Zero tolerance compares the entered range exactly.
9. Run the comparison and inspect the matching readings and sources.
10. Select **Download claim comparison with sources**.
11. If recording your response, use the accompanying decision controls, explain agreement or disagreement and select supporting attachments. Confirm the resulting note in Workspace.

The **Minimum tolerance (whole currency units)** field takes whole units. For example, enter `1` for GBP 1.00, not `100`. The extra amount tolerance is the larger of the percentage of the range midpoint and the stated minimum. A non-match can result from incomplete records. The claim remains separate from ledger totals.

## Trace funds in one account

Tracing asks how selected calculation rules allocate money under assumptions you supply. Begin only after checking the account's readings, dates and source coverage.

### Load the account

1. Open **More financial tools**, then **Trace funds**.
2. Select **Trace one account**.
3. Find and select one account.
4. Enter both ordering-date bounds and select **Apply ledger filters**.
5. Choose **Tracing population**.
6. Select **Load tracing inputs**.
7. Inspect the loaded currency, rows, excluded records and missing-evidence notices.

![Conditional tracing entry screen](images/05-tracing.png)

*Choose one account and date range before loading inputs. Tracing results depend on the assumptions you enter afterward.*

### State the assumptions and calculate

1. Enter the opening amount for the start of the selected period.
2. Explain the opening amount's basis. If it is unknown, obtain evidence or describe an explicitly hypothetical scenario rather than silently using zero.
3. Add a deposit attribution: choose **Attributed deposit**, enter a **Claim label**, enter the attributed amount and explain the **Attribution basis**.
4. Repeat for further deposits or claims. Do not allocate more than a deposit's recorded amount. Opening funds remain unattributed in this form.
5. Review the order of the movements. Use **Move earlier** only for the permitted same-date changes.
6. Record the basis for your assumed order. The display order is not proof of a bank's same-day processing order.
7. Select the calculation methods to compare.
8. Select **Calculate conditional scenario**.
9. Read each method's result, warnings and unidentified withdrawals.
10. Open **Save this calculation in Findings**, enter a name and note, then select **Save calculation and note**.
11. In **Findings**, select **Open saved calculation** to reopen the assumptions, results and source references. You can download its readable report there. Reopening does not recalculate it using later corrections.

### Understand the calculation choices

| Method shown | How to read its role in your scenario |
|---|---|
| Lowest intermediate balance | Uses money not assigned to a claim first. Once claimed money is spent, later deposits do not restore it. |
| First in first out | Allocates withdrawals against earlier money before later money. Same-day order can affect the result. |
| Last in first out | Allocates withdrawals against later money before earlier money. Same-day order can affect the result. |
| Direct amount matching | Matches the funded part of a withdrawal only when one available deposit or attributed portion has that amount. No unique match leaves it unidentified. Equal amounts alone do not prove origin. |
| Pro rata | Allocates a withdrawal proportionally across the available components under the calculation's rules. Inspect rounding in the detailed output. |

Use the methods offered by the selected screen and record why you are comparing them. Loupe does not decide which method should govern the case. If methods produce different answers, retain that difference and explain the assumptions rather than presenting only the most favourable number.

Editing an assumption clears a stale result. Calculate again and save a new scenario. A downloaded scenario is a record of its captured inputs; it does not update when the live ledger changes.

## Trace funds between accounts

1. Open **More financial tools**, then **Trace funds** and **Trace between accounts**.
2. Enter **Trace from date**, **Trace through date**, population and transfer date tolerance.
3. Select **Load cross-account inputs**.
4. Choose the currency if more than one is present.
5. Enter an opening amount and opening basis for each account.
6. Inspect possible transfer pairs and both sources. Select the pairs to use, without reusing a posting.
7. Enter **Basis for selected transfers**.
8. Attribute root deposits to claims using their amounts and supporting basis. A receiving credit already selected as a transfer is not a separate root attribution.
9. Inspect the movement order and enter **Basis for cross-account order**. In ordinary forward timing, the selected receiving credit must follow its outgoing side.
10. Select the methods to compare.
11. Select **Calculate cross-account scenario**.
12. Read the results by method, account and transfer step, including all warnings.
13. Use **Save this calculation in Findings** to keep the assumptions and results with your note.
14. Select **Download cross-account scenario**, or download its readable report or audit package when required.

The calculation retains each account's original movements. It does not rewrite ledger dates or confirm ownership.

### Test backward timing only when you can explain it

If you need to test an earlier receiving entry against a later payment, select **Allow backward transfer timing** and enter **Basis for backward timing**. Inspect the resulting backward-timing labels. This is an explicit hypothesis about timing, not proof of causation. Circular account dependencies are refused. Do not change a printed date to force a forward result.

## Record asset purchases and resale assumptions

Use these controls within a loaded tracing scenario when you have evidence about how a withdrawal was used.

### Add a purchase interpretation

1. Expand **Optional asset-use interpretations**.
2. Select **Add asset interpretation**.
3. Choose the **Source withdrawal**.
4. Enter the **Asset description**.
5. Enter the amount funding the asset where only part of the withdrawal was used. When several purchases share one withdrawal, give an explicit amount for each.
6. In **Basis and source interpretation**, identify the purchase evidence and explain the allocated amount.
7. Check the order of multiple asset interpretations. Allocation and rounding follow the displayed order.
8. Recalculate the scenario and inspect **Conditional asset-use allocations** by method.

A selected transfer cannot also fund an asset in this form. Allocating a withdrawal to an asset does not establish ownership or current value.

### Add a full-disposal resale interpretation

1. In the relevant asset interpretation, select the available resale option.
2. Choose a later **Resale receipt** from the scenario.
3. Enter **Proceeds attributed to the full disposal**.
4. Explain the evidence for full disposal and the proportional allocation basis.
5. Recalculate and inspect **Conditional resale value substitution** separately from cash results.

The receipt already appears in the cash calculation. The resale interpretation does not add another receipt. Do not add the asset or resale result to cash as though it were additional money. The entered proceeds are allocated according to each method's acquisition-cost components, including a gain or loss under that assumption.

## Prepare an indirect financial workpaper

An indirect workpaper compares amounts from your evidence, such as assets, deposits or spending, when payment records alone do not answer your question. You enter the amounts, explain how you arrived at them and record the checks you performed.

1. Open **More financial tools**, choose **Trace funds**, then select **Indirect review methods**.
2. Choose a method from **Method**.
3. Enter the subject, currency and review dates.
4. Select **Search indirect sources** to find supporting files in the case.
5. For each amount field, enter the assessed amount, select its supporting source, give the page or section and explain how you arrived at the amount.
6. Use **Inspect source** to check the referenced file.
7. Enter an explicit zero only when supported. Leave unknown values unresolved.
8. Complete each required review item with its source, location and work performed. Mark it reviewed only when you have done that work.
9. Select **Calculate indirect workpaper**.
10. Read the missing-item list or resulting conditional difference.
11. Select **Download indirect workpaper** to retain it.
12. Select **Save workpaper in Findings** to keep the calculation with the case. Open **Findings** to see the saved workpaper. It is also available in Workspace.

![Indirect review form](images/08-indirect-review.png)

*Enter assessed amounts and their sources. Required review items ask what work supports the calculation.*

| Method | Information you must assess and enter |
|---|---|
| Net worth | Opening and closing assets and liabilities, personal outlays, non-taxable adjustments, applicable deductions and reported income. |
| Bank deposits | Deposits, expenditure outside deposits, changes in cash, transfers and other non-income items, costs, expenses, adjustments, deductions and reported income. |
| Expenditure | Money spent or applied, non-taxable funding, applicable deductions and reported income. |
| Cash-T | Reviewed cash uses and known cash sources, including opening cash and non-taxable sources. |

The required review covers starting assets and cash, non-income explanations, reasonable alternative leads, and the accounting and other applicable basis. Loupe does not supply deductions or investigate these explanations for you. A completed form is not independent verification of the entered amounts.

### Reopen a saved workpaper

1. Open **Findings**.
2. Use **Search saved work** to find the subject or name of the workpaper.
3. Select **Open saved workpaper** on its note.
4. Check the subject, dates, currency and calculated difference at the top. If the work was incomplete when saved, read **Still to complete**.
5. Read **Amounts used in the calculation**. Each item shows its amount, your explanation and the recorded source location.
6. Use **Open source:** followed by the filename to open the supporting file. Close the file viewer to return to the workpaper.
7. Read **Recorded checks** to see what was marked reviewed and the explanation saved with each check.
8. Select **Download workpaper report** for a readable HTML file containing the saved amounts, checks, result, note and source references. Open it in a browser to read it or use Print to save it as a PDF. The original files are not included.
9. Use **Download workpaper data** if you also want the JSON calculation file for restoring in Loupe.

The viewer shows the calculation as it was saved. It does not recalculate using later transaction corrections. Workpapers saved before this viewer was added can also be opened, provided their method still matches the available definition. If a calculation or its attached sources cannot be checked, Loupe shows an error and retains the original note.

![Saved workpaper with its result, input amounts and source buttons](images/15-saved-workpaper.png)

*Open a source to check an amount, download the workpaper report, or create a revised copy.*

### Change a saved workpaper

1. Open the saved workpaper and select **Create revised copy**.
2. A separate editing form opens under the original note in Findings. The original workpaper remains saved.
3. Change the subject, dates, amounts, explanations or supporting files as needed.
4. Select **Calculate indirect workpaper**. Read the new result or complete any missing items. Changing a field clears the previous result.
5. Select **Save workpaper in Findings**. A new note is created with the revised calculation and a link to the original workpaper.
6. Open that new note to check the saved result.

Use **Hide revised copy** to fold away the editing form and **Continue revised copy** to return to it. Changing financial tabs retains the form. Save before refreshing the page, leaving the case or closing the browser; an unsaved copy is not a shared case record.

To resume a downloaded calculation file instead, open **Indirect review methods**, find **Restore a downloaded workpaper** and select the original JSON file. Check the restored subject, dates, inputs and result before editing. Changing a field clears the old result until you calculate again.

## Download reports and supporting records

### Make a report from a saved note

1. Open **Findings** and find the note you want to report.
2. Expand **Create a report from this note**.
3. Read what will be included. The report covers that note and its attached payment values and references.
4. Choose **Download this note and its payments** for a readable HTML file without original PDFs. Open the file in a browser. Use the browser's Print command if you need to save it as a PDF.
5. To include the supporting PDFs, review the listed files and select **Download report with source PDFs**.
6. Extract the downloaded ZIP. Open `report.html`. Its source links open the originals in the `statements` folder. `references.json` records the note version and file references.
7. Check the content before sharing. Each included PDF is the whole original file and may contain other statement periods.

The PDF package supports up to 20 files and 64 MB in total. Loupe checks the downloaded file bytes against their recorded hashes and stops if a source has changed. A saved note's payment values describe the time it was saved. Open its linked payments in Loupe to inspect later corrections.

For a saved tracing calculation, use **Open saved calculation**, then **Download readable tracing report**. The general note report does not replace the detailed tracing report.

### Choose the right output

| You need to give someone | Use |
|---|---|
| Current ledger rows, totals and recorded source/review history | Ledger snapshot ZIP. |
| A particular searched and sorted table | Table-view export, with its separate table scope. |
| A readable ledger report | HTML inside the ZIP, or select the PDF option before downloading. |
| Original referenced files | Select the originals option before downloading the ledger export. |
| Tracing inputs and calculated alternatives | Conditional scenario JSON and readable tracing report. |
| A checked collection of tracing support | Tracing audit ZIP or assembled review package. |
| Selected statement checks | Download this page of statement checks. |
| An indirect review calculation | Save workpaper in Findings to reopen the calculation and its sources. Download indirect workpaper keeps its JSON file. |

ZIP is a container of files. HTML is a report you open in a browser. JSON retains structured records for checking or reusing in Loupe's supported tools; you do not need to edit it to read the HTML report.

### Download a ledger snapshot

1. Open the ledger or documentary Transactions and apply the required account/date filters.
2. Read the applied scope and totals before exporting.
3. Choose the offered marking: No privilege marking, Confidential, or Privileged and confidential. Select the marking appropriate to your instructions; choosing it does not establish a legal status.
4. Select the PDF option if you need a paginated readable report.
5. Select the originals option if the recipient needs the complete referenced source files.
6. Select **Include wider case financial review history** if you need records beyond the selected ledger, including pending PDF readings and recorded case audit events.
7. Select **Download ledger snapshot**.
8. Wait for the download to finish. If source or integrity checks fail, investigate the stated issue rather than treating a partial download as complete.
9. Open the ZIP from your browser's downloads list or your computer's Downloads folder. Extract the entire ZIP into one folder so related files stay together.
10. Open `ledger-report.html`. If requested, open the included PDF too.
11. Check the case, exporter, preparation time, marking, account/date scope, populations, totals and limitations.
12. Retain the original ZIP as well as any extracted viewing copy.

The PDF option supports up to 2,000 captured readings. The originals option supports up to 100 files and 64 MiB. If a limit is exceeded, use a narrower documented scope or omit the optional PDF/originals as appropriate, then retain the needed separate captures. Do not describe several partial captures as one complete case export without checking their coverage.

Originals are complete files. They may contain pages outside the selected account or date range. Review that scope before sharing. When originals are included, Loupe checks their bytes against the saved hashes. When they are not included, a recorded source hash is not a fresh check of the original file.

Wider case history is intentionally broader than the selected ledger. Read the captured scope before sharing it. It does not add pending or rejected readings into the ledger totals.

### Export a searched table

1. Apply the main account/date filters.
2. Set the table search, currency, amount bounds, direction, proof class and order.
3. Open **Download these transactions** below the table and choose its PDF, originals and history options as needed.
4. Download the table-view export.
5. Inspect its captured search and order in the report.

The table capture includes every matching table page, not just the page visible on screen. The bundle also contains the fuller applied account/date snapshot. Its main totals refer to that fuller scope. Distinguish those totals from the searched table's population when describing the report.

### Download tracing reports

1. Calculate the single-account or cross-account scenario.
2. Download its scenario JSON first and retain it unchanged.
3. Use the tracing report controls to choose a marking and download the readable report.
4. Open the HTML report in a browser and check the assumptions, method alternatives, source references and any asset/resale tables.
5. Use the tracing audit download when you need the scenario, recalculation record and supporting files together.

The report explains the calculated scenario. It does not establish ownership, complete custody, independent extraction accuracy or an expert's opinion.

### Assemble a review package

The assembly controls are available with the ledger export tools.

1. Open **Assemble a review package**.
2. Under **Saved tracing scenarios (JSON)**, choose between one and eight scenario files you want included.
3. Optionally select a **Saved ledger export (optional ZIP)** from the same case.
4. If you have completed independent extraction validation, attach its reconciled review record and corresponding extraction predictions together. Do not substitute ordinary notes or a software test log.
5. Choose the review package marking.
6. Select **Prepare and download review package** and wait for the checked ZIP.
7. Extract the ZIP and open `review-index.html`.
8. Check the listed inputs, each capture's scope, method results and any validation or custody information. If you attached a ledger export containing support records, **Saved ledger methods, versions and decision references** opens an unchanged copy of that saved index. Older exports may not contain it.
9. Read **Recorded statement processing**, where present, for the software versions recorded when those pages were extracted. A missing version remains **Not recorded**; it is not replaced with the version running today.
10. Retain the ZIP and original input files.

The index links the retained files and keeps their scopes separate. Assembly does not merge ledger rows or make different captures contemporaneous. Enclosed files retain their original markings. Synthetic validation remains labelled synthetic. Missing measurements remain missing.

## Compare and check saved packages

### Compare two ledger exports

1. Open **Compare saved ledger exports** beside the export tools.
2. Select the **Earlier ledger export** and **Later ledger export** from the same case.
3. Select **Compare captured exports**.
4. Read differences in filters and scope before reading row changes.
5. Inspect readings reported as changed, added or absent.
6. Select **Download full export comparison** to keep all details, beyond the first references shown on screen.

A row absent from a later filtered export may still exist unchanged in the case. Different captured filters are not evidence of deletion. Comparing saved exports does not change the current ledger or add those ZIPs as case evidence.

### Check a saved tracing audit package

1. Open **Check a saved tracing audit package**.
2. Choose the **Tracing audit ZIP**.
3. If you retained its SHA-256 separately when it was prepared, enter it in **Previously saved SHA-256**. Otherwise leave the field blank.
4. Select **Check package**.
5. Read the file checks and recalculation result separately.
6. Inspect any changed output paths or package-description differences.
7. Select **Download verification** and retain it with the package.

SHA-256 is a file fingerprint: changing the bytes changes the fingerprint. A fingerprint kept separately helps identify replacement of a whole package. Matching a package's own internal list alone does not establish who supplied it.

A calculation can match under a different code revision. The verification reports that separately. A different calculated amount needs investigation. Do not edit the saved files to make a check pass; keep the original and ask the case lead or administrator to inspect the difference.

### Understand recorded history and timestamps

Exports can include recorded decisions and an audit chain, which links recorded events so alterations or gaps can be checked. It describes captured history from the point those records were introduced, not invented earlier events.

External timestamping is an administrator-operated process, not a button an investigator must find on these screens. If your case requires it, give the administrator the case and retained export you want covered, and ask for the retained verification record. Do not assume it runs automatically. A timestamp can support when a particular captured record existed; it does not verify the financial facts inside it.

## Stop work and return later

| Work | What to do before leaving | What to do on return |
|---|---|---|
| Unconfirmed normal statement review | Look for the message that the review is saved in this browser tab. | In the same tab, reopen the same file, statement period and currency. The draft restores if its source revision has not changed. Closing the tab may discard it. |
| Imported statement | Wait for import confirmation. | Open Transactions or reopen the uploaded statement. |
| Transaction note | Select Save investigation note and wait for Note saved. | Open Workspace, then Casework and Notes. |
| Selected PDF rows in advanced review | Select Save selected rows for review and wait for confirmation. | Open PDF readings, find the saved batch and open its readings. |
| A review decision | Record resolved reading or Reject reading and check the confirmation. | Reload the batch and use the saved progress and pending filter. |
| A partially filled statement | Use Save unfinished statement editor. | Load unfinished statement editor. |
| Statements already added to a preview | Save statement controls to case. | Load saved statement controls and inspect them. |
| Custody or identity decisions | Save and confirm the recorded history. | Reload the relevant history before adding or changing anything. |
| A tracing calculation | Save this calculation in Findings, then wait for confirmation. Download a report if needed. | Open Findings, then Open saved calculation. Use Trace funds to calculate a new result with current records. |
| A transfer comparison | Save this analysis with a note. | Open Findings to review its selected payments and explanation. |
| A selected set of payments | Save selection with a note and wait for confirmation. | Reopen the named entry in Findings. |
| An indirect workpaper | Save workpaper in Findings. Download it if you also need the calculation file. | Open saved workpaper in Findings, or restore the downloaded file. |
| A pattern theory or claim response | Use the provided Workspace save action and confirm the entry. | Open Workspace and inspect the saved entry and attachments. |
| A ledger report | Wait for the completed download and retain the ZIP. | Open the retained report or prepare a fresh capture for current records. |

Switching financial tabs keeps visited forms and analysis results during that page visit. Statement drafts and unfinished note text also have browser-tab storage where the screen says so. These are not shared case records. Save your notes and calculations before closing or refreshing the browser; uploads or calculations still running can be interrupted.

If a save's outcome is uncertain, reload the saved record first. A repeated click is not a reliable way to find out whether the first request succeeded.

## Solve common problems

| Problem | What to do |
|---|---|
| I cannot see the case | Check that you signed into the correct server and account. Ask the case owner to check access. |
| I can read but cannot save | Ask for case editing access. Keep a note of the intended decision and source location. |
| There are no prepared PDF pages | Check the correct file's preparation status. Preparation must complete before stored tables can be selected. |
| The PDF has unreadable or misplaced text | Compare the original page with the stored table. Review OCR results carefully. Keep unsupported readings pending and report the page. |
| Scan results omit a page | Read its unchecked or ambiguous reason and inspect the page manually. Scan results do not establish full-document coverage. |
| AI reports authentication or provider failure | Use manual review where possible. Ask the administrator to check the server's configured provider. Do not paste a key into a case note. |
| A model attempt appears stuck | Check its saved status. Follow the same-request retry or interrupted-attempt controls; avoid repeated fresh requests. |
| The amount is zero | Inspect the source. A printed zero can be a valid reading; a missing or illegible value is unknown and should not be entered as zero. |
| No account matches | Search more narrowly, inspect the account references and create a clearly reasoned provisional account if justified. |
| A date is ambiguous | Inspect all cited date cells and the period context. Keep the type or year unresolved rather than guessing. |
| Finalization is disabled | Read the preview errors. Check pending rows, incomplete-coverage acknowledgement, finalization reason, source changes and statement controls. |
| I forgot pages after finalizing | Preserve the existing finalization and tell the case lead which pages were missed. Do not delete or blindly reimport to bypass the seal. Plan a separately identified supplementary review with duplicate checks. |
| Verified totals are zero | Inspect working totals and evidence classes. Finalized manual PDF readings remain P3. |
| A statement does not balance | Open printed controls and source readings. Check direction, account section, missing fees, duplicates and actual errors before correcting. |
| A period balances but rows are missing | Review page and row coverage. Matching balances do not prove that every transaction was captured. |
| A saved decision conflicts with another change | Reload the current record and its history, then make a new decision against that version. |
| A tracing result disappears | An input changed. Review the new assumptions and recalculate; use the earlier download for the old result. |
| A transfer has several possible partners | Open all relevant sources. Leave the choice unresolved unless you can explain a specific hypothesis. |
| The export says a source changed or is missing | Retain the message and source reference. Ask the administrator to inspect the stored file. Do not replace the source just to pass export checks. |
| A PDF export exceeds its limit | Narrow and document the scope, or download the non-PDF capture and prepare appropriately scoped reports. |
| A package check fails | Keep the original ZIP and verification result. Report the exact failure and avoid sharing it as a verified package. |
| A list says its count disagrees or data is incomplete | Treat it as a partial answer. Record the message and do not describe its total as the full case. |

### Inspect recorded loading attempts

1. Open **Processing history**.
2. Find the relevant attempt and read its status, start and end times.
3. Compare **Documents seen**, **Rows admitted** and **Rows set aside**. These are recorded attempt counts, not a guarantee that every source transaction was extracted.
4. If an attempt did not complete, inspect its available detail and any notice on the Ledger tab.
5. Give the administrator the attempt reference and status. Check what was already recorded before arranging another load.

PDF preparation status also appears in the PDF intake controls. Use the status for the action you actually submitted; the absence of a financial loading attempt does not prove that a PDF preparation job never ran.

### Inspect evidence classes

1. On **Import review**, find **Evidence classification** and select **Refresh classification**.
2. Expand **View all classes and their rules**.
3. Read the displayed counts and rules for automatic admission, required human decisions, whether the class may produce ledger rows and eligibility for totals.
4. Check held-out and superseded records separately before interpreting these counts as current usable readings.

The class is calculated from source and verification results. There is no control here to manually change a label to make a total count.

### Report a problem so someone can reproduce it

Give the case name, filename, PDF page or reading reference, the screen, the action taken, the expected result and the actual result. Include the displayed error and whether a refresh changed it. Add a screenshot if it helps, after checking what case information it contains. For an interrupted save, say that its outcome is uncertain so the record can be checked before retrying.

## Complete your case review

Before giving another person the financial work, check these items against the question you were asked to answer:

- [ ] The correct case and original sources are identified.
- [ ] Every intended page and account section has been inspected, or omissions are listed.
- [ ] Selected readings have recorded decisions; unresolved material is identified.
- [ ] Finalized coverage and any deliberately incomplete selection are explained.
- [ ] Printed controls and missing statement periods have been inspected.
- [ ] Duplicates, held-out rows and corrections have been reviewed.
- [ ] Names and transfer pairings are described at the level the evidence supports.
- [ ] Each quoted total identifies its currency, population and account/date scope.
- [ ] Each tracing result includes its opening amounts, deposit attributions, order and method assumptions.
- [ ] Asset or resale interpretations are not added to cash totals as extra money.
- [ ] Reports open correctly and show the intended case, scope and marking.
- [ ] The original ZIPs and scenario files are retained unchanged.
- [ ] Missing source history, provider acceptance or independent accuracy measurements are not described as completed checks.
- [ ] The next reviewer can find the sources, decisions and saved work without relying on your open browser session.

## Words used in Loupe

| Word | Plain explanation |
|---|---|
| Account perspective | The account from whose point of view money comes in or goes out. |
| Admitted | A row allowed into the relevant ledger status. Its evidence class still affects which totals include it. |
| Audit chain | Linked records used to check recorded event history for changes or gaps. |
| Batch | A saved group of selected PDF readings. |
| Candidate | A possible reading awaiting or undergoing review. |
| Capture or snapshot | A saved set of records and settings taken at one time. It does not change with the live case. |
| Conditional | The result depends on specified assumptions. |
| Counterparty | The other name or party recorded for a payment. A printed name is not automatically an established identity. |
| Custody | The reported receipt and handling of a source. |
| Finalization | The action that writes reviewed rows and seals that PDF reading against further candidate additions or edits. |
| Hash or SHA-256 | A fingerprint calculated from exact file bytes or recorded content. |
| Held out or quarantined | Kept outside normal ledger use pending or because of a recorded condition or decision. |
| Ledger | The stored financial readings used by the documentary financial views. |
| Minor units | Whole units of a currency's smallest recorded subdivision. For GBP, 6,162 pence means GBP 61.62. Use the displayed currency when reading raw figures. |
| Native file | Data supplied in its system's original structured format, rather than only a PDF view. |
| OCR | Reading characters from an image of a page. It can misread characters. |
| Ordering date | The date used to put a reading in sequence. Its basis may differ from the transaction date. |
| P3 | The class retained by manually reviewed documentary PDF readings in this workflow. They can be used in working analysis while remaining outside verified totals. |
| Population | The set of readings chosen for an answer, such as working or verified only. |
| Provisional | Recorded for working use while identity or other information remains unconfirmed. |
| Reconciliation | Comparing the recorded movements with opening and closing balances or printed totals. |
| Scenario | A calculation saved with its selected records and assumptions. |
| Source reference | The file, page, cell or other location supporting a reading. |
| Statement control | A printed date, balance or total used to check the reviewed statement. |
| Superseded | Replaced by a later reading while the original remains in history. |
| Verified totals | Totals restricted to the application's eligible verified population, not every reviewed row. |
| Workspace | The case area where saved theories, notes and workpapers can be retained with attachments. |

## Advanced manual review

Use these older controls for existing saved batches or an exceptional document that needs manual table interpretation. Start in **Import review**. For an ordinary new statement, use sections 3 to 7 instead.

#### Advanced: Add a PDF

#### Advanced: Upload and prepare a new file

1. Open **Financial**, then **Import review**.
2. Select **Open PDF readings**.
3. In **PDF document**, choose the PDF from your computer.
4. Check the filename and case name.
5. Select **Prepare PDF for review** once.
6. Wait for preparation to complete. This step reads the PDF and prepares text and table information. Scanned pages may require OCR, which reads letters and numbers from page images.
7. When **Choose prepared PDF rows** becomes available, select it.
8. Confirm that the available source pages belong to the correct file.

![PDF upload and preparation controls](images/02-pdf-upload.png)

*Choose a document, then prepare it. Preparation does not approve transactions or put amounts in the ledger.*

#### Advanced: Use a file already uploaded

1. Open **Open PDF readings**.
2. Select **Find uploaded PDFs**.
3. Choose the matching file from the results. Check its processing status as well as its name.
4. If the file is unprocessed, use **Prepare PDF for review**.
5. If preparation has completed, use **Choose prepared PDF rows**.

Do not upload repeated copies just because preparation is taking time. Check the saved status first. If the page reports a failed or interrupted attempt, note the filename and error before asking the administrator to investigate.

#### Advanced: Check whether preparation was useful

Open a page that contains transactions. Compare its stored text with the original PDF. Check a date, an amount and a description. Watch for missing decimal points, mixed columns, repeated headers and unreadable characters. A successfully prepared file can still contain extraction errors that need manual review.

### Advanced: Select possible transactions

#### Advanced: Select rows manually

1. In **Choose rows from a PDF**, select the file and page from the available source pages.
2. If the page has more than one stored table, use **Previous table** or **Next table** to find the transaction area.
3. Read the original page beside the extracted table.
4. Click a table value to locate it on the original. Use **Show table location** when you need to inspect the table area.
5. Assign the proposed meaning of each relevant column. Identify dates and amounts from the printed headings and values. Leave meanings unknown when the source does not support a choice.
6. Tick **Use row** only for rows you intend to review as transactions.
7. Check that you have not selected an opening balance, a closing balance, a heading, a subtotal or a disclosure paragraph as a payment.
8. Select **Save selected rows for review**.
9. Wait for **Rows saved**. Open the saved readings to check that the intended rows are present.

Use the source viewer's **+** and **−** controls to change zoom, **Fit source width** to fit the page area, and **Show highlighted value** to return to the selected source location when those controls are available. Zooming does not change the saved reading.

Clicking a value to inspect its location does not select its row. Selecting a row does not confirm the amount or direction. Saving rows creates a review batch, which is a group of selected readings you can return to later.

#### Advanced: Use printed headings and account references

The source selector can show proposals based on exact printed headings and labelled account references. Inspect the cited cell before accepting a column proposal. A generic **Date** heading does not tell you whether the date is a transaction, booking or value date.

A masked account number may identify a useful section of a statement without identifying the full account. Do not combine different card endings or account sections merely because they appear in one PDF. Keep separate provisional accounts where the evidence does not establish a shared identity.

#### Advanced: Scan a page range

1. Open the page scan controls in the source selection area.
2. Enter the first and last pages you want to inspect. Scan at most 50 pages in one request; repeat for the next range in a longer PDF.
3. Choose the scan currency.
4. Use automatic column proposals where supported, or identify the possible date and amount columns from the source.
5. Select **Scan selected page range**.
6. Read the result for each page. Some pages may have suggestions; others may be unchecked or ambiguous.
7. Open the supporting cells for proposed readings and compare them with the original.
8. In the queue controls, select the pages whose proposals you want to save for review. Include undated fee and interest proposals only when you intend to review those separately.
9. Save the selected proposals using the queue's save control.
10. Check the saved batch list. Different layouts can create separate groups, even on the same page.

Do not count unchecked pages as reviewed. If saving stops partway through, inspect the list of confirmed saved groups before trying again. Earlier confirmed saves remain; restarting without checking may repeat work.

#### Advanced: Use optional AI proposals

1. Inspect the local scan and original table first.
2. Open **Model-assisted PDF nominations** for the selected source table.
3. Read the notice about sending that table's text to the configured model.
4. If that use is appropriate for your case, select **Request AI proposals for this page**.
5. Wait for the recorded result, then inspect every proposed row and its source cells.
6. Select only the proposals you want to review.
7. Select **Save selected model proposals for review**.
8. Review those saved readings using the same process as manual selections.

One request covers one table, up to 200 rows and 24 KB of source text. Proposals do not change source values or admit transactions. An empty proposal list does not prove that a page has no transactions.

If the response is interrupted, select **Check saved model attempt** first. Checking saved status does not call the model again. If no outcome is found, follow the offered same-request retry rather than creating repeated requests. **Close interrupted model attempt** prevents its result being used, but cannot undo a request already sent to the provider. A separate request may incur additional usage.

If an attempt is labelled **SIMULATED**, it is test data. Do not describe it as a successful call to an external AI model.

### Advanced: Review each reading

#### Advanced: Open a saved batch

1. Return to **Import review** and **Open PDF readings**.
2. Find the saved batch and select **Open readings**.
3. Read **Saved review progress**. The counts concern selected rows in that batch, not the whole PDF.
4. Select **Show only rows awaiting review** if you want to hide rows already decided.
5. Select **Review next pending row**, or open a specific reading.

![Saved PDF reading progress in a synthetic case](images/09-saved-readings.png)

*The saved batch shows pending, resolved and rejected counts. These example readings have already been decided.*

#### Advanced: Complete the review form

1. Inspect the original cells and PDF page beside **Reading and decision**. Check that the highlighted amount belongs to the selected row.
2. Choose the three-letter **Currency**, such as GBP, EUR or USD.
3. Enter the **Reviewed amount** as a magnitude, using a decimal point. For example, enter `61.62`, not `£61.62` or `6,162`. Keep a printed zero as zero when it is a genuine selected reading.
4. Search for and select the **Account** whose statement records this movement.
5. Choose **Money out** or **Money in** from that account's perspective. Do not infer the direction from a person's name alone.
6. Enter supported dates in the appropriate fields. The transaction date, booking date and value date can differ.
7. Check or enter the **Description**.
8. Enter **Counterparty as printed** only if the source supplies a name. This field preserves the source wording; it does not establish the person's identity.
9. Write a **Reason for decision** that identifies what you checked and explains any interpretation or correction.
10. Select **Record resolved reading**.
11. Wait for confirmation, then reload the review and inspect its status and history.
12. Continue with the next pending row.

A useful reason is specific: “Page 4, purchase row: printed amount is 61.62. Selected the card-ending 3539 account. Used the transaction date column, not the posting date column.” Avoid reasons such as “checked” when a decision involves uncertainty.

![Original source and review fields for a finalized synthetic reading](images/10-reading-review.png)

*The original source appears beside the review fields. This example has already been finalized, so its fields are read-only. An unfinished reading uses this area to record a decision.*

#### Advanced: Assess an unclear amount or date

Use **Assess original amounts** and **Assess original dates** to inspect the application's interpretations of the original text. These are aids to review. Compare alternatives with the source before entering your decision. A short year, ambiguous day/month order or OCR error needs a supported interpretation. Leave unresolved information pending when you cannot justify it.

For an undated fee or interest row, leave the transaction, booking and value date fields empty. The **Statement end date (ordering only)** option places an eligible undated row in order using its statement end. It does not claim the payment occurred that day. Finalization requires the matching printed statement-end control.

#### Advanced: Create a provisional account

1. Search existing accounts first.
2. If none is supported by the source, use the provisional-account controls in the review form.
3. Enter a **Provisional account label** that distinguishes the source, such as “Card ending 3539”.
4. Enter the **Reason for provisional account**, explaining what is known and what remains unknown.
5. Select **Create provisional account**.
6. Check that the new account is selected, then complete the reading decision.

Creating an account does not resolve the reading. It also does not establish the holder's identity.

#### Advanced: Reject or reopen a reading

If a selected row is a summary, duplicate selection or otherwise unsuitable, explain why in **Reason for decision** and select **Reject reading**. Reload to confirm the recorded result.

Before finalization, use **Reopen for review** when an existing decision needs reconsideration. Record the new reason and decision. After finalization, use the ledger correction or inclusion processes in section 10; the original candidate review is sealed.

### Advanced: Record statement dates and balances

Use printed statement controls to compare reviewed transactions with what the statement actually reports. A control is a printed date, balance or period total used as a check.

#### Advanced: Add one printed statement period

1. Finish reviewing the rows you intend to assign to the period.
2. Open **Finalize reviewed rows**, then **Add printed statement controls**.
3. Under **Statement account**, choose the correct account and currency.
4. Select the reviewed rows belonging to that printed statement period.
5. Enter **Printed statement start** and **Printed statement end** from the statement.
6. Locate and select the supporting original cells for both dates using the source controls.
7. Enter the **Printed opening balance** and **Printed closing balance** where present, and select their original source cells.
8. If present, enter **Printed total money in** and **Printed total money out**, with their sources.
9. Choose **What do the printed balances represent?** Select **Money held in the account** for held funds or **Money owed to the issuer** for a debt balance, according to the statement.
10. Enter a **Reason for statement control readings**.
11. Select **Add statement to preview**.
12. Repeat for each separate account and printed period. Check the complete preview before finalizing.

Leave an unprinted balance blank. Blank means unknown. Enter `0.00` only when you have evidence for zero. Enter decimal amounts without symbols or thousands separators, retaining a minus sign if printed. When you choose money owed to the issuer, Loupe converts amounts owed to negative ledger balances and retains the original printed amount and your choice.

Do not use a purchases subtotal as total money out if fees or interest are listed separately. The direction total must cover all money in or out in that period.

#### Advanced: Save an unfinished statement editor

1. While entering a statement, expand **Save unfinished statement editor**.
2. Save the unfinished fields and selected source cells.
3. Check for **Unfinished editor saved** before leaving.
4. When you return, use **Load unfinished statement editor**.
5. Finish the fields and add the statement to the preview when ready.

An unfinished editor is not yet a reviewed statement in the preview.

#### Advanced: Save statements already added to the preview

1. Open **Save statement controls**.
2. If saved controls already exist, load them before replacing the draft.
3. Select **Save statement controls to case**.
4. Check for the saved confirmation.
5. On return, select **Load saved statement controls** and inspect the preview.

These two saves are separate: one preserves the editor you are still filling in; the other preserves statements you have already added to the preview. Source checks run again before finalization. If another reviewer has changed the draft, refresh and compare their version before saving again.

### Advanced: Finish the PDF review

**Finalization seals this PDF reading in the case. Do not finalize the first batch while you still need to select rows from other pages.** You can leave recorded reviews saved while completing the rest of the document.

1. Open **Show document progress** under the saved readings. Inspect each page and use **Previous overview pages** and **Next overview pages** for longer documents. A page with no saved rows still needs inspection. Open every saved batch from the PDF and check its progress.
2. Confirm that every intended row has been selected. Revisit unchecked pages and separate account sections.
3. Resolve or reject every selected reading. Do not leave pending rows in the intended finalization.
4. Load and inspect saved statement controls, if used.
5. Open **Finalize reviewed rows** and read the preview, source checks and any errors.
6. If you are deliberately finalizing an incomplete document selection, read the incomplete-coverage acknowledgement and tick it only if it describes your decision.
7. Enter **Reason for finalization**, explaining the reviewed coverage and anything excluded or unresolved outside it.
8. Select **Finalize selected rows** once.
9. Wait for the receipt. If the connection is interrupted, reload and inspect the saved receipt before repeating the action.
10. Return to the ledger. Inspect the current working readings, totals and source links.
11. Open **Statements** and inspect the resulting checks.

Finalized manual PDF rows remain P3. Finalization does not certify complete extraction, identify every account holder or promote readings into verified totals. To change a written amount later, use a ledger correction. Do not attempt to reopen the original source selection as if it were an unsaved form.
