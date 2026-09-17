# Capital One extraction check, 17 September 2026

This check uses the supplied 222-page statement collection read-only. Original PDFs, private source screenshots and extracted personal data are not included in this document or committed. No documents were uploaded to an external service, and no real transactions were imported.

## Problems corrected

1. **Amounts after a split description.** Six transaction amounts were readable in the original but missed when a description was extracted into two cells. The recogniser now uses the measured column positions and the right edge of the Amount heading. Each original cell and its PDF position is retained. Unclear or conflicting positions remain flagged.
2. **Purchases just before the billing period.** Fifteen printed transaction dates preceded their billing period, with a separate posting date inside that period. Both dates are now retained. For these rows, the posting date can identify the year of a transaction up to 31 days earlier, including across New Year. Unsupported dates, a purchase later than its posting date and a more distant date remain unresolved.
3. **Advertisements beside transactions.** Text beyond the printed table's Amount column stays available in the original source cells. It does not become part of the payment description. An amount in an uncertain position is not guessed from the last number in a row.

## Whole-document regression result

The same saved source extraction was evaluated before and after these changes. This checks the proposal rules; it is not a second independent transcription of every page.

| Check | Before | After |
| --- | ---: | ---: |
| Detected account/period sections | 52 | 52 |
| Proposed transactions, including undated charges | 301 | 301 |
| Matching opening/closing arithmetic | 45 | 51 |
| Unavailable opening/closing checks | 7 | 1 |
| Periods with at least one flagged row | 36 | 29 |
| Transaction-date flags | 16 | 1 |
| Unreadable transaction-amount flags | 6 | 0 |
| Undated interest-charge flags | 29 | 29 |

Twenty rows changed: six gained their amounts and complete descriptions, fifteen gained their transaction dates, with one row in both groups. All row IDs, inclusion choices and original source cells were unchanged. A matching balance does not by itself prove that no payment was missed or duplicated.

## Separate visual sample

Original physical PDF pages 57, 87, 191 and 217 were rendered and read visually. Expected counts and credit/debit totals were recorded separately from the proposals, then compared with their results. All 27 entries in this sample matched the counts and totals. The four nonzero interest charges remained explicitly undated. This is a targeted sample of the reported failures, not a random or full-document accuracy measurement.

Private local records are in the ignored `data/local-runtime/capital-inspection/audit/` directory: `card-flag-audit.json`, `visual-sample.json` and their reproduction scripts. They must not be published with the guide.

## Remaining work

- One transaction predates its billing period without a separate posting date and still needs review.
- Twenty-nine interest charges have no printed transaction date. They now import without a date decision, retain blank printed dates and use explicit statement-end ordering context. The table labels them **Date not printed**. Generic missing dates still require review.
- One period still lacks sufficient opening/closing controls for that arithmetic check.
- Independent transcription of all payments and checks of other supplied statement formats remain outstanding.
- These are local changes. Deployment and team acceptance have not been verified.

## Focused verification

Synthetic tests cover split descriptions, exact amount locations, side advertisements, unreadable amounts, absent or conflicting geometry, separate transaction/posting dates, year boundaries, unsupported dates and fees. A database import regression checks that the corrected dates, amount, complete description and original source cells survive import and that a repeated confirmation creates no second import. The layout context view explains the date basis while retaining separate source links.

## Undated-interest follow-up

The next read-only comparison kept all 52 periods, 301 entries, amounts, original cells, inclusion choices and printed dates unchanged. It removed only the unnecessary date flags on 29 clearly labelled interest charges, including two on interest-only continuation pages. Periods with flagged rows fell from 29 to 1. Opening/closing results stayed at 51 matching and one unavailable. The remaining row has a transaction before its billing cycle with no separately printed posting date. These counts concern row flags, not a claim that every account detail or statement has passed user acceptance.

The original undated charges stay undated. When imported, the existing statement-end sorting context is retained explicitly; it cannot establish the exact day of a payment. A later printed-date correction removes that fallback from the new version and preserves the earlier reading and source link. Focused tests exercise both individual and background bulk imports, rejection of an ordinary missing date disguised as an undated charge, and later date correction. Private reproduction records: `undated-before.json`, `undated-after.json`, `check-undated.py`.
