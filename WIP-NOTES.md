# fin/alex-1009 — statement import fixes (2026-10-09)

Branch `fin/alex-1009` = fin/release-1 + live c3417d74. Not pushed, not deployed.

## Commits

- `6a843280` fix: one shared import action at top and bottom, never silent while saving (bug 1)
- `aebf1094` fix: make a statement file's incomplete records findable and its counts honest (bug 2)
- this notes file

## Bug 1: "Import transactions at the top does nothing"

What the live evidence showed (case 49494305, file 0f8dc458): the queue-import request never logged a
response. The first confirm-result poll came exactly 30 s after the operation's transaction started, so the
browser's 30 s timeout fired. The operation row's `created_at` is the transaction start (`now()`). The
import finished about 4.5 min later. The browser gave up after about 23 s of polling and showed an error
only in the summary area.

Changes:
- `backend/services/financial/standalone_import_jobs.py`: `queue_statement` bounds its `SELECT … FOR
  UPDATE` on the EvidenceFile with `SET LOCAL lock_timeout = '5s'`. `SET LOCAL` is used so the setting
  cannot leak into the pool (same reasoning as 54ed3f8c), and the timeout is reset to DEFAULT once the lock
  is held. On 55P03 it rolls back, writes nothing, and returns `busy: true` with a message. If an identical
  submission was already accepted, it returns that operation instead.
- `frontend_v2/.../lib/statement-import-recovery.ts`:
  - A `busy` answer is definite (nothing was written), so the same queue-import is retried after 2, 3, 5,
    5 and 5 s. This is safe because the job id is deterministic. If the file is still busy after that, it
    reports "Nothing was imported" and clears the pending key.
  - When the receipt polls run out after an accepted (`in_progress`) operation, it throws
    `ImportStillSavingError` ("Import accepted — still saving…") instead of the generic error.
- `StatementImportPanel.tsx`:
  - The summary (top) and the confirmation area (bottom) both use `importActions(place)`. The primary action
    has the same behaviour and label in both places: `Import N transaction(s)`, `Save statement balances`,
    `Save account closure`, or `Save for bulk import` in a batch review that has no confirm handler.
  - In batch review both places also show the same secondary action, `Save for bulk import`. Before this,
    the top button imported and the bottom one saved to the batch.
  - Pending, accepted, error, background-job link and Check saved result now render beside the copy that
    was pressed, in `importStatus`. The default is the summary, or the bottom copy when the summary is not
    rendered.
  - An accepted import that is still running shows the status "Import accepted — still saving". The existing
    `backgroundChecks` loop keeps checking every 15 s for up to 40 checks (about 10 min, up from 10 checks).
- Test labels updated mechanically: "Confirm import of N transactions" and "Import N payments and view
  Transactions" became "Import N transaction(s)". Because the label now appears twice, `getByRole` became
  `getAllByRole(...)[0]`.

## Bug 2: file card "300 usable transactions · 1 incomplete records to check"

Findings (read-only, case 49494305):
- On d32d2711 (001052-001273), the one open record is page 7 row 7:0:17. The reader dropped its date under
  "Check the transaction date against this billing period": the printed date is just before the cycle start,
  i.e. a late-posted charge. Its `missing_fields` is `['date']`.
  NOT CHANGED: that is the benchmarked reader's date rule, which belongs to the reader pipeline.
- On 5c4cf2dd (001501-001722 copy) there are three open records, and all three have complete values. On
  2026-10-06 the investigator:
  - corrected 7:0:17 with a date the day before the cycle,
  - added a manual re-entry of that same charge,
  - added a manual payment credit.
- **Why they are stored as incomplete (f):** this is by design, not a bug.
  - `append_payment` and `complete_record` keep corrections and manual additions in
    `statement_incomplete_records` until `complete_currency_records` → `assess_saved_additions` shows that
    the whole statement reconciles with all of them together. That is the "reconciled-statement-v1" policy,
    covered by `test_financial_statement_admission.py`.
  - Here the assessment fails on the closing balance (`statement_admission.blockers`). The difference equals
    exactly the net of the two manual additions (the credit minus the duplicated charge). So the corrected
    original row on its own would reconcile.
  - The investigator's re-entry duplicates the corrected row. The manual credit either is already accounted
    for in the printed figures or belongs to another cycle.
  - Effect: one wrong manual addition blocks a correct correction (all-or-nothing).
  - Because this is by design, the UI now says what is still needed (see below). No code path stores a
    complete manual row incorrectly, so no fix for new saves and no backfill are needed. The new card and
    list fields are computed on read.
- "53 periods have checks to review": every period's only problem is the coverage note "Another supplied
  statement covers some of these dates". This comes from the duplicate copy.
- "52 of 53": period 2021-09-10..2021-10-10 was prepared under two statement keys (703f…, f244…), and only
  703f… was saved.

Changes:
- `statement_file_status.py`, per file:
  - `awaiting_reconciliation_count`: open records with `missing_fields == []`.
  - `incomplete_sources`: source id, period start/end, missing count, awaiting count, and up to 3 blocker
    messages.
  - `repeat_periods`: unsaved, not available, not pending, not ignored and not under duplicate review, with
    the same dates (and the same account, when known) as a period already saved from this PDF.
  - `overlapping_periods`: periods whose only problems are coverage notes. These are no longer counted in
    `periods_with_checks`. Duplicate holds, needs_comparison and conflicting reviews still count as checks.
  - This is the honest-label option. Suppressing the notes outright would hide real overlaps.
- `imported_records.py` and the router: `GET /incomplete-records` accepts a repeated `evidence_file_id`
  filter. Each record gains `awaiting_reconciliation` and `statement_blockers`.
- `StatementFilesPanel.tsx` card:
  - The badge reads "N usable transaction(s) · X incomplete record(s) to check · Y completed record(s)
    waiting for the statement to reconcile".
  - A list below the card button names each affected period and what is still needed.
  - A separate `Show N records to check in <file>` button (not nested in the card button, with
    `aria-expanded`/`aria-controls`) opens `ImportedRecordsPanel`. The panel is scoped to all of the file's
    reading versions, expanded, and its Review statement action opens this file.
  - The period line reads "52 of 52 statement periods saved · 1 repeat reading of an already saved period,
    not imported again · 1 period has checks to review · 51 periods overlap another supplied statement
    (compare if needed)".
  - Plurals are fixed for transactions, payments, statements, imports, periods and records.
- `ImportedRecordsPanel.tsx`:
  - The summary tells missing-value records apart from completed ones that are waiting.
  - Completed records show "Values complete · enters Transactions when the statement reconciles" and "Still
    needed: <blocker>" instead of an empty "Check".
- Verified read-only against live case 49494305 with this branch's code:
  - d32d2711: 1 missing record (2020-10-08..2020-11-09), 52 saved, 1 repeat, 1 period with checks, 51
    overlaps.
  - 5c4cf2dd: 3 waiting records with the closing-balance blocker, and the same period counts.

## Tests run

- Backend (CHROMADB_PORT=1 CHROMA_PORT=1), all passing:
  - `test_financial_standalone_import_busy.py` (new, 3 tests)
  - `test_financial_statement_file_status.py` (3 new tests)
  - `test_financial_duplicate_file_status.py`
  - `test_financial_optional_import_review.py` (new filter/awaiting assertions)
  - `test_financial_refresh_currency.py`
  - `test_financial_statement_import_router.py`
  - `test_saved_statement_recovery.py`
- Frontend unit (vitest), all passing:
  - `lib/statement-import-recovery.test.ts` (new, 4 tests)
  - `StatementImportPanel.test.tsx` (2 new tests, plus a batch both-places assertion)
  - `FinancialBatchPanel.test.tsx`
  - `StatementFilesPanel.test.tsx` (1 new test)
  - `ImportedRecordsPanel.test.tsx` (1 new test)
  - `SavedManualRefresh.test.tsx`, `InvestigatorOverview.test.tsx`, `hooks/`
- Frontend browser (vitest, chromium; needs `PLAYWRIGHT_BROWSERS_PATH=/home/conorbowles51/.cache/ms-playwright`):
  - Passing: BulkStatementDetails, StatementClarity, StatementBalances, SavedStatementRecovery,
    FinancialFileMembership, StatementTotals, FinancialPersistence, ReconciliationJourney, StatementRowReview
    and TransactionBalanceCorrection.
  - 9 tests fail in StatementImportPanel.browser, StatementDuplicateIntegration.browser and
    MonexStatementWorkflow.browser. **The same 9 fail identically on the unmodified base**: I checked by
    reverting the frontend diff and re-running. They are pre-existing failures on this box, not caused by
    these changes.
- `npx tsc --noEmit` in frontend_v2: clean.
- Postgres-only lock tests (`LOUPE_TEST_LOCAL_POSTGRES`) were not run: there is no local test PG on :55434.

## Not done / open

- I did not identify what held the EvidenceFile row lock for minutes at 02:17. The fix bounds the wait; it
  does not remove the long holder. Worth checking whether a batch turn or a statement save holds the
  evidence row for its whole preparation.
- Product question: complete corrections are all-or-nothing with manual additions. A wrong manual addition
  holds back a correct correction, as on 5c4cf2dd. Options:
  - admit each completed record that reconciles on its own,
  - or let the investigator withdraw a manual addition from the records list.

  I did not check whether a manual addition can already be withdrawn in the UI.
- For 5c4cf2dd the investigator needs to remove or correct the two manual additions. The corrected original
  row would then reconcile. No data was changed.
- Not touched: the reader date rule for late-posted charges, and the double-counting of the two Bates copies
  (that is the duplicate set-aside script's job).

## Follow-up (Neil's decision on open question 2): completed rows enter Transactions on their own proof

Rule (`backend/services/financial/held_record_admission.py`, one module; `INDIVIDUAL_ADMISSION = False`
restores the old all-together rule):
- Ready = unresolved retained records with every value present.
- Corrected printed rows are the statement's own lines and form the base, tested together.
- Each investigator addition is first checked for a likely repeat. A repeat has the same amount and
  direction as a row in one of these places:
  - an admitted saved row of this statement,
  - a corrected printed row,
  - an earlier addition.

  It must also have the same date, or the same description within 3 days. A likely repeat is held:
  "Looks like a repeat of an existing row (…)".
- Each remaining addition is assessed alone on top of the base, using the ordinary
  `assess_saved_additions` / `assess_admission` reconciliation. That function gained an `include=` candidate
  set: printed rows outside the set keep their original reading, and additions outside it are left out.
- Admission:
  - If the base reconciles, the base is admitted together with the additions that pass alone, as long as
    they also reconcile together. If they don't, those additions are held as ambiguous.
  - If the base fails and exactly one addition fixes it, the base and that addition are admitted.
  - If several additions could fix it, everything is held as ambiguous.
  - Otherwise the base is held ("doesn't add up with the corrected printed rows").
- Additions that fail alone are held:
  - "The statement doesn't add up with this row", or
  - "only adds up together with another added row" when they reconcile only as a group (fail closed).
- Held records carry `hold_reason` and `hold_blockers` in `statement_incomplete_records`.
  - The default assessment (`include=None`) leaves records with a hold reason out of totals, so a statement
    reconciles with its admitted rows while held rows remain visible.
  - Every completed row is still drafted, so a bad counterparty link fails the save as before.
- Applied on every save path that calls `complete_currency_records`: complete-record, manual-payment, and
  statement details / currency.
- Reading the records list (`GET /incomplete-records`) runs the same rule as a dry run (no writes). It
  returns `hold_reason` and `can_enter_now`.
- New `POST /sources/{id}/admit-ready-records` runs the rule for real, with the same locks and ingestion run
  as complete-record.
- UI (`ImportedRecordsPanel`):
  - each held record shows its specific reason;
  - records that check out are labelled as such;
  - an "Add N records that check out to Transactions" button calls the new endpoint.
- Replayed save receipts include the record's hold reason as a blocker (`kind: held_record`).

How the live held rows are picked up after deploy (no migration; nothing rewritten):
- When the investigator opens the records list for case 49494305, copy file 5c4cf2dd, the read-time dry run
  marks the corrected original row 7:0:17 as "checks out" and shows the "Add 1 record that checks out to
  Transactions" button.
- Clicking it, or any later save on that statement, runs the rule and admits that row.
- The two manual rows remain held with their reasons. No automatic background admission is done.

Read-only dry run against live data (this branch's code, `SET TRANSACTION READ ONLY`, case 49494305):
- 5c4cf2dd, row 7:0:17 (corrected original): **would enter**. The statement with it is `reconciled`, with
  difference 0 and no blockers. Under the old all-together rule it was held, with a closing-balance
  difference equal to the net of the two manual rows.
- 5c4cf2dd, manual re-entered charge: **held**, "Looks like a repeat of an existing row (corrected …)",
  matching the corrected 7:0:17.
- 5c4cf2dd, manual payment credit: **held**, "Looks like a repeat of an existing row (saved …)". A saved,
  admitted payment with the same date and amount already exists. So the "missed" payment was not missed,
  which also explains the failed reconciliation.
- d32d2711, row 7:0:17: unchanged. It still needs its date (missing value, not a held completed row).

Tests:
- Backend, `test_financial_statement_admission.py`:
  - The old by-design test was replaced: offsetting additions that only reconcile together stay held.
  - New: an addition matching a saved row is held as a likely repeat.
  - New: a lone valid correction enters while a bad addition stays held.
  - New: records held under the old rule are reported by the dry run and admitted by admit-ready-records.
  - Another offsetting-pair test (unread-page addition) was updated to the new rule.
- Backend, `test_financial_payment_counterparty_link.py`: the offsetting-pair tail was updated to the new
  rule (both held, no link history).
- Backend suites run: every test file using these paths, 824 tests in all. 812 pass. The 12 failures are
  all in `test_financial_deployment_recovery.py` / `test_financial_recovery_followup.py`
  (DetachedInstanceError), and the same 12 fail on the unmodified base.
- Frontend: `ImportedRecordsPanel.test.tsx` gained a hold-reason and admit-button test. The
  ImportedRecordsPanel, StatementFilesPanel and SavedManualRefresh tests pass, and `tsc --noEmit` is clean.

Open:
- The likely-repeat window (same amount and direction, plus the same date or the same description within 3
  days) is a heuristic. A held repeat can only be resolved by changing or removing the addition.
  - Withdrawing an addition from the list is still not built.
  - There is no "I checked, this is a separate payment" override; that would be the next product decision.
- The base of corrected printed rows is still tested as one block. One wrong printed correction holds back
  the others in the same statement.
