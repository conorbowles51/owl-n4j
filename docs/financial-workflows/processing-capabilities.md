# Financial processing capabilities

Verified against the shared reader registration and implementation on 24 September
2026. These readers apply across cases and future documents; no reader is chosen
by client name, case ID or a supplied filename. Regression tests retain the
supported layouts as maintained product capabilities.

## Dedicated statement layouts

| Bank or issuer | Supported statement family | Scope and limits |
|---|---|---|
| BBVA Mexico | Cash-management and Maestra account statements, including the tested MXN and USD layouts | Operation/value dates, deposits, withdrawals, balances and prior-period sections; native and scanned examples. Other BBVA products/layouts are not automatically certified. |
| Santander Mexico | Account movement statements, including the tested chequing/peso/dollar and Inversion Creciente sections | Separates printed account products, deposits, withdrawals and balances. This is not support for every investment instrument or Santander country. |
| Kapital | Product statements with separately printed CLABE/currency sections | Deposits, withdrawals, fees, offsets, continuation tables and balance-only sections. Keeps account/currency compartments separate. |
| Intercam Mexico | Product statements and continuation tables | Uses the shared product reader with Intercam recognition; separate currency/account sections and no-activity compartments. |
| Monex | Numbered contract statements containing currency summaries with explicit zero activity | Dedicated recognition currently covers balance-only sections; movement tables and FX executions are not validated by this reader. |
| Scotiabank Mexico | The tested explicit zero-activity statement family | Saves account, period and printed balances without inventing transactions. Does not establish dedicated support for active Scotiabank transaction layouts. |
| Andrews Federal Credit Union | Account/share statements: Base Share Savings, Free Checking and Visa Payment sections | Separate share/account periods, continuations and closure entries. Unassigned continuation payments remain available for account assignment; missing pages and unreadable amounts remain review items. Visa Payment sections do not constitute general Visa card-statement support. |
| Capital One | Credit-card billing statements | Purchases, payments/credits, fees, interest and amount-owed balances; separates accounts and billing cycles. Partial printed card references stay partial. |
| Merrick Bank | Credit-card statements | Transactions, payments/credits and card summary balances. Unreadable dates or account digits remain reviewable. |
| Credit One Bank | Credit-card billing statements | Purchases, payments/credits, fees, interest, credit balances and continuation pages. Added in the statement-collections change described below. |

The latest Credit One reader and additional Andrews date/currency/reread handling
are documented in [statement collection acceptance](statement-collections-2026-09-24.md).
The other registered layouts predate this change. A registered reader does not
guarantee that every scan or later redesign from its bank will be fully readable.

## Collection and source types

- Single statements and collections containing several accounts, months or
  recognised banks/card issuers. Selection, review and import retain the original
  PDF page and separate account type, currency and period.
- Native PDFs, scanned PDFs and PDFs with an OCR text layer. Recognised damaged
  embedded readings can receive a guarded image reread. Unreadable values and
  unassigned pages remain visible; the processor does not calculate missing digits.
- Balance-only/no-activity statements where the source establishes that status;
  an empty extraction alone is not evidence of no activity.
- Deposit receipts have a separate review/import path, distinct from full account
  statements. Informational pages, applications, coupons and tax material remain
  source evidence rather than extra payments.
- A generic statement-table review path remains available when no dedicated bank
  layout matches; its presence is not a claim of automatic bank-specific accuracy.

## Native bank data and other financial evidence

The native Financial processor also registers **ISO 20022 camt.053**, **BAI2**,
**SWIFT MT940** and **NACHA/ACH** readers through the precheck/import API. These are
structured bank/payment formats, not additional named-bank PDF layouts. Their
own format versions, controls, date interpretation and attribution requirements
still apply. They were inspected for this inventory, not re-certified against
new client samples in the statement-collections change.

Any Evidence file can be deliberately selected for Financial, including CSV,
spreadsheets, Word documents and images. That selection records financial
relevance; it does not claim that all such sources use the PDF statement importer
or automatically produce transactions. Their available Evidence readers and
review controls govern extraction. The current legacy Office guidance requires
XLS to be converted to XLSX/CSV and DOC to DOCX/PDF while retaining the original.

## Verification and release status

See [statement collection acceptance](statement-collections-2026-09-24.md) for the
new reader's source checks, synthetic regression tests, real-service browser
journey and release evidence. Earlier acceptance is recorded in
[bank layouts](bank-layout-acceptance.md) and the
[23 September follow-up record](implementation-progress-2026-09-23.md).
Code publication, automatic deployment and independent live verification are
separate facts. This inventory does not assert that old imports have been
automatically repaired or that the requested live content cleanup has run.
