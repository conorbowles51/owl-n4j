# Supplied statement checks, 15 September 2026

This is a development inventory of all 567 PDF pages across the eight supplied filenames. One 56-page file is byte-identical to another, leaving seven unique files and 511 unique-file pages. Private filenames, account details, source text and page images stay in `data/local-runtime/financial-completion-page-inventory.json`. This inventory is not independent transaction ground truth or an accuracy score.

| File type | Pages | Result and remaining source work |
| --- | ---: | --- |
| Capital One collection | 222 | 52 account/period choices and 301 proposed payments. Preparation now retains unboxed summary text beside drawn payment-notice tables. All 106 opening/closing balance readings are preserved. One period repeats on pages 43/45/46 and 49/51/52; compare both copies and exclude repeated payments and balances before import. |
| Capital One older collection | 108 | 27 account/period choices and 42 proposed payments. All 54 opening/closing balance readings are preserved. Previously flagged undated interest and damaged values still need checking. |
| Merrick collection, two identical filenames | 56 each | 42 account/period choices and 235 proposed rows from the retained OCR reading. Damaged dates remain flagged. Pages 8, 14, 24 and 44 are interest-calculation continuations; 24 and 44 have damaged account headings. Pages 51/52 are payment-history supporting records, not bank-statement transaction tables. |
| Andrews larger collection | 99 | 44 recognised account sections and 2,044 proposed payments. Page 13 is printed continuation page 5 without its page 4 predecessor. Its account cannot be assigned from a neighbouring page. Page 41 is summary information. Page 42 is a separately reviewable deposit receipt. |
| Andrews smaller collection | 24 | 15 recognised sections and 381 proposed payments in the existing text reading. On page 12 the savings-share identifier is read as `ODDO`; it is not silently replaced with digits. Check the original and use Read from page images if needed. The checking section on the same page remains separate. Page 11 is summary information. |
| Wells Fargo wire report | 1 | Checked as a supporting payment document. It can be saved in Findings and linked to an existing payment without creating a second payment. |
| Simple bank statement | 1 | 12 payments, separate opening balance, credits of EUR 1,035,000 and debits of EUR 1,000,000. Page headings, beneficiary information and references remain outside payments. |

The remaining pages are account/statement sections, recognised card terms, notices, advertisements, applications, membership/signature forms, legal documents or blank pages. The two Capital One files include five pages with only a production number and eleven entirely blank pages, respectively; their original renders were inspected. No page was counted as a successful transaction extraction merely because it contained text.

## What an investigator can do with unresolved source information

1. In statement review, open **Inspect another page of the original PDF**. Pages not assigned to a statement are marked **needs coverage check**.
2. Compare the original page with the extracted values. Use **Read the statement again > Read from page images** when the PDF is legible but its text reading is damaged. The new reading remains separate until explicitly imported or used to replace an existing import.
3. Correct a flagged value only when the original supports it, and record the reason. If a payment is missing but its account and period are established, use **Add a missed transaction** on the original page.
4. For repeated opening or closing balances, open each page link, compare the source, clear a repeated balance and explain why. Check for repeated payments too. A repeated balance is not shown as a missing balance.
5. If the account cannot be established or a page is absent, retain the gap and request the missing or clearer evidence. Do not assign the payment to the nearest account merely to complete an import.

## Verification evidence

- 78 focused backend checks cover table preservation, coordinate rotation, statement grouping, conflicting headers and generic statement proposals.
- 16 statement-review component checks cover balance editing, retaining a repeated original while clearing its import value, separate date fields, failed confirmation, refresh and replacement controls.
- A source-only browser check reprocessed the actual 222-page file, opened its first period with three payments and both summary balances, and followed the opening amount to its original PDF position. The earlier reading remains available. No real payments were imported.
- Private preparation and proposal caches bind these counts to the original source hashes. New preparation is required for previously processed files whose unboxed text was omitted. The reader version is `statement-review-v13`.

The remaining recovery and combined investigation checks are tracked in the financial completion plan. Independent human reference reviews are a separate acceptance item.
