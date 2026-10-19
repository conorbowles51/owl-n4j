# Read files: status, group review and scanned headings

27 September 2026. Acceptance reopened after a fresh upload group showed the same “PDF read · payments not yet imported” label for materially different outcomes.

## Investigator journey

Start at Statement files after uploading PDFs. A processed card now has an explicit Review and import action (or Review reading and saved records). Open it, review the account/period and current checks, confirm only when ready, and return to All files & imports. Read files without a prepared batch status are counted separately from assessed ready periods, with Review N read files together leading to the existing batch preparation and confirmation workflow. It uses retained readings and does not silently import payments.

An independent upload of identical PDF bytes can resolve to an existing saved import even though its evidence ID is new. The register now reports that relationship as “Same PDF has saved records · review this copy”. It does not duplicate payment totals, assume all periods are saved, or inherit another file's duplicate exclusion. Matching is case-scoped and ignores superseded/removed imports.

## Reading repair

OCR punctuation attached to BBVA credit and liquidation column headings prevented recognition of a complete first-page table. The dated rows and exact amounts were present but classified as other page text. The reader now tolerates edge punctuation on the fixed known column labels while still requiring the full positioned header. Amounts, source text and reconciliation requirements are unchanged. This operates on retained geometry; a new OCR run is not required.

## Verification

- Supplied scan replay with the observed header punctuation recovers every printed payment; closing, running, credit and debit checks match. Private source and replay artifacts remain outside Git.
- Backend status/BBVA regressions cover identical-copy links, case isolation, no duplicated totals, superseded sources, source preservation, confirmation and reopening.
- Three older BBVA tests still assumed pre-admission imports could be created through the current policy. Baseline execution reproduced those failures. Legacy fixtures now explicitly seed the historical policy, then exercise actual recovery; the count-mismatch test asserts rejection rather than an import with warnings.
- Frontend unit checks cover explicit file actions, read-group preparation and same-PDF status. Chromium checks open/review/return on a narrow viewport without importing live records.
- Implementation and local verification do not by themselves establish deployment or source-specific live acceptance. No live imports or investigator decisions were changed during diagnosis.

## Remaining acceptance

Verify the released file list and the repaired scanned statement against retained live readings. Currency choices, separate account sections, zero-activity saves and genuine differences remain distinct outcomes requiring visible review. Do not describe an upload as a confirmed transaction import or claim that the whole case is complete from a sample of files.
