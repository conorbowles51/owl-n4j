# Import throughput investigation — 26 September 2026

The renewed investigator report asks why so few source files have imported
payments, whether processing can be accelerated, and why a reviewed peso
statement points to dollar-denominated printed totals. This remains open;
the earlier navigation release does not establish acceptance of this incident.

## Confirmed locally

- The overview counts distinct evidence files with `current_transactions > 0`.
  It is not a transaction count, completed-review count, or queue-progress
  measure. A saved quiet period does not contribute to that payment-file count.
- Admission blocks an identified but unreadable printed credit/debit total even
  when the closing balance matches. A total absent from the source is optional.
  Correct source assignment must be established before changing this behaviour.
- Nine Kapital/Intercam tests pass, including separate currency sections,
  payment continuation before another currency section, and import/reopen.
  These synthetic results do not reproduce or resolve the reported source.

## Live access and remaining evidence

The user signed into the in-app browser and authorized read-only inspection.
Authenticated inspection distinguished queued extraction work, running readers,
prepared reviews and saved payments. Work is still queued and progressing;
no live job was paused, cancelled, retried or reconfigured. The payment-file
counter alone does not establish reader throughput. Private case counts,
identifiers, amounts and screenshots remain outside Git.

The affected multi-currency review now identifies the correct saved account and
currency. Existing saved payments and retained extraction readings have different
counts; the historical source flags must not be presented as unsaved work.

Opening an unread/error-only batch unnecessarily reconstructed unrelated legacy
statement comparisons. The status projection now returns immediately when there
are no prepared items. A regression check fails if comparison reconstruction is
called in that state. This speeds access to recovery controls; it does not change
OCR worker concurrency or claim to accelerate every PDF reading.

## Attached Intercam source follow-up

The investigator supplied an original PDF reported as yielding no transactions.
Local extraction using `read_tables`, catalog recognition and the bank reader
successfully separate its active peso account from its quiet dollar account.
The printed totals, closing balance and every running-balance interval match.
The full stored-geometry review and confirmation service also succeeds in an
isolated temporary test database, with no incomplete payments. This is a
fresh-read result, not a reproduction of the production failure. The private
PDF, extracted content and probe scripts remain outside the repository.

Authenticated live inspection subsequently confirmed that the affected active
account has saved payments and reconciled totals, with the quiet currency section
separate. This establishes its current saved state, not the cause of the original
empty reading. No live import was changed to demonstrate this.

## Amount-reading defect reproduced

Retained PDF text can insert horizontal whitespace beside a grouping comma.
The exact-amount parser now normalizes only that spacing before validating the
complete numeric grouping. Digits, separators and original source text are kept;
malformed grouping, multiple amounts and whitespace between digits remain invalid.
Synthetic regression coverage includes ordinary, nonbreaking and narrow spaces,
as well as rejection cases. Imported reviews describe incomplete original totals
as historical readings and lead to current saved payments.

## Release status

The user explicitly authorized committing and pushing these verified code-only
fixes on 26 September. Automatic deployment retains ingestion-idle checks.
Publication and deployed revision verification are recorded separately from local
validation. Original source material and live case observations are not fixtures.
