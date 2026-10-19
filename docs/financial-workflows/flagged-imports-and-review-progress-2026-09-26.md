# Flagged imported rows and visible review progress

## Report and investigator journey

The supplied screenshots show a flagged original row without a correction action,
and a finished recovery banner whose review count does not establish how far the
investigator has progressed. The statement filename and the exact saved record
behind the first screenshot remain unidentified. No client data is a test fixture.

From Statements & accounts, select a file or batch statement, locate a flagged
source row, inspect its saved records beside the original, correct the matching
payment or complete a retained incomplete record, save, and return to the same
source row. If a payment was never captured, the existing missed-transaction
entry remains available. A changed reading can shift row IDs; the interface must
not guess which ledger payment to edit from that ID.

From Processing batches, distinguish saved records, unfinished reviews, saves in
progress and retained decisions. Open only unfinished statements, save before
moving, skip saved/decided statements, and return to the same filter. Reaching the
end must not silently cycle to an earlier statement. Earlier unfinished work
remains available by returning to the batch.

## Implementation

- Imported flagged rows now have a visible saved-record review action, including
  source focus, inline correction, incomplete-record recovery, missed-payment
  entry and a return control. View-only access remains read-only.
- Saved-statement review uses independent filters, so retained account, category,
  currency or search filters from Transactions cannot hide its records or be
  changed by this review.
- Imported extraction flags are explicitly comparison history. Current saved
  payments may already contain corrections. Source readings remain unchanged;
  opening the panel never reimports, replaces or marks a reading checked.
- Batch cards show saved batch counts. Opening a batch refreshes its current
  checks. The batch summary distinguishes saved, unfinished, ready, pending,
  ignored/skipped, assigned and other reviews without counting overlapping
  reasons as additional statements.
- Saved, ready-to-save and unfinished filters apply before server pagination.
  Next unfinished statement saves review progress before navigation and uses
  the existing non-wrapping navigation. The filter survives return to the batch.
  Current checks may legitimately reopen an outdated duplicate decision.
- A sticky statement header retains batch/file/account/period context and import
  status. Imported status takes precedence over an older readiness flag.
- The recovery banner explains that its completed background run and historical
  review count are separate from current investigator progress.

## Verification and limitations

- Chromium journeys at 1280px and 390px exercise imported-row correction,
  ambiguous save failure, retained draft, refreshed ledger, successful correction,
  return and server-response-backed reopening. The original warning stays intact.
- Batch browser journeys exercise saved identity, save-before-navigation,
  unfinished scope, explicit end-of-list, return and switching saved/unfinished
  filters. Existing pre-import row-review and recovery journeys also pass.
- Synthetic database tests cover whole-batch filters beyond the first page,
  non-wrapping navigation past imported/skipped statements and reduced unfinished
  counts after saving. Pure summary tests also cover duplicate/assigned states.
- The broader batch suite had 83 passing tests and one environment error: the
  local Python runtime lacks `langchain_core`, required by an unrelated router
  import. This is not counted as a passing test. Seven targeted progress/navigation
  checks pass. Frontend verification results are finalized below.
- Browser access to the existing Brave session was declined. No alternate route
  was used to bypass that denial. Live revision, the exact supplied row and live
  investigator acceptance remain unverified. Client records and running jobs were
  not changed. This record does not assert publication or deployment.

Final local checkpoint: 78 frontend unit checks and 15 distinct Chromium journeys
pass (including the later independent-filter and main Transactions regressions).
The production build and scoped ESLint pass. The existing large-bundle and React
act warnings remain. Workflow action inventories were regenerated. All sources
and screenshots remain outside publication. Code-only publication is the next
step; automatic deployment and live acceptance remain separately unverified.
