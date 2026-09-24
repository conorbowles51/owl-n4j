# Alex's financial workflow acceptance

**24 September connected release:** [source selection, compact saved work and one-time recovery](financial-workflows/next-release-2026-09-24.md). Implementation is complete locally with workflow verification. The content/provenance cleanup remains a separate scheduled production pass; publication and live results are recorded separately.

**24 September correction:** Ordinary Evidence PDFs were incorrectly listed as statement files. The [scope correction and connected acceptance](financial-workflows/evidence-file-scope-2026-09-24.md) separates explicit financial work from general Evidence while retaining saved reviews, imports and sources in any format. The follow-up supports explicit CSV, spreadsheet, Word, image and other source selection; non-PDF files do not enter the PDF reader. Legacy XLS/DOC still need conversion for processing. Live verification remains separate.

**23 September feedback implementation:** The [complete implementation plan](financial-workflows/feedback-implementation-plan-2026-09-23.md) covers F01–F28 and J01–J12. That implementation was pushed as `60b6706a`; [the acceptance record](financial-workflows/implementation-progress-2026-09-23.md) records local tests and remaining live limits. The earlier results below are historical and do not override newly reported failures.

20 September 2026. Earlier component tests and public deployment checks did not establish that Alex's 588-file workflow worked. This pass covers the reported failures together, including existing saved work.

| Concern | Implemented outcome | Evidence and remaining acceptance |
| --- | --- | --- |
| Empty rows and irrelevant issues | Unrecognised summary/account text stays outside payments. Saved reviews with unchanged sources retain corrections while untouched empty entries are excluded. | Parser, saved-review and batch regression tests pass. Full 588-file extraction remains unverified. |
| Balance-only statements | Save the account, period and printed balances with zero transactions. Visible labelled opening/closing controls distinguish zero from unknown. | Synthetic balance-only import/reopen and Chromium interaction pass. January and February ARRENDO EUR were opened in Alex’s live test case and saved with matching 1,817.77 opening/closing balances and no payments. |
| Missing balances after import | Edit account and balances beside the PDF; update statement checks in the same save. | Supplied TITANIUM PDF and synthetic missing/zero/stale-save cases pass. |
| Account holder and number edits | Persist before and after import, including leading zeros, reopening, batch review and history. | Combined source/import/detail tests pass, including saved older drafts. |
| Currency choices across cases | All backend-supported currencies in batch, statement and post-import selectors, preserving printed values without FX conversion. | Supplied PDF roundtrip EUR → MXN → USD → EUR preserves amounts/categories and updates Transactions, totals and checks. GBP/CHF/JPY/KWD/CLF roundtrips also cover exact 0/2/3/4-decimal scales, saved balances, history and atomic precision refusal. Unknown-currency records become usable together when no other field is missing. |
| Repeated reasons and flags | Routine corrections and completing missing fields have optional notes. Mark checked records an automatic review decision for a correct flagged row. Actual unresolved fields stay visible. | Frontend import decision plus backend persistence, arithmetic and optional-note tests pass. |
| Imported but invisible | Separate usable payments, balances and incomplete records in receipts. Current batch counts follow corrections and replacement readings. | Supplied PDF imports two payments and opens the same saved values through transaction queries; synthetic pagination tests already cover large results. |
| Previously imported BBVA empty records | Eligible imports offer Save [number] payments to Transactions, using the existing PDF; original reading is retained. Saved payment corrections are protected, and account/balance edits are carried forward. | Supplied PDF replay: simulated 223 incomplete/0 payments becomes 0 incomplete/2 payments. Repeated request adds nothing. Batch count follows replacement. The live ARRENDO February USD import was recovered from 245 incomplete readings to 17 visible payments; January USD now has 15 payments. Two EUR balance-only imports were also recovered. MXN follow-up is detailed below. |
| Confusing save and issue navigation | Explicit saving/importing actions; missing details and balances lead to their controls; failed saves retain drafts. | Existing browser tests and refreshed component tests pass. |
| Unrelated account checks during review | Case-wide checks only appear under Review accounts → Account checks. | FinancialPage regression verifies their absence in Statement files/review. |
| Indistinguishable batch runs | Date, starter, short batch identifier, reading progress and sample filenames distinguish runs; older batches remain accessible. | Two runs with 588 files open their own saved batch in the UI test. |
| Multiple periods in one PDF | Recognise the Capital One World Elite to Quicksilver heading change and matching continued transaction pages. Existing batches can check for additional periods using saved extraction, keeping reviews and imports. | The supplied 201-page file detects and imports all 51 printed periods: 653 transactions and charges, one USD account, no incomplete records, all 51 balances matching. Saved corrections, reopening and retry without duplicates pass in an isolated database. |
| Transactions should start with everything, then filter by holder/account | Main Transactions navigation opens every imported payment in the case without selecting an account first. Visible Person or company and Bank account selectors narrow immediately; Show all imported payments clears an earlier statement/batch/account/date/category scope. | Multi-bank fixtures verify automatic loading, 50-row pagination, matching totals, holder/account export filters and clearing old scope. Holder grouping uses recorded names, ignoring case and whitespace; it does not infer aliases. Browser refresh preserves chosen filters. Chromium walkthrough and navigation regressions pass. |

## Verification

- 187 backend tests passed across statement details, BBVA, batches, router permissions, optional review, arithmetic, saved-review upgrade and corrections. Shared imported fixture tests are included in that count.
- 117 component tests passed across seven affected areas; the additional Mark checked interaction test passed separately.
- Two Chromium browser tests passed for adding statement balances and editing saved details beside the source. Synthetic PDF placeholders test interaction/layout, not extraction. Both current screenshots were inspected.
- Two private local journeys used the supplied TITANIUM PDF's extracted text and table geometry in an isolated database: the complete import/edit/currency/totals flow and recovery of a simulated legacy empty import. Opening 60.00, charges 34.80 and closing 25.20 agree; original readings and retry behavior are checked. The private source and receipts are excluded from Git.
- TypeScript/production build, scoped lint and publication checks are recorded with the release checkpoint after completion.
- Additional real-file test: `000846-001046 Statements.pdf` initially reproduced only five detected periods. After the layout fixes, all 51 periods (30 November 2020 through 20 February 2025) import and reopen. The old five-period batch refresh preserves a saved correction, adds the remaining 46, and repeated confirmation/refresh adds no duplicates. All 653 entries appear through the batch transaction scope; paginated statement checks cover all 51 periods. Fresh production table extraction was used; selected pages were visually compared. Private source, geometry and audit remain outside Git. The complete isolated import journey took 224 seconds; this is not a production performance estimate.
- This follow-up passes 129 focused backend tests, 10 batch-panel component tests, TypeScript/production build, scoped lint and diff checks. The imported batch link also follows a verified replacement reading, covered by the BBVA regression, so its transaction view agrees with the refreshed count.
- The later Transactions-default follow-up passes 20 backend tests, 109 component/API/navigation tests and one Chromium walkthrough with a visually inspected screenshot. Tests cover all-account case reads, grouping the same recorded holder across two banks, one-account filtering, separate currency totals, pagination, export parity, date/filter retention, fresh navigation and browser refresh. Production build, TypeScript, scoped lint and diff checks pass. These fixtures exercise the workflow; they do not add evidence about extraction of the unavailable 588-file corpus.

## Still required for full acceptance

Alex is testing in **Neil finance**. Do not use the client case for acceptance writes. Only the explicitly authorized Neil finance test case was modified. The client case was not used.

The actual six-file ARRENDO batch is accessible in the authorized live test case. Four statements have been repaired and reopened live. The two MXN files are read locally with matching counts, totals and balances; their save/reopen and the refreshed six-file batch still require the follow-up deployment. The full 588-file client corpus has not been replayed. Do not mark that full batch accepted from six files.

## Actual February USD ARRENDO follow-up

Authenticated observation in Neil finance reproduced the missing import action: the new reading has 17 usable payments while its old saved import contains 245 incomplete records and zero payments. No live data was changed during diagnosis. Local production extraction and isolated recovery preserve Alex's saved account details and balances, expose all 17 payments (six incoming, eleven outgoing), reconcile USD 191,772.17 to USD 157,624.78, and repeat without duplicates. The actual live saved review has 204 unchanged rows; metadata-only revision recovery was verified against those rows. The direct batch action, saved-balance destination, full incomplete-statement links and false Spanish-layout warning are covered in the same repair. Authenticated post-deployment acceptance remains required; the full 588-file set is not certified.

## Live follow-up and MXN/currency release

After deploying 2937364, February USD saved 17 usable payments and January USD saved 15; both match printed money-in/out and closing balances. Refresh, source highlighting, saved account details and filtered/all-account navigation were checked. January and February EUR save their unchanged 1,817.77 balances and open Review accounts with an explicit no-payments confirmation.

The MXN test found right-aligned large amounts assigned to description text and BBVA Bancomer footers included as fake rows. Corrected retained-source replays give 137 January payments and 136 February payments, no row issues, and printed count/total/balance matches. The following release also refreshes old batch status from the current saved imports, so individually completed reviews no longer lead back to stale balance/draft warnings. Post-deployment MXN saves and the batch transaction destination remain the next live acceptance steps.

Currency selectors use a common catalog matching the backend (including historical codes), with no default case-specific choice in bulk. Exact rescaling preserves printed values; impossible precision is refused atomically. 187 focused backend tests, a further 14 detail/currency tests, 92 component/format tests and six Chromium workflow checks passed, with production build and scoped lint.

January MXN is now saved live: all 137 payments are visible with the exact printed totals and 50-row pagination. February MXN revealed an additional older-draft comparison dead end, now covered by 51 backend and 49 UI tests. Its comparison and Save payments action share one screen; previous draft values stay in history, stale comparisons fail, and existing payment edits remain protected. Live February save and final batch navigation follow this release.

## Investigator workflow reference and navigation — 21 September 2026

The user's acceptance standard is the complete investigator journey, including discoverable actions, visible outcomes and the way back. The maintained [financial workflow reference](financial-workflows/README.md) now maps all sections and processes, with a generated control inventory linked to source. Root `AGENTS.md` records these standing agreements and requires future financial work to consult and update this record. These files support continuity; they do not guarantee compliance or establish acceptance by themselves.

The Statements workspace now separates **Statement files**, **Review accounts**, **Processing batches** and **Remove imports…**. The 51-period PDF has a compact file card, and its review states the selected account/period, whether its payments are already imported, and where to view those payments. Returning to files closes the review visibly; unfinished upload/review state survives navigation. Removal starts with PDF selection and a scope preview, retaining original evidence and the same case. The source-to-review handoff now opens the clicked statement period instead of an unrelated previously selected period from the same PDF.

On the pre-change live release `7917f36d`, the ARRENDO **Review dates & statements** click did open a visible account dialog. The user's earlier no-visible-result report was not reproduced; its root cause must not be claimed as proven. The file-list layout did show all 51 Capital One periods above its removal action, confirming why common actions were difficult to find.

Local acceptance: 117 focused component tests, seven Chromium workflow tests, eight statement-source backend tests, production build, scoped lint and diff checks passed. The Chromium journey uses a 51-period fixture and checks saved status, return navigation, visible removal, preview and cancellation. No live records have been removed or reprocessed in this pass. Post-deployment observation is recorded in the flow reference. Broad Financial actions and Alex's full 588-file corpus are not all re-certified by this change.

Live `43f465b` in the user-created **finance sunday** case: the 51-period file is compact, saved-period context is explicit, the December–January review opens its six payments, account checks open visibly, and the first-period source returns to 30 November–23 December 2020 with five payments rather than the prior selected period. Bulk removal previews 3 PDFs / 53 periods / 672 transactions / one batch; cancelling leaves all 672 payments available. No live imports were removed or reprocessed. The walkthrough also prompted moving the primary payment action into the first-screen context panel and connecting timeline sources to the same period-specific review handoff. Those follow-ups pass six Chromium and 57 account/timeline/navigation tests; see the maintained reference for live verification status.

Final live `c350c0c` verification also passed: account timeline → second period → source → review opens 24 December 2020–23 January 2021 with the six-payment action beside its saved status in the first screenful. That action opens six matching transactions. Workspace navigation and dedicated removal selection remain visible on return. No removal confirmation or reprocessing was performed. Full-corpus and unrelated conditional journeys remain subject to the acceptance limits above.

## 21–22 September: investigator working-session fixes

The latest reports are one workflow: remove bad imports safely, choose several people/accounts, investigate beside the transaction table, correct a selection, and return without losing work. Scope includes every item below; completion requires the checks, not just the controls.

- Removal: named confirmation route must reach the removal writer; short errors, bounded scrolling and reachable recovery actions for one and many PDFs. Actual confirmation is tested in an isolated database; live client records must not be deleted for a demonstration.
- Shared account filters: multiple Person or company selections and multiple Bank account selections, with any-match within each group and intersection between groups; preserve them across Financial and carry them through totals and exports.
- Working toolbar: search, Category and Filters beside Charts, From & To and Money flow; keep it visible near the transaction table.
- Search: ordinary text filtering and Boolean AND/OR/NOT, phrases, parentheses and field searches; invalid syntax is explained and export uses the same selection.
- Single and bulk transaction editing: choose specific fields, preview the affected rows, save atomically; From, To, Category, amounts, dates, descriptions, references and balance. Preserve source readings and correction history. Update totals, filters and selected replacement rows.
- Tab continuity: navigation retains state; Reset view explicitly clears presentation state without deleting saved casework or unfinished editors.
- Amount ordering: allow mixed currencies and order by the displayed numeric amount, accounting for each currency’s decimal places; no currency conversion.

Implementation and acceptance evidence will be recorded here after the combined browser journey and deployment checks.


Additional accepted scope: Findings & Observations terminology and direct actions; Follow money must distinguish recorded directions from an assumed funding relationship, offer FIFO/LIFO and one-to-many timing comparisons, and allow explicit cross-currency transfer hypotheses with original amounts and the implied rate visible. The detailed workflow and methodological limits are recorded in [the reference](financial-workflows/README.md#working-session-acceptance--22-september-2026). This is not automatic confirmation that two FX legs belong together. Both original currencies and all calculation inputs remain inspectable.

Implemented and locally verified: removal routing/scroll/recovery; shared holder/account selection through ledger/totals/exports; toolbar text/Boolean search and category filters; reviewed single/bulk edits; retained tabs with explicit reset; amount-size sorting across currencies; Finding/Observation creation and editing; explained flow methods and selected FX legs with onward allocation. Deployment and live checks are recorded after revision verification. No live client rows have been edited, removed or reprocessed by these tests.

## Transactions, Findings and Observations on Timeline — 22 September 2026

Accepted: select one or several Transactions and add them to Loupe’s case Timeline; Findings and Observations must also offer the action. This is an addition to the financial investigator journey, not an export file or a separate financial-only chart.

Implemented locally: direct Add to Timeline actions, a source/date preview, explicit event-date choice for Findings and Observations, duplicate prevention, saved receipt and Open Timeline, automatic visibility of the new event, original-source inspection and return to retained Financial state. Undated payments remain in Transactions; statement-end placeholders are not event dates. Payment corrections resolve through the same Timeline identity, removed sources keep labelled snapshots, and saved Timeline views/exports resolve these additions. See the [workflow reference](financial-workflows/README.md#add-financial-evidence-to-loupe-timeline--22-september-2026) for the full path and acceptance limits.

The user authorized deployment of all outstanding ready work on 22 September. Releases `e0bce92c` and `73e9cf45` are deployed: the live version endpoint and Admin Updates both identify `73e9cf4`; the deployment log completed database migrations and backend health reports the current schema, connected Postgres/Neo4j and a healthy evidence engine. In monday finance, live previews covered two selected payments → Timeline and an existing Finding → Timeline, with source/date/count verification and cancellation. Bulk edit opened with the full field set. Boolean search returned 55 of 960 payments; switching to Findings and back retained the query and two-row selection. Existing entries showed Finding/Observation classification and Edit/Add to Timeline. Reset view cleared demonstration state. No live Timeline entry, correction, removal or reprocessing was saved during these checks. Actual saved Timeline creation remains established by isolated SQL and Chromium fixtures rather than a client-case write. The separate browser Update platform control still reports a server sudo configuration problem; the automatic deployment succeeded.


## Balance-only and operation/settlement statements — 22 September 2026

The supplied NOVAC Scotiabank January 2026 PDF has three pages, an explicitly zero activity chart and unchanged zero MXN balances. The generic reading turned summary/disclosure/glossary text into incomplete records. The targeted recognizer requires complete matching pages, one account, labelled national currency, matching printed balances and all five zero activity values; missing/conflicting/nonzero evidence falls back to review. It preserves every source row and does not infer zero from missing text. Local actual-PDF extraction gives zero payments and no issues; isolated save/reopen and legacy replacement preserve source/history and investigator account edits while removing false incomplete records from the active view. Existing row corrections block automatic replacement. The live BNB2 case was already empty with 590 removed files when inspected; those files were not restored or changed.

The supplied January 2026 BBVA MXN PDF reconciles its operation opening balance plus credits minus debits exactly to its closing balance. Page 11 explicitly explains the difference from the liquidation opening: a 31 December payroll operation settling on 2 January. The prior-period section remains in the PDF/source rows and is excluded from the current period's payment list and totals. The fiscal certificate remains an information page even when OCR misses its page number. Actual-PDF extraction/save/reopen gives 148 payments (24 credits, 124 debits), zero incomplete records and no reading issues; all totals and 21 running-balance intervals match. The review now explains its balance basis beside the controls and identifies the prior-period source page.

Validation: 104 focused backend tests, 49 review component tests, nine Chromium checks, production build and scoped lint pass. Final balance-only wording is additionally checked in Chromium. Post-deployment checks for this additional repair will be recorded in the workflow reference. Automatic approval review blocked transmission of the two supplied PDFs to live neil finance until the user explicitly authorizes that upload; no upload occurred. These two documents do not establish acceptance of Alex's full 588-file corpus or every bank layout.

Live release `2327d9bb` is verified by the version endpoint and successful deployment log, with current schema and healthy services. The new balance explanation was inspected on an existing live BBVA statement with its saved 137 payments unchanged. The supplied 2026 PDFs have not been uploaded: automatic approval review requires the pending explicit authorization for the neil finance destination. Their actual-PDF local save/reopen/reconciliation checks are complete; live ingestion acceptance remains pending that authorization.

## BNB2 ingestion and recovery feedback — 22 September 2026

The user requests a detailed, connected investigator workflow plan before further implementation. The [platform-wide plan](financial-workflows/statement-ingestion-workflow-plan.md) is the maintained reference for this scope. BNB2 is the reproduction case; the user explicitly requires the fixes for every existing and future Financial case and ingestion. All acceptance items below remain open; this planning pass changes documentation only.

Read-only live BNB2 inspection reproduces the Kapital statement's four saved USD payments, disabled main currency selector, separate editable saved-currency field and absence of saved date controls. The review also displays zero current payment readings alongside the four saved payments without an adequate comparison explanation. Code confirms the imported-detail writer has no period-date fields. The precise cause of USD detection, the historical 109-transaction attempt and the reported concurrent-processing stall still require targeted reproduction/operation evidence. The current case has 175 active PDFs and recent reviewable batches, so its present counts cannot certify the earlier 150-file attempt. No client records were changed during this investigation.

| ID | Complete journey to accept | State |
|---|---|---|
| BNB2-01 | Upload/read → understandable file/period/import/check status → same facts in batch, review, accounts and Transactions | Planned; open |
| BNB2-02 | Concurrent financial/general processing → progress → leave/return → interruption/retry without duplicate work | Local request/status race repaired; dedicated workers pass synthetic Redis/process and Chromium checks. Alex's live termination cause and full provider/load acceptance remain unconfirmed. See [ingestion reliability](ingestion-reliability-workflow.md#starting-financial-while-ai-ingestion-is-running--22-september). |
| BNB2-03 | Wrong currency → direct scoped correction beside source → save → current totals/links → reopen | Planned; disabled entry point confirmed |
| BNB2-04 | Missing holder/account/dates → edit the visible field → persistent save → coverage and checks updated | Planned; saved-date contract gap confirmed |
| BNB2-05 | Import available transactions once → durable progress/receipt → exact saved set → partial-failure recovery | Planned; original 109-transaction outcome unconfirmed |
| BNB2-06 | Flag → source and actionable explanation → correction/review decision → updated check → next item | Planned; open before and after import |
| BNB2-07 | Repeat/overlap/alternate scan → explained match → retained/excluded/additional-record decision → correct totals | Planned; exact-import retry protection exists, blanket skipping not established |
| BNB2-08 | Existing BNB2 case → reconcile current state → finish affected work without losing edits, evidence or links | Planned; combined live acceptance outstanding |
| FIN-09 | Source → general processing → Financial reading/version → repeated folder selection/retry → one current import per real statement scope | Planned; generated-copy mechanism confirmed in code; actual duplicate ledger contributions not established |
| FIN-10 | Repeat all reported journeys in unrelated new and legacy cases, across banks/currencies/entry points and concurrent users/cases | Mandatory platform-wide release gate; open |

The plan preserves previous agreements on source history, editable Transactions, shared multi-account filters, tab retention, direct actions, meaningful analysis and Timeline links. The subsequent 22 September deployment hold overrides earlier deployment authorization. No push/deployment or destructive client-case demonstration is authorized by this plan.

## Account ownership and onward payments — 22 September 2026

Update: [Monex/Kapital layout acceptance](financial-workflows/bank-layout-acceptance.md) now records local implementation and tests of separate account/currency sections, balance-only Monex imports, recovered Kapital postings, source identifiers and save/reopen/retry. This is a shared service change, not a BNB2 data patch. Existing incorrect combined-import recovery, full ownership/trail UX, ingestion interruption acceptance and live validation remain open. No push or deployment occurred.

The [connected ownership and money-trail design](financial-workflows/account-ownership-and-money-trails.md) records the latest request. Source header identifiers can support common-holder suggestions; investigator knowledge can establish a reviewed link with its own basis. Distinct bank/currency accounts stay separate. The sending debit and receiving credit are two retained statement entries of one transfer; linking that receipt to a later supplier payment is a separate attribution. Existing party links and conditional transfer tools provide a foundation, but normal-screen entry points, structured identifier extraction, shared identity filtering and persistent transfer/trail integration remain open. Mixed-currency subaccount detection is a prerequisite. This is design and code-inspection evidence, not implementation, browser or live acceptance.

Additional duplicate-creation report: statement preparation/reprocessing can create byte-identical EvidenceFile copies with parent/root metadata. Folder selection does not collapse those versions, and the Financial register does not group that lineage. This can expose generated versions as additional selectable files. It is a confirmed implementation mechanism, not proof that payments are currently counted twice. The plan requires a read-only source/job/period/ledger audit, prevention in shared services and regression of the complete repeat-processing loop. Any necessary correction to client totals must retain sources, edits and citations and use a reviewed action; no destructive cleanup was performed.

## Current implementation status — 23 September 2026

The [release verification record](financial-workflows/release-verification-2026-09-23.md) supersedes the historical Planned/open implementation labels above. It records the connected outcomes for every reported ingestion/correction/status/duplicate and ownership/trail journey, completed local checks, supported-source limits and outstanding live verification. The user's subsequent instructions authorise commit, push and deployment of verified code. The user subsequently confirmed deployment of that release. Push triggers automatic deployment; no separate Google Cloud login is required to publish code.
## 23 September: bulk account details

Alex reported that she could not find a way to bulk set or edit account details.
The earlier request explicitly covered bulk transaction edits and multiple account
filters; the earlier implementation exposed individual account edits and bulk
currency edits, but not this complete workflow. The user explicitly requested
building it now and pushing; the platform deploys automatically on push.

Added a visible **Edit account details** action beside the file-selection actions
in **Statement files**, and the same action in **Processing batches**. Select
individual statement periods or all matches across pages, tick holder/account
number/bank/currency/dates, fill missing values or explicitly replace populated
values, preview each change, save and reopen. Imported statements and saved drafts
are both included. Unread/conflicting statements explain the review required.
Unticked fields, row corrections and original evidence are retained. Saved results
distinguish updated imports from drafts awaiting import. Retry receipts, case
permissions, stale-preview checks and atomic rollback protect the complete set.

Verification: 136 existing statement/batch backend checks; 31 new bulk and route
checks; 27 frontend checks; two Chromium journeys through the actual file/batch
entry points, including saved reopening and a narrow viewport. Synthetic screenshots
were inspected locally. Production build and scoped lint passed. These tests did
not change client records. Independent live acceptance remains separate from the
automatic deployment triggered by publication.


## Complete 23 September follow-up feedback

All F01–F28 reports are mapped to implemented workflows and local evidence in the [current acceptance record](financial-workflows/implementation-progress-2026-09-23.md). This includes both late additions: retained review filters/active manual rows and direction-aware existing counterparty/account links. Real-service Chromium checks save/import/reopen through production FastAPI routes and independently read back a second bulk correction. The source PDF, account/period/currency, payment identity, history and next action remain part of each journey. Live incident verification is separately blocked by the origin-authorization review described in that record; no live client records were changed.

## 24 September: future bank and card collections

Latest file-register follow-up: [Ready-to-import workflow acceptance](financial-workflows/ready-statement-workflow-2026-09-24.md) records the repair for the apparently inactive ready counter. It now reveals and focuses ready periods with direct review/import actions; real-service browser checks confirm import, refreshed availability and return to the same filter. The prior live-origin restriction remains separate from this verified local implementation.

The additional statement types are shared processing capabilities, not case- or
file-specific repairs. The [collection acceptance record](financial-workflows/statement-collections-2026-09-24.md)
covers Credit One cards, Andrews account/share dates and currency, targeted image
rereads, mixed bank/card selection, separate imports and saved reopening. Source
uncertainties and an apparent missing printed page remain explicit review items;
they are not silently completed with guessed values. Private documents and source
checks remain outside Git. The existing production-access restriction still
prevents independent live verification.

## 24 September: explain the batch before individual review

The report that almost every statement appears problematic adds an explicit acceptance requirement: show the reasons and import consequences at batch level, then retain the selected reason through review, correction, next/previous and return. This workflow is implemented and locally verified in the [connected release record](financial-workflows/next-release-2026-09-24.md#follow-up-understand-and-work-through-batch-checks), together with the missing-reading Retry repair and the earlier source-selection, compact saved-work and background-recovery work. Counts span all pages; absent balance inputs do not become false differences; correcting a shared missing holder updates the group without importing or changing payments. Exact causes in the reported live batch and the three unresolved file failures are not established by the synthetic tests. Publication/live access remain blocked as recorded there.
