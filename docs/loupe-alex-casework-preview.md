# Alex's first case-work preview

The first handoff is **start and resume a financial case with manual PDF review**.
It does not wait for automatic whole-statement extraction, transfer matching or
all analysis screens. It is a testing release, not financial completeness certification.

## What Alex should be able to do

1. Sign in with his own account and create a clearly labelled test case.
2. Open Financial → Open PDF readings. Upload a PDF and choose Prepare PDF for review.
3. Choose prepared PDF rows. Inspect the original page beside the stored cells,
   assign column meanings, and select actual transaction rows. Save the batch.
4. Open readings. Use Review next pending row, check values against the source,
   choose the account/currency and record a resolved or rejected reading with a reason.
5. Close the case and return. Open the saved batch and confirm the review counts
   and decisions remain. Use Show only rows awaiting review to continue.
6. When all intended rows from that PDF have been saved and reviewed, preview
   finalization. Optional statement dates/balances must cite the printed cells.
   Finalization seals further additions from this PDF in this case: do not finalize
   the first batch if more pages still need selection. Recorded reviews can remain
   saved while that work continues.
7. Inspect the ledger, correct a test reading with a reason, inspect its source
   and decision history, check statement balances and download the ledger snapshot.

Counts describe selected rows only. Resolved does not mean independently verified.
These manually finalized documentary rows remain P3 and outside verified totals.
An empty verified total does not mean the statement has no money movements.
Only recorded decisions survive closing the form; unsubmitted form edits and
statement-control preview drafts are not yet saved drafts.

## Handoff gates

- [x] Supplied real PDFs prepare locally without an AI provider.
- [x] Source selection, review, account setup and bounded finalization work.
- [x] Reviewed statement controls preserve original cells and expose a known discrepancy.
- [x] Ledger corrections preserve originals, reasons and source links.
- [x] Exact exports retain reviewed values and history; optional original files verified.
- [x] Review-progress counts and pending filter added; targeted tests cover refreshed decisions.
- [x] Reopen progress through the browser against the saved real-PDF case; 2 resolved readings remain, no financial writes.
- [ ] Resolve the five integration conflicts with the remote updates and rerun release checks.
- [ ] Confirm watched deployment branch and site URL, then release and check that site.
- [ ] Confirm Alex's account/case permissions and run one new upload on the server.

The existing local cases and PDFs are not automatically shipped by a Git push.
The server check must use an uploaded test document and the server's own case records.
Do not publish the local development login as Alex's server account.

## Feedback to collect

For each problem record the case, filename, PDF page, action, expected outcome,
actual outcome and whether a refresh changes it. Prioritise lost work, wrong values,
source mismatches, blocked review and confusing navigation over additional analysis
features during this first handoff.

## Work continuing after the handoff

Automatic transaction nomination and full-statement coverage; broader printed-control
rechecks; reviewed-ledger graph/counterparty projections; transfer matching and
money-flow views; remaining tracing and reporting features. These remain on the
full development checklist rather than disappearing from scope.
