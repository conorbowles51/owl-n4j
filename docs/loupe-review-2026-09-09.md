# Review the real-PDF workflow — 9 September 2026

Open the isolated [real-PDF acceptance case](http://127.0.0.1:55174/cases/c06c264c-a402-4895-a696-be634fe23629/financial).
This contains a copy of the supplied 56-page PDF. The original file is unchanged.

1. In Ledger, open PDF readings, then Open readings on the saved batch.
2. Review source row 41 or 42. Original page4 and selectable value highlights sit
   beside the reviewed fields. The amounts are USD14.00 and USD100.00. Printed
   transaction dates are04/22 and04/23;2021 came from the statement header.
3. Open Review history to see the recorded review and basis. Original text is
   retained, including OCR mistakes in descriptions corrected during review.
4. These rows were finalized into the ledger as an incomplete P3 sample. They
   remain outside verified totals. This is deliberate, not a missing-data bug.
5. Download ledger snapshot to inspect exact rows, source references and excluded
   population. The saved test ZIP was independently verified against its manifest.

This proves a bounded real-PDF path through actual application upload, queued
local text/location preparation, source selection, review and export, without
fixture seeding, external AI or automatic admission. It does not establish whole
PDF transaction accuracy, complete statement coverage, currency/account identity
outside this sample, or completion of the full financial feature set.

The sample account is explicitly provisional. Do not run a second acceptance
writer against this finalized PDF. Existing scripts preserve checkpoints and
refuse blind repetition:

- scripts/check_local_pdf_intake_ui.cjs
- scripts/check_local_real_pdf_review.cjs
- scripts/verify_local_real_pdf_export.py (read-only; safe to repeat)

Outstanding near-term usability/workflow gaps:

- [x] Source image zoom100–400%, fit-width and highlight focus.
- [x] Structured candidate review history now included in schema3exports, with
  2PDFreview decisions/1receipt recorded separately from0ledger adjudications.
- Complete-statement controls and reconciliation; verify more than a two-row sample.
- [x] Repeat the journey on the second supplied PDF. Cancellation handling also has a targeted engine test; complete hard-crash/retry acceptance remains.

The [second PDF sample](http://127.0.0.1:55174/cases/4d897cb5-b9e4-4df7-9a21-b1ba4b8bf5d7/financial)
contains two reviewed page 3 rows: a USD 180.00 payment (credit) and USD 61.62
purchase (debit). Open PDF readings and the saved batch to inspect rows 10 and 13.
Both remain P3 and excluded from verified totals. Its exported originals, decisions,
amounts, directions and dates were independently checked, including file hashes.

Choose PDF rows now puts the source image beside the selection grid. Click a table
value to highlight its location; use the checkbox separately to nominate a row.
The source has zoom and the layout stacks on narrower screens. Looking at a value
does not save anything. Avoid saving another copy of these already reviewed rows.

Open **Statements** for balance checks and the coverage timeline. The real two-row
PDF samples have no complete statement periods, so missing controls remain explicit.
The existing [corrected synthetic statement](http://127.0.0.1:55174/cases/5675421f-0860-4048-abe1-902241a1feec/financial)
demonstrates the new checks: open Statements, Check statement balances, then Check
running balances. The GBP 10 discrepancy links to the original source. The
[coverage example](http://127.0.0.1:55174/cases/e0da5581-a1ac-4db5-a3a9-e17021fb807a/financial)
shows gaps and overlaps in its Statements timeline. These are synthetic fixtures,
not findings about the supplied documents.

For a portable review bundle, select **Include original source files with fresh
hash checks** before downloading the ledger snapshot. The ZIP then contains the
complete referenced PDF alongside the report, snapshot and verification manifest.
Missing or changed files stop that export. This option was checked on both supplied
PDFs, whose originals remain unchanged.

## Statement controls sample

Open http://127.0.0.1:55174/cases/c1453d2f-c2ff-47c6-a58a-1a9786803f44/financial
and choose **Statements**, then **Check statement balances**. This isolated real-PDF
sample deliberately contains only the payment and purchase from page 3. It leaves
out $56.16 of interest, so the balance difference should be $56.16. It remains
outside verified totals.

Choose **Inspect statement source**, then **Inspect opening** or **Inspect closing**
to see the original value highlighted on PDF page 1. The printed positive amounts
are credit-card amounts owed; the ledger therefore uses negative balance signs.
Review reason and verification details can be expanded. The original PDFs and
previously finalized test cases are unchanged.

## Correction and audit history sample

Open http://127.0.0.1:55174/cases/ea81df83-814c-4f9e-b3a8-3a989190b920/financial
and choose **Decisions**. Expand **Original and replacement readings**. The test
intentionally entered $61.26 and then corrected it to the actual $61.62 on PDF
page 3. **View original source** reopens that page. The original reading remains
visible and the corrected replacement stays outside verified totals. The ledger
export preserves both amounts, the correction reason and original source cells.
