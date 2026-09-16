# Financial investigation workspace

Approved design, 16 September 2026; application implementation completed locally on 17 September. The user approved the interactive design and asked to build it. This document records the intended investigator workflow and acceptance tasks. Existing financial data, statement review, corrections, specialist analysis and saved reports are retained. Local product verification is recorded below. User acceptance and deployment of this redesign are separate and have not been claimed.

## The investigator's job

An investigator should be able to answer:

1. Which records and accounts do we have, and what is missing or unchecked?
2. Who paid into each account and where did payments go?
3. Which payments are related in time, amount or description, and what remains uncertain?
4. What does the original evidence actually say?
5. What question, observation or conclusion should we record, and which records support it?
6. What should another investigator do next, and what can we report with evidence?

The working sequence is select, inspect, compare, record, share. A payment, person, period or comparison must lead through this sequence without re-entering filters or finding the source again.

## Application structure

Keep the Loupe case shell and an always-visible Financial guide. Give each page one main purpose. The default financial landing page becomes Overview. Returning to a case restores the last page, applied filters, selected payments and open evidence. The original statement panel opens on demand; it does not permanently consume a third of every screen.

| Page | Question answered | Main content | Main action |
| --- | --- | --- | --- |
| Overview | What do these records tell me to examine first? | Accounts, imported money movements, record completeness and specific comparisons with linked payments | Open a comparison or continue checking records |
| Statements & accounts | What evidence is in the case? | The actual file register, processing/import state, account, printed period, payment count, unresolved issues | Upload files, review a file or open its account payments |
| Transactions | What happened, and which payments matter? | Compact, searchable payment table with selection and source access | Inspect, compare or create a finding from selected payments |
| People & businesses | Who appears in the payments, and how are they connected? | Searchable directory and profiles with payment history, accounts, names, totals and unknown details | Open their payments, resolve identity or record an enquiry |
| Follow money | Which movements might be connected? | Chronological comparisons, account connections and access to existing transfer, pattern and tracing tools | Compare the actual entries and record the basis of any connection |
| Trends | How did activity change over time? | Continuous time axis, incoming/outgoing amounts, frequency and recorded balances, with gaps distinguished | Select a period or change and inspect its payments |
| Findings | What have we established, and what needs more work? | Investigator-written questions, observations and conclusions with linked evidence and next actions | Create/revise a finding or build a report from selected findings |

This consolidates navigation, not capabilities. Existing transfers, pattern searches, payment graph, case-event comparison and conditional tracing stay accessible under Follow money and relevant payment/account actions. Processing history and import decisions belong with Statements & accounts. Corrections and exclusion history stay accessible from the affected payment and from the case history.

## Overview

The first screen is an evidence-backed starting point. Show the selected accounts, period and currency once. Totals refer only to included records within that scope. Keep currencies separate and distinguish credit-card charges/credits from bank cash flow. Never describe the sum of payments as an account balance.

For the supplied Nexus example:

- One imported account, twelve payments, EUR 1,035,000 received and EUR 1,000,000 paid out.
- Opening statement balance EUR 12,450. Last printed transaction balance EUR 47,450 on 28 December 2023. Do not relabel that as an explicit closing balance when the document does not print one.
- Six receipts naming GlobalTech Industries are each followed by a payment naming Cayman National Bank, two to five days later. The six outgoing amounts total EUR 1,000,000. Present this as a comparison to examine, with all twelve source-linked entries available.
- The statement descriptions do not identify the ultimate recipient account or establish ownership. The comparison is not proof that those receipts funded those payments.
- The screenshots show three uploaded PDFs, with one imported and two ready for review. These are three files, not necessarily three distinct statements. Two share a filename; a filename alone must not establish duplication.

No invented risk score, fraud conclusion or general claim of complete coverage. A suggested comparison must say what was compared and provide its supporting entries. Hide empty decorative cards. A new case starts with the statement upload/register, not an empty analysis dashboard.

## Statements & accounts

Show every uploaded financial file in the main page. Filename, status, account(s), printed period(s), imported payment count, and unresolved issues are visible without opening a side panel. Search and status filters act on this register. Keep the side file switcher available while reviewing a document.

Statuses distinguish uploading, waiting to read, reading, needs attention, ready to confirm, partly imported, imported and failed. A ready file is not an imported statement. A multi-account PDF has child sections and per-section status; the parent must not appear completely imported after importing one section. Wire reports and receipts remain supporting records with their own review actions.

The original PDF and extracted table open side by side. Retain the printed column order and blank cells. Highlight specific problems. Allow direct correction of an extracted field with the original value and a reason retained. Page forward/back, jump to page, file switching and restoration after navigation are required. Confirm once with a clear count and destination account. An already imported section opens for inspection and correction without offering another duplicate import.

The account view groups the original files and periods under that account. Show what was requested, what was supplied, overlap/possible duplication, unresolved dates and balances. A period with no supplied records is not a period with no activity.

## Transactions

Place the payments near the top. Show account/date scope once, one search row, a compact summary and the table. More filters is a disclosure, not several permanent rows of forms. Active filters are visible and removable. Search and totals must use the same population; exports identify that scope.

Default columns: selection, date, description/name, money in, money out and printed balance. Keep the account column when comparing multiple accounts. Avoid repeating the same long account and bank description on every row. Show flags and attached-note indicators unobtrusively. Allow date, amount and name sorting. Larger results need complete access and stable selection across pages.

Selecting a row opens a detail panel beside the table with the exact values, account, source file/page and any previous corrections. Opening the PDF does not replace the payment list or clear its selection. Keep Original, Details/history and Notes within this context. On narrower screens, use an overlay with a clear return to the same row and scroll position.

Selecting several rows reveals one action bar: Compare payments, Create finding, Mark for follow-up, Export selected. Show the count and selected amounts. Prevent silently saving hidden selections from another filter; list or explicitly include them in the review.

Compare presents selected payments in date order, with time between entries, amounts and source links. From one payment, Show nearby payments offers the chosen account and explicit date interval. It must not declare a match based only on similar dates or amounts. Keep correction/exclusion controls in payment details rather than in every table row.

## People & businesses

A profile directory replaces a second copy of the generic totals chart. For each name show money received from it, money paid to it, number of payments, first/last payment dates and accounts involved. Search the names and sort by total amount, payment count or recency. Keep unknown/blank names visible as a separate group.

A profile contains:

- The name printed in the records and any investigator-confirmed identity/aliases, clearly distinguished.
- Payment history, amounts, first/last dates, linked accounts and supporting statements.
- A chronological activity view and the actual underlying transactions.
- Connections to other case entities only when supported by a saved link or source, with that basis visible.
- Known account identifiers, references and addresses only where supplied. Unknown details are explicitly unknown.
- Existing findings and open enquiries concerning that person/business.
- Actions to open/filter payments, compare selected entries, link an identity and create an enquiry with evidence already attached.

In the example, Cayman National Bank is a name in the payment descriptions. Do not identify the bank as the ultimate beneficiary, infer a destination country solely from the name, or claim an independently verified counterparty identity.

## Follow money

Use a directed connection view for the accounts and payment names, paired with chronological entries. Selecting a connection opens the payments behind it. Distinguish two recorded sides of a transfer from a suggested relationship between different amounts.

The Nexus example shows six chronological comparisons. Each shows receipt date/amount, outgoing date/amount, elapsed days, amount difference and both source references. These are proposed comparisons, not confirmed transfers. The original twelve payments remain separate.

Provide access here to the existing transfer comparison, pattern searches, payment graph, conditional tracing and case-event comparison. Explain each tool in terms of the question it answers. Tracing requires explicit opening amounts, order and assumptions. Preserve its method and inputs with any saved calculation. Do not imply the three unfinished larger-case analysis capacities have been solved by redesigning this screen.

## Trends

Use a real chronological horizontal axis. Monthly money-in and money-out bars share one scale and remain aligned to every calendar month in the chosen period. A period with no imported payments is labelled as such; missing coverage is a separate state and must not be silently plotted as known zero activity. A selected period opens its payment list and can become a finding.

Support changing granularity, inspecting counts as well as amounts, and viewing recorded balances for one account. A balance chart uses actual recorded balances and identifies gaps; it does not synthesize a balance by summing unrelated accounts. Card amounts owed use their own convention. Long ranges use an explicit overview and zoom/paging, with the displayed interval identified.

State changes in concrete terms and cite the dates: December receipts EUR 275,000 versus November EUR 150,000 in the example. Do not use unexplained scores or label a rise as suspicious. The user can inspect the two months' payments, compare them, and save the explanation or follow-up question.

## Findings and reports

Findings is the case's financial reasoning record. A system comparison is not automatically a finding. An investigator creates a Question, Observation or Conclusion, writes the explanation and attaches the relevant evidence. A question can record the information needed, next action, owner and progress. A conclusion can record contrary evidence and unresolved limitations.

Creating a finding from payments, a person, a period or a calculation carries that context into the editor. The investigator sees the attached records before saving. Preserve the original source, referenced payment versions, author and revisions. A correction made later must be visible when the finding is reopened, without silently rewriting an earlier saved report.

The empty page explains that nothing has been recorded yet and offers Create finding and Choose payments to investigate. Once populated, show title, type, concise explanation, linked payment count, source files, owner and follow-up state. Search and filter questions/observations/conclusions. Opening a finding returns to the evidence and associated calculations.

The report builder collects selected findings, ordered by the investigator. Preview the narrative, payment schedules, source citations and originals before saving/export. It must identify repeated payment references so their amounts are not inadvertently double-counted across findings. Authorised colleagues can reopen the saved report and source records.

## Shared behaviour

- A single case/account/date/currency scope stays visible. Changing scope updates the relevant counts, chart and table together. Reported selection counts include any retained off-screen entries.
- Tabs and source views retain filters, drafts, selection and position. Shared saved work is visibly distinguished from a local draft.
- No financial action silently edits the original PDF. Corrections, exclusions, identity links and conclusions retain reasons and history.
- Empty, filtered-empty, loading, failed, partly loaded and inaccessible states are distinct. A failed query cannot look like zero activity or no uploaded files.
- Read-only members can inspect evidence and saved work. Editing controls respect actual permissions.
- Unknown values stay unknown. No dashboard should imply missing records have been independently checked.
- Explanations answer what a user can do next. Internal identifiers, proof codes and processing details remain under the appropriate history/detail view.

## Implementation and local verification, 17 September 2026

- [x] Build the seven main pages in the existing application: Overview, Statements & accounts, Transactions, People & businesses, Follow money, Trends and Findings.
- [x] Show uploaded files in the main register, retain original statement review, and reopen the last page. Checked next/previous navigation, register return, tab return and refresh on an existing 167-page, 5,000-payment synthetic statement.
- [x] Add a compact payment table, contextual original, complete selection comparison, nearby-payment lookup and ordinary-currency CSV download. Checked a 2,700-payment comparison without truncation and a source overlay at a 390-pixel viewport.
- [x] Connect the Nexus Overview to its six chronological comparisons, twelve underlying payments and original source. The name profile shows six Cayman National Bank payments without asserting recipient ownership.
- [x] Build chronological amount, count and recorded-balance views. Checked the Nexus January-to-December axis and its two December payments; pure checks cover exact large amounts, currency/account separation, unknown dates and empty calendar intervals.
- [x] Create and edit an evidence-linked question with next action, recorded owner and progress. Reopened its saved report and verified links and follow-up markers in the payment table. This used the existing synthetic checking/savings case, with two source-linked payments.
- [x] Keep transfer comparison, pattern searches, graph, tracing, case-event comparisons and history available through Follow money and More financial tools.
- [x] Update the in-application guide and testing pack with the actual screens and synthetic-only screenshots.
- [ ] Obtain the user's acceptance of the implemented application, including the specific live-case examples below.
- [ ] Verify this redesign after deployment and with a separate authorised colleague account. No push has occurred for this work.

These checks do not measure extraction accuracy on new statement layouts. The separate larger-analysis capacities for Transfers, case-event comparison and Patterns are still recorded as unfinished; this UI work does not mark them complete. No new PDFs were uploaded or imported for this implementation's browser checks. Existing synthetic fixtures were reused.

## Acceptance against the user's screenshots

Implementation is accepted only after these tasks succeed in the actual product. A prototype demonstration and unit checks do not tick these boxes.

- [ ] From Statements & accounts, identify all three uploaded files, the one imported file and its twelve payments without opening the side panel.
- [ ] Open that imported file, compare its original columns, change pages and return to the file register without losing the current review.
- [ ] From Overview, understand the six incoming/outgoing comparisons and open the twelve relevant payments. No inference is presented as a confirmed transfer.
- [ ] Find March's EUR 125,000 receipt, compare it with the EUR 120,000 payment two days later, open both source readings and record a question with both attached.
- [ ] Inspect the Cayman National Bank name profile, its six payments and sources, and identify that the ultimate beneficiary is not provided.
- [ ] See an actual January-to-December time axis. Select December and reach its two payments. Understand the distinction between no imported activity and missing statement coverage.
- [ ] Reopen the saved question in Findings, add a next action, and create a report with its payment schedule and original source.
- [ ] A colleague can reopen the saved finding/report and source files. Permissions, corrections and source history remain intact.
- [ ] Repeat with multiple accounts/currencies, a multi-period PDF and a large case; no silently incomplete profile or chart is accepted.
- [ ] Complete the journey without instructions about internal ingestion stages, proof classes or batch identifiers.

## Delivery order

1. Build one complete investigator journey first: visible file register, focused transaction table, contextual source/compare and evidence-backed finding. Verify it with the Nexus example and a second account.
2. Add the person/business profile, chronological Trends and case Overview using the same source/payment actions.
3. Integrate the existing transfer, pattern, graph, tracing and case-event tools into Follow money, retaining every supported analysis and its assumptions.
4. Verify saved work, reporting, permissions, recovery and larger datasets. Resolve the separately recorded capacity gaps rather than disguising them with smaller display limits.
5. Update user documentation/screenshots only after the actual investigator journey is accepted. Preserve previous guides as needed until the deployed screens change.

The interactive design uses the twelve synthetic Nexus payments shown in the conversation. It illustrates selection, comparison, source references, profiles, periods and a locally saved example finding. It does not read or change the live case. Its recreated statement excerpt is explicitly marked and is not the original PDF.
