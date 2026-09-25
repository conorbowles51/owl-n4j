# Retry, currency context and responsive statement review

25 September 2026. Alex reports that Retry still does not work for failed files
from the initial batches, a file reports "Statement not found in this case",
EUR is absent from Transactions, and loading/saving makes revisions take
20–25 minutes. These reports reopen the affected acceptance items after the
earlier release; successful deployment alone is not workflow acceptance.

## Investigator journey and acceptance

1. Open an existing failed batch. Every retained file remains identifiable even
   when old metadata is blank or a reading reference needs recovery.
2. Retry the particular failed reading from either its file or reading-job card.
   Show the request immediately, prevent repeat dispatch, and display the actual
   progress, receipt or actionable error beside that control. Track an already
   running attempt through completion. Preserve separate general AI processing,
   saved reviews, original files and removed/duplicate decisions.
3. Review and save one statement without reparsing unrelated case statements
   while holding save locks. Retain all fresh reconciliation and duplicate
   checks before import. Hidden screens should not repeatedly request expensive
   case-wide summaries; reopening them must refresh current results.
4. In Transactions, display known currency/account groups even when there are
   zero imported payments: zero money in/out/net, zero transactions and the
   account count. Keep this distinct from confirmation that the statements are
   quiet. Unread, unimported and incomplete statements must remain visible as
   pending work. Do not create fake payment rows. All holder, bank, account,
   currency and represented-date filters must describe the same scope.
5. Preserve the selected currency visibly when the current account/date scope
   contains no payments in it. Clearing the filter restores the matching rows.
6. Reopen the batch/source, return to the working view and verify saved state.

## Confirmed defects and local evidence

- Failed reading-job cards rendered enabled Retry without an action callback.
  The repaired control maps the exact case and retained evidence ID to the
  durable batch retry endpoint; unavailable/ambiguous mappings have an explicit
  explanation. A synchronous pending guard and nearby result/error prevent
  silent repeated clicks. Unit and Chromium regressions failed before repair.
- A separate original-file AI job incorrectly blocked retry of a failed retained
  Financial reading. Retry now checks the selected Financial attempt. A verified
  active job in an old error batch also needs the batch to resume observing it;
  no second processing job is dispatched.
- Old missing prepared references can already recover through the retained
  original or its existing reading. Additional regressions cover both and
  preserve saved corrections. The exact cause of Alex's historical file error
  is not established solely by its old error text.
- Saving one draft called a case-wide comparison solely to construct its
  response. On the same synthetic 200-file, 2,400-reading case, the repair reduced
  Save from 4.484 seconds / 1,413 SQL statements to 0.031 seconds / 13 statements.
  Queue and final import still reject overlapping or unreconciled statements.
- Sharing a fresh request-local reading between legacy comparison and current
  batch projection reduced the same batch GET from 9.145 seconds / 2,997 SQL
  statements to 5.255 seconds / 1,604. No persistent cache bypasses current input
  or admission checks. These local SQLite measurements do not establish the
  precise cause or production duration of Alex's reported waits.
- Old explicit null strings in summaries can fail batch ordering, and are also
  incompatible with the frontend response schema. The repaired read projection
  presents missing details as unknown while preserving the saved raw summary.
- A fresh, already case-scoped account-label directory replaces a canonical
  account lookup for every payment. For 865 synthetic alias-account payments,
  projection fell from 866 SELECTs to one, without changing membership or sums.
- Hidden statement registers, recovery/upload lists and account coverage readers
  no longer poll while the investigator is working elsewhere. Components remain
  mounted to preserve drafts; returning enables a fresh read. A Chromium request
  count regression proves the previously repeated hidden requests stop, including
  after broad query invalidation.
- Changing account/date scope could remove the selected currency's option while
  leaving that invisible filter active. The selected option now remains visible
  with its out-of-scope explanation; actual sums and imported rows are unchanged.

## Live observation and limits

Read-only inspection confirms the initial batches retain failed entries. Opening
the reported 22-file batch returned a generic HTTP 500; a separate 16-file batch
opened and displayed historical missing-statement errors and explicit retained
source restoration messages. No failed client reading has been retried solely
to demonstrate a control.

With all account, holder, bank, date and payment filters clear, the observed case
showed only MXN and USD imported payments. Inspected EUR sources included saved
balance-only periods and unimported periods. One EUR source had printed zero
opening/closing and movement totals. This does not establish that every EUR
statement is quiet or that expected EUR payments are absent from the source.
Alex clarified the required zero-payment currency/account summary above; that
requirement must be implemented without asking her to explain it again.

## Completion checkpoint

At the pre-publication checkpoint, Retry, draft-save/read performance, nullable
batch metadata, hidden polling and known-account currency summaries are
implemented. The account directory provides scalar saved-period metadata without
replaying admission or inferring inactivity. Currency/account/bank counts include
known zero-payment accounts, preserve current date/source filters and canonical
aliases, and leave payment rows, exports and actual monetary sums unchanged.

Focused validation includes:

- Retry service tests cover independent general-AI work, active-attempt
  observation, missing old references and reuse of retained readings.
- 151 save/import/overlap tests and 13 subtests preserve draft values and reject
  incomplete or duplicate imports. Batch-read projection checks cover null
  summary fields, Next ordering and fresh request-local reading reuse.
- 88 account-directory/selection/router tests and 19 subtests cover current
  same-case saved-period context with bounded query counts. Ledger tests cover
  EUR, cleared scopes and canonical label lookup without per-payment queries.
- Chromium covers exact reading-job Retry dispatch, pending feedback, source
  return, hidden request suppression and edit/save failure recovery. Known EUR
  account summaries are checked at 1280px and 390px with account/date/bank/source
  filters, currency retention and account-history return.
- Two additional Chromium journeys use actual FastAPI routes and a disposable
  synthetic database: missing prepared reading → Retry → import once → reopen
  unchanged payment IDs; saved EUR account directory → zero-payment summary →
  EUR filtering, with no fabricated payments. This harness does not use client
  data or an external processing provider.

The code-only release's automatic deployment result and affected live journeys
must be checked separately from these local results. No claim is made that the
entire observed production delay has been measured or eliminated before that
verification, or that every historical missing-statement error has the same cause.
Client originals, screenshots, extracted records and credentials are excluded
from publication. Active case jobs must not be cancelled or force-restarted.

## Published release and subsequent import progress

The verified code-only package was pushed as `6f773e02`. The automatic release
attempt at 16:47 UTC deferred before service replacement because one batch had
two accepted imports and an active worker lease. No active work was cancelled,
paused, force-released or restarted to pass the gate.

At the later read-only check, the same batch opened and its saved receipt showed
all 12 accepted statements imported, zero pending and 137 saved transactions.
Its separate file-preparation list still contained older failed readings; a
completed import receipt does not mean that every source file has been read.
The earlier generic batch error no longer reproduced at that check. The last
captured deployment log still described the deferred attempt, so successful
rollout of `6f773e02` and the affected live journeys remained unverified.

## Concurrent import and save — reproduced follow-up

An isolated PostgreSQL test reproduced an application-level deadlock: the batch
worker retained its item row lock while calling the strict import service through
a second database session. A concurrent review save could hold the Evidence row
while waiting for the item. The import service then waited for that Evidence row,
while the worker waited for the service in Python. Because the complete cycle
crossed database sessions and a Python wait, PostgreSQL could not detect it as
one ordinary database deadlock. The bounded probe used a local lock timeout to
release the test and confirmed the import could then complete once.

Independent review identified the same central lock-order risk with other
writers, so a pre-check in the Save form alone is insufficient. The repair must
release the worker's snapshot transaction before strict import confirmation and
guard its later receipt update against changed, removed or already completed
work. Reconciliation, exact-request idempotency, removal decisions and saved
edits must remain protected. This reproduced code defect is not proof that the
now-completed live batch experienced that exact lock sequence.

The central repair is implemented and independently reviewed. A successful
concurrent result can resolve only the exact failure projection of the unchanged
accepted request; it cannot overwrite later edits, removal or another accepted
request. A late failure cannot reset an already successful result. The existing
strict writer continues to serialize admission and exact-request reuse.

Validation: 99 connected batch/save/import/removal tests passed, and three real
PostgreSQL tests passed in disposable synthetic schemas. They reproduce the
concurrent Save/import ordering, verify two workers create one set of 12 payments,
and confirm that removal after admission cannot be undone by delayed finalization.
Seven finalization regressions cover both success/failure arrival orders, later
investigator edits, removal before/after admission, and replay after process exit
following a committed import. No live jobs or database records were changed for
these tests. The prevention repair and the live incident's precise cause remain
separate findings.

## Deployed and live checks — 25 September evening

The automatic deployment of `902ec945` (including `6f773e02`) succeeded. Its
recorded run started at 17:36:17 UTC and completed in 184 seconds; the final
health checks passed. All ingestion gates were idle before replacement. The
release nevertheless restarted the frontend and backend, overlapping Alex's
report that controls stopped responding during reconciliation at approximately
18:37 Dublin time. Safe ingestion transition does not mean uninterrupted access
for an investigator editing a statement. The user was advised to preserve the
existing tab and save its progress before reloading; no claim is made that every
unsaved edit in Alex's separate browser has been recovered.

Read-only live Transactions checks verified the known-account EUR summary,
currency filtering, complete account list, account-history navigation and return,
and clearing the payment filters. EUR accounts with no imported payments show
zero totals and account counts without creating payment rows or claiming the
statements are fully processed. A directory currency label does not change the
currency of independently saved statement periods in account history.

In the authorized test case, saving a statement's existing account, dates,
currency and balances returned the saved confirmation; reopening retained those
values. No client-case records were changed. The live “Read the statement again”
entry point exposes the reading method and explains that a new reading requires
review while existing transactions remain until a replacement is confirmed.
The inspected test batch has seven completed readings and no failed source
eligible for a fresh failure-to-Retry test. The actual FastAPI/Chromium Retry
journey passed locally, but a new Retry of Alex's failed client records on this
release remains unverified. Do not manufacture a failure or reprocess a client
file solely to demonstrate the control.

Remaining live evidence: confirm Alex's failed-file Retry result and representative
large-review save latency after the update. The successful test-case save is not
a measurement proving that all previously reported 20–25 minute delays are gone.
These post-release acceptance notes are local documentation; no additional
service restart is warranted just to publish verification notes.
