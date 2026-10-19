# Ready statements: from the counter to a saved import

24 September 2026. Alex reports that clicking the ready-to-import count appears
to do nothing. The previous handler only set the file filter; a repeated click
had no visible result, and matching file cards did not expose their ready periods.

## Investigator journey

1. In Statements & accounts → Statement files, choose **Show … statement periods
   ready to import**. The control identifies itself as a filter and shows its
   selected state. It clears a stale filename search and focuses/scrolls to the
   ready-results heading, including on a repeated click. The dropdown also focuses
   its results while retaining any deliberately entered filename search.
2. The list shows how many periods and files match. Each processed PDF exposes
   its ready periods with holder, bank/account, currency, dates, payment count
   and retained checks. Long collections show five periods at a time with next
   and previous controls. Existing file selection and batch preparation remain
   available for reviewing multiple PDFs together.
3. **Review and import** opens that exact file and period, focuses the review,
   and shows the existing source comparison and confirmation controls. Merely
   opening the list or selecting a period does not import, process or overwrite
   evidence. Read-only investigators receive **Review statement** instead.
4. Import through the existing explicit confirmation. The saved receipt and
   persisted transactions remain the authority. Returning to the file list keeps
   the ready filter; refreshed status removes the saved period from the available
   set while retaining other periods from the same PDF. Leaving an unimported
   review through **All files & imports** also returns to the filtered list.
5. Failed status requests display **Retry import status**. A deployment temporarily
   serving only the older count response retains a working file-review action.
   Existing missing-reading, stale-revision and saved-review recovery stay in the
   statement review workflow.

## Shared implementation and protections

The file-status service returns ready-period destinations from the same latest,
case-scoped, importable batch snapshots used for its counts. Already saved source
scopes, pending imports, skipped items and removed batches are not offered as new
ready imports. Reading-history grouping forwards the current reading's ready
periods. The primary ready count excludes files removed from Financial.

The broader regression run also exposed a stale removal preview: a session could
retain pre-worker Evidence metadata while confirmation refreshed it. Preview and
confirmation now both read current persisted objects before calculating their
revision. Concurrent-change checks, active-worker protection and source retention
remain in place; no client records were removed to demonstrate this correction.

## Acceptance evidence

- 94 backend tests plus four subtests pass across file status, batches and removal,
  including exact ready destinations, duplicate snapshots, existing imports,
  case boundaries and stale/concurrent removal protection.
- 21 UI tests pass, including repeated clicks/focus, stale filename searches,
  direct period selection, older-server fallback, pagination and read-only access.
- All eight real-service Chromium persistence journeys pass. The new journey
  prepares a synthetic multi-account collection, clicks the ready counter, opens
  and imports one period, independently reads the stored payments, confirms that
  only that period disappears from the ready list, then reopens/returns to another
  period. It checks 1360 × 900 and 390 × 844 viewports. Screenshots were inspected
  outside Git. Only authentication and the source canvas are substituted in
  this disposable harness; production Financial routes and database writes run.
- Scoped frontend lint, production build and regenerated workflow inventory are
  recorded with this release. No source PDFs, client screenshots or case exports
  are part of the commit.

Push triggers the user's automatic deployment. Independent live verification
remains restricted by the previously recorded live-origin authorization denial;
this local acceptance does not claim that the live incident has been reproduced
against Alex's case or that the earlier requested content cleanup has run.
