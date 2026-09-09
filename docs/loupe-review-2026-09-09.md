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

- Source image zoom/readability on dense real statements.
- Include structured candidate review history in exports, beyond finalization
  references. Current ledger manifest has0adjudication decisions for this sample;
  that does not mean no candidate-review decisions exist.
- Complete-statement controls and reconciliation; verify more than a two-row sample.
- Repeat the journey on the second supplied PDF and exercise interrupted preparation.
