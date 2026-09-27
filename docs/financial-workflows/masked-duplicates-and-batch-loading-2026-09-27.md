# Masked duplicate copies and batch reopening

27 September 2026. This is one implementation checkpoint in the whole financial journey, not completion of the import or investigation acceptance.

## Investigator journey

Upload independent copies, prepare their account periods, see one retained period and the excluded duplicate, import once, and reopen either original. Investigator corrections must return a changed copy to review. Reopening a large batch must not reconstruct every unchanged ignored statement merely to count its status.

## Changes

- Identical source hashes can establish masked-account copies only when account/holder/currency/period scope, usable financial readings and source sections also agree. Shared masked digits alone never establish duplication. Original files and conflicting edits remain available.
- Retained-source selection prefers an already verified retained peer; tied file timestamps and UUID order cannot nominate a second retained copy during sequential preparation.
- Batch and coverage projections share a request-local bulk freshness context already used by file status. Unchanged ignored decisions avoid PDF reconstruction. Changes to readings, geometry, draft reviews or retained evidence invalidate the shortcut. Import admission remains separately checked.

## Verification

43 focused backend tests passed: statement overlaps, pending duplicate decisions, batch read projections, duplicate file status and read-only duplicate queries. Added regression cases exercise masked identical/nonidentical sources, import-once ledger counts, preservation of both PDFs, changed edits, distinct source sections and reopening without statement reconstruction. `git diff --check` passed.

A broader run could not execute router-dependent tests because the local environment lacks `langchain_core`; this is not a passing full-suite result. No frontend controls changed in this checkpoint. Live performance, existing-batch reclassification and the complete browser journey remain unverified until deployment.

## Remaining acceptance

Repeat preparation/check against retained readings for the existing affected batch without re-uploading, verify one contribution per duplicate period, and verify large-batch reopening with measured response time. Diagnose preparation failures independently; the optimization is not yet proven to resolve the observed live timeout. Complete unresolved source checks and source-linked coverage, flow, large-transfer and unusual-activity findings. Continue E01–E18 and U01–U07 in the error register.

## Preparation conflict recovery

Server diagnostics subsequently confirmed PostgreSQL deadlock (`40P01`) in the audit trigger while updating a prepared file's metadata. The reading was retained; the prior worker converted this transient database conflict directly into a terminal preparation error.

The worker now retries deadlock/serialization failures on up to three subsequent bounded turns, without restarting the PDF reader. Persistent conflicts end with a specific recoverable message. Explicit Retry resets this retry budget. Ordinary validation errors remain visible and are not retried as database contention. Batch cards now accurately describe reading **or preparation** recovery instead of claiming every failed preparation was an unreadable PDF.

Verification: three new recovery tests plus the duplicate/projection tests pass together (25 tests); 28 batch UI tests and 13 Chromium navigation/recovery tests pass, including 1280px and 390px journeys. Browser tests initially required permission for their local listening port; they then completed successfully. Live recovery and release remain unverified. This handles transient conflicts; it does not claim to eliminate all audit lock-order contention.

## Upload observation from another tab

E03's interruption label was inferred solely from the absence of local file handles. Another tab or device does not share those handles, so it could label a still-running upload interrupted. Both single-file and selection cards now explain that the original upload tab must be checked before resuming; they do not assert that an upload is stopped. Server-reported paused state and resumable recovery remain available.

Chromium coverage observes increasing server progress and disappearance after completion without reselecting or issuing writes, for both single files and selections at a narrow viewport. Existing pause, reopen, changed-byte rejection and lost-acknowledgement recovery journeys are retained. This corrects misleading interruption advice; it does not establish cross-device ownership or repair a genuinely stale server upload record. Live acceptance remains pending deployment.
