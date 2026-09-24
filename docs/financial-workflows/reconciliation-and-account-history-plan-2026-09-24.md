# Prepare, reconcile and investigate account history

Status: R01–R06 implemented and locally verified; code-only release preparation. Production verification is recorded separately below.
24 September 2026. The user asked for a connected plan after collecting all of
Alex's feedback, then confirmed that work can proceed. This document supersedes
the earlier policy that reading/arithmetic issues may remain unresolved when
statement transactions are imported. Older completion records are historical.

## Objective and complete investigator journey

Alex opens a batch, supplies missing currency and period details without opening
every statement, resolves the remaining discrepancies beside the source, and
imports only reconciled statements. A statement with confirmed no activity is
saved to Financial as account/period/balance evidence with no artificial payment.
From that account or from Trends, she compares balances and activity over time,
then opens the exact statement or payments explaining a change and returns to
the same account/date selection.

All of this applies across cases, banks and supported statement readers. Source
format selects a reader, never whether a document belongs in Financial. Evidence,
source history, corrections, annotations, duplicate decisions and citations are
preserved. No new feature may make Alex repeat an earlier review or abandon an
unfinished manually entered payment.

## Feedback coverage

| ID | User report | Acceptance outcome |
|---|---|---|
| R01 | Add start/end dates beside batch currency; month/year shortcut | Individual and selected statement periods can receive explicit dates or correct whole-month dates without opening each review. |
| R02 | Unreconciled statements should not enter Transactions | One server-enforced reconciliation decision controls every statement import entry point and its visible readiness. |
| R03 | Apply USD clicked repeatedly with no result | One click produces visible pending state and a persisted result, or an actionable error retaining the selection; repeat changes and uncertain responses recover safely. |
| R04 | Cannot copy from the left PDF or open it separately | Review source offers selectable text where present and a direct, authenticated original-file tab at the current page. Scanned pages provide explicitly labelled available OCR text. |
| R05 | What happens to statements without transactions? | Confirmed inactive periods remain searchable and visible in Financial, preserving balances and dates, without creating payments. Failed extraction is not called zero activity. |
| R06 | Compare quiet months and bursts across one/several accounts | Account balance/activity history includes inactive periods, distinguishes missing evidence, separates currencies and bank/card products, and supports source/payment drill-down and return. |

## 1. Prepare details from the batch

- Keep common preparation controls above the statement list. Rename the existing
  currency-only area to explain both currency and statement dates; reuse the
  account-detail preview/save machinery instead of introducing conflicting writers.
- On each relevant batch item expose currency, **Statement start date** and
  **Statement end date**. These are period dates, not opening/closing balances or
  transaction dates. Unknown dates remain blank.
- For a selected set, choose the fields to change. The month/year shortcut fills
  day 1 through the actual final day, including February/leap years; custom dates
  remain available for cards, partial periods and non-monthly statements. Do not
  assume every statement is a calendar month or infer dates silently from names.
- Show affected account, file, period and before/after values. Fill missing values
  by default; replacing known values is explicit. Selecting January and February
  together must not silently give both January's dates. Mixed-account PDFs are
  edited by statement period, not by the whole PDF.
- Apply once, show Saving, then saved/unchanged/conflicting counts beside the
  action. Refresh counts, dates, currency, duplicate checks and reconciliation in
  place. Reopening a batch or review must show the saved values. Preserve other
  selected rows, corrections, filters and current position.
- Reproduce Apply USD through request, revision checks, currency rebasing, saved
  review, server response and client refresh. Current code has two currency paths
  and a separate bulk-detail writer; consolidate their visible behaviour and use
  the existing atomic/receipt protections. A stale selection must explain which
  statement changed and offer refresh/review without silently dropping typed data.
- Relabelling printed currency is not FX conversion. Do not multiply amounts or
  move a statement into the wrong currency subaccount. Already saved periods use
  the existing correction route with the exact scope shown.

## 2. Correct while keeping the source in view

- Place **Open original in new tab** and the text-selection/copy control in the
  left source toolbar, visible before long row lists. Reuse the authenticated
  file-opening utility; do not navigate Alex to Evidence or expose an auth token.
- Open the retained original at the selected page, leaving the current correction
  form, batch position and filters untouched. Handle popup blocking, expired
  authentication, loading and failed retrieval with retryable feedback in place.
- Native PDF text should be selectable in a document view; an image of a page
  does not support copying. For scans, offer the available extracted/OCR page text
  alongside the image, clearly labelled as a reading that must be checked.
  Unsupported or unreadable text must not be invented.
- Copy/paste into a newly added transaction must not submit it, collapse the
  editor or filter it away after the debit/credit field changes. Preserve the
  active manual row until Alex explicitly saves or cancels. Existing source-page
  and original-versus-corrected provenance must remain intact.

## 3. Reconcile before adding transactions

- Introduce one shared assessment for the reviewed statement. Return its state,
  revision, exact checks, blocking reasons and source/field destinations. The UI
  displays **Needs reconciliation**, **Ready to import**, or the saved state;
  it must not independently guess importability from row counts.
- For an ordinary bank statement, the opening balance plus money in minus money
  out must equal the printed closing balance in exact currency units. Credit-card
  statements use the existing amount-owed convention and their printed charges,
  payments, fees and interest. Different account/currency sections are independent.
- Require a usable opening/closing comparison and resolution of contradictory
  printed totals, counts, running balances and financial row values. Additional
  controls that are genuinely not printed are not invented or described as failed
  checks. Missing essential controls mean **Cannot reconcile yet**, with a direct
  action to enter their source-supported values or inspect the source.
- Matching closing balances alone do not prove every transaction was captured:
  omitted offsetting payments, incomplete records, unassigned payment sections and
  conflicting totals must remain explicit blockers. Narrative notices that have
  no bearing on accounting completeness do not become arbitrary import blockers.
- An acknowledgement or typed exception must not override an actual unresolved
  arithmetic difference under the new rule. Correction, evidence-backed exclusion
  of non-payment text, or supplying a missing printed value can resolve it; a
  checkbox alone cannot. Save progress is always available for unfinished work.
- Enforce the same assessment before writes in individual confirm, batch confirm,
  durable workers, replacement and automatic recovery of statement payments.
  Recheck under the existing lock against current saved edits. Old clients cannot
  bypass it. Duplicate-source holds remain separate additional safeguards.
- A batch imports its reconciled subset once and leaves unresolved statements
  in a clearly counted review group. Selecting that group opens the first actual
  blocker; next/previous and return preserve the group and progress.
- Edits affecting amounts, balances, directions, currency, period, included rows
  or source reading invalidate the previous assessment. Existing imported records
  are not silently deleted or withdrawn from analysis by this policy change.
  Mark older/unverified statement status honestly and direct further repairs
  through the retained correction/replacement workflow.

## 4. Save and recognise an inactive statement

- Separate **confirmed no activity** from **no payments were extracted**. Equal
  balances alone cannot distinguish a quiet month from missed offsetting payments.
  Require clear source evidence or an explicit recorded investigator review of
  the complete period, plus consistent balances/printed controls where applicable.
- Show a specific **Save statement with no activity** action. Save the account,
  currency, start/end dates, printed balances, source pages and review history.
  The result says that the statement was saved and zero transactions were added.
- A PDF containing several periods can have inactive and active periods together;
  each receives its own status. Empty extraction, missing pages, unreadable
  balances or a real balance change without explaining movements stay in review.
- Keep the record visible in Statement files, the batch, Review accounts and
  account history, and keep its Evidence search/source entry. Counts distinguish
  saved statement periods from saved transactions. An account with no payments
  must still appear in account selectors.
- Retain balance observations even when no-activity status cannot yet be proved,
  clearly marked unverified; never manufacture a zero-value transaction merely to
  make the account appear. Missing and zero balances remain distinct.

## 5. Investigate balances and activity over time

- Extend the existing **Trends** and account-review journeys, using their shared
  account/bank/holder/date filters. Add a visible **Balances & activity** view and
  a direct account-review entry to it. No second disconnected account selector.
- Include accounts with saved periods and no transactions. Give selected accounts
  stable distinct colours and explicit names. Amounts of different currencies or
  bank versus card liabilities must not be summed or plotted as equivalent values.
- Show two aligned views: closing-balance observations and movement activity
  (money in/out or card charges/payments). Balance is a stock and activity is a
  flow; one ambiguous bar series cannot communicate both. Offer a readable table
  of the same observations as an accessible alternative.
- Keep months with confirmed zero activity visible. A month without source
  coverage is a labelled gap, not a zero, and a flat line is not interpolated
  through missing evidence. Preserve irregular statement dates and partial-month
  coverage; do not pro-rate or invent daily balances from a month-end observation.
- Clicking a balance opens the source statement and its controls. Clicking
  activity opens the scoped payments. A no-activity period opens its statement,
  not an unexplained empty Transactions table. Returning restores comparison
  accounts, dates, chart choice and position.
- Respect current import/supersession/exclusion and duplicate decisions. Internal
  reading versions do not create extra balance points or movements. Overlapping
  independent statements and unverified periods are visibly unresolved rather
  than silently added to one amount. Do not assert a suspicious pattern merely
  because a user can see recurring activity.
- The acceptance example is an account with quiet periods, a later deposit/ending
  balance, several verified quiet periods at that balance, and later activity,
  compared with another account. Add a deliberately missing period to demonstrate
  that the display does not present absent evidence as inactivity.

## Implementation order and architecture

1. Reproduce and repair currency save/repeat behaviour; build the batch-date and
   month/year workflow on the same persistent statement-details writers.
2. Expose the original/text workflow so the next reconciliation step is usable.
3. Introduce the shared reconciliation assessment and server admission checks;
   replace obsolete UI promises that reading issues never block import.
4. Complete inactive-period evidence, save receipt and account discoverability.
5. Feed saved periods, reconciled activity and coverage into the shared history
   query and Trends/account views. Implement drill-down and return.
6. Audit legacy states read-only, verify all connected journeys, and release the
   complete connected scope. A passed unit test or a rendered chart is not closure.

Existing integration points: `BatchCurrencyEditor`, `BulkStatementDetails`,
`StatementImportPanel`, `StatementCoverageReview`, `TransactionSourceHighlight`,
the protected file utilities, `InvestigatorTrends` and shared investigation scope;
`import_batches`, `statement_import`, `review_arithmetic`, `bulk_statement_details`,
`statement_details`, source lineage, coverage queries and recovery services.

The existing application already supports bulk exact dates, a general viewer's
new-tab action and saved balance-only periods. These are foundations to connect
and verify, not evidence that Alex's reported workflow currently works. The Apply
USD incident's precise cause remains unconfirmed. The isolated tests reproduce a lost response after a successful save and verify safe retry; this does not establish which condition caused Alex’s live incident.

## Acceptance and release checklist

| Journey | Required evidence | Status |
|---|---|---|
| R01 dates | Several statements; calendar February/leap February; custom period; mixed-account PDF; preview; replace/fill; save/reopen/second edit; transaction dates unchanged | Implemented; local evidence below |
| R03 currency | One and many selections; USD save; second correction; stale revision; conflict; timeout-after-save; refresh/reopen and authoritative stored result | Implemented; local evidence below |
| R04 source | Current-page original in separate tab; copy native/OCR text; paste manual row; debit/credit editing does not remove it; save/reopen; auth/popup failures; narrow viewport | Implemented; local evidence below |
| R02 admission | Balanced bank/card imports once; missing controls, real discrepancy, missing/invalid payment and stale assessment cannot write; acknowledged difference cannot bypass; server direct call and batch agree | Implemented; local evidence below |
| R02 recovery | Existing imported data and receipts retained; queued/recovery paths apply the same rule without terminating ingestion or overwriting corrections | Implemented; local evidence below |
| R05 inactive | Explicit no activity vs missed extraction; zero/nonzero unchanged balance; active/inactive sections; saved receipt, account discovery, Evidence and Financial reopening | Implemented; local evidence below |
| R06 history | Two accounts with quiet/activity/missing periods; no-transaction account; currency/card separation; repeat readings/overlap; exact source drill-down and scoped return | Implemented; local evidence below |
| Connected release | Real-service Chromium at realistic wide/narrow viewports; representative existing and fresh data; suitable regressions/build/lint; safe deployment gate and deployed revision/workflow evidence | Local checks passed; publication and live verification tracked below |

Use synthetic committed fixtures; keep client files, screenshots, extracted data
and credentials outside Git. Preserve unrelated workspace changes. Push is the
authorized automatic deployment trigger; no separate manual deployment or service
restart. Active ingestions must be protected by the existing deployment gate.
The existing live-origin authorization restriction is separate from code release;
record local, pushed/deployed and live-verified states separately. Do not claim
that existing live case data was cleaned or that a production journey was verified
without observing it.

## Implementation and local acceptance — 24 September 2026

- R01 uses the existing statement-detail preview/save service for individual or selected period dates. Month/year fills actual calendar boundaries; custom edits, replace/fill-missing choices and statement-specific scope remain available. Dates do not rewrite transaction dates. Calendar/leap tests, six bulk-detail component tests and real-service February 2024 save/reopen pass.
- R03 records currency request receipts on the server and reuses the same request after an uncertain response. Selection/revision refresh is explicit; results/errors are visible and focused. Backend unknown-currency/read-again tests, component stale/second-edit tests and a browser response-loss-after-commit → retry → reopen pass. The original live Apply USD cause is not asserted.
- R02 uses a shared server admission assessment for individual/batch/replacement imports, recovered additions, and repaired/manual payments from already saved statements. A typed exception cannot bypass a discrepancy. Legacy repairs and manual entries are saved as pending records and admitted together only when the final current statement reconciles. Updating currency/balances assesses the final saved state, not the pre-edit balances. Existing payments and original request/reading snapshots remain intact.
- R04 adds protected original-file opening at the selected page, the browser’s native PDF view and clearly labelled selectable extracted page text beside the working form. Authentication/popup failures keep the draft. Chromium confirms source retrieval, page addressing, text selection and an unchanged unfinished input. Native PDF rendering and text selection depend on the browser’s PDF viewer; the copy-text and original-tab alternatives remain visible. A separate visible-Chromium source run verified the actual new tab navigates to the protected PDF at page 1 and preserves the unfinished input. The copy-text screenshot is evidence for selectable page text, not a certification of native PDF rendering in every browser.
- R05 distinguishes saving unverified balance observations from confirming a no-activity period. Neither creates artificial payments. Confirming quiet activity requires full-period review (or explicit printed zero counts), matching controls and complete details. Reopening a previously saved balance-only statement allows that confirmation from its account/balance editor. Changing values invalidates verification. Backend and browser tests cover save → reopen → confirm → account history with zero payments.
- R06 extends Trends and account review with balances/activity, shared account/date selections and exact source tables. Currencies and card liabilities have separate charts. Missing evidence and unverified periods are not zero activity; overlapping periods are not double counted. Synthetic browser comparison covers four account/currency/product series, filtering/reopening, quiet months, missing months, and payment drill-down/return. Unit checks cover activity bursts, multi-month periods, unprinted dates, overlaps and large exact amounts. The 420-pixel view was checked for horizontal overflow.

Verification: 324 backend tests plus 23 subtests pass across admission, imports, batches, details, bulk corrections, deployment recovery and manual payments; 86 focused frontend unit tests pass; six Chromium journeys against the real disposable backend pass; TypeScript/production build, scoped ESLint and diff checks pass. Some historical persistence fixtures explicitly seed pre-policy imports so preservation and recovery remain tested; current admission tests never bypass the policy. Existing test-library/deprecation and build chunk-size warnings remain.

No client file, screenshot, extracted financial data or credential is part of this release. Browser artifacts and service logs are in the temporary directory. No production data was changed in acceptance. The existing deployment script still gates service transitions on queued/active AI and financial jobs and defers when it cannot verify that state; it was inspected, not executed against a live database.

Release checks are complete locally. The authorized code-only push triggers automatic deployment; the publication receipt is recorded in the task. Live deployed-revision and workflow verification remain unperformed because the earlier live-origin access denial has not been resolved. The earlier production cleanup audit remains separate and unverified; this release does not claim to have performed it. No manual deployment or ingestion cancellation was attempted.
