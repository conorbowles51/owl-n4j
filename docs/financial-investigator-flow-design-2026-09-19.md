# Loupe: a simpler working flow for investigators

Approved design, 19 September 2026. Builds on the [product research](financial-simple-flow-research-2026-09-18.md) and the workspace accepted on 16 September. The interaction specification is below. The import-to-finding path, shared payment actions, chart views and navigation are implemented locally; validation and remaining deployed acceptance are recorded in [the build state](loupe-build-state.md). Local implementation does not establish deployment or team acceptance.

## The design decision

Make a transaction a dependable starting point for investigation. From it, the investigator can see the original, change a reading or label, find related payments, compare them, and record a finding. Each action carries the relevant records forward. Returning brings the investigator back to the same place.

Keep the current Loupe case navigation and financial pages. Their contents should share this working pattern. Simplification comes from reducing repeated decisions and preserving context, rather than removing useful investigative capabilities.

The everyday journey is **add records → import → examine payments → record and share a finding**. Automatic checks accompany it. Reviewing them is optional and never a prerequisite for importing.

## Why the current experience still feels difficult

The screens expose several versions of the same task: file processing, statement review, a transaction table, payment selections, source inspection and separate analysis tools. The user must understand those divisions to get a straightforward job done. Repeated totals, filters, explanations and action rows increase the effort of locating the actual records.

The missing connection is the investigator's current question. A person looking at a receipt wants to examine what happened next. A person selecting payments wants to categorise or record them. A person looking at a chart wants its supporting entries. Those actions should be immediately available in that context.

The three repeated elements will be:

1. **Working scope:** which accounts, dates, currencies and filters are included.
2. **Records:** the transaction list, statement or analysis the user is examining.
3. **Current work:** the selected transaction, comparison or finding, opened beside those records.

There should be at most two work areas side by side. Opening a source replaces the content of the current detail area; it does not add a third permanent pane.

## One concrete investigation

The synthetic Nexus example gives the design a specific task:

> Find the EUR 125,000 received on 18 March. Inspect the statement. Compare it with the EUR 120,000 outgoing payment two days later. Record a question about the recipient, with both source entries attached.

The successful path:

1. Import the statement. Outstanding extraction flags remain available.
2. The transaction list opens. Search for GlobalTech or select the relevant name.
3. Open the March receipt. The original opens at its row beside the list.
4. Choose **Related payments**. Show a small dated list with an explicit criterion, such as same account, following seven days. The user can widen it or use their own selection.
5. Select the outgoing payment and choose **Compare**. Show both records chronologically: EUR 125,000 in; two days; EUR 120,000 out; EUR 5,000 difference. Both source links remain available.
6. Choose **Create finding**. The two payments are already attached. The investigator enters a title and question, optionally a next action, and saves.
7. Return to the same list. The two rows now show that they belong to a finding. A colleague can reopen the finding and both sources.

The comparison does not prove that the same funds were transferred or that the statement's named bank is the ultimate recipient. Those remain questions for investigation. The interface should make this distinction through precise labels and accessible source details.

## Arrival and import

An empty case offers **Add statements** and **Choose from Evidence**. Existing Evidence folder/file selection also opens this destination directly. A returning investigator resumes their last financial view. After an import, open Transactions filtered to the new records, with a visible **Show all case transactions** action.

Use one file register with filename, detected accounts/periods, transaction count and progress. Expand a file to its periods. A file containing fifty statements remains one file with fifty identifiable periods. File/account/period selectors belong to statement work, not the global investigation filters.

The primary action is **Import transactions**, with the current count. The adjacent issue count is a link. Do not ask the user to acknowledge every warning, supply reasons for unchanged values or visit each period before importing. Processed files can be imported while other files continue in the background.

Keep these states distinct:

- **Processing:** progress and the ability to leave and return.
- **Available to import:** extracted records exist; issues may also exist.
- **Imported · 3 issues:** records are usable and concerns remain attached.
- **Could not process:** explain the failure for that file and offer retry; other files remain usable.

An incomplete record stays findable in the financial workspace with its original. The count distinguishes records captured from amounts available for calculation. For example: **52 records imported · 1 amount unreadable**. Unknown amounts never become zero. Reprocessing preserves investigator edits and shows conflicts against changed readings.

Discarding a non-statement removes it from Financial, with a clear restore route. Its Evidence original is retained. A suspicious document can remain evidence even when it contains no transactions.

## Transactions: the main working surface

### Default screen

Put transactions in the first visible screen. Above them, show the account/date scope in one compact row, a search field and **Filters**. Category, amount, currency, direction and source-file constraints belong in that filter control. Applied constraints remain visible as removable chips. Change the table, counts, totals and exports together.

Show one compact money-in/out comparison for the current scope. Avoid a second set of totals for the same population. If a selection exists, its totals belong to the selection controls and are explicitly labelled. An unreadable amount gets a small count beside the affected calculation.

Default data: Date, From, To, description, category and incoming/outgoing amount. Balance appears when supplied or when the investigator requests it. On a narrow screen or with the original open, From and To can share a clearly labelled column; every value remains accessible. Preserve the source statement's own columns in statement review.

Normal rows are quiet. Use teal for incoming money, muted rose for outgoing, amber for an unresolved reading and Loupe red for the primary action or active selection. Keep text labels alongside colours. Financial significance is not established by colour.

### Actions appear at the right moment

| User action | Result |
| --- | --- |
| Click a transaction | Open that record with the original alongside it, at the relevant page/line. |
| Click its category | Edit the category in place; show that it has saved. |
| Select several records | Reveal a single bar: selected count, Categorise, Compare, Create finding, and More for export/exclusion. |
| Click From or To | Open that name's profile and payments, with a return to the originating transaction. |
| Click an issue | Open its field, explanation and source; offer correction, next issue and leave for later. |
| Correct a reading | Save the correction, rerun applicable checks and update affected views; retain original and history. |

The row panel provides **Related payments**, **Add note** and **Create finding**. Less frequent actions such as exclusion and change history sit under More. Avoid an action button for every field in every row.

Selection must be trustworthy at scale. A page checkbox selects that page; **Select all matching** states the full count. Selection persists across pages. If a filter hides selected records, show the hidden count and an explicit way to review or clear them. Bulk actions show the affected set before saving. No action quietly reduces a selection to loaded rows.

### Working with the original

Keep the PDF and extracted record close. The source panel opens at the selected line; next/previous transaction and next/previous page remain distinct. From a multi-period file, choosing another period changes the statement context and its records together.

Editing should reveal a small form beside the relevant value. Store corrections immediately after an explicit save; show saved/error state without dismissing the form on failure. A source correction can require a concise reason as part of the edit itself. Viewing, categorising and importing unchanged records do not require reasons.

The original-document image is never repainted to look as though it contained an investigator's amendment. A corrected value can show **Corrected** with the printed reading and history available on request.

## Each surrounding page has one purpose

### Overview: orient the investigator

Answer what evidence exists and where to begin. Show accounts and statement coverage, recent imports and saved questions needing follow-up. Make each item open its records. Unresolved extraction checks have their own count; they are not findings or evidence of suspicious activity. The page should not require configuring a dashboard.

### Statements & accounts: manage the supplied evidence

Show the files in the main page, with account/period children and coverage. The existing optional file rail is useful while switching originals; it need not occupy every investigation page. Each imported period opens its transactions or original. Distinguish unsupplied periods from periods known to contain no payments.

### People & businesses: understand the recorded parties

Show a searchable name list with amounts paid/received, payment count, accounts and first/last date. Selecting a name opens its payments in the same working layout. Keep statement wording, investigator labels and linked case identities distinguishable in details.

Unknown names remain actionable: show their underlying descriptions and source, and allow selected records to be labelled together. The system should not present an inferred bank or payment processor as a verified beneficiary. Alias linking affects only the records the user selects or the explicit rule they create.

### Follow money: examine a connection

Start with an account or selected payment. Show incoming and outgoing records chronologically, with dates, amounts and supporting sources. A connection can open its payments. A related-payment suggestion states why it appears, such as amount and time interval, and remains a suggestion until examined.

Use a small focused graph when it helps, with text large enough to read and editable labels accessible from the selected node. Keep formal tracing methods and their assumptions under a deliberate tracing action. A large case-wide graph is an optional exploration view.

### Trends: see change and open its evidence

The default is chronological incoming/outgoing bars on a shared scale, with a clearly visible date range. Offer **Over time** and **By category** as two views of the same scoped records. Clicking a month or category opens its payments, preserving a return to the chart.

Show bank payments separately from card credits/charges. Currency selection is part of the shared scope; never sum currencies without an explicit conversion method. Missing coverage is marked on the chart. Undated records are separately accessible rather than silently omitted from all analysis.

A category is a useful description of a payment. An investigative concern is a question, note or finding. Categorising a hotel payment as Travel should not imply it is legitimate or suspicious.

### Findings: retain the reasoning and next action

The common entry is **Create finding** from selected evidence. Require only a title and the investigator's note. Attach the selected payments and sources automatically, visibly listing them. Optional fields include question/observation/conclusion, next action, owner and due date.

Findings lists that saved work and its follow-up status. It also allows a new question without payments attached. Opening a finding returns to its narrative and evidence. Reports are assembled from selected findings, with narrative and cited transactions previewed together.

Later corrections show a changed-evidence indicator on an existing finding. They do not silently rewrite a previously exported report. A saved finding is shared case work; personal table filters and scroll position are personal working state.

## Preventing lost context

Maintain a compact return path when moving from transaction to person, comparison or finding. Restoring it restores filters, selection, pagination and scroll position. Browser back follows the same path. A source panel cannot reset the list.

Related-payment exploration may need records outside the current filter. First show the stated interval and accounts; provide **Search beyond these filters** as an explicit action. A category chart click can narrow the scope with a visible chip. Avoid silently widening a person's investigation when they open a different page.

Case edits and notes save to the server. Leaving the tab preserves an unfinished finding draft; failed saves remain visible and editable. Shared updates use conflict handling that preserves the user's work and explains which record changed.

The default empty states should contain a useful action: Add statements, clear a particular filter, retry the failed file or create a question. A loading or failed query must not display an authoritative zero total.

## What becomes less prominent

- The imported-records versus other-records selector becomes a visible scope choice under Filters, with a badge when both are included. Existing routes and origin distinctions are preserved.
- Technical processing history, proof codes and internal identifiers remain in history/details.
- Long explanations of calculations become short contextual labels with expandable details.
- Generic refresh buttons disappear where the page can update automatically. Show refresh/retry when recovery is actually needed.
- Repeated account identifiers leave each row when one account is already selected; account identity remains visible in scope and details.
- The bulk-action bar appears when there is a selection. Blank detail panels and permanently expanded correction forms disappear from ordinary reading.

These changes must not conceal issues, scope restrictions, unsaved work or incomplete results.

## The design sample

The accompanying clickable sample uses twelve synthetic Nexus payments. Start with a processed file containing an unreadable amount, import without resolving it, open a transaction, inspect its illustrative source, compare related payments, change a category, save a finding, and inspect Trends or a name's payments. It preserves state while changing its views during the sample session.

The statement excerpt is explicitly illustrative. It is not the original PDF. Data and saved findings in this sample are local to the sample and do not touch a case. It does not demonstrate server persistence, large-case performance, real uploads or production extraction accuracy. Those belong to application acceptance.

## Acceptance before calling the experience good

### Build order

1. **Make imported records and outstanding issues independent.** Persist both, retain incomplete records and source links, and expose honest totals. Fix the outstanding batch-import failure independently. Exit condition: import a mixed batch, leave, return, and find both the usable records and unresolved issues without duplication or lost edits. Enabling a disabled button alone does not meet this condition.
2. **Complete one transaction-to-finding journey.** Consolidate the table controls, keep source/correction work in the adjacent panel, retain selections and return context, and attach selected evidence to a saved finding. Exit condition: complete the March Nexus task without re-entering context; reopen the finding in another authorised session. Preserve the existing PDF renderer and extraction rather than replace them for appearance.
3. **Connect the surrounding views to that same journey.** People, Follow money and Trends open their exact supporting records. Categories and scope agree across tables, totals and exports. Exit condition: selecting a chart period, name or category produces the same count and amount in its records; returning restores the originating view.
4. **Finish the demanding cases and release evidence.** Exercise multi-period/multi-account documents, card transactions, currencies, missing fields, larger selections, concurrent edits and failed saves. Update the guide against the implemented experience, capture light-mode screens and verify the deployed build. Team observation remains a separate acceptance step.

Keep changes reviewable by delivering this sequence in complete working paths. Avoid another pass of unrelated labels, controls and cosmetic changes across all tabs before the first path works.

### Acceptance tasks

Build and check the complete Nexus investigation above first, then repeat it with a multi-period card document and multiple bank accounts. Introduce a missing amount, a missing date, a failed file and a duplicate candidate; none should force the investigator to abandon the working context or lose the usable records.

Measure real tasks, rather than the number of features present:

1. The user can identify the next action on each screen without being taught internal processing stages.
2. A flagged statement imports, its issues survive refresh, and incomplete records remain findable with honest totals.
3. Opening a transaction, source or related record requires no re-entered filters or copied identifiers.
4. A selected comparison becomes a finding with its sources attached in one action before writing the note.
5. Charts, names and categories always lead to the exact supporting payments.
6. Correcting a record updates its displays and retains the original; the user can see whether it saved.
7. Large result sets and selections remain complete and clearly counted. Navigation does not silently clear work.
8. A second authorised investigator can reopen the saved finding and sources; read-only users can inspect them without edit controls.

Use focused automated regressions for these state transitions and a browser walkthrough of the entire journey. Product acceptance still requires observing the team perform the tasks. Keep guide updates and deployment verification separate from a claim that this design is implemented.
