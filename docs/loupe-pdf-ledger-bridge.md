# PDF to relational ledger: next implementation boundary

Checkpoint: 6 September 2026. This is an implementation proposal for the remaining
ingestion work, not a statement that the bridge is built or that every extracted
number is a transaction.

## What the code currently provides

- `backend/services/financial/native_ingest.py` is the only production caller of
  `record_transactions`. Native rows already contain normalized `RowReading`
  objects. Reformatting their integers cannot recover original source text.
- PDF extraction records canonical text, page spans and table geometry. The
  engine's `extract_entities.py` builds financial graph properties; it does not
  produce relational `TransactionDraft` objects.
- `EvidenceDocumentText` holds canonical content, digest and source locations.
  `EvidenceTableGeometry` holds page/table/cell geometry. A geometric row alone
  does not establish which column is an amount, or its account and direction.
- `assess_source_amount` assesses an explicitly selected text span against stored
  content and provenance. Currency is caller supplied. It does not identify a row
  or admit a figure. Historical missing origin remains unknown.
- `TransactionDraft` requires a complete `RowReading`, row index, account and
  locator. Stored transactions require an integer magnitude. An unresolved amount
  cannot be represented by choosing one proposal just to satisfy that schema.
- Corrections append a replacement and audit event, retain original readings and
  locators, and recompute statement consequences. Native control totals and printed
  running-balance chains remain explicit revalidation reservations.

## Proposed bounded sequence

1. **Capture a source-bound mapping before creating ledger rows.** Define a typed
   manifest that identifies case, evidence file, file/text digests, table identity,
   rows, column meanings, account context, currency and direction convention.
   Preserve the exact cell text and locator. Map only fields supported by the
   source; missing account/date/direction stays unresolved. Column recognition
   must be measured and reviewed, rather than inferred from every numeric token.

2. **Store unresolved readings outside the integer ledger.** Introduce reviewed
   extraction candidates with explicit pending/resolved/rejected state. Keep raw
   text, origin, all amount proposals, source/mapping revisions and the actor's
   explanation. No placeholder zero or selected default proposal enters totals.
   Define schema and migration with immutable original snapshots before adding a
   writer. This separate storage is proposed because the current transaction
   schema cannot faithfully hold an unresolved amount.

3. **Assess candidates from the stored source.** Reuse the money and suspect-amount
   readers. Bind each result to the exact candidate and source digest. Preserve
   uncertain dates, directions and account mappings as well as uncertain amounts.
   Reject stale source/mapping revisions before recording a review. A model may
   suggest a mapping, but its suggestion is not evidence of source identity.

4. **Materialize complete reviewed drafts atomically.** Reuse ingestion runs,
   document/period writers, `record_transactions`, reconciliation and computed
   proof classes. Review resolves a reading; it must not let the reviewer assign
   a proof class or bypass missing admissibility conditions. Record a unique
   candidate-to-transaction link so retries cannot create another transaction.
   Keep pending/rejected candidate counts distinct from ledger totals.

5. **Project only after the relational record is authoritative.** Implement the
   agreed projection stage separately. Existing graph financial entities must not
   be silently treated as reviewed ledger rows or unioned into its totals.

## Checks before enabling writes

Use generated native, digital-PDF, image/OCR and missing-provenance fixtures. Prove
case isolation, digest drift refusal, ambiguous columns, repeated amounts on a
page, source order, zero/sign/currency handling, duplicate retries and concurrent
review. Verify originals survive resolution and correction, unresolved candidates
remain outside totals, proof class is computed, and displayed source highlights
still identify the original evidence. Exercise the final bridge through the
isolated HTTP/PostgreSQL app, not only mocked component tests.

The first next code unit should be the typed mapping/candidate contract and its
source-binding tests. A migration or admission endpoint should follow only after
that contract can express unresolved fields without fabricating a transaction.
