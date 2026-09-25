# Make a saved balance correction visible beside its original

## New report and boundaries

Alex reported an unexplained quoted text fragment in the extracted balance cell
and a replacement balance that appeared not to save. The screenshot shows an
original extracted row above an editable correction. It does not show a failed
save response or the reopened saved value. The statement filename and whether
the correction itself reverts have been requested; both remain needed to
attribute this specific report.

A synthetic reproduction confirms that standalone and batch review saves retain
numeric corrections of malformed original balance readings. A valid number that
disagrees with neighbouring balances saves successfully but remains blocked from
import. A source-accurate correction passes the same checks and is used for the
imported running balance. Original extracted cells remain source evidence.

The confirmed UI defect is that closing the editor leaves the retained original
prominent while hiding the corrected value and its save status. This makes the
interface appear to ignore a correction even when it was accepted.

## Investigator journey

1. Open the flagged row beside its original source and enter the reviewed balance.
2. See the retained original separately from the current reviewed balance.
3. Save all review progress directly from the editor, with wording that it saves
   all current statement details and corrections. Closing the editor is separate.
4. Keep the reviewed balance and row-specific saved/unsaved state visible after
   closing, moving focus or reopening the saved review.
5. Distinguish saved progress from current reconciliation. A remaining difference,
   pending check or failed check cannot be presented as reconciled.
6. Preserve newer edits while a save is pending or fails. A receipt for older
   values must not label newer values as saved. The original stays unchanged.

The implementation uses the existing persistence and admission contracts; it
does not rewrite source readings, infer missing balances or waive discrepancies.
Client records are not changed merely to demonstrate this behavior.

## Acceptance

Backend and browser checks cover malformed original cells, a wrong numeric
correction that saves but remains unreconciled, source-accurate correction,
server-backed reopening, ledger use of the reviewed balance and retained original
provenance. Separate UI checks exercise pending saves, subsequent edits, failed
responses, recovery, and compact/narrow layouts. Final results and publication
are recorded separately from the still-unidentified source-specific report.

Verified on 25 September before release:

- All 51 statement-progress backend tests pass, including standalone and batch
  malformed-balance save/reopen/import and repeat-import protection.
- All 75 connected UI unit tests pass, including both overlapping-save response
  orders, navigation preserving newer edits, transport-default normalization,
  malformed acknowledgments and invalid amount text.
- Chromium correction journeys pass at 1280px and 390px; screenshots were visually
  inspected. The previous printed-total journeys also pass at both widths.
- A separate Chromium journey against the real local FastAPI service and database
  saves an unreconciled numeric correction, clears browser drafts, reopens the
  server value, corrects it against a synthetic original and imports 12 payments
  exactly once. The original malformed reading remains retained.
- The production build, targeted lint and diff checks pass. Existing bundle-size
  and React test act warnings remain; neither indicates a failed assertion.

No client document or case record was used as a test fixture. The exact filename
and reopened-field behavior for Alex's report remain unconfirmed. Publication and
live verification are recorded separately; these local checks do not establish
that her particular save succeeded or that the unexplained text was a balance.
