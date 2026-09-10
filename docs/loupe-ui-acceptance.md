# Loupe UI and practical workflow acceptance

Current focus agreed with Neil on 9 September 2026: finish a usable PDF import →
review → correction → analysis → export journey. Implement the saved design as
part of that journey, not as an unspecified finishing phase. Existing completed
work stays visible; broader features remain outstanding. Do not silently replace
this milestone with more tracing methods or transfer-matching infrastructure.

Design sources: `bundle/docs/13-target-state-financial-forensics.md` §10,
`bundle/docs/11-v1-learnings-into-loupe.md`, `docs/financial-handoff.md` settled
rules, and the running state. The March frontend design-system draft and the
separate Loupes collection design are not by themselves an agreed financial layout.

## Practical journey

- [x] Upload a copy of a supplied real PDF through the application and follow its
  processing state. Preserve original files. Keep testing isolated and offline
  until a provider setup is explicitly selected.
- [x] Reach stored source rows from that upload without fixture database seeding.
  Verified 9 September with the 56-page PDF, isolated case c06c264c-a402-4895-a696-be634fe23629. Original hash unchanged; no admitted transactions.
- [x] Review existing saved candidate values beside their source image; choose
  a column to highlight without first requesting a numeric/date assessment.
  Desktop side-by-side and narrow stacking checked against a synthetic PDF.
- [x] Verify source/review interaction on the first supplied real PDF (page4, two purchases).
- [x] Repeat source/review acceptance on the second supplied PDF: 108 pages prepared, two page 3 rows reviewed and exported with exact credit/debit readings, source history and P3 exclusions.
- [x] Resolve a bounded, manually checked real-PDF sample, preserve source
  and decision history, and finalize it without implying complete extraction.
- [x] Correct a deliberately misstated reading in a separate real-PDF test case,
  verify preserved source/decision history, unchanged P3 eligibility and exact
  export contents. $61.26 test entry corrected to printed $61.62; no original PDF
  edited. Case ea81df83-814c-4f9e-b3a8-3a989190b920 (9 September).
- [x] Give Neil one clear entry point and repeatable steps through the sample journey:
  docs/loupe-review-2026-09-09.md. Full-statement acceptance remains; bounded PDF review history export is verified.

## Full analytical UI (retained beyond the first milestone)

- [ ] Ledger: full filtering/sorting, visible reliability and corrected/original
  distinction, totals with their included population, reproducible export state.
- [ ] Account continuity timeline: verified periods, held periods, gaps/overlaps
  visible together with navigation to the relevant statement.
- [ ] Quantitative money flow: select parties or a group; incoming/outgoing and
  internal transfers, internal counted once; divergent counterparty chart.
- [ ] Relationship graph: connected payment paths, complementary to amount charts.
- [ ] Tracing: method comparison, expansion across accounts, source-row/page
  navigation, explicit assumptions and missing evidence. Single-account initial
  UI exists; this does not complete the planned trace view.
- [ ] Case timeline: transactions correlated with events from other evidence.
- [ ] Pattern hypotheses: attached supporting rows, no automatic conclusions.
- [ ] From every total to rows, and from rows to source images when a measured
  location exists. Missing locators must remain explicit.
- [ ] Export: same scope/values, originals and decisions, appropriate limitations.

Current visual state is functional, not final. The existing Loupe shell is retained.
Backend test counts do not establish completion of these user journeys.

## Verified refinements — 9 September 2026

- [x] Source zoom100–400%, fit width and highlight focus, verified on the real PDF.
- [x] Structured PDF original readings/review decisions/finalization receipts in
  schema3ledger exports, with separate counts and hash verification on the real sample.

- [x] Show the source beside row selection; clicking a value highlights its stored
  location without nominating or saving the row. Desktop and narrow layout verified
  on the second real PDF with no financial writes (5f5a2a9).

- [x] Dedicated Statements tab with current balance checks, source-linked running
  balance discrepancies and selectable account/currency coverage timeline (84cd821).
  Excluded bounds remain visible; eligible does not mean complete extraction.

- [x] Optional original source files included in the ledger ZIP with fresh byte
  hashes and explicit complete-file scope; verified independently on both real PDFs
  (5eeda00). Default export stays metadata/history only.

- [x] Review printed statement controls before finalization and assign explicit rows.
  Real credit-card sample reports the deliberately omitted $56.16 interest while
  retaining P3 exclusions; original PDF unchanged (d45fb02).
- [x] Inspect retained dates/balances beside original PDF cell highlights after
  finalization; readable export includes controls and source pages (7716d86, 79e1ee8).

## Verified visual analysis — 10 September

- [x] Authoritative ledger posting graph with working/verified scope and source arrows.
- [x] Diverging money charts for date/source-label groups; exact selected totals,
  currency separation and direct contributing-source navigation.
- [x] Search and sort the loaded ledger rows, with50-row paging and clear scope.
- [x] Multiple-claim tracing uses decimal currency inputs and source buttons.
- [x] Paginated PDF export alongside the captured HTML/JSON and originals option.

- [x] Forward cross-account tracing with source-linked hops, explicit assumptions,
  per-account coverage checks and method comparison. Three-account synthetic browser
  journey and exact download verified. No claim of real-PDF transfer verification.

These implement parts of the full design above. Timeline correlation, perspective
flow selection and evidence-linked hypotheses remain active development.

- [x] Case context timeline displays ledger postings beside case events, explicit
  value/transaction/fallback dates and unknown-date warnings. Synthetic browser
  verifies event-detail navigation, display search, exact capture and P3 exclusion
  under verified population. Persistent correlation decisions remain separate work.

- [x] Select an account group in Transfers, calculate explicit pairings, view
  external incoming/outgoing bars ordered by net and internal movements counted
  once, with both source links. Synthetic browser verifies exact totals, selection
  changes and captured assumptions. This is account perspective, not resolved-party
  identity; unidentified internal movements remain explicit.

- [x] Pattern review offers two bounded equal-amount screens and source inspection.
  A proposed Workspace theory requires investigator wording, carries exact captured
  supporting rows/source links and retains revision history. Synthetic save/reopen
  browser check passed; no automatic finding or proof-class promotion.

- [x] Payment-claim comparison lives beside Patterns: inspect a selected evidence
  file, preserve quotation/ranges, see component-by-component proposals and sources,
  download the captured result, and save an investigator response in Workspace.
  Synthetic browser verifies source hash, working/verified separation, P4 retention,
  changed-input clearing and persistent source-linked review history.

- [x] Exact inclusive amount-range filters in the main ledger, currency-scoped decimal input and reproducible table export. Real61.62USDpurchase selected by60–70range; complete3reading capture and report hashes verified (10September).

## Whole-payment asset interpretations — 10 September, about09:18Dublin

Single-account and network tracing now accept optional whole-withdrawal asset
interpretations with a description and basis. Per-method allocations reuse the
calculated withdrawal; cash claims/balances do not change and are not counted
twice. Positive unpaired withdrawals only; duplicate, credit, missing-source and
paired-transfer selections fail. No ownership, valuation, partial purchase or
resale tracing is inferred. Backward scenarios can retain these interpretations.

47 targeted backend and20 tracing UI/contract tests pass, including bigint,
allocation tampering and unchanged cash; TypeScript and scoped ESLint pass.
Read-only browser acceptance on synthetic case3dfbafe7-fa6b-4bdd-9af5-0e97975447b9
passes for both forms: network FIFO20GBP/pro-rata10/LIFO0 allocated to equipment,
remaining80/90/100 unchanged; single-account60claim pays20, leaving40. Original
source navigation, exact scenario download and stale-result clearing verified,
with0 financial writes. Network screenshot visually inspected. Repeatable scripts:
check_local_asset_journey.cjs and check_local_single_asset_journey.cjs. Reports
asset-trace-ui-check.json and conditional-trace-asset-ui-check.json under
 data/local-runtime. Current backend18209, log/tmp/loupe-asset-runtime.out.
No push. Broader asset substitution, extraction and integrated acceptance remain.

