# Evidence uploads and the Financial library

Reported 24 September: ordinary, unprocessed Evidence PDFs appeared in Financial.

Confirmed cause: the shared statement-file hook fetched all case Evidence and
filtered only by the `.pdf` suffix. Merely listing these files did not enqueue a
reading or import payments, but it presented ordinary documents as statements and
made them selectable for bulk financial work.

The Financial library now requests a case-scoped, server-filtered list. Files
belong there after explicit financial preparation/selection or existing saved
financial work. Compatibility covers queued and historical batches, imported
sources (including balance-only/incomplete records), manual candidate reviews,
saved drafts, payment-document reviews and verified internal reading versions.
Ordinary upload, ordinary AI processing, filename, text extraction and PDF table
geometry do not enrol a file. Independently uploaded equal hashes remain distinct.
Explicit preparation remains recorded even if a later ordinary AI run replaces
the latest processing snapshot.

Investigator journey: upload to Evidence → remain in Evidence → open Financial
without seeing the ordinary PDF → Choose from Evidence → select/review/send the
intended PDF → see that file in Financial → leave/reopen with the same scope.
Financial's empty state explains how to add files. Shared upload activity is
labelled as case-wide Evidence activity, separately from the Financial file list.
If reading never started after upload, Choose from Evidence uses the retained PDF.

Existing accidental list entries with no financial intent disappear on the next
corrected listing. No evidence, source bytes, jobs, saved reviews, payments or
history are deleted. Files explicitly selected earlier are retained; this patch
does not guess whether an investigator's prior selection was a mistake.

Local verification:

- 126 backend tests and four subtests: ordinary/unprocessed/AI-processed exclusion,
  unchanged Evidence, explicit batch selection before workers, existing imports,
  saved drafts, preparation persistence, remove/restore, same-hash independence,
  case boundaries, existing intake/retry and route authorization.
- 148 frontend tests, TypeScript/production build and scoped ESLint pass.
- Real Chromium and disposable SQL/FastAPI: ordinary files remain in Evidence;
  the explicit picker sends one PDF; reopening preserves the list; source ids and
  job states are unchanged. The existing review → import → correction → reopen →
  second bulk correction journey also passes through the same real service.

No database migration, live case mutation, source-document publication or worker
restart is required. Push uses the user's automatic deployment. Independent live
verification is separate; the previously blocked signed-in origin has not been
accessed through an alternative tool.

## Format correction, 24 September

The user clarified that Financial is determined by content, including CSV, Excel,
Word, images and other formats. The earlier PDF-only membership projection was
therefore too restrictive. The operating rule is now recorded in `AGENTS.md`.

The library now retains financial sources regardless of extension, including
existing native bank imports. The Evidence picker previews all selected formats,
lets the investigator remove unrelated items, and separates the resulting work:

- PDFs continue through the existing statement-preparation batch.
- Other formats are included as financial sources, without starting a job or
  importing transactions. Their cards show Evidence processing status, open the
  original in Evidence, and provide a direct return to Financial. They do not
  appear in the PDF statement selector or PDF bulk-processing controls.
- Sources can be removed and restored with the original evidence retained.
  Membership is case scoped, audited and idempotent. A stale preview cannot
  silently restore a file another investigator has removed. Existing imported
  ledger records remain protected by the removal guard.

Source selection is an investigator decision about relevance, not automatic
validation of every amount as a transaction. Ordinary upload, a filename,
processing status, or an extension does not establish financial content. No
ordinary Evidence files are automatically added by this change.

Reader limits remain explicit: the existing Evidence pipeline reads CSV, XLSX,
DOCX and images. Legacy XLS and DOC currently require conversion to a supported
format; their originals can still be selected and retained as financial sources.
This change does not add universal structured transaction import or automatic
content classification to every reader. Native bank import and PDF statement
review keep their existing admission and confirmation steps.

Local acceptance uses synthetic files only. It exercises selection, mixed-format
routing, saved membership after reopening, remove/restore, stale selections and
case permissions. Independent live acceptance and source-extraction accuracy are
separate from this membership/navigation correction.

Verification for the format correction: 130 backend tests plus four subtests,
58 frontend tests, three real-service Chromium journeys, production build,
TypeScript and scoped ESLint passed. The browser journey covers CSV, XLSX, DOCX,
PNG and a legacy XLS source; the unit/service matrix also covers TSV, DOC, JPEG,
XML and an unfamiliar extension. No extraction accuracy claim is made from
membership fixtures. The source card was inspected at desktop and narrow widths.

Publication status: the format correction is complete and locally verified, but
remains uncommitted/unpushed. Automatic approval review rejected the commit twice,
stating that the earlier push instructions were not accepted as authorization for
this specific financial-code change. A fresh code-only commit/push confirmation
has been requested. No client documents or screenshots are staged. The earlier
PDF-list correction remains separately pushed as `7d548487`.

## Requested cleanup after the next deployment

The user authorized a one-time content and provenance review of all documents
currently in Financial, removing clearly non-financial sources or demonstrably
accidental system assignments from Financial. Any Evidence file may be selected
for Financial; the named formats are examples, not an allow-list.

The thread heartbeat `review-financial-after-next-deployment` is active, checking
every 15 minutes for a verified successful deployment after 24 September 2026
at 01:22 UTC. This schedules the follow-up; the live scan and removals have not
happened. A local commit or push is not accepted as deployment proof. The task
does not authorize deployment, service restarts or interruption of ingestion.

The pass must inventory every accessible Financial source across cases, starting
with BNB2, and inspect content together with selection/import provenance. Missing
transactions, unreadable content, a failed reader or an extension cannot justify
removal. Preserve genuine financial sources, including invoices, quotes, receipts
and balance-only statements. Leave uncertain, actively processed or protected
sources for review. Use reversible, audited file visibility changes, preserving
original Evidence and all saved transactions, accounts, findings, notes, links,
reviews and history. Respect later investigator edits and restores.

Keep the audit outside Git and report retained, removed, uncertain, protected and
inaccessible counts. Verify original Evidence remains after each removal. Pause
the heartbeat once the complete inventory is accounted for. Existing live-origin
access denials must be resolved through approval, never bypassed.

Later release update, 24 September: the user explicitly instructed “deploy when
this is ready”, authorizing publication of the connected code-only release.
The cleanup heartbeat is paused after the user reported its repeated no-progress
wakeups; the content/provenance audit remains required and unperformed. See the
[connected release record](next-release-2026-09-24.md) for current verification
and publication status. The independent live-origin access restriction remains.
