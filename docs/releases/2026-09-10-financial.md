# Financial casework release, 10 September 2026

Branch: integration/evidence-main-reunion. Application and user-guide commit:
22964457. This note describes committed work being pushed through the existing
server deployment process. It does not certify that deployment or server testing
has completed.

## Work included

- PDF preparation, source-linked row selection, page scans and optional model
  proposals feed a saved human review process. Investigators can resume batches,
  preserve unfinished statement controls and finalize explicitly reviewed scope.
- Current working ledger views, corrections and exclusion decisions retain
  original readings and reasons. Statement balances, printed controls and date
  coverage expose discrepancies, missing periods and unknown information.
- Documentary transactions, counterparties, trends and posting graphs use the
  reviewed ledger populations. Account and payment identity links record explicit
  investigator decisions without changing printed source names.
- Transfer comparisons, account-group perspectives, pattern theories and payment
  claim comparisons retain their selected records and assumptions. Single-account
  and cross-account tracing compare methods and preserve asset/resale assumptions.
  Indirect workpapers retain assessed amounts, sources and review requirements.
- Ledger exports include readable reports and optional PDFs, originals and wider
  case history. Saved exports can be compared; tracing packages can be assembled
  and independently checked against their captured calculations.
- New custody reports and corrections append to recorded source history. Financial
  audit events record covered changes prospectively. The optional timestamp runner
  requires operator-selected cases and trust configuration; it is not auto-started.
- A beginner user guide covers 25 sections with ten synthetic-case screenshots.
  The Financial guide button remains above every financial tab and opens an
  accessible modal. Contents links, loading/retry and keyboard dismissal support
  reading instructions without losing an unfinished case form. The guide is also
  available as portable HTML with embedded images.

## Validation completed locally

- 4,389 backend financial tests passed for the committed financial implementation
  before the documentation/UI addition.
- The documentation/UI addition passed a production frontend build, 37 existing
  financial-page tests and scoped ESLint.
- Read-only browser checks confirmed guide access across 13 tabs, desktop/mobile
  layout, contents links, image loading, Escape dismissal, focus return and an
  unchanged unsaved transfer-date field. Case mutations were blocked.
- Earlier source review and export acceptance used supplied PDFs. Synthetic tracing
  and package verification checks are identified as synthetic in their records.
  Software test counts are not measurements of extraction accuracy.

## Remaining limitations and excluded work

The unfinished runtime-inventory service, migration and associated backend edits
remain local and are not included. They require export integration and acceptance
before release. Earlier component versions and custody events are not invented.

Manual finalized PDF readings remain P3 and can appear in working totals without
entering verified totals. Automatic extraction still requires representative
independent accuracy acceptance. The local provider credential failed its capped
synthetic authentication check; the server's own provider configuration must be
checked separately. No real case evidence was sent for that synthetic check.

## Checks after deployment

1. Confirm the deployment script completed the build, migrations, restart and
   health checks for the intended branch.
2. Sign in using an authorised server account and open a test case.
3. Upload a test PDF, prepare it, save and reopen a reviewed reading, then inspect
   the source and applicable statement controls.
4. Check ledger populations and a downloaded report against the selected records.
5. Open Financial guide on several tabs and confirm its images and contents links.

The server uses its own database, user accounts, source files and provider settings.
A Git push does not copy the local development cases or credentials. Retain the
server's database recovery point: reverting application code does not automatically
reverse the database migrations.
