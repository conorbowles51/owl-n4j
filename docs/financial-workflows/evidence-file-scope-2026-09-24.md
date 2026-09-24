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
