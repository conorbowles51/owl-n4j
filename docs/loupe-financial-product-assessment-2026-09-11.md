# Financial investigation product assessment

Date: 11 September 2026

This document records the assessment before redesign. Implementation and acceptance results are tracked in [the redesign plan](loupe-financial-redesign-plan.md).

## Conclusion

The financial section has substantial reading, calculation and evidence-recording functionality, but it does not yet provide a coherent investigation workflow. It asks users to understand internal data categories and processing rules before they can work. Several useful actions are hidden, and some unfinished work is lost during normal navigation. Passing component tests did not establish usability.

This assessment supersedes any implication in earlier development checklists that implemented components alone make the financial section ready for an investigator. It does not declare the underlying calculations incorrect or the whole system nonfunctional. It identifies where the application fails to turn those capabilities into understandable, connected tasks.

## Evidence and limits

- Opened all 13 Financial tabs in the local running application at a 1440 by 1000 viewport, using the existing synthetic Nexus case with 12 current transactions. Captured each tab and its visible controls.
- Clicked the actual load actions for Transfers, Patterns, Posting graph and Case context. These returned results without browser exceptions.
- Opened the transaction note and correction actions. Tested unsaved note retention and pattern-setting retention without submitting changes.
- Inspected the route composition, data hooks and components for the remaining actions and saving paths.
- Blocked API writes after login. This assessment did not rerun import, correction submission, note submission, transfer scenario creation, report generation or multi-account tracing. Prior acceptance records cover some of these, but they are not fresh verification of this assessment.
- This is the local checkout, not a verification of the deployed server. It includes provisional, unpushed layout and copy changes made before the user requested assessment first. In particular, transaction actions are now under the description locally, and some counterparty copy has changed. These do not resolve the wider findings. After the assessment, those four provisional source files were restored to their prior state only after their exact edited contents were backed up and checked. The screenshot evidence therefore shows a provisional local layout, not a released fix. The earlier statement-file recovery changes are still local.
- Temporary browser evidence: `/tmp/loupe-financial-audit.json`, `/tmp/loupe-financial-actions-audit.json`, and `/tmp/loupe-audit-*.png`. These contain synthetic case data. No real customer statement was changed.

## Findings by area

### 1. Navigation and starting a case

**Investigator's task:** Add statements, see the accounts and payments, choose a question to investigate.

**Observed:** Thirteen peer tabs mix everyday investigation with processing administration. At the tested width the later tabs extend beyond the visible navigation strip. Transactions, Counterparties and Trends each offer “Ledger postings” and “Financial intelligence”.

**Code finding:** These switches change between separate relational transaction data and graph records. Graph categorisation and amount edits do not update imported transaction rows. This is a meaningful data distinction presented as an unexplained mode choice.

**Required:** A clear starting page, primary navigation for everyday tasks, and a separate place for import/history administration. Explain what a secondary dataset contains at the point it is opened. Do not present disconnected datasets as interchangeable views of the same corrected payments.

**Acceptance:** A new user can identify how to add a statement and open its transactions without knowing what a ledger, proof class or graph record is. The user can tell which records an action will change.

### 2. Uploading and opening original statements

**Investigator's task:** Upload several PDFs, see progress, and switch between originals without losing work.

**Existing implementation:** Visible single-file upload, bulk selection of up to 20 PDFs, per-file queue, Statements sidebar and file search. Local follow-up adds Read statement and Retry reading for existing files.

**Gaps:** “Ready to review” does not distinguish an imported statement from one still waiting for confirmation. Upload progress is not a durable server-side queue visible across browser restarts. Preparation failures need a clear next action. The Statements tab itself is mostly checks rather than a file workspace, while the file workspace lives in the right panel.

**Required:** One consistent statement list with file name, account, period, reading state, import state and clear actions. Show whether a file is waiting, failed, ready to check or already imported. Keep the original accessible in each state.

**Acceptance:** Upload multiple files, recover one failed read without creating a duplicate, restart the browser, and identify which files still need attention.

### 3. Checking and confirming extracted statements

**Investigator's task:** Compare the PDF with its extracted values, correct mistakes, then confirm the import once.

**Existing implementation:** Original PDF alongside printed columns, blank cells and source text; page controls; separate import corrections; counts and balance comparison; one confirmation action. Recent dedicated acceptance covered synthetic bulk upload and a real multipage statement.

**Gaps:** Printed source values and editable import values are separate views whose relationship needs to be immediately visible. A saved browser-tab draft is not the same as a saved case review. Page and file navigation must not obscure the active statement period. No fresh import acceptance was performed in this assessment.

**Required:** Show corrections beside the affected source values, clearly distinguish original and corrected values, explain where work is saved, and show the exact transaction count and destination before confirmation.

**Acceptance:** Correct a date, description, credit, debit and balance; switch pages/files/tabs; reopen; confirm; verify the imported values and unchanged original.

### 4. Transactions

**Investigator's task:** Find relevant payments, open one, compare its source, record an observation and collect relevant payments for further work.

**Observed:** Filtering exists. The deployed screenshot cuts off row actions at the right. Technical columns and repeated date badges consume space. Locally, moving existing actions below the description makes them visible, but the page still spends most of the first screen on filters and explanation before reaching transactions.

**Code finding:** Existing imported-row actions open source, add a Workspace note, correct the transaction or set it aside. The imported transaction table has no row selection for assembling a named set of transactions. Bulk actions in the graph-data branch do not supply that missing imported-row workflow.

**Required:** A compact transaction table with a clear open action and a useful transaction detail view. Provide deliberate selection and a way to save a named set of relevant payments, with source references, for notes and reporting. Preserve the difference between correcting a value and making an investigative observation.

**Acceptance:** Find a payment, inspect the PDF, save an observation, select related payments, save the selection, leave and return to it.

### 5. Filters, totals and dates

**Investigator's task:** Narrow the case and understand what the displayed totals represent.

**Observed/code:** Account/date filters apply to the fetched transaction scope. Search, currency, amount and other table filters operate on those rows. Top totals do not follow all table filters. The screen explains this in dense paragraphs. Amount ordering has a currency restriction. Dates are presented through internal “ordering date” terminology.

**Required:** Make the active scope visible in plain language, put filtered totals beside the filtered table, and label any wider case totals separately. Explain a restriction beside the relevant field. Preserve mixed-currency separation. Explain a fallback date only on rows where it matters.

**Acceptance:** Search for one recipient and verify that the amount shown as the selection total matches only those payments. Clear filters and recover the previous scope. Check date boundaries and mixed currencies.

### 6. Notes and findings

**Investigator's task:** Record why a transaction matters and find the note again.

**Observed:** Add note opens a source dialog and note form. The form explains that saved notes go to Workspace.

**Confirmed defect:** Entered an unsaved note, closed the dialog, reopened it, and found an empty field. No warning was shown.

**Code finding:** Notes save with transaction and evidence references, but the transaction note component does not retrieve prior notes or display a note count on the transaction row.

**Required:** Preserve drafts or warn before discarding. Show existing notes in transaction details and provide a visible path to the case's financial findings. Let the user distinguish an observation, a question and a supported conclusion without requiring internal terminology.

**Acceptance:** Save and reopen a note from the transaction and Workspace, follow its source, and verify safe handling of an unsaved draft.

### 7. Corrections and review decisions

**Investigator's task:** Fix a wrong value, explain the change and inspect its history.

**Observed/code:** Correction controls exist and open. Their placement was poor. Earlier correction history appears in Decisions. Setting a row aside is a distinct action. Replacement records preserve the earlier reading.

**Gaps:** Source inspection, correction and review status are scattered. A description-only correction is labelled “Ledger amount corrected” in the displayed history, which misdescribes the change. The current design exposes P3 and Admitted as prominent user concepts.

**Required:** A transaction detail view with clear correction controls and a before/after history stating the actual changed fields. Put processing classification under technical details. Explain the practical effect of setting a transaction aside before submission.

**Acceptance:** Correct a description without changing the amount; verify the history describes a description change. Correct an amount; verify current totals and earlier values. Review set-aside and restore behaviour.

### 8. Accounts, balances and missing periods

**Investigator's task:** See account holders and numbers, which periods are present, and any discrepancies that need attention.

**Observed:** Account cards open their transactions. Statements provides balance and period checks. Some returned messages discuss proof classes, missing controls and why substituting zero would manufacture a delta. These messages are unsuitable as primary user guidance.

**Required:** A statement list organised by account and period. Show “Closing balance not printed”, “Balance agrees” or “Difference to check”, with source and correction actions. Show the missing period plainly and distinguish an absent printed balance from an arithmetic mismatch.

**Acceptance:** Open an account, inspect its supplied periods, identify a gap, compare opening/running/closing balances without inventing a missing value.

### 9. Counterparties

**Investigator's task:** Find who paid in, who received money, and all payments involving a person or business.

**Observed:** Totals by recorded name and currency exist, with chart selection and source links. The original screen repeated qualifications above the results. Provisional local copy is clearer but still opens numbered source buttons rather than a recognisable transaction list.

**Code finding:** Linking names to a reviewed identity is a separate directory workflow. The name on a transaction is not automatically a confirmed person or business.

**Required:** A readable list showing name, payments in/out, count and date range; one action opens the matching transaction table. Name-linking should start from that context and retain its reason/history.

**Acceptance:** Open GlobalTech Industries, see the six incoming payments and their total, inspect a statement, record a finding and return without losing scope. Verify identity grouping separately using ambiguous names.

### 10. Transfers

**Investigator's task:** Follow money between accounts and inspect both sides of a possible transfer.

**Observed:** Find possible transfers returns results. The one-account fixture correctly offered no cross-account pairs, but then presented extensive identifier rules and a separate account-group calculation.

**Code finding:** Pair selection, explanation and calculated scenarios exist. This is separate from the original transaction totals. Selection and scenario state are held in local component state. No fresh multi-account matching or save/reopen test was performed.

**Required:** Side-by-side outgoing/incoming payments, clear account names, dates and amounts, source actions and a reason to accept or reject a proposed relationship. Save the investigator's review and make it discoverable later. Explain when another account's statement is needed.

**Acceptance:** Use a two-account fixture with one clear pair, one ambiguous pair and one unmatched payment. Review each and reopen the saved result. Do not imply that equal amounts alone prove a transfer.

### 11. Patterns and payment claims

**Investigator's task:** Find repeated payments or rapid movements, inspect the relevant transactions and record what needs investigation.

**Observed:** Screening runs, but setup and returned explanations expose “population”, “captured ledger”, internal rules and long caveats. The Nexus fixture produced no results under the default equal-amount rules, despite visually obvious recurring payment relationships with changing amounts. That result is limited to the implemented rules, not evidence that the case has nothing to investigate.

**Confirmed defect:** Changed Screening window days to 11, switched to Transactions and back, and it reset to 3.

**Code finding:** Pattern results can save a proposed theory to Workspace with sources. A payment-claim comparison is a secondary mode. Neither should be assumed to cover all investigation patterns.

**Required:** Describe the actual questions each check answers before running it, preserve settings/results and offer useful next actions when no result is found. Show supporting payments in a table. Assess recurring relationships with variable amounts as a separate missing capability, not a wording fix. Explain where saved findings can be reopened.

**Acceptance:** Fixtures with known repeated amounts, changing recurring amounts, quick in/out movements and ordinary explanations. Verify which checks find each, what remains outside scope, and saved-result navigation.

### 12. Trends

**Investigator's task:** See changes in activity over time and open payments behind an unusual period.

**Observed:** Monthly/daily aggregation and source links work on the synthetic case. Technical explanations dominate. Counterparty and trend views share a chart component; the provisional counterparty instruction about ticking names also appeared on date groups, demonstrating why broad string replacement is inadequate.

**Required:** Time-specific instructions, readable amounts and axes, obvious drill-down into the period's transaction table, and clear handling of gaps and currencies. A blank period must not be represented as confirmed zero activity without evidence.

**Acceptance:** Select a month, inspect the matching payments and totals, change granularity, and return to the same selection.

### 13. Payment graph

**Investigator's task:** Understand money relationships visually and follow a payment to its evidence.

**Observed:** The graph loads. Its node selector lists the account and recorded names, and transaction arrows/source actions exist. The UI exposes “posting”, “source label” and short identifiers.

**Required:** Account and name labels, useful summaries on selection, plain-language explanation of arrows and a table of related payments. Make clear when a name is only text in a statement. Do not imply this is a confirmed multi-account money trail.

**Acceptance:** Select account, recipient and arrow; verify displayed payment details and source, readability at normal window size, and return navigation.

### 14. Tracing and indirect calculations

**Investigator's task:** Examine how identified funds may have moved, using explicitly chosen assumptions, and save the calculation with its evidence.

**Observed:** Single-account tracing opens with a disabled load button, unfamiliar filtering and a default Verified only setting. Ordinary reviewed PDF imports in the fixture are P3, so they require a different selection. The screen does not guide the user through that consequence.

**Code finding:** Single-account, network and indirect methods are distinct workflows with inputs, source references and result downloads. Indirect work can save a Workspace workpaper. This assessment has not validated each calculation or each method's full form in a browser.

**Required:** Treat these as advanced tools with step-by-step account, period, funds and method selection. Explain inputs with concrete examples and expose assumptions in the result. Preserve unfinished work. Keep normal transaction exploration available without requiring these methods.

**Acceptance:** Separate complete fixtures for each offered method, same-day order, incomplete coverage and mixed sources; save, reopen and inspect inputs and output. Calculation correctness needs its existing specialist tests as well as a usable workflow.

### 15. Case context

**Investigator's task:** Compare payment dates with case events and record a possible connection.

**Observed:** The timeline loads the 12 payments in date order. Source links work as entry points. Event records are a separate query. Display is primarily a long list with technical payment labels.

**Required:** A clear date-based comparison, visible filters for event/payment types, and a direct way to record a connection with both sources. Nearby dates should invite investigation, not create an automatic conclusion.

**Acceptance:** Fixture containing case events before and after a payment. Find both, record the observation and reopen it with the evidence links.

### 16. Import history, held-out records, attempts and decisions

**Investigator's task:** See which file failed, what needs attention, what was excluded and who changed something.

**Observed:** Import history duplicates the transaction list alongside classification and duplicate controls. Held out is an empty technical explanation. Attempts is a run-count table. Decisions exposes UUIDs and internal duplicate reasons. These are four separate navigation destinations without a clear shared task.

**Required:** An import/review history organised by file, with status, time, transaction count and the relevant action. Put technical records under expandable details. Link each change to the named file or transaction. Explain an empty state and offer the next relevant action.

**Acceptance:** Failed import, successful import, duplicate, correction and excluded row can each be traced from a named file to the reason and available recovery action.

### 17. Reports and sharing

**Investigator's task:** Select relevant payments, add the finding, include supporting statements and produce something a colleague can read.

**Observed/code:** Table-view downloads and wider exports exist, with optional PDF and original files. Wider reporting is buried under “Reports, balance coverage and verification details” and mixed with archive comparison, verification and assembly controls. Export scope can include a wider account/date snapshot than the table selection.

**Required:** A visible report action with a preview of selected transactions, totals, narrative and included originals. Explain exactly what will be included before download. Keep technical evidence packaging available separately. Verify how financial findings integrate with the platform Reports area instead of assuming existing ZIP downloads complete that task.

**Acceptance:** Save a finding about selected payments, create a readable report, verify every total and source link, and confirm that unrelated payments/files are not silently presented as part of the finding. Explicitly test any wider supporting material included in the package.

### 18. Guide, language and accessibility

**Investigator's task:** Get concise help while doing the current task.

**Observed:** The guide is always available, but a long manual cannot correct unclear navigation and disconnected actions. Dense explanatory paragraphs precede useful content. Technical terms are used in ordinary labels and empty states. Repeated groups of generic numbered source buttons do not describe the transactions they open.

**Required:** Rewrite help after each workflow is settled. Use task-specific directions, explain necessary specialist concepts once, and move detailed calculation limitations under clearly named details. Check keyboard access, visible focus, readable widths, narrow-window layout and meaningful button names. Preserve substantive limitations without putting raw backend prose in the main workflow.

**Acceptance:** A person unfamiliar with the system completes the core task script below without a developer explaining where controls are or what internal words mean.

## Fix order and completion evidence

1. [x] Finalise the investigation workflow and navigation around user tasks, including the relationship between imported payments and other case data.
2. [x] Make transaction details, notes, correction history and source access visible and connected. Protect unsaved work.
3. [x] Add saved selections of relevant imported transactions and a direct path from them to findings and reports.
4. [x] Make accounts, statement status and missing coverage understandable in one statement workspace.
5. [x] Connect people/businesses, trends, graph and transfer results to the same transaction-detail workflow.
6. [x] Make pattern checks explicit about the questions they answer; retain settings and results.
7. [x] Review each advanced tracing and indirect method as a separate complete workflow.
8. [x] Consolidate import failures, exclusions and change history; keep technical records accessible beneath user-facing explanations.
9. [x] Complete reports with an understandable inclusion preview and source verification.
10. [x] Rewrite task help, validate keyboard/layout behaviour, then run the investigator acceptance script.

No item above is marked done merely because existing code was found. Provisional copy/layout edits were backed up and removed from the working implementation. Their focused test run had stale-label failures; it is not evidence of passing redesign checks. That was the position at assessment time. The checked fix-order items now refer to the implementation evidence in the redesign plan, with remaining limitations retained there.

## Core investigator acceptance script

1. Start a case and upload several statements from at least two accounts, including a multipage PDF and one file requiring correction.
2. See which files need attention. Compare and correct values against the original. Confirm each import once.
3. Open an account and its payments. Find a recipient and inspect the source for a chosen payment.
4. Save an observation and a named selection of related payments. Switch tabs, close/reopen the view, and retrieve the work.
5. Inspect a possible transfer using both statements. Record the review without losing the original transactions.
6. Run an explained pattern check, inspect its supporting payments and record a reasoned finding.
7. Compare a payment with a case event and save the connection with both references.
8. Produce a report containing the chosen finding, payments and supporting evidence. Check amounts and scope against the screen.
9. Have another authorised user find the saved work and understand what was changed, what remains uncertain and what to investigate next.

This script defined the technical acceptance work. The redesign plan now records the checks performed, distinguishes fresh journeys from retained fixtures, and keeps real-file and human usability limits visible.


## Additional findings from the user's complex-statement screenshots

### Statement review must be a separate workspace

The user confirms that upload and field correction are becoming useful for simple statements, but the transition after confirmation mixes imported payments with the area used to review/edit the file. This is a workflow defect, not merely an unclear button.

Required boundary:

1. Statements is the place to upload, compare the original, fix extraction errors and confirm an import.
2. Confirmation shows the result and opens the imported payments in the investigation workspace, scoped to that statement.
3. Investigation provides source access and deliberate corrections without reopening the whole intake process.
4. Returning to Statements shows the file as imported, with its original and review history available.

### Complex page reconstruction is misleading

The screenshots show a Capital One page with separate payment, purchase, fee and interest sections and an advertisement beside the transaction area. The reconstructed table mixes these areas, creates unrelated extra columns and puts some totals under the wrong column. A physical PDF page number and a printed statement page number also differ without explanation.

Code evidence:

- `PrintedStatementTable.tsx` renders all supplied rows and their column indices as a rectangular table. It does not select transaction sections or reconstruct the original page's separate regions.
- `text_rows.py` explicitly recovers page text without deciding whether it represents transactions, summaries or advertisements.
- `pdf_tables.py` uses that recovery when drawn table extraction does not resolve cells.
- `statement_import_card.py` separately marks recognised transaction candidates and excludes information rows. Displayed text rows are therefore not the same thing as imported transactions.

A read-only check of a different existing local real-file proposal returned 67 displayed rows, of which 63 were statement information, two were transactions and two were zero charges. This confirms the display/classification distinction. It does not verify the exact Capital One statement in the user's screenshots, which was not located and checked in this assessment.

Required: show the original page faithfully; reconstruct each recognised transaction section with its own headings and column positions; distinguish metadata and summary sections; keep unclassified raw text under diagnostic inspection. Do not claim that printed layout is retained when the display is a generic grid. Check the transaction candidates separately against the original, including signs, credit-card sections, repeated dates, totals, different cardholders and account references.

Priority: this is a core import-quality issue. Do not fix it by merely hiding nontransaction rows and declaring the remaining extraction accurate. A missing or misclassified transaction could be hidden by that approach.

Acceptance: use the actual page shown by the user, identify each printed transaction and section by visual inspection, compare the proposed import row by row, then verify section layout and source highlights. Repeat on the other supplied real PDFs. Preserve original files and previously recorded imports while correcting future extraction/display behaviour.
