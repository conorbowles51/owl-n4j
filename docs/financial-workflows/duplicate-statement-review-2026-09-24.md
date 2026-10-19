# Repeated statement reviews and duplicate import decisions

24 September 2026. Applies to existing and future statement reviews in every
case. This is a shared service and investigator workflow repair; it is not a
change to a client's evidence or transaction data.

## Investigator objective and observed failure

Alex reports being asked to review a system-generated copy repeatedly. The
screenshot shows an overlapping statement awaiting import and an enabled import
button. That screenshot cannot establish the files' provenance or whether either
statement has contributed duplicate payments.

Code inspection confirmed that coverage warnings did not prevent even strongly
matching statements from being imported, a fresh preparation request could make
another batch for an unchanged selection, and stale internal reading versions
could remain in the competing-review list. These mechanisms are repaired below;
the precise history of the reported live statement has not been inspected.

## Connected journey

1. **Statement files → Prepare statements.** Preparing the same current file
   selection resumes its existing batch, retaining paused work, saved corrections,
   decisions and receipts. Case-level locking prevents simultaneous requests from
   making parallel preparations for that unchanged selection. An explicit new
   reading has a new version ID and may prepare a new review.
2. **Processing batches → Possible duplicate statements.** A separate source
   with matching bank, full account reference, holder, currency, account type and
   exact period is held out of individual and bulk import until a comparison
   decision is recorded. The batch groups these matches separately from ordinary
   date overlaps. File-register readiness uses the same hold, so a held statement
   is not advertised as ready to import.
3. **Review → Compare original PDF.** The comparison identifies the other source,
   dates and whether it is awaiting import or already imported. Open its original
   and return to the current review without losing edits. Exact metadata is a
   reason to compare: a revised statement may contain additional records.
4. **Copy → Leave unimported.** Return to the batch, choose this action on the
   extra statement and record the reason. The other retained statement becomes
   available if it has no other import blockers. The excluded copy is labelled
   **Left unimported**, retains its source and corrections, and can be restored
   to review. A single-file review can also be closed without importing it; a
   durable leave-unimported choice is made in its batch.
5. **Both sources needed → record why.** Select the comparison acknowledgement
   and enter a reason. The review shows **comparison recorded** and allows the
   otherwise valid import. This intentionally allows a reviewed exception; it
   does not claim that every repeated payment in two different sources is unique.
   Changing the relevant account, period, reading or comparison set invalidates
   a stale decision. Another statement being imported does not itself invalidate
   a comparison already made against that same source and period.
6. **Import → saved result → reopen.** The server enforces the hold inside the
   existing case transaction lock. Existing idempotent receipts still return the
   original result. Reopening or preparing the same selection returns to the
   existing work with its retained choice and one saved payment set.

## Identity, existing data and boundaries

- Bank/account/holder alone cannot identify a monthly statement: complete start
  and end dates are necessary. Currency and account type keep separate products
  distinct. A statement number is not required by this safeguard and is not
  currently an additional matching key.
- Bank/account use the existing identity normalisation; holder comparison ignores
  case and whitespace. This does not infer ownership from similar names or treat
  an account suffix as a full identifier. Missing identities, masked references,
  partial date overlaps or different currencies/products do not become proven
  duplicates. Existing ordinary overlap warnings remain available.
- Only case-scoped, explicitly linked versions with matching source hashes are
  treated as internal readings. Unverified lineage metadata cannot hide a separate
  file. Old versions remain in history but do not become competing pending
  statements. A changed reader section key cannot make an otherwise identical
  source/account/period appear to be a separate competing PDF.
- Older batch summaries recover missing bank/product fields from their retained
  reading without overwriting investigator corrections. Removed batches do not
  contribute pending comparison candidates.
- These rules are evaluated when existing work is opened; no database migration,
  bulk reprocessing or deletion is required. Already imported potential duplicates
  are not silently removed. Existing copies and their provenance still require a
  record-specific audit before any correction to client totals.
- A new source must be read far enough to establish its contents and account/
  period before metadata matching is possible. The rule does not reject an
  unread document by name or extension. Financial membership remains based on
  content and the investigator's selection.

## Verification and release

Synthetic tests exercise the production services and a disposable database:

- Backend checks cover matching imports held before writes, current comparison
  exceptions, unchanged request receipts, partial overlaps, holder/masked-account/
  currency/product boundaries, case isolation, invalid lineage, changed reader
  keys, old reading history, batch reuse, skip/restore with corrections retained,
  old summaries and accurate file readiness. Existing import/batch suites and
  ingestion-release gates are included.
- The statement-review component suite tests exact matches held until a reason
  is recorded and partial overlaps remaining importable.
- Chromium runs the actual FastAPI routes and SQL writers. The new journey holds
  an individual import, resolves a two-source batch by leaving one unimported,
  imports the other, independently reads back the saved payment IDs, repeats the
  selection and reopens the retained decision. Existing ready-period, mixed-bank/
  card, correction, recovery, file-selection and retry journeys run alongside it.
  Authentication and the PDF canvas are synthetic; business APIs are not mocked.
- Wide (1360 × 900) and narrow (420 × 900) views are inspected. The narrow result
  retains the reason and Restore action without horizontal overflow. Visual
  inspection caught and repaired a stale "Available to import" label on skipped
  statements.

Final local results: 148 backend tests and eight subtests pass; five additional
legacy/group checks pass (one repeats an earlier test with the final legacy
fixture). All 51 statement-review component tests and nine real-service Chromium
journeys pass. Scoped ESLint, production build, whitespace checks and regenerated
action inventory pass (1,667 actions across 173 components). Existing dependency
deprecations, React test act warnings and bundle-size warnings are unchanged.

Test images, source documents and extracted client data remain outside Git. This change does
not alter workers, leases, queue configuration or accepted import operations.
The existing deployment gate defers service changes while ingestions/imports are
active; it is not bypassed. Push triggers the user's automatic deployment.

Independent live verification and the exact reported incident remain unverified:
automatic approval review previously rejected access to the production origin.
No alternate route is used to bypass that restriction. Publication is not a claim
that a record-specific live cleanup has occurred.
