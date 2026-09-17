# Loupe financial testing guide

Follow this guide in order for your first test of Financial. It starts with two invented statements and ends with a saved report that a colleague can open. You do not need previous experience of Loupe.

**Updated: 17 September 2026.** Use the full **User guide** for detailed explanations of each tool. This testing guide tells you what to try and what result to check. A result is only a pass after you have checked it yourself.

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
7. In its **Reason for correction or decision**, enter **This is the test document footer, not a payment.** Do not invent a date or amount for it.
8. Check the import count. It should now say **6 transactions** and offer **Confirm import of 6 transactions**. Opening and closing balances must remain outside that count. Do not confirm yet; first try step 4.

**Expected:** the table still shows the original statement. The footer remains available as an excluded reading, with your explanation. The six actual payments remain selected. If the footer is already excluded in a later build, check that there are six payments and continue without changing it.

![Checking statement beside the extracted table, with the footer flagged below it](images/01-statement-check.png)

*This is the checking PDF supplied with this guide. The flagged footer is separate from its payment table.*

![Correction controls used to exclude the test document footer](images/02-exclude-footer.png)

*Clear Use on the footer row and record why. The excluded footer must not become a seventh payment.*

For a wrong payment value, use **Edit import values** or **Show corrections and import choices**. Correct the field against the original and give a reason. For this exercise, leave the correct payment amounts unchanged. If any other line is flagged, inspect it before importing and record the unexpected result in your test notes.

Before resolving the footer, also check the confirmation area. **Before you can confirm** should identify the footer and offer **Review row**. That button must open the matching correction controls even if they were closed. After the footer is excluded and its reason recorded, the blocker should disappear and confirmation should become available.

## 4. Leave the review and return

1. While the checking statement is still unconfirmed, open **Transactions**, then return to **Statements & accounts**.
2. Reopen **checking.pdf** from **Statement files** if necessary.
3. Check that the footer is still excluded and its reason remains.
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
6. Select **Clear payment filters**. Use **More filters**, choose USD if needed, and set both the minimum and maximum amount to **120**. Check that the USD 120 outgoing payment is the result. Clear the filters again afterwards.

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
4. If a file contains several statement periods or accounts, choose each recognised section separately. Check that edits made in one do not appear in another.
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
5. For a clean statement, confirm once without opening every transaction. For a flagged statement, select **Show items to check** and verify that each blocking row opens directly for correction.
6. Check a period with a balance difference and one with no readable balance controls. Neither must be labelled as having matching balances.


### G. Import ready statements together and fix one flagged row

1. Use a separate test case containing at least two clean synthetic statements and one with a known ambiguous date or unreadable amount. Send their Evidence folder to Financial.
2. Wait for **Files checked** to finish. The clean statements should be **Ready to import**. The problem statement should be **Needs attention**, with the actual field or row identified. A multi-period PDF should list its recognised periods separately.
3. Read the ready statement and transaction counts, then select **Import [number] ready statements** once. Only those statements should become **Imported**. The problem statement must remain outside Transactions.
4. Refresh the page. Imported counts must remain correct and the problem must still be available. Reopening the batch must not import duplicates.
5. Tick **Show statements needing attention only**. Select **Go to this row**. Confirm that its correction controls and the matching PDF page open directly.
6. Correct the value against the synthetic source and enter a reason. Select **Save for bulk import**. The batch should reopen and show the statement ready, unless another problem remains.
7. Close and reopen the batch. Open that statement again and confirm that the saved correction is retained. Then import the newly ready statement.
8. Open Transactions. Check the exact counts and totals against your synthetic source files. Confirm that every imported row can still open its original PDF.
9. If a test file fails processing, confirm that its error remains visible with **Open file review** and **Retry this file**. Other successfully imported statements must remain available.

**Expected:** folder processing leads directly to a persistent Financial batch, ready statements import together, flagged statements stay out until fixed, saved corrections survive reopening, and repeated actions do not add duplicates.

## Check corrections, automatic checks and saved progress

Use artificial test statements in a test case for these checks.

1. In Evidence, select a folder containing statements and use **Send to Financial**. Confirm the selected PDFs. Check that Financial opens the processing batch.
2. Open a ready statement with running balances. Check that **Balances between payments** gives the number of checked intervals.
3. Select a printed transaction and **Edit this row**. Increase its credit or debit amount by 1.00 and enter a correction reason. Expect a balance difference with a link to the affected row. The original printed value must remain visible.
4. Select **Save progress**. Return to the batch, reopen this statement and refresh the page. Expect the corrected value and reason to remain.
5. Clear that transaction's date and select **Save progress** again. Expect the statement to remain under **Needs attention**, with import unavailable. Saving incomplete work must not add transactions.
6. Restore the date and amount from the PDF. Expect the checks to run again and the difference to clear. Use **Save and open next problem**. Expect another statement with a problem to open, or the batch list if none remains.
7. For a PDF containing several accounts and periods, change **Account**, then **Statement period**. Check that next/previous period stays in the chosen account. Search a long collection using **Find a period**.
8. Import all ready statements. Expect the exact transaction count shown before confirmation. Refresh and repeat opening the batch; no duplicate payments should appear.
9. If a synthetic statement deliberately contains a printed balance error, keep its printed values. Select **I checked these differences against the PDF**, enter **Why the difference remains**, and save. Expect the difference and explanation to stay recorded. Change an amount again; the previous acknowledgement must no longer accept that new difference.

Record the filename, account, period, action, expected result and actual result for any failure. Do not repair a test result by changing the original PDF.

### Check individual saved progress and repeated corrections

1. Open an unimported synthetic statement from **Statements & accounts**. Clear one transaction date, select **Save progress** and wait for the saved message. Import should remain unavailable.
2. Reload and reopen that statement. Expect the unfinished date correction to remain. Restore the date from the PDF and enter the reason.
3. Open **Correct several rows**. Select two rows, choose **Switch credit and debit**, add a reason and select **Preview corrections**. Expect only those two rows in the preview, with their current and proposed columns.
4. Apply the changes. Expect new balance differences where the switched values no longer match the statement. Switch the same rows back with a reason, then save. Expect the original values to remain visible in the printed table throughout.
5. If two authorised reviewers open the same saved review, save a change from one and then attempt to save the older review from the other. Expect a conflict message; the later attempt must not overwrite the first saved review.
6. If reprocessing changes a reading with an earlier saved review, open **Earlier saved reviews** and **Compare earlier values**. Expect individual and bulk corrections, including changed periods, to remain available. Compare them, tick the comparison box and select **Save comparison for this file**. Reload to check that the comparison remains saved. It must not add payments.

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
6. Open the copy, tick the comparison checkbox and enter a reason. Save progress, leave the page and return. Check that the decision was saved. Change its period dates and check that the old comparison no longer authorises import.
7. Leave the copy unimported when finished. Check that both original PDFs remain in Evidence.

Expected result: no duplicate payments are added without a deliberate comparison. A skipped statement can be restored without losing its source or saved work.

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

Expected result: recognised information stays available without adding review tasks, while uncertain payments stay visible and require a decision.

### Additional dates beside Andrews payments

1. Use an Andrews-style test row with a first date of **06/03** and an additional date of **06/02**, with readable amounts and a matching balance.
2. Open its import values. Expect the first date to be used and the additional printed date to be identified beside it. It should not require a reason merely because the second date is present.
3. Confirm the import and open its original source. Both printed dates must remain available. The extra date must not be labelled as a value date or posting date without source support.
4. Compare a row whose additional date is invalid or later than the first date. That row should still need attention. A missing minus sign, unreadable amount or balance difference must also remain flagged even when both dates are readable.

Expected result: ordinary extra date text does not require repetitive approval, and unrelated payment errors remain visible.
