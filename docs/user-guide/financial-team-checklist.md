# Financial testing: a first investigation

Use this checklist for the first team test. Allow about 25 minutes. The two PDFs below contain invented accounts and payments, with known results you can check. After this exercise, try a copy of a real statement in a separate test case.

## 1. Download the two test statements

- [Checking account: six payments](checking.pdf)
- [Savings account: two payments](savings.pdf)
- [Download both statements and this checklist](financial-test-pack.zip)

Create a new case with a name such as **Financial test - your name - 16 September**. Open its **Financial** view. Use a separate case for each tester so another person's imports or corrections do not change your expected results.

## 2. Upload and check the statements

1. Open **Statements** and select **Upload PDFs**. Select both downloaded PDFs.
2. Wait for each file to finish reading. Open the checking statement from the file list.
3. Compare its original PDF with the extracted statement. Check the dates, descriptions, payment amounts and running balances under the headings printed on the PDF. Opening and closing balances must not be selected as payments.
4. Confirm the checking import once. It should add **six transactions**.
5. Open the savings file and confirm its **two transactions**.
6. Open **Transactions**. Clear payment filters and choose all accounts with no date restriction.

Expected results before making any corrections:

| Account | Payments | Money in | Money out | Closing balance printed on the PDF |
| --- | ---: | ---: | ---: | ---: |
| Checking, ending `/0040` | 6 | USD 1,550.00 | USD 895.00 | USD 875.00 |
| Savings, ending `/0000` | 2 | USD 305.00 | USD 0.00 | USD 355.00 |
| Both accounts | 8 | USD 1,855.00 | USD 895.00 | Check each account separately |

The USD 300 transfer appears once leaving checking and once entering savings. Both are real entries on these invented statements, so both remain in the transaction table. The combined net movement is USD 960.00; it is not an account balance.

## 3. Find a payment and open its original

1. Search Transactions for **Example Supplies**. There should be two payments: **USD 120.00 on 5 July 2020** and **USD 75.00 on 16 July 2020**.
2. Open the USD 120 payment, then open its source file. Confirm that it is the matching row in the checking PDF.
3. Close the source and payment details. Your search should still be present.
4. Open another financial tab, return to Transactions, then refresh the browser. Check that your search and place are retained.

Report it if the original is unavailable, the wrong row is highlighted, or changing tabs loses the search.

## 4. Make an explained correction

1. Open the USD 120 payment again and select **Correct a value**.
2. For this test, change only its description to **Payment to Example Supplies - test correction**. Keep the date, amount and balance unchanged.
3. Select **Preview correction**, enter **Checking the correction workflow on synthetic data** as the reason, then record the correction using the confirmation shown.
4. Reopen the transaction. Check that the corrected description and the previous reading are available and that its original PDF has not changed.
5. Check that there are still **eight current transactions** and the totals above are unchanged.

## 5. Investigate the payments

1. Open **People and businesses**. Open the payments behind **Alpha Consulting**. There should be two incoming payments, USD 900 and USD 650, totalling **USD 1,550**.
2. Open the payments behind **Example Supplies**. The two outgoing payments total **USD 195**. Follow either one back to its original.
3. In **Transfers**, use the July 2020 dates and compare the two accounts. Inspect the USD 300 leaving checking and arriving in savings on 3 July. Record a match only after opening both sources.
4. Open **More financial tools**, then **Payment graph**. Load the connections and open the payments behind a name. Confirm that the payment list and source links work.

## 6. Save work that a colleague can reopen

1. Return to Transactions and select the two Example Supplies payments.
2. Select **Save selection with a note**. Name it **Example supplier payments** and explain that the two payments total USD 195.
3. Open **Findings** and reopen the selection. Check that both payments and their source links are present.
4. Create one more observation using **Add note** on the USD 300 transfer. Explain what you would investigate.
5. In Findings, include both notes in a report. Build it, preview it and save it to the case.
6. Reopen the saved report, include its supporting PDFs and download the package. Confirm that the notes, selected payments and original statement are included.
7. Ask a colleague who has access to this test case to reopen the saved report. Your unsaved browser drafts are not shared, but the saved report must be.

## 7. Try a real statement

Use a separate test case and keep the original file. Check the account, period, transaction count, dates, Credit/Debit or Amount columns, balances and page references. For a long PDF, check the first, middle and last pages, including any account change or continuation page.

A flagged date, unreadable amount or missing page should lead to a visible correction, source or rereading action. Do not fill a value solely to make a warning disappear. A successful synthetic test does not prove that every real statement format will read correctly.

## Working with a large case

Large imports, transaction lists, saved selections, payment graphs and reports are available. Three analysis tools still need a smaller selection of dates or accounts:

| Tool | Current limit for one check | What to do |
| --- | --- | --- |
| Transfers | 500 payments across all accounts, and 1,000 possible pairs or reference comparisons | Enter a shorter **From date** and **To date**, then select **Find possible transfers**. Both sides of the transfer need to be within those dates. |
| More financial tools > Payments and case events | 1,000 payments | Choose an account or shorter dates, select **Apply**, then **Load payments and case events**. |
| Patterns | 1,000 payments; further limits apply when there are many possible matches | Choose an account or shorter dates, select **Apply**, then **Find patterns**. If the message asks for a smaller range, narrow it again. |

Pattern checks can also stop above 200 proposed matches, above 50 payments in a repeated-name group, or after examining 10,000 possible steps between accounts. When a limit is reached, the tool displays a message instead of returning an incomplete result. A failed or refused check does not mean that no matches exist.

Dates follow you between investigation tabs. Check them before starting the next analysis. A result describes only the selected dates and accounts. Separate date ranges can miss a relationship that crosses their boundary, so these tools do not yet replace one complete analysis of a large case.

## Report a problem

Send these details with each issue:

- The case name and the tab or button you were using.
- What you did immediately before the problem.
- What you expected and what actually happened.
- The filename, page and transaction involved, where relevant.
- A screenshot and the exact error message, if any.
- Whether refreshing changed the result.

Keep private statement files and screenshots within your team's approved channels. If an import appears to have stalled, reopen the statement and check its current status before uploading or importing it again.
