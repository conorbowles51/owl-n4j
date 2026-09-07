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


## Source-byte prerequisite — extended 7 September window

`candidate_source_bytes.verify_candidate_source_bytes` rebinds the immutable saved
candidate, scopes the storage lookup to its case and verifies the current file
against the bound evidence digest. The trusted application storage resolver is
injected; callers cannot supply an arbitrary source path. Hashing streams bounded
chunks, refuses non-regular files and files over 256 MiB, and detects observed
size/metadata changes during the read. Errors do not expose private storage paths.
The receipt records the exact digest, count and verification time without changing
the saved original's historical `file_bytes_verified:false`.

This internal prerequisite has no public admission endpoint. It does not prove
extraction accuracy or classification and is not a reusable permit. The future
writer must acquire file/text/geometry/review locks in the established order,
rebind under those locks, call this check immediately before its atomic write,
and retain the receipt. Database locks cannot stop external filesystem changes
after the read. Source shape/layer and immutable materialization/source claims
still remain as described above.


## Investigator reading method — extended 7 September window

The schema now represents `ExtractionLayer.investigator_review = 4`, a separate
method rather than another automated extraction tier. Source documents and
transactions accept this code, and the UI labels it “Investigator reviewed” while
explicitly withholding any claim that financial checks passed. Human-reviewed
rows/documents cannot be mixed with automated extraction methods in the writer.
Native source shapes still require native extraction; an investigator-reviewed
statement starts at computed P3 like any unchecked statement. Original extraction
origin and immutable review history must still accompany future materialization.

The existing duplicate ranking retains automated method order before method4:
review alone earns no preference over an otherwise equally checked automated
reading. This is a conservative tie-break, not a new proof class or a claim that
human readings are a model fallback. Method3 alone retains the fallback badge.

Migration `20260907_investigator_reading` extends both database constraints and
refuses downgrade while method4 rows exist. Verified on isolated PostgreSQL by
`scripts/check_local_reading_method.py`, rolling back every test row change.
The local database is migrated; restart the local backend before exercising a
future writer using the new method. No reviewed candidate has entered the ledger.

Next resolve selected-row source shape/coverage without claiming the full PDF is
a statement or all transactions were selected. Then immutable source/candidate
claims and atomic whole-document finalization remain before a public ledger writer.


## Selected financial rows are not a complete statement — 7 September 2026

`SourceShape.selected_document_rows` represents deliberately chosen documentary
financial rows where whole-document coverage and a complete control block have
not been established. It always computes P3, including when a subset's arithmetic
is reported balanced. Reclassification and correction verification preserve that
restriction. The persisted source-shape metadata makes the coverage limitation
recoverable; the UI's P3 explanation now includes incomplete document coverage.

This is not an alternative classification for amounts asserted in letters, chats
or interviews: those remain unstructured narrative/P4. The future candidate writer
must require an explicit documentary-financial-row attestation and reason, rather
than assume that a selected table is a financial record. It must hardcode this
limited shape for the selected-row workflow, preserve source/review provenance,
and never accept caller-supplied proof class or complete-statement claims. A full
statement extraction/verification workflow is separate; balanced subsets cannot
replace it. No automatic mapping, ledger writer or coverage acceptance is added
by this prerequisite.

Next: immutable candidate-to-transaction links/source claims and an atomic sealed
whole-file finalization. Require all saved candidates to be resolved or rejected,
exclude rejected readings without deleting their history, and refuse unresolved
source reuse before writing. Repeated content requires document-wide occurrence
indexing; reviews after finalization must use existing ledger correction history.


## Immutable finalization storage — 7 September 2026

`FinancialCandidateFinalization` seals one candidate batch per case/file and
links its source document/run, byte digest, manifest digest, actor/reason and
transaction count. `FinancialCandidateTransaction` retains each candidate's exact
resolved review and original ledger transaction, plus a stable source-claim digest.
Unique constraints cover file finalization, source document, candidate, transaction
and source claim within the sealed file. UPDATE guards preserve both records;
existing case/file/source deletion cascades remain consistent with repository policy.

PostgreSQL validates case/file/document/run/digest/reading-method/shape consistency
on finalization, and candidate/latest-resolved-review/transaction scope on linking.
File locks serialize seals with direct mapping, candidate and review insertions;
new insertions after sealing are refused. The service review guard gives a plain
409 directing users to ledger corrections. Mapping creation permits an identical
pre-existing retry but refuses a new mapping after the seal. Original links remain
attached to their original transaction when that transaction's ledger state changes.

Migration `20260907_candidate_finalizations` is applied only to the isolated local
database. The local verification script exercises scope, duplicate, update and
post-seal guards plus protected downgrade with every synthetic row rolled back.
This is storage infrastructure, not a materialization writer: manifest integrity,
complete candidate review coverage, overlap checks, source-claim derivation and
atomic transaction creation remain the writer's next responsibility. Do not expose
a public finalize route until those checks and concurrent retry tests pass.

Whole-file sealing deliberately refuses later additions. A future whole-reading
replacement workflow would be needed to add omitted rows after finalization; never
work around it with another mapping or a second source-document batch. Current
limits remain explicit (up to 1,000 transactions); selecting fewer rows must never
be described as complete extraction of a larger PDF.


## Atomic reviewed-row writer — 7 September 2026

`preview_candidate_finalization` and `finalize_candidates` now perform fresh
whole-file preparation. They lock case (NO KEY UPDATE, preserving foreign-key
insert compatibility), file, text, geometry, candidates and sorted accounts; bind
every mapping; require all readings resolved/rejected; validate exact readings and
account scope/currency; compare every active source pair; and verify source bytes.
At most100 mappings/1,000 total candidates are accepted. The writer's complete
comparison is bounded at499,500 pairs, independent of the smaller UI reuse-report
limit; a truncated UI report is never a write permit. Stable source claims omit
proposed column meanings. Exact date roles and original source cells are preserved.

The explicit request accepts documentary financial rows and incomplete coverage,
a reason and the current manifest revision. Source/transaction/link/receipt rows
commit together. The source uses investigator_review and selected_document_rows;
P3 is computed and default verified totals exclude it. Distinct source rows with
identical reviewed content remain distinct through document-wide occurrence
hashes. A row locator encloses selected stored cells without fabricated text
offsets; individual originals remain in provenance. No guessed balances/periods
are written. Existing source-file or identical-byte ledger readings are refused.

Identical retries return the durable original receipt and transaction IDs; changed
requests conflict. A racing second attempt may leave a separate completed audit
attempt with zero new rows, while the returned result names the original run.
The fast retry path creates no run. Run lifecycle uses the existing separate audit
sessions, so audit termination after a committed write can still fail independently;
a durable receipt makes retry safe. Source-byte checks remain point-in-time.

`check_local_candidate_materialization.py` verifies actual PostgreSQL rollback
after all rows/links flush, two demonstrably blocked competing requests, one seal,
two equal-value distinct transactions, identical retries and refusal of reopening.
Its latest synthetic fixture is recorded in candidate-materialization-check.json;
candidate-check.json now points at that finalized fixture. Recreate a pending
fixture before older source-selection/review scripts expecting pending candidates.
The writer is service-only; authenticated preview/finalize routes and UI remain.


## Authenticated finalization and browser workflow — 7 September 2026

Case:view GET `/candidate-sources/{file}/finalization-preview` releases snapshot
locks in finally. Case:edit POST `/candidate-sources/{file}/finalize` derives the
actor from authentication and uses the trusted storage resolver. Scoped/stale
errors retain their status; unexpected failures return generic messages. The
response echoes the finalized manifest revision, so UI acceptance is tied to the
preview shown. Write-route permission inventory includes the new endpoint.

A deliberate panel within saved PDF batches loads the whole-file preview, reports
resolved/rejected counts and incomplete coverage, requires two unchecked explicit
acceptances and a reason, and blocks uncertain/repeated submissions until reload.
Receipt scope, revision, count and unique transaction/candidate links are checked.
Finalization refreshes original-case candidate/ledger/audit/classification caches
even after unmount. Receipts open each original transaction's protected source
highlight and acknowledge later corrections. Existing saved candidate forms can
still be opened for review history; a later review write is refused by the seal.

`prepare_local_finalization_ui.py` creates a fresh synthetic pending fixture and
resolves its two rows. `check_local_finalization_ui.cjs` then verifies actual UI
finalization, ledger refresh, identical HTTP retry, rejected caller proof-class
override, changed-request409, reload without another write action and the source
image/highlight. Source image is checked in the citation dialog, before opening
the separate full-document viewer. Screenshots are kept under /tmp only. The
latest case/result is in `data/local-runtime/finalization-ui-check.json`.

This completes deliberate stored-grid selection/review/finalization connectivity.
Automatic financial extraction, broader date/account uncertainty handling, complete
statement coverage/control verification and the remaining numbered features are
not completed by this workflow. Selected rows still do not enter default verified
totals. The two real PDFs remain read-only test inputs, never ingested into a case.

## Finalized review protection — 7 September 2026

The review response now requires a nullable `finalization_id`, case-scoped through
its mapping/file. It leaves original/history/review revision unchanged. Both resolved
and rejected readings in a sealed batch become read-only; missing seal-state fields
fail frontend validation rather than accidentally enabling old write controls.
Review cache refresh keys include finalization so an already-open form resets when
another screen finalizes. Source amount assessment stays available with a separate
currency input that does not change the displayed reviewed currency. Corrections
belong to the ledger, and receipt source links preserve the original transaction.

Provisional-account setup checks for finalization before opening its audit run and
again under the source-file lock. The second check protects against finalization
between initial inspection and account creation. A rejected raced attempt records a
failed audit run but no account. Tests exercise this ordering and both sealed statuses.
The browser correction round trip keeps the selected-document P3 classification and
replaces the active ledger row without changing the saved candidate reading.

## Numeric date uncertainty — 7 September 2026

`assess_date_text` offers conservative numeric calendar proposals: ISO dates,
day-first/month-first numeric dates with one consistent separator, explicit missing
year or two-digit-century uncertainty, invalid calendar values and unsupported text.
No locale, current year, period context or OCR character repair is inferred. Even
one valid calendar reading requires source review. Recognised/unknown glyph origins
remain explicit. Two month/day alternatives with no full year never contain an ISO
date; leap-year validation remains dependent on actual source year context.

`assess_candidate_dates` first rebinds the immutable saved mapping to its current
case-scoped source, processes only columns proposed as booking/value/transaction
dates, and retains original source spans or stored locators and review revision.
Case:view GET `/candidates/{candidate_id}/date-assessment` and the review panel
expose these proposals read-only, including after finalization. Response scope,
revision, raw-source consistency and no-write status are validated. Unknown columns
are counted, not classified. Named-month/other unsupported formats are retained for
manual review; automatic nomination and date-context resolution remain outstanding.

## Explicit column suggestion aid — 7 September 2026

The source picker scans at most the first ten stored rows for exact supported labels
(case/whitespace normalization only). It cites original text and source row/column,
retains competing meanings, and does not guess generic Date, OCR repairs, substrings
or row classifications. Users explicitly apply each suggestion to the existing
proposed-meaning controls; all row checkboxes remain unchanged. Reload resets the
suggestions and selections. A matched label is not proof of a header or transaction.

Accepted meanings are stored using the existing source-revision-bound manual mapping
contract; this UI aid does not claim an independent automatic extraction provenance
or persist a separate header-extraction event. Whole-page source revision still
protects against drift. Automatic transaction row nomination remains outstanding.
Both grid and canonical-text column contracts now accept transaction_date separately
from booking_date/value_date; existing snapshots serialize identically. No schema
migration or original rewriting is needed.

## Conditional running-balance correction diagnostics — 7 September 2026

Correction previews compare current/proposed movement against stored running balances
for the linked period, under both ascending and descending source-row interpretations.
They assume post-transaction balances explicitly; matching arithmetic does not prove
that convention, order, coverage or glyph accuracy. Only independent printed opening
balances anchor the first interval. Missing balance rows accumulate intervening
movement; excluded rows break the chain. Superseded versions are not counted again.
Duplicate active positions, mixed account/currency, malformed arithmetic, absent
balances and more than1,000 period rows produce explicit unavailable results.
All integers serialize as decimal strings. Counts cover the complete bounded walk;
only the first100 mismatches per interpretation are displayed, with truncation stated.

The correction event retains the reviewed comparison in after.running_balance_comparison
(before is null). The existing revalidation reservation remains: no grading promotion
is earned from these conditional diagnostics. Document revision now includes actual
row order, running balance, amount/direction/account/currency/period fields, so a
changed stored balance invalidates a prior preview even without a recalculated
content hash. Source links open the original row, including after replacement.

## Printed statement-bound coverage — 7 September 2026

Case:view GET statement-coverage reads account/period/source ownership together and
reports bounded date coverage. It reuses the existing printed-bound rule but unions
all eligible intervals, including enclosing exports, before computing gaps; the
continuity module's exclusion of enclosing periods is appropriate for balance seams,
not for claiming date-range absence. Overlaps are explicit, dates count once and
currencies are separate. Missing/derived dates and nonadmitted sources remain visible.
Cross-case source links or accounts over500 periods return unavailable rather than
partial or leaked information. Accounts page25 at a time with has_more/offset.

The Ledger coverage panel uses the financial-ledger case cache prefix, so existing
correction/finalization/duplicate invalidations refresh its snapshot. It makes clear
that bounds do not certify extracted transactions or records outside known bounds.
Source period/document/file IDs are retained in the response. Exact source-bound date
citation navigation and integration with transaction search remain further work;
this panel does not invent a page/rectangle for a period bound.
