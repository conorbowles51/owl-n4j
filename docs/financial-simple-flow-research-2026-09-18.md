# A simple financial workflow for Loupe

Research and implementation direction, 18 September 2026. This is a design specification, not a claim that the changes are implemented or deployed.

## The user's direction

Keep the parts of Loupe that work. Start with a simple, usable journey and extend it to the other financial views. The user specifically clarified that checking flagged problems **must not block import**.

The normal journey is:

**Add documents → automatic processing → import → investigate transactions → save a finding.**

An investigator can open a flag before importing, after importing, or later. Review is available throughout that journey. Importing records does not assert that all their readings or balances have been verified.

This changes the earlier benchmark's requirement that only statements with cleared checks can be imported. It preserves the accepted Loupe navigation, original-document viewer, corrections, categories, source links and saved findings.

## Research scope

I reviewed official workflow documentation from DocuClipper, Monarch, Xero and MindBridge, plus Valid8's product and investigation material. They were selected for particular tasks, rather than ranked as universally best. DocuClipper is the closest processing reference; Monarch supplies useful everyday transaction interactions; Valid8 is directly relevant to investigations. Xero and MindBridge provide narrower lessons.

The comparison below is based on documented behaviour and the DocuClipper screenshots supplied by the user. The earlier [DocuClipper benchmark](docuclipper-benchmark-2026-09-17.md) records a separate public-demo inspection. This research does not claim a new authenticated trial of these products, comparative extraction accuracy, or measured user-performance results. No case documents were sent to another service.

## What to borrow from each product

### DocuClipper: a statement, its transactions and its checks in one place

Its documented review view supports filtering, selected-row edits and reversible exclusion. Corrections remain associated with the raw reading. Separate account and period selectors let the user navigate collections and repair assignments. The documentation also acknowledges that automatic assignment can be wrong; a dropdown is useful only if the underlying grouping is correct. [Transaction review](https://www.docuclipper.com/docs/matching-transactions/), [account and period assignment](https://www.docuclipper.com/docs/how-to-assign-transactions-to-multiple-accounts-and-periods-in-docuclipper/).

The checking documentation distinguishes a net balance check, row-by-row running balances and printed credit/debit totals. It locates discrepancies and reruns checks after corrections. A totals warning can reflect the bank's grouping convention rather than a wrong transaction. This is valuable evidence for keeping checks explanatory rather than treating every warning as an import prohibition. [Balance and totals checks](https://www.docuclipper.com/docs/review-transactions-balance-and-totals-checks/).

**Loupe application:** retain the side-by-side viewer and file/account/period navigation. Put a short issue description beside the affected field, with previous/next issue controls. Keep the import action available when checks are outstanding. The non-blocking import policy is the user's requirement; it is not a claim about every DocuClipper import or export path.

### Monarch: the transaction list is already useful

Monarch documents a short edit path: open a transaction, change its fields, and save changes in context. Bulk changes begin with selecting transactions and show the affected count. Review status is a filter and can be assigned by rules. Transactions are already present while this review happens. [Editing transactions](https://help.monarch.com/hc/en-us/articles/360048393532-Editing-Transactions), [reviewing transactions](https://help.monarch.com/hc/en-us/articles/5528707082516-Reviewing-Transactions).

Its rules can match original statement text and preview affected records. An edit can become a reusable rule. Cash-flow analysis offers time periods and category or merchant breakdowns without requiring a budget to be created first. [Transaction rules](https://help.monarch.com/hc/en-us/articles/360048393372-Transaction-Rules), [cash flow](https://help.monarch.com/hc/en-us/articles/20504904768020-Cash-Flow).

**Loupe application:** one working transaction list; click a category to change it, click a row to see its source, select rows to act on them together. A category change updates the same records in People, Trends and exports. Reusable categorisation can follow once that basic interaction works. Preserve source readings separately from investigator labels.

### Valid8: transactions become an investigation

Valid8 describes source-linked transaction evidence, custom categories, account-transfer views and indexed evidence reports. Its Stories feature groups transactions of interest into collections that can support an investigator's explanation and subsequent report. These are vendor descriptions, not independently verified accuracy claims. [Financial crime workflow](https://www.valid8financial.com/use-cases/financial-crime), [Stories](https://www.valid8financial.com/resource/valid8-launches-stories-to-accelerate-financial-fraud-investigations).

**Loupe application:** select relevant payments, choose **Create finding**, write the question or observation, and retain those payments and their sources together. Reuse Loupe's existing Findings. The investigator should not have to navigate to an empty page and work out how to reconstruct the evidence they were just examining.

### Xero: act where the relevant line is visible

Xero's reconciliation detail puts the bank line alongside its matched account transaction. Its cash-coding workflow uses a spreadsheet-like list, selection and a counted bulk action. These interfaces connect a decision to the records being affected. Xero reconciliation is primarily matching statement lines to accounting entries; that is different from checking whether Loupe extracted a PDF correctly. [Reconciliation details](https://central.xero.com/0/article/View-bank-reconciliation-details), [bulk cash coding](https://central.xero.com/0/article/Reconcile-using-cash-coding-US).

**Loupe application:** show corrections alongside their source; make the scope of a bulk change visible. Keep accounting setup, tax coding and matching requirements outside Loupe's ordinary investigation path.

### MindBridge: a flag should lead somewhere useful

MindBridge documents a transaction detail view that explains the contributors to a risk score and offers actions to create a task, mark a transaction normal and navigate to another item. The transferable pattern is an explanation and action attached to the transaction. [Transaction and entry details](https://support.mindbridge.ai/hc/en-us/articles/1500001228061-Transaction-and-entry-details).

**Loupe application:** a flag says what was found and opens the evidence needed to assess it. For example, **Closing balance differs by $21.19** leads to the printed balance and the relevant transactions. Introducing a new risk score is unnecessary for this flow.

## The smallest complete journey

### 1. Bring records in

Use the existing upload or Evidence file/folder selection. Both lead to the same processing list. Show filenames and progress, and identify the accounts and periods as they become available. Already imported records reopen; retries do not create another copy.

The primary action is **Import transactions**, with the record count. A secondary **View issues (3)** action is available. Flags do not require an acknowledgement or written exception before the user can continue. Completed files remain available while another file is still processing or has failed.

Files with no usable extraction retain their filename, original and a specific retry/error action. They must not stop other files. A non-statement can be removed from Financial while its Evidence original remains available.

### 2. Arrive at the transactions

After import, open the actual records. Show the imported count and an unobtrusive issue count. Keep one account/date scope, one search field and **Filters**. Active category, currency and other filters appear in this same area rather than in another toolbar elsewhere on the page.

The table retains Date, Description, From, To, Category, Money in and Money out. Balance remains available where recorded. Source-statement review continues to show the statement's actual columns; the investigation table is a separate view of those records. Keep pagination and a clear total count. At narrower widths, show less detail per row and keep every field available in the row panel.

Row click opens the transaction and original beside the list. Category editing is available on the category itself. Selecting rows reveals the relevant actions: categorise, compare, create a finding and export. There is one selection count and one affected-record set.

### 3. Review when useful

**View issues** filters the existing records and opens the first selected issue beside its original. **Next issue** moves directly to the next one. An investigator can correct a value, leave it for later, or record that a discrepancy exists in the original. Navigation and saved work survive refresh and file switching.

Checks rerun after an edit. Resolved flags disappear from the outstanding list. A note that the original contains a discrepancy records a reviewed difference; it does not turn that difference into a matched balance.

No second mandatory acceptance process follows the initial import.

### 4. Extend the same records into investigation

| Investigator's question | Extension of the basic flow |
| --- | --- |
| Who paid or received this? | Select From or To, open that name's payments, edit the recorded label if needed, and return to the same transaction. |
| What did we spend on travel? | Select the Travel category and see its payments and totals. Categorise additional selected rows in place. |
| How did money move over time? | Trends opens the same scope, with a chronological money-in/out chart. Select a period to see its transactions. |
| Which categories account for the amount? | Switch the Trends breakdown to categories. A bar opens the supporting records. |
| Where did this payment go? | Open related payments or Follow money from the selected transaction. Connections lead back to the recorded entries and originals. |
| What do I want to record? | Select payments, create a finding, and save the explanation with its evidence already attached. |

Keep the existing navigation. Improve these connections incrementally rather than replacing it with another set of destinations. More specialised graph, tracing and history controls remain available when the user needs them.

## Non-blocking review, precisely

Import progress and data quality are separate properties. A statement can be **Imported · 3 issues**. A transaction can be used while its balance warning is still open. An uncategorised payment is not an extraction failure.

| Condition | User experience | Totals and analysis |
| --- | --- | --- |
| Readable transaction with a balance discrepancy | Import it and retain a source-linked warning. | Use its recorded amount; show the unresolved check when relevant. |
| Date unreadable, amount readable | Keep the record accessible with Date unresolved. | Include its amount in applicable totals; show undated records separately from the dated chart. |
| Amount or credit/debit side unreadable | Retain the incomplete record and source in the workspace, with a direct correction action. | Do not invent an amount or sign. Show the count of records not included in calculated totals. |
| Account or currency unresolved | Keep the records under an explicit unresolved group. | Do not assign them to an invented account or combine unknown currency with a known currency. |
| Possible duplicate | Retain the concern and an easy comparison/exclusion action. | Do not silently remove records on a weak similarity match. Exact repeated import requests remain idempotent. |
| Summary, advert or rewards text | Retain it in the original; do not manufacture a payment row. | It contributes no transaction or amount. |
| File processing actually failed | Show a specific failure and retry for that file. | Other files and existing transactions remain usable. |

The distinction between incomplete source records and calculated transaction amounts may use separate storage internally. The user must be able to find and correct both in the same financial workspace. A displayed import count must explain how many records have amounts available for calculation. No hidden second queue should make incomplete records appear lost.

Bank money-in/out and credit-card credits/charges keep their appropriate labels. Different currencies stay separate. Missing statement coverage stays distinct from a known period with no transactions. These distinctions belong in the relevant values and states, with fuller explanations on demand.

## Changes to the current implementation

Code inspection confirms the current gate: `import_batches.py` marks a statement `attention` when problems exist, and `queue_import` takes only `ready` items. `FinancialBatchPanel.tsx` disables bulk confirmation when no ready statements exist. Its imported-summary path also clears the problems list. The new direction needs an independent, persistent issue state; enabling the button alone would not implement it correctly.

The current local category work provides useful data and edit endpoints. Its additional header filter, transaction controls and category comparison add presentation layers. Consolidate those controls into the existing transaction workflow and Trends view. Preserve their stored categories, From/To edits and correction history.

Relevant implementation areas:

- [Import classification, queuing and imported summaries](../backend/services/financial/import_batches.py)
- [Batch screen and import action](../frontend_v2/src/features/financial/components/FinancialBatchPanel.tsx)
- [Current financial header/category filter](../frontend_v2/src/features/financial/components/FinancialPage.tsx)
- [Transaction filters, selection and category comparison](../frontend_v2/src/features/financial/components/LedgerRowBrowser.tsx)
- [Transaction table](../frontend_v2/src/features/financial/components/InvestigationTransactionTable.tsx)
- [Original and transaction details](../frontend_v2/src/features/financial/components/LedgerSourceDialog.tsx)
- [Trends](../frontend_v2/src/features/financial/components/InvestigatorTrends.tsx)

The separate generic live batch-import failure is still unresolved. A more permissive review policy does not fix an import exception. Diagnose that failure from its actual server error or a reproducing source, retain retry safety, and verify the deployed path separately.

## Development order and acceptance

1. **Make import and review independent.** Persist outstanding issues after import, carry incomplete records into the workspace, update counts and calculation exclusions, and keep retries idempotent. Preserve the original and existing corrections.
2. **Complete one transaction journey.** Import, find a payment, open its original, change a category, correct a value, and save a finding without losing context. Consolidate repeated controls within the current pages.
3. **Extend that working journey.** People, Trends and Follow money reuse the same scope, selected records, source panel and edits. Categorisation rules can follow the direct edit/bulk path; they are not a prerequisite for it.
4. **Verify in the actual application.** Use focused checks for the changed behaviour, then one complete browser journey at the milestone. Update guides and light-mode screenshots after the implementation matches it.

Use a clearly synthetic acceptance example: two files, three periods, 52 transaction records, one unreadable amount, one missing date and one balance discrepancy. This is a proposed fixture, not an observed result.

- All 52 records become accessible without reviewing the three issues first. Calculated totals explain that one amount is unresolved; the undated record remains findable.
- A separate failed file does not prevent importing the processed files.
- Both the transaction view and statement view expose the same outstanding issues after refresh.
- Fixing the amount updates totals and charts; resolving a date puts the record into its proper time bucket. Neither creates a second transaction.
- The investigator opens the original, changes a category, edits From/To, returns to the list and saves a finding with the same selected payments.
- A chart or name opens the exact payments behind it. Pagination and selected counts do not hide further records.
- Existing bank and card examples retain correct amount conventions. Currency and account scope remain explicit.
- Import failure, no transactions, unresolved values and filtered-empty results have different messages and recovery actions.

Completion means this journey works in Loupe and survives navigation and refresh. A new diagram, more buttons or passing isolated component tests are not a substitute for that result.
