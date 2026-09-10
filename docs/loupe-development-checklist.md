# Loupe financial development checklist

Current milestone: complete the practical PDF-to-export journey and saved UI design.
See [UI and workflow acceptance](loupe-ui-acceptance.md). Broader work stays listed.

Development resumed in this task on9September2026 at Neil's request. The earlier
timed schedule stays paused; historical handoff status below is retained.

Final scheduled handoff:7September2026. The authorized cutoff was
13:00Europe/Dublin; the heartbeat was **PAUSED at12:43Dublin** for handoff before
that cutoff, confirmed by automation_update. No further automatic segments are
expected. Earlier ACTIVE/time-window statements below are retained history.

**Current overall: six completed workflows (2,3,4,5,6,8); four features retain
outstanding work.** Completion here means the stated investigator-review,
authoritative-view and recorded-coverage workflows, with their explicit evidence
limitations preserved. The historical handoff tables below remain unchanged. See [the review and testing guide](loupe-review-2026-09-07.md).
Completed subitems stay visible. Neil requested mindful usage; valid passing tests
were reused and targeted checks covered the final small change.

Keep all ten features and their subitems visible. Mark verified completions [x];
never remove completed work. A feature is complete only when its complete user
workflow is connected and tested. Existing foundations are listed separately so
that progress is not confused with completion of the remaining feature.

Baseline: implementation 5d7279d; 3,570 financial tests passed. No entire remaining
feature below is complete at the start of this window.

1. **Import financial transactions from PDFs — partial**
   - [x] Full supplied108-page document reviewed/finalized through a fresh UI upload and public APIs:27balanced printed periods,104source readings (42nonzero,62explicit zeros), two separate printed-header account perspectives. Browser verifies all ledger/statement pages, exact totals and source-inclusive90-page report; originals/history/hashes preserved. Automatic extraction, wider evidence completeness and account identity remain unconfirmed.
   - [x] Printed-control source finder nominates exact labelled balances/totals for inspection, preserves repeated alternatives and stops at intervening headings. Real opening/closing cells verified; amounts/dates are not filled automatically.
   - [x] Source selection exposes recorded PDF-text/OCR/unknown origin with the same provenance resolution as saved cell binding. Both supplied PDFs checked in the browser; overlapping metadata remains unknown, no automatic confirmation.
   - [x] Automatic paired debit/credit column nominations require coherent exact headers, retain each header and amount locator, and leave conflicting layouts unresolved. Synthetic stored-grid and UI tests plus unchanged real108-page scan verified; no automatic direction confirmation or ledger admission.
   - [x] Separate source-bound undated charge suggestions across page ranges, without inferred dates/direction or automatic admission. Real108-page scan finds81labelled rows on27pages, including56.16USDinterest;62zero-amount rows remain explicit and23dated suggestions unchanged. Ambiguous amounts and unsupported labels remain for manual review.
   - [x] Per-page automatic date/amount column proposals across the supplied108-page PDF:20pages have supported layouts and23dated suggestions;88pages retain explicit unavailable/ambiguous reasons. Manual review and undated interest remain separate; no automatic admission.
   - [x] Read-only page-range scan across up to50pages, with exact date/amount citations and explicit unchecked-page results. Real108-page PDF first50pages:40checked,10unchecked,15suggestions; no writes. Undated rows and changing layouts still need review.
   - [x] Save unfinished statement-editor fields and source cells separately, preserving partial amounts and revision conflict protection; five backend/eight UI tests pass.
   - [x] Save and reopen added statement-control scopes with revision-conflict protection; live real-PDF save/reload/finalization journey passes. Unsubmitted editor fields remain.
   - [x] Real-PDF ledger correction acceptance: intentionally misstated test purchase $61.26 corrected to printed $61.62 in a separate case; original source/history and exact export preserved, P3 unchanged. Fixed long decision-reason layout during walkthrough.
   - [x] Second supplied PDF: prepare 108 pages, visually review a payment and purchase, finalize as an incomplete P3 sample and verify exact source/history export (f6220fa). All originals unchanged; full-statement accuracy remains.
   - [x] Interrupted PDF preparation marks unfinished jobs failed and propagates cancellation; 13 targeted engine tests pass (f6220fa).
   - [x] Source beside row selection with clickable cell locations, bounded source-page list and narrow stacking; 19 UI tests plus real-PDF browser check pass (5f5a2a9).
   - [x] Upload a supplied real PDF through the application and queue local source preparation without AI, then reach source selection (213ed7e).56pages prepared; original unchanged. Financial reading accuracy and fullstatement coverage remain unverified.
   - [x] Inspect source-bound date/amount row suggestions and explicitly add them to pending review selection (35b6ccb).25UI tests and live3-row/2-suggestion/0-write check pass. Automatic acceptance/classification remains excluded.
   - [x] Source-bound backend date/amount row suggestions preserve uncertainty and all checked rows, with explicit columns/currency and no automatic admission (ea125fd).36tests plus route test pass; UI integration next.
   - [x] Propose explicit English named-month dates while preserving source text and unresolved year/century/glyph uncertainty (43dbbd5).24targeted tests pass; source review remains required and automatic extraction remains incomplete.
   - [ ] Identify transaction rows and column meanings: dates, amounts, accounts and money coming in or going out.
   - [ ] Link each extracted value to its exact location in the original document, including verified stored PDF cells.
   - [ ] Handle digital PDFs and scanned documents while preserving uncertainty where the source is unclear.
   - [x] Foundation: bind nominated canonical-text rows to exact source spans and source/provenance revisions; keep every candidate pending. Verified in 5d7279d, including 21 new tests. Automatic extraction remains; geometry adapter completion is recorded below.

   - [x] Foundation: verify stored PDF table/cell identity and rectangles without guessed text offsets (5ab6931). Includes repeated amounts, provenance drift, malformed geometry and generated-PDF extraction tests.

   - [x] Deliberate source selection: inspect a stored PDF table, choose rows and assign proposed column meanings without automatic transaction classification (9ddfe63). Both real PDFs passed source-binding smoke checks; full transaction accuracy remains.

   - [x] Source-byte prerequisite: compare the current case-scoped file against the saved candidate digest, refusing missing/changed sources and observed changes during reading (43b2402; 11 new tests). This is a backend prerequisite; ledger admission remains unconnected.

   - [x] Column suggestion aid: propose exact supported labels from the first ten stored rows, require explicit acceptance, and preserve a separate transaction-date role (aac46b0). No automatic transaction classification or row selection is claimed.

2. **Review uncertain readings before they enter the ledger — complete**
   - [x] Saved batch review progress, pending-only filter and next-pending-row navigation; reopened real-PDF decisions verified. First Alex case-work milestone documented in docs/loupe-alex-casework-preview.md.
   - [x] Show all saved original cells and switch source highlights beside the review form without requesting amount/date assessments. Source binding and UI scope validated; synthetic desktop/narrow browser check and 31 targeted tests pass. Real-PDF acceptance remains.
   - [x] Save deliberately selected rows from stored PDF tables separately until they are ready for use (9ddfe63). Automatic extraction/nomination remains under feature 1.
   - [x] Show questionable amounts, dates and account details alongside the source. Verified by the10September source-review, statement, analysis, comparison, export or tracing acceptance recorded above; conditional results retain their stated limits.
   - [x] Let the investigator confirm, correct or reject saved candidate readings, preserving the original and the reason for each decision (ee6edb4). Local UI verified; deliberate stored-PDF mapping is now connected. Automatic nomination and ledger materialization remain.
   - [x] Prevent retries or simultaneous candidate reviews from creating duplicate transactions in the deliberate saved-PDF workflow (27f8328, a2f4337). PostgreSQL competing writes and authenticated UI/HTTP retries preserve the original receipt and transaction IDs.
   - [x] Foundation: immutable in-memory pending candidate contract, with missing context representable (5d7279d). Persistent storage and review are now implemented below.
   - [x] Existing ledger corrections retain originals, history and reasons, with stale-review protection; manual source amount assessment is connected. These do not yet provide candidate review.

   - [x] Foundation: persist immutable candidate originals outside totals with atomic saves and same-mapping retry safety (826caee). Verified with PostgreSQL lock contention and overwrite-refusal triggers. UI completion is recorded below.

   - [x] Foundation: assess saved original amount cells through case-scoped read-only APIs, preserving uncertainty and source citations and refusing source drift (8d6425a). Verified through authenticated local HTTP; UI completion is recorded below.

   - [x] Foundation: append resolved/rejected/reopened review decisions with reasons, exact reading validation, immutable history and stale-review protection (c4ae63e). Case-scoped read/edit APIs and real PostgreSQL contention verified. Review screen completion is recorded below.

   - [x] Saved-reading UI: bounded batch/row lists, account search, original amount assessment with source image, exact review form and immutable history (ee6edb4). Creation API retries preserve original IDs.

   - [x] Provisional account setup: explicit document/currency-scoped label and reason, audit run, same-account retry protection and a guard against use from another PDF (dd7fc5b). Known-account identity/merge remains separate.

   - [x] Cross-batch source reuse review: detect repeated stored rows/overlapping source claims, expose uncomparable pairs and coverage limits, and open the affected readings (7ee220b). This is not database-enforced materialization deduplication.

   - [x] Truthful reading method: explicitly record investigator-reviewed readings without claiming native/template/model extraction or promoting their classification (08b1540). Storage, UI labels and PostgreSQL downgrade protection verified; candidate materialization remains.

   - [x] Incomplete coverage stays explicit: selected documentary financial rows remain outside verified totals even when subset arithmetic balances; reconciliation and corrections cannot silently promote them (ed656da). End-to-end admission remains.

   - [x] Durable finalization storage: keep permanent candidate/review/transaction links, refuse repeated sealed batches and later review/mapping changes, and protect source scope in PostgreSQL (f0ddde3). Atomic transaction creation and its concurrent retry acceptance remain.

   - [x] Atomic candidate writer: fresh review/account/source checks, exact whole-batch transactions, retained originals/rejections, one finalization receipt and safe retries (27f8328). PostgreSQL rollback and two competing requests verified; authenticated API and UI remain before this workflow is complete.

   - [x] Connected finalization UI: current preview, explicit coverage acceptance/reason, safe reload/retry behavior, refreshed ledger rows and source-image links (a2f4337). The larger automatic extraction and complete-statement workflows remain.

   - [x] Finalized review protection: keep originals/history and source assessment accessible, block later candidate/account edits, and verify a ledger correction preserves the receipt and original PDF citation (a7c231d). The replacement remains P3 outside verified totals.

   - [x] Source date assessment: display alternative numeric dates, unresolved years/centuries, invalid dates and original citations without selecting a reading (46a3417). Automatic date/context resolution and account uncertainty work remain.

3. **Complete financial accuracy checks — complete**
   - [x] Statement checks explicitly distinguish counted zero-amount source lines from nonzero payments; full supplied-file browser verifies62zeros across27periods without changing amounts or eligibility.
   - [x] Explain arithmetic discrepancy leads with source navigation, directional checks, bounded screening and explicit unresolved cases. Synthetic native correction/restoration browser journey and captured correction audits verified; leads never assert the cause or change classification.
   - [x] Source-bound printed total money in/out saved through PDF review and drafts, separately checked against current admitted rows, compared before/after corrections and retained in history/reports. Synthetic browser100in/30out/70closing passes; proposed30.01out shows1minor discrepancy. Older receipt identities preserved. Native format controls remain separate.
   - [x] First complete printed statement in the supplied 108-page PDF: payment, purchase and undated interest reconcile opening $6,700.18 to closing $6,637.96 owed. Other statements remain outside this acceptance (10 September).
   - [x] Undated fee/interest review preserves unknown row dates; explicit statement-end ordering requires a matching source-bound end control at finalization, retains provenance and remains P3.
   - [x] Document-wide saved review overview shows pending/resolved/rejected rows per page, unselected pages, preparation gaps and direct batch resume; it does not label selections as complete extraction.
   - [x] Statements workspace displays current balance identity and conditional running-balance checks, exact discrepancies and source navigation without overwriting prior results or changing admission (84cd821). Both possible source-row orders remain explicit.
   - [x] Account/currency timeline shows eligible and excluded bounds, internal gaps and separate overlapping statements; select a period to inspect its registered source (84cd821). This does not prove complete transaction extraction.
   - [x] Bind manually reviewed statement dates and opening/closing controls to selected PDF rows, preserving original cells and liability sign convention (d45fb02). Fresh real-PDF test correctly exposes omitted $56.16 interest; P3 remains excluded.
   - [x] Reopen saved controls beside highlighted original PDF cells and include readable controls in the export report (7716d86, 79e1ee8).
   - [x] Complete checks against supported source controls: reviewed PDF opening/closing and money-in/out totals; native camt.053, BAI2, MT940 and NACHA controls. Statements now rechecks whole native sources explicitly and downloads current results/source hashes. Source drift/missing mappings remain unavailable, and whole-source arithmetic is distinct from admitted-period totals.
   - [x] Check running balances from one transaction to the next. Verified by the10September source-review, statement, analysis, comparison, export or tracing acceptance recorded above; conditional results retain their stated limits.
   - [x] Repeat affected checks after an amount/direction correction: native camt.053, BAI2, MT940 and NACHA controls now rebind fresh source bytes and original row hashes, compare current/proposed readings and retain the audit. Source gaps/drift stay unavailable; running-balance order remains conditional. Four-format database roundtrips and synthetic camt.053 browser preview pass.
   - [x] Display discrepancies and arithmetic leads with source references, while keeping classification calculated by the system. Where the cause cannot be established, it remains explicitly unresolved; no automatic causal explanation or correction is invented.
   - [x] Existing statement balance reconciliation and correction consequences are connected; proof class is computed. Broader checks remain.

   - [x] Correction running-balance diagnostics: compare before/after under both possible source-row orders, expose unchecked intervals and retain source-linked results in the correction audit (4b70844). Proven order/coverage and native-control revalidation remain; this does not promote classification.

   - [x] Historical running-balance diagnostics: show the saved comparison in correction history, preserve original source links, and distinguish historical results from current ledger state (42e42f1).

4. **Finish duplicate handling — complete**
   - [x] Compare a second explicitly authorized case for matching ingestion hashes or stored readings; bounded full scans and paged results, no cross-case exclusion. Real-PDF pair browser check passes.
   - [x] Same-case comparison now also exposes matching ingestion hashes across different/missing recorded coverage and held documents. These source sightings never offer exclusion; identical-reading decisions retain current revision checks.
   - [x] Show matching evidence in another explicitly selected case only after verifying view permission, without changing either case.
   - [x] Bulk-loaded same/cross-case comparison avoids repeated per-document scans, with500documents/case,50,000readings and10,000period limits and no partial result. Paged10-group UI; synthetic24documents/48rows/12groups/source navigation verified read-only in877ms. Twenty-document test confirms at most10SQL statements and writer-identical revisions.
   - [x] Preserve reasons for excluding or restoring a duplicate in the existing same-case workflow, including tested concurrent decisions.

5. **Make every financial view use the authoritative ledger — complete**
   - [x] Account-group perspective with exact incoming/outgoing/net figures, explicit internal transfers counted once and excluded from the external chart, currency separation, source drill-down and captured assumptions export. Synthetic3-account browser acceptance:GBP200in,20out,180net,160internal across2pairs; changing selected accounts recalculates. Party identity resolution remains separate.
   - [x] Exact incoming/outgoing charts for date and source-label groups, selected-group totals, separate currencies and chart-to-source links; real-statement browser verified.
   - [x] Ledger table search, direction/currency/proof display filters, exact single-currency sorting and50-row pages, explicitly separate from analysis/export scope; browser verified.
   - [x] Working/verified Trends and Counterparties share captured current readings; real-statement date and label totals verified.
   - [x] Authoritative Posting graph with per-posting source arrows, account/date/population scope and distinct account/currency label groups; real-statement browser rendering verified.
   - [x] Separate working totals include current admitted P3 readings while preserving verified totals. Exact currencies, correction exclusions, account/date scope and matching JSON/HTML exports verified on two real-PDF cases (10 September).
   - [x] Live exclusion acceptance across Transactions, Counterparties, Trends and export (5aff978): synthetic400GBP excluded, all totals2100→1700, restored with originals/history retained and export hashes verified. Broader correction/legacy graph propagation remains.
   - [x] Main documentary Counterparties displays ledger label groups with exact reconciled totals, scoped filters, paged source links and decision refresh (0fe3c69).35page/14panel tests and live source-dialog check pass; equal labels do not prove identity or transfers.
   - [x] Backend/API exact counterparty source-label totals share ledger eligibility, separate currencies and retain contributing transaction/source references (5cc894e).38 summary/package tests, route test and live HTTP parity pass. UI integration remains; no identity/transfer matching claimed.
   - [x] Main documentary Transactions uses current ledger readings, filters, exact summary and source/correction/decision controls independently of graph loading (b67e365).31 page tests and live bigint/decision-dialog check pass. Counterparties migration remains.
   - [x] Exact daily/monthly ledger totals display with paged contributing-reading source links and reconciliation to the summary (8582179). Legacy graph Trends remains separate.
   - [x] Daily/monthly exact ledger posting totals share summary eligibility and retain contributing transaction/source IDs (d40474a). Time-series display and legacy graph migration remain.
   - [x] Preserve full bigint money through individual ledger JSON, table and decision identity using exact strings, with safe numeric compatibility (19a8980).
   - [x] Backend/API exact ledger posting summaries, separate currencies, explicit excluded populations and a hard no-partial-total limit (0ae8242). Display and legacy-view replacement remain.
   - [x] Connect the graph and financial analysis screens to the reviewed ledger. Verified by the10September source-review, statement, analysis, comparison, export or tracing acceptance recorded above; conditional results retain their stated limits.
   - [x] Main documentary Trends uses ledger analysis independently of graph loading; intelligence remains explicitly separate (9e0ec3a). Transactions/Counterparties graph migration remains.
   - [x] Current ledger summary display uses exact currency totals and included/excluded populations, with applied-filter scope and correction/adjudication refresh (b82d010). Legacy graph cards and other analysis views remain.
   - [x] Ensure corrections and exclusions consistently update totals, searches and money-flow views. Synthetic30.00→30.01→30.00 correction verified across Ledger, Transactions, Counterparties, Trends, Posting graph and statement controls; original/source/history preserved. Earlier exclusion/restoration acceptance remains recorded above.
   - [x] Prevent older extracted graph values from being counted alongside reviewed transactions. Documentary views use captured ledger populations; graph intelligence is an explicit separate mode. Corrected/superseded rows were excluded from current graph and totals in browser acceptance.

6. **Show missing periods and incomplete evidence — complete**
   - [x] Identify gaps and overlaps between recorded account statements with eligible printed bounds (8b6c9ad). Enclosing exports are included; oversized accounts are explicitly unavailable.
   - [x] Show which accounts and dates the recorded statement bounds cover, with exclusions and limits visible (8b6c9ad). This does not certify full transaction extraction or undated/unprocessed evidence.
   - [x] Distinguish no matching transaction found from insufficient records to know. Verified by the10September source-review, statement, analysis, comparison, export or tracing acceptance recorded above; conditional results retain their stated limits.
   - [x] Display requested-date coverage alongside applied ledger account/date filters, explicitly distinguish unknown bounds from covered dates, retain exclusions and prevent stale scope results (982c530). Wider search and exact PDF-bound navigation remain.
   - [x] Backend/API requested account/date coverage counts outside tails, preserves currency groups and exact intersecting source-period references, and returns unknown/unavailable explicitly (036f700). Filter-screen integration remains.
   - [x] Explicit account/date filters on current ledger rows, draft/apply/clear behavior, bounded case-scoped account lookup and case-switch resets (a6ee80c). Requested-interval coverage remains.
   - [x] Empty ledger answers respect account/date filters, explain that no match does not establish absence of transactions, and retain response-count discrepancy warnings even for zero rows (e13375c). Quantified search coverage and filter controls remain.

7. **Connect transactions and explain money movement — partial**
   - [x] Reviewed counterparty identity links for explicitly selected payments, immutable history, correction inheritance/override, source inspection and optional identity-grouped charts. Synthetic save/reload/source/download preserves raw labels,24.68GBPworking debits and0verified rows. Original names and future imports are not merged automatically.
   - [x] Optional source-linked equal-value transfer chains and return-flow hypotheses across accounts, bounded to two/three candidate transfers without posting reuse. Synthetic three-account/six-posting theory save/source/history verified; all pairings stay conditional, with no allocation or automatic finding.
   - [x] Connect scoped identifier comparisons to Transfers and captured scenarios: version4UUID equality and native ACH traces with explicit effective-date scope. Conflicting amounts, same-side sightings, multiple partners and unsupported scope remain visible. Synthetic source-navigation/scenario browser acceptance passes; no automatic merge or UETR assertion.
   - [x] Optional investigator-selected split-payment threshold screens exact same-direction/account/currency groups with all source readings and captured threshold. Synthetic browser:two GBP100 credits cross a GBP150 criterion;GBP250 removes the candidate; changing criteria clears old results. No automatic finding or ledger write.
   - [x] Investigator-transcribed payment claims retain quote/source, amount/date ranges, holder interpretation and explicit tolerance; compare verified/working rows without promoting P4. Human agree/disagree responses persist as Workspace notes with chosen source attachments and history. Uploaded synthetic quotation/browser/source-hash/download/review-note checks pass. Automatic assertion extraction and certified-coverage contradiction remain separate.
   - [x] Pattern review screens repeated equal amounts and nearby equal incoming/outgoing postings, retaining sources and uncertainty. Investigator reasoning can be saved as a proposed Workspace theory with grouped evidence attachments, captured readings and immutable history; synthetic browser save/reopen verified. Other typologies and claim-correlation decisions remain.
   - [x] Case context timeline joins captured ledger chronology with wider case events for review, with explicit date bases, distinct context labels, source/event drill-down, unavailable/incomplete event states, search and captured JSON. Synthetic7-posting/1-event browser journey passes; proximity is not a corroboration decision.
   - [x] Compare cross-account equal-amount/currency postings with compatible dates and preserve ambiguous alternatives.
   - [x] Explicit conditional pairing scenario counts each chosen pair once, forbids reusing a posting and exports the source snapshot and reasoning. Synthetic bigint browser journey verified; this is not a verified transfer assertion.
   - [x] Link likely transfers between accounts and investigator-reviewed parties: durable account-party assignment/removal history survives reload and selects account groups in the flow perspective. Three-account synthetic browser and exported decision history verified. Automatic counterparty identity resolution remains separate.
   - [x] Avoid counting both sides of the same transfer as separate money movements. Verified by the10September source-review, statement, analysis, comparison, export or tracing acceptance recorded above; conditional results retain their stated limits.
   - [x] Show the evidence supporting a match and distinguish exact matches from uncertain ones. Verified by the10September source-review, statement, analysis, comparison, export or tracing acceptance recorded above; conditional results retain their stated limits.
   - [x] Connect comparisons between financial records and statements or claims about payments. Verified by the10September source-review, statement, analysis, comparison, export or tracing acceptance recorded above; conditional results retain their stated limits.

8. **Produce traceable reports and exports — complete**
   - [x] Reproducible table-view export captures search, currency, direction, proof filter and deterministic row order across every matching page, alongside the full account/date/history snapshot. Real-PDF one-row61.62USD search verified against all3captured readings and JSON/HTML/PDF hashes; exact scope echoed to browser.
   - [x] Optional paginated PDF derived from the same captured ledger, with independent manifest hash; real-statement exact text and five-page layout verified. Full raw values retained in HTML/JSON. Browser download verification passed.
   - [x] Optional original-source bundle with fresh byte verification, source manifest, case ownership checks and whole-bundle limits; both supplied PDFs independently verified unchanged (5eeda00). Complete referenced files may extend beyond ledger filters.
   - [x] Include source-file PDF mappings/originals, review chains and finalization receipts in schema3 snapshot and readable report; separate review/adjudication counts.50backend/9frontend tests and real-sample hash/content verification pass. Original PDF bytes remain outside bundle.
   - [x] Primary Ledger and documentary Transactions export their applied filter scope directly, with case-switch reset and no misleading held-out-only export (51ebd77).44targeted tests and primary browser ZIP/hash checks pass.
   - [x] Format report money exactly in currency units while preserving minor units, and verify exported totals/exclusions against the summary API across case/account/date/empty scopes (96f3a3f).92 targeted tests and live HTTP/hash/layout checks pass; non-member access matrix remains.
   - [x] Bundle a readable HTML report derived from the exact captured snapshot, with scope, totals, included/excluded readings, source references and decision details; independently hash the report (8a1e051). Browser layout/download verified. Amounts use explicit minor units; polished exhibits and PDF pagination remain.
   - [x] Download the applied ledger scope as a ZIP with exact rows/totals, source references, relevant decision history and a byte-verifiable manifest (49f2b83). Browser download and digest verified; formatted reports and broader export workflow remain.
   - [x] Consistent PostgreSQL snapshot of relevant decision history plus exact JSON export manifest, with event/output bounds (001009d). Download/report UI remains; candidate-review history and fresh source-byte verification explicitly excluded.
   - [x] Internal immutable ledger snapshot captures exact rows/totals/source metadata and exclusions from one read, with stable content hash (1efe4ad). Decision history, manifest and download remain; snapshot explicitly not export-ready.
   - [x] Existing exhibit assessment now uses the exact verified/working/table-view populations, separate currencies, signed net postings, proof composition and source disclosure lists. Classification is section-specific; P3 remains illustrative and no disclosure/legal admissibility is asserted. Real-statement JSON/HTML/PDF capture and hashes verified.
   - [x] Include source references, correction history and relevant limitations. Verified by the10September source-review, statement, analysis, comparison, export or tracing acceptance recorded above; conditional results retain their stated limits.
   - [x] Ensure exported totals agree with the application. Verified by the10September source-review, statement, analysis, comparison, export or tracing acceptance recorded above; conditional results retain their stated limits.
   - [x] Record which evidence and decisions supported an exported result. Verified by the10September source-review, statement, analysis, comparison, export or tracing acceptance recorded above; conditional results retain their stated limits.

9. **Complete funds tracing — partial**
   - [x] Optional whole-withdrawal asset interpretation in single-account and network scenarios, with per-method allocation and source/basis retained; cash figures unchanged. Both browser forms/source/download verified with zero ledger writes. Partial purchases, ownership, valuation and resale substitution remain outside this calculation.
   - [x] Explicit backward timing, off by default and requiring a basis, with unchanged source dates and acyclic account dependency checks. Synthetic earlier-credit/later-debit browser scenario conserves each method, flags the backward hop and preserves source/download; circular backward dependencies are refused. Asset substitution remains separate.
   - [x] Forward tracing across 2–10 accounts, selected source-bound transfer pairs, all scoped readings, explicit openings/order/root claims and per-method conservation. Three-account browser test verifies FIFO £80, pro rata £90 and LIFO £100 remaining from a synthetic £100 claim; exact download and stale-result clearing pass. Backward tracing and asset substitution remain unsupported.
   - [x] Decimal currency entry converts exactly to minor-unit requests; readable movement amounts and source buttons. Multiple-claim browser results preserved.
   - [x] Multiple explicit deposit/claim attributions and working/verified population selection preserve original proof classes; reject excess attribution and export all assumptions. Focused23backend/12UI and working-population multiple-claim browser checks pass. Cross-account propagation remains.
   - [x] Conditional single-account tracing captures reviewed ledger/history, explicit opening/deposit/order assumptions and selected methods. Invalid/stale inputs fail without writes. Existing core and bridge tests pass.
   - [x] Conditional tracing screen compares selected methods and downloads exact hash-verified scenario bytes. 45 frontend tests, TypeScript/scoped ESLint and read-only synthetic browser acceptance pass. Unidentified withdrawals remain visible; changing assumptions clears results. Current UI supports one attributed deposit; broader multi-deposit and cross-account work remain.
   - [x] Connect existing tracing calculations to reviewed transaction history. Verified by the10September source-review, statement, analysis, comparison, export or tracing acceptance recorded above; conditional results retain their stated limits.
   - [x] Support comparison of the available tracing methods. Verified by the10September source-review, statement, analysis, comparison, export or tracing acceptance recorded above; conditional results retain their stated limits.
   - [x] Explain how assumptions, missing records and transaction ordering affect the result. Verified by the10September source-review, statement, analysis, comparison, export or tracing acceptance recorded above; conditional results retain their stated limits.
   - [x] Preserve the basis for each tracing result so it can be reviewed. Verified by the10September source-review, statement, analysis, comparison, export or tracing acceptance recorded above; conditional results retain their stated limits.

10. **Test the complete application locally — partial**
    - [x] Fresh current-schema real PostgreSQL concurrency and injected-failure acceptance: two saves/one batch, two finalizers/one receipt, full rollback after flush, idempotent retry and sealed review. Ten database guards and14subsequent application/analysis/export checks pass on the new synthetic case.
    - [x] Integrated4186backend/917financialUI/build gate and87live access checks across15read/scenario and9edit endpoints. Temporary local viewer can calculate conditional scenarios, cannot edit, and loses access immediately on membership removal; test user cleaned up.
    - [x] First real-PDF bounded UI journey: upload/local preparation → select two page4 rows → visually checked review/OCR description correction → finalize → exact export verification.0included/2P3excluded, original unchanged. Fullstatement accuracy and candidate-history export remain.
    - [x] Integrated post-migration baseline:3,827backend tests,1,032frontend unit tests,11Chromium tests, TypeScript and full ESLint pass (09c341c). Full real-PDF/AI journey and all broader features remain incomplete.
    - [x] Verify actual export membership permissions and immediate revocation with a temporary ordinary local user (cc96526): non-member/no-view denied, view-only allowed, revoked same-token denied, test user removed.
    - [x] Exercise the full journey from document upload through review, analysis and export. Both real PDFs and the complete first printed statement are recorded above; generated printed-controls journey adds six source controls, correction propagation and preserved audit exports.
    - [ ] Validate external AI processing.10September: one capped synthetic-only request with the existing project.env OpenAI configuration returned401AuthenticationError. No retries or real documents sent; a working provider connection is needed for full AI acceptance.
    - [ ] Test interrupted processing, retries, permissions and larger document sets across the completed workflow.
    - [x] Consolidated startup/testing guide in docs/loupe-local-testing.md, idempotent local tester setup and14repeatable service/migration/financial-read/export checks. Actual supplied-statement case passes; writer fixtures are explicitly separate and external AI remains unvalidated.
    - [x] Foundation: separate persistent backend/engine venvs, isolated services and synthetic HTTP/PostgreSQL/UI checks. Setup and repeatable partial-workflow scripts are documented in docs/local-application.md.

## Completion record for this window

- Schedule and retained checklist established. No new implementation has landed in
  this window yet. Earlier implementation details and test evidence are in
  docs/loupe-build-state.md. Add dated completed segments here with commit and test
  evidence, retaining all earlier entries.

- 7 September, overnight: **5ab6931** completed the stored PDF grid binding
  foundation under feature 1. All 3,596 financial tests, 895 unit tests, 11 Chromium
  tests, TypeScript and ESLint pass. Feature 1 remains partial; storage/review and
  automatic extraction are not claimed complete. Next: persistent candidates.

- 7 September, overnight: **826caee** completed candidate original storage under
  feature 2. 3,612 financial tests and all frontend gates pass. Live PostgreSQL
  contention produced one mapping/two candidates/zero ledger rows; both originals
  reject SQL updates. Next: review records and assessment, then endpoints/UI.

- 7 September, overnight: **8d6425a** connected saved-candidate amount assessment
  and read APIs under feature 2. 3,631 financial tests and all frontend gates pass;
  authenticated local HTTP returns exact original readings and their PDF rectangle.
  Candidate review decisions/UI remain next; no whole feature is newly complete.

- 7 September, overnight: **c4ae63e** completed review history and APIs under
  feature 2. 3,651 financial tests and all frontend gates pass. Real concurrent
  reviews return one 200/one 409; authenticated reopen/resolve retains history.
  Next: candidate listing/creation and review screens, then materialization.

- 7 September, overnight: **ee6edb4** connected saved-candidate review screens under
  feature 2 and mapping creation/list APIs. 3,657 financial tests, 905 unit tests,
  11 Chromium tests, TypeScript and ESLint pass. Live browser review retained five
  history events and displayed the original PDF image; authenticated creation retry
  returned original IDs. Source mapping creation UI and materialization remain.

- 7 September, overnight: **9ddfe63** connects deliberate PDF source selection under
  features 1/2. All 3,666 financial, 912 unit, 11 Chromium tests and TS/lint pass.
  Local UI save/retry preserves one pending row under the same mapping ID.
  Read-only real-PDF checks passed 153 tables/7,529 source rows; these are not
  transaction counts. Next: account setup and materialization/revalidation.

- 7 September, overnight: **dd7fc5b** adds provisional account setup under feature2.
  3,676 financial tests, 917 unit tests, 11 Chromium tests and TS/lint pass.
  Two real PostgreSQL lock waiters produced one account; browser account setup
  and candidate resolution passed without ledger admission. Next: materialization.

- 7 September, overnight: **7ee220b** adds cross-mapping source reuse checks under
  feature2. 3,685 financial tests, 922 unit tests, 11 Chromium tests and TS/lint pass.
  Live browser found one repeated source row across three compared pairs and opened
  its exact reading. Ledger materialization remains; fix account-audit run wording next.

- 7 September, overnight: **f94e347** corrects account-setup audit display. Setup
  failures stay visible without being mistaken for missing transaction imports.
  927 frontend unit tests, 11 Chromium tests, TS/lint and live UI pass; backend
  remains at the verified 3,685-test checkpoint.

## Morning handoff

Prepared 7 September 2026 before the 06:00 Dublin cutoff. The heartbeat
`continue-loupe-development` was paused through the app at approximately 04:42 UTC
(05:42 Dublin). The local application remains running. Completed work remains
checked above; none of the ten whole features is being marked finished prematurely.

| Feature | Overall status | Position at handoff |
| --- | --- | --- |
| 1. PDF import | Partial | Stored-table selection, exact source binding and real-PDF extraction checks work. Automatic import/nomination and complete transaction accuracy remain. |
| 2. Uncertain-reading review | Partial | Separate immutable originals, review/history UI, source assessment, provisional accounts and source-reuse checks work. Ledger materialization and database-enforced cross-mapping transaction deduplication remain. |
| 3. Financial accuracy checks | Partial | Earlier balance reconciliation/correction work remains connected. Broader printed controls and running-balance revalidation remain. |
| 4. Duplicate handling | Partial | Earlier same-case exclusion/restoration works. Authorized cross-case comparisons and larger-scale coverage remain. |
| 5. Authoritative ledger across views | Remaining | Graph and financial analysis still need the agreed ledger projection. |
| 6. Evidence coverage and missing periods | Remaining | Statement gaps/overlaps and coverage views remain. |
| 7. Transaction connections | Remaining | Transfer matching and explainable money movement remain. |
| 8. Reports and exports | Remaining | Connect existing components to reviewed results with matching totals and audit references. |
| 9. Funds tracing | Remaining | Connect calculations to reviewed history and expose assumptions/results. |
| 10. Full local testing | Partial | Isolated runtime and repeated synthetic HTTP/PostgreSQL/UI checks work. Upload-to-analysis/export and external AI acceptance remain. |

**Completed this window:** immutable stored PDF candidate originals and review
history, source amount assessment, row/column selection UI, provisional account
setup with recorded reasons, cross-batch source reuse checks and accurate audit
notices. Implementation commits and evidence are retained in the completion record.

**Verification:** 3,685 backend financial tests (zero skips), 927 frontend unit tests,
11 Chromium tests, TypeScript and full ESLint pass. Live synthetic checks cover
source images, exact amounts, case scope, stale reviews, immutable originals/history,
concurrent saves/reviews/account creation, retry reuse and navigation to source findings.
The last frontend-only wording change did not alter the backend test checkpoint.

**Real PDFs:** both supplied files remain byte-for-byte unchanged and outside Git.
164 pages were read locally, with 153 tables/7,529 source rows passing the source-binding
contract check; 11 pages render blank. Those source rows are not transaction counts.
No real-document database ingestion, external AI processing or transaction-accuracy
acceptance is claimed by this check.

**Local availability verified at 04:39–04:41 UTC:** frontend55174/backend58002,
engine58003, PostgreSQL55434, Neo4j57474/57687, Redis56379 and Chroma58101 respond.
Engine checks also confirm OCR/storage availability. Its OpenAI health flag only
checks that a key string exists; the isolated launcher uses a dummy key and external
AI processing is not verified. Local migration: 20260907_candidate_reviews.

**Try the new screens:** open Financial → Ledger → PDF readings in the synthetic
case `61272494-00de-4a97-8ba9-77fce4be2f24`. Select a saved batch to review readings or
check source reuse; Choose PDF rows opens deliberate source selection. The displayed
refused setup audit is an intentional stale-review test, not missing imported money.
The real PDFs have only been tested read-only, so they do not appear as ingested cases.

**Next development priority:** safely move complete reviewed candidates into the
ledger. This needs immutable candidate-to-transaction links, whole-document occurrence
handling, defensible source shape/extraction-layer provenance and reconciliation
coverage. Concrete constraints are in docs/loupe-pdf-ledger-bridge.md. No uncommitted
implementation is left. No pushes, merges or real-data changes were made.


### Extended-window checkpoint — 7 September 2026

Neil extended continuation to 09:00 Dublin, with the same five-minute schedule.
Source-byte verification foundation completed in 43b2402; 3,696 financial tests
pass with zero skips. The original ten-feature statuses remain unchanged: this
prerequisite does not yet make candidate-to-ledger admission complete. Next work
is truthful human-review provenance, followed by immutable ledger/source links
and transaction retry/concurrency protection.

Extended-window implementation08b1540 adds explicit investigator-reviewed origin.
Verified: 3,699 backend financial tests (zero skips), 927 frontend unit/11 Chromium,
TypeScript/full ESLint; local PostgreSQL constraints and downgrade guard checked.
Main feature statuses remain partial/remaining until the end-to-end work is done.

Extended-window implementationed656da preserves incomplete selected-row coverage
through computed classification, stored document metadata, reconciliation and
correction verification. 3,701 financial tests pass (zero skips); 927 frontend
unit/11 Chromium, TypeScript/full ESLint pass. Next: immutable finalization links
and source claims, then the atomic candidate-to-ledger writer.

Extended-window implementationf0ddde3 adds immutable whole-file finalization and
source/review/transaction linkage infrastructure. 3,707 financial tests pass with
zero skips; ten isolated PostgreSQL guard checks passed with all fixture rows
rolled back. End-to-end candidate admission is still incomplete: its writer,
preview, concurrent retry test and UI remain. All original features are retained.

Extended-window implementation27f8328 connects reviewed rows to the ledger at
the service layer. 3,721 backend financial tests pass (zero skips). Live synthetic
PostgreSQL confirms rollback, two contending requests, distinct equal-value rows,
one durable receipt, stable retries and sealed review history. API/UI integration
is next; incomplete-coverage P3 rows remain outside default verified totals.

Extended-window implementationa2f4337 completes the deliberate stored-grid review
to finalization UI/API connection. Verified3725 backend/934 frontend unit/11
Chromium tests, TypeScript/full ESLint and real-browser creation/retry/source
highlight checks. The original retry-protection subitem is now checked rather
than removed. Whole-feature statuses remain partial/remaining as broader automatic
extraction, uncertainty, controls/coverage and other listed capabilities still remain.

- 7 September, extended window: **a7c231d** makes finalized candidate screens
  read-only and refuses new provisional accounts before/after a racing finalization.
  All 3,728 backend financial, 937 frontend unit and 11 Chromium tests pass, plus
  TypeScript/ESLint. Synthetic browser correction replaces GBP12.34 with12.35,
  keeps P3, and retains the original highlighted source through its receipt.
  Features1/2 remain partial; no complete-application claim.

- 7 September, extended window: **46a3417** connects read-only source date
  assessment in saved candidate review. All 3,739 financial, 944 frontend unit and
  11 Chromium tests pass, plus TypeScript/ESLint. Live browser preserves both01/02
  interpretations and the missing year while highlighting the original PDF cell.
  Full automatic extraction/nomination and complete date/account review remain.

- 7 September, extended window: **aac46b0** adds explicit printed-label suggestions
  and transaction-date column support. All 3,741 financial, 950 frontend unit and
  11 Chromium tests pass, plus TypeScript/ESLint. A fresh synthetic PDF browser check
  saved only the chosen non-header row pending and preserved its mapping on retry.
  Full automatic row nomination/extraction remains; next focus is missing accuracy
  checks under feature3. Completed work remains visible above.

- 7 September, extended window: **4b70844** connects conditional running-balance
  correction diagnostics and persists the reviewed results. All 3,753 financial,
  952 frontend unit and 11 Chromium tests pass, plus TypeScript/ESLint. Synthetic
  browser/PG correction400→410 reports the introduced mismatch and retainsP3 plus
  original source navigation. Feature3 remains partial: complete controls and
  source-confirmed order/coverage are not claimed verified.

- 7 September, extended window: **8b6c9ad** connects case-scoped statement date
  coverage under feature6, now partial. All 3,763 financial,957 frontend unit and
  11 Chromium tests pass, plus TypeScript/ESLint. Synthetic browser shows the
  February gap and its absence where an enclosing export covers the same dates.
  Search integration and precise period-bound source navigation remain; no whole
  remaining feature is newly completed.

- 7 September, extended window: **42e42f1** exposes saved running-balance diagnostics
  in correction history.960 frontend unit/11 Chromium/TypeScript/ESLint pass; unchanged
  backend remains at3,763 passed financial tests. Read-only browser history/source
  check passes. Development now transitions to final verification and the morning
  handoff; all ten features and their completion marks remain above.


- 7 September, 08:53 Dublin: **e13375c** corrects scoped empty ledger answers
  and preserves incomplete-response warnings with zero returned rows.15 targeted
  unit tests, TypeScript and scoped ESLint pass; unchanged backend gates reused.
  Neil extended the ACTIVE five-minute heartbeat until13:00 Dublin (12:00 UTC).
  All ten features and earlier completion entries remain visible.


- 7 September, 09:04 Dublin: **a6ee80c** connects account/date controls to current
  ledger rows.20 targeted frontend tests, TypeScript/scoped lint and read-only
  authenticated synthetic Chromium pass: February gap returns0 rows, Clear
  restores10. No real evidence edited. Requested-interval coverage remains next;
  feature6 is still partial and every prior completed item is retained.


- 7 September, 09:16 Dublin: **036f700** adds requested-date coverage backend/API.
  Targeted coverage/router tests and authenticated synthetic HTTP pass (February
  gap28 versus enclosing export0). No source/evidence writes. The result panel is
  next; feature6 stays partial and the five-minute schedule remains ACTIVE to13:00.


- 7 September, 09:24 Dublin: **982c530** connects filtered coverage UI.15 targeted
  tests, TypeScript/scoped lint and read-only live browser pass. February0/28
  covered-day comparison and Clear behavior verified. Begin authoritative ledger
  analysis summary next; preserve source admission and computed classification.


- 7 September, 09:35 Dublin: **0ae8242** adds authoritative summary backend/API.
  37 targeted backend tests and read-only synthetic HTTP pass; exact GBP2100 and
  filtered GBP840 verified. Feature5 remains overall unfinished because no
  analysis screen is migrated yet. Next: exact summary display and invalidation.


- 7 September, 09:44 Dublin: **b82d010** connects authoritative ledger summary UI.
  43 targeted frontend tests, TypeScript/scoped lint and live synthetic exclusion/
  restoration pass (GBP2100→1700→2100). Feature5 now partial; graph views remain
  unmigrated. Status: partial1,2,3,4,5,6,10; remaining7,8,9; no whole feature complete.


- 7 September, 09:55 Dublin: **19a8980** closes individual ledger JSON precision
  loss.38 targeted backend and114 targeted frontend tests pass (contract test
  adjusted/rerun); TypeScript/scoped lint and real synthetic PostgreSQL→HTTP→UI
  bigint/negative-balance checks pass. API money fields now strings. Next: exact
  authoritative time summaries; no whole feature newly complete.


- 7 September, 10:03 Dublin: **d40474a** adds date-grouped ledger backend/API.
  32 targeted backend tests and read-only synthetic HTTP pass; date totals reconcile
  exactly with the summary and source IDs match. Next: display and contributing-row
  navigation. Feature5 stays partial; original ten-feature checklist retained.


- 7 September, 10:12 Dublin: **8582179** connects date totals/source navigation.
  21 targeted frontend tests, TypeScript/lint and live synthetic source-record check
  pass. No page-location claim for the fixture. Next scheduled unit consolidates
  accumulated changes with one full integration gate before further migration.


- 7 September, 10:21 Dublin: **421ad37** fixes integration-gate findings: missing
  package export and page query-provider/default-filter test setup. Final full
  backend3,791 pass; frontend1,001-test run had six page-test failures, all resolved
  by the24-test page rerun.11 Chromium, TypeScript/full lint pass. Next: migrate
  the top-level documentary Trends workflow to authoritative ledger data.


- 7 September, 10:31 Dublin: **9e0ec3a** migrates main documentary Trends to ledger
  analysis.36 targeted tests, TypeScript/lint and live source-linked Trends check
  pass. Feature5 stays partial; next work begins traceable authoritative exports.


- 7 September, 10:40 Dublin: **1efe4ad** adds internal deterministic snapshot
  foundation.47 targeted tests and single-SELECT proof pass. No export endpoint or
  completion claim; next is consistent decision history and accurate JSON manifest.


- 7 September, 10:50 Dublin: **001009d** captures export history under repeatable
  read with JSON-specific manifest.29 targeted tests covered/resolved and live
  synthetic concurrent-write consistency/digest checks pass; row restored. Next:
  authenticated attachment and browser download. Feature8 remains unfinished.

- Scoped export download checkpoint (49f2b83): backend31/frontend33 targeted tests,
  final six-button-test rerun, TypeScript/scoped ESLint and Chromium download pass.
  Saved ZIP independently verified: ten synthetic rows, four decisions, GBP2,100,
  matching digest/byte count. Feature8 now partial; no entire feature complete.

- Readable report checkpoint (8a1e051):32 targeted backend tests and scoped ESLint
  pass. Browser ZIP and both hashes verified, ten readings/four decisions rendered;
  screenshot inspected with no horizontal overflow. Feature8 remains partial.

- Exact report/scope checkpoint (96f3a3f):92 targeted tests, scoped ESLint and
  browser layout pass; live HTTP parity/hash checks cover five scopes. Anonymous,
  missing-case and reversed-date refusals verified. Feature8 stays partial.

- Export access checkpoint (cc96526): live four-state membership matrix passed;
  temporary user/membership removed. No ledger/evidence writes or production fix.
  Feature10 remains partial; next main documentary Transactions migration.

- Main Transactions checkpoint (b67e365):31 page tests, TypeScript/scoped ESLint,
  exact bigint/negative-balance browser check and decision dialog open/cancel pass.
  Feature5 remains partial; documentary Counterparties is the next migration.

- Counterparty-label backend checkpoint (5cc894e):38 tests plus route scope/errors
  and live case/account/empty summary parity pass. Main Counterparties UI remains.

- Counterparties UI checkpoint (0fe3c69 plus test-only lint fix):35page/14panel
  tests, TypeScript and scoped lint pass after correcting redundant test escapes;
  live totals/source dialog verified. Feature5 remains partial for broader graph,
  search and money-flow consumers. Integration suite is next.

- Integrated verification checkpoint (09c341c):all3,827backend/1,032unit/11browser
  tests passed, plus TypeScript/full ESLint. No regressions to fix. Existing probe
  test included but untouched. No full-feature completion is implied.

- Cross-view acceptance (5aff978): browser exclusion updates all three migrated
  views; exact restored snapshot, preserved original and both audit decisions
  verified. Synthetic fixture restored; now6decisions. No real evidence changes.

- Primary export checkpoint (51ebd77):44targeted tests, TypeScript/scoped ESLint
  and browser download/hash checks pass.10restored synthetic rows/6decisions;
  no evidence or ledger changes. Prepare final retained feature/demo handoff next.

- Review guide checkpoint (5975be9): docs/loupe-review-2026-09-07.md preserves
  numbered complete-subitem/remaining status and three local demos. Current API
  counts verified; generated-PDF correction-history browser demo passed read-only.
  Final health/preservation check and scheduled pause remain at11:45UTC.

- Handoff preservation checkpoint (46c4339),12:36Dublin:all three HTTP services
  healthy, synthetic10rows/2100GBP restored, both original PDF hashes unchanged,
  zero matching isolated ingestions. AI processing not tested. Schedule remains
  ACTIVE pending planned11:45UTC final handoff/pause.

- Final handoff: automation_update confirmed PAUSED at12:43Dublin, before13:00
  cutoff. App remains running. Final verification and all ten feature statuses
  recorded in running state and review guide; no whole-feature completion claim.

- 9September continuation (43dbbd5): named-month date proposals connected through
  existing saved-candidate assessment,24targeted tests passed. No live data writes;
  old local backend not listening, runtime/browser acceptance to resume next.
