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

## Implemented contract — 7 September 2026

`backend/services/financial/pdf_candidates.py` now provides a read-only typed
contract for a nominated canonical-text region, proposed columns, ordered rows,
exact cell spans and optional source-backed account/currency/period/direction
context. Binding queries the case-scoped stored source, verifies the text digest
and exact spans, and returns immutable **pending** candidates. It does not assess
or normalize amounts, resolve context, write candidates or admit ledger rows.

Source revisions include case/file identity, recorded file digest, canonical text
digest, source locations and extraction job. Changing provenance without changing
characters therefore invalidates a mapping. Mapping revisions include the complete
proposal, and repeated identical amounts at different offsets retain distinct
candidate keys. The key identifies a mapping snapshot; it is **not** sufficient
for cross-revision or cross-table materialization deduplication. A future writer
must enforce that separately and rebind under its transaction.

Origin and page come from the same conservative page-span helper as manual amount
assessment. Missing, malformed or overlapping provenance stays unknown. The
contract does not accept caller-supplied origin, settled amounts or proof class.
Recorded file metadata is checked; original file bytes are not reread.

This is the canonical-text part of step 1, not a completed PDF extractor. Table
identity is caller-nominated, column meanings remain proposals, and no geometric
table detection or rectangle claim is made. The v1 contract supports nonoverlapping
rows in canonical text order; column-major/irregular extraction needs an explicit
geometry binding extension, not reordered or guessed offsets. Empty/missing fields
may be omitted without creating placeholder ledger values.

The stored grid adapter below now covers table/cell identity where canonical text
offsets do not faithfully locate a cell. Immutable candidate storage and review
transitions outside the integer ledger are next. Automatic mapping, amount
assessment integration, atomic materialization and projection remain.

## Stored grid adapter — 7 September 2026

`pdf_geometry_candidates.py` adds the alternate `pdf-grid-mapping-v1` contract.
It binds page/table index/row/column and exact stored cell text without fabricating
canonical character offsets. A single case-scoped query snapshots file metadata,
canonical text/provenance and the page's geometry. Text and geometry must share a
non-null extraction job; historical unbound geometry is refused. The revision
covers the complete page geometry as well as source metadata and text provenance.

The adapter validates stored locators, page agreement, table containment, page
size, unique grid coordinates and nonoverlapping cell rectangles. Missing cell
rectangles remain explicitly unlocated. It preserves drawn versus text-aligned
table provenance and proposed column meanings. Origin remains unknown unless the
stored page map establishes it conservatively. Every result is still pending;
there is no candidate persistence, review endpoint or ledger write yet.

Generated PDF extraction is exercised through the actual table reader into stored
geometry and back through this binder. Case isolation, drift, malformed geometry,
repeated amounts, unknown/recognised origins and immutable originals are tested.
Next implementation is candidate persistence with immutable source/mapping
snapshots, followed by auditable review transitions and amount assessment.

## Pending original storage — 7 September 2026

Migration `20260907_candidate_originals` adds mapping and candidate original tables
outside the ledger. `candidate_store.py` locks the evidence file and existing
source text/geometry rows, rebinds either mapping contract, then commits all
originals atomically. Same-mapping retries return the original IDs and actor;
changed mappings append new originals. Snapshot digests detect incomplete or
inconsistent stored data. PostgreSQL triggers reject updates, and ORM guards
provide the same protection for ordinary ORM writes in SQLite. Case/file deletion
still cascades, consistent with existing evidence deletion semantics.

These tables contain no normalized money or mutable review status. The current
reader reports pending. Reviews will be separate records, leaving these originals
intact. New mapping snapshots are not deduplicated across revisions or overlapping
regions; materialization must enforce that later. The service requires an
authorized case and actor from its eventual route, and a dedicated clean session.
No route/UI or review transition is enabled by this storage segment.

## Saved-candidate assessment and read API — 7 September 2026

`candidate_assessment.py` rebinds saved originals to the current source before
assessing proposed amount/debit/credit/balance columns. It uses stored text and
origin, preserves all uncertain alternatives, returns integer monetary values as
decimal strings and identifies unclassified columns without guessing their role.
Currency remains caller-supplied context. Numeric certainty does not resolve a
transaction, and a saved mapping remains pending. The assessment revision covers
the displayed result and currency; it is not a write permit.

Read-only, case:view endpoints now expose `GET /api/financial/candidate-mappings/
{mapping_id}` and `POST /api/financial/candidates/{candidate_id}/amount-assessment`
(the URL is continuous). The assessment body accepts only currency. The local
synthetic script verifies these through normal login and source rectangles.
Review records, transitions, creation endpoints and review UI remain next.

## Append-only candidate reviews — 7 September 2026

Migration `20260907_candidate_reviews` adds immutable review events separate from
original snapshots. `candidate_reviews.py` computes pending/resolved/rejected state
from a sequence and prior-revision chain. Resolution requires exact nonnegative
minor-unit strings within BIGINT range, supported currency, explicit direction,
at least one identified calendar date and an account in the same case with a
compatible currency. No proof class or admission field is accepted. Reopening
clears the current reading but retains it in history; revised resolutions append.

The writer locks source and candidate rows, rebinds originals, checks the reviewed
revision and commits a named actor/reason atomically. `GET /api/financial/candidates/
{candidate_id}/review` is case:view; POST at that same continuous path is case:edit.
Mapping reads and assessments now include current review state and its revision.
History remains readable when source data later drifts, while further decisions
are refused until a new source mapping is made. The PostgreSQL history trigger
refuses UPDATE; existing case/file deletion still cascades.

Review UI, candidate creation endpoints and atomic materialization remain. Resolved
means an analyst supplied a complete reading, not that the evidence passed
reconciliation or that the transaction counts in totals. A future materializer
must bind the exact current review and prohibit contradictory later edits after
materialization, directing ledger corrections through the existing audit path.


## Saved-candidate review screen — 7 September 2026

Case-scoped GET candidate-mappings and ledger-accounts provide bounded lists/search.
POST candidate-mappings accepts only the typed source-bound proposal and uses the
existing atomic writer with the authenticated case:edit actor. The Financial Ledger
now has a lazy-open PDF readings panel with batch/row pagination. Review shows exact
original text, amount assessment and the source image, then accepts explicit account,
currency, direction, exact amount, separate date roles and reason. Resolve/reject/
reopen preserve history. Writes block repeat submissions until an explicit reload,
including uncertain failures; responses are checked against case/candidate/revision.

Verified with a synthetic real-browser reopen/resolve round trip and authenticated
creation retry. Creation of source mappings through the UI, automatic extraction,
account creation and atomic materialization still remain. Resolution stays outside
ledger totals. Earlier “UI remains” notes above describe the preceding checkpoint.


## Deliberate stored-grid nomination — 7 September 2026

`candidate_sources.py` lists case-scoped source pages and reads one validated table
at a time using the same revision and geometry checks as the binder. Source cells
are returned with exact text, grid coordinates and locators; oversized tables/cells
are refused without truncation. Read routes use case:view. The UI shows the page,
leaves columns unidentified and rows unselected, and saves only deliberate choices
through the existing case:edit writer. Rows from text alignment are explicitly
labelled as inferred. Pagination never changes source row indices.

Saved responses must echo the exact proposed source revision, rows and meanings.
Writes require explicit reload before another attempt; identical retry safety stays
in the writer. A synthetic live-browser selection/save/retry produced one pending
row under the same mapping ID. All 153 extracted tables in the two user-provided
PDFs passed a read-only source/binding contract check. Their 7,529 source rows are
not claimed to be transactions. Account setup, extraction initiation and atomic
materialization remain; this adds a UI for already-stored PDF table extraction.


## Provisional account setup — 7 September 2026

Candidate review can create an explicitly provisional account through a case:edit
endpoint. `AccountDraft.unidentified` and `record_account` retain the existing
identity rules; the distinguisher includes source file, currency and the explicit
label. No printed identifier or holder is invented. An ingestion run records actor,
request/reason and outcome, and first-seen provenance survives retries. The source
file/text/geometry are locked and rebound before creation, and stale review context
is refused. Concurrent same-label creators serialize on the source file and reuse
one account. Candidate review refuses a document-scoped account from another PDF.

The UI marks these accounts provisional, records a reason, checks the returned
case/source/currency, selects a newly created account and blocks uncertain retries
until review reload. This makes a new-source review possible without guessing
identity. Known-account establishment/merge and atomic ledger materialization still
remain; provisional setup changes neither the reading nor classification/totals.


## Source reuse review before materialization — 7 September 2026

`candidate_overlap.py` rebinds every saved mapping under a shared source-file lock
and compares active candidates across mappings. Same stored row identity survives
changed proposed meanings. Canonical character overlap and conservative bounding
source-area overlap are reported separately; mixed/unlocated source claims may be
uncomparable. Equal values at different source rows are not by themselves a finding.
Rejected candidates remain counted but are excluded from active comparisons.

Bounds are explicit: 100 mappings/1,000 readings (refused beyond either), 10,000
pairs per check, first 100 finding details with complete compared-pair counts. The
response includes scope, coverage, limitations and a snapshot revision over all
mapping/review revisions. The UI can open the exact candidate in either batch.
No source finding rejects or merges anything, and this snapshot must never be
used as a materialization permit. Database-enforced immutable source claims and
candidate-to-transaction links are still required for the future writer.

### Materialization questions resolved by the current code inspection

- `record_transactions` writes a document's whole batch because identical-content
  occurrence indices are document-scoped. Incremental per-candidate calls cannot
  simply append to that writer without addressing occurrence identity.
- Existing extraction layers describe native/template/structural-model/grounded-
  model readings; the candidate record preserves text origin and review history
  but does not yet establish a truthful ledger extraction-layer assignment. Do not
  call a human reading native/template or invent model involvement to fit the enum.
- PDF row nomination does not establish statement shape or printed period/control
  coverage. `SourceDocumentDraft` requires source shape and computes proof class.
  Resolution cannot be used as evidence that statement arithmetic passed.
- Existing PDF snapshots check recorded file digests, not the current file bytes.
  A materialization boundary must decide and verify the actual-byte requirement.

Address these contract/integration issues before exposing a ledger writer; retain
existing source originals and review histories throughout.
