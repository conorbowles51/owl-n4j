# Core financial release estimate — 9 September 2026

This estimate supersedes the earlier unsupported calendar dates. It covers Alex's
core statement → reviewed ledger → balance checks → corrections → report release.
It is an engineering estimate, not measured future execution time or a guaranteed date.

## Acceptance boundary

Alex can create a case on the server, upload a supported statement, work through
its transaction rows, save/resume review, see explicitly labelled working totals,
inspect statement discrepancies, correct a reading and export matching values and
source/decision history. Unreviewed or unsupported pages remain visible as gaps.
Verified totals retain their current eligibility rules; a working reviewed total
must not silently promote incomplete documentary readings. No automatic processing
of arbitrary bank layouts is promised by this core release.

## Evidence checked

- Current HEAD 59e56a2d. Source selection, saved review, bounded finalization,
  statement controls, correction/source history and exports are implemented.
- Real-PDF acceptance currently covers two selected transactions, a separate
  deliberately omitted-interest discrepancy, and an audited correction. It does
  not establish complete-statement or whole-PDF accuracy.
- candidate_materialization.py caps finalization at 100 mappings / 1000 candidates
  per PDF and seals further additions after finalization. These limits must be
  checked against the intended case, not silently removed.
- ledger_summary.py excludes P3 from default totals. Existing real-PDF samples
  therefore have zero included rows. Usable reviewed-working totals need an explicit
  separate population and matching report treatment; weakening verification rules
  is not a shortcut.
- Row/header suggestion aids exist; source selection and individual review remain
  investigator-driven. Statement-control preview drafts are not persistent.
- Production frontend build passed before the latest small progress change.
- Remote f76524e contains four updates with five conflicting files, including
  processing guards versus evidence navigation changes. Integration requires tests,
  not merely accepting one side of those conflicts.
- Deploy script rebuilds frontend/engine and runs migrations. Server branch, URL,
  configuration and Alex's access are not yet confirmed. Local fixtures do not ship
  in a Git push.

## Remaining critical path: estimated active hours

| Work | Estimate | Exit evidence |
| --- | ---: | --- |
| Integrate remote changes, resolve conflicts and build/test combined code | 3–5 | Combined branch passes build and affected evidence/financial tests |
| Complete-statement review acceptance, page/row completeness visibility and workflow fixes for supplied layouts | 5–8 | Full statement compared with source, missing pages/rows explicit, resume verified |
| Explicit reviewed-working totals and matching readable export, retaining separate verified totals | 5–8 | Exact totals reconcile to selected current rows; superseded/excluded readings handled; export agrees |
| Deploy, migrations, ordinary-user permissions and fresh server upload-to-report test | 3–5 | Alex can access his own case and complete server workflow |
| Defect allowance across the integrated journey | 4–6 | No known blocker to the defined workflow |
| Total | 20–32 | Core release gates met |

Planning target: approximately three working days of sustained development;
allow a fourth if integration or document acceptance exposes defects. A narrower
manual-review preview may be deployable in 4–8 active hours, but is not this release.
Calendar delivery depends on server details and sustained execution; no scheduler
has been reactivated and this document does not start background work.

Confidence: moderate for the estimate's lower-complexity items, lower for complete
statement acceptance. Re-estimate after integrating and completing one full statement;
report any changed scope or blocker rather than moving the date silently.

## Outside this accelerated release, still retained in the full backlog

Automatic extraction across arbitrary institutions/scans; advanced transfer matching
and internal-flow accounting; all reviewed-ledger graph/analysis projections; complete
multi-account funds tracing and method comparison; the remaining analytical UI.
This core release must not be described to Alex as the entire agreed financial scope.
