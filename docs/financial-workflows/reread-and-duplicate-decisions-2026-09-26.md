# Re-read import and separate duplicate review — 26 September 2026

## Investigator journey

Open a re-read statement from its file or batch, compare its payments and
printed controls, choose to replace the earlier import, then confirm once.
Correct payments do not need individual acknowledgements. Earlier evidence,
records and corrections remain in history. A failed save leaves the review
available for retry; confirmation is still bound to the current source revision.

Open Statements & accounts to continue normal work. Files whose known prepared
periods are all duplicate holds or ignored copies appear under Review duplicates;
mixed files stay in the normal list. Processing batches start with unfinished
nonduplicate statements. Possible duplicates have their own count and section,
alongside retained ignored copies. All files and all batch statements remain
explicitly accessible.

For a matching separate statement, choose Don’t import this duplicate directly
in its review. This records the investigator's reversible decision without
deleting evidence, corrections or existing payments. Restore for comparison
returns it to review; importing both remains a separate explicit decision.

## Implementation

- Re-read replacement is a visible choice at the beginning of the review.
  Batch context no longer disables editing merely because an earlier reading
  was imported. Only the current imported reading uses the saved-detail editor.
  Go to field targets the replacement control directly.
- Selecting replacement of an empty import supplies a recovery note. Existing
  nonempty replacements retain their explicit reason. Currency conflicts,
  missing values and reconciliation remain checked.
- Manual duplicate exclusion uses the existing case/evidence locks, source
  revision, decision history and projection checks. The backend verifies a
  matching separate statement and rejects exclusion of an already imported
  statement through this action. Changed reading/review invalidates the decision.
- Batch counts partition possible duplicates from unfinished work, and default
  navigation skips duplicate holds. Explicit filters retain access to them.

## Validation and limits

Targeted backend, UI and Chromium checks cover replacement from a batch without
row edits, manual duplicate exclusion/restore, import suppression, retained
evidence, mixed-file visibility and scoped navigation. Final test counts and
publication are recorded at release. Private evidence and test captures remain
outside Git. Authenticated read-only inspection is now available; local browser tests alone
do not establish that every live case is repaired.

Final local verification: 34 backend checks, 90 UI unit checks and 22 Chromium
journeys passed. Production build and targeted ESLint passed; Vite retains its
large-chunk advisory. The replacement screenshot was inspected after removing
the inappropriate old-import detail editor. The action inventory is regenerated.
Publication uses the existing automatic deployment trigger and its ingestion
idle gates; no live worker or job is restarted manually.

The earlier publication block is superseded: on 26 September the user explicitly
authorized committing and pushing these exact code-only import, re-read,
duplicate, progress, retry and amount-reading fixes. Client documents, financial
data and credentials remain excluded.

## Later feedback: removed-source retry dead end

The later batch screenshot shows eight file errors before any reviews are
prepared. The exact error is the removal restart-reference validation, not an
OCR or statement reconciliation failure. Live availability of the source bytes
has not been established.

For that failure, Check source again now exposes Read this retained PDF afresh
when the selected case-owned source remains eligible. The explicit action queues
one durable attempt, verifies the source revision and PDF bytes, and creates a
new reading version. It never follows a foreign/missing restart pointer or
rewrites the prior removal. Old reviews remain in history. Repeated requests
reuse the queued attempt. A changed/missing PDF remains an actionable error;
Find source in Evidence remains the recovery route. Batch status and reading
receipts persist across reopening.

Failed/unread files are now visible as outstanding work beside prepared review
counts. Zero prepared reviews is explicitly distinguished from a finished
batch. Imported statement navigation says Original extraction flag, separating
historical extraction warnings from current saved-record corrections.

Local validation of this extension: 150 backend checks passed across reading
retry, restored recovery scope and batch processing; the strengthened 44-check
retry suite passed again. 13 Chromium batch journeys and the production build
passed. Recovery screenshots use synthetic data and stay outside Git. Targeted
ESLint passed. Live records have not been retried or changed. This extension is included in the subsequently authorized code-only release.

Additional local acceptance: 65 UI checks passed, followed by a focused imported
malformed-amount navigation check. The recovery action and queued receipt were
captured and visually inspected in Chromium; the focused action journey passed
again after adding wrapping for its controls. No files are staged.

## Final connected verification

Read-only live inspection confirmed saved payments for the reported re-read and
correct account/currency separation in the multi-currency review. It also
reproduced grouping-comma whitespace in retained amount text; the exact parser
now handles that spacing without changing digits or accepting malformed amounts.
Imported incomplete-total warnings now identify historical extraction totals.

Empty/error-only batch status no longer reconstructs unrelated legacy statement
comparisons. Batch cards explicitly distinguish prepared unfinished reviews from
files still needing reading or preparation. See the
[throughput audit](import-throughput-audit-2026-09-26.md) for the remaining limits.

No live source recovery, replacement, duplicate decision or ledger write was
performed. Those mutating paths have isolated backend and Chromium journey
coverage; the release must not label them live-written acceptance.

Final release checks: 173 targeted backend tests, 108 UI unit tests and 22
Chromium journeys pass. The production build and scoped ESLint pass. Existing
Vite large-chunk and Python deprecation advisories remain. Action inventories
were regenerated. Automatic deployment and read-only live verification follow
the authorized code-only push.
