# Loupe financial testing guide

Follow this guide in order for your first test of Financial. It starts with two invented statements and ends with a saved report that a colleague can open. You do not need previous experience of Loupe.

**Updated: 20 September 2026.** Use the full **User guide** for detailed explanations of each tool. This testing guide tells you what to try and what result to check. A result is only a pass after you have checked it yourself.

Screenshots show light mode using the supplied test statements. The controls are the same in dark mode.

## Contents

1. [Create a separate test case](#1-create-a-separate-test-case)
2. [Upload both statements](#2-upload-both-statements)
3. [Check the statement and exclude its footer](#3-check-the-statement-and-exclude-its-footer)
4. [Leave the review and return](#4-leave-the-review-and-return)
5. [Confirm both imports and check the totals](#5-confirm-both-imports-and-check-the-totals)
6. [Find payments and open their originals](#6-find-payments-and-open-their-originals)
7. [Correct a description and check the history](#7-correct-a-description-and-check-the-history)
8. [Compare people and businesses](#8-compare-people-and-businesses)
9. [Link payments to a name](#9-link-payments-to-a-name)
10. [Compare a transfer](#10-compare-a-transfer)
11. [Check trends and the payment graph](#11-check-trends-and-the-payment-graph)
12. [Run the pattern and case-event checks](#12-run-the-pattern-and-case-event-checks)
13. [Save payments and an investigation note](#13-save-payments-and-an-investigation-note)
14. [Build, save and download a report](#14-build-save-and-download-a-report)
15. [Reopen the work with a colleague](#15-reopen-the-work-with-a-colleague)
16. [Test a real statement and a longer PDF](#16-test-a-real-statement-and-a-longer-pdf)
17. [Further tests for the tools you use](#17-further-tests-for-the-tools-you-use)
18. [Check the current size limits](#18-check-the-current-size-limits)
19. [Record results and report a problem](#19-record-results-and-report-a-problem)

## 1. Create a separate test case

You need the Loupe address, your own sign-in details, and permission to create or use a test case and upload files. Ask the case owner to provide a test case if you cannot create one.

1. Open Loupe and select **Sign in** after entering your username and password.
2. Select **Cases** in the left sidebar, then **New**.
3. In **Case Title**, enter **Financial test - your name - today's date**.
4. In **Description**, enter **Invented statements for financial testing.** Select **Create Case**.
5. Open that case, then select **Financial** in the left sidebar. Check the case title at the top before uploading anything.
6. Select **Financial guide**, then **Testing guide** to return here. **Open testing guide in a separate tab** lets you keep these instructions beside your case. Closing the guide returns you to the case underneath it.
7. Download [checking.pdf](checking.pdf) and [savings.pdf](savings.pdf) to a folder you can find. Alternatively, [download the test pack](financial-test-pack.zip) and extract its files first. Upload the PDFs, not the ZIP.

**Expected:** you have a new empty case and the two PDFs. Use your own case so another tester's changes do not alter your results. These PDFs contain no real customer or payment data.

## 2. Upload both statements

1. Close the guide and open **Statements & accounts**.
2. Check **Files in this case** in the main page. Select **Statement files** if the account view is showing.
3. Select **Upload PDFs**. In your computer's file chooser, select both **checking.pdf** and **savings.pdf**, then confirm the choice.
4. Keep the browser tab open while the files upload and are read. Wait until each file says **Ready to review**.
5. Select **checking.pdf** in that list.

**Expected:** both filenames appear. The checking statement opens with its original PDF beside its extracted table. Uploading alone does not put payments into Transactions; you confirm each statement in step 5.

If a file says **Read statement**, select that action. If it says **Retry reading**, use that action on the existing file. After a connection failure, select **Refresh files** and check whether it arrived before uploading it again.

## 3. Check the statement and exclude its footer

1. In **Review checking.pdf**, compare the extracted table with the original. It should retain **Date**, **Description**, **Credit**, **Debit** and **Balance**, including blank cells.
2. Select the printed **900.00** credit. The source viewer should locate that value in the original. If needed, use **Fit source width** to make the page readable.
3. Check these details: holder **EXAMPLE PERSON**, checking account ending **0040**, currency **USD**, and period **1 July to 31 July 2020**. The opening balance is **220.00** and the closing balance is **875.00**.
4. Find **Rows needing a layout check**. These sample files currently flag the line **SYNTHETIC TEST DOCUMENT. No real customer or payment.** It is the footer printed at the bottom of the PDF, not a payment.
5. Beside that footer, select **Review this row**. The correction controls open at the matching row.
6. Clear the checkbox in the **Use** column for that footer only.
7. The row disappears from the correction list. Use **Show excluded rows** to inspect it or restore it. No reason is required; do not invent a date or amount.
8. Check the import count. It should now say **6 transactions** and offer **Confirm import of 6 transactions**. Opening and closing balances must remain outside that count. Do not confirm yet; first try step 4.

**Expected:** the table still shows the original statement. The footer remains available as an excluded reading, with its original text. The six actual payments remain selected. If the footer is already excluded in a later build, check that there are six payments and continue without changing it.

![Checking statement beside the extracted table, with the footer flagged below it](images/01-statement-check.png)

*This is the checking PDF supplied with this guide. The flagged footer is separate from its payment table.*

![Correction controls used to exclude the test document footer](images/02-exclude-footer.png)

*Clear Use on the footer row. An explanation is optional; The excluded footer must not become a seventh payment.*

For a wrong payment value, use **Edit import values** or **Show corrections and import choices**. Correct the field against the original; leave the optional note blank to check that it does not block import. For this exercise, leave the correct payment amounts unchanged. If any other line is flagged, inspect it before importing and record the unexpected result in your test notes.

Before excluding the footer, check that its reading issue is visible but does not itself disable import. Use **Review row** to open the matching correction controls. Exclude the footer without entering a reason. The corrected count should then be reflected beside confirmation.

## 4. Leave the review and return

1. While the checking statement is still unconfirmed, open **Transactions**, then return to **Statements & accounts**.
2. Reopen **checking.pdf** from **Statement files** if necessary.
3. Check that the footer is still excluded and its original text remains available.
4. Refresh this same browser tab. Reopen the statement if needed and check the same two details again.
5. Open **savings.pdf** from the file list, then return to **checking.pdf**. The checking review should still be present.

**Expected:** changing financial tabs, switching files and refreshing the same browser tab do not lose your review. Select **Save progress** before closing the tab: saved statement corrections can then be reopened from another device with case access. Edits made after that save remain browser drafts until saved again. Imported payments, findings and reports are kept with the case.

## 5. Confirm both imports and check the totals

1. In the checking review, select **Confirm import of 6 transactions** once. Wait for the outcome. Its payments should become available in **Transactions**.
2. Return to **Statements & accounts**, open **Statement files**, then select **savings.pdf**.
3. Check its account ending **0000**, USD currency and July 2020 period. Its opening balance is **50.00** and closing balance is **355.00**.
4. Exclude the same test document footer using step 3. Check that only the **300.00** transfer and **5.00** interest payment are selected.
5. Select **Confirm import of 2 transactions** once.
6. Open **Transactions**, choose **Imported statement payments**, select **Reset** in the account/date filter, then **Clear payment filters** beside the search controls. This removes earlier searches and restrictions.
7. Check the total count and the figures below.

| Account | Payments | Money in | Money out | Opening balance | Closing balance |
| --- | ---: | ---: | ---: | ---: | ---: |
| Checking, ending 0040 | 6 | USD 1,550.00 | USD 895.00 | USD 220.00 | USD 875.00 |
| Savings, ending 0000 | 2 | USD 305.00 | USD 0.00 | USD 50.00 | USD 355.00 |
| Both accounts | 8 | USD 1,855.00 | USD 895.00 | Check each account separately | Check each account separately |

**Expected:** eight current transactions, with combined money in of **USD 1,855.00**, money out of **USD 895.00**, and difference of **USD 960.00**. The difference is money in minus money out, not a closing account balance. The transfer has one entry leaving checking and another entering savings.

Select checking under **Account**, then **Apply** to check its six payments. Repeat for savings and its two payments. Select **Reset** afterwards to return to both accounts.

If confirmation appears to fail, reopen the file and check its imported count before trying again. Do not repeatedly click confirmation or upload more copies to make the count change.

![Eight imported payments from the two supplied test statements](images/03-transactions.png)

*Your new test case should contain these eight payments before any further test adds or excludes a transaction.*

## 6. Find payments and open their originals

1. In **Search payments**, enter **Example Supplies**.
2. Check that two outgoing payments remain: **USD 120.00 on 5 July 2020** and **USD 75.00 on 16 July 2020**. Together they total **USD 195.00**.
3. Beside the USD 120 payment, select **Open transaction**. Check its date, amount, account and source filename.
4. Select **Open source file**. Compare it with the USD 120 debit in checking.pdf. Close the source viewer and transaction details when finished.
5. Open another financial tab, return to Transactions, then refresh the browser. Check that your **Example Supplies** search remains.
6. Select **Clear payment filters**. Use **Filters**, choose USD if needed, and set both the minimum and maximum amount to **120**. Check that the USD 120 outgoing payment is the result. Clear the filters again afterwards.

**Expected:** each payment leads to the correct original file and value. Searching or changing tabs does not change the payment itself. If a value has no stored page position, the app must explain that rather than highlighting an unrelated location.

## 7. Correct a description and check the history

This changes only wording, so the expected money totals remain the same.

1. Find the USD 120 payment again and select **Open transaction**, then **Correct a value**.
2. Change **Description** to **Payment to Example Supplies - test correction**. Leave every date, amount, direction and balance unchanged.
3. Select **Preview correction**. Check that the proposed change is only the description.
4. Enter **Checking the correction workflow on synthetic data** in **Reason for correction**.
5. Select **Record correction** and wait for the result.
6. Reopen the payment. Check the new description, its previous reading and its unchanged original PDF.
7. Open **More financial tools**, then **Change history**. Find your correction and check its reason and before/after readings.
8. Return to Transactions, reset the filters and confirm there are still eight current transactions with the totals from step 5.

**Expected:** the description changes, its history is retained, and the correction does not add a ninth current payment or change totals. A saved report made before a later correction retains its earlier captured values.

## 8. Compare people and businesses

1. Open **People & businesses**. Under **Accounts and dates**, choose all accounts for July 2020 and apply.
2. Search **Alpha Consulting** under **Search names and accounts** and open its profile.
3. Check two payments and **USD 1,550.00** incoming. Open the two payment descriptions to inspect their original records.
4. Select **Compare 2 payments**. Confirm 2 July and 14 July and their amounts. Close the comparison.
5. Return to the directory and search **Example Supplies**. Its two outgoing payments should total **USD 195.00**.

**Expected:** each profile leads to actual payments and originals. A recorded name is not presented as an independently verified identity.

## 9. Link payments to a name

This checks the decision-saving controls. The invented statement already uses a consistent name; this is practice for cases with differing spellings.

1. In People & businesses, open **Link recorded names to a person or business**, then **Link different names for the same person or business**, then **Open payment identity review**.
2. Search for **Alpha Consulting** under **Find payment names, descriptions or references**.
3. Select the two matching payments. Check the count before continuing.
4. Under **Person or business**, choose **A new person or organisation** and enter **Alpha Consulting - test grouping** in **Name**.
5. In **Why do these payments belong to this person or business?**, enter **Both invented statement descriptions name Alpha Consulting; testing a saved grouping.**
6. Select **Save payment identity links**. Check the saved links and history.
7. In the analysis, select **Combine names I have linked to the same person or business**. Check that your named group contains those two payments and USD 1,550.00 incoming.
8. Expand **Names printed on statements** to check that Alpha Consulting remains recorded as the original name. Switch the grouping option off to return to the printed-name view.

**Expected:** the grouping is saved without rewriting the statement descriptions, original files or payment amounts. If a save response is lost, reload the current links and check whether it saved before retrying.

## 10. Compare a transfer

1. Open **Follow money**, then **Compare transfers**. Set **From date** to **1 July 2020** and **To date** to **31 July 2020**.
2. Choose **All imported payments** and leave **Maximum days between payments** at **3 days**.
3. Select **Find possible transfers**.
4. Find the pair for **USD 300.00 on 3 July**: outgoing from checking and incoming to savings. Open both source readings.
5. Select that pair. Under **Why do you think these payments are transfers?**, enter **The two invented statements show the same USD 300 transfer on 3 July between these accounts.**
6. Select **Compare totals using these transfers**. Inspect the selected pair and the account comparison.
7. Use **Save this analysis with a note** to keep it, with the name **Test transfer between checking and savings** and your observation.

**Expected:** the pair contains exactly the two USD 300 entries. The comparison and explanation can be reopened in Findings. Transactions still contains eight entries; saving a transfer comparison does not delete either side from the bank record.

## 11. Check trends and the payment graph

1. Open **Trends**, select all accounts for July 2020 and select **Apply**.
2. Under **Interval**, choose **Monthly**. Under **Show**, choose **Amounts**. Check **USD · bank accounts** under **Amounts**.
3. Select July in the chart. Check its eight payments and totals against step 5. Change Interval to Daily to see every July date, including dates with no imported payments. Open a payment and inspect its source.
4. Open **More financial tools**, then **Payment graph**. Apply the same account/date choice and select **Show connections** if needed.
5. Search for **Example Supplies** under **Find an account or name**, then select the matching name under **Choose an account or name**.
6. Select **View selected connections** and check its two payments. Open one to confirm its source.
7. Select **Show all connections** to return to the complete selected account/date range.

**Expected:** the chart and graph lead to the payments that explain them. A line in the graph is not a new payment. Both recorded sides of a transfer remain available.

## 12. Run the pattern and case-event checks

1. Open **Follow money**, then **Look for repeated activity**, then **Review patterns** if the payment-claim form is showing.
2. Apply all accounts and July 2020. Choose **All imported payments**. Leave the optional split-payment amount blank and cross-account path checking off for this first run.
3. Select **Find patterns**. Check the result or explicit no-result message. A small test set need not contain every type of pattern; do not mark a failure merely because a particular pattern is absent.
4. If a result appears, open its supporting payments and check the stated dates and amounts.
5. Open **More financial tools**, then **Payments and case events**. Apply all accounts and July 2020, then select **Load payments and case events**.
6. Check that the eight payments are available. A new case with no events can legitimately show zero case events. Use the next-page control if needed to reach every payment.

**Expected:** the tools return results or explain a problem. A blank screen, endless loading indicator or unrelated payment is a failure. Case-event amounts must not increase transaction totals.

## 13. Save payments and an investigation note

1. Return to Transactions. Clear earlier selections if present, then search for **Example Supplies**.
2. Tick the two payments, or use **Select all 2 matching payments** and check that the selection count is two. **Review selected payments** lets you check what is included.
3. Select **Create finding** and choose **Question** under **Type**.
4. Enter **Example supplier payments** as **Title**.
5. In **Explanation**, enter **Two payments to Example Supplies total USD 195.** In **Next action**, enter **Request the invoices and check what was supplied.** Enter your name in **Assigned to** and leave **Progress** as Open.
6. Select **Review attached payments** and confirm two entries. Close that review, select **Save finding** once and wait for the saved confirmation.
7. Select **Open Findings**. Check your question, next action and two payment links. Select **Edit finding**, change Progress to In progress and save. Refresh and check that the change remains.
8. Return to Transactions, clear the search and open the outgoing USD 300 transfer and select **Add investigation note**.
9. In **Your transaction note**, enter **Check the corresponding USD 300 receipt in the savings account.** Select **Save investigation note**.
10. Check that this second note also appears in Findings. Refresh and reopen both notes.

**Expected:** both notes and their payment links remain after refresh. They are saved case work, not just text left in your browser.

## 14. Build, save and download a report

1. In Findings, tick **Include in report** for **Example supplier payments** and your transaction note from step 13.
2. Select **Build report**. Check that it shows two selected notes.
3. Enter **First financial test report** as **Report title**.
4. In **Introduction**, enter **Testing saved findings and original statement references using invented payments.**
5. Use **Move up** or **Move down** to place the supplier note first. Select **Preview report** and read both notes and their linked payments.
6. Select **Save report to case**. Wait for **Report saved to this case** before closing it.
7. Refresh. In Findings, find your report and select **Open financial report**. It is also available under **Reports** in the main sidebar, in **Financial reports**.
8. Select **Download readable report**. Open the HTML file in a browser and check its title, introduction, notes and payments. The browser's Print command can save a PDF if you need one.
9. Back in the saved report, expand **Supporting file references**. Tick **Include the supporting PDFs in the download package**, then select **Download report package with PDFs**.
10. Extract the ZIP into one folder and open **report.html**. Follow its file links. Keep the other downloaded files with it.

**Expected:** the report reopens from the case and the downloaded copy contains both notes and the checking PDF referenced by their payments. Savings may be absent because these two notes concern checking transactions. A source used by both notes should be included once. The download must not report success while omitting a required file.

A payment can appear in several notes. Do not add every note's total together as if those were different payments. The case's transaction totals remain the reference for money in and out.

## 15. Reopen the work with a colleague

1. Give a colleague who already has access to this test case its name and the report title. Do not share your password.
2. Ask them to sign in with their own account, open the case, select Financial, then Findings.
3. Ask them to open **First financial test report**, read both notes and open a linked payment's source.
4. Check that they see the saved descriptions and explanations. They should not need your browser tab or computer.
5. If they have read-only access, check that they can inspect the records but cannot confirm imports, correct payments or save changes.

**Expected:** saved case work can be reopened by the authorised colleague. Your unfinished selections and form drafts are not shared. Mark this test **Not run** if no colleague is available; do not count your own second browser tab as another person's access test.

## 16. Test a real statement and a longer PDF

Use a separate test case. Keep the invented eight-payment case unchanged for comparing results later.

1. Before upload, note the real statement's account, currency, dates, number of actual payments, opening balance and closing balance from the original. Keep those notes separate from Loupe's extraction.
2. Upload a copy through Statements. Compare the extracted table with the original, including blank columns, minus signs, refunds, balance-only rows and wrapped descriptions.
3. For a document with several pages, use **Next page**, **Previous page** and the **Page** chooser. Check the first, middle and last pages. The viewer uses PDF page numbers; these can differ from numbers printed inside the document.
4. If a file contains several statement periods or accounts, choose each recognised section separately. Check that edits made in one do not appear in another. Currency should be detected from each statement, including when periods in one PDF use different currencies. Repeat through bulk processing and check that the same currencies and amounts appear. If an older review has a wrong currency saved, use the detected-currency button and check that the amounts populate without reuploading.
5. Correct a flagged value only when you can read it in the source. If it remains unclear, try **Read the statement again** or record the unresolved issue. Do not use a guessed amount to make a warning disappear.
6. Compare the proposed payment count with your own count. Inspect any difference, including duplicate pages and headings mistaken for payments, before confirming.
7. After confirmation, select that account and date range in Transactions and compare its payments and totals with your notes. Open sources from the first, middle and last pages.
8. Switch files and tabs, refresh, then reopen the statement and a payment.

**Expected:** every difference you find is explainable and every imported payment leads back to the correct original. Agreement on a closing balance alone does not prove that all payments were read correctly. Record uncertain or missing items even if the import completed.

For a credit card, compare charges, credits and **Opening amount owed / Closing amount owed** separately from bank money in and out. For a wire report or deposit receipt, expect its own supporting-document review and a saved finding. Do not count the receipt as an extra bank payment merely because the corresponding statement was also uploaded.

### Compare a new reading with an unclear scan

1. Keep your original count and field notes from the steps above. In the test case, open **Read the statement again**, choose **Read from page images**, then select **Reprocess statement**.
2. Open the new reading. Check that the earlier file and any saved reviews remain available. Compare both versions with the original PDF before replacing an import.
3. On a supported Merrick statement with damaged date text, compare the newly read dates with their original locations. Some dates may be recovered automatically. A date the reader still cannot resolve should remain a problem to correct.
4. Check remaining amounts, credit signs and balances. Fixing a date must not clear a separate amount problem. If a number looks valid but differs from the original, record that difference even if there is no warning on that row.
5. After correcting known field errors, inspect the balance result. A remaining difference must stay visible and must not be called a match. Record the amount and the source page for investigation.

**Expected:** a new reading retains the source and earlier work. It does not silently replace an existing import. Fewer warnings alone are not a passing result; the checked fields must agree with the original.

## 17. Further tests for the tools you use

Do these in additional test cases or after recording the eight-payment baseline. Use the matching User guide chapter for the complete procedure. Record tests you did not attempt as **Not run**.

### A. Exclude and restore a payment

1. Open an invented payment and select **Exclude from totals**. Enter a clear test reason and confirm the permitted action.
2. Check that it leaves current totals and remains in **More financial tools > Excluded transactions** with its source and explanation.
3. Use its inclusion action to restore it, giving a second reason.
4. Confirm that the eight-payment count and original totals return. Inspect Change history for both decisions.

### B. Repeated copies and missing periods

1. In a separate case, upload two different copies of the same statement, such as a native PDF and a scan supplied for this test. Open their originals before treating them as duplicates.
2. Open **Statements & accounts**. In **Do you have all the statements?**, check that overlapping dates are shown for the imported copies. Select **Check duplicate imports**, open their originals, then follow **Review duplicates** in the User guide to record which copy to retain.
3. Close the comparison. Check that the register no longer counts the excluded copy in its date coverage, and that Transactions totals change accordingly. Restore the decision and check that both the history and the overlap return. Do not delete the originals to make totals agree.
4. On the account card, select **Review dates & statements**. Check the listed filenames and open an original using **Open statement and dates**. Apply a requested date range that extends beyond the statement you supplied. Use **View transactions in the checked date range** and confirm that the correct account and dates are selected.
5. If January and March statements for the same account are available, import them and check that the missing February dates are listed in the register. Files awaiting review must not count as imported date coverage. Check that dates which cannot be established are described as unknown or needing attention, rather than as a period with no payments. If there are more than 25 accounts, check subsequent pages as well.

**Expected:** the register leads directly to the missing or repeated records, exclusions and restorations update the date checks, and every listed statement can be opened without reuploading it.

### C. Trace funds

1. Open **More financial tools > Trace funds > Trace one account**. Choose the invented checking account and July dates, then **Apply account and dates** and **Load tracing inputs**.
2. Enter its USD 220 opening amount and cite the invented statement as the basis. Attribute the USD 900 deposit to a claim labelled **Training example**, with an explanation that this is a hypothetical test.
3. Check the movement order, explain it, select the methods to compare and select **Calculate conditional scenario**.
4. Use **Save this calculation in Findings**, name it and select **Save calculation and note**.
5. Reopen **Open saved calculation** in Findings. Check the opening amount, deposit attribution, assumptions and source links. Changing an input must require a new calculation before saving a revised result.
6. To test the separate cross-account method, use **Trace between accounts** and the User guide's complete procedure, supplying both opening balances and the two sides of the USD 300 transfer.

### D. Payment claims and other financial records

1. Follow **Compare a stated payment with the records** in the User guide, using an invented claim that Alpha Consulting paid USD 900 on 2 July 2020 and a supporting test document. Keep this separate from the bank import.
2. Run the comparison and check that the correct payment is available, with its date, amount, currency and source.
3. Record your response with a reason and the supporting payment; reopen the saved note.
4. If the case contains **Other financial records**, open a record and its original. Follow that guide chapter to test an explained amount correction. Check that its original amount and reason remain available and that it does not become a bank transaction.

### E. Asset and indirect calculations

1. Open **Trace funds** and choose the relevant asset or indirect review method described in the User guide.
2. Use invented amounts with written source explanations. Calculate the result and save it in Findings.
3. Refresh and reopen the saved workpaper. Check every entered value and its source.
4. Make a revised copy, change one amount, calculate again and save the revision. Check that the original saved calculation remains available.
5. Include both versions in a report and explain why their results differ.

### F. Select existing evidence folders and remove an unrelated PDF

1. In the separate test case, place a synthetic PDF in an Evidence folder with a subfolder. Include a non-PDF file if available.
2. Select **Send to Financial**. Tick the parent folder, browse into its subfolder and tick the same PDF too.
3. Select **Review selected PDFs**. The PDF should appear once and the non-PDF file should be counted as skipped.
4. Send the selection. Financial should open automatically on **Prepare statements for import**. Existing readings should be reused. No transactions should be imported before you confirm. Refresh and check that processing continues and the same batch remains available.
5. Open Financial and select **Remove from Financial** on an unrelated, unimported PDF. Confirm removal, refresh and check that it stays out of the normal list while its original remains in Evidence.
6. Select **Removed files**, restore the PDF, then select **Back to financial files**. It should reappear.
7. A file already used by an imported statement should not offer removal. Existing transaction counts must stay unchanged.

**Expected:** folder choices work across subfolders, selections do not duplicate a file, existing evidence results are preserved, and removal is reversible for the case.

## 18. Check the current size limits

A case can contain more payments than one analysis permits. These are separate limits, not a single maximum case size.

| Feature | Current behaviour | What to test |
| --- | --- | --- |
| Upload PDFs | Up to 20 files per selection | Confirm each file appears and can be opened separately. |
| Single statement review | Up to 25,000 possible transactions and 100,000 retained text rows | Use the correction-page controls; check first, middle and last payments before and after import. |
| Saved payment selections | No 100-payment count restriction; saved details must fit within 32 MB | Save a known selection across pages, refresh and reopen its first and last payments. |
| Payment graph | No 1,000-payment count restriction; 250 connections drawn per page | Check the total payment count and the underlying payments on later graph pages. |
| Combined reports | No 20-finding or 20-PDF count restriction; 32 MB saved report data and 64 MB supporting files | Include findings from several pages and check that the saved report and download retain all of them. |
| Transfers | 500 payments per comparison, with 1,000 pair/reference comparisons | Narrow From date and To date, then select Find possible transfers. |
| Payments and case events | 1,000 payments per check | Choose an account or shorter dates, select Apply, then Load payments and case events. |
| Patterns | 1,000 input payments; also 200 proposed matches, 50 payments per repeated-name group, and 10,000 examined steps between accounts | Narrow the account/dates, select Apply and Find patterns again. |

The larger imports, selections, graph and reports were checked locally with a 5,000-payment statement, a 2,700-payment case and a 50-finding report. These figures describe earlier development checks, not results your team has already obtained on the deployed server. General response and file-size bounds still apply.

A refused check must explain why. It is not a finding that there are no matches. Each smaller date check covers only those dates; splitting a case into separate ranges can miss relationships crossing their boundaries. Whole-case transfer, timeline and pattern work beyond these limits remains unfinished.

## 19. Record results and report a problem

Copy this table into your team's test notes, or print this guide and fill it in. Use **Pass**, **Fail**, **Blocked** or **Not run**. Record the actual result; do not mark a pass just because a button could be clicked.

Tester: __________  Date: __________  Case name: __________

| Test | Result | What differed or where the evidence is saved |
| --- | --- | --- |
| 1. Separate case | | |
| 2. Two files uploaded | | |
| 3. Original comparison and footer exclusion | | |
| 4. Draft kept through tabs, files and refresh | | |
| 5. Eight imported payments and exact totals | | |
| 6. Search, filters and original source | | |
| 7. Correction and history, totals unchanged | | |
| 8. People and business totals | | |
| 9. Saved name links | | |
| 10. Two sides of the USD 300 transfer | | |
| 11. Trends and graph payment links | | |
| 12. Patterns and case events | | |
| 13. Saved selection and note | | |
| 14. Saved report and original-file download | | |
| 15. Colleague access | | |
| 16. Real and multi-page statements | | |
| 17. Further tools: name each one tested | | |
| 18. Larger selections and known limits | | |

For each failure, record:

1. Case name, filename and page, and the affected payment if relevant.
2. The numbered test above and the exact button or field used.
3. What you expected and what actually appeared, including counts or amounts.
4. A screenshot and the exact error message.
5. Whether switching tabs or refreshing changed the result.
6. Whether the action saved anything before showing the problem. Check the case before repeating an import or save.

Keep private real statements and their screenshots within your team's approved channels. A synthetic test passing does not establish extraction accuracy for every real statement. Keep your manually checked real-file notes so the team can compare them with the imported records.


### Statement periods and transaction navigation

1. Open a PDF containing more than one statement. Check that the **Statement period** dropdown lists the separate accounts and dates.
2. Choose a period. Compare its count and balance check with the PDF. Check that summary pages and terms are not counted as transactions.
3. Select **Next transaction**. The counter, table highlight and original PDF must refer to the same payment. Continue across a page boundary, then use **Previous transaction** to return.
4. Correct a value and enter a reason. Switch to another period, then return. The correction must still be present.
5. For a clean statement, confirm once without opening every transaction. For a flagged statement, select **Show items to check** and verify that each flagged row opens directly for correction.
6. Check a period with a balance difference and one with no readable balance controls. Neither must be labelled as having matching balances.


### G. Import a batch, leaving one unreadable amount for later

1. In a test case, send an Evidence folder with two clean synthetic statements and a statement containing a known unreadable amount to Financial.
2. Wait for processing. Check that each recognised account and period is listed and that **Issues to check** identifies the unreadable amount.
3. Select **Import [number] records**. All available statements should become imported, including the statement with the unresolved reading. Files that failed processing stay separate.
4. Refresh. Check that the counts remain and that importing the same batch again adds no duplicates.
5. Open Transactions. All complete payments should be present. Expand the amber missing-values message and open the incomplete record with its original.
6. Verify that the unreadable amount is absent from totals rather than counted as zero. Date and currency totals must still agree with the complete readings in the synthetic sources.
7. Enter the amount from the original, give the reason and save. The payment must join the table and totals exactly once. Its original unreadable field and later correction must remain in the history.
8. Reopen the batch. The issue count should reflect the saved correction. Any remaining balance difference must still be visible, without preventing work.
9. If another file fails processing, check its retry action and confirm that the successful imports remain available.

**Expected:** flagged readings can be imported, incomplete records remain findable, known amounts are counted honestly, and correcting a record later does not duplicate it.

### H. Follow a payment into a finding

Use a test case with an incoming EUR 125,000 payment dated 18 March and an outgoing EUR 120,000 payment dated 20 March on the same account.

1. Search for the incoming payment. Open its description and confirm that its source line is highlighted.
2. Select **Related payments**, choose payments after this one within seven days, then tick the outgoing payment.
3. Narrow the interval so that the outgoing payment is hidden. Check that the selection count still includes it. Return to seven days.
4. Select **Compare 2 selected payments**. Confirm that the difference is EUR 5,000 and the second payment is two days later.
5. Choose **Create finding from these payments**. Enter a title and question. Check that two supporting payments are attached before saving.
6. Save and return to the investigation. The search, source and selected payments should remain. Open Findings and reopen the saved narrative and evidence.
7. Have another authorised investigator open the same finding. A read-only user must be able to inspect it without editing controls.
8. Open a name from From or To and use the return button. Open Trends, choose a month or category, and confirm that its supporting list has the same count and totals.

**Expected:** an investigator can follow evidence, record the question and return without reconstructing the search. A timing match is not automatically presented as a proven transfer.

## Check corrections, automatic checks and saved progress

Use artificial test statements in a test case for these checks.

1. In Evidence, select a folder containing statements and use **Send to Financial**. Confirm the selected PDFs. Check that Financial opens the processing batch.
2. Open a ready statement with running balances. Check that **Balances between payments** gives the number of checked intervals.
3. Select a printed transaction and **Edit this row**. Increase its credit or debit amount by 1.00 and enter a correction reason. Expect a balance difference with a link to the affected row. The original printed value must remain visible.
4. Select **Save progress**. Return to the batch, reopen this statement and refresh the page. Expect the corrected value and reason to remain.
5. Clear that transaction's date and select **Save progress** again. Expect the statement to remain under **Needs attention**, with import unavailable. Saving incomplete work must not add transactions.
6. Restore the date and amount from the PDF. Expect the checks to run again and the difference to clear. Use **Save and open next problem**. Expect another statement with a problem to open, or the batch list if none remains.
7. For a PDF containing several accounts and periods, change **Account**, then **Statement period**. Check that next/previous period stays in the chosen account. Search a long collection using **Find a period**.
8. Import all available records. Expect the exact transaction count shown before confirmation. Refresh and repeat opening the batch; no duplicate payments should appear.
9. If a synthetic statement deliberately contains a printed balance error, keep its printed values. Select **I checked these differences against the PDF**, enter **Why the difference remains**, and save. Expect the difference and explanation to stay recorded. Change an amount again; the previous acknowledgement must no longer accept that new difference.

Record the filename, account, period, action, expected result and actual result for any failure. Do not repair a test result by changing the original PDF.

### Check separately printed fee and interest totals

1. Use an artificial Merrick statement whose original interest charge and interest total both show 36.32, but whose extracted charge reads 36.52. Expect **Interest charges against printed total: needs checking**, with a difference of 0.20. The statement must need attention in the batch as well.
2. Select **View printed value** to inspect the total, then **Check charge 1** to open the charge's editor beside the PDF. Correct the debit to 36.32 and explain that the original charge was checked. Expect the comparison to change to **matches**.
3. Include a card-payment reading with a missing trailing minus. Expect a specific request to check its date and original amount. Enter its original value under **Credit / money in**, correct any misread date and give a reason. The system must not silently convert the amount to a credit just because the description says payment.
4. Save the review, leave and reopen it. Expect both corrections and their reasons to remain, including after browser tab storage is cleared. The batch should be ready only when its other problems are resolved.
5. Import once, then open the resulting transactions. Expect the corrected interest amount, payment date and credit amount. Open each original PDF location and confirm the original reading remains available.
6. Check a test statement with a damaged section total or a manually added transaction whose section is unknown. Expect that comparison to be unavailable. A missing or unreadable total must not be treated as zero or described as a match.

**Expected:** separate charge totals expose an amount error even when that amount looks like a valid number. Corrections change the calculation and imported values while preserving the original source.

### Check individual saved progress and repeated corrections

1. Open an unimported synthetic statement from **Statements & accounts**. Clear one transaction date, select **Save progress** and wait for the saved message. Import should remain unavailable.
2. Reload and reopen that statement. Expect the unfinished date correction to remain. Restore the date from the PDF and enter the reason.
3. Open **Correct several rows**. Select two rows, choose **Switch credit and debit**, add a reason and select **Preview corrections**. Expect only those two rows in the preview, with their current and proposed columns.
4. Apply the changes. Expect new balance differences where the switched values no longer match the statement. Switch the same rows back with a reason, then save. Expect the original values to remain visible in the printed table throughout.
5. If two authorised reviewers open the same saved review, save a change from one and then attempt to save the older review from the other. Expect a conflict message; the later attempt must not overwrite the first saved review.
6. If reprocessing changes a reading with an earlier saved review, open **Earlier saved reviews** and **Compare earlier values**. Expect individual and bulk corrections, including changed periods, to remain available. Compare them, tick the comparison box and select **Save comparison for this file**. Reload to check that the comparison remains saved. It must not add payments.

### Check names read from a statement's mailing address

1. Open an artificial Merrick statement with the account holder's name above its mailing address, separate from the bank's payment address. Expect **Account holder** to contain the complete printed name, including a surname extracted into the next cell.
2. Check an Andrews statement with joint names. Expect both names, separated by a slash. The street address and mailing code must not become part of either name.
3. Use a test reading with a damaged surname or incomplete address. Expect a missing-name problem where the complete name cannot be established. Enter the name from the original PDF, explain the correction and save it.
4. Return to the batch. Expect the saved name and an updated status for that statement. Other unresolved amounts or dates must remain flagged, but must not prevent import. Their incomplete records must remain outside calculated totals.
5. Reopen an earlier saved review after a new reading finds the name. Check its earlier corrections before importing. A newly recognised name must not create a second period or a duplicate import.

**Expected:** clear names appear automatically. Unclear names have a specific correction route, and the account's payments do not change because its name was recognised.

### Check an Andrews image reread

1. Use an Andrews test statement with a damaged amount or balance reading. Record its account sections and transaction count before reprocessing.
2. Choose **Read from page images** under **Read the statement again**, then **Reprocess statement**.
3. Compare recovered values with the original PDF, including decimal points and minus signs. Readable values without a sign conflict and account assignments should remain unchanged. A flagged sign conflict can be reread from its image: check both the digits and the sign of the replacement. Dates and descriptions must not change because a money cell was reread.
4. Check the remaining problems and balance differences. A newly readable balance can reveal a mismatch in another payment. Neither that mismatch nor a conflicting visual reading should be marked as resolved automatically.
5. Open any earlier saved review and compare its corrections before importing a changed reading. Confirm only the statements whose remaining problems you have resolved.

**Expected:** specific damaged money cells can improve without hiding unresolved values or replacing previous imports automatically. A lower warning count alone is not a successful test; record any wrong or missing value found against the PDF.

### Check a refund whose amount is on the next line

1. Use an Andrews-style test statement with a **Credit Voucher** refund. Its description should be on one line and its amount and running balance immediately below. Include another refund with its amount at the end of the description line.
2. Open the statement review. Expect one payment for each refund, with its printed amount and balance. The extracted view must retain the original lines. The amount line must not become another payment or part of the payment description.
3. Select the amount on the second line, then **Edit this row**. Expect the refund's date, description, credit and balance in the editor. Make a description correction without a reason and select **Save for bulk import**.
4. Reopen the saved review after clearing this tab's temporary storage. Expect the correction to remain. The original printed text must still be visible.
5. Import the ready statement once. Open that refund in **Transactions**. Expect its amount and balance, the saved description correction, and a source highlight covering both the first line and the amount line.
6. Repeat with an unreadable amount or an unrelated number further down the page. Expect a review problem. Loupe must not choose a value just because it would make the balances match.

### Check missing Andrews pages and broken dates

1. Use an artificial statement whose first-page logo is unreadable in the extracted text. Its printed account and dates must match the next branded page, numbered **2**, and the first page must contain an account opening and a continuation notice. Expect both pages under the same account and period. A conflicting account, different dates or missing intervening page must prevent that automatic grouping.
2. In a scanned statement with a damaged full-period date, use **Read from page images**. Compare the recovered date with the PDF. If the local readings disagree, it must stay unresolved. An existing readable date must remain unchanged.
3. Check a payment with a broken date such as **O6 /O3**. Expect its own transaction row and a date problem. Its description and money must not be appended to the preceding payment. Correct the date beside the PDF and save.
4. Open the PDF page selector. Recognised account applications, account agreements and fee-only pages should remain accessible as information pages. A page that also contains payments must not be dismissed as information.

For a Merrick collection, also check recognised cover letters, application continuations, cardholder notices, separate interest-calculation pages and records-request paperwork. Open their original pages from the page selector. A payment-history list must remain available for financial review, even when it shares a page with familiar notice text. Check for payments already recorded in the monthly statements before adding anything from that list.

Use an artificial Merrick statement containing an **Interest Charge on Purchases** or **Interest Charge on Cash Advances** line showing `0.00` with an unreadable date. That clearly positioned zero-charge line should remain in the source view without asking for a date correction. Change the amount to `0.01`, make the amount unreadable, or move it outside the amount column. It must then remain available for review, rather than being dismissed as a zero charge. An unfamiliar zero-value row with an unreadable date also stays flagged.

Check the date warning on a nonzero row. A day read as `44`, a month read as `14` or 29 February in a non-leap year should be described as an invalid month or day. A readable month/day with no usable statement year should retain the missing-year instruction. Correct only the indicated fields against the original. For an Andrews sign warning, compare the numeric amount as well as the minus sign: a misread sign can also introduce a digit.
5. Compare transaction counts and balances before and after processing. Additional genuine payments can raise the problem count. Verify each newly found payment, and keep earlier saved corrections available for comparison.

**Expected:** missing statement pages and damaged-date payments are recovered where the source supports them. Existing dates, amounts, signs and balances are preserved. No real imports are replaced automatically.

### Check repeated statement dates

1. Use a Merrick test statement whose closing-date reading differs from its **Statement Date**. Keep a note of the printed dates and transaction count.
2. Choose **Read from page images** under **Read the statement again**, then **Reprocess statement**.
3. Compare any corrected closing date with both printed dates and the year-to-date heading. A remaining disagreement must still be flagged. Transaction amounts and descriptions must not change because a date was reread.
4. In a statement where the statement-date heading was not recognised, check the separately labelled **Billing Cycle Closing Date**. A unique, readable closing date with a matching year-to-date year can supply missing transaction years. It must not fill the statement's coverage dates or replace an existing conflicting heading.
5. Check any interest-charge date warning. Confirm the printed month and day against the closing date. The warning must not silently change the transaction date to make them agree.
6. Reopen any earlier saved review and compare it before importing a changed reading.

**Expected:** repeated printed dates reduce unnecessary year corrections. Conflicting dates and unreadable transaction days remain visible. Record any apparently valid date that differs from the PDF.

### Check several missing transaction years

Use an artificial Merrick statement with readable numeric month/day values and an unreadable closing-date reading. Keep its original PDF legible.

1. Open **Correct several rows** and choose **Complete missing years**. Enter the closing date from the PDF and a reason.
2. Use **Select readable dates missing a year**, then **Preview corrections**. Expect the printed month/day beside each proposed full date. Check December transactions against a January closing date: their year must be the previous year.
3. Include a row with an unreadable day or a date outside the closing month and previous month. Expect a message directing you to check it individually. No correction should apply from an invalid preview.
4. Apply a valid preview. Expect amounts, descriptions, existing complete dates and undated charges to remain unchanged. Original printed date cells must remain available.
5. Select **Save progress**, reopen the review and refresh. Expect both the completed dates and the reason to remain. Import the ready statement once and check the same dates in Transactions.

**Expected:** one checked closing date completes only the missing years of eligible rows, with a preview and a retained explanation. It must not replace unclear days or invent statement-period coverage.

### Check a transaction assigned to the wrong statement

Use an artificial PDF with two recognised accounts or periods, before importing either statement.

1. Save a correction in the receiving statement, such as a description with a reason.
2. In the source statement, open **Correct several rows**, tick a transaction and choose **Move to another account or period**.
3. Enter the reason, choose the receiving statement and select **Preview move**. Expect both accounts and periods, before/after transaction counts, and the balance checks for both statements. Preview alone must not save anything.
4. Select **Save move**. Expect the transaction to leave the source review and appear once in the receiving review. Existing corrections in both reviews must remain.
5. Refresh and reopen both statements. In the receiving statement, use **View original** on the moved transaction. Expect its original PDF page and location, not a new or invented source.
6. Check the bulk list when the file also belongs to a processing batch. Its transaction counts and checks must reflect the move. A balance difference must stay under **Needs attention** until corrected or explained.
7. Move the transaction back with a reason. Expect the original counts and both move reasons to remain in the saved history.
8. With two authorised reviewers, preview a move, then save a change to either affected statement from the other reviewer. Attempt the original move. Expect a conflict and a request to preview again, with neither saved review overwritten.
9. Import both corrected statements. Expect each transaction once. The moved transaction must retain its original source and the reason for reassignment. Moving between these reviews after import must be refused.

### Check a missing page with unassigned payments

Use an artificial Andrews-style PDF with a checking account opening, a skipped printed page number and a continuation containing payments but no share heading.

1. Prepare its bulk review. Expect a recognised account review and a separate **Unassigned payments** review. The latter must need attention even when every payment value is readable.
2. Open the unassigned review. Expect its original PDF, printed main account and period, an explanation of the missing account context, and the move controls. There must be no direct **Confirm import** button.
3. Select its payments, record the account evidence and preview a move to the recognised account. Expect both counts before and after. The preview must not change saved reviews.
4. Save the move, refresh and reopen both reviews. Expect every payment once in the receiving review, with original PDF locations and corrections retained.
5. Expect **Payments assigned** for the emptied page and no empty correction controls. The bulk ready count must include only the receiving statement.
6. Import the ready statement. Open its Transactions and the moved payment's original PDF. Expect no duplicate and no second import of the emptied page.
7. Repeat with a PDF that has no recognised receiving account. Expect instructions to obtain the missing account page, no empty destination form and no direct import. Excluding the unassigned rows alone must not mark the account decision complete.

### Check the link from a completed batch to Transactions

1. Use a synthetic case with an imported batch and another imported statement outside that batch.
2. From the batch, select **Open imported transactions**. Expect the batch notice, the dates of those payments, and only that batch's imported payments in the table.
3. Check a batch with more than 100 periods if available. Its table filter must include every imported period, not just the visible batch page.
4. Download **this table view**. Check that its recorded row list and batch source list agree with the displayed filter. Other case payments must not enter that recorded table selection.
5. Select **Clear batch filter**, then widen the account/date range if needed. The other statement's payments should become available again.
6. If the batch gains another imported statement after you opened its transactions, try the old download. Expect an instruction to reopen the batch's transactions so the displayed and downloaded statement lists agree.

### Undated card interest

1. Use a synthetic Capital One statement containing purchases, a payment and a nonzero **Interest Charge on Purchases** with no date beside it.
2. Send it to Financial. If the other fields and checks are clear, confirm that this charge alone does not put the statement in **Needs attention**.
3. Open the review. Check the interest amount against the PDF. The date should remain blank and the review should explain that it was not printed. Do not enter the closing date as its transaction date.
4. Import the ready statement. In Transactions, find the interest charge. Expect **Date not printed** and the statement end shown separately. Check that the charge is included in the totals.
5. In a disposable test case, record a date correction using a known source date and a reason. Expect the corrected transaction to use that date, with the earlier undated reading retained in its history.
6. Confirm that an ordinary payment with an unreadable date still needs attention. The interest handling must not clear that error.


### Compare possible copies before a bulk import

Use synthetic copies in a separate test case. Do not create duplicate live case payments for this test.

1. Send two different PDFs for the same bank, account and overlapping dates from Evidence to Financial. Both should need attention, with the other filename and dates identified.
2. Open one review and select **Compare original PDF**. Confirm the other file opens, then close it and check that your current review is still present.
3. Return to the batch. On the copy, select **Leave unimported**, give a reason and confirm. The original should become ready if it has no other problems. The copy should remain listed with its reason and **Restore to review**.
4. Import the ready statement. Open its transactions and check the expected count and totals. Refresh the batch and confirm that only one statement was imported.
5. Select **Restore to review** on the copy and record a reason. Its saved corrections must remain available, and its overlap with the imported statement must be flagged again.
6. Open the copy, tick the comparison checkbox and enter a reason. Save progress, leave the page and return. Check that the decision was saved. Change its period dates and check that a new overlap is reported without silently reusing the old comparison as a fresh check. Import remains available.
7. Leave the copy unimported when finished. Check that both original PDFs remain in Evidence.

Expected result: overlapping dates are visible for comparison, and the choice to leave a statement unimported persists. Restoring it preserves its source and saved work. Overlap warnings do not automatically prevent import.

### Follow a referenced account and save the question

Use a synthetic statement whose payment descriptions contain an explicit reference such as **Transfer to account 9911223344** and **Payment from account 9911223344**.

1. Import the statement and open **Statements & accounts**. Find **Other accounts mentioned in payments** below the file list.
2. Expect one reference with two supporting payments and **No matching statement imported**, provided the case has no statement for that number.
3. Select **View 2 payments**. Check that both descriptions are present. Open the original statement and compare the printed reference.
4. Select **Save question in Findings**. Check the suggested question, two attached payments and proposed next action. Edit the question and select **Save finding**.
5. Select **Open Findings**, refresh the page and reopen the saved question. Confirm the explanation and both payment links remain available.
6. If the test case includes a matching account statement, tick **Include references with a possible statement match**. Open that account's statements. Expect a possible match, not a claim that the number proves the account owner's identity.
7. Check a payment containing only a telephone number, an amount or an unlabelled trace number. It should not create an account-reference entry.

Expected result: the investigator can follow the reference to its evidence and record what needs to be obtained, without copying payment IDs or descriptions between screens.

### Information pages and damaged payment fields

Use a test collection with known transactions and separate notices. Record the expected transaction count before processing it.

1. Open a recognised Capital One collection with privacy notices, billing-cycle notices or advertisements. Check that those pages do not create transactions or unnecessary coverage warnings.
2. Open **Inspect another page of the original PDF**. Choose a page labelled **information page** and select **Show selected page**. The original notice must still be available.
3. Check a transaction page with an advertisement beside its table. Its payments must remain present, and the advertising text must not become part of their descriptions.
4. Check a payment with a damaged date or missing extracted field. It must remain flagged with a source link. Readable amounts and descriptions should remain available; the system must not silently discard the payment or invent its date.
5. In an Andrews test statement, inspect an **Ending Balance** line and the period/year-to-date fee summary. Neither should be an extra payment. Actual dated fees must remain in the transaction list. A misread date on the ending balance must not cause the following summary text to join a payment description.
6. Include a page the reader does not recognise. Expect **needs coverage check**, then inspect it for missed payments. It must not be labelled harmless solely because it has no detected transactions.

Expected result: recognised information stays available without adding review tasks, while uncertain payments stay visible for optional review.

### Additional dates beside Andrews payments

1. Use an Andrews-style test row with a first date of **06/03** and an additional date of **06/02**, with readable amounts and a matching balance.
2. Open its import values. Expect the first date to be used and the additional printed date to be identified beside it. It should not require a reason merely because the second date is present.
3. Confirm the import and open its original source. Both printed dates must remain available. The extra date must not be labelled as a value date or posting date without source support.
4. Compare a row whose additional date is invalid or later than the first date. That row should still need attention. A missing minus sign, unreadable amount or balance difference must also remain flagged even when both dates are readable.

Expected result: ordinary extra date text does not require repetitive approval, and unrelated payment errors remain visible.

## Check categories, From and To, and money charts

Use an artificial case with at least two incoming and two outgoing payments. Include more than 50 payments to check table paging. If testing card statements, expect **Card credits** and **Card charges** instead of bank money in and out.

1. In **Transactions**, tick two payments. Select **Categorize selected**, type **Team test**, and save. Both rows should show that category.
2. Select one payment's description, then **Edit names and category**. Change its From or To name and save. The source PDF and original description should stay available.
3. Refresh the page. The category and edited name should remain.
4. Choose **Team test** in Category at the top. Only that category should contribute to the transaction totals and chart.
5. Open **Trends**. The selected category should remain active. Check its incoming and outgoing amounts against the two payments. Open its category name under **Money by category** to inspect the supporting payments.
6. Choose **All categories**. Compare category amounts and check that different currencies and credit cards are shown separately.
7. Open **People & businesses**. The edited name should be present. Open the profile and one of its transactions.
8. Open **More financial tools**, then **Payment graph**. Select the person or business and use **Edit this person or business name**. Save and check the same payment back in Transactions.
9. Select payments and use **Export selected**. Check From, To and Category in the CSV. Use **Download these transactions** to check the filtered report as well.
10. Select every matching payment in a list with more than 50 rows. Assign a category, go to the next page and confirm those payments were included. The count should represent the whole selection, not just the visible page.
11. With two editors open on the same payment, save a change in one and try to save the older edit in the other. The older edit should be rejected without overwriting the first person's work.
12. Sign in as a user who can view but cannot edit the case. Categories and names should be visible, but saving changes should not be offered.


## Empty entries, optional notes and balance-only statements

Use disposable test cases for these checks.

1. Open a review with empty, unrecognised entries on more than one correction page. Confirm each input has a visible label even after scrolling.
2. Fill the description of one empty entry, leaving another payment partly filled. Choose **Exclude [number] blank rows from import**. Expect all wholly empty entries across the statement to be excluded, while both partly filled rows remain selected.
3. Select **Undo excluding blank rows**. Check that the entries return without losing the description you entered. Exclude them again; use **Show excluded rows** to inspect their original text or restore one.
4. Correct an amount and the account holder without typing a reason. Save progress, reopen the review and confirm the import. Expect the corrected values and original readings to be retained. Repeat through **Save for bulk import** to check the batch path.
5. Open a balance-only test statement with a readable closing balance and no opening balance. Select **Save statement balances**. Expect an account/statement record, the printed closing balance, no invented opening balance and zero new transactions.
6. Repeat with a printed zero balance. It must remain zero. Repeat with different opening and closing balances: saving must work, and the difference must remain flagged rather than labelled as reconciled.
7. Try an unreadable balance with no payments. Expect an actionable request for a printed balance. Correct the amount without a note, then save. Repeating the same confirmation must not create a duplicate statement.
8. Check Alex's **01 ARRENDO BBVA EUR ENE 2021.pdf** and the other balance-only files on the deployed build. Record whether their actual labels and amounts are recognised. Synthetic examples passing is not confirmation that every BBVA layout is supported.

## Import a group without reviewing each statement first

1. In the main **Statement files** list, select several disposable PDFs containing multiple periods. Use **Select all [number] shown files** for the current list.
2. Search for one selected filename. Check that the count still includes selected files hidden by the search. Clearing the search must restore their selected checkboxes.
3. Select **Prepare statements from [number] files**. Expect the financial batch screen to open directly and contain every recognised account and period. Preparation must not create imported transactions yet.
4. Select **Import [number] records** once. You should not need to open each period or resolve each reading issue first. After completion, check that usable transactions are available, incomplete records retain their sources outside totals, and issues remain accessible. Existing imports must not be duplicated.
5. In a separate individual review containing an unreadable amount, select **Import statement now** above the PDF without opening corrections. Check the same separation between usable transactions and incomplete records after import.
6. Record elapsed user time, number of manual corrections and any unexpected detours for a representative document. Do not use automated test runtime as the time a person needs to process a PDF.

## BBVA balances and small charges

Use a separate test case and a BBVA Mexico **Cash Management** statement supplied for testing. This check does not establish support for every BBVA product.

1. Prepare the PDF with **Use the PDF text where available**. Check that the account, dates and currency agree with its printed headings.
2. For the September 2024 euro sample, expect two charges: €30.00 and €4.80. Both operation dates are 2 September; both liquidation dates are 1 September. The second description continues with **16%** on the next page.
3. Check the opening balance (€60.00), closing balance (€25.20), total charges (€34.80) and two-charge count. Glossary, summary chart and tax-certificate lines must not appear as payments.
4. Import once. Expect two usable transactions and no incomplete records. Open each source and check its printed amount. Repeating the confirmation must not duplicate the transactions.
5. Test a genuinely empty statement of the same layout. Expect its printed balances to save with zero transactions, without requiring any empty rows to be filled in.
6. For a previously incorrect import, use **Review statement: [filename]**, reprocess the PDF, then explicitly replace the old import. Expect only the corrected payments in the active list; the earlier reading must remain in history.
7. Record any unexplained differences or missing charges with the filename and page. Do not enter zeros to make an unreadable amount appear complete.

## Save account details and missing balances without reprocessing

### Before import and across a batch

1. Open a statement with no identified payments or balances. Select **Show items to check**. Expect focus on the balance controls, not the disabled confirmation footer.
2. Add the opening and closing balances with their source pages. Test a printed zero separately from an unknown blank. **Save statement balances** should become available when a valid printed balance is present. In a batch it saves for later bulk import; an individual review saves directly.
3. Add a missing holder and save the batch review. Reopen it and check that the holder persists and its missing-holder warning clears.
4. Search a large batch by a currency token in filenames. Select all matching statements across pages, change the search and check the hidden-selection count. Apply USD, MXN or EUR. Reopen a selected statement: currency, manual account edits and corrected amounts must persist. Unselected and imported statements must remain unchanged. This is not currency conversion.
5. Check the batch counts: usable transactions and incomplete records must be separate. Ordinary unmatched source text must not inflate either count; it remains available in the statement. A damaged amount inside a recognised transaction table must still be flagged.
6. For the older BBVA Bancomer Cash Management format, check the actual source account, period, opening/closing balances and movements before accepting it. The supplied TITANIUM September 2024 PDF has also been checked locally through import and later edits. That does not establish that every historical BBVA file is supported.
7. Mark an unchanged flagged payment **Mark checked**, save and reopen. Its reading flag must stay resolved. A remaining unreadable amount or balance difference must remain visible.
8. Open an old saved review whose source has not changed. Its account and payment edits must persist after the reader upgrade. Only untouched empty text entries should leave the payment selection. A changed source must require comparison rather than silently moving corrections.

### After import

Use an editable test case, not the investigation's only copy.

1. Before import, enter a missing account number beginning with zeros. Select **Save account details**, leave the review and reopen it. Expect exactly the same number.
2. Import the statement, reopen it and check the saved number again. The original extraction must not replace the manual value.
3. From the balance check, select **Open statement and balances → Edit account and balances**. Expect labelled fields beside the original PDF, in the same view.
4. Correct the number and add a missing balance with its printed PDF page. Select **Save changes**. Reopen the editor, statement list and balance check; all should show the saved changes. The payment count and existing payments must be unchanged.
5. Save a printed zero balance and reopen. It must remain zero. Clear it and save; it must become missing, not zero. A balance difference must remain visible.
6. In a second authorised session, change the same statement after the first session opened its editor. The first session's stale save must fail clearly and keep its unsaved text. Repeat with a viewer: the edit control must be absent and a direct save request forbidden.
7. Test an incomplete-only import. Expect **0 usable transactions** and its separate incomplete-record count, including after selecting **Open imported records**. The file list must not describe these as usable payments or a statement with no records.
8. Reprocess a test copy after saving account and balance corrections. Under **Compare earlier values**, check the previous account number and the balances with their PDF pages. They must remain available for comparison without overwriting the new reading.
9. Correct the statement currency in **Edit account and balances**, first to MXN, then USD, then back to EUR. Reopen Transactions, totals and statement checks after each save. Amounts, categories and exclusions must remain unchanged, with earlier currency readings retained. When currency was an incomplete record's only missing field, it should join the usable payments once.
10. For an eligible old BBVA import containing only empty incomplete records, use **Update saved reading and open results**. Check its preview against the PDF first. Expect the recognised payments and balances, no remaining empty records, and the updated batch count. Retry after a simulated lost response: no duplicate payments. The old import must remain in history. Saved row or balance corrections must prevent this shortcut from displacing them.
11. While editing a statement, there must be no **Checks across all accounts** panel. Open **Review accounts → Account checks** deliberately for case-wide checks. Returning to **Statement files** must retain the current review.
12. In the batch list, distinguish two runs with the same file count using their date, starter, batch identifier, sample filenames and reading progress. Open the older one and confirm that its own saved review appears.

Local automated checks do not replace these tests against the deployed version and the team's actual saved imports.
