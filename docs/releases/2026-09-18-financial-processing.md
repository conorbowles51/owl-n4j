# Financial statement processing, 18 September 2026

This release completes the local A-E development and acceptance plan in the DocuClipper benchmark. It retains the investigator workspace and improves how documents become usable transactions. Deployment verification and team acceptance are recorded separately; they are not implied by the local results.

## What an investigator can do

1. Select PDFs or folders in Evidence and send them to Financial. Processing and per-period review status stay on the server.
2. Choose a file, account and statement period. Original PDF navigation is separate from transaction and problem navigation.
3. Import ready periods together. Open each remaining problem beside its original, correct it, save and continue. Saved unfinished reviews survive navigation and loss of browser tab storage.
4. Compare opening/closing balances, running-balance intervals and recognised printed totals. Merrick fee and interest totals are compared with their own charges. Checks use current corrections and exclusions; unavailable checks are explained.
5. Correct several selected rows with a preview, complete missing years from a checked statement date, or assign extracted payments to a recognised account/period. Original text and reasons remain recorded.
6. Compare overlapping statements before importing both. Leave a duplicate unimported with a reason and restore it later if necessary. Retrying a confirmed import does not add it again.
7. Open the exact batch's imported transactions, inspect originals, examine account references and save investigation questions with their supporting payments.

## Difficult-file improvements

Capital One multi-period reading retains 52 periods and 301 proposed entries, with 51 opening/closing matches and one unavailable check in the supplied collection. Recognised undated interest does not need an invented transaction date.

Andrews reading recovers previously missed account pages and payment boundaries, retains extra printed dates, reads measured wrapped credit-voucher amounts and makes an unassigned continuation available for reviewed account assignment. Bounded image rereading can recover specific damaged amounts, balances and dates when complete readings agree.

Merrick reading distinguishes headings and zero-charge information from actual payments, recognises measured mailing names and repeated date context, flags missing payment minus signs, and compares fee/interest subtotals. Four valid-looking interest amount errors in the supplied scans now have direct charge/total checks.

These changes do not guarantee error-free extraction. Damaged scan fields still need correction. Two Merrick names remain unreadable; uncertain payment histories or account assignments remain review work. An image reread can be worse than the PDF text, so it remains an explicit option with earlier-review comparison. Existing imported payments are not silently rewritten by new reading rules.

## Recorded checks

- The combined financial regression covered 4,712 backend cases and 1,386 frontend cases. Environment-related backend failures and stale fixtures were resolved and affected cases rerun. Later changes have their own focused checks; see persistent state for exact results.
- All 87 ready reviews from the four retained collections were confirmed and immediately retried in disposable databases. They produced 339 payments exactly once. Ready review counts include balance-only reviews.
- Synthetic browser journeys cover mixed-folder processing, saved incomplete corrections, recovery without tab storage, overlap decisions, account reassignment, missing years, wrapped-source values and exact import scope.
- The final charge correction journey imported three synthetic payments once, then opened their original PDF. The production build and read-only compiled-browser source/guide checks pass with no JavaScript errors.
- Real PDFs were read only. Private statements and audit crops are not in this release. The user guide and testing guide are updated and retain light-mode screenshots.

## Release boundary

The user cancelled the intermediate deployment while Alex was working. These changes were held locally until the complete local benchmark passed. This is the final development release for that plan, not another partial checkpoint.

The current Loupe deployment URL is still needed for the authenticated deployed check. The previously supplied IP now serves an unrelated website and must not receive Loupe credentials or case data. A successful Git push proves publication to the repository, not a successful server deployment.
