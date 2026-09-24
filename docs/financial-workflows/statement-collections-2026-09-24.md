# Reusable bank and card collection readers

24 September 2026. The user asked that each supplied layout become an ongoing
Loupe processing capability for future files and all cases. Client PDFs, extracted
rows, page images and detailed source-check results remain outside the repository.

## Investigator journey

1. Upload a document or deliberately send an existing Evidence file to Financial.
2. Read the PDF. A recognised statement with unreadable embedded dates or amounts
   receives a targeted image reread. Ordinary readable pages keep their text.
3. Choose the bank/account, currency and statement period within the PDF. The
   selector identifies checking, savings and credit-card sections. Mixed
   institutions and months use the same catalog; neither filename nor case ID
   chooses the parser.
4. Review the original page beside the payments and controls. Purchases, card
   payments, fees and interest keep their separate directions. A card debit
   increases the amount owed; a credit reduces it. Bank balances remain assets.
5. Import the chosen section, see its receipt and payments, then return to choose
   another account or period. Reopening retains the saved account and source
   citations. Repeating import does not add the same payments again.
6. Correct genuinely unreadable fields in the existing source review. A missing
   preceding page cannot establish the ownership/share of continuation payments;
   those payments remain available through the account-assignment workflow.

## Shared implementation

- `credit-one-card` identifies the complete issuer heading, printed account and
  cycle on each physical page. It groups matching continuation pages and separates
  other cards, banks and months. Activity-summary balances exclude repeated
  payment-coupon balances. Credit balances retain their printed trailing minus.
- Credit One transactions include posting and transaction dates, references,
  wrapped descriptions, negative payments/refunds, fees and interest. Summary
  totals, annual totals and interest-calculation illustrations are not additional
  payments. Printed zero interest remains an excluded source row.
- The Andrews share reader now accepts spacing within printed date digits and
  retains additional date text. Its verified US share layout establishes USD for
  bare amounts; explicit conflicting currency evidence still takes precedence.
  Savings/checking share boundaries, shuffled-page handling, membership paperwork
  and separate receipt review remain part of the existing collection workflow.
- Before selecting an image reread, Loupe requires the same printed account and
  period, the same payment/control counts, and fewer unreadable fields. A worse
  reading, missing geometry, changed identity or image timeout retains the native
  reading with a recorded reason. This check measures reading completeness, not
  truth or complete statement coverage. It never calculates missing digits from
  balances and never conceals unresolved source readings.
- Parser revision `statement-review-v31` and PDF reading revision
  `bank-payment-rows-v6` distinguish new proposals/checkpoints. Existing saved
  imports are not replaced simply because a reader changed. Existing recovery
  and reviewed-reread safeguards preserve investigator corrections and history.

## Acceptance evidence and limits

Local source inspection covered both supplied PDFs, including rendered page
headers, account/share boundaries, transaction tables and supporting paperwork.
Private source checks exercised the production extractor and statement catalog
through a disposable database. Some OCR values remain unreadable, and a printed
page-number gap in the bank collection remains a source-coverage issue. These are
visible review requirements, not a claim that every original amount was recovered.

Synthetic checks cover mixed banks/cards in one PDF, multiple accounts and
periods, liability balances, year boundaries, dates before the cycle that post
within it, continuation descriptions, damaged fields, conflicting identities,
cross-case rejection, repeated import and saved reopening. A real-service Chromium
journey selects bank/card sections, imports each, switches sections and reopens
their independently persisted payments. The existing Financial persistence
journeys also pass; authentication and PDF canvas rendering are substituted in
that disposable browser harness. Actual source page rendering was inspected
separately, outside Git.

Final local checks: 197 backend tests plus 135 subtests passed across the bank
readers, catalog, currencies, imports and persistence. The PDF extraction/worker
suite passed 57 tests; the five targeted reread tests passed again after the final
logging change. All seven real-service Chromium persistence journeys and five
section-picker unit tests passed. Scoped frontend lint, production build and the
workflow action inventory completed successfully. Private source probes use the
production canonical page-location mapping, preserving native/OCR origins.

Publication triggers automatic deployment through the standing release workflow.
Independent live verification and the previously requested live content cleanup
remain subject to the existing live-origin access restriction. No live documents,
running ingestion jobs or investigator records were changed by these tests.
