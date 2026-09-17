# Financial information-page check, 17 September 2026

This is a local, read-only comparison of the seven supplied prepared files. It does not import transactions, change case evidence or send documents to another service. Private readings and source images remain outside Git.

## What changed

- Recognised Capital One privacy notices, billing-cycle notices and referral advertisements no longer require a statement-coverage decision. They remain available as original information pages. A page containing a transaction heading or dated amount is not cleared by the notice recogniser.
- An unreadable date in a recognised card row does not discard its readable description and amount. A measured payment line with a missing field remains an unresolved row. Nothing fills a date or amount by guessing.
- Seven damaged Merrick section headings are kept out of payment rows. This requires a standalone heading with no digits and a nearby, exact section-total label. Unknown text and amount-bearing lines remain flagged.
- Andrews period/year-to-date fee summaries are not additional payments. An explicit Ending Balance label closes its account section even if the date text is damaged. Its readable balance remains a control and its misread source date remains unchanged. A following summary page cannot join the preceding payment description.

## Complete prepared-reading comparison

These are proposed-entry and flagged-row counts, not independent accuracy scores. A flagged entry can have more than one issue. Counts do not include all account-detail or coverage decisions.

| Prepared source | Review choices | Entries before / after | Flagged rows before / after |
| --- | ---: | ---: | ---: |
| Capital One, 222-page collection | 52 | 301 / 301 | 1 / 1 |
| Merrick, 56-page collection | 42 | 260 / 253 | 142 / 135 |
| Wire report | 1 document review | 0 / 0 | 0 / 0 |
| Synthetic Nexus statement | 1 | 12 / 12 | 0 / 0 |
| Andrews, first collection | 44 statements and 1 deposit-receipt review | 2,044 / 2,041 | 200 / 197 |
| Andrews, second collection | 14 | 296 / 296 | 116 / 116 |
| Second Capital One collection | 27 | 42 / 42 | 0 / 0 |

Every review-choice identifier stayed the same. Every retained payment kept identical proposed fields and original source cells. The only removed payment candidates were the seven Merrick headings, two Andrews summary rows and one Andrews ending balance. That ending balance is now a retained balance control.

The first Capital One collection gained 13 recognised information pages, leaving none of its extracted pages unassigned. The second gained three. One Andrews fee-summary page is now an information page. This does not establish that every physical page was successfully extracted or every payment was found.

Original pages were inspected for the Capital One billing notice and privacy notice, the Merrick fee heading and the Andrews fee-only summary. The comparison also caught a temporary regression that appended summary text to an Andrews balance row. The final comparison confirms that no retained payment description changed.

## Remaining difficult-file work

The supplied older Merrick and Andrews readings contain damaged dates, amounts, signs and joined columns. Those issues remain visible. Some Andrews rows also print two different dates without headings, so the reader does not silently choose a meaning for the second date. The large remaining flag counts mean these files still need usability work and a local rereading comparison. This checkpoint alone does not close the difficult-file acceptance target.

Independent transcription of all payments, deployed checks and team acceptance have not been completed. A matching balance or unchanged proposal is not a substitute for those measurements.

## Reproduction and verification

Private baseline and current records are under ignored `data/local-runtime/context-audit/`, `context-audit-after/` and `context-audit-final/`. The final `result.json` contains aggregate counts; `preservation.json` records the exact candidate changes. Original PDFs and private fields must not be committed with this report.

Six focused classification tests cover complete versus mixed information pages, missing card cells, unreadable dates, damaged section headings, fee-summary exclusion and damaged closing dates. The affected Andrews suite passes with the six new cases, 24 tests in total. The page-selector test checks that information pages remain reachable. Intake tests check the updated file-selection and processing messages.

## Follow-up: extra dates and damaged headings

Visual inspection of Andrews page 6 confirmed that extra dates appear beside payment rows and on continuation lines. The earlier reader demanded a decision only for the same-line layout. The first printed row date now stays in use consistently. A readable additional date on or up to 31 days before it is retained without inventing a posting-date or value-date role. Invalid, later or more distant additional dates still require review. The row editor explains which date is used.

The first Andrews collection retains 2,041 entries; its flagged rows fall from 197 to 104. The second retains 296 entries; flags fall from 116 to 104. All 116 additional printed dates, all primary dates, amounts, descriptions and source cells are unchanged. The remaining flags concern other fields or checks. A database regression confirms import without a per-row reason, original-date retention and an idempotent repeated confirmation.

On Merrick, a damaged date-column heading can be recognised only with the other two exact headings, consistent measured columns and at least two other readable payment dates in that section. This recovers descriptions for 18 previously unresolved rows and readable amounts for 16 of them. It does not repair or invent any transaction date. Existing recognised fields, inclusion choices and source cells are unchanged.

A separate local Tesseract reading of all 56 Merrick page images took approximately 234 seconds. It recognised 42 review sections and 235 proposed entries with 153 flagged rows, compared with 253 entries and 135 flags in the retained reading. Some amounts improved while dates worsened. These differing counts require source comparison; the new reading was not substituted into the case or treated as successful extraction. A small private date-crop experiment recovered several readable date strings but was not adopted as an automatic repair rule.

This comparison does not close the remaining difficult-file acceptance work. Its private records are `andrews-additional-date-comparison.json`, `merrick-layout-comparison.json` and `merrick-image-comparison.json` under the ignored final-audit directory.

## Follow-up: bounded visual date rereading

A new local OCR pass rereads unclear dates only in recognised Merrick date columns and explicitly labelled statement dates. It requires measured source positions, a complete primary line reading and agreement from another visual reading. Conflicting valid dates remain unresolved. Readable dates, amounts, descriptions, signs and balances are not rewritten by this helper. The page deadline bounds the retries. Original text, accepted text, rectangles and all attempted readings are retained in page provenance and the runtime record includes this code's fingerprint.

The final read-only run of all 56 pages took about 251 seconds. Against the same image-reading baseline, it retains 42 sections, accepts 59 date rereads across 18 pages and reduces flagged entries from 153 to 101. Proposed nonzero/unresolved entries change from 235 to 230 because five previously unresolved zero-charge lines are now identified as zero charges. Row addresses are identical, and all amounts, descriptions, credit/debit choices and balances are unchanged. This improves the explicit image-reading option; it does not automatically replace the older prepared text or any imported statement.

Visual inspection was performed on all 73 accepted crops from an intermediate attempt. It found one wrong date: printed 10/11 was read as 10/14. That attempt was rejected. The final rule refuses the incomplete-primary pattern responsible for it, as well as 13 other incomplete-primary readings. Every one of the final 59 accepted date readings is unchanged from a visually checked, matching crop. This is an assistant visual comparison, not a blinded independent review or a general accuracy guarantee.

A separate manual transcription of 33 entries from original pages 9 and 13 checked dates, amounts and credit/debit placement. It found two valid-looking amount errors on page 9, 28.40 read as 26.40 and 35.81 read as 35.61, which had no individual row warning. Other missing fields remained flagged. After filling only those missing fields in memory, the shared closing check reported a 2.20 difference, so the statement was not labelled a match. Page 13 matched after its missing fields were filled. No corrections or imports were saved to either real statement. The amount errors remain a documented limitation of the image reading and must not be hidden by a lower date-error count.

An image reread of the smaller 24-page Andrews collection took about 148 seconds and retained 14 sections, 296 entries and 104 flagged rows. It did not reduce the manual work, so repeated OCR is not the solution for that collection. Next work should address the specific unresolved fields and repeated date-context decisions rather than rerunning the same whole-file reader.

Focused validation: 19 date-region cases, affected extraction/provenance checks, and existing canonical-text/runtime-manifest checks pass. The guides include the rereading and original-comparison steps. The difficult-file acceptance items remain open. The compiled app and deployed workflow have not yet been updated for this checkpoint.

Private records are under `data/local-runtime/context-audit-final/`: `merrick-refined-image-comparison.json`, `merrick-date-reread-preservation.json`, `merrick-visual-payment-sample.json`, the retained rejected intermediate readings and `andrews-second-image-comparison.json`. Original PDFs and case evidence were unchanged, and no external processing service was used.
