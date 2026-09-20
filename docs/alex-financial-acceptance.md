# Alex's financial workflow acceptance

20 September 2026. Earlier component tests and public deployment checks did not establish that Alex's 588-file workflow worked. This pass covers the reported failures together, including existing saved work.

| Concern | Implemented outcome | Evidence and remaining acceptance |
| --- | --- | --- |
| Empty rows and irrelevant issues | Unrecognised summary/account text stays outside payments. Saved reviews with unchanged sources retain corrections while untouched empty entries are excluded. | Parser, saved-review and batch regression tests pass. Full 588-file extraction remains unverified. |
| Balance-only statements | Save the account, period and printed balances with zero transactions. Visible labelled opening/closing controls distinguish zero from unknown. | Synthetic balance-only import/reopen and Chromium interaction pass. Actual ARRENDO PDF was not available. |
| Missing balances after import | Edit account and balances beside the PDF; update statement checks in the same save. | Supplied TITANIUM PDF and synthetic missing/zero/stale-save cases pass. |
| Account holder and number edits | Persist before and after import, including leading zeros, reopening, batch review and history. | Combined source/import/detail tests pass, including saved older drafts. |
| USD, MXN and EUR | Printed currency detection, preserved edits during bulk assignment, and inline currency correction after import without FX conversion. | Supplied PDF roundtrip EUR → MXN → USD → EUR preserves amounts/categories and updates Transactions, totals and checks. Unknown-currency records become usable together when no other field is missing. |
| Repeated reasons and flags | Routine corrections and completing missing fields have optional notes. Mark checked records an automatic review decision for a correct flagged row. Actual unresolved fields stay visible. | Frontend import decision plus backend persistence, arithmetic and optional-note tests pass. |
| Imported but invisible | Separate usable payments, balances and incomplete records in receipts. Current batch counts follow corrections and replacement readings. | Supplied PDF imports two payments and opens the same saved values through transaction queries; synthetic pagination tests already cover large results. |
| Previously imported BBVA empty records | Eligible imports offer Update saved reading and open results, using the existing PDF; original reading is retained. Saved payment/row/balance corrections are protected. | Supplied PDF replay: simulated 223 incomplete/0 payments becomes 0 incomplete/2 payments. Repeated request adds nothing. Batch count follows replacement. Actual live import has not been changed. |
| Confusing save and issue navigation | Explicit saving/importing actions; missing details and balances lead to their controls; failed saves retain drafts. | Existing browser tests and refreshed component tests pass. |
| Unrelated account checks during review | Case-wide checks only appear under Review accounts → Account checks. | FinancialPage regression verifies their absence in Statement files/review. |
| Indistinguishable batch runs | Date, starter, short batch identifier, reading progress and sample filenames distinguish runs; older batches remain accessible. | Two runs with 588 files open their own saved batch in the UI test. |

## Verification

- 187 backend tests passed across statement details, BBVA, batches, router permissions, optional review, arithmetic, saved-review upgrade and corrections. Shared imported fixture tests are included in that count.
- 117 component tests passed across seven affected areas; the additional Mark checked interaction test passed separately.
- Two Chromium browser tests passed for adding statement balances and editing saved details beside the source. Synthetic PDF placeholders test interaction/layout, not extraction. Both current screenshots were inspected.
- Two private local journeys used the supplied TITANIUM PDF's extracted text and table geometry in an isolated database: the complete import/edit/currency/totals flow and recovery of a simulated legacy empty import. Opening 60.00, charges 34.80 and closing 25.20 agree; original readings and retry behavior are checked. The private source and receipts are excluded from Git.
- TypeScript/production build, scoped lint and publication checks are recorded with the release checkpoint after completion.

## Still required for full acceptance

Alex is testing in **Neil finance**. Do not use the client case for acceptance writes. No live case was modified in this pass.

The actual ARRENDO file, the remaining bank formats, and the full 588-file set are not available locally. Their location has been requested. Therefore this is not a claim that every statement in that batch now extracts correctly, nor that the existing live batch has been repaired. Test the released flow on Neil finance first, then replay the full supplied corpus before marking full-batch acceptance complete.
