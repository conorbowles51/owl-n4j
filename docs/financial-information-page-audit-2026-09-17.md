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


## Bounded rereading of damaged Andrews money cells

A second local image-reading pass now examines damaged amount and running-balance cells on recognised Andrews payment rows. It requires the printed bank/title, measured row and column positions, and agreement from complete visual readings. It never fills an amount by calculating from a balance. Different valid digits or signs remain unresolved. A positive rereading of an ordinary withdrawal is rejected rather than adding a missing minus sign. The retry is capped at 40 cells and 30 seconds per page, within the page's existing deadline.

In the smaller supplied collection, a read-only whole-file run took 165 seconds. It retains all 14 section identities, all 296 transactions, every row address, inclusion choice and existing payment value. Twenty-two damaged cells on ten pages gained readings: ten amounts and twelve balances. All 22 were visually compared with the original crops. Flags decrease from 104 to 89. The newly readable balances also expose three additional running-balance differences, retained for review. No real evidence or imports were changed.

An earlier crop experiment obtained a matching positive reading for a printed negative amount. Visual inspection caught the missing sign. The final rule refuses that result, and the regression is tested. Conflicting or incomplete readings are not outvoted. This is an improvement to image rereading, not a claim that 296 transactions were independently transcribed or that the difficult-file acceptance target is complete.

The remaining 89 flagged rows include 57 amount problems, 14 unreadable balances, 14 date problems, 9 running-balance differences and 3 direction problems. Categories overlap. The larger Andrews collection has not been reread with this helper yet. Existing stored readings are not silently replaced. Original money text, source rectangles, attempted readings and accepted values survive in page provenance, and the runtime record includes the helper's code fingerprint.

Validation: 22 focused money-region and provenance tests pass. The affected PDF/geometry/text-origin/manifest checks also pass: 52 passed initially, and the one expected-response fixture missing the new empty refinement list passed after correction. Private diagnostic records are `andrews-refined-image-reading.json`, `andrews-refined-image-comparison.json`, `andrews-money-preservation.json` and the two visual comparison sheets under the ignored final-audit directory. No external OCR provider was used.

## Follow-up: missing Andrews pages and separate payment rows

The next source comparison found a completeness problem that a lower flag count had not exposed. In the smaller collection, August's first statement page had no readable bank logo, although it printed the full account and period. November page 4 had `11/01/20` misread as `LI/GL/20`, breaking continuation to pages 4 and 5. These pages had remained available for coverage review, but their transactions were absent from the proposals.

An opening with an unreadable logo now requires a valid share opening, a continuation notice and an immediately adjacent, branded printed page 2 with exactly matching account and period. Conflicting details, page gaps and missing notices are rejected. A bounded visual reread of an Andrews period header requires one readable full date, measured bank/title/account context and complete agreement from two crop readings. The new date must form a valid period of at most 62 days. The November crop was visually inspected and both readings returned the printed `11/01/20`. Existing readable dates are untouched. This header pass has a 15-second maximum within the page deadline.

Damaged date text split into several words also caused genuine payments to join the preceding description. A recognised payment verb beginning in the measured date column now keeps that row separate. Its unreadable date stays flagged; readable amounts, signs and balances remain available. No date is inferred from neighbouring transactions.

The smaller collection now has 16 account-period sections and 383 proposed entries, compared with 14 sections and 296 entries. The 87 additions comprise 22 payments on physical page 9, 21 on page 10, 32 on page 21, five on page 22 and seven separately recovered payment lines on pages 19 and 20. All four newly grouped transaction pages and the seven other row crops were inspected against the originals. All prior section identifiers and source cells are preserved, as are every existing date, amount, sign and balance. Descriptions stop absorbing the recovered payments; running checks recalculate. Flags rise from 89 to 128 because the previously missing rows contain real reading problems. This is not a claim of full-field accuracy for the 383 entries.

Two account applications, two account agreements and the August fee-only page are now retained information pages. No extracted page in this smaller collection remains unclassified. This means the prepared pages have a recognised purpose, not that every value is correct. Mixed payment/information pages and unfamiliar content remain reviewable.

The larger collection retains 44 account-period sections and gains 24 separately identified payments, taking its proposals from 2,041 to 2,065. All 24 source crops were visually checked as genuine payment rows. Existing dates, amounts, signs, balances and source cells remain unchanged. No original PDF, saved review or imported record was modified. The period-header image pass was checked on the one affected original page; the larger collection has not been reread with it.

Validation: 31 focused backend tests and 54 date/money OCR tests pass. Negative cases cover conflicting accounts/periods, gaps, missing logos/notices, ambiguous headers, invalid dates, mixed payment pages and false continuation boundaries. Private records are `andrews-grouping-comparison.json`, `andrews-grouping-proposals.json`, `andrews-large-grouping-comparison.json` and the associated page/crop images in the ignored audit folder. Proposal revision is v19. Existing saved inputs retain their comparison and recovery path.

A separate experiment with the official Tesseract `tessdata_best` English model was not adopted. Some fields improved, but one sampled Merrick page gained date problems and an Andrews page changed its row count. Those results do not justify changing the default model. No document was sent to an external OCR service. Difficult-scan accuracy and the two D acceptance items remain open.

## Follow-up: compact money crops

The next fallback uses the existing local OCR model with a 300/450 dpi crop and a white border when the larger crop has no complete agreement. It retains all earlier valid readings when checking for a conflict. It requires a complete compact primary reading, four completed attempts and at least two identical valid results. A disagreement or missing withdrawal sign stays unresolved. Measured fragments within the same amount or balance column can be read together. The 40-cell/30-second page bounds remain unchanged.

A whole-file read-only check took 187.6 seconds. All 16 sections and 383 entries remain, as do the earlier 22 accepted money readings and one period-heading reading. Twenty-one additional money cells gain readings, all compared visually with the source crops. Existing proposed dates, amounts, directions, balances and descriptions remain unchanged; only diagnostic differences and shifted column references are allowed to recalculate. The original PDF hash is unchanged.

Flagged rows fall from 128 to 116. Remaining overlapping issue counts are 79 unreadable amounts, 19 balances, 28 dates, five running-balance differences and three direction conflicts. These are not dismissed as successful extraction. Private records and the accepted comparison image use the `andrews-compact-*` prefix in the ignored audit folder. A separate 28-date crop experiment produced conflicts and has not changed the transaction-date reader.

28 focused money-region tests pass, including compact-profile conflicts, fragmented primary readings, lost minus signs and separate OCR fragments. A synthetic database import test also confirms that a newly separated damaged-date payment requires correction, preserves its original date cells and is not duplicated on repeat confirmation. No real imports were performed. Deployment remains held and D remains open.

## Follow-up: Andrews transaction-date image regions

The reader now revisits damaged dates on measured Andrews payment rows with an unambiguous printed account and period. It requires a complete primary reading, four completed attempts, at least two identical dates, no other valid conflicting date and a result within that period. It leaves readable dates and two-date fields alone. Original words, rectangles and observations remain in provenance. The 20-cell and 15-second limits sit within the page deadline.

An eight-page read-only comparison recovered 12 previously unresolved transaction dates. Every accepted crop was visually checked against the original. All 16 sections and 383 entry identifiers remain. Existing amounts, balances, directions and descriptions are unchanged. Flagged rows fall from 116 to 111 and date issues from 28 to 16; several corrected rows still have other problems. The final geometry guard requires both amount and balance columns and was checked against every accepted source row.

84 focused OCR and runtime-manifest tests pass. The records and visual comparison are under the ignored `andrews-row-date-*` files. No original PDF, saved review or case transaction was changed. These corrections do not close the difficult-file acceptance work or resolve the remaining money errors.

## Follow-up: cleaned single-line money readings

The 78 remaining measurable amount crops exposed a segmentation problem. Raw-line mode frequently omitted the printed minus or introduced a leading digit. Ordinary single-line mode on cleaned crops produced 65 agreed values, all matching visual comparison. The production helper therefore starts with six single-line readings at two resolutions and three ink thresholds. It needs a complete primary, at least four complete matches across both resolutions and no conflicting valid value. The older profiles can complete an insufficient reading only when all complete values agree. It does not vote away a disagreement or calculate money from balances.

The new 24-page run took 208.76 seconds and retains all 16 sections and 383 entry IDs. It adds 77 money refinements, comprising 62 amounts and 15 balances. Every new crop was visually compared. Two earlier amount refinements become unresolved because the new readings disagree. No existing proposed date, description or other previously readable financial value changes; no real saved review or import is written. The PDF hash remains unchanged.

Flagged entries fall from 111 to 49. Nineteen amount problems, four balance problems, 16 dates, ten running-balance differences and three direction conflicts remain, with overlapping categories. The ten running differences include five newly exposed by readable values. These are not hidden to improve the result count.

39 focused tests cover both reading profiles, conflicts, partial primaries, lost signs, deadlines, geometry and retained provenance. An additional 48-cell artificial raster check accepted nine amounts with no incorrect accepted value, leaving the others unresolved. That small experiment is not a general accuracy score. Private records are the `andrews-line-*` comparison and crop files. The normal-line, border and threshold choices follow the options described in [Tesseract's image-quality guidance](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html); their benefit here is supported by the local comparisons, not guaranteed by the documentation. Difficult-file acceptance remains open.

## Follow-up: repeated Merrick dates and missing heading context

Four closing-date image readings were recovered by requiring agreement at two resolutions with the independently printed full statement date and year-to-date year. All four original crops were inspected. Other full valid readings cannot conflict. This additional corroboration applies to the repeated closing date, not to arbitrary transaction dates. On two other pages, the separately labelled, readable closing date and full YTD year supply context when the statement-date heading was not recognised. Source labels remain distinct and no coverage range is invented.

The six-page image comparison, combined with the unchanged readings from the other pages, retains 42 sections and 230 entry identifiers. Existing proposed fields remain unchanged. Thirty-five previously missing full dates become available. Visual inspection of their month/day crops found 34 correct and one already misread month: page 46 prints 09/25, although its original OCR read 08/25. An interest-charge date check now flags that difference. It also flags a second existing difference on page 26, which still needs original comparison. Nothing changes a transaction's date to match the closing date automatically.

The final comparison has 70 flagged entries, down from 101. Remaining overlapping issues include 42 unreadable dates, 13 unresolved year/context dates, 14 amounts, four credit-sign problems and two interest-date differences. These counts do not include account-detail or coverage decisions. The unresolved case on page 12 has conflicting complete crop dates and remains unchanged.

48 focused date OCR tests and 22 Merrick proposal tests pass. The guide explains repeated-date checks, closing-date context and the new interest-date warning. Private records use `merrick-repeated-date-*`, `merrick-heading-*` and `merrick-completed-year-crops-*`. No real review or transaction was written. The 14 unclassified pages include two genuine payment-history pages; they cannot all be treated as harmless information. Difficult-file acceptance remains open.

## Follow-up: Merrick supporting pages

The originals of all 14 unassigned pages were visually inspected. Twelve contain a cover letter, two application pages, a cardholder notice, four interest-calculation pages and four pages of records-request/certification paperwork. Recognised combinations of their printed headings and text now identify these as information pages. All tables on each physical page are checked for payment headings and dated amounts before this classification applies. Original pages and their figures remain available.

The two payment-history pages, 51 and 52, contain 33 genuine payment records and stay available for financial review. They are neither dismissed as information nor appended automatically to monthly statements. Those records can overlap statement payments, include account references and contain no printed currency or receiving-account identity on the list itself. Their separate review needs those details checked before import.

The comparison retains all 42 sections, 230 entries and 70 flagged rows with byte-for-byte equal proposal objects and unchanged source cells. Unassigned pages fall from 14 to two. Proposal revision is v21. Private record: `merrick-supporting-pages-comparison.json`; the four `merrick-supporting-pages-*.png` sheets were all inspected. Page 26's original was also inspected separately and confirms that its interest date is printed 09/25, rather than the OCR's 08/25. Both newly flagged interest-date differences therefore correspond to observed reading errors. No real data or original PDF was changed.

## Follow-up: zero-interest lines with damaged dates

Six remaining flagged Merrick rows are explicitly labelled interest charges with a readable amount of 0.00. Their measured columns agree with the transaction header. All six original crops were inspected and show no charge. They now follow the existing zero-charge exclusion without requiring a date correction; their original cells and parsed fields remain unchanged. An unclear amount, nonzero amount, misplaced amount or unfamiliar description retains review. Proposal revision is v22.

The read-only result retains 42 sections and all source rows, with 224 included entries and 64 flagged entries. Only the six confirmed zero-charge rows change exclusion/kind/issues. The comparison and inspected crop sheet are `merrick-zero-interest-comparison.json` and `merrick-zero-interest-crops.png` under the ignored audit folder. All 23 Merrick proposal tests pass, including the existing unfamiliar-zero-row guard.

Two additional date-image experiments were not adopted. Six thresholded, compact line readings accepted none of the 42 remaining unreadable date crops under the agreement rule. An unrestricted text-reading sample still returned fragments or conflicting characters. Their records remain as `merrick-cleaned-date-experiment.json` and `merrick-unrestricted-date-experiment.json`. They do not change the reader or clear any remaining date flag.

## Follow-up: remaining flagged fields and the larger collection

Every remaining flagged row in the smaller Andrews image reading (49) and Merrick (64) was compared visually with its original line crop. All are real payments or nonzero charges. No further heading or zero-interest false candidate was observed in this flagged set. Some arithmetic differences concern a correct row immediately after an incorrectly read balance. The warning must retain that interval for review. This does not measure unflagged errors or establish whole-file completeness.

Merrick dates such as a day of 44 previously received the missing-year instruction. Proposal v23 distinguishes invalid month/day, unreadable characters, dates outside the closing month and previous month, and genuinely missing year context. Andrews warnings now ask the user to check both the number and its sign. Source comparison shows that a minus can be lost or become a digit; reversing direction alone would not fix the latter. All 47 focused backend checks pass. Original fields remain unchanged by this wording correction.

Four widened Merrick original crops confirm trailing minus signs outside the OCR word rectangles. An 18-region money experiment still had incomplete or conflicting readings, so no change to the OCR reader was adopted. The private sheets and records use `merrick-remaining-flags-*`, `andrews-remaining-flags-*`, `merrick-missing-sign-crops.png` and `merrick-money-region-experiment.json`.

The 99-page Andrews collection was also read once using the current optional whole-image mode. It took 888.7 seconds and retained the original PDF hash. It produces 41 account-period sections, 1,418 included entries, 254 flagged rows and 36 unassigned physical pages. By comparison, the retained PDF-text sources with current proposal code produce 44 sections, 2,065 entries, 113 flagged rows and six unassigned pages. The image reread is worse for this input and has not replaced any evidence, saved review or import. It is a comparison of reading modes, not an independent accuracy measurement. The existing text-first default and saved-reading comparison remain necessary. Private records use `andrews-large-current-*` and `andrews-large-retained-text-comparison.json`. No repeat whole-file run is warranted without a relevant reader change.

## Follow-up: amounts with a readable but conflicting sign

The bounded Andrews image rereader now considers a measured amount whose sign already conflicts with its Withdrawal or Deposit description. It requires complete matching image readings for the replacement digits and sign, retaining all original words and observations. The description selects a damaged region for checking; it never supplies the amount or sign. Readable nonconflicting values, adjustment credits and zero values are unchanged.

Three affected pages from the smaller collection were reread. Two recoveries match the inspected original crops: a minus previously read as an extra leading digit, and an omitted minus. A third candidate has conflicting complete readings and is unchanged. All 16 sections and 383 entry identifiers remain. Only the two recovered amounts/directions and recalculated diagnostics change. Every other field remains equal. Flags fall from 49 to 47. All 52 focused reader tests pass. Private comparison and inspected image: `andrews-sign-comparison.json` and `andrews-sign-accepted.png`. No real saved review or transaction was changed.

Visual inspection of the larger collection's six unassigned pages found three account forms, one dividend-only summary, one deposit receipt and a genuine statement continuation with a missing preceding page. Physical page 13 prints July page 5, directly after printed page 3. It has ten payment rows but no share heading. Those payments are outside the 2,065 proposed entries and remain available for coverage review; they must not be counted as handled or silently assigned across the missing page. The receipt also remains financial. These findings are retained for the next recovery-workflow check.

## Follow-up: unassigned continuation pages and remaining-row review

A missing printed page in the larger Andrews collection prevents safe automatic share assignment for ten payments on physical page 13. These now appear in a separate assignment-only review. An investigator can select and move the extracted rows to a recognised account/period with a preview and reason. Direct import is refused. Completed assignments do not re-enter the ready queue. All 44 existing sections and complete proposal objects remain equal; original source cells are untouched. A synthetic database/browser journey verifies saved assignment, refresh, exactly-once destination import and original-document navigation.

Physical page 1 is a recognised primary-member application and page 41 a dividend-only summary. Both remain viewable information pages. The application guard distinguishes the form's STATE ID label from a dated account-share opening. The remaining unclassified physical pages are 3, 4, 13 and 42, including the actual payment continuation and deposit receipt. Unfamiliar text is not dismissed automatically.

All 113 flagged payment rows in the larger retained reading were visually inspected in twelve private crop sheets. None was an advertising or summary row. Some running-balance flags involve an earlier incorrect balance. The inspection found a further layout problem: long credit-voucher descriptions can contain a readable trailing amount or place amount/balance on a following line. This is still development work, rather than an unavoidable manual-reading exception. It remains open before difficult-file acceptance. The crop review is not an independent transcription of all 2,065 proposed payments.

## Follow-up: amounts printed with or below credit-voucher descriptions

The larger Andrews file exposed two repeatable layouts: a refund amount at the end of the exact credit-voucher description, and an amount/balance pair immediately below that description. Proposal v25 reads these only when the printed wording, measured positions, same-page coordinates and complete money values agree. It does not infer money from a running balance. Original rows and cells remain unchanged; separate field references identify money on the following line. Selecting either cell opens the parent payment editor. Imported source highlights include both lines.

Read-only comparison retains all 44 ordinary sections plus the assignment-only review, and all 2,075 included entries. Eleven previously unresolved payments now have amounts and balances, reducing flagged entries from 113 to 102. Every one of those eleven original crops was visually checked and agrees. The other changes are eight parent links on the excluded continuation lines and nine newly available balance comparisons. The smaller collection remains exactly unchanged at 16 sections, 383 entries and 47 flagged rows. No real case, saved review or PDF was changed. Private records: `wrapped-vouchers-5-comparison.json`, `wrapped-vouchers-6-comparison.json`, `wrapped-vouchers-summary.json` and two inspected crop sheets in the ignored audit folder.

Validation includes 28 Andrews reader tests, an exactly-once database import with retained money sources, 43 affected frontend checks, TypeScript and scoped lint. The added frontend test initially used the wrong accessibility label; the corrected test passes, with all other 42 checks already passing. Its two unsupported test-query options were removed before TypeScript passed. A fresh artificial browser case verifies a saved description correction, recovery after clearing tab storage, import of exactly three payments, and an original PDF highlight covering the wrapped money. No JavaScript errors. Browser harness selectors were corrected for the actual save endpoint, navigation back to the batch and the visible source panel; the completed import was not repeated.

This closes the specific wrapped-layout defect found during the remaining-row review. Final combined build/workflow acceptance is still required before declaring the development ready. The remaining flags concern actual payments, uncertain fields or a running-balance interval affected by a misread neighbouring value. This flagged-row audit is not an independent transcription of the entire files or a guarantee of unflagged accuracy.
