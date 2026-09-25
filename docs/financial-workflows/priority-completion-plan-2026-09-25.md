# Complete statement processing and investigation — parallel delivery plan

Date: 25 September 2026. This is the consolidated plan requested after Alex's
latest priority feedback. Three parallel, read-only code reviews informed it.
It preserves the earlier work rather than restarting or replacing that work.
The work packages below are implemented or in final integration as recorded in
the dated completion checkpoint. Publication, live verification and the source
audit remain separate acceptance steps.

## Intended outcome and scope

Alex opens a batch and can account for every file and statement period. A failed
reading has a working recovery action. A genuine duplicate is ignored once and
linked to its retained statement. A statement containing payments becomes
importable only after its current rows and printed controls reconcile and its
completeness checks pass. Import produces one durable result. Transactions,
filters, profiles, charts and exports then describe the same saved records.

This applies to every case and future statement using the shared services, not
only the reported case or particular uploaded PDFs. Financial relevance depends
on content and investigator selection. File format chooses the reader, never
whether evidence is financial. A reader limitation must remain explicit.

The principal journey is:

1. **Statements & accounts:** see which sources are reading, failed, awaiting
   correction, ready, ignored as duplicates, or already imported.
2. **Batch/file review:** recover a failed stage or inspect the exact reason for
   a discrepancy beside its source. Save unfinished work without importing it.
3. **Reconciliation:** see the current calculation, resolve problems and retain
   control of unfinished rows. Complete statements become ready automatically.
4. **Import:** confirm a named scope; receive a persisted statement/payment
   receipt; repeated clicks or interrupted responses do not import again.
5. **Transactions:** see the complete imported scope and counts, then optionally
   filter, categorize, link counterparties or inspect sources.
6. **People and Trends:** investigate confirmed ownership and represented periods,
   drill into the exact records, and return to the same working context.

## Continuity: work that must not be lost

| Existing work | Observed state at this checkpoint | Next obligation |
| --- | --- | --- |
| R01 bulk/per-statement dates and month shortcut | Implemented in `62f7db3a`; live two-statement preview produced February 2024 ending on the 29th. Preview was cancelled without applying dates. | Preserve individual/custom dates, fill-missing/replace preview, mixed-PDF period selection, second edit, save/reopen and unchanged transaction dates. |
| R02 strict reconciliation admission | Shared gate exists for single/batch/recovery/manual and saved pending additions. | Strengthen current-result consistency, exact differences and all write-boundary checks described below; do not return to permissive import. |
| R03 currency save/retry | Idempotent receipts and lost-response local journey implemented. | Original live Apply USD cause is still unproven. Trace that incident, verify repeated correction/reopen, and retain useful errors and safe retry. |
| R04 original PDF/copy/edit | Live original action created a separate protected current-page tab and kept an unfinished row. Extracted text and source pages were inspected. Automation cannot inspect the resulting blob URL. | Preserve copyable source text, working-form state, page addressing, popup/auth errors and source access. Do not claim native viewer inspection that did not occur. |
| R05 saved quiet periods | Saved balance/page edits persisted live; a legacy period still required review after explicit no-activity confirmation. | Read and resolve its actual current blockers. Do not equate saving a value with confirming inactivity. Preserve quiet periods without inventing transactions. |
| R06 account balances and activity | Implemented; live currencies, saved observations and unavailable months distinguished. | Finish source/payment return checks; replace the old continuous-month axis with Alex's new represented-month rule. |
| Follow-up saved-check explanation | Backend response and UI now expose stored admission reasons; local regressions pass. Uncommitted. | Integrate with the authoritative current assessment below so a stale historical success cannot conflict with history or batches. |
| Follow-up draft discard | Explicit discard removes an added manual draft row without resetting other corrections; authenticated save/reopen regression passes. Uncommitted. | Verify in the live test case and discard only the verification draft created during testing. Never import it. |
| Follow-up import wording | One contradictory permissive message replaced. Uncommitted. | Audit the other missing-field/arithmetic messages and make all affected screens agree with the current policy. |
| Current release | `ded066c9` successfully deployed; authenticated log showed successful frontend build, idle ingestion gates and healthy services. Its preceding release had a frontend build failure despite the checkout label. | Verify build completion and affected behavior on the next release, not just the displayed checkout hash. |
| Previous evidence-membership cleanup | Accepted content/provenance audit remains unverified. | Keep it in the completion register with actual retained/removed/uncertain/protected counts. It is separate from statement recovery and must preserve Evidence and investigator work. |
| Earlier findings cards, navigation, parser families and source selection | Existing implemented work and local acceptance are recorded in the linked references. | Regression protection, not an unrequested rewrite. Any newly exposed failure reopens its acceptance item. |

The follow-up currently passes 129 backend tests plus 11 subtests, 58 frontend
tests, forced TypeScript checking, production build and scoped lint. Those results
cover the follow-up as written, not the new work packages below. No client
document, source image, extracted record, export or credential belongs in Git.
The current index is empty; the pending implementation and documentation are
saved in the working tree. Unrelated local files must remain untouched.

## Parallel ownership and integration rules

| Owner | Independent work | Owned implementation areas | Required handoff |
| --- | --- | --- | --- |
| Agent A — processing and recovery | Diagnose retries, repair reading completeness, safely revisit affected batches | `evidence_intake`, `statement_reprocessing`, extraction/reader quality, durable jobs and `deployment_recovery`; focused tests | Stable source/reading/period IDs, reader version, stage/outcome, structured extraction problems and recovery receipts |
| Agent B — reconciliation and duplicate decisions | Current assessment, exact differences, completeness gate, automatic duplicate disposition | `statement_admission`, `review_arithmetic`, `saved_statement_admission`, overlap/duplicate services; focused tests | One versioned assessment and duplicate contract consumed by every writer and screen |
| Agent C — investigation views | Complete counts/filters, accurate ownership profiles, represented chart months | Transaction/account directories, people/profile calculations, chart helpers, matching export membership; focused tests | Exact record/account/party membership, represented periods and consistent counts after import/correction |
| Coordinator — connected workflow and release | Preserve pending fixes, integrate shared files, real-browser acceptance, source/data audit, release | Common statement/batch UI, API wiring, query invalidation, migration ordering, acceptance documents, staging and push | One working journey, consolidated results and an honest remaining-work register |

Before edits, give each shared file one writer. The coordinator owns
`StatementImportPanel.tsx`, `ImportedStatementDetails.tsx`,
`FinancialBatchPanel.tsx`, `FinancialPage.tsx`, shared API schemas and query
invalidation. Agent A owns retry branches in `import_batches.py`; Agent B supplies
the assessment/disposition interface and the coordinator reviews integration.
Agent B owns backend saved-detail assessment changes after incorporating the
existing local patch; Agent C owns `account_history.py` and consumes that result.
`ledger_table_view.py` and profile membership changes belong to Agent C with
coordinator review. Migrations are ordered centrally.

Agents must not operate the same live browser, run overlapping live recovery
campaigns, stage unrelated work, push independently or redefine shared financial
calculations. They may work concurrently on independent source files, synthetic
tests and read-only investigations. A blocked lane reports the exact dependency;
other lanes continue. New feedback is appended to this register and routed to an
owner rather than replacing an active task.

## Shared contracts to settle first

These are extensions to existing services, not a replacement ingestion system.

- **Identity:** case, original evidence, retained reading, statement period,
  canonical account, confirmed party and currency/product compartment are
  explicit IDs. A filename or display label is never an account identity.
- **Processing:** attempt ID, reader/version, actual stage, last progress,
  accepted/already-running/paused/failed/completed outcome, problem and next
  allowed action. Reading completion is separate from financial readiness.
- **Assessment:** current source/edit/ledger revision, policy version, exact
  arithmetic in integer minor units, calculation availability, completeness,
  blockers, optional checks and precise correction targets.
- **Duplicate:** pending/retained/ignored/conflicting disposition at statement
  level, retained-statement link, matched fields, evidence basis and reversible
  decision history. Its human label is **Duplicate - Ignored by system**.
- **Import:** one durable operation/result per request, admitted/pending/ignored
  counts and exact source/account/payment IDs. All consumers invalidate from the
  same completed operation.
- **Investigation scope:** whole-case inventory, current account/date scope and
  matching table-filter scope remain distinct. Totals use all matching records;
  pagination affects presentation only. Currencies and liabilities remain
  separate.

## Workstream A — get failed and partial statements through processing

### A1. Establish the causes using existing work

Create a private read-only inventory of the reported failed/partial items and a
successful control from the same bank/layout. Record current and original reading
lineage, attempt/stage, source availability, parser version, extracted sections,
saved review revision, existing imported count and current reconciliation state.
Do not claim a historical fix explains Alex's current incident without evidence.

Classify each failure before deciding the recovery action:

1. Job failed, missing or orphaned: resume or retry its durable reading stage.
2. Job completed but missed rows/account sections: re-evaluate with a newer
   reader or perform a targeted new extraction.
3. Rows exist but values/controls do not reconcile: open the specific review
   problem; rerunning the same extraction is not a useful default action.
4. Original unavailable/unsupported/unreadable: explain the limitation and the
   next usable recovery action while retaining the source and saved work.

The existing missing-reference Retry repair, pause/lease machinery and protected
one-off recovery remain foundations. `has_financial_reading` currently checks
text/geometry presence, not extraction completeness; this is an identified gap.

### A2. Make Retry an observable operation

- Clicking Retry creates or resumes one attempt and immediately shows its
  accepted/running result. Repeat clicks or a lost response return that same
  attempt. An active job says it is already running.
- Reopen the batch and see the same persisted stage and outcome. An error states
  what failed, whether another retry can help and the available next action.
- Preserve source lineage and saved edits when creating a fresh reading. An
  internal reading is history beneath its original, not a new apparent upload.
- Keep pause/resume/checkpoints, worker restart and timeout recovery intact.
  Starting Financial must not cancel AI ingestion or the reverse.
- On completion, reveal the affected statement/period and retain the user's
  batch position. Completed batches move to history only when unresolved work
  remains discoverable elsewhere.

### A3. Repair supported readers from actual omissions

Use the maintained bank/layout matrix and reported private examples: BBVA
MXN/USD/EUR, Santander bank/investment/cheque variants, Monex, Kapital/Intercam,
and mixed bank/card collections including the previously supplied card and
Andrews layouts. Include scanned/OCR text, sparse/zero-activity statements,
multi-account/multi-currency PDFs, repeated headers and long documents.

Compare printed rows, dates, directions, amounts, balances, counts and section
boundaries. Repair the shared layout/quality fallback responsible. Targeted image
rereading currently covers only some known families; extend on demonstrated
need and keep incomplete results explicit. Register improvements for future
files in every case, with synthetic committed regressions. Private originals and
extracted customer values stay outside the repository.

### A4. Revisit affected old batches once, safely

Use a stable, versioned recovery campaign with a snapshot of eligible failed or
partial sources and durable per-source receipts. A fixed old release identifier
must not make completed recovery permanently skip later reader improvements.
Select by affected reader/version/outcome; avoid rerunning every successful
statement after every release.

Protect newer reviews, manual additions/exclusions, categories, ownership,
removals, skips, notes, findings and active jobs. Recovered candidate rows pass
the same duplicate and reconciliation gate as new reads. Uncertain matching
opens comparison; it does not overwrite an investigator's decision. Repeated
campaign starts and worker restarts must not repeat completed writes.

## Workstream B — import complete statements once, with understandable checks

### B1. One current reconciliation result everywhere

The code already has a shared admission gate and exact arithmetic. The gaps are
in its lifecycle and presentation: imported batches can still use historical
issue metadata; transaction corrections can invalidate verification without
updating the displayed assessment; the local saved-details patch reads stored
admission. Make details, batch/file summaries, history and import decisions use
the same current revision. A stale result displays that checks need updating and
cannot enable a new import.

Keep a compact calculation visible beside the PDF:

- Printed opening balance.
- Total included money in and money out (card charges/payments use their proper
  liability convention).
- Calculated closing balance.
- Printed closing balance.
- Signed difference and a plain-language explanation.

Example: opening 100,000; net transactions +300,000; calculated closing 400,000;
printed closing 500,000. Display **100,000 short of the printed closing balance**.
The difference is an unexplained amount, not proof of the exact missing payment.
As Alex adds/corrects values, show Checking and then the assessment for that edit
revision. Invalid/incomplete amounts show Cannot calculate yet, not zero.

A zero closing difference is insufficient when printed totals/counts, running
balances, section coverage or unresolved payment readings still contradict it.
Never certify a failed extraction as quiet simply because balances match.

### B2. Every flagged row explains itself and leads to its correction

Return a stable reason, affected field, source page/row, expected format/value
and correction destination. Missing dates, invalid characters, ambiguous money
columns and conflicting balances must be visible without Alex discovering a
hidden validation rule. Show a problematic character intelligibly while
preserving the original text and evidence.

Selecting a problem focuses its field beside the right source page. Metadata,
balance, assignment and no-activity problems need their own destinations, not a
generic account editor. Keep a current reason list and Next problem/Next
statement/Back to batch, retaining filters and position. A saved correction has
a saved receipt; it is not labelled reconciled until the current checks pass.
Remove remaining copy saying missing required details can be imported later.

Manual rows remain until an explicit Save/Done/Discard. Preserve source page and,
where running balance order matters, a position relative to a printed row or
control. Today any manual row disables every running comparison; change this so
only genuinely unordered intervals are unavailable. Do not infer same-day order
from dates or switch off unrelated reliable checks.

### B3. Apply admission at every write boundary

Use the current assessment under the existing concurrency controls for single,
batch, queued, replacement, recovery and saved pending/manual additions. Reject
stale requests, unresolved differences and duplicate-ignored periods server-side.
Keep a single durable receipt on repeated requests and response loss.

Editing existing imported payments preserves those records and citations while
refreshing their assessment. Legacy partial imports must be identified and
repaired through a reviewed, source-backed recovery; do not silently delete or
withdraw historical work to make the new policy appear satisfied. Pending new
rows stay outside admitted totals until the whole current statement qualifies.
Any proposed exclusion/replacement of existing admitted records needs a concrete
scope preview and retained history.

### B4. Automatic duplicate ignoring with a visible retained original

Match normalized bank, full account number, holder and exact start/end dates as
requested. Preserve leading zeros; a masked suffix, similar name or overlapping
date range cannot establish identity. Currency/product compartments remain
safeguards: a foreign-currency section or credit-card account is not discarded
merely because other printed identifiers coincide.

For confirmed repeats, choose a deterministic retained statement, preferring an
existing admitted/reviewed source. Persist the ignored disposition and show
**Duplicate - Ignored by system**, with Open retained statement, Compare sources
and Restore to review. Keep ignored items in searchable history and out of the
active import queue. Repeated prepare/retry returns the same decision.

Apply this per statement period: ignoring one period in a mixed PDF must not
discard its other accounts or months. Explicit revisions/conflicting payments or
controls require comparison. Unique corrections on a copy are preserved and
never silently overwrite the retained version. Restore means review again, not
import immediately. Already imported duplicate candidates use a previewed
duplicate-exclusion/merge journey; no bulk deletion of originals.

## Workstream C — make the imported records complete and usable

### C1. Complete inventory, concise summary and optional filters

Transactions opens with all imported case payments. Clearly distinguish case
totals from current scope/filter totals. Show transaction, canonical account and
bank counts, currencies and actual date coverage. Use an expandable account
directory when the list is long, not a truncated filename/label list.

Count from structured IDs and the full matching dataset, not the visible page.
Keep unknown bank/account/date/counterparty counts explicit. The directory can
include saved quiet accounts without claiming they contain transactions.
Incomplete directory or ledger loading must show a recoverable error rather
than a partial list labelled complete.

Preserve existing separate Person/company, Bank and Bank account selectors.
Bank-only spans all owners; an account filter narrows it. Dates, currency,
category, sender and beneficiary combine predictably. Each selection can be
cleared independently; returning retains scope. A matching-count denominator
must say whether it refers to the case or a narrowed selection.

### C2. Filters, categories and counterparties as a complete saved workflow

Choose records across pages, edit or link, see a saved result, reopen and verify
the same values in Transactions, profile, filter choices and export. Existing
person/account selection uses stable IDs while preserving the printed name.
For a bank account, a debit leaves the statement account and a credit enters it;
the counterparty picker fills the other side. Keep card liability conventions
explicit rather than inverting transaction direction ad hoc.

If a saved correction moves a row outside its active filter, explain where it
went and offer to open it. Do not drop an unfinished editor mid-entry. Failed or
stale saves preserve the draft. Export membership and totals match the complete
filtered set, including ownership/counterparty scope.

### C3. One confirmed person/business, with all their accounts inside

The current profile code can mix owned-account activity with appearances as a
counterparty, and can infer owned accounts from the latter's originating rows.
Fix the shared frontend/export membership contract before grouping cards.

Default to one profile per confirmed person/company. Populate its accounts from
the ownership directory, including quiet accounts, not only transaction rows.
Keep unlinked accounts and unresolved printed payment names discoverable in
clearly labelled views. Do not merge identity by similar names alone.

Within a profile separate:

1. Activity on this person's accounts.
2. Payments involving this person as sender or beneficiary.

A third party paying this person must not make the third party's bank account
appear as owned. Honor dated and joint ownership, deduplicate transaction IDs
within each scope, and explain that profiles of joint owners are not additive.
Preserve currency/product separation, source aliases and account-level detail.
Account/payment/source drilldown returns to the parent profile and its filters.

### C4. Only represented months in charts

Change both `transaction-analysis.activitySeries` and
`account-history.historyMonths`, which currently generate intervening months.
Transaction charts use actual dated transaction months. Account-history charts
also include months supported by saved statement coverage, including genuine
quiet periods. Filter bounds alone never generate months.

October, November and January must render exactly in that order when December
has no supporting data. A small date-gap annotation may explain the gap, but do
not add a December zero bar or carry a balance forward. Across selected
accounts, use represented months' union: if one account has November evidence
and another does not, the latter is unavailable, not zero. Distinguish partial,
unverified and multi-month coverage. Preserve year labels and never place
undated payments into an invented month. Keep source tables, drilldown and return.

## Integration and delivery order

1. **Checkpoint and contracts:** preserve the current local patches, record the
   private test draft, establish source/assessment/disposition/scope contracts and
   single-file ownership. Audit the specific live failures read-only.
2. **Run three lanes concurrently:** A diagnoses and repairs recovery/extraction;
   B implements current assessment and duplicate disposition; C repairs scope,
   ownership and represented months against those agreed interfaces. Coordinator
   integrates the common UI and retains date/currency/source fixes.
3. **Connect every writer and consumer:** verify retry → review → reconciliation
   → one import → accurate Transactions/People/Trends/export. Recheck all old
   entry points; no separate permissive import route remains.
4. **Existing-data rehearsal:** run a source-backed recovery/duplicate audit in a
   disposable environment, report protected/conflicting cases and prove repeated
   runs preserve IDs, edits and receipts. Preview any existing-import exclusion.
5. **Release gate:** focused regressions, real-service browser journeys, forced
   typecheck, production build, scoped lint, migration compatibility and explicit
   staged-content inspection. Regenerate the action inventory after final UI.
6. **One coordinated publication:** push the completed authorized code-only
   scope; that triggers deployment. Honor active-ingestion gates. Do not manually
   restart/cancel jobs or treat checkout version alone as successful deployment.
7. **Live acceptance and recovery:** confirm build/health/revision, verify the
   affected journey in the authorized test case, inspect actual reported failures
   and run the scoped authorized recovery with preserved work. Record real counts
   and unresolved reasons. Reopen saved results and return paths.

This plan does not create another scheduler. Durable server jobs should own
recovery progress; repeated unchanged assistant wakeups are not progress.

## Acceptance matrix — completion requires observed outcomes

| ID | Scenario | Required result |
| --- | --- | --- |
| P01 | Failed file; single/double Retry; lost response; reopen | One attempt, visible stage/result, no duplicate reading/import. |
| P02 | Missing prepared reference with existing reviews/imports | Reference repaired; saved IDs, corrections and notes retained. |
| P03 | Processed file with printed activity but zero/partial extraction | Correct reader/re-extraction or specific unresolved explanation; never certified quiet from zero rows. |
| P04 | Interrupted/paused recovery and AI/Financial in either start order | Independent progress, restart-safe checkpoints, no unintended cancellation. |
| P05 | Exact duplicate and repeated preparation | One retained active statement; ignored copy has exact required label, source link and reversible history. |
| P06 | Masked account, overlapping dates, currency/card compartment or revised content | No unsupported automatic discard; explicit comparison when necessary. |
| P07 | Mixed PDF containing one duplicate and one new period | Only duplicate period ignored; other period progresses normally. |
| P08 | Calculated closing 400k vs printed 500k; then correction | Exact 100k shortfall; updates for current edit; no import until complete checks pass. |
| P09 | Closing matches but offsetting rows are missing | Printed counts/totals/coverage still prevent false readiness. |
| P10 | Missing/invalid field or invisible character | Specific reason and target field/source; unfinished row remains visible. |
| P11 | Manual row with known/unknown placement | Reliable intervals still checked; unknown interval explained; no global running-check bypass. |
| P12 | Save balances/date/currency; reopen; correct again | Current details, batch reasons and history agree; transaction dates unchanged by period edits. |
| P13 | Stale assessment, queued import and concurrent import requests | Server rejects stale state; one successful admission and receipt. |
| P14 | Explicit verified quiet period versus failed extraction | Quiet period visible with no fabricated payments; failed extraction remains unresolved. |
| P15 | More than 100 accounts and multiple pages/currencies/banks | Complete counts and choices, canonical accounts counted once; unknowns explicit. |
| P16 | Bank → account → dates/currency/category/party, clear and return | Predictable intersection, independent clear, saved scope and exact matching export. |
| P17 | Category/counterparty edit across pages, stale save and reopen | Persisted identities/labels and consistent profiles/totals; failed edits retained. |
| P18 | One confirmed owner with five accounts, including quiet account | One primary profile with all five accounts and currency-separated totals. |
| P19 | Third-party payment, joint and dated ownership | Counterparty appearances do not become ownership; no duplicated IDs within scope. |
| P20 | October, November, January plus a quiet month | Only supported months; no invented December; genuine quiet month visible. |
| P21 | Month covered for one comparison account only | Other account unavailable, not zero; no carried balance through missing evidence. |
| P22 | Chart/profile → payments/source → return, wide/narrow | Correct scope, source and restored selection without buried controls. |
| P23 | Re-run recovery after a newer reader; repeat campaign | Only eligible affected sources revisited; edits/exclusions/receipts protected. |
| P24 | Live deployment and old backlog | Successful frontend build/health plus actual workflow evidence; all audited items have a recorded outcome. |

Each row is tracked as implemented, locally verified, deployed and live verified
separately. A passing component test, registered parser or green build alone is
not whole-workflow completion. The original Apply USD incident, specific retry
failures, legacy quiet-period blocker and content/provenance cleanup remain named
items until their actual outcomes are known.

## Completion record to publish to the user

Report original failures resolved, files/periods processed, statements ready,
statements imported and exact payment counts; duplicates ignored with retained
links; unresolved items grouped by reason; investigator work preserved; version
deployed; local versus live evidence. Say precisely what remains, with no blanket
claim that all banks or every historic statement has been certified.

References: [R01–R06 plan and acceptance](reconciliation-and-account-history-plan-2026-09-24.md),
[workflow reference](README.md), [Alex acceptance](../alex-financial-acceptance.md),
[processing capabilities](processing-capabilities.md),
[duplicate-review foundation](duplicate-statement-review-2026-09-24.md),
[recovery and source-scope release](next-release-2026-09-24.md),
[23 September complete feedback](feedback-implementation-plan-2026-09-23.md).


## Implementation checkpoint — 25 September 2026

Work resumed after the user's requested pause; the checkpoint preserved every
lane and the uncommitted changes. No new code from this plan has been published
at this checkpoint. The previous successful deployment is `ded066c9`.

### Connected changes implemented locally

- Retry persists a correlated attempt, stage, explanation and permitted next
  action. A failed preparation on a readable source rebuilds reviews from that
  same reading, preserving saved work. Missing sources produce a persisted
  unavailable-source result, with an Evidence destination and explicit recheck.
  Verified lineage is required before any retained reading is offered.
- Single review, batch, saved details and account history use current admission
  results. The calculation shows exact opening balance, incoming/outgoing totals,
  expected closing balance, printed closing balance and difference. Pending
  checks do not display an old result as current. Corrections target the named
  field/source and keep manual rows present until explicitly finished/discarded.
- Manual additions carry explicit before/after source positions. An unread page
  can use its nearest printed boundary within the selected statement. Unknown
  intervals remain explained and blocked; reliable intervals remain checked.
  The saved-payment and pending-record forms share this workflow and retain
  placement through edits, reopening and lost-response recovery.
- Duplicate decisions require complete statement identity plus identical source
  bytes or financial readings. Currency and account type remain part of scope.
  Revised content, partial references and investigator edits are protected.
  Ignored copies have a retained-source link, reversible decision and exact
  **Duplicate - Ignored by system** label. Mixed PDFs retain their new periods.
  A late check cannot overwrite an edited form; an ignored receipt stays on the
  review instead of redirecting to nonexistent imported payments.
- Batch file review now opens the intended reading, focuses the destination and
  retains a route back to the same batch/reason. Refresh and browser Back preserve
  that context. Removed and superseded items no longer inflate active work.
- Transactions expose complete available inventory and matching totals. Profiles
  show confirmed owners with all their accounts, including quiet accounts, and
  separate their own-account activity from counterparty appearances. Export scope
  matches that distinction. Charts include represented months and source-backed
  quiet periods without adding artificial gap months or carrying balances.

### Verification recorded so far

The combined coordinator backend run passes **332 tests and 48 subtests**.
The main statement/retry/detail/draft component run passes **89 tests**. The broad
financial unit run passed 1,546 tests with two failures: an outdated account-history
request fixture and a large-selection timeout under concurrent load. The fixture
was corrected; a bounded rerun of both suites plus the batch suite passes **33
tests**. These numbers overlap and must not be added into one claimed total.

Independent Chromium checks cover the actual Financial page's batch/file return
journey (two tests), actual statement review and duplicate/manual-position flows
(six), saved manual additions and pending corrections (two), plus the ownership,
filter, register and represented-month checks reported by their owners. Synthetic
browser fixtures prove interaction and layout; they do not certify unread client
records. Final build, affected lint, publication and live results follow below.

### Source findings and remaining acceptance

- The supplied mixed bank/card collection currently has **52 of 53 periods**
  passing reconciliation and **280 actual payment rows**. One conflicting opening
  balance remains a review item. A corrupted zero-interest line is excluded from
  payment count. The OCR guard preserves identity, readable controls and rows.
- The supplied credit-union collection retains **45 account/period sections**
  and **2,076 candidate readings**. Only one is automatically admissible; 24 quiet
  sections require explicit confirmation, and damaged values or coverage gaps
  still need source review. Registration of its targeted repair campaign does
  **not** activate a blanket reread; that campaign remains dormant.
- The supplied no-activity bank sample passes quiet admission. It is not the
  reported example containing the unread transaction, so it cannot prove that
  historical incident resolved.
- Live read-only inspection reproduced the old batch-to-file navigation failure
  and confirmed that originals for two failed entries still exist in Evidence.
  The historical missing-reference error is not yet conclusively attributed.
  Existing failed batches are not silently reprocessed during this inspection.
- The original currency-apply incident, current blocker on the legacy saved quiet
  period, final source/payment return checks and explicit discard of the test-only
  draft still require live acceptance after deployment.
- The authorized content/provenance cleanup has **not** been established by the
  old removed-file count or statement-recovery count. Those measure different
  operations. Pure Financial-membership hide/restore and active-work protection
  are implemented and locally verified before that pass; original Evidence, saved imports and
  investigator work must remain protected. Financial content is independent of
  extension. Uncertain content remains available for review.
- Deployment guards and graceful worker transition pass 20 focused checks.
  The gate now includes active recovery, uploads and registration; shell snapshots
  preserve the gate across pull and rollback. Backend shutdown gets the same long
  grace period as ingestion workers. The recorded external push runner pulls before
  starting the deploy script; its installed configuration is outside this repository.
  The separate admin updater starts the installed script first and is not the user's
  push route. Verify the actual release log rather than assuming either entry path.
  Successful build, service health and the affected live journeys must be checked
  after the authorized push. No claim of whole-backlog completion is made here.

Private source identities, data, audit files and screenshots are outside Git.
This checkpoint supersedes earlier planning-only language without marking the
remaining P24 or existing-data acceptance complete.

### Final integration additions

Financial membership removal now preserves Evidence, saved drafts, notes and
reading history. Imported records and active work are protected; a completed file
is not blocked merely because an unrelated file in its batch is still running.
Verified same-case reading versions share the decision, while independent uploads
with identical bytes remain separate. Restore returns to the visible register.
This packet passes 52 backend tests with 13 subtests, 22 unit tests and two Chromium
membership tests plus three existing import-removal browser tests.

A collapsed, read-only source audit is connected to the statement register.
It lists recorded provenance and protected work, and opens one bounded retained
excerpt at a time. It does not start extraction or decide relevance from file type.
The backend's five dedicated synthetic checks pass. The actual authorized content
review and its outcomes remain a post-release step.

Final schema checks accept absent calculations and admission results on older or
blocked statements rather than rejecting the whole response. Both affected screen
suites pass 29 tests. Final TypeScript/build/lint results and live evidence are
recorded separately after all handoffs; none of these counts should be summed.

### Release checks before publication

The complete Financial unit run passes **1,560 tests in 198 files**. Forced
TypeScript checking, the production build and scoped Financial lint all pass.
The audit UI passes 27 focused unit tests and four Chromium journeys covering
wide/narrow viewports, retained excerpts, source viewing, locating exact file
families and returning. These checks overlap the full unit run.

An independent review found that queued recovery was missing from membership
protection. A shared scalar-ID lookup now protects pending/waiting/reading items
in running campaigns, including case-owned retained versions. Paused and terminal
campaigns remain distinct. Audit/intake/scope checks pass **48 tests and 21
subtests** after the fix. Review counts now explicitly count storage records,
with the interface showing review presence rather than an inflated review total.

Publication and live verification remain the next steps. The live admin updater
is not configured; it is separate from the confirmed automatic push deployment.
The previous successful release log identifies the built revision and healthy
services. Do not use its checkout label alone as evidence for this new release.
