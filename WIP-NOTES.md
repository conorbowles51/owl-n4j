# r5-alex-feedback — investigator feedback round 2 (E33–E37)

Branch `fin/r5-alex-feedback`, based on `fin/alex-1009` (which already contains the alex-1009
work: shared import button, clickable incomplete-records list, honest card counts, individual
admission of held rows). No separate merge was needed. Not pushed, not deployed, nothing written
live. All live numbers below come from read-only transactions (`SET TRANSACTION READ ONLY` plus a
flush guard) on the largest case (49494305), using this branch's code; "before" uses an archive
of the branch start (e7860616).

## Commits

| Commit | Items |
|---|---|
| cfc38b5c | A (Needs action view), B (fast status, adaptive polling), C (honest counts, empty-reading reasons) |
| df0828f9 | E (bulk account details: fast listing, reachable without ticking, works for empty readings) |
| c8d1d5f9 | F (each incomplete record names its statement period) |
| cf8661c6 | D (account type after import, flagged rows, confirmed flip, card suggestion, same-card merge) |
| (this file) | notes |

A, B and C share one commit because the card-state helper, the status payload and the filter
row change together.

## A. "Needs action" is the default view

- `frontend_v2/src/features/financial/lib/statement-file-state.ts`: `statementFileCard()` is the
  one source of a PDF card's state: label, tone, `notImported`, `needsAction`. The filter, the
  "Not imported: N" count and the card text all read it, so they cannot disagree.
- `StatementFilesPanel.tsx`:
  - the register opens on "Needs action": not imported (read, nothing saved), empty or failed
    readings, files with incomplete records, checks or periods available to import, and copies
    of a PDF saved elsewhere;
  - the statement viewer's side list (no filter control) keeps listing every file;
  - filter buttons sit in a "Filter the list" group that says they read and save nothing:
    Needs action (N), Not imported (N), ready, checks, imports in progress, duplicates, all;
  - the batch check, which does start work, moved to its own "Start a batch check" box. Its
    button now reads "Start batch check of N read files".
- Test: clicking every filter makes no request.

## B. Status endpoint and polling

Measured on the largest case (read-only):

| | Time |
|---|---|
| Before | 32.7 s and 36.0 s (two runs) |
| After, cold (first call in a process, or after any change) | 3.1–4.0 s |
| After, unchanged since the last call | 0.05 s (fingerprint query 0.075 s on its own) |

The response is byte-identical to the old code on that case (empty-reading field aside).

What changed:
- The register loaded every saved source document in full twice. Each one carries its whole
  reading (about 85 MB of JSON on this case). It now selects only the columns it shows.
- The coverage comparison joined the evidence row to every prepared period. One PDF's metadata
  was therefore decoded about 2,400 times. Each evidence row is now loaded once.
- The prepared-period read and the duplicate fingerprints are shared with the coverage
  comparison.
- Periods with no date in common skip the printed-reference comparison.
- The result is cached per case behind a fingerprint of every row the computation reads.
  - The fingerprint uses PostgreSQL `xmin` (row versions) from periods, sources, accounts,
    transactions, evidence files, batches, batch items, texts, geometry and workspace
    entries/links.
  - Any insert, update or delete changes it, including a long transaction that commits late.
  - SQLite (the tests) is never cached.
- Frontend: the status query polls every 30 s when nothing is reading or importing, and every
  5 s otherwise (`statusPollInterval`). TanStack Query does not overlap interval fetches.

## C. Honest counts

- "pending" is now "imports in progress", both on the filter and on the card line.
- "Not imported: N" counts the cards whose own text is a not-imported state.
- An empty reading (no rows, records, dates or balances in any current reading, and nothing
  saved) is labelled on the backend as `empty_reading` with a reason taken from the page text
  origins:
  - every page recognised from images: "Nothing could be read: scanned image, needs visual
    reading";
  - a usable text layer that produced nothing: "Nothing could be read: layout not supported
    yet";
  - no readable pages: "Reading found no statement".
- Live counts (read-only): 108 PDF cards are in a not-imported state:
  - 79 scanned images;
  - 15 with an unsupported layout;
  - 9 read but not imported;
  - 5 ready to save.

  The other cards: 6 imported and 3 with incomplete records.
- How the "count equals cards" check was done: in the UI, by a unit test that counts rendered
  `data-not-imported` badges against the button. For the live count, by re-applying the same
  rules in a read-only script.

## D. Account type (credit card / bank account)

Backend: `services/financial/account_type_change.py`, with routes under
`/api/financial/statement-import/`:
- `account-types`
- `accounts/{id}/type` (GET)
- `accounts/{id}/type/preview`
- `accounts/{id}/type` (POST, needs edit access)
- `accounts/{id}/type/flip-rows` (needs edit access)

Changing the type does the following:
- Each saved statement of the account gets `statement_convention_review` in its source metadata.
  - It records the new convention, the previous one, the actor, the time and the reason, with
    history, and is checked by digest.
  - The sealed reading, the import request and the import controls are not touched.
- One accessor, `effective_convention()` in `statement_details.py`, is now used by the details
  view, saved admission, import controls output, currency edit, recovery additions and account
  history.
- Period opening/closing and running balances are re-signed; the printed values are unchanged.
- Each period is reconciled again and its saved assessment refreshed. No PDF is read again; a
  test refuses any read.
- The account keeps `account_type_history` (before, after, actor, reason).
- A stale revision changes nothing.

Rows entered under the wrong convention:
- Flagged rows are the rows the investigator chose a direction for while the previous type
  applied: rows added in review, completed incomplete records, corrected rows, and rows whose
  direction was changed in review.
- They are flagged, never flipped by the type change.
- `flip_flagged_rows` flips exactly the rows currently flagged on one statement, through the
  normal correction chain: the original is superseded and an adjudication is recorded with a
  reason.
- Rows already flipped, and rows entered after the change, are never flagged again, so a double
  flip cannot happen (tested).

Detectors (read-only):
- Card suggestion: an account recorded as not a card whose statements' own pages print at least
  2 of "new balance", "minimum payment due", "credit limit", "payment due date" is suggested as
  a credit card.
- Same-card merge offer:
  - Accounts printing the same Luhn-valid full card number, with the same bank name once product
    words ("card", "credit") are ignored, are offered for the existing reversible merge.
  - `preview_consolidation` now accepts that case. Different numbers or different banks are
    still refused (tested).

UI:
- Shared `AccountTypeEditor`. It shows the current type and the suggestion with its printed
  signals, and lets the investigator choose a type, see a preview (statements, whether each adds
  up after the change, flagged rows) and confirm.
- Flagged rows are listed per statement (date, description, amount, money in/out → proposed)
  with a "Flip N rows" button.
- Where it appears:
  - single Edit account details (`ImportedStatementDetails`);
  - the bulk dialog, for the accounts of selected imported statements (drafts are told the type
    is set after import);
  - Review accounts, through `AccountTypeReview`, which also shows same-card groups with
    "Merge into one account".

Read-only dry run on the largest case (the acceptance case):

| Check | Result |
|---|---|
| Accounts | 10 |
| Suggested as credit card | 2: the two untyped same-card accounts, 4 printed signals each |
| Same-card groups | 1 (those two) |
| Merge preview | accepted (2 accounts, 6 payments) |
| Switch to credit card | flags 4 + 2 = 6 rows |
| Each statement after the switch | does not add up as-is; adds up exactly with its flagged rows flipped |
| Each statement today | adds up (as the investigator reconciled it) |
| False same-card groups | none other |

## E. Bulk Edit account details

- Entry point:
  - with nothing ticked, the button covers the files the current filter shows (up to 50):
    "Edit account details of N shown files";
  - otherwise the help text says to tick files or narrow the list to 50 or fewer.
- Listing speed. Each reading used to re-query or recompute the following for every statement;
  each is now done once per request (per PDF):
  - the geometry page list;
  - the printed header parse;
  - the evidence row (identity map);
  - the saved sources of the same PDF. This one applies only on a read-only listing, which marks
    its request cache with `READ_ONLY_LISTING`; save paths never set the mark.

  In addition:
  - the first reading of each unsaved statement is reused by `_load`;
  - the duplicate verdict is no longer built to list or preview. Save attaches it to the draft
    rows it writes, with a shared cache, so an ignored copy still saves as ignored (tested).
- Listings are identical before and after on all three measured folders (read-only, live):

  | Folder | Before | After |
  |---|---|---|
  | 16 files | 6.21 s | 3.89 s |
  | 5 PDFs, 264 unsaved periods | 249.4 s | 46.1 s |
  | 5 PDFs, 232 saved periods | 389.8 s (1.3 GB RSS) | 111.4 s |

  The UI gives up at 300 s.
- Empty readings: in the 16-file folder, all 14 empty readings list as editable rows. A preview
  that sets holder and currency on all 14 updates 14 rows (3.7 s).

## F. Incomplete records name their period

- `GET /incomplete-records` returns `period_start` / `period_end` per record. It uses the saved
  period, else the dates on the saved review, else null.
- The list and the record view show "statement <start> to <end>", or "statement period dates
  not read", beside the file, page and missing field.
- Live: 142 open records. 10 have a period; 132 have period dates not read, all on the
  card-statement file named in the feedback (132 of its 138).

## Tests run

- Backend checkpoint (`pytest tests -k "financial or bulk_statement or saved_statement"`,
  `CHROMADB_PORT=1`): 6417 passed, 43 skipped, 16 failed.
  - All 16 failures also fail on the unmodified base: 9 in deployment_recovery, 3 in
    recovery_followup, 2 in recovery_preparation and 2 in unassigned_statement. They are
    DetachedInstanceError, or 'attention' != 'ready'.
  - The 4 in recovery_preparation and unassigned_statement were re-run on a base archive: same
    failures.
- New or extended backend tests:
  - `test_financial_account_type_change.py` (11);
  - `test_financial_statement_file_status.py` (+4: empty readings, cache);
  - `test_bulk_statement_details.py` (+2);
  - `test_financial_optional_import_review.py` (+period assertion);
  - export surface: `account_type_change`, plus `held_record_admission`. The latter was
    unexported, which already failed `test_financial_exports` on the base.
- Frontend:
  - vitest unit: 10 files, 109 tests, all passing. New: `statement-file-state.test.ts`,
    `AccountTypeEditor.test.tsx`, and panel/records tests.
  - Browser tests: BulkStatementDetails, ImportedStatementDetails, StatementClarity,
    DuplicateRegister, FinancialFileMembership, FinancialSourceAudit, ResumableUploadGroups,
    FinancialBatchNavigation and ReconciliationJourney pass.
  - StatementRequestLoad "measures connected review requests" fails identically on the base.
- `tsc -b`: the same 4 errors as the base, all in test files I did not change (verified on a
  base copy). eslint on the changed files is clean.
- Synthetic benchmark: 105 of 125 ready, 0 wrongly admitted, exit 0, identical to real-wave4.
  - Engine readings were reused with `--readings` from real-wave4, because the changes are
    backend-only.
  - Run: `bench-runs/r5-alex-feedback-final`.
- Real-statement benchmark: not run. It takes about 13 h and integrate-4 is running it on this
  machine.
  - The reader changes here are caching only; live bulk listings were byte-identical before and
    after.

## Open / for Neil

1. **Automatic flip.** Should a flagged row flip automatically when flipping all flagged rows
   makes the statement add up exactly, as it does on both live statements? The current default
   is flag plus one-click confirm.
2. The bulk listing for large saved PDFs is still 46–111 s. What remains is re-reading each PDF's
   statements once (statement engine catalogue). The next step would be to list from stored
   batch snapshots and saved details and re-read only on preview. That needs a decision on
   stale snapshots.
3. Account type applies to imported statements. Drafts take their convention from the reading.
   Carrying a type override into a not-yet-imported review would change the import request
   contract.
4. The finalization-receipt path (`ledger_source` reviewed scopes from bulk finalization) keeps
   the convention of its own receipt. A type change does not rewrite those receipts.
5. The cold status read is about 3 s on the largest case, above the 2 s target. Every later
   unchanged poll costs 0.05 s.
