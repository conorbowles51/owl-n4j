## Split amount columns and live access matrix — 10 September, about09:21Dublin

Automatic page nomination now checks both explicitly labelled money-in/out
columns when one coherent header row identifies date/debit/credit positions.
Each amount retains its original header cell and locator. Zero amounts and two
populated cells remain separate proposals; no direction convention or admission
is inferred. Conflicting repeated layouts remain unchecked.31 targeted backend
and5 scan UI tests pass; the real108-page PDF remains23dated proposals and81
undated charge rows,0writes. Synthetic stored-grid test verifies both exact
header/amount locations; no claim of a real split-column PDF acceptance.

Integrated asset/split-column gate:4186backend tests,917financialUI tests,
TypeScript, production build and scopedlint pass. Live access matrix verifies
15read/scenario endpoints and9edit endpoints over non-member, missing-view,
view-only and same-token revocation states (87checks). Read-only network asset
scenario succeeds for a viewer; edits refuse before invalid-body validation.
Temporary user/memberships removed; no financial records changed. Script
check_local_financial_access_matrix.py may rerun; reportfinancial-access-matrix.json.
This supplements earlier export membership testing; upload/worker disruption
and broader completed-workflow concurrency still need integrated acceptance.
Backend22431, log/tmp/loupe-split-runtime.out. No push. Development continues.

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

## Explicit backward timing — 10 September, about09:01Dublin

Cross-account tracing now offers an off-by-default backward timing option with
mandatory investigator basis. It permits an earlier receiving credit to carry
an allocation from its selected later debit. Recorded dates and chronology
within each account are unchanged; account dependencies determine calculation
order. Circular account dependencies are refused in this mode. Forward results
remain unchanged when no backward pair is used. This is a conditional timing
assumption, not a legal-applicability or payment-causation conclusion.

Every affected hop is flagged and the exact basis/calculation order are captured.
Frontend independently checks those flags, account order, source pairs and claim
conservation. Unsupported cycles, missing basis and stale scope return no trace.
4182backend tests,913financialUI tests, TypeScript/build/scopedlint pass.
Synthetic case3dfbafe7-fa6b-4bdd-9af5-0e97975447b9: January1receiving credit linked
toJanuary5payer debit; sevenpostings/threeaccounts/twohops. Browser default422
refusal, explicit basis, FIFO80GBP/pro-rata90/LIFO100remaining from100claim,
source navigation, exact download and stale-result clearing pass with0financial
writes. prepare_local_backward_review.py guarded seed completed; read-only
check_local_backward_journey.cjs canrerun. Reports:backward-trace-ui-check.json
and backward-trace-scenario.json underdata/local-runtime. Current backend59951,
log/tmp/loupe-backward-runtime.out. No push. Asset interpretation and remaining
extraction/identity/integrated acceptance continue.

## Repeatable local application checks — 10 September, about08:48Dublin

New local_app.py setup verifies the existing tester or creates it only on an
empty local database; it creates no case. local_app.py check optionally accepts
--case-id and uses fixed loopback services with proxy environment disabled.
It checks frontend/backend/engine, OCR/storage/databases, migration-head parity,
worker heartbeat and login. With a case it checks eight financial reads and
compares captured working totals/export hashes. Results are local-check.latest.json;
failures exit nonzero without printing tokens, response bodies or source data.
No fixture/review/ledger mutations or external provider calls. Check-only mode
without a case explicitly does not claim financial workflow validation.

Consolidated docs/loupe-local-testing.md covers both venvs, startup, idempotent
setup, current real-statement review, safe repeated browser scripts and stopping
without deleting volumes. Existing local-application.md notes remain as history.
Actual idempotent setup and all14checks pass for e8ecc646-7b29-49d6-b64d-7086a9a14ad4.
External model connectivity remains untested; the misleading nonempty-key health
flag is excluded. No push. Current backend61016 unchanged. Remaining work continues.

## Cross-account pattern hypotheses — 10 September, about08:44Dublin

Patterns optionally screens two/three candidate transfers for an equal-value
chain or return to the starting account. It requires all-account scope, excludes
unknown chronology/zero amounts, forbids posting reuse, checks forward displayed
dates and the overall window, and retains all source readings and candidate
pairings. Same-day order remains unknown; alternatives can overlap. Transfer
matching is bounded500rows/1000pairs, path extensions10,000 and total hypotheses
200; excess refuses the whole screen. No allocation, automatic finding or merge.

UI preserves explicit selection and clears results when criteria change; each
source shows its account and date basis. The displayed amount is per candidate
transfer, not a sum. Workspace theories retain the selected path, captured ledger
hash, all source attachments, investigator explanation and immutable history.
15targetedbackend and6UI tests, TypeScript/scopedlint pass. Synthetic browser case
777fa2ac-91d7-4ad1-b5ff-010601ec762c: three100GBPtransfers A→B→C→A represented by
sixpostings; sixsource attachments and threecandidate pairings saved in proposed
theorya4ee0667-5cbe-4a2a-9201-28bc07e3ec0c; source navigation/history verified.
No financial writes. Guarded prepare_local_chain_review.py and
check_local_chain_theory.cjs havecompleted: do not rerun writers. Report:
data/local-runtime/chain-theory-ui-check.json. Current backend61016,
log/tmp/loupe-chain-runtime.out. No push. Remaining development continues.

## Current native statement controls — 10 September, about08:36Dublin

Statements can explicitly recheck native file controls from fresh original bytes,
without proposing a correction. The read-only repeatable-read transaction takes
no source row lock; the correction writer retains its existing source lock.
Repeated periods in one source share one calculation per page. Source/hash/row
population drift remains unavailable. Controls apply to the whole native source,
including other periods/accounts and held current readings, and are distinctly
labelled from admitted period ledger totals. PDF controls stay separate.

The displayed statement-check page downloads its exact results, check time,
source hashes and period scope. It includes only the displayed25or fewer periods,
not every page or original files. No classification or reconciliation write.
4177backend and910financialUI tests, production build and scoped lint pass.
Final download addition: TypeScript/scopedlint and read-only browser acceptance.
Synthetic restored camt case e1642248-9df2-48b0-b098-f4ece94b0cf8:3current rows,
2balanced native checks; original SHAandchecked_at preserved in downloaded JSON.
No financial writes. Repeatable scriptcheck_local_current_native.cjs; artifacts
current-native-browser-check.json and current-native-statement-checks.json under
data/local-runtime. Current backend51333, log/tmp/loupe-current-native-runtime.out.
No push. Supported accuracy-check workflow3nowcomplete: PDF printed controls and
four native formats, correction rechecks, discrepancy diagnostics and retained
unknown causes. This does not establish complete extraction or explain every
source error causally. Remaining features1,7,9,10continue.

## Exact ledger amount ranges — 10 September, about08:30Dublin

Main Ledger now filters inclusive minimum/maximum posting amounts in an explicitly
selected currency. Decimal entry converts exactly to integer minor units. Invalid
precision/reversed ranges block table export; changing currency clears the range.
Backend capture independently validates bounds and applies them to the complete
admitted display population, preserving original account/date history separately.

4backend table-view tests,16targeted UI tests, TypeScript and scoped lint pass.
Read-only real-statement browser:USD60–70range selects the61.62purchase. Export
records6000/7000minor bounds and one row; full capture keeps all3readings. JSON,
HTML andPDF manifest hashes verified. No financial writes. Repeatable script:
scripts/check_local_amount_range.cjs. Artifacts:data/local-runtime/ledger-range-
check.json and ledger-range-export.zip. Current backend97292,
log/tmp/loupe-range-runtime.out. No push. Development continues.

## Undated PDF charge review — 10 September, about08:26Dublin

Page-range scans now supplement dated proposals with a separate exact-label
screen for supported undated interest/fee rows. Each result retains original
label and possible amount cells/locators and the source revision. Multiple
amounts stay unresolved; no date, direction or admission is inferred. Summary
and APR labels are not recognised transaction labels. Source-unavailable pages
remain explicit, and absence of a dated layout does not suppress undated review.
At most1000undated rows across50pages; excess refuses the whole result.

29targeted backend tests,4page-scan UI tests, TypeScript and scoped lint pass.
Read-only browser scan of supplied108pagePDF:81undated charge-labelled rows on
27pages (62display zero amounts), alongside unchanged23dated suggestions on20
pages. Known page3row22 purchase interest56.16USD found with exact amount cell;
zero cash-advance/other interest rows remain explicit. Browser panel visually
inspected, no financial writes. Original file unchanged. Repeatable readonly
scripts/check_local_undated_page_scan.cjs; results/check JSON under
 data/local-runtime/undated-page-scan-*.json. Current backend79431,
log/tmp/loupe-undated-runtime.out. No push. Other extraction layouts and full
application acceptance remain in progress.

## Payment identifier review — 10 September, about08:21Dublin

Transfers now connects the existing exact-identifier comparison to captured
current ledger readings. Recorded version4UUID equality is explicitly not a
claim that the source field is UETR. Native NACHA trace comparison requires its
parser provenance, routing prefix and the same recorded effective date. Bare
bank/check references and unscoped/undated ACH references remain unmatched.

Equal-value opposite postings may be proposed outside the date tolerance, with
identifier evidence retained in the scenario. Amount/currency conflicts and
same-side sightings remain separate source comparisons. All possible partners
stay visible, no posting may be selected twice, and no ledger status/proof class
changes.500rows/1000comparisons bounds refuse partial results; evidence pages10.

4172backend tests,906financialUI tests, TypeScript, production build and scoped
lint pass. Synthetic case310e8139-1957-4cf8-999c-45c40bd0b2d2 verified in browser:
100GBPdebit January1 and100GBPcredit January20 share a UUID; a101GBPcredit with
the same UUID remains separate. Zero-day tolerance still offers the identifier
pair, all3reference comparisons remain visible, both source links open, and the
scenario retains3readings represented as2conditional movements. No financial
writes in browser acceptance. Guarded seedprepare_local_reference_review.py
completed; readonlycheck_local_reference_review.cjs canrerun. Reports:
data/local-runtime/reference-browser-check.json,reference-transfer-scenario.json.
Current backend73115, log/tmp/loupe-reference-runtime.out. No push. Broader
identity resolution, extraction, tracing and integrated acceptance continue.

## Statement discrepancy leads — 10 September

Statements now screens a nonzero balance difference against the current admitted
readings. It identifies arithmetic possibilities for an extra/missing amount or
reversed direction, with source links and explicit explanations that these are
leads, not findings. Opening-sign and divisible-by-nine signatures retain the
same uncertainty. Limits refuse partial screening above5000rows or100leads.
Unknown balance identities and differences with no matching lead remain explicit.
No row, proof class or recorded reconciliation result is changed by screening.

15targeted backend tests,11UI tests, TypeScript and scoped ESLint pass. Synthetic
native case e1642248-9df2-48b0-b098-f4ece94b0cf8 browser acceptance changed a3000USD
credit to5000, inspected the2000difference/source lead, then restored3000 through
a second correction. Both decisions and native-control comparisons remain in
history; final difference is zero. Export hash and5captured readings/2correction
events verified. Guarded writer scripts/check_local_statement_delta.cjs has
completed: do not rerun it. Report:data/local-runtime/native-delta-journey.json;
export:native-delta-export.zip. Current backend37595 includes this and the final
held-source duplicate branch. No push. Development continues through remaining
matching, extraction, tracing and integrated acceptance work.

## Bulk duplicate review and source sightings — 10 September, about08:02Dublin

Same-case comparison now exposes matching recorded ingestion hashes even when
account/period coverage differs or is unavailable. Held sources remain visible
as hash sightings while their readings remain skipped. These supplementary
matches never offer exclusion. Source navigation uses a retained transaction
when available; recorded hashes are explicitly not fresh byte verification.

Same-case fingerprints, row status counts and revision inputs are bulk-loaded;
cross-case fingerprints also share a bulk load. Twenty-document test requires
at most10SQL statements and exact parity with the locked writer's revisions.
Bounds:500documents percase,50,000readings,10,000periods; exceeding a bound refuses
the whole comparison. Reading/hash groups page10at a time; page position is
clamped afterrefresh. Existing exclusion/restoration behavior is unchanged.

All4150backend tests and901financialUI tests/build/scopedlint pass. Final held-file
sighting addition has13backend and12frontend targeted tests passing, plusTypeScript.
Syntheticcase561bc2db-c038-40e5-843e-f3b9dea2a08c:24documents/48readings/12readinggroups,
onehashgroup acrosscoverage; browser10+2paging andsource navigation pass with0writes,
877mscomparison. Seed scriptprepare_local_duplicate_review.py refusesrepeatwrites;
readonlycheck_local_duplicate_bulk.cjs canrerun. The seed initially usedthe test
factory's unrelated file digest; onlythese24synthetic file metadata records were
aligned tothe actual generatedsource. No real evidence orledgerreading changed.
Report:data/local-runtime/duplicate-bulk-browser-check.json. Backend36700 contains
bulkcomparison; finalheld-sourcebranch willload atnextbackendrestart. No push.
Documentduplicateworkflow4nowcomplete withinthese supportedbounds; transaction
identity/reconciliation istracked separately under7. Work continues.

## Connected exhibit exports — 10 September, about07:47Dublin

The existing exhibit engine now assesses exact verified, working and table-view
populations separately within captured ledger exports. Currency/net-posting/class
composition, ordered row references and source hashes are retained. Empty sets
stay unavailable; excluded-source display populations are not classified as
summary candidates. Source-file inclusion does not assert disclosure. Whole
archives include history/other rows, so no single legal category is claimed for
the archive and the software does not determine legal admissibility.

Adapted legacy P3 caveat wording to the reviewed-PDF workflow: P3 can reflect
incomplete coverage or interpretation even when arithmetic agrees. Classification
remains conservative. Report includes assessment reasons, outstanding software
conditions and review points separately, plus source disclosure lists.

All4147backend financial tests pass; final wording change has32targetedbackend
and12export-button tests passing. Reused899UI/build/lint verification from the
party batch for unchanged components. Real-statement filtered export verified
read-only: working netUSD62.22; selected purchase netUSD-61.62; bothP3 illustrative;
no verified rows; disclosure unrecorded. JSON/PDF hashes verified and both new
assessment pages visually inspected in7-pagePDF. Scripts:
check_local_exhibit_export.cjs and verify_local_exhibit_export.py. Artifacts:
data/local-runtime/ledger-exhibit-export.zip and ledger-exhibit-verification.json.
Backend15878, log/tmp/loupe-exhibit-runtime.out. No push. Feature8nowcomplete for
its specified report/export workflow; other outstanding features remain.

## Durable account-party links — 10 September, about07:39Dublin

Account-to-party decisions are retained as ordered immutable adjudication events,
replayed rather than stored by overwriting account names. Case-scoped assignments,
removals and reassignments require a reason and current revision. Source account
identifiers/holder names, postings and proof classes stay unchanged. Directory
limits1000accounts/5000events; batch changes at most100accounts. No automatic name
matching, LEI lookup or raw-counterparty entity resolution is claimed.

Transfers now opens the party directory, saves/reopens links and selects linked
accounts into the captured perspective. Download includes the exact party-link
history/revision. Main ledger export now also captures decisions about referenced
accounts. Synthetic case7d7d04f7-012f-4dc4-bc03-30351f3db15a: three accounts linked to
Synthetic account group; browser reloaded and verified selection and both exports.
No real account-ownership claim is made. Guarded writer:
scripts/check_local_account_parties.cjs; --read-only repeats acceptance without
new decisions. Reports and exports:data/local-runtime/account-parties-browser-check.json,
account-party-perspective.json,account-party-ledger-export.zip. ZIP contains all
three assignment events and account scope. Local migration20260910_account_parties
applied; current backend18837, log/tmp/loupe-party-runtime.out.

Five new service tests and34targetedUI tests pass; full899financial UI tests,
production build and scoped lint pass. Full4141backend run had one expected route
inventory failure for the new endpoint; inventory updated and26targeted route/service tests pass. No push/deployment. Work continues through remaining scope.

## Native correction controls — 10 September, about07:28Dublin

Continued development; no deployment/push. Source-bound native correction checks
now cover all four supported formats, retaining unmapped records and the actual
child-trailer basis for higher-level controls. Current/proposed controls appear
in review and saved correction history. Fresh bytes must match the original SHA;
all original row hashes and current row/account populations must match. Bounded
at16MiB/1000originals/2000historical readings. Recorded original ledger dates give
the explicit century context; an unreproducible original parse is unavailable.
Human reinterpretations retain P3 reservations even when arithmetic agrees.

Also fixed camt.053 separate credit/debit count checks, including count-only
summaries. Overall counts can no longer hide an incorrect directional split.
All4136financial backend tests pass, including four native-format correction
and audit roundtrips. All896financial frontend tests, the production build and scoped ESLint pass.

Synthetic browser case e1642248-9df2-48b0-b098-f4ece94b0cf8 verifies actual uploaded
camt.053 ingestion and source-bound correction preview with visible discrepancy;
no correction saved in that browser case. Source fixture is explicitly synthetic.
Report:data/local-runtime/native-controls-browser-check.json; guarded writer
scripts/check_local_native_controls.cjs must not rerun afterverified.
Backend session56692 uses current implementation; log/tmp/loupe-native-runtime.out.
Remaining broader application work stays on the retained checklist.

# Loupe build state

## Current position — 9 September 2026, Codex continuation

**Read this section first. It supersedes the older status, permission and sandbox
claims preserved below.** The older detailed decisions remain useful, but dates,
completed-item claims and environment recipes in that history are not current.

### Active full-scope development — 10 September, continued

Neil explicitly rejected early-preview handoffs: finish the complete agreed
financial application and UI, keep working across intermediate units. No push yet.
Current work continues through the remaining full checklist. Do not stop because a
small unit or manual-preview test passed. No push or deployment performed.

Completed in this continuation:
- Document-wide saved review progress, pending-row resume and explicit unselected pages.
- First complete printed statement (PDF pages 1–3): payment18000, purchase6162,
  interest5616 minor USD; owed opening670018 to closing663796 reconciles exactly.
  Undated interest retains null row dates and uses a source-bound statement-end
  ordering date only. This does not cover the other statements in the108-page PDF.
- Trends and Counterparties now offer working P3/verified populations with exact,
  consistently filtered source readings. Real-statement browser acceptance passed.
- Statement controls can be saved/reloaded before finalization. Revision conflicts
  prevent overwriting another reviewer's draft; finalized files refuse edits.
  Live save/reopen/load/finalize acceptance passed in isolated case
  2da970d0-b96b-4928-a23d-14f5e03407bb. Only added control scopes are saved;
  partially filled editor fields are not yet saved. Migration20260910_statement_drafts
  applied locally only; supports up to100 explicit statement scopes.
- Transfers tab compares compatible cross-account postings, exposes ambiguous
  alternatives, prevents source reuse and exports conditional pair-once scenarios.
  Exact bigint synthetic browser acceptance passed (case28fcae19-9673-4f85-9473-496c5828c85f).
  Pairings are investigator hypotheses, not verified ledger relationships.
- Posting graph now uses captured authoritative ledger rows, source-bound arrows,
  per-account/currency label groups and working/verified filters. Real-statement
  browser rendering inspected and passed; labels do not establish party identity.
- Explicit optional counterparty-as-printed review field preserves exact labels
  through review history and materialization without increasing proof class.
  Focused backend46tests passed; integration verification follows.

Full-statement case e8ecc646-7b29-49d6-b64d-7086a9a14ad4, file
f256eda2-7ac7-46e9-855b-01a0ed0d7785. Persistent acceptance reports in
 data/local-runtime: full-statement-review-check.json,
 statement-draft-journey-check.json, transfer-review-check.json.
Completed writer scripts must not be rerun against these saved cases. Originals
and all previous test cases preserved. Current backend session51672 uses
/tmp/loupe-working-tracing-runtime.out and includes counterparty and tracing changes.

Verification: integrated4033financial backend and855financial UI tests plus
production build passed. Subsequent tracing extension adds multiple deposit
attributions and explicit working/verified population without changing P3 source
classes;23focused backend and12UI tests pass. Multiple-claim working-population browser acceptance passed, including exact
downloaded scenario hashes and clearing results when assumptions change. No full-feature completion claim. Continue through remaining
PDF extraction, review persistence, cross-case duplicates, tracing and reporting.

### Cross-view correction acceptance — 10 September, about07:03 Dublin

4f25dada saves reproducible table export locally, no push.40additional financial
page/correctable-ledger tests pass. Final runtime64512 includes CORS exposure;
HTTP verified actual allowed origin127.0.0.1:55174 and all scope headers.

Synthetic printed-total case d72a4ac0-f990-415e-be89-838f955e6af2: browser changed
Office cost30.00→30.01 and verified Ledger, Transactions, Counterparties, Trends,
Posting graph and printed statement controls. Restored30.00 with a second explicit
correction. Two current rows remain;P3 unchanged. Export preserves4readings,
2correction events with before/after printed-total audits; snapshot hash verified.
Original1417e855-67d3-41c2-b739-b7adf90c4a87,
temporary132f7eb6-da9f-4103-88da-cb4588021d34,
currentaa66950f-0c9b-442b-84d3-c7dfbe965708. Do not rerun the completed writer
scripts/check_local_correction_across_views.cjs. Reports:
data/local-runtime/correction-across-views-check.json and correction-across-views-export.zip.

Retained checklist now marks workflows2(uncertain-reading review),5(authoritative
ledger views) and6(recorded evidence coverage) complete on their listed scope.
Seven broader features retain remaining work, including native control revalidation,
automatic extraction/claim processing, party resolution and remaining design scope.
This is not a whole-application completion or permission to deploy. Keep working.

### Reproducible ledger table export — 10 September, about06:57 Dublin

d770f805 saves printed incoming/outgoing controls locally. No push. Added a table
view inside the captured JSON/HTML/PDF export: exact search/currency/direction/proof
filters, deterministic display order (ordering date, source row, UUID tie-break),
all matching row IDs across table pages. Full applied account/date snapshot and
history retained, with explicit wording that main totals describe that full scope.
Browser refuses a different view echo; amount sorting refuses mixed currencies.
Table export controls compact, separate from main snapshot download. CORS exposes
scope verification headers for separately hosted configured frontends.

Read-only real-statement casee8ecc646-7b29-49d6-b64d-7086a9a14ad4:searchTSP*COPPER,
USD/debit/P3/largest-first gives1row61.62USD; export retains all3source readings.
JSON/HTML/PDF hashes verified;6page PDF table view visually checked onpage3.
Reports data/local-runtime/ledger-table-view-{check,export-check}.json and
ledger-table-view-export.zip.37initial/61export-query backend tests,30UI tests,
TypeScript/scoped lint pass. Current backend89999 (/tmp/loupe-table-view-runtime.out);
restart required to include the final CORS header exposure. This is an intermediate
checkpoint; continue full scope, no push/deploy.

### Printed incoming/outgoing controls — 10 September, about06:45 Dublin

b358fbe1 saves automatic PDF columns and split-payment screening locally. No push.
Printed total money in/out now bind to exact PDF cells through statement review,
unfinished editor drafts, sealed finalization, source inspection and HTML/PDF export.
Optional fields preserve older receipt/draft serialization and retry identities.
Totals are nonnegative magnitudes, independent of liability balance convention;
UI explicitly excludes partial purchase subtotals from whole outgoing totals.
Current admitted-side checks show exact differences and unknown controls separately.
Correction preview computes both sides before/after; the append-only correction
audit retains these comparisons and the history UI displays them. P3 is unchanged;
this does not claim native control verification or complete extraction.

Generated synthetic statement, visibly labelled NOT BANK EVIDENCE, uploaded and
prepared through the browser into cased72a4ac0-f990-415e-be89-838f955e6af2,
file0ac7ff2d-a188-4448-9a93-2eebafa8e441,
account239d5270-3671-4cbc-a730-445baf1b552e. Two reviewed rows:GBP100in/30out;
opening0,closing70; all six controls saved/source-bound/finalized. Browser current
checks balanced, proposed30.01out gives1minor discrepancy; no correction written
in this browser case. Read-only source highlight/export passed. Four-page PDF and
JSON/HTML/PDF hashes verified; printed direction controls visible on page4.
Reports data/local-runtime/printed-totals-{intake,journey,analysis,export}-check.json,
printed-totals-export.zip. Completed intake/journey writers refuse reruns; the
journey resumed once from its untouched review checkpoint after test selector fixes.
Do not reuse its resume flag after verified status. Original supplied PDFs untouched.

Validation:98targeted backend checks initially found/fixed old-draft serialization
and legacy-period test assumptions;49focused correction checks then passed.
41existing UI plus7new/updated UI checks passed. Integrated4116backend run found
one missing public-package export; fixed and rerun package/printed checks.891financial
UI tests, production build and scoped ESLint passed (removed an unused schema export
from the component for fast-refresh lint). Native controls remain explicitly pending.
Current backend88942, /tmp/loupe-printed-totals-runtime.out. Continue full scope;
no early handoff or deployment. Git stale empty Aug30index.lock was verified unowned
and removed during the previous local commit; normal index operations work again.

### Automatic PDF columns and split-payment screen — 10 September, about06:26 Dublin

bc1ef447 saves payment-claim review locally; no push. Automatic per-page PDF
column proposals now read all108pages in bounded50page batches.20pages have
supported date/amount layouts,23dated suggestions;88pages retain reasons for no
accepted layout. Page3 recovers date0/amount2 and both dated rows; undated
interest remains separate. No rows saved/admitted. Browser report:
data/local-runtime/automatic-page-scan-check.json and full results beside it.
Five backend and13UI targeted tests, TypeScript/lint passed.

Added optional split-payment threshold screening: explicit currency/decimal
amount, same-account/direction exact sum, maximal forward windows, all source
readings (up to50), overlapping-window caveat and threshold retained in proposed
Workspace theory. No implicit regulatory amount, misconduct conclusion or proof
promotion. Synthetic browser7d7d04f7-012f-4dc4-bc03-30351f3db15a:twoGBP100credits
crossGBP150, failGBP250; changed criteria clear results and0is refused;0ledger
writes. Report data/local-runtime/split-payment-screen-check.json.13backend and
4frontend focused tests passed. Subsequent integrated4085backend financial/
888financial UI tests and production build passed. TypeScript test-fixture literal
types corrected during the gate; no product failure remained.
Current backend session90685, /tmp/loupe-threshold-runtime.out. Earlier runtime
session references below are historical. Native-control revalidation is still
reserved after corrections, not silently equated with opening/closing arithmetic.
The retained checklist now checks several older broad subitems whose connected
acceptance has been completed; original descriptions/history remain visible.
Continue full development; this checkpoint is not a handoff or completion claim.

### Latest cross-account continuation — 10 September, about05:30 Dublin

552986db saved exact charts, ledger browsing and decimal tracing inputs locally.
Forward cross-account tracing now implemented: explicit selected transfer pairs,
all selected-currency current readings, 2–10 account openings, root deposit claims,
reviewed chronological order, five core methods and root-claim conservation.
Source-only statement-end dates are excluded from transfer nomination but remain
in account calculation with an explicit timing warning. No proof-class changes.

Verified three-account synthetic browser case7d7d04f7-012f-4dc4-bc03-30351f3db15a:
7postings,2hops,rootGBP100,remainingFIFO80/pro-rata90/LIFO100. Downloaded scenario
hash and exact bytes verified; changed assumptions remove stale results;0ledger
writes. Fixture writer scripts/prepare_local_network_review.py refuses reruns.
Reports data/local-runtime/network-review-check.json,network-trace-ui-check.json,
network-trace-scenario.json. This is synthetic evidence, not a real-bank transfer.

Integrated4064financial backend tests and874financial UI tests passed; production
build passed. Final comparison-table/source-date warning polish:8focused UI tests,
TypeScript and lint pass. Backend current session54918, log /tmp/loupe-network-runtime.out.
No push. Continue full scope, especially timeline/correlation, perspective selection
and evidence-linked hypotheses; never treat this checkpoint as a preview handoff.

### Case-context timeline — 10 September, about05:37 Dublin

e744bbe3 saves cross-account tracing locally. No push. Added captured ledger
chronology and Case context tab: value-date-first with labelled fallbacks,
statement-end-only caveats, separate wider case events, search/type filters,
source/event details, bounded completeness states and captured JSON export.
Graph/ledger fetched separately; no simultaneous cross-database snapshot claim,
no amounts from case events enter ledger totals, proximity is not correlation.

Focused3backend tests and39UI tests passed. Syntheticnetworkcase nowhasone
clearly labelled Meeting event. Browser verifies7postings+1event,detailpanel,
search,downloadscope/hashreference,verified0/P3excluded7,0financialwrites.
Fixture writer scripts/prepare_local_financial_context.py refuses repeats;
read-only check scripts/check_local_financial_context.cjs. Reports in
 data/local-runtime/financial-context-{fixture,ui-check,export}.json.
Backend current session87014, log /tmp/loupe-timeline-runtime.out.
Continue full scope: perspective flow and persistent evidence-linked hypotheses
and correlation decisions remain. Do not stop after this unit.

### Account-group perspective — 10 September, about05:44 Dublin

309f3bd7 saves case-context timeline locally. Added account-group flow in Transfers:
selected explicit scenario pairs count once, internal movements stay outside the
external-flow chart, unpaired labels remain local to each account. Exact BigInt
net must agree with selected original postings. Snapshot/assumptions/result export
captures the selected account set. Changing pair assumptions falls back visibly to
unpaired readings until recalculated. No party identity assertion or ledger writes.

Synthetic3-account browser passed GBP200in/20out/180net/160internal,2internalpairs;
changing account selection recalculates and downloaded source scope matches.
Script scripts/check_local_account_perspective.cjs, reports
 data/local-runtime/account-perspective-{ui-check,export}.json. Backend session60692
log /tmp/loupe-perspective-runtime.out. Original real PDFs and prior cases preserved.

42focused backend and11UI tests passed; integrated880financial UI and production
build passed. Integrated4067backend tests found one old export test decoding native
PDF bytes as HTML. Corrected that format assumption;38export-manifest tests pass
with native PDF libraries. Full backend rerun will accompany next integration gate.
No push; keep working through remaining hypotheses/correlation and complete PDF
review/analysis acceptance. This is a development checkpoint, not a handoff.

### Pattern review and persistent theories — 10 September, about05:52 Dublin

aebbd0e4 saves account-group flow locally. Pattern review now screens two explicit
rules (repeated equal amounts; equal incoming/outgoing amounts within0–30days),
using exact amounts, account/currency separation, stated date basis and bounded
complete results. Unknown statement-end-only timing is excluded. No misconduct,
common-funds or corroboration conclusion is made.

The investigator can save their own reasoning as a proposed Workspace theory.
Canonical Workspace API preserves source links grouped by evidence file, exact
captured row/provenance metadata, snapshot reference and revision/event history.
Synthetic browser saved and independently reread theory610fb970-13fc-48e9-8c7e-cfcf8e1ccc8d
in case7d7d04f7-012f-4dc4-bc03-30351f3db15a:2evidence links,P3unchanged,0ledgerwrites.
Script scripts/check_local_pattern_theory.cjs refuses reruns after its persistent
checkpoint data/local-runtime/pattern-theory-ui-check.json (status verified).
Nine backend tests (including inherited chronology checks),39UI tests,TypeScript
and scoped lint pass. Missing tab-content connection was fixed and now tested.
Backend session7571, log /tmp/loupe-pattern-runtime.out. Full scope continues;
next payment-claim comparison and broader PDF end-to-end acceptance remain.
No push/deploy. Do not pause for a preview handoff.

### Payment-claim comparison — 10 September, about06:07 Dublin

fdc8d017 saves pattern review locally. Added payment-claim comparison under Patterns:
investigator-selected source file and quotation/location; explicit amount/date ranges,
account-holder assumption and tolerance; existing correlation rules over captured
ledger chronology; preserved P4 and source classes. No certified completeness claim:
unknown coverage cannot yield a contradiction. Statement reconciliation is reported
unknown rather than as a failure. Verified and working populations stay explicit.

Uploaded synthetic-payment-claim.txt in syntheticcase7d7d04f7-012f-4dc4-bc03-30351f3db15a;
file04935d4a-0aa6-4f4f-8ce7-c1b3d94bd3ee. Browser source hash/download verified;
verified result unresolved with0rows; working result conditional corroboration
with3compared readings and unknown counterparty caveat. Editing bounds clears it.
A human agree/disagree response can be saved with up to20 selected supporting
readings in canonical Workspace notes (quote/source metadata and immutable history).
Browser note f45183b2-762d-43d9-a852-6d0b86d0dfbd verified2source links, P4unchanged,
0ledgerwrites. Scripts/check_local_claim_comparison.cjs andcheck_local_claim_decision.cjs
have completed checkpoint guards; do not rerun writers. Reports/export in
 data/local-runtime/claim-{comparison,decision}-ui-check.json andclaim-comparison-export.json.

Integrated4079financial backend and885financial UI tests pass, production build,
TypeScript and scoped lint pass. Native PDF test format issue nowresolved in full
suite. Backend session5349, log /tmp/loupe-claim-runtime.out. No push/deployment.
Continue remaining PDF intake/layout nomination and full review acceptance, then
reassess retained checklist against actual completed workflows. Do not stop here.

### Further full-scope work — 10 September

Local commit c39d23ca saves working analysis, posting graph, control drafts,
conditional transfer scenarios and multiple-attribution working tracing. No push.

Subsequent changes (continue until complete):
- Cross-case document comparison with explicit second-case view authorization,
  indistinguishable inaccessible/missing second-case responses, bounded complete
  scans and no exclusions. Real-PDF case-pair browser acceptance passed: identical
  ingestion hash, different recorded reading identities, zero financial writes.
- Unfinished statement editor fields/source cells can be saved separately from
  reviewed scopes. Revision conflicts and file/case ownership checked. Existing
  scope-only saves retain the editor. Migration20260910_statement_editor applied
  locally. Five backend/eight targeted UI tests passed.
- Optional paginated PDF in ledger ZIP, derived from the captured snapshot and
  independently hashed in the manifest. No external resources load during render.
  Real statement rendered to five pages: exact working totals, statement-end-only
  date caveat, controls and page bounds verified; representative pages visually
  inspected. Full raw data remains in HTML/JSON. Browser download check passed.

Latest combined gates after PDF:4042financial backend and862financial UI tests
passed, with production build. Package export issue corrected. Page-range PDF
scan added:11backend and12UI focused tests passed. First50pages of the real108-page
PDF yielded40checked/10unchecked pages and15suggestions, including both known
dated first-statement rows; undated interest remains explicitly separate. No writes.
Current backend session72261, log /tmp/loupe-page-scan-runtime.out; latest session recorded by
live tools. PDF migration and script cache paths are local only. Full scope remains
active; no early-preview stopping point or deployment blocker.

### Visual analysis continuation — 10 September, about05:05 Dublin

adfa960f saved cross-case comparison, unfinished editor persistence, PDF export
and page-range nomination locally. No push. Following visual work is now tested:
- Incoming/outgoing diverging bars for exact date/source-label groups, explicit
  currency separation, selectable group totals and chart-to-source navigation.
  Month buckets label the month rather than suggesting a first-of-month posting.
  Chart selection is explicitly separate from exported account/date scope.
- Tracing accepts decimal currency amounts, converts exactly to minor-unit API
  inputs, displays readable amounts and offers per-movement source buttons.
  Multiple-claim working-population browser acceptance preserves exact results.
- Ledger table search, currency/direction/proof filters, exact single-currency
  amount sorting and50-row display pages. Default ledger order preserved. Table
  search is explicitly a view over loaded rows, not the exported analysis scope.
  Real-statement search, sorting, direction filtering, chart sources and PDF
  download all passed without financial writes.
Verification:871financial UI tests and production build pass; backend unchanged
since page scanner (4042integrated +11targeted page-scan/package checks). Current
runtime backend72261 /tmp/loupe-page-scan-runtime.out.
Next: cross-account conditional tracing over explicit transfer pairings, preserving
per-hop source rows, proof classes, opening/attribution/order assumptions and
alternative-method results. No silent graph-path or backward-tracing assumptions.
Continue through remaining full scope; do not stop at this intermediate unit.

### Working totals and usable manual-preview checkpoint — 10 September 2026

Neil explicitly clarified: deployment is not blocked; pushing triggers the existing
server deployment. Do not push before a useful tested build. No push performed.
The limited manual-review preview now includes separate working totals in the
ledger and exact JSON/HTML exports. Current admitted P3 readings count here while
verified totals remain unchanged. Superseded, quarantined, rejected and excluded
source readings do not enter working totals; currencies and integer precision are
preserved. Existing account/date filters apply. Compact UI displays money together,
with calculation explanations expandable and classification limits still visible.

Verification: 3,947 financial backend tests; 834 financial UI tests; TypeScript,
production build and scoped lint pass. Read-only browser checks on fresh preview
case ccae1db4-43f8-4f93-b5b8-b744e4d50af9 and corrected case
 ea81df83-814c-4f9e-b3a8-3a989190b920 show 18000 credit, 6162 debit, 11838 net USD
minor units, matching both downloaded snapshots/reports. Corrected case excludes
one superseded reading. Verified totals remain zero with 2/3 excluded readings.
Case-view authorization tested: nonmember/no-view/revoked403, view-only200; temporary
user removed. No financial writes or original-PDF changes during acceptance.

Backend session41593 serves this implementation, log /tmp/loupe-working-runtime.out.
Acceptance script scripts/check_local_working_totals.cjs; logs
/tmp/loupe-working-{financial,financial-ui,build,live,access}.out. Earlier integrated
Workspace/Dossier/source-viewer tests remain valid. The existing local preview is
usable for bounded manual PDF review, corrections, statement checks and exports;
full-statement extraction and broader analysis remain on the checklist. No claim
of full financial feature completion or deployment. The instruction to stop at this limited-preview
checkpoint was superseded by Neil: continue through the complete agreed financial
application, including the UI. Do not stop at preview or intermediate milestones.
No background schedule started.

### Limited-preview local release candidate — integrated checkpoint

808cf691 integrates local 59e56a2d and remote f76524e with both parents retained.
Normal git merge failed with `fatal: stash failed` without changing tracked files;
used git merge-tree, applied its tracked tree with collision checks, resolved five
files, and committed the tested tree with both parents. No push or deploy.

Preserved remote navigation/pinning/Workspace/Dossiers and local processing guards.
Remote removed stale processing-status semantics, so removed obsolete sidebar stale
panel instead of restoring an impossible status. PDF source-preparation now uses
an explicit evidenceAPI.preparePdfReview method whose mode is fixed to pdf_review;
no exemption for general processing. Updated incoming pin tests for guarded hook.
Added missing financial package exports and missing receipt table to a legacy source
fixture. Viewer Chromium selector distinguishes iframe from newly titled heading.

Added migration merge 20260909_preview_merge joining 20260907_candidate_finalizations
and 20260902_workspace_ai. Local isolated upgrade succeeded. 3,926 financial tests,
51 Workspace/Dossier pytest tests, 1,010 UI unit tests pass. Chromium 50 passed in
suite + final failed selector fixed and passed individually (51). Production build
and scoped lint pass. Backend venv now also has pytest 8.4.2 for incoming tests.

Integrated runtime backend session 49852; log /tmp/loupe-preview-integrated-runtime.out.
Fresh real-PDF case ccae1db4-43f8-4f93-b5b8-b744e4d50af9, file
b807ba23-b704-4edc-9499-c0a1d2853f20; receipt 5df7ed86-f5f0-444c-a175-bd8b9fefd9d4.
Two actual page-3 readings 18000 credit/6162 debit, P3; exported exact values/history
and hashes verified. Scripts check_local_pdf_intake_ui.cjs preview and
check_local_second_pdf_review.cjs preview refuse repeated writes via checkpoints.
Artifacts preview-pdf-{intake,review}-check.json, preview-pdf-sample-export.zip under
 data/local-runtime. Existing real cases unchanged; original PDF unchanged.

Local limited-preview release candidate checkpoint achieved. Neil confirmed that
pushing the repository triggers the existing deployment script. There is no
deployment blocker. Do not push until the application is useful and tested.
No deployment or Alex account access is verified.
User explicitly asked to continue until limited preview, then report. See
 docs/loupe-alex-casework-preview.md for handoff gates and exact scope. Do not claim
full core release; accelerated core-release estimate remains
 docs/loupe-release-estimate-2026-09-09.md. No background schedule started.

### Alex case-work preview milestone — 9 September 2026

Neil asked to keep developing and select a useful point for Alex to start a case.
Chosen handoff: create/upload/manual PDF review/save/resume, then optional bounded
finalization/correction/statement checks/export. Do not wait for all automatic
extraction or money-flow analysis. Guide: docs/loupe-alex-casework-preview.md.

Added server-backed current batch review progress (pending/resolved/rejected),
pending-only filtering and next-pending-row action. Pagination clamps after review
updates. Review work now appears before reuse/finalization actions to avoid
encouraging premature sealing. 16 targeted UI tests pass, TypeScript/scoped lint
pass; read-only browser reopened saved real-PDF batch twice, 2 resolved / 0 pending,
zero writes. Script check_local_review_progress.cjs, report
 data/local-runtime/review-progress-check.json. No draft-persistence claim: only
recorded decisions survive; unsubmitted forms/statement previews are not saved.

Release preparation found remote integration branch now f76524e, four commits
beyond old remote tip. Local branch retains 317 earlier unpublished commits before
this segment. Merge-tree check (no working-tree merge performed) reports five
conflicts: EvidenceContextSidebar.tsx, FileListPanel.tsx, FileListToolbar.tsx,
FileRow.tsx, vitest.config.ts. Production frontend build at 2ce6604 passed; Alembic
has one head 20260907_candidate_finalizations. No push/deploy performed. Watched
branch/site URL still unconfirmed; do not assume local sample records go to server.
Current user priority is continued development toward Alex's case-work handoff.

### Real-PDF correction journey verified — 9 September 2026

Fresh isolated case ea81df83-814c-4f9e-b3a8-3a989190b920, evidence
be641df2-c498-4f92-91bd-8abab499b1e4. Test deliberately entered purchase $61.26
rather than the original PDF page 3's $61.62; reasons explicitly identify this
as a test error. UI preview/record correction restores $61.62, original reading
remains superseded, replacement P3 excluded. Original transaction
aa0dd4e9-3345-4df2-99e1-12fac552e1ac, replacement
016a65e8-794c-4440-8b4c-0bc4fd888a4a, decision
bfd114f9-a143-4df2-8fac-95f15188efc5. No source file edits or changes to earlier
finalized samples. Independent export verification checks 6126 → 6162 exact values,
original candidate cell $61.62, identical page-3 locator, before/after decision,
snapshot/report hashes, 0 included / 3 excluded (including the superseded reading).

Original-source navigation from Decisions verified read-only with actual PDF
page 3 rendered. Found/fixed long correction reasons forcing decision columns
outside desktop viewport: fixed table layout and wrapping keep all four desktop
columns visible; narrow view retains contained horizontal scroll. 24 targeted UI
tests pass; TypeScript and scoped ESLint pass. Read-only check
check_local_real_pdf_correction_history.cjs safe to repeat. **Do not rerun writers**
prepare_local_real_pdf_correction.cjs or check_local_real_pdf_correction.cjs.
Artifacts correction-pdf-{intake,setup}-check.json, real-pdf-correction-check.json,
real-pdf-corrected-export.zip, real-pdf-correction-{export-verification,history-check}.json
in data/local-runtime. Independent verifier verify_local_real_pdf_correction.py.

Backend now session 99026, /tmp/loupe-neilbyrne-controls-report-runtime.out, includes
readable-control report. Practical bounded upload → review → finalization → ledger
correction → retained source/decision → exact export journey is now checked against
supplied real PDFs. This does not finish full-statement extraction/coverage,
full printed-control revalidation, or wider analytical UI. Retain all checklist
items; do not treat the bounded sample as a whole-document accuracy claim.

### Reviewed statement controls completed — 9 September 2026

d45fb02 connects optional reviewed statement bounds/balances to PDF finalization.
Explicit candidate assignment, account/currency, original stored control cells,
reviewed dates/exact signed balances, balance convention and reason are bound into
a fresh preview digest. Finalization rechecks sources, creates periods and row
links atomically, preserves P3/incomplete coverage and legacy receipts. Blank
balances stay unknown; credit-card amounts owed convert to negative ledger signs
while original printed values survive in the receipt. Rollback/stale source,
assignment/scope and old-finalization regression tests pass (26 at initial check).
20 targeted UI tests, TypeScript and scoped lint pass.

Fresh real-PDF case c1453d2f-c2ff-47c6-a58a-1a9786803f44, evidence
300c464c-5a53-4d2e-94fc-03420880f374, receipt
5badfcc6-47a2-4808-bd6a-d991a60649c2. Two payment/purchase rows on PDF page 3;
page 1 printed May 12–June 11 2020, opening $6,700.18, closing $6,637.96,
liability owed. Deliberately omits $56.16 interest: current check correctly reports
5616 minor-unit difference. 0 included / 2 P3-excluded rows; original PDF hash
unchanged. Period f3a9c1ae-3c97-41fb-9fcf-7ef5488d7dbf. Existing finalized real
cases untouched. **Do not rerun writer check_local_statement_controls_review.cjs.**
Artifacts statement-controls-{pdf-intake-check,review-check,export-verification}.json
and statement-controls-sample-export.zip in data/local-runtime.

7716d86 adds retained control inspection to the Statements source dialog: exact
original cell highlights, dates/balances/reason, explicit liability sign explanation.
Checks sealed digest and period/account/document binding; no invented legacy
controls. Read-only browser check reopens all four controls on original page 1,
zero financial writes; desktop/narrow source views verified. 20 backend and 15 UI
tests pass, TypeScript/scoped lint pass. Verification details/review reason are
collapsible to keep the actual source prominent. Script
check_local_statement_control_sources.cjs is read-only and repeatable.

79e1ee8 adds readable statement-control tables to the HTML export, retaining raw
source text, exact reviewed printed values, PDF pages, convention and review reason.
Unknown controls stay explicit, source text HTML-escaped; full raw receipt remains.
38 targeted backend tests pass. Real snapshot rendered to
 data/local-runtime/statement-controls-readable-report.html.

Backend session 66028 currently serves source-inspection changes; restart to pick
up the newest readable-report change. Log
/tmp/loupe-neilbyrne-retained-controls-runtime.out. Existing worker/engine/frontend
remain running. No schedule resumed. Continue the practical journey, including a
real-PDF ledger correction acceptance in a separate explicitly labelled test case;
full-statement extraction/coverage/admission and broader analysis remain incomplete.

### Original-source export verified — 9 September 2026

5eeda00 adds optional original-file bundling to ledger exports. Default remains
metadata/history only. The UI explicitly selects complete referenced files and
warns that these may contain pages outside account/date filters. Same-case file
records and ingestion digests are checked in the export database snapshot; actual
regular-file bytes are hashed before ZIP creation. Missing/changed/non-regular
files, conflicting digests, more than 100 files or more than 64 MiB refuse the
entire bundle. Safe UUID-based archive names; no local disk paths exported.
Manifest records per-file SHA-256, size, original name and archive path.

37 targeted backend export tests, 9 frontend export tests, TypeScript/scoped lint
pass. Both real PDFs downloaded through the UI with original sources; independent
verification confirms byte-for-byte originals (6,921,177 and 5,561,852 bytes),
snapshot/HTML hashes, retained review history and 0 included/2 excluded rows each.
Original files unchanged; zero financial writes. Artifacts first-pdf-with-sources.zip,
second-pdf-with-sources.zip, original-source-export-verification.json under
 data/local-runtime. Scripts check_local_original_source_export.cjs and
verify_local_original_source_exports.py are read-only and safe to repeat.
Backend session 69571, log /tmp/loupe-neilbyrne-source-export-backend-runtime.out.

Continue in this turn: connect explicitly reviewed PDF statement dates and balance
controls to finalization. Candidate materialization currently creates no periods
and permanently seals additions for a file, so a two-row sample must stay a sample.
Read candidate_materialization.py before extending; preserve legacy receipts and
incomplete-coverage P3 protection. Do not edit existing finalized real cases.

### Statements workspace completed checkpoint — 9 September 2026

84cd821 adds a dedicated Statements tab: current balance identity, conditional
running-balance checks, account/currency date timeline and source navigation.
Current diagnostics use fresh PostgreSQL repeatable-read read-only snapshots;
exact money strings, scope/ownership checks, explicit missing controls, source
exclusions and prior stored reconciliation retained. No proof class or admission
changes. Running comparisons expose both row orders and source links; neither
order is silently chosen. Checks cover at most 25 periods per page; running balance
comparison refuses more than 1,000 rows. Timeline preserves held ranges, gaps and
overlaps separately and does not claim complete extraction.

55 targeted backend tests and 86 frontend tests pass, plus TypeScript/scoped ESLint.
Read-only live checks on existing coverage, second real PDF and corrected synthetic
PDF cases passed; zero financial writes and unchanged recorded reconciliations.
Synthetic correction fixture shows GBP 10 statement discrepancy and -10 forward
running-balance discrepancy with original source links. Second real PDF has no
statement periods; selected candidate rows did not invent printed controls.
Report data/local-runtime/statement-workflow-check.json. Desktop/narrow screenshots
inspected. Backend session 77497, log /tmp/loupe-neilbyrne-statement-backend.out.

Neil again instructed fewer hand-backs. Continue across meaningful units in the
same turn; no new authorization is needed. Next active work: optional original
source files in exports with fresh byte hashes, while retaining source-only
metadata exports. Full PDF printed-control entry/complete-statement admission,
native control revalidation and wider analytical features remain outstanding.

### Second PDF acceptance and source selection layout — 9 September 2026

Latest local commits: f6220fa (interrupted preparation and second-PDF acceptance),
5f5a2a9 (source beside row selection). Continue without requesting another prompt.
The earlier source zoom and PDF review export changes are committed as 359f821
and dc1526d. Completed entries remain in the checklist.

Both supplied originals are unchanged. The second PDF was uploaded through the UI
into isolated case 4d897cb5-b9e4-4df7-9a21-b1ba4b8bf5d7, evidence file
64a25fe8-980f-4a35-a5d1-84c10e558154. Preparation completed all 108 pages using
97 native text pages and 11 local OCR pages. This is not a claim of OCR accuracy.
Page 3 source rows 9 and 12 (UI 10 and 13) were visually checked and reviewed:
USD 180.00 payment/credit on 2020-05-30 and USD 61.62 purchase/debit on 2020-05-29.
Year came from the printed statement header. Printed totals were not nominated.
A provisional account was used. Finalization 6c34cefb-817d-4c68-9b8b-b90a52bdfdc0
remains P3, with 0 included and 2 excluded rows. Original negative payment text,
review reasons, exact amounts/directions/dates and finalization links survive the
schema 3 export; snapshot/HTML hashes and unchanged original PDF hash verified.
Reports: second-real-pdf-intake-check.json, second-real-pdf-review-check.json,
second-real-pdf-sample-export.zip, second-review-history-export-verification.json
under data/local-runtime. Acceptance writers refuse repeat writes; do not rerun.

PDF preparation now catches cancellation, marks unfinished batch jobs failed with
an interruption reason, and re-raises cancellation. 13 targeted engine tests pass.
This verifies cancellation handling, not every hard-crash/retry condition.

Row selection now shows the original page beside the stored grid on desktop,
stacks at narrow widths, and lets a cell locate its original rectangle without
selecting a row or enabling save. Source page list has a bounded scroll area.
19 targeted UI tests, TypeScript and scoped ESLint pass. Read-only browser check
on the second PDF verified desktop/narrow layout and zero financial writes;
screenshots inspected. Report source-selection-layout-check.json.

Runtime backend session 39538 now includes final export count/link checks; worker
49063 includes cancellation handling. Engine 85887 and frontend 21189 unchanged.
Logs remain /tmp/loupe-neilbyrne-review-export-backend.out and
/tmp/loupe-neilbyrne-pdf-prep-worker.out. Old heartbeat remains paused.

Next: complete statement controls/coverage and practical correction/analysis
acceptance. Do not fabricate a wrong reading in these real-PDF samples merely to
exercise correction; use explicit synthetic fixtures for deliberate errors.
Full statements, account identity and the wider analytical UI remain incomplete.

### Continue autonomously: source zoom and PDF history export — 9 September 2026

Neil explicitly said continue without asking. Continue across tested units; do not
pause for another keep-going prompt. Keep practical workflow/UI priorities.

359f821 adds100–400%source zoom, fit-width and highlight focus. Same page/image and
normalized box scale together; page changes reset zoom.19source tests,TS/scopedlint
and read-only real-PDF300%zoom/focus browser check pass. Screenshot inspected.
Also fixed three unsupported testing-library exact options introduced in the prior
intake test. Reports source-zoom-check.json; scriptcheck_local_source_zoom.cjs.

PDF history export now captures mappings/original cells, all review events and
current states, finalization snapshots and original transaction links for referenced
source files. Uses samePGrepeatable-read transaction; file context can exceed row
filter scope but never enters totals. Schemasnapshot3, separate manifest PDFreview/
candidate/receipt counts; HTML readable decisions plus complete details. Count/digest/
chain/link failures and10kcombined record limit refuse incomplete exports.50backend
snapshot/history/tracing tests,9frontendexport/intake tests,TS/scopedlint pass.
Realcase export downloaded and independently verified:2candidateoriginals,2reviews,
1receipt,0adjudications,0included/2excluded. Oldschema2 ZIP preserved; current
real-pdf-history-export.zip and review-history-export-verification.json.
Backend63339 /tmp/loupe-neilbyrne-review-export-backend.out runs the earlier version
of this unit before final count/link validation; restart before next live export.
Engine85887/worker45023 remain. No evidence/ledger decisions changed in this unit.

Next: second supplied PDF upload/preparation/source review acceptance; continue
statement coverage/accuracy and workflow failures. Do not call the full financial
application complete. FirstPDFsample account stillprovisional,P3,incomplete.

### Real PDF two-row review and export verified — 9 September 2026

The uploaded real PDF now completed a bounded actual UI workflow: stored source
page4 rows40/41 (UI rows41/42) nominated, provisional USD account created, two
visually verified purchase readings resolved, OCR descriptions corrected against
the image, finalized and exported. No raw evidence changes or synthetic fixture
seeding. Finalized P3,0included/2excluded; do not imply complete statement coverage.
See docs/loupe-review-2026-09-09.md for one user entry point and precise limitations.

Mapping6202a5db-9c9f-458c-9227-99b571ee028e;
account024a3805-f44d-475f-81cb-2a6f9066e4fa;
finalizationd19d0ab9-bfb2-495e-b3f0-387125f1e549;
transactions4465cd35-aa06-4298-af63-0d93430ce880 (1400minor USD) and
cee1b0d8-31e7-4051-94ae-db3970766147 (10000minor USD).
Reports data/local-runtime/real-pdf-review-check.json,real-pdf-sample-export.zip,
real-pdf-export-verification.json. Verification confirms sourcepage4/file/hash,
exact amounts and exclusions, snapshot/HTMLbyte hashes and unchanged original.
Screenshot /tmp/loupe-neilbyrne-real-row-review.png inspected; real document text
is small at current image scale, motivating source zoom as a practical UI fix.

Important remaining export gap: candidate-review history lives in application,
not bundled with ledger export; manifestdecision_count0 refers to adjudication
history, not absence of PDF review. Don't mark complete export history done.
Next practical work: source zoom, bundle candidate review history, extend statement
accuracy/coverage and secondPDF acceptance. Keep broad transfer/graph expansion
behind this usable workflow milestone. Scripts refuse duplicate acceptance writes.

### Real PDF upload reaches source review — 9 September 2026

Implementation213ed7e adds preparation_mode=pdf_review to explicit processing,
engine job_type pdf_review and a batch branch that bypasses AI policy/summary,
embeddings/entities/graph. PDF text/local Tesseract and geometry are saved by the
existing services; source-only quality report and message, no admitted rows.
Mixed mode batches refused; native generic processing gate retained. UI uploads
one PDF, queues/previews progress, opens source selection, and can reuse uploaded
files after interrupted requests. Scope/file/job/result validation retained.

Real supplied56-page PDF uploaded through application into isolated case
c06c264c-a402-4895-a696-be634fe23629, evidence1cf0de89-8d40-482a-90a5-38619c0a493f,
job62c9eea8-b3ed-4f1f-ac54-32ccd0de390b. Preparation completed in about5seconds,
56native text pages, source selection reached, original hash unchanged. The first
UI attempt exposed filename/original_filename contract mismatch; fixed and resumed
same uploaded file. Do not reupload. Report data/local-runtime/real-pdf-intake-check.json.
No reviews or ledger transactions created yet. The PDF contains embedded text
noise/duplication; native text extraction must not be equated with correct readings.

Tests:19engine (includes no-AI branch, upload modes, queue and normal batch regression),
25admission gate,1backend response-recovery,18frontend tests, TS/scopedESLint pass.
Backend17624,engine85887,worker45023; logs /tmp/loupe-neilbyrne-pdf-prep-{backend,engine,worker}.out.
Backend has latestmode implementation except harmless moved case check; restart
before more backend edits. Frontend remains21189. Old heartbeat paused.

Current next: small manually verified sample on PDFpage4: two purchase rows printed
04/22 amount14.00,04/23 amount100.00; year2021 supplied from statementheader. Rendered
page visually checked at /tmp/loupe-neilbyrne-real-statement-page4.png. Inspect stored
cells before creating candidates; do not assume header rows are transactions or
that a two-row subset proves fullstatement coverage. PDFskill read in this session.

### Product focus and source-beside-review UI — 9 September 2026

Neil raised elapsed time and concern that UI discussions were forgotten. He agreed
with a new focus: finish a practical real-PDF import/review/correction/analysis/export
journey, using the saved analytical design. This supersedes the previous next-work
sequence of expanding tracing/transfer matching. Read docs/loupe-ui-acceptance.md.
Do not treat endpoint screens or test counts as completion of the intended UI.

Source review improvement: read-only source-readings endpoint validates current
saved binding and returns all original cells/locators independent of numeric/date
assessment. CandidateSourcePanel validates case/file/mapping/review/text coverage,
shows original image beside review fields, switches measured highlights; no guessed
locations.15UI tests,16backend tests, TypeScript/scoped ESLint pass; live synthetic
finalized review verifies image, column switching, desktop adjacency and narrow
no-overflow. Screenshot inspected. No review/ledger writes. Backend64595,
/tmp/loupe-neilbyrne-source-panel-server.out. Tracing implementation1679cfa is complete
within its stated single-account/one-deposit UI scope. Its checkpoint docs had not
yet been committed before Neil's UI questions.

Next: inspect actual PDF upload-to-stored-source route. Existing fixtures seed
source geometry directly and do not prove production upload workflow. Preserve
real PDFs; use isolated test copies for the agreed practical journey. No external
AI processing without selected provider setup. Old heartbeat remains paused.

### Conditional ledger tracing — 9 September 2026

Conditional tracing is connected to the existing five-method core using a captured
repeatable-read ledger/history snapshot. One account and closed date interval;
explicit opening balance/basis, complete date-respecting order/basis and attributed
credits/bases; methods default to none. Stale snapshot, omitted/duplicated readings,
reversed dates and invalid attribution refused. No ledger writes. API supports50
attributions; initial UI supports one deposit. Opening funds remain unattributed.
Results show unidentified/unfunded withdrawals separately; assumptions are never
marked verified. Download preserves exact server JSON bytes and validates SHA-256,
byte count, case/account/snapshot and all submitted assumptions. Source files are
not embedded and cross-account tracing is not established.

Tests:121 targeted backend/core/package tests before final envelope change, then21
bridge/router tests after;45 frontend tests, TypeScript and scoped ESLint pass.
Live existing synthetic coverage account:4included readings, FIFO attribution100
minor units, exact download verified, input edit clears result, no ledger writes.
Screenshot inspected. Reports data/local-runtime/conditional-trace-ui-check.json
and conditional-trace-check.json. New backend session6096 log
/tmp/loupe-neilbyrne-tracing-server.out. Engine94599/frontend21189 remain.

Neil asked status during work; answered progress and remaining scope, continuing.
Nine features partial, feature7 remaining; none complete end to end. Next extend
source navigation/multiple deposit assumptions in tracing, then ledger transfer
matching and broader reconciliation/real-PDF acceptance. Provider question remains
pending; continue offline. Old heartbeat stays paused.

### Row suggestion review UI — 9 September 2026

35b6ccb connects CandidateRowSuggestions to source picker. Explicit nominated date/
amount columns and currency; response scope/revision/text and full row coverage
validated. All checked rows and uncertainty displayed25/page. Only explicit Add
suggested rows changes selection; existing save action remains separate. Source/
column/input changes discard suggestions.25targeted source-picker/date/suggestion
UI tests, TypeScript/scoped ESLint passed. Read-only Chromium existing header PDF:
3checked/2suggested data rows, header unselected,0candidate writes. Screenshot
inspected and controls restyled; browser rerun passed. Report
 data/local-runtime/row-suggestions-ui-check.json. Backend now60821, log
/tmp/loupe-neilbyrne-suggestions-server.out; engine94599/frontend21189 remain.
No ledger/evidence writes. Provider question remains pending; continue offline.

Next investigate existing tracing/flow/correction cores and choose a bounded
ledger integration with explicit source/assumption contracts. Do not replace proven
cores or infer party identities from labels. Account tracing can be a conditional
scenario only with explicit opening balance, attributed deposits, order and basis;
no legal-method default or hidden same-day ordering assumption. Continue all
remaining work, checkpointing each tested unit; old heartbeat remains paused.

### Continued through remaining work — 9 September 2026

Neil explicitly requested continuation through all remaining work. Continue across
bounded tested units without another keep-going prompt. Old heartbeat remains
paused; no timed schedule was requested. Provider preference question is pending
for final AI-assisted acceptance; continue offline work independently and never
paste/read credentials into messages. No new real-evidence ingestion authorization.

Latest implementationea125fd: source-bound date/amount row suggestions using two
explicit columns and caller-supplied currency; uncertainty preserved, all checked
rows retained, no selection/persistence/classification/admission.36source/candidate/
package tests plus1route scope/error test passed. UI next. Numeric-only date
assessment limitation corrected. Isolated Docker services restarted; backend2279,
engine94599, frontend21189 running, logs /tmp/loupe-neilbyrne-resumed-{backend,
engine,frontend}.out. Backend started beforeea125fd; restart it before new endpoint
UI check. Existing synthetic fixtures retained; no evidence/ledger writes.

Next: CandidateRowSuggestions component within source picker; explicitly nominated
columns/currency, scope/source-text validation, paged suggestions, deliberate add
to selection, no save until existing investigator action. Tests and synthetic UI
acceptance, then continue extraction/accuracy and remaining ledger consumers.

### Resumed development — 9 September 2026

Neil explicitly said "continue". Development resumed in this task; the old timed
heartbeat remains paused (no new schedule requested). This supersedes the older
instruction to await resumption below. Tracked checkout was clean at cc61a14.

Latest implementation43dbbd5: source_dates.py recognizes explicit English month
names in day-first/month-first forms, full/three-letter/Sept tokens, preserving
raw text/origin/source references. Full year gives a review-only ISO proposal;
missing year/century stays unresolved, impossible calendar dates rejected, unknown
language/OCR lookalikes/ordinal suffixes unsupported without repair. Existing
candidate date endpoint/UI schema unchanged; no automatic acceptance or class change.
24targeted source-date/candidate-date/package tests passed; diff check passed.
Log /tmp/loupe-neilbyrne-named-dates-tests.out. No evidence/ledger/database writes.

Local runtime is not assumed healthy after two days: prior backend exec18309 no
longer exists and lsof found no listener on58002. Unit checks used the persistent
backend venv. No live browser claim for this parser change. Next resume should
check isolated services and restart as needed before doing a synthetic named-date
UI acceptance check. Then continue conservative extraction/accuracy work, including
year/context resolution and broader printed controls. Do not guess source years or
promote classifications. Original ten-feature checklist retained, none whole complete.

### Final scheduled handoff — 7 September 2026, 12:43 Dublin

**Scheduled development is PAUSED.** automation_update confirmed
continue-loupe-development statusPAUSED at11:43UTC, ahead of the13:00Dublin cutoff
while completing the reserved handoff. No more automatic segments are expected.
Earlier ACTIVE/deadline/next-heartbeat instructions below are historical and are
superseded here. Resume only on a new user request; do not silently reactivate.

User-facing guide: docs/loupe-review-2026-09-07.md. Original ten-feature checklist
retained:1,2,3,4,5,6,8,10partial;7transaction matching and9funds tracing remaining;
none complete end to end. Main documentary Transactions, Counterparties and Trends
now use current ledger data. Exact scoped ZIP/HTML/JSON exports, decision history,
manifest hashes, permissions and exclusion propagation are implemented and tested.
Remaining work includes automatic PDF extraction, complete control revalidation,
broader duplicate/cross-case handling, all graph/search consumers, matching/tracing,
polished exhibits and full real-PDF/AI acceptance. Do not mark these complete.

Verification:3,827backend tests,1,032frontend unit tests,11Chromium tests, TypeScript
and full ESLint passed at09c341c; later primary export change51ebd77 passed44targeted
tests, TypeScript/scoped ESLint and live ZIP/hash checks. Last app change51ebd77;
health/script/docs checkpoint46c4339. Tracked tree clean before final state edits;
unrelated untracked material preserved. No pushes, merges or git-config changes.

Local stack remains running:frontend55174, backend58002(exec18309,
/tmp/loupe-neilbyrne-counterparty-server.out), engine58003; separate persistent
venvs and Docker data. Last read-only health/preservation check11:36UTC passed:
all three HTTP200, real PDFs unchanged/no matching isolated ingestion copies,
synthetic coverage fixture10included/0excluded/2100GBP.6audit decisions retained
there after restored tests. AI processing remains untested. Reports and replay
instructions are in docs/local-application.md and data/local-runtime.

**On requested resumption:** read this section and retained checklist, inspect git
and live fixture state. Prioritize end-to-end extraction/accuracy acceptance and
remaining authoritative consumers before transfer matching/tracing. Do not rerun
mutation fixture scripts blindly; finalized/corrected fixtures are intentionally
persistent. Reuse passing suites unless further changes justify another full run.

- **Branch:** `integration/evidence-main-reunion`. No merge to main; Neil pushes.
- **Latest implementation checkpoint:** `51ebd77`, primary Ledger/Transactions
  export integration. Full integrated baseline at `09c341c`;44targeted tests and
  browser export checks cover this later change. State commit follows.
- **Authorization:** Neil asked Codex to understand the project, then explicitly
  said **“ok take over and continue please.”** The preceding recommendation was
  to complete the admission control and the case-wide proof-class display,
  then continue the agreed sequence. The older demand for a ruling on the
  admission control is resolved. Do not ask for that approval again.
- **Completed on takeover:** admission control at `8ac2455`, then the case-wide
  evidence-classification display at `b8aeb5b`. **Item 8's planned wiring is now
  complete**, subject to the explicitly preserved backend limitations below.
- **Uncommitted implementation work:** none. Existing unrelated documents,
  evidence, backups and `src/__probe.test.ts` were left untouched and untracked.
- **Session convention:** Neil explicitly said the session-delimitation rule was
  for Claude and authorized continuing in this same session. Keep tested commits
  and the disk handoff; do not require a new session after each unit.
- **Next integration milestone:** Neil said, “At some point I want to get the
  whole application running locally in a venv so we can test, keep that in mind.”
  The local application is now running with separate persistent Python 3.12 venvs,
  isolated Docker services, real HTTP duplicate round trips and verified PostgreSQL
  lock contention. See the local application section below. The old `/tmp` venv
  remains test-only. AI processing and full application acceptance remain untested.
- **Duplicate status:** comparison plus explicit exclusion/restoration are connected
  for one case. The broader item 9 still has authorized cross-matter sightings and
  comparison scaling/coverage work outstanding. The legacy bulk resolver is not
  exposed. Item 10 is underway: correction preview and replacement writer are
  complete, and correction UI/history are now connected on both Ledger and Held out.
  Broader revalidation remains outstanding.

### Extended authorization — 7 September 2026, through 13:00 Dublin

Neil upgraded and requested mindful usage, then explicitly said “extend this
working session until 1pm”. The existing continue-loupe-development heartbeat was
updated through the app and confirmed ACTIVE every five minutes until
**13:00 Europe/Dublin (12:00 UTC)**. This supersedes all earlier cutoff/pause
statements below. Reserve 11:45–12:00 UTC for verification and the retained
checklist/handoff. Reuse valid passing checks; target tests to changed behavior
and avoid unnecessary repeated full suites. No reset credits were redeemed.

### Handoff health/preservation check — 7 September 2026, 11:36 UTC

`46c4339` adds repeatable read-only scripts/check_local_handoff.py. Frontend55174,
backend58002/health and engine58003/health all200. Synthetic coverage case remains
10included/0excluded/210000GBPminor units. Both real PDF SHA-256 values match the
original inspection baseline; zero isolated evidence_files match either digest or
filename. SQL connection explicitly READ ONLY. Report
 data/local-runtime/handoff-verification.json. AI provider processing still not
validated. User guide updated with12:36Dublin verification time. Application code
unchanged since51ebd77; full and targeted test baselines remain valid.

**Next heartbeat:** check clock. At/after11:45UTC begin final handoff/pause through
 automation_update, preserving existing automation fields/prompt and marking status
PAUSED. Before11:45UTC avoid repeated full suites/extraction; no remaining bounded
implementation is in progress. Verify tracked tree clean and guide/checklist links.
Final message: scheduled run paused for13:00Dublin handoff; application running,
completed main ledger views/export work, eightpartial/two remaining, none whole
complete; link review guide. No claim of pause before tool success. No pushes.

### Review guide prepared — 7 September 2026, before final cutoff

`5975be9` adds docs/loupe-review-2026-09-07.md: plain-language numbered status of
all ten retained features, three verified synthetic demo links and exact limits.
Current read-only API check confirms analysis case10included/0excluded/GBP2100;
finalized-review case0included/3excluded; correction-history case0included/3excluded.
Report data/local-runtime/demo-check.json. Read-only Chromium historical correction
and generated-PDF source check passed again; log
/tmp/loupe-neilbyrne-handoff-history-demo.out. No live writes.
Eight features partial,7and9remaining, none whole complete. The detailed original
checklist remains intact. Application head51ebd77; documentation guide5975be9.

**Next segment:** prepare/run final read-only local service health and real-PDF hash/
no-ingestion preservation check, review git tracked status, and record final results.
At11:45UTC reserve the remainder for handoff and pause heartbeat through
 automation_update; do not claim it is paused before tool confirmation. Final
message should link docs/loupe-review-2026-09-07.md and the local demo, state eight
partial/two remaining, main completed changes and tests, without claiming full
application acceptance. No need repeat full suites or regenerate PDF extraction.

### Primary ledger export integration — 7 September 2026

`51ebd77` mounts existing LedgerExportButton in CorrectableLedger beside summary,
using the same applied params. Both Ledger and documentary Transactions benefit;
Held out stays without this all-scoped-readings export.44targeted wrapper/export/
page tests passed, TypeScript/scoped ESLint/diff checks passed. Browser primary
Transactions ZIP download verified; independent checks10restored rows,6decisions,
snapshot/report hashes match. Report data/local-runtime/primary-ledger-export-check.json;
script check_local_primary_ledger_export_ui.cjs. No live data changes. Backend
remains exec18309. No need repeat full integration suite for this tested wiring.

**Next segment:** prepare a concise local testing/demo guide and retained numbered
feature status for Neil's13:00return. Verify source/correction/finalization demo
fixture paths from persistent reports before linking. Continue bounded acceptance
checks that fit before11:45UTC; do not begin speculative large feature work. At
11:45UTC perform final local health/PDF-preservation/git status check and pause
heartbeat through automation_update, with clear complete/partial/remaining report.
All ten full features remain partial or remaining;7and9 remain unconnected.

### Cross-view exclusion/export acceptance — 7 September 2026

`5aff978` adds browser check_local_cross_view_exclusion.cjs and independent ZIP
verify_local_cross_view_exports.py. Fixed synthetic coverage case only; exact UUID
18ab50c4-1f32-4274-add9-3d1afecd9886/400GBP was excluded through main Transactions.
Transactions, Counterparties and Trends all changed2100→1700GBP; saved excluded
ZIP. Finally restored exact row through release API; Transactions returned2100,
saved restored ZIP. Independent bytes/hash/case/original-reading checks passed:
9→10included rows,1700→2100GBP,5→6decisions. Both decisions retained. First script
attempt stopped before mutation because ref_id was not table text; selector fixed
to existing data-row-key UUID before successful run. No real evidence changes.
Live fixture now has6decisions (was4); all10rows admitted/restored. Report
 data/local-runtime/cross-view-exclusion-check.json. Backend still exec18309.
Existing full integration baseline reused, no application code changed.

**Next segment:** expose the already-tested LedgerExportButton alongside applied
filters/summary in CorrectableLedger, so both primary Ledger and documentary
Transactions can download their own scope without navigating away. Held-out tab
should not imply a held-out-only export. Targeted scope/page checks and read-only
browser download suffice; do not rerun full suites. Then prepare final local demo
and retained ten-feature status report. Reserve11:45UTC for final handoff;
schedule remains ACTIVE until13:00Dublin.

### Integrated verification baseline — 7 September 2026, 11:03 UTC

`09c341c` records a single integrated verification after main Transactions,
Counterparties and export work:3,827backend financial tests, zero skips;1,032frontend
unit tests/108files;11Chromium tests/9files; TypeScript/full ESLint/diff checks all
passed. Existing unrelated src/__probe.test.ts ran but was not edited or committed.
Logs /tmp/loupe-neilbyrne-final-integration-{backend,unit,browser,tsc,lint}.out.
No failures to fix. No real evidence or database changes. Backend still exec18309.
Do not repeat this full baseline without subsequent changes or unresolved concerns.

**Next segment:** live cross-view exclusion consistency test using existing synthetic
coverage case. Exclude one known400GBP row through the authorized writer/UI; verify
Transactions summary, Counterparties, Trends and export all move2100→1700 and ten→nine
included rows, then restore in finally and verify2100/ten. Preserve audit events;
no real evidence. Existing check_local_summary_panel_ui.cjs is a useful starting
point. This verifies exclusion propagation, not full correction/graph-wide matching.
Afterward use remaining time for bounded acceptance checks; reserve11:45UTC for
final verification and plain-language ten-feature handoff. ACTIVE until13:00Dublin.

### Documentary Counterparties UI — 7 September 2026

`0fe3c69` mounts LedgerCounterpartiesAnalysis in main documentary Counterparties
independent of graph loading/emptiness. Shared filters/coverage/summary plus exact
verbatim source-label groups, explicit null/blank and quoted whitespace. Scope,
unique contributing IDs and group-to-summary arithmetic validated.25groups and
25source links/page; financial-ledger cache prefix refreshes on decisions. Source
links open current case-scoped reading dialog.35page tests and14panel tests passed;
TypeScript passed. Final scoped lint found two redundant escapes in a test label;
removed in following test-only commit and scoped lint rerun passed. Browser verified
GBP2100/10missing-label readings and correct source scope; report
 data/local-runtime/counterparties-panel-ui-check.json. No live evidence/ledger
writes. Backend unchanged exec18309.

**Next segment:** integration verification is now justified by main Transactions,
Counterparties and export changes since421ad37: run financial backend suite and
frontend unit/browser/TypeScript/lint once, resolve any integration failures, then
checkpoint. Read existing logs instead of duplicating targeted checks. Broader
identity matching, tracing, automatic extraction and full real-PDF acceptance remain.
Reserve11:45UTC for final handoff; ACTIVE schedule ends13:00Dublin. Feature5 remains
partial because graph-wide/search/money-flow consumers are not all migrated.

### Counterparty-label summary backend — 7 September 2026

`5cc894e` adds ledger_counterparties in ledger_summary.py and case:view GET
ledger-counterparties. Same bounded captured-readings eligibility, exact integer
currency totals, transaction/source IDs; excluded rows never enter groups. Verbatim
labels: null/blank/case/whitespace differences distinct; no inferred identity,
sender/beneficiary or transfer match. Removes internal readings from API response.
Oversized scope unavailable without partial counts/groups.38 summary/package tests
passed after replacing an invalid direct quarantine fixture update with the real
writer; additional route scope/error test passed. Live synthetic HTTP case10,
account4, empty0 with summary parity and missing-label/source refs verified.
Report data/local-runtime/ledger-counterparties-check.json; script
check_local_ledger_counterparties.py. Backend exec18309, log
/tmp/loupe-neilbyrne-counterparty-server.out. No real evidence or synthetic ledger
writes in live check. Counterparties UI still legacy until next segment.

**Next segment:** connect LedgerCounterpartiesPanel to this endpoint with shared
financial-ledger cache prefix, applied account/date filters and scope validation;
validate exact group totals against response summary, page groups and contributing
source links. Null/blank source labels explicitly distinct. Mount in documentary
Counterparties independently of graph loading, retain explicit intelligence switch.
Do not claim identity/transfer matching. Reserve11:45UTC for final handoff;
schedule ACTIVE until13:00Dublin. None of ten full features newly complete.

### Main documentary Transactions migration — 7 September 2026

`b67e365` mounts CorrectableLedger in main Transactions when mode=transactions,
independent of graph loading/empty states. Reuses exact ledger summary, applied
filters, source/correction/adjudication controls. Explicit Ledger postings vs
Financial intelligence selector remains reachable even on empty graph; intelligence
shows limitation and keeps its graph UI. Existing Ledger tab remains.31 page tests
passed after updating an old graph-search expectation to the intelligence search
placeholder. TypeScript/scoped ESLint/diff checks passed. Local Chromium verified
main Transactions bigint amount and negative balance plus decision open/cancel;
report data/local-runtime/transactions-ledger-ui-check.json. No writes to evidence
or ledger. Backend unchanged exec20679.

**Next segment:** migrate documentary Counterparties to exact summaries of captured
ledger counterparty_raw labels with included eligibility, separate currencies and
contributing row/source references. Do not infer identity or claim transfer matching
from equal labels. Missing labels remain explicit. Reuse shared bounded ledger read
and exact arithmetic; ensure corrections/exclusions invalidate view. Inspect existing
counterparty services before choosing implementation. Funds matching/tracing remains
separate unfinished work. Reserve11:45UTC for handoff; ACTIVE until13:00Dublin.

### Live export membership verification — 7 September 2026

`cc96526` adds check_local_ledger_export_access.py against only fixed isolated
PostgreSQL/HTTP services. Temporary ordinary user: non-member403; collaborator
with edit but without case:view403; case:view without edit200; revoke membership,
same token403. Finally removes membership/user and confirms removal. All passed;
report data/local-runtime/ledger-export-access-check.json. No ledger/evidence
changes and no production fix needed. Backend remains exec20679. Existing92
money/snapshot/package tests reused; this segment adds a live boundary check.

**Next segment:** migrate main documentary Transactions tab to CorrectableLedger,
independently of graph loading/empty state, using the same explicit documentary vs
intelligence selector pattern already in main Trends. Keep intelligence separate,
source/correction/adjudication controls available and graph counts outside ledger
view. Existing Ledger tab remains available. Inspect FinancialPage test harness;
verify graph-independent rendering, mode switch and synthetic browser flow. Then
Counterparties and transfer/tracing work remain. Reserve11:45UTC for handoff;
schedule ACTIVE until13:00Dublin. No whole feature is complete.

### Exact report money and export scope parity — 7 September 2026

`96f3a3f` reuses Money.format for familiar currency units plus exact raw minor units
in brackets. Historical currencies labelled; unsupported/invalid excluded values
remain unscaled.92 targeted snapshot/money/package tests passed including unsafe-JS
integer range, signed and0/2/3/4decimal currencies. Scoped ESLint/diff checks passed.
Read-only HTTP script check_local_ledger_export_scope.py compares snapshot summary
scope/totals/exclusions for whole case10rows, account4, inclusive single day4,
empty date0 and unknown account0; both artifact hashes verified. Unknown account
is an empty filter, not a validated identity. Anonymous refused, missing case404,
reversed dates422. This is not a non-member authorization matrix.
Report data/local-runtime/ledger-export-scope-check.json. Local Chromium rendered
2,100.00GBP alongside210000minor units without1280px overflow; screenshot visually
checked at data/local-runtime/ledger-report-money-preview.png. Backend exec20679,
log /tmp/loupe-neilbyrne-report-money-server.out. No real evidence changes.

**Next segment:** verify actual case-member/non-member authorization for exports
with isolated synthetic users/fixtures and restore any setup changes; then review
remaining main Transactions/Counterparties migration to authoritative ledger data
(feature5) before building transfer matching/tracing on it. Report/exhibit feature8
remains partial. Reserve11:45UTC for handoff; schedule ACTIVE until13:00Dublin.

### Readable captured ledger report — 7 September 2026

`8a1e051` adds ledger-report.html to the same ZIP, rendered only from immutable
snapshot content. Scope, currency totals in explicit exact minor units, included
and excluded readings, source metadata/digests, row/provenance and relevant decision
records are present. HTML escapes all evidence values; CSP forbids scripts and
external resources. Report size over16MiB refuses instead of truncating. Manifest
adds report SHA-256/byte count/derived snapshot digest, preserving snapshot bytes.
32 targeted backend tests passed including hostile markup, unsafe-JS-range money,
size refusal and hash binding. Scoped ESLint/diff checks passed; browser downloaded
ZIP and independently checked both digests, ten synthetic rows and four decisions.
Chromium rendered all14 articles with no horizontal overflow at1280px; screenshot
visually checked. Reports: data/local-runtime/ledger-report-check.json and
ledger-report-preview.png. Backend now exec17992, log
/tmp/loupe-neilbyrne-report-server.out. No real evidence changes.
Feature8 remains partial: PDF pagination/polished exhibits, candidate-review history
and source-file bundling are not completed. This report labels minor-unit values;
familiar major-unit formatting can reuse the existing exact currency formatter.

**Next segment:** verify filtered export totals and permission refusals over actual
HTTP; then improve readable money display using the established currency-unit rules
without losing the exact integer representation. Preserve all ten checklist features.
Reserve11:45UTC for final verification/handoff; ACTIVE schedule ends13:00Dublin.

### Scoped ledger ZIP download — 7 September 2026

`49f2b83` connects the case:view authenticated ledger-export endpoint and Trends
button to the owned consistent export transaction. Applied account/date scope is
checked before the browser saves original ZIP bytes. Fixed safe filenames contain
ledger-snapshot.json and manifest.json. No-store response, bounded content, abort
on scope change, two-minute timeout and duplicate-click protection are included.
Backend 31 targeted tests and frontend 33 tests passed; final six-button-test rerun,
TypeScript, scoped ESLint and diff checks passed. Chromium saved the synthetic ZIP;
independent byte verification confirmed ten rows, four decisions, GBP 2,100 and the
matching digest/byte count. Report: data/local-runtime/ledger-export-ui-check.json.
No real evidence changed. Backend now exec22102, log
/tmp/loupe-neilbyrne-export-download-server.out. Feature8 is partial: this is a
structured snapshot, not a formatted investigator report. Original source files,
structured candidate-review history and fresh source-byte checks remain excluded.

**Next segment:** build a readable report from the same immutable captured snapshot,
including exact totals, scope, sources and decision references; keep all limitations
visible and avoid mixing in legacy graph export results. Reserve 11:45 UTC onward
for final verification/handoff; schedule remains ACTIVE through 13:00 Dublin.
Older next-step text below describes completed historical stages.

### Consistent history/export manifest service — 7 September 2026

`001009d` adds capture_ledger_export(Engine): owns fresh PostgreSQL REPEATABLE READ,
READ ONLY transaction for snapshot plus relevant AdjudicationEvents. Refuses
non-PostgreSQL/reused connection. History scoped by case and captured transaction,
source-document, period and evidence-file subjects. Keeps actor/reason/before/after
and per-subject sequence; explicitly no cross-subject chronology claim.10,000-event
and16MiB bounds refuse truncation. Snapshot schema2; separate manifest correctly
names ledger_snapshot_json_utf8, digest, byte count, generated_at and code_version.
Structured candidate-review history is not embedded, recorded source bytes not
reverified; these limitations remain in content. No download endpoint/UI yet.

Verified:29 targeted snapshot/package tests covered; one expectation corrected to
preserve the writer's existing 'Investigator: ' reason prefix, focused rerun passed.
Real PostgreSQL synthetic concurrent write test passed: export begun before an
exclusion equals baseline bytes/history despite intervening commit; later export
has one fewer included row and one extra decision. Finally restores row; two
synthetic audit events remain. Baseline2 decisions, post-exclusion3, now4 after
restore. Digest/byte count and output limit verified. Script check_local_ledger_export.py;
report ledger-export-check.json. Logs /tmp/loupe-neilbyrne-export-history-{tests,
final,live}.out. Backend remains exec21922; restart before exposing export API.
No real evidence writes. Internal snapshot-only function still marks history absent;
full owned-transaction export function marks captured scoped history present.

**Next segment:** expose a case:view download of the captured snapshot and manifest
as an attachment, then connect a button in LedgerAnalysis using applied account/date
filters. Preserve canonical snapshot bytes (do not parse/re-serialize through JS),
include manifest with accurately named digest, and do not reuse graph PDF exports.
Use a bounded ZIP or equivalent with fixed safe filenames; no external publication.
Verify authenticated HTTP, scope/refusals, exact downloaded bytes/digest, history,
and one synthetic browser download. Keep limitations visible and report feature8
partial until human-readable reports/exhibits and broader exports are connected.

### Internal deterministic snapshot foundation — 7 September 2026

`1efe4ad` adds optional capture_readings to the same ledger_summary SELECT/pass;
normal summary/trends responses unchanged. Captures all scoped readings including
excluded states, exact money strings, original provenance, source IDs/digest/parser/
classification/status, inclusion/reason and replacement link. Frozen LedgerSnapshot
contains deterministic UTF-8 JSON, SHA256 and byte count, no generation timestamp.
No partial snapshot above row limit. Explicit export_ready=false/history_captured=false;
not exposed through API/download and not a completed traceable export.

Verified:47 targeted snapshot/summary/package tests, plus focused single-read proof.
Exact >JS-safe money, stable hash, byte length, immutable old content after later
provenance edits, excluded readings and no-partial bound pass. Initial SELECT-count
test counted an expired fixture case-ID lookup; resolve fixture UUID before measuring,
then actual capture performs one SELECT. Logs /tmp/loupe-neilbyrne-ledger-snapshot-
{tests,single-read}.out. No live DB changes; backend session21922 not restarted for
this internal service. Source bytes not verified; only recorded ingestion hashes.

**Next segment:** add consistent decision-history capture and export-event manifest.
Rows/totals/source state and relevant AdjudicationEvents must share one PostgreSQL
repeatable-read read-only transaction, not independent READ COMMITTED snapshots.
Use a fresh owned session/connection so caller auth reads cannot change isolation;
SQLite test path must have explicit documented snapshot behavior. Bound decisions
and serialized output; refuse truncation. Bind relevant case/row/source/file subjects,
retain original correction lineage and actor/reason/before/after. Preserve deterministic
content hash; generation time belongs in manifest, whose digest_covers must correctly
name ledger JSON (existing export_manifest is HTML-specific, do not relabel blindly).
Only expose download after these prerequisites and synthetic consistency tests.

### Main documentary Trends migration — 7 September 2026

`9e0ec3a` routes main Trends in transactions mode to LedgerAnalysis (its own
account/date filters, requested coverage, exact summary/date totals/source links).
It is independent of graph loading/emptiness. Always-visible Ledger postings /
Financial intelligence selector preserves the graph intelligence workflow; its
explicit note says graph claims/valuations do not reflect ledger corrections.
No graph amounts are fed into ledger analysis. Transactions/Counterparties remain
legacy graph views. Ledger tab still has its own summary/date panels.

Verified:36 targeted frontend tests (27 page,9 date panel), TypeScript and scoped
lint. Page tests verify empty/loading graph access and mode-switch return. Read-only
live browser enters top-level Trends, switches monthly/daily GBP2100 and opens
contributing source citation. Script check_local_trends_panel_ui.cjs now checks this
entry point; existing runtime report/screenshot reused. Logs use
/tmp/loupe-neilbyrne-trends-migration-{tests,tsc,lint,live}.out. Backend unchanged
exec21922. No real evidence changes. Feature5 remains partial.

**Next segment:** inspect existing report/export components and add a traceable
export of the authoritative ledger analysis, with exact currency totals, scope,
source/transaction IDs, included classifications, exclusions and limitations.
Prefer a bounded immutable snapshot contract before UI download; ensure rows and
totals come from the same eligibility read rather than two changing queries.
Do not reuse legacy graph numeric exports for ledger results. Include correction
lineage/decision basis explicitly or retain the export as incomplete until connected.
No external publishing; use synthetic local verification. Graph/counterparty,
transfers and tracing still remain. Schedule ACTIVE until13:00 Dublin.

### Consolidated integration checks — 7 September 2026

`421ad37` registers ledger_summary/LedgerSummaryError/requested_statement_coverage
in the financial package and supplies QueryClientProvider in FinancialPage tests,
stable across rerenders/isolated per test. Updates default empty-filter expectation.
The full run exposed one missing package export and six test-harness failures:
new query panels had no provider, triggering the ledger error boundary. Production
already provides the query client. No product rendering defect was found by this gate.

**Verified:** final full backend3,791 financial tests, zero skips. Frontend full
run covered1,001 tests (995 passed/six page-harness failures); after fixes all24
FinancialPage tests pass, so all failures are resolved without repeating unrelated
unit files.11 Chromium tests pass, TypeScript/full ESLint pass; post-fix TypeScript
and changed-file lint pass. Package/summary/coverage45-test check also passes.
Logs /tmp/loupe-neilbyrne-integration-{backend-final,unit,page-final,browser,tsc,lint,
final-tsc,final-lint,exports-fix}.out. Do not describe the original frontend full
run as all-green; give its targeted-resolution sequence when relevant. Tests remain
synthetic/read-only; real PDFs untouched. Backend session21922 still serves current
feature code; package export registration takes effect on next restart.

**Next segment:** connect authoritative date analysis into the top-level Trends
workflow rather than leaving users on legacy graph totals. Inspect FinancialPage's
mode behavior and filters before changing it: documentary transactions should use
ledger scope/summary/date totals, while any retained financial-intelligence view
must be clearly distinguished. Preserve current source links, excluded populations,
exact-money handling and no graph/ledger mixing. Use page integration tests plus
one live synthetic navigation check. Graph/counterparty migration and traceable
exports still remain; feature5 stays partial. Schedule ACTIVE through13:00 Dublin.

### Source-linked ledger date display — 7 September 2026

`8582179` connects LedgerTrendsPanel in Ledger to applied filters, with explicit
read/refresh and daily/monthly selection.25-point pages and25-reading pages per
point; links use existing LedgerSourceDialog. Validates scope/grouping, exact
point/summary money, row counts and unique contributing IDs. Currency groups stay
separate; unavailable never zero. Scope-keyed state clears old results/source.
Legacy graph Trends remains separate; no graph migration claim.

Verified:21 targeted frontend tests (9 new trends,2 wrapper,10 summary), TypeScript
and scoped lint. Initial TypeScript test-only exact option was removed (testing-
library role options differ from Playwright); final typecheck passed. Live read-only
synthetic browser daily/monthly GBP2100 and contributing source record scope passed.
Fixture has no stored page location; source dialog correctly says so. Screenshot
visually inspected, no PDF highlighting claimed. Script check_local_trends_panel_ui.cjs;
report trends-panel-ui-check.json; screenshot /tmp/loupe-neilbyrne-trends-source-ui.png.
Logs /tmp/loupe-neilbyrne-trends-panel-{tests,tsc,lint,live}.out. Backend unchanged
exec21922. No real evidence changes. Feature5 remains partial.

**Next segment:** consolidate the connected summary/date-filter/trend work with
one full financial backend gate and frontend unit/browser/TypeScript/lint gate.
Several bounded segments have landed since the last full gate, so this is now
integration verification, not repetition of unchanged checks. Fix actual failures,
record current counts, and inspect source action/routing behavior. Then continue
migrating legacy graph analysis to the authoritative ledger or traceable exports
in dependency order; never mix graph numeric values with ledger exact strings.
Schedule remains ACTIVE to13:00 Dublin, reserve final15 minutes for handoff.

### Authoritative date totals backend/API — 7 September 2026

`d40474a` extends the shared ledger_summary eligibility/arithmetic pass with optional
daily/monthly grouping and exposes case:view ledger-trends. Ordinary summary JSON
is unchanged. One bounded read returns overall currency totals and sorted date/
currency points with exact money strings and contributing transaction/source IDs.
Monthly labels are first-of-month; actual grouping uses ordering_date, not statement
bounds. No zero-filled missing dates or transfer/balance claims. Same10,000-row
limit and exclusions; unavailable returns no partial points.

Verified:32 targeted backend tests (summary/date grouping/transaction query), including
points summing exactly to summary, >JS-safe cents, rejected exclusion, leap/max dates,
currency separation, scope and size bound. Read-only authenticated synthetic HTTP
compares daily/monthly GBP2100 and10 tx/five source IDs to actual ledger rows;
February returns no points; invalid grouping422. Existing fixture's ten rows all
have January ordering dates even on March statements, so groupedJanuary is correct.
Script check_local_ledger_trends.py; report ledger-trends-check.json. Logs use
/tmp/loupe-neilbyrne-ledger-trends-{tests,live}.out. Backend exec21922, logfile
ledger-trends-backend.out. Frontend unchanged; no real evidence writes.

**Next segment:** connect a bounded exact-date totals panel in the Ledger view,
with daily/monthly selection, applied account/date scope and current query
invalidation. Validate point/overall totals and case/scope before displaying.
Allow inspecting contributing current ledger rows and their existing source action
without presenting excluded rows as contributors. Keep legacy graph Trends clearly
separate until deliberately migrated; no silent amount-sign translation. Use
synthetic daily/monthly source-linked browser acceptance and targeted tests.

### Exact individual ledger money — 7 September 2026

`19a8980` changes TransactionView.to_json amount_minor and non-null
running_balance_minor to integer strings. Python view fields remain integers.
Frontend LedgerTransaction accepts string or legacy number; formatLedgerAmount
scales canonical integer strings exactly and still refuses unsafe numbers or
malformed strings. Table and decision identity both reuse this formatter. API
consumers must accept strings for these two fields; other money contracts unchanged.

Verified:38 targeted backend tests;114 frontend tests across formatting/table/
dialog/API contract passed after updating the contract test's old direct-self
serialization regex (the16 contract tests rerun and pass). TypeScript/scoped lint
pass. Separate synthetic PostgreSQL case4f760410-9f57-4f0e-9c5f-cfc703505871 proves
9007199254740993 amount and -9223372036854775808 balance through real HTTP and table;
decision dialog displays exact amount and is cancelled. Initial browser check
failed on an exact-text locator that omitted the nested currency; corrected
row-identity text locator passes, no product defect. Scripts prepare_local_exact_rows.py
and check_local_exact_rows_ui.cjs; runtime exact-rows-{check,ui-check}.json and
/tmp/loupe-neilbyrne-exact-rows-*.out/png. Backend now exec93997, logfile
exact-rows-server.out. No real evidence changes; synthetic fixture retained.

**Next segment:** continue authoritative analysis integration. Inspect existing
financial trend/graph contracts and build exact per-date currency ledger summaries
using the same row/source inclusion rules rather than legacy signed graph amounts.
Keep count/exclusion scope and transfer limitations visible, ensure totals agree
with ledger-summary, and connect a bounded trends display with source drill-down.
Avoid duplicating eligibility logic: refactor a shared reader if needed with targeted
regression checks. Graph replacement, exports and tracing remain unfinished.

### Exact ledger summary display — 7 September 2026

`b82d010` connects LedgerSummaryPanel to applied account/date filters. Exact-string
money formatting; validates response scope, count reconciliation and signed net
arithmetic with BigInt. Unknown/oversized summaries never become zero. Shows
included proof classes, separate currency posting totals and disjoint exclusion
counts. Hides old totals while refetching; case-scoped financial-ledger invalidation
from corrections and adjudications refreshes it. Held out remains separate.

Verified:43 targeted frontend tests (10 new summary,2 wrapper,14 correction,17
adjudication), TypeScript and scoped ESLint. Authenticated synthetic UI set aside
one GBP400 row: summary changed2100→1700 and10→9 included/1 excluded; restored row
returned2100/10. Two synthetic audit decisions remain; all fixture rows restored.
Screenshot visually inspected: /tmp/loupe-neilbyrne-summary-panel-ui.png. Script
check_local_summary_panel_ui.cjs; report summary-panel-ui-check.json. Logs use
/tmp/loupe-neilbyrne-summary-panel-{tests,tsc,lint,live}.out. Backend unchanged at
exec61007. No real evidence writes. Feature5 is now partial due connected ledger
summary; graph transaction/counterparty/trend cards remain legacy and unmigrated.

**Next segment:** audit exact money in the existing ledger row API/UI before
expanding authoritative analysis. Summary strings now safely exceed JS integer
precision, but transaction_query.TransactionView.to_json currently returns integer
amount_minor/running_balance_minor. Inspect frontend API types, formatting and
all callers; connect a compatible exact-string boundary if unsafe JSON numbers
can lose cents, with beyond-safe-integer end-to-end tests. Preserve original money,
source/correction actions and historical contracts rather than coercing via Number.
Then continue migrating analysis/graph views. Schedule remains ACTIVE to13:00 Dublin.

### Exact ledger summary service/API — 7 September 2026

`0ae8242` adds case:view ledger-summary and ledger_summary.py, one bounded SELECT
joining current transaction/source/account state with populate_existing. Optional
account and inclusive ordering-date filters; max10,000 matching rows. Above limit,
null counts/no money rather than a partial result. Both source and row must be
admitted and counted by default P0/P1/P2; excluded rows counted once in status,
source-status, proof-class priority. Refuses inconsistent ownership, admitted
replacement links and malformed included money/direction/currency. Money is summed
as Python integers and serialized as exact integer strings, currencies separate.
Net postings are not an account balance or transfer-deduplicated money movement.

Verified:37 targeted summary/router/transaction-query tests;9 new summary tests
include >JS-safe money, negative net, currency separation, row/source exclusions,
case/date/account filters, hard limit, ownership and inconsistent replacement.
Read-only authenticated isolated HTTP:10 postings GBP2100, account4 GBP840, and
February0 rows. Script check_local_ledger_summary.py; report ledger-summary-check.json.
Logs /tmp/loupe-neilbyrne-ledger-summary-{tests,final-tests,live}.out. Backend now
exec session61007, logfile ledger-summary-backend.out. No frontend changes, no
real evidence writes. Latest frontend passing targeted checks remain unchanged.

**Next segment:** connect an exact-string LedgerSummaryPanel to the applied
account/date filters with clear inclusion counts and exclusion reasons. Bind
case/account/date response scope, show unavailable without zeros, format via
existing exact money helpers, and use the financial-ledger invalidation prefix
so corrections/exclusions refresh it. Verify synthetic totals and a correction
or exclusion refresh without touching real material. Graph cards remain legacy
until deliberately replaced; do not claim every financial view is authoritative.

### Filtered coverage connected — 7 September 2026

`982c530` connects RequestedCoveragePanel beside the applied ledger filters. One
account and both date bounds are required; checking is explicit. Response case,
account, dates, applied=false and day-count totals are validated. Scope-keyed
state hides prior results after applying another scope or Clear; refresh hides
stale results while fetching. Shows unknown/unavailable, currency-separated counts,
uncovered requested dates, intersecting period IDs and recorded exclusions.
Fully covered printed dates explicitly do not certify complete extraction.

Verified:15 targeted frontend tests (10 new coverage + existing filters/wrapper),
TypeScript and scoped ESLint. Read-only authenticated browser checks both existing
synthetic accounts (February0 versus28 covered days), Clear removes old coverage,
and source-period details remain available. Screenshot visually inspected at
/tmp/loupe-neilbyrne-filtered-coverage-ui.png. Existing check_local_ledger_filters_ui.cjs
now verifies coverage too; report ledger-filters-ui-check.json. Logs use
/tmp/loupe-neilbyrne-filtered-coverage-{tests,tsc,lint,live}.out. Backend restarted
with final036f700 code as exec session83809; logfile filtered-coverage-backend.out.
No real evidence changes. All ten whole-feature statuses remain unchanged.

**Next segment:** begin the authoritative-ledger analysis connection (feature5)
by inspecting existing financial aggregate/proof-class/source-admission rules and
current graph totals. Build a bounded read-only exact-money summary from current
ledger rows, preserving currencies and explicit included/excluded populations;
never total quarantined/superseded/rejected or unverified evidence as verified.
Connect and test in small units before replacing any legacy graph analysis view.
Do not silently imply ledger corrections update graph data. Coverage exact-PDF
bound citations and wider search completeness still remain. Schedule ACTIVE to13:00.

### Requested-date coverage service/API — 7 September 2026

`036f700` adds case:view requested-statement-coverage requiring account and closed
start/end dates. Filters the account in SQL before its bounded500-period read.
Reuses printed-bound exclusions and unions clipped original periods per currency,
including both outside tails as uncovered requested dates. Clipping before union
prevents outside-only periods becoming false coverage citations. Missing eligible
bounds, oversized accounts and inconsistent source ownership remain unavailable;
foreign/absent account404, invalid interval422. No transaction-completeness claim.

Verified:34 targeted coverage/ledger-router tests pass; after adding explicit
missing-account protection and requested oversized-account assertions, the coverage
suite passes again. Read-only authenticated local HTTP compares February gap28 days
versus enclosing export0, and refuses unauthenticated/missing-account/reversed-date
requests. Script check_local_requested_coverage.py; report under data/local-runtime/
requested-coverage-check.json. Logs /tmp/loupe-neilbyrne-requested-coverage-*.out.
No full unchanged frontend suites repeated; this unit has no UI changes.
Backend restarted as exec session41598, logfile requested-coverage-backend.out.
Its loaded endpoint preceded the final direct-service None-account guard (HTTP
already requires UUID); restart on the next integration check to load the final code.
Use explicit backend workdir for unittest and root workdir for edits/scripts;
wrong-cwd test invocations failed before running and were corrected.

**Next segment:** connect a requested-coverage result panel beside applied ledger
filters. Require one selected account and both dates; preserve case/account/date
response bindings, uncertainty/exclusions and separate currencies. Do not show old
coverage for changed applied filters. Verify live February-gap and enclosing-export
results using existing synthetic fixture. Exact PDF date-bound navigation and
broader search coverage remain; all ten overall feature statuses unchanged.

### Current ledger filters connected — 7 September 2026

`a6ee80c` connects deliberate account lookup/selection and inclusive optional
ordering-date bounds on Ledger. Draft choices do not alter the existing answer;
Apply submits them and Clear restores all admitted rows. Account lookup uses the
existing case:view endpoint, validates response case scope, and displays the100-
result limit/has_more notice. No account auto-selection. Case or held-out mode
changes remount all filter/source/correction state. Held out remains separate.

Verified:20 targeted tests across LedgerFilters/CorrectableLedger/LedgerPanel,
TypeScript and scoped ESLint. Read-only authenticated Chromium against existing
synthetic coverage case e0da5581-a1ac-4db5-a3a9-e17021fb807a selects its gap account,
keeps10 rows while drafting, applies February bounds to0 rows with limitation,
and restores10 after Clear. Screenshot visually inspected. Script:
check_local_ledger_filters_ui.cjs; report data/local-runtime/ledger-filters-ui-check.json;
screenshot /tmp/loupe-neilbyrne-ledger-filters-ui.png. Logs use
/tmp/loupe-neilbyrne-ledger-filters-{test,tsc,lint,live}.out. No backend/evidence edits.
Chromium needs escalation for macOS MachPort access; successful escalated check
followed the sandbox failure. Initial root npx test invocation was stopped; run
frontend commands with explicit frontend_v2 workdir. Unchanged full gates reused.

**Next segment:** quantify coverage for a selected account and requested date
interval, including requested dates outside known printed bounds; never equate
printed date coverage with complete extraction or absence of transactions. Reuse
coverage_query interval-union logic and preserve exclusions/currency separation.
Return unavailable for oversized or cross-case data. Add targeted backend/API/UI
checks and a synthetic February-gap versus enclosing-export comparison. Broader
graph, exports, transfers and tracing remain. Schedule ACTIVE until13:00 Dublin.

### Scoped empty ledger answers — 7 September 2026

`e13375c` corrects empty LedgerPanel answers when an account or date filter is
supplied: no matching rows no longer claims the whole case has none. Both empty
and populated answers show the requested scope and explain ordering-date bounds.
Empty answers explain that they do not prove no transactions occurred or complete
records. A reported-count discrepancy remains visible even if zero rows arrive.
The existing account/date hook contract is used; new filter controls and measured
search coverage are not claimed complete.

Verified: 15 targeted LedgerPanel tests, TypeScript build and scoped ESLint pass.
The named CorrectableLedger.test.tsx does not exist; only the actual 15-test file
was collected, and that is the reported count. No backend changes; earlier full
backend 3,763, frontend 960 and Chromium 11 passing gates remain baseline evidence,
not reruns of this change. Logs: /tmp/loupe-neilbyrne-empty-ledger-{test,tsc,lint}.out.

The earlier final read-only check succeeded after the upgrade: frontend/backend/
engine returned HTTP200 at 07:47UTC. Both real PDF hashes match their inspection
baselines and each has zero evidence_files copies in isolated PostgreSQL. Report:
data/local-runtime/morning-verification.json. AI processing remains untested.

The account/date controls planned here are now connected at a6ee80c above.

### Historical balance diagnostics connected — 7 September 2026

`42e42f1` displays saved running-balance comparisons inside Decisions → Original
and replacement readings. The panel explicitly labels them as the comparison at
correction time, not a recalculation against later changes. Missing old diagnostics
are explicit; malformed/currency-inconsistent optional data does not hide the two
readings. Source links retain original transaction IDs and case-bound dialog state;
no links are offered without case context.

**Verified:**960 frontend unit tests,11 Chromium,TypeScript/full ESLint. Backend
unchanged; its latest full gate remains3,763 financial tests, zero skips. Read-only
live browser check reopens the existing running-balance correction decision, shows
saved400→410 diagnostics and opens the highlighted replaced original PDF row.
Script check_local_balance_history_ui.cjs uses running-balance-ui-check.json; it
makes no record changes. Screenshots /tmp/loupe-neilbyrne-balance-history-ui.png
and balance-history-source-ui.png. Backend remains exec session97535 from coverage.

The prior 09:00 cutoff plan has been superseded by the 13:00 authorization above.
Feature status remains partial 1,2,3,4,6,10; remaining 5,7,8,9. None of these ten
whole features is fully complete.

### Printed statement coverage connected — 7 September 2026

`8b6c9ad` adds protected case:view statement-coverage and a Ledger panel.25-account
pages,500-period hard limit per account; oversized/cross-case-source data returns
unavailable rather than partial or leaked coverage. Reuses the existing printed-bound
rule and retains missing/derived dates/nonadmitted-source exclusions. Unions all
eligible intervals, including enclosing exports, before calculating internal gaps,
so long exports do not falsely appear to leave months missing. Counts overlapping
days once, keeps currencies separate, and retains source period/document/file IDs.
The panel explains that covered bounds do not prove complete extraction or absence
of transactions, and dates outside first/last known bounds are not assessed.
Query key uses financial-ledger case prefix for existing write invalidations.
Exact date-bound citation navigation and integration with transaction searches remain.

**Verified:** all 3,763 backend financial tests, zero skips;957 frontend unit;
11 Chromium;TypeScript/full ESLint. Synthetic PostgreSQL/browser accounts show a
28-day February gap versus a0-day gap/90-covered-day union when an enclosing export
spans January–March. Tests cover nesting, duplicate/contiguous bounds, leap day,
maximum calendar date, exclusions, source ownership and the500-period guard.
Scripts prepare_local_coverage_ui.py then check_local_coverage_ui.cjs use a separate
fixture with a completed synthetic audit run,5 documents/10 transactions; no real
source material. Case `e0da5581-a1ac-4db5-a3a9-e17021fb807a`. Reports under
coverage-check.json/coverage-ui-check.json; screenshot
`/tmp/loupe-neilbyrne-statement-coverage-ui.png`. Backend current exec session97535,
log `/tmp/loupe-neilbyrne-coverage-backend.out`. Existing synthetic fixtures unchanged.

**Next segment:** check clock and timebox another bounded integration if before
07:45UTC. Candidate options: expose the newly retained running-balance audit details
in correction history, or improve source navigation for recorded coverage periods
without inventing a page for printed dates. Native revalidation, automatic PDF
nomination/full extraction and canonical graph/exports/tracing remain larger work.
Feature6 is now partial, alongside1,2,3,4,10; remaining5,7,8,9. No entire remaining
feature is completed. At07:45UTC switch to final verification and a plain-language
nine-o'clock report retaining all ten features; pause automation by08:00UTC(09:00Dublin).
The active schedule remains every5 minutes. Real PDFs remain read-only/un-ingested.

### Running-balance correction diagnostics — 7 September 2026

`4b70844` adds current/proposed running-balance comparisons in correction preview
and stores them in the immutable correction event. Both source-row orders are shown;
post-transaction balance convention, correct glyphs and coverage remain explicit
conditions, so no class is promoted and existing revalidation reservations remain.
Only printed independent opening balances anchor the first interval. Missing-balance
rows accumulate movement; excluded rows interrupt the chain; superseded versions
are not counted twice. Limits1,000 period rows/100 displayed mismatches per walk;
full bounded comparison counts and truncation are explicit. Missing/ambiguous order,
malformed arithmetic or account/currency mismatch is unavailable, not a clean pass.
Exact decimal strings and original transaction source links survive recording.
Document revision now binds actual running balance/order/amount/direction/account/
currency/period fields in addition to hashes, so changing a balance invalidates a
review even without updating content_hash. This also strengthens duplicate revisions.

**Verified:** all 3,753 backend financial tests, zero skips; 952 frontend unit;
11 Chromium; TypeScript/full ESLint. Initial audit-snapshot shape mismatch was caught
and fixed: running_balance_comparison is null in before and the full reviewed result
in after. Live synthetic PDF/PG/browser preview400→410 shows0→1 mismatch in source
order, recordsP3, and opens the original replaced row's highlighted PDF source.
Scripts prepare_local_running_balance_ui.py then check_local_running_balance_ui.cjs
create/mutate only a fresh labelled synthetic case. They inherit the ledger-source
fixture's open audit-run convention; this fixture is not a full ingestion acceptance.
Case `5675421f-0860-4048-abe1-902241a1feec`, original
`0ac8a69d-e642-45e6-9bf6-198f2fe7afd0`, replacement
`d68a7a5f-5b37-4398-b10a-f74aa0c8c27b` (`TX-DGAZ-KGTF-F0NH`). Reports under
running-balance-check.json/running-balance-ui-check.json. Screenshots under
/tmp/loupe-neilbyrne-running-balance-preview-ui.png and running-balance-source-ui.png.
Current isolated backend exec session23096, log `/tmp/loupe-neilbyrne-balances-backend.out`.

**Next segment:** inspect remaining complete-period/printed-control checks and their
existing services before choosing the next bounded unit. Native mandatory-control
revalidation and proven running-order/coverage still remain; this diagnostic does
not finish feature3. Period coverage/continuity may offer an independently connectable
capability under feature6 if full native revalidation cannot fit before the handoff.
Use existing exact-money services rather than inventing control facts. Still partial
features1,2,3,4,10; remaining5,6,7,8,9. Check clock before starting. Reserve07:45–08:00UTC
for final verification/checklist/handoff and pause the active5-minute automation by
09:00 Dublin (08:00UTC). Real PDFs remain read-only and un-ingested.

### Explicit PDF column suggestions — 7 September 2026

`aac46b0` adds a deliberate source-picker aid: scan only the first ten stored rows
for exact supported labels, preserving original text and positions and showing
competing meanings without choosing. No fuzzy OCR repair, substring matching or
generic Date-role guess. Every suggestion requires a click; no source rows become
selected. Source reload clears suggestions/selection. Accepted meanings use the
existing revision-bound manual mapping, not a new automatic-extraction provenance.
The aid does not persist a separate header event or claim transaction classification.
Both text and grid contracts now support transaction_date separately from booking
and value dates. Existing snapshots serialize identically; no migration/rewrite.

**Verified:** all 3,741 backend financial tests, zero skips; 950 frontend unit;
11 Chromium; TypeScript/full ESLint. Fresh synthetic PDF browser check accepted
Transaction Date/Amount labels, selected only the first actual data row, kept the
header/other row unselected, saved one pending candidate and preserved the same
mapping on retry. No ledger admission or real evidence use. Repeatable scripts:
prepare_local_header_ui.py then check_local_header_ui.cjs. Separate fixture/report
header-check.json/header-ui-check.json; existing candidate-check.json unchanged.
Case `b89ed1d8-b40e-492a-8365-1b66e5d2eef8`, file
`9101c4b5-2e9f-4533-8062-b37017bf0750`, mapping
`7380d10e-2a48-4f20-8fdf-d51ba9f37586`. Screenshot:
`/tmp/loupe-neilbyrne-header-suggestions-ui.png`. Current isolated backend exec
session55961, log `/tmp/loupe-neilbyrne-headers-backend.out`, supports new date role.

**Next segment:** move to retained feature3, inspecting existing printed-control,
reconciliation and running-balance modules/contracts. Implement a bounded missing
accuracy check and its appropriate connection, preserving exact integer money,
source evidence, explicit unavailable outcomes and computed classification. Automatic
transaction nomination, complete extraction/date/account context and complete PDF
coverage remain unfinished; do not spend the whole remaining window presenting
small selection aids as full extraction. Independent accuracy checks are authorized.
All ten features remain: partial1,2,3,4,10; remaining5,6,7,8,9. Check the clock before
a new segment. Keep every5-minute schedule to09:00 Dublin; final verification and
handoff start07:45UTC, pause no later than08:00UTC.

### Source date uncertainty connected — 7 September 2026

`46a3417` adds conservative numeric date assessment before review: keep both valid
numeric orders, missing years, ambiguous two-digit centuries, invalid calendar values
and unsupported text. Never infer locale/year/century/period context or OCR repairs.
Even unambiguous calendar formats require source review. Named-month dates remain
unsupported/manual. The service rebinds current candidate originals and processes
only proposed booking/value/transaction columns, retaining exact locators/spans,
origin and review revision. Unknown columns remain unclassified. Read-only case:view
GET date-assessment and a review panel show proposals with source highlights; they
never fill review fields or write ledger data, including on finalized readings.

**Verified:** 3,739 backend financial tests, zero skips; 944 frontend unit tests;
11 Chromium tests; TypeScript/full ESLint. The first full suite correctly caught
missing package exports for source_dates; assess_date_text and assess_candidate_dates
are now exported and the full rerun passes. Live browser on the existing synthetic
case shows both month/day alternatives for01/02, no fabricated full year, and the
highlighted exact date cell. `scripts/check_local_candidate_dates_ui.cjs` is read-only
and works against candidate-check.json's original synthetic01/02 fixture, including
when finalized. Screenshot `/tmp/loupe-neilbyrne-candidate-dates-ui.png`. Backend now
exec session36691, log `/tmp/loupe-neilbyrne-dates-backend.out`, current date route
loaded via local_app.py. No real evidence modified or ingested.

**Next segment:** inspect existing PDF extraction and stored-grid source picker,
then connect a bounded automatic nomination aid where source evidence supports it.
Any suggested column meanings/rows must remain proposals for explicit review, with
headers/nontransaction rows not silently admitted. Reuse exact source binding and
revision protections, preserve unsupported/uncertain cases, and keep external AI
disabled. Account context, full date-context resolution, complete statement controls
and remaining financial features are not complete. The retained checklist still has
partial1,2,3,4,10 and remaining5,6,7,8,9. Check the clock; schedule remains every5
minutes until09:00 Dublin, reserving07:45–08:00UTC for final verification/handoff.

### Finalized review protection and correction round trip — 7 September 2026

`a7c231d` makes review responses explicitly report nullable case-scoped
finalization_id without changing original/history/revision. Finalized resolved and
rejected forms retain the original fields/history but disable edits and remove
review/account write controls. Source assessment remains usable with independent
currency state. Missing seal-state fields fail UI validation. Refreshed finalization
state remounts the fields even when the review revision itself has not changed.
Provisional account creation checks before audit and again under the file lock;
interleaved finalization cannot leave an unused account behind.

**Verified:** all 3,728 backend financial tests, zero skips; 937 frontend unit tests;
11 Chromium tests; TypeScript/full ESLint. Live synthetic browser check confirms
read-only review/history/source assessment and authenticated account setup409.
A finalized GBP12.34 row was corrected to12.35; only the replacement remains in
the active ledger, classification staysP3, and the original receipt acknowledges
the correction and opens the highlighted original PDF row. No real evidence used.

New script `scripts/check_local_finalized_review_ui.cjs` runs AFTER fresh
prepare_local_finalization_ui.py and check_local_finalization_ui.cjs. It mutates
only their synthetic case and needs a fresh fixture to repeat the correction.
Latest case remains `5adf884c-aede-4a8d-923e-c3f240d2f708`; original transaction
`85c81954-4957-4510-91b3-16981fc321bc` is now superseded by
`91628f90-46f2-4f33-a098-7e6d9f3bb320` (`TX-FF03-S888-TJ4W`). Report:
`data/local-runtime/finalized-review-ui-check.json`. Screenshots:
`/tmp/loupe-neilbyrne-finalized-review-ui.png` and
`/tmp/loupe-neilbyrne-finalized-correction-source-ui.png`. Current isolated backend
exec session49440, log `/tmp/loupe-neilbyrne-readonly-backend.out`, launched through
local_app.py. It contains the new required response field and account guard.

**Next segment:** the deliberate source-selection → review → finalization → ledger
correction path is connected. Continue the retained feature1/2 work: inspect existing
PDF extraction/nomination and date/account assessment contracts, then implement a
bounded source-bound uncertainty/nomination improvement. Ambiguous date order or
missing years must remain explicit; do not silently infer context or admit automatic
proposals. External AI remains disabled. Complete controls/coverage, canonical ledger
views, exports and tracing are still outstanding. All ten features remain visible;
partial1,2,3,4,10, remaining5,6,7,8,9. No whole feature newly completed.
Schedule remains ACTIVE every5 minutes through09:00 Dublin (08:00 UTC). Check the
clock before a new segment; reserve07:45–08:00UTC for final verification/handoff.

### Finalization API and UI connected — extended window, 7 September 2026

`a2f4337` exposes protected case:view preview and case:edit finalization endpoints,
with authenticated actor/trusted storage resolution and ordinary scoped errors.
Preview releases locks in finally. The receipt echoes its manifest revision.
The saved-batch UI checks all batches from the PDF, requires explicit documentary
financial-row and incomplete-coverage acceptance/reason, blocks double/uncertain
writes until reload, validates receipt scope/revision/count/unique IDs, and refreshes
original-case caches even after unmount. Receipt links open the exact source image
and highlight. Original rows remain P3/method4 outside default verified totals.

**Verified:** 3,725 backend financial tests (zero skips), 934 frontend unit tests,
11 Chromium, TypeScript/full ESLint. Live browser finalization shows two new ledger
rows; identical HTTP retry preserves IDs; proof-class injection422 and changed
request409; reload shows the receipt without another write action; source image
and highlighted original row checked visually. Scripts prepare_local_finalization_ui.py
and check_local_finalization_ui.cjs require a fresh synthetic fixture in that order.
Current backend launched by local_app.py, exec session25410, logs at
`/tmp/loupe-neilbyrne-finalization-ui-backend.out`; new routes/method/shape active.

Latest synthetic UI case `5adf884c-aede-4a8d-923e-c3f240d2f708`, file
`c39d567e-5f9b-4e0c-b1ea-ccc9245f855b`, seal
`dd95cc88-e229-4ae1-a70f-90aa3805668b`, source document
`3273797c-470a-4eec-8c77-a93674bd6ef7`. Two GBP12.34 P3 rows with original PDF1234
kept intact. Full IDs: data/local-runtime/finalization-ui-check.json. Screenshots:
/tmp/loupe-neilbyrne-finalization-preview-ui.png, finalization-result-ui.png,
finalization-source-ui.png (each with loupe-neilbyrne prefix). candidate-check.json
now names this FINALIZED fixture; recreate before older pending-candidate scripts.

**Historical next segment (completed in a7c231d above):** make candidate review screens explicitly read-only after sealing
while retaining all originals/history/source assessment, and verify a finalized
ledger row's correction/source/receipt round trip. Backend already refuses review
writes after seal, but the old form still offers controls that lead to that409.
Prevent pointless provisional-account setup for a sealed reading too. Then continue
remaining financial development from the retained checklist in dependency order:
automatic PDF extraction/nomination and broader uncertainty/coverage/reconciliation
remain, alongside canonical ledger wiring to all views/exports/tracing. The deliberate
stored-grid workflow is connected, but do not mark whole features complete on that
basis. All real PDFs remain untouched/read-only and absent from the database.
Schedule ACTIVE through09:00 Dublin (08:00 UTC); final15 minutes for handoff.

### Atomic materialization service — extended window, 7 September 2026

`27f8328` adds CandidateFinalizationRequest, preview_candidate_finalization and
finalize_candidates. A fresh locked snapshot covers all reviews, original source
bindings, exact reading/account context, complete source-pair comparisons and
actual bytes. Requests require manifest revision plus explicit documentary-row
and incomplete-coverage acceptance/reason. One transaction writes the selected
source document, document-wide integer transaction batch, seal and review/source
links. P3/method4/selected_document_rows are computed/fixed by the service; no
caller proof class or guessed control balances/periods. All rejected reviews
remain in the snapshot. Source locators and all original cell readings survive.

Limits100 mappings/1,000 total candidates; complete pair check up to499,500 pairs
rather than treating the bounded UI reuse report as a permit. Case NO KEY UPDATE
serializes candidate-file aliases without blocking FK inserts; file/text/geometry/
candidate/sorted-account locks protect the write. Same-source ledger readings
are refused. Identical retries return original IDs; changed requests conflict.
A racing losing attempt can have a zero-row completed audit, but fast retries
create no run. Existing separate audit termination can fail after data commit;
receipt-based retries still cannot duplicate money.

**Verified:** 3,721 backend financial tests, zero skips (14 new writer tests).
`scripts/check_local_candidate_materialization.py` passed on isolated PostgreSQL:
fault after all rows+links flush rolls back source/transactions/seal; two actual
lock waiters produce one receipt, two distinct equal-content rows, stable retry
IDs and review-after-seal refusal. No real PDFs were processed or changed.
Frontend unchanged: last927 unit/11 Chromium plus TypeScript/full ESLint.

Latest synthetic case `2d8dbffc-1b04-42e5-9ab3-7aa92f9555a0`, file
`ab69826c-f53b-4310-800f-49c61431eb8a`, seal
`a12db21a-54a0-456a-b409-5f7ba07161db`, source document
`5a98b864-517d-4cfb-9478-e4412c48a323`, two P3 rows of1234 minor units.
`data/local-runtime/candidate-materialization-check.json` has full IDs.
`candidate-check.json` now points at this FINALIZED fixture: recreate a pending
fixture before older source-selection/review scripts expecting pending candidates.

**Next segment:** expose authenticated case:view preview and case:edit finalization
routes with ordinary scoped404/stale409/invalid422/generic500 handling, and update
write-route permission inventory. Then add a deliberate UI preview/acceptance panel
with two explicit confirmations, reason, fixed P3/incomplete-coverage warning,
review revision/scope validation, synchronous retry lock and links to resulting
ledger rows. Invalidate original case caches even if UI unmounts; do not assume
resolution means inclusion in verified totals. Test HTTP retries/scope and real
browser flow, then checkpoint. Restart the isolated backend before HTTP tests;
its currently running process predates the new services/migrations. Migration
remains20260907_candidate_finalizations. Schedule ACTIVE through09:00 Dublin
(08:00 UTC), reserving07:45–08:00 UTC for handoff.

### Finalization storage — extended window, 7 September 2026

`f0ddde3` adds immutable FinancialCandidateFinalization and
FinancialCandidateTransaction records. One seal per case/file/source document;
unique candidate/transaction/source-claim links retain the original reviewed
transaction after ledger state changes. PG insertion guards verify source/run/case
and digest/method/shape scope, plus the candidate's latest resolved review and
transaction scope. UPDATE guards prevent rewriting; existing deletion cascades
remain. File locks serialize finalization with mapping/candidate/review insertions,
which are refused after sealing. Service review returns409 pointing to corrections;
identical mapping retries still return the original, but new mappings are refused.

**Verified:** 3,707 financial tests pass, zero skips (six new storage/service tests).
Isolated PG migration20260907_candidate_finalizations applied; script
`scripts/check_local_candidate_finalizations.py` passed ten live scope/duplicate/
immutability/post-seal/downgrade checks. It copies freshly generated synthetic
fixtures and rolls every inserted row back. No real evidence or cases changed.
Frontend unchanged: last verified927 unit/11 Chromium, TypeScript/full ESLint.
The running backend needs restart before exercising the new workflow/guards.

**Next segment:** implement the actual atomic whole-file writer and preview. Read
all current mappings/candidates/reviews under file→text→geometry→candidate locks;
refuse pending readings, empty resolved set, overlap/uncomparable/truncated reuse,
stale source bytes, cross-case or wrong-currency accounts and existing ledger
readings of this file/digest. Compute canonical manifest/revision and stable source
claims independently of proposed meanings. Use complete document-wide occurrence
hashing; create method4/selected_document_rows/P3 source and exact integer drafts,
then finalization+links in the same transaction. Receipt snapshots must include
all rejected and resolved review revisions plus the verified-byte receipt, actor
and explicit documentary-financial-row attestation/reason. Retry should return the
same durable receipt/transaction IDs; no second run's duplicate rows. Validate
actual PG concurrent/retried writes before exposing APIs or UI. Whole-file sealing
refuses adding omitted rows later; document that limitation plainly. Limits1000
readings/transactions do not imply full extraction of larger PDFs. No public
finalize endpoint exists and no saved app candidates have been materialized.
Schedule ACTIVE every five minutes to09:00 Dublin (08:00 UTC), handoff07:45 UTC.

### Selected-row classification — extended window, 7 September 2026

`ed656da` adds SourceShape.selected_document_rows for documentary financial rows
with incomplete document/control coverage. Computed P3 is retained for every
reconciliation outcome, including balanced. Persisted source metadata round-trips,
and both reclassification and correction verification keep the original source
and transaction at P3/outside default totals. P3 UI wording describes incomplete
coverage as well as failed/unavailable checks. Narrative assertions remain P4;
this shape must not be used to relabel figures in letters or interviews.

**Verified:** 3,701 financial tests, zero skips (two new safety/persistence tests
and expanded complete shape/outcome matrix); 927 frontend unit/11 Chromium,
TypeScript/full ESLint pass. No new database migration in this unit. The local
backend still needs restart before exercising the new writer/method/shape.

**Next segment:** immutable candidate-to-transaction links and source claims, then
atomic sealed whole-file finalization. All saved candidates must be resolved or
rejected; retain rejection history and refuse unresolved source overlap/reuse.
Use a whole-document batch for occurrence hashes, current source/review locks,
verified bytes, method investigator_review and selected_document_rows shape. A
future request must explicitly attest documentary financial rows with a reason;
never infer that from a table or accept caller proof class/coverage promotion.
Use durable finalization identity for retries and reroute post-finalization edits
to ledger corrections. Test concurrent/retried writes on isolated PostgreSQL
before exposing API/UI. Detailed limits/provenance remain in the bridge plan.
Heartbeat ACTIVE every five minutes through 09:00 Dublin (08:00 UTC), reserving
07:45–08:00 UTC for handoff. No candidates admitted yet.

### Investigator reading provenance — extended window, 7 September 2026

`08b1540` introduces extraction method4, investigator_review, with corresponding
source/transaction constraints and frontend wording. It is a separate human
reading method, not an automated tier or a verification grade. The transaction
writer refuses mixing human/automated document and row methods. Native shapes
still require native extraction; unchecked reviewed statements remain P3/outside
default totals. Original extraction provenance/review history remain necessary.
Existing duplicate ranking gives review alone no preference over an equally
checked automated reading; only method3 is labelled a model fallback.

**Verified:** 3,699 financial tests, zero skips; 927 frontend unit and 11 Chromium;
TypeScript/full ESLint pass. Isolated PostgreSQL migrated to
`20260907_investigator_reading`. `scripts/check_local_reading_method.py` verifies
both table constraints accept4/refuse5 and downgrade refuses existing human
readings, with all synthetic row changes rolled back. No candidates materialized.
The running backend predates this change: restart it before exercising a writer
using method4. Frontend Vite already serves changed labels.

**Next segment:** represent selected PDF financial rows without asserting the whole
PDF is a statement or that every transaction was selected; settle the conservative
computed source classification/coverage contract. Then implement immutable source
claims and candidate→transaction links, sealed whole-document finalization with
retry/concurrency tests, review-after-materialization rules, and UI/API connection.
Existing source-byte verification is ready to call inside that locked boundary.
Schedule remains ACTIVE every five minutes through 09:00 Dublin (08:00 UTC).

### Source bytes verified — extended window, 7 September 2026

`43b2402` adds the source-byte prerequisite for materialization. It freshly binds
saved candidates, scopes the evidence lookup, streams the trusted resolved file,
compares its SHA-256, refuses missing/changed/non-regular/oversized sources and
observed mutation during reading. A timestamped receipt preserves the old immutable
original snapshot; this does not establish extraction accuracy or admit money.
No HTTP writer has been exposed. Callers must retain source/review locks through
rebinding, this check and their future atomic write; filesystem changes after the
read cannot be prevented by database locks.

**Verified:** all 3,696 backend financial tests pass, zero skips (11 new source-byte
tests). Prior frontend gates remain 927 unit/11 Chromium plus TypeScript/ESLint;
no frontend changes in this unit. Tracked implementation is clean after checkpoint.

**Next segment:** resolve truthful provenance for human-reviewed PDF readings by
examining extraction-layer schema/constraints and consumers. Existing layers must
not be repurposed to claim native/template/model extraction. Then implement the
immutable candidate-to-transaction/source claims and atomic whole-document writer
with real PostgreSQL retry/race validation. Keep reviewed candidates outside totals
until that connection and computed classification are verified. The byte checker
is now available as `verify_candidate_source_bytes` from the financial package.
Schedule ACTIVE every five minutes until 09:00 Dublin (08:00 UTC); last15 minutes
reserved for the new morning handoff. The earlier closing report below is history.

### Morning handoff — 7 September 2026, overnight window closing

The authorized overnight development is checkpointed. The final ten-feature status
and checked subitems are retained in `docs/loupe-development-checklist.md` under
Morning handoff. Whole features **1,2,3,4,10 are partial**; **5,6,7,8,9 remain**.
No whole remaining feature is claimed complete. The older “Item8 complete” near the
top refers to an earlier wiring-plan item, not feature8 of the overnight checklist.

Current verified gates: 3,685 financial tests (zero skips), 927 frontend unit tests,
11 Chromium tests, TypeScript/full ESLint. Local application/service checks at
04:39–04:41 UTC passed, with migration20260907_candidate_reviews. Engine's OpenAI
health flag checks key presence only; external AI is not tested or enabled with a
real key in this isolated runtime. Real PDFs remain unchanged/untracked; no real
PDF was ingested into a database. Synthetic UI case:
`61272494-00de-4a97-8ba9-77fce4be2f24`, frontend55174. The app-panel request to show
that case was queued by Codex; the URL is valid and the frontend is responding.

Latest implementation f94e347; state commits follow. No uncommitted implementation
remains. The next substantive dependency is ledger materialization, with constraints
in docs/loupe-pdf-ledger-bridge.md. Do not mistake resolved candidates for admitted
transactions or source binding smoke checks for transaction accuracy. Heartbeat `continue-loupe-development` was confirmed PAUSED through automation_update
at approximately 04:42 UTC (05:42 Dublin), before the cutoff. The local application
was left running; no post-cutoff development is authorized.

### Account audit display corrected — 7 September 2026 overnight

`f94e347` distinguishes the known provisional_candidate_account operation from
transaction imports in notices and the Attempts table. Refused/failed setup keeps
its audit/error visible without claiming missing imported ledger rows. Mixed
histories count genuine imports separately. Nonzero import counters contradicting
the operation tag retain ordinary import warnings. Unknown statuses are not guessed.

**Verified:** 927 frontend unit tests (five new operation/notice tests), 11 Chromium
tests, TypeScript/full ESLint pass. Backend is unchanged from the 3,685-passing-test
checkpoint. Live browser source-reuse/navigation recheck passes; the screenshot
`/tmp/loupe-neilbyrne-source-reuse-ui.png` now also shows the corrected setup notice.
All implementation and state checkpoints are local; real PDF files are untracked.

**Next run:** check clock. Reserve 04:45–05:00 UTC for final local availability,
working-tree/checklist verification and the morning handoff, then pause heartbeat
before 05:00 UTC. Do not rush the materialization writer: its source shape/layer,
whole-document occurrence handling and immutable transaction-link issues are recorded
in `docs/loupe-pdf-ledger-bridge.md`. The current workflow reaches saved/resolved
candidates, not ledger admission. The ten main remaining features are still partial
or remaining; no whole feature has been completed in this overnight window.

### Cross-mapping source reuse checks completed — 7 September 2026 overnight

`7ee220b` adds a bounded read-only check across saved candidate batches from one
PDF. A shared source-file lock and fresh source binding precede the snapshot.
Repeated stored grid rows survive changes to proposed meanings; text overlap and
possible bounding-area overlap are distinct findings. Mixed/unlocated sources may
be uncomparable. Rejected rows stay counted but are not compared. Limits and
truncated details are explicit (100 mappings/1,000 readings, 10,000 pairs, first100
finding details). No check is a duplicate exclusion or ledger materialization permit.
The UI can open the exact candidate in either batch; snapshots must be rerun after
review changes. Identical amounts at distinct source rows alone are not findings.

**Verified:** 3,685 financial tests (zero skips), 922 unit tests, 11 Chromium tests,
TypeScript/full ESLint pass. Nine backend/five UI tests added. A live authenticated
browser compared three synthetic reading pairs, found one repeated source row and
opened the exact candidate from its finding. Script:
`scripts/check_local_candidate_reuse_ui.cjs`; screenshot
`/tmp/loupe-neilbyrne-source-reuse-ui.png`; backend currently logs to
`/tmp/loupe-neilbyrne-reuse-ui-backend.out`.

**Immediate next fix found by visual QA:** a failed provisional-account setup audit
run currently triggers ingestion-specific warning language claiming missing ledger
transactions. Distinguish this known operation in run display while retaining its
audit/error visibility. Then final integration verification/handoff before cutoff.
Materialization remains substantial: whole-document occurrence indexing, truthful
source shape/extraction-layer provenance, printed controls and actual-byte verification
need resolution alongside immutable transaction links. Details are recorded in
`docs/loupe-pdf-ledger-bridge.md`; do not guess an extraction layer to fit the enum.

### Provisional candidate account setup completed — 7 September 2026 overnight

`dd7fc5b` lets a reviewer explicitly set up a provisional account using currency,
a descriptive label and a reason. It reuses AccountDraft.unidentified/record_account
and records the actor, request/reason and outcome in an ingestion run. The label is
not a printed identifier or holder name. Identity is scoped to source file, currency
and label. Source locks/rebinding and expected review revision precede the write;
same-label concurrent creators reuse one account and first-seen run is preserved.
A candidate cannot use this document-scoped account from another PDF. Known-account
identification/merging remains separate. Account creation does not change a candidate
review, proof classification or ledger totals; UI selection still requires review.

**Verified:** 3,676 financial tests (zero skips), 917 unit tests, 11 Chromium tests,
TypeScript/full ESLint pass. Added nine account-service tests, one cross-source
review guard test and five account UI tests. Real PostgreSQL contention observed
two waiting creators and one account; authenticated retry returns that account,
stale review returns409, review stays unchanged and zero transactions exist.
A real browser then created/selected a provisional account and resolved a synthetic
12.34 GBP reading with applied:false. Logs `/tmp/loupe-neilbyrne-accounts-*.out`
and `/tmp/loupe-neilbyrne-account-ui-live.out`; screenshot
`/tmp/loupe-neilbyrne-provisional-account-ui.png`. Repeatable scripts:
`scripts/check_local_candidate_accounts.py`, `scripts/check_local_candidate_account_ui.cjs`.
Backend log now `/tmp/loupe-neilbyrne-account-ui-backend.out`.

**Next:** atomic materialization of resolved candidates with source-row identity
across mapping revisions, immutable links, review-after-materialization rules,
computed classification and existing reconciliation. Read docs/loupe-pdf-ledger-bridge.md
before writes. Still missing: automatic PDF nomination/extraction integration,
known-account establishment/merge, statement controls, projection and the remaining
ten-feature checklist. Do not equate resolved candidates with admitted transactions.

### Stored-PDF row selection completed — 7 September 2026 overnight

`9ddfe63` adds candidate_sources service and case:view list/table endpoints.
Financial → Ledger → PDF readings → Choose PDF rows exposes stored page/table
selection with an authenticated source image. Column meanings start unidentified;
no rows are preselected. Rows inferred from text spacing are labelled accordingly.
Exact row/cell coordinates and text are submitted through the existing case:edit
candidate writer. Source revisions and echoed selections are checked. Source reload
resets the form, and uncertain submissions cannot be repeated without that reload.
Tables/cells beyond candidate bounds are refused without silently truncating data.

**Verified:** 3,666 financial tests (zero skips), 912 unit tests, 11 Chromium tests,
TypeScript and full ESLint pass. Nine backend/seven UI tests added. A real local
Chromium check selected one synthetic source row, rendered its source page, saved
and retried with the same mapping ID, then opened its pending review. Repeat with
`scripts/check_local_candidate_source_ui.cjs`; IDs in
`data/local-runtime/candidate-source-ui-check.json`. Source screenshot:
`/tmp/loupe-neilbyrne-source-selection-ui.png`. Current backend log:
`/tmp/loupe-neilbyrne-source-ui-backend.out`; frontend55174/backend58002.

The read-only real-PDF contract check (`scripts/check_real_pdf_candidate_sources.py`)
passed all 153 extracted tables/7,529 source rows across the two supplied PDFs.
These are not transaction counts. All cells were bound with unknown meanings in
memory only; no real evidence was persisted, admitted or sent to AI. Aggregate local
results: `data/local-runtime/pdf-inspection/candidate-sources.json`.

**Next:** account setup for candidate resolution, then atomic materialization of
resolved candidates with conservative classification/revalidation and cross-revision
source-row duplicate protection. Extraction initiation/automatic nomination remain
separate work: this UI requires stored text and geometry from the same extraction.
Earlier next-step/UI-missing notes below are historical checkpoints.

### User-supplied real PDF checks — 7 September 2026

Neil supplied two redacted PDFs in `data/loupe-test-pdfs` for local testing.
Read-only extraction with the actual `read_tables` adapter completed all 164 pages
without exceptions: 56/56 pages with text/table candidates in the first document,
97/108 in the second. All 11 textless pages in the second render entirely white
at native scale (pixel check), not missed scanned transaction pages. Sample pages
were visually inspected. The adapter also emits text-alignment tables for letters,
application forms and disclosures: a located table is not a transaction.

Local-only per-page results/hashes: `data/local-runtime/pdf-inspection/inspection.json`.
Real PDFs, rendered pages and extracted content must stay out of commits. No external
AI calls, application ingestion or ledger writes were made with these files. This
is extraction smoke coverage, not transaction accuracy or complete import acceptance.
Use these real formats for the next source-row selection/mapping workflow and verify
transaction/date/amount meaning against the actual page. The user's folder is inside
the project, not ~/data. Existing synthetic review tests remain independently repeatable.

### Saved-candidate review UI completed — 7 September 2026 overnight

`ee6edb4` adds case-scoped bounded mapping lists/account search and a case:edit
creation API that reuses the source-bound atomic writer. Financial → Ledger → PDF
readings opens saved batches/rows, preserves original text and exposes review,
rejection, reopening, exact amount assessment and authenticated source highlights.
All three date roles remain separate. A reason, known compatible account, explicit
currency/direction and exact amount are required to resolve. Uncertain writes block
further submissions until explicit reload; stale responses cannot silently replace
the displayed review. Resolution still does not create/admit a ledger transaction.

**Verified:** 3,657 financial tests (zero skips), 905 frontend unit tests, 11 Chromium
tests, TypeScript and ESLint pass. Six backend tests and ten UI tests added; export
checks and focused UI/TypeScript/lint rerun after final accessible-label fixes.
Authenticated creation retry returns the original IDs. Real Chromium through the
local application reopened/resolved the synthetic candidate, retained five events,
showed the source image and original 1234.00 GBP, and saved reviewed 12.34 GBP.
Screenshot `/tmp/loupe-neilbyrne-candidate-review-ui.png`; repeat with
`scripts/check_local_candidate_ui.cjs` after the review fixture script. Fixture IDs
remain in `data/local-runtime/candidate-review-check.json`. Backend currently runs
via local_app.py (log `/tmp/loupe-neilbyrne-candidate-ui-backend.out`), frontend55174.

**Next:** source mapping creation workflow (stored table inspection and deliberate
column/row nomination) so users can populate these reviews without fixture scripts;
then account setup and atomic candidate materialization/revalidation. Automatic PDF
extraction/OCR and the remainder of the ten-feature checklist are not complete.

### Candidate review history and APIs completed — 7 September 2026 overnight

`c4ae63e` adds migration `20260907_candidate_reviews`, an append-only review
model/service, and GET/POST `/api/financial/candidates/{candidate_id}/review`.
Reads require case:view; writes require case:edit and the authenticated actor.
Every decision has a reason, original digest, sequence and previous-revision link.
State derives from history; original candidate/mapping rows stay unchanged.
Resolution, rejection, reopening and revised resolutions append events.

A resolved reading requires a supported currency, nonnegative decimal-string
minor units within BIGINT, explicit direction, at least one identified ISO
booking/value/transaction date, description and a same-case compatible account.
No amount floats, inferred dates or manually assigned proof class/admission.
Source/text/geometry and candidate locks precede rebinding and stale-review checks;
account compatibility is checked under a lock. Resolution does not admit a row.
Mapping/assessment reads now include current review state/revision. History remains
readable after source drift, while new decisions are refused. PostgreSQL and ORM
UPDATE guards preserve history; case/file deletion still cascades.

**Verified:** 3,651 financial tests, zero skips; 895 frontend unit tests, 11
Chromium tests, TypeScript and ESLint pass. Added 20 review/service/route tests.
The exhaustive adjudication route whitelist was extended to acknowledge the new
POST rather than weakening the permission check. Logs:
`/tmp/loupe-neilbyrne-review-{financial,unit,browser,eslint,migration,postgres}.out`.

Migration applied only to isolated loupe_local. New repeatable
`scripts/check_local_candidate_reviews.py` creates a synthetic PDF fixture,
observes two PostgreSQL review lock waiters, gets exactly one 200/one 409, then
reopens and resolves via authenticated HTTP. Three history entries and original
text survive; PostgreSQL rejects history UPDATE. Latest fixture case
`35ed8c59-9115-451d-bc7d-037ffacdb069`, candidate
`4968063f-2818-4f46-b5e1-97ac4cc60d74`, account
`03aa6b56-b4d0-45dd-bcca-ffd0e42f4bd4`; full IDs in
`data/local-runtime/candidate-review-check.json`. Synthetic reviewed 12.34 differs
from the digital 1234.00 original intentionally to test audit preservation.

Backend restarted for these routes; exec session 7860, log
`/tmp/loupe-neilbyrne-review-backend-runtime.out`. **Next: candidate listing and
creation endpoints, account choices and the candidate review UI**, then atomic
ledger materialization. Materialization must pin the reviewed revision and prevent
later candidate changes from bypassing the existing ledger correction path.
Feature 2 remains partial until its user workflow is connected. Schedule active
through 06:00 Dublin with final 15 minutes for handoff. No real data or AI calls;
tracked implementation committed and no push.

### Saved-candidate assessment connected — 7 September 2026 overnight

`8d6425a` adds `candidate_assessment.py`: saved originals are checked against a
fresh source binding before assessing amount/debit/credit/balance proposals.
Raw text and origin come from the original cells; uncertain alternatives remain,
unknown columns are listed without guessing, and money integers serialize as
strings. Currency is explicit caller context. Every candidate remains pending;
there is no review decision or ledger write. An assessment revision hashes the
exact displayed result for future review, but does not authorize a write.

Case:view routes: GET `/api/financial/candidate-mappings/{mapping_id}` and POST
`/api/financial/candidates/{candidate_id}/amount-assessment`, body currency only.
`current_candidate_original` verifies stored hashes, source binding and full
snapshot equality; a later writer must hold locks through verification/commit.
No source-state cache may substitute for that check. Unexpected route errors are
sanitized, and wrong-case/stale-source responses remain distinct.

**Verified:** 3,631 financial tests (zero skips), 895 frontend unit tests, 11
Chromium tests, TypeScript and ESLint pass. New assessment coverage adds 19 tests
including source drift, canonical/grid originals, uncertain alternatives, large
exact values, zero/sign, case scope, unclassified columns, currency revision and
rehashed corrupted originals. Logs `/tmp/loupe-neilbyrne-assessment-*.out`.

The isolated backend was restarted (verified old PID 84533) to load new routes.
Current backend exec session 83073, log
`/tmp/loupe-neilbyrne-candidate-backend-runtime.out`. Updated
`scripts/check_local_candidates.py` passed authenticated HTTP mapping read and
assessment, source rectangle, forbidden raw-text override and invalid currency.
It also reruns the PostgreSQL contention/immutable-trigger checks. Latest fixture:
case `9b633df0-1d6c-453b-ad76-5a140a1f9601`, mapping
`411e6b12-d386-4043-88ac-26393e694cf9`; durable IDs in
`data/local-runtime/candidate-check.json`, log
`/tmp/loupe-neilbyrne-candidate-assessment-http.out`. No real evidence or AI calls.

**Next:** append-only candidate review records and resolved/rejected/pending
transitions with exact complete reading validation and stale-review protection.
Then creation/review endpoints and UI, followed by atomic materialization. Keep
feature 2 partial until this workflow is usable end to end. Tracked implementation
committed; schedule remains active to 06:00 Dublin with final 15-minute handoff.

### Pending PDF originals persisted — 7 September 2026 overnight

`826caee` adds mapping/candidate original tables, migration
`20260907_candidate_originals`, and `candidate_store.py`. A dedicated-session
writer locks the case-scoped evidence file and existing text/geometry rows,
rebinds either typed mapping, and atomically commits the complete originals.
Same-mapping retries return original IDs/actor; new mapping revisions append.
Readers verify counts and snapshot digests. PostgreSQL UPDATE triggers protect
both original tables; an ORM guard covers ordinary SQLite ORM writes. Case/file
deletion still cascades. No money or mutable review state is stored: candidates
remain pending and outside totals. No HTTP/UI has been added yet.

**Verified:** 3,612 financial tests (zero skips), 895 frontend unit tests, 11
Chromium tests, TypeScript and ESLint pass. New unit tests cover 16 storage cases,
including persisted reload, stale/cross-case refusal, failure rollback, original
immutability, returned-payload isolation, and both source contracts. Logs are
`/tmp/loupe-neilbyrne-candidate-{financial,unit,browser,eslint}.out`.

The migration was applied only to isolated loupe_local PostgreSQL. Repeatable
`scripts/check_local_candidates.py` generates a synthetic PDF and actual table
geometry, then observes two PostgreSQL lock waiters before releasing competing
saves. Result: one mapping, two pending candidates, zero ledger transactions.
Direct SQL UPDATE of both originals is refused. Fixture case
`77196023-eda3-48cb-b6c9-dc7bdb126e0f`, mapping
`6e30ec2f-cf76-4784-8704-075e69fcaae9`; IDs also saved in
`data/local-runtime/candidate-check.json`. Migration and live logs:
`/tmp/loupe-neilbyrne-candidate-{migration,postgres}.out`. The migration refuses
downgrade while originals exist. No HTTP or full workflow acceptance is claimed.

**Next:** append-only candidate review records with pending/resolved/rejected
states, review revisions and reasons; integrate assessment of original amounts.
Then authorized endpoints/UI and atomic ledger materialization. Cross-revision
or overlapping-mapping transaction deduplication is still required at
materialization; snapshot retry safety must not be mistaken for that guarantee.
Keep all ten checklist features visible and partial until their whole workflows
are connected. Scheduled work remains authorized until 06:00 Dublin; last
15 minutes reserved for handoff. Tracked implementation is committed; no push,
no real data changes, no external AI calls.

### Stored PDF grid binding completed — 7 September 2026 overnight

`5ab6931` adds `pdf_geometry_candidates.py`, an alternate immutable pending mapping
contract keyed to stored page/table index/row/column. It handles cell text without
inventing canonical offsets when PDF text is column-major. A single case-scoped
query snapshots file/text/geometry; the source revision includes geometry and
provenance. A matching non-null extraction job is required for text and geometry.
Historical unbound geometry is refused; the canonical text contract remains
available. Neither adapter rereads file bytes or writes/adopts a transaction.

The binder preserves exact stored text, proposed column meanings, table discovery
method and valid locators. It rejects repeated grid coordinates, page/dimension
mismatches, cells outside table bounds, overlapping rectangles, changed metadata,
changed geometry and stale provenance. Unlocated cells stay unlocated. The stored
page map determines origin conservatively; invalid/overlapping maps stay unknown.

**Checks:** 3,596 financial tests pass, zero skips; 895 frontend unit tests, 11
Chromium tests, TypeScript and ESLint pass. The new module has 25 tests including a
generated PDF read by the actual table extractor, stored and bound back to distinct
rectangles for repeated amounts. Package export coverage adds one more test.
Logs: `/tmp/loupe-neilbyrne-grid-{financial,unit,browser,eslint,real-pdf}.out`.
Initial browser run hit sandbox EPERM opening loopback; the approved escalated
rerun passed all 11 tests (the earlier no-tests output was not accepted). Initial
fixture used sub-point page dimensions and was corrected to realistic millipoints
so the established 1-point containment tolerance was tested meaningfully.

The retained feature checklist marks this foundation complete under feature 1,
which remains partial. **Next: immutable candidate persistence and review state
outside the integer ledger, then assessment and materialization.** No real evidence
or external AI calls; no push. Tracked implementation committed; unrelated
untracked files untouched. Scheduled continuation remains active every 5 minutes
until 06:00 Dublin, with the final 15 minutes reserved for handoff.

### Authorized scheduled continuation until 6am Dublin — 7 September 2026

Neil explicitly asked to work through the remaining ten-feature list on a schedule
until **2026-09-07 06:00 Europe/Dublin (05:00 UTC)**, and to mark completed work
without removing it. The existing heartbeat `continue-loupe-development` has been
updated through the app tool to ACTIVE every 5 minutes, with this cutoff and the
current next implementation scope. This supersedes the older paused-window notes.

`docs/loupe-development-checklist.md` preserves all ten numbered features, the
remaining subitems, and checked existing foundations. Update it after every tested
segment, keeping completion evidence and distinguishing partial from complete.
Read the clock before starting segments; reserve the final 15 minutes for the
morning handoff and pause the automation before the deadline. At or after the
cutoff, only checkpoint/report/pause; do not start more development.

This scheduling/checklist checkpoint changes no application code. The last passing
financial baseline remains 3,570 tests. Immediate next work is still verified
stored table/cell geometry for pending PDF mappings. No automatic promise that all
ten features will fit inside this window is made.

### PDF candidate text contract — 7 September 2026

Neil asked whether much development remained, received an explicit account of the
unfinished ingestion/validation/projection work, and said **“please continue.”**
This authorizes active development; yesterday's heartbeat remains paused.

`5d7279d` adds `services/financial/pdf_candidates.py`: immutable typed proposed
columns, ordered rows, exact Unicode text spans and optional source-backed context.
The read-only binder joins evidence file/text within the authorized case, verifies
recorded file metadata and recomputed text digest, and checks every cell/header/
context span. It returns pending candidates only, with stored-origin/page metadata.
No migration, HTTP endpoint, candidate writer, normalized amount or admission is
introduced. Missing context and unknown column meanings remain representable.

Source revisions cover identity, recorded file/text digests, source locations and
extraction job. Mapping revisions cover the entire proposal. Identical amounts at
different offsets have distinct snapshot keys. Snapshot keys are not sufficient
for future cross-revision/cross-table ingestion deduplication. The eventual writer
must rebind within its transaction and enforce separate materialization identity.

The conservative stored-page provenance logic was extracted from amount assessment
into `source_span_origin` and reused without changing assessment behavior. Unknown,
malformed and overlapping source maps cannot acquire digital certainty. Callers
cannot add origin, settled amount, status or proof-class fields to proposals.

**Scope limitation:** this binds nominated canonical-text regions, not verified
stored table geometry. No rectangles are asserted or file bytes reread. The v1
contract expects nonoverlapping rows in canonical text order; irregular/column-major
source needs an explicit geometry adapter, not fabricated canonical offsets.

**Validation:** 3,570 financial tests passed, zero skips, in the persistent backend
venv, including 21 new contract tests. Command from backend:
`../data/local-runtime/backend-venv/bin/python -m unittest discover -s tests -p
 'test_financial_*.py' -t .` (one line); log
`/tmp/loupe-neilbyrne-pdf-contract-financial.out`. Earlier focused run passed 37
tests before three additional edge tests were added. New checks include cross-case
refusal, file/text/provenance/job drift, repeated values, malformed grids, exact
Unicode offsets, zero/sign/currency/unreadable raw text, immutable originals and
revalidation of copied models. Existing optional-library warnings are non-failing.
No frontend change; frontend gates and app health were not rerun this segment.
`git diff --check` passes. No real evidence was read or changed. Nothing pushed.

**Next:** bind the contract to verified stored table/cell geometry, then immutable
candidate storage and review transitions outside the integer ledger. Amount
assessment integration and atomic materialization remain after those boundaries.
See `docs/loupe-pdf-ledger-bridge.md` for the updated contract and limitations.
Tracked implementation is committed; unrelated untracked files remain untouched.

### Historical end-of-window availability checkpoint (6 September)


Progress report committed as `bdedcda`: **docs/loupe-progress-2026-09-06.md** is the
short briefing for Neil. Detailed resumable state remains here. Last implementation
is still `092d32e`; subsequent commits record handoffs/reports.

At 18:55 UTC (19:55 Dublin), frontend 55174, backend /health on 58002 and engine
/health on 58003 all returned HTTP 200. Tracked working tree was clean and diff
checks passed. Latest test logs reconfirmed 3,549 financial tests with zero skips,
895 frontend unit and 11 Chromium passing. These suites were not redundantly
rerun for this documentation-only checkpoint. No new feature work was started
in the final five minutes.

Heartbeat **continue-loupe-development is PAUSED**, updated through the app tool
at 19:00 UTC / 20:00 Dublin and verified in its saved configuration. The authorized
unattended window has ended; no further automatic segments should run. Local app
processes remain running for Neil's testing. Resume development when Neil asks.
Next implementation remains the typed source mapping/candidate contract described
in docs/loupe-pdf-ledger-bridge.md, not automatic admission from graph numbers.

### Historical correction sources verified live; next bridge designed

`092d32e` extends `scripts/check_local_ledger_source.py` with optional
`--correct-held-out`. It creates a fresh generated-PDF fixture, supplies its
explicit statement_document shape, previews/records an intentionally synthetic
20.00 → 21.00 GBP correction, and checks that the original is superseded while
the replacement stays quarantined. Both source citations retain the same file
and rectangle. Default invocation still leaves the original two-row fixture.
The script changes only its freshly created isolated synthetic case.

Live case **defe8353-1427-48ff-a9fe-becd9e735e14**, source file
0667f9ac-6230-4a6d-9c7d-f5428aa478fb. Original held-out row
fb7e190d-f589-419a-977c-27a23ce2129b; replacement
7cdc441f-277e-4c34-90e9-21b2c871a779, reference TX-QTQV-4EB4-PQ8G.
The Decisions screen displayed original 20.00 and replacement 21.00. Both source
buttons fetched their own row IDs and displayed the correct original printed
20.00 rectangle. The original dialog states it has been replaced. Screenshot
inspected. A computed p2→p3 event also appears because the fixture's held-out row
leaves the statement unbalanced; no reviewer-assigned class was used.

Validation: synthetic HTTP preview/write/history-source checks pass; live browser
checks pass. Logs `/tmp/loupe-neilbyrne-history-source-{http,live}.out`; browser
harness `/tmp/loupe-neilbyrne-history-source-live.cjs`; screenshots
`/tmp/loupe-neilbyrne-View-{original,replacement}-source.png`. Python 3.10 syntax
and diff checks pass. Production app unchanged; baselines remain 3,549 financial
(zero skips), 895 unit and 11 Chromium. No real data or external AI calls.

New **docs/loupe-pdf-ledger-bridge.md** is a concrete proposal for the missing
PDF-to-relational ingestion bridge, clearly marked unimplemented. It separates
source-bound mapping, unresolved candidate storage, source-grounded assessment,
atomic complete-draft materialization and later graph projection. The next code
unit is the typed mapping/candidate contract and source-binding tests. Do not
materialize unresolved readings by selecting a proposal to fit the integer schema.

Unattended window is nearing its 20:00 Dublin / 19:00 UTC cutoff. Keep the next
segment bounded and leave a clean checkpoint. At cutoff, pause the heartbeat and
summarize completed work and the remaining bridge, revalidation and projection.
Backend session 72136 remains running. Engine/worker still need the earlier
text_origin restart before any new extraction test. All unrelated files preserved.

### Source rendering failures are explicit

`1aea7f2` fixes a misleading source-view failure path. TransactionSourceHighlight
now surfaces failed authenticated page requests instead of silently falling back
to text that could claim a page was shown. SourceHighlight handles browser image
decode failures, removes the page/highlight and reports the failure. A different
image URL can recover. Page-only citations with no supplied image explicitly say
that no rendering is available. Neither path invents a rectangle or drops the
stored page number. Close/reopen retries through the existing authenticated fetch.
The source dialog's original-file action remains independent and available.

Validation: **895 unit tests in 92 files, 11 Chromium tests in 9 files pass**;
TypeScript, ESLint and diff checks pass. Four new tests cover both image kinds'
decode failure/recovery, no-image wording and page-only HTTP failure. Updated the
existing rectangle-fetch failure expectation and supplied a valid PNG in the
Chromium source test, since invalid fake bytes now correctly trigger an error.
Logs `/tmp/loupe-neilbyrne-source-failure-{unit,browser}.out`.

Live local browser check intercepted only the generated fixture's page-image
request with a synthetic 503. Verified an explicit page-1 failure, no highlight,
and enabled Open source file action. No server/evidence mutation. Harness/output:
`/tmp/loupe-neilbyrne-source-failure-live.{cjs,out}`. Production backend unchanged;
baseline remains 3,549 with zero skips. Real local app continues running.

Next: live correction-history source navigation with a real synthetic correction,
then preserve a concrete design for the absent PDF-to-relational draft bridge.
Do not claim automatic suspect-amount ingestion or graph projection is done.
Current backend session 72136 remains current; engine/worker still need their
prior text_origin restart before new extraction testing. The unattended window
ends at 20:00 Dublin / 19:00 UTC; finish a safe checkpoint and pause heartbeat then.

### Correction history exposes both source citations

`52fa438` threads the decision's case ID into CorrectionHistory and adds View
original source / View replacement source. Each opens LedgerSourceDialog with
its own snapshot row ID; it does not substitute the currently admitted version
for the original. The historical exact amounts remain unchanged. The dialog is
hidden when the case changes; absent case context or unreadable snapshots offer
no navigation. The existing source endpoint supports superseded rows and the
shared dialog reports their current historical status separately from the event.

Validation: **891 unit tests in 91 files, 11 Chromium tests in 9 files pass**;
TypeScript, ESLint and diff checks pass. Three new tests cover each version's ID,
exact large amounts, original-case isolation and unavailable snapshots. Logs:
`/tmp/loupe-neilbyrne-history-source-{unit,browser}.out`. Backend unchanged; baseline
3,549 with zero skips. No real data changes. Live historical-source navigation
has not yet been exercised; the underlying current/held-out PDF viewer path was
verified in preceding segments.

Ingestion seam audit: production search for record_transactions calls under
backend/services and evidence-engine/app returns only native_ingest.py:240.
NativeRow at native.py:528 already contains RowReading, locator, account/date and
reversal fields; _RowCollector constructs it after normalized fields are parsed.
The PDF extraction path builds financial graph entity properties in
extract_entities.py and property_canonicalization.py, not TransactionDraft objects.
There is no existing PDF-cell-to-relational-writer handoff to attach automatic
suspect flags to. A source amount selected in the UI is grounded text, not a
complete transaction draft. Do not wire it into ledger admission by inventing
account, date, direction or column semantics. That larger bridge needs an explicit
implementation design retaining raw amount text/origin and row identity.

Next bounded work: live correction-history source check using a generated-PDF
fixture with a real correction, or finish source-view failure reporting. Then
prepare the PDF-to-relational draft design from the actual extraction contracts.
Current backend session 72136 is still valid. Engine/worker restart for prior
text_origin code remains pending. Unattended cutoff stays 20:00 Dublin (19:00 UTC).

### Amount assessment is reachable from a ledger citation

`8a3ab2f` adds Assess an amount in source text inside LedgerSourceDialog, reusing
the same SourceAmountPanel already tested in evidence search. It passes the
resolved evidence-file ID and original case, never derives raw text from the
ledger amount, and requires an explicit text selection and currency. Closing
assessment leaves source navigation available. Missing canonical text returns its
clear error while Open source file stays usable. No correction or admission is
performed; the separate correction preview/record flow remains authoritative.

Extended `scripts/check_local_ledger_source.py` to extract the actual generated
PDF's text into a canonical record, with digital provenance explicitly assigned
for this generated fixture, and verify an exact read-only 400.00 GBP assessment.
New fixture case **5adbd65c-2541-4b8b-88b7-b9358896b944**, file
7364782f-1eae-425a-bbf3-90f4c1b77712. Admitted row
67f55237-fed8-45f6-8b8e-dfbdaa807d7f; held-out row
54e2a8f2-72a1-415c-a6e6-9ee40a6e393f. Latest IDs are in
`data/local-runtime/ledger-source-check.json`. Prior synthetic cases remain intact.

The real browser followed Ledger → View source → Assess an amount in source text,
selected 400.00 and entered GBP. It returned Digital text / 400.00 GBP. Closing
assessment/source returned to the unchanged admitted 400.00 GBP ledger row.
Screenshot inspected. Harness `/tmp/loupe-neilbyrne-ledger-assess-live.cjs`, output
same basename .out, screenshot same basename .png. HTTP integration also passed.

Validation: **888 unit tests in 90 files, 11 Chromium tests in 9 files pass**;
TypeScript, ESLint, Python 3.10 syntax and diff checks pass. Two new integration
unit tests cover resolved file/text selection and unavailable canonical text.
Logs: `/tmp/loupe-neilbyrne-ledger-assess-{focused,full,browser,http}.out`.
Production backend unchanged; baseline stays 3,549 with zero skips. No real data
or external AI calls. Existing backend session 72136 remains current.

Next: move from the now-tested manual source review/correction interface toward
remaining ingestion integration. Before wiring automatic suspect flags, establish
where extracted table cells become relational transaction drafts, retaining raw
amount text, origin and row/column identity; do not invent them from normalized
ledger integers. If that seam requires a larger design, implement another bounded
agreed-plan prerequisite and record the dependency. Engine/worker still need the
prior text_origin restart before a new extraction run. Stop starting segments at
20:00 Dublin (19:00 UTC) and pause the heartbeat after a safe checkpoint.

### Live ledger PDF source navigation verified

`a5857b3` adds `scripts/check_local_ledger_source.py`, a generated-PDF integration
fixture and a Chromium regression for the citation/highlight/file dialog chain.
The real local backend lacked PyMuPDF (only the engine installed it), so page
rendering would return 503. Added PyMuPDF>=1.25,<2 to backend requirements, installed
1.28.2 in the isolated backend venv, and updated the renderer loader comment.
Backend pip check passes. No new PDF system dependency was needed.

The script targets only the isolated database/API, creates a clearly synthetic
PDF/case with one admitted 400.00 GBP row and one held-out 20.00 GBP row, records
explicit rectangles, checks both citation responses, the real rendered PNG and
original PDF digest. It assigns synthetic positions/statuses, not extraction or
admission outcomes. Its ingestion attempt remains open, accurately disclosed in
the UI. The fixture is for navigation, not balance/reconciliation acceptance.

Case **38f31809-eaed-44cc-a537-92e86f579d16**, file
223c8d83-b26d-4938-99e3-5105dd97c199. Admitted row
81aa78c2-a3f5-4b9d-ba04-ea0d6cac7a19; held-out row
82524359-fb99-4178-9e8c-a2e0fbe2ce08. IDs persist in
`data/local-runtime/ledger-source-check.json`. The live browser verified both
View source actions: 1200×1553 page image, separate correct highlights on the
400.00 and 20.00 printed lines, original PDF opened at page 1, Escape returning
to the source dialog and then the ledger. Screenshot visually inspected.
Live harness `/tmp/loupe-neilbyrne-ledger-source-live.cjs`, log same basename .out;
screenshots `/tmp/loupe-neilbyrne-ledger-{Ledger,Held-out}.png`.

Validation: **all 3,549 financial tests pass, now with zero skips**: installing the
renderer enabled the 12 previously skipped real-library checks. **11 Chromium
tests in 9 files pass**; TypeScript, ESLint, Python 3.10 syntax and diff checks pass.
Unit baseline remains 886 (no production frontend code changed). Chromium test
initially compared computed pixel styles against percentages; corrected it to
assert stored relative styles, and the rerun passed. Logs:
`/tmp/loupe-neilbyrne-ledger-source-{http,pdf-browser,pdf-backend}.out`.
Backend restarted with citation route; exec session 72136, runtime log
`/tmp/loupe-neilbyrne-ledger-source-backend-runtime.out`. No real evidence changed.

Next: source navigation is connected for stored relational locators. Revisit the
remaining item 10 source-assessment-to-review link; avoid presenting the read-only
assessment as automatic transaction identification. Native/running-balance
revalidation and graph projection remain outstanding. The engine/worker still
need restarting for prior text_origin changes before a new extraction check.

### Source navigation connected on Ledger and Held out

`65be755` adds View source through CorrectableLedger, both ledger panels and
LedgerTable. Selection captures the original case and is hidden on a case switch.
LedgerSourceDialog fetches the new citation endpoint, validates case/transaction,
recorded digest agreement and locator-state coherence, then passes the resolved
**evidence-file ID**, never the relational document ID, to the existing source
highlight renderer and DocumentViewer. It uses the stored page when available.
No guessed page or highlight is supplied for missing/invalid locations.

The dialog explains missing/invalid locations and historical superseded readings.
Its Open source file action opens the authenticated original file viewer; PDFs
also use the existing page image/highlight path. Non-PDF sources do not request
the PDF rendering endpoint. Server errors, digest refusal or inconsistent metadata
block navigation. A failed background citation refetch returns to the error dialog.
No correction/admission/graph write occurs.

Validation: **886 frontend unit tests in 90 files, 10 Chromium tests in 8 files
pass; TypeScript and ESLint pass.** Nine new dialog tests cover resolved evidence
identity, stored page, historical labels, missing/invalid locator disclosure,
wrong-case/row, digest and contradictory locator refusal. Existing Chromium gates
passed; this new dialog still needs its own real PDF integration smoke test.
Logs: `/tmp/loupe-neilbyrne-ledger-source-ui-{focused,full,browser}.out`.
Backend unchanged; financial baseline remains 3,549 (12 skipped).

Next: restart isolated backend for the citation route, build a labelled synthetic
relational fixture tied to an actual generated PDF with a stored page rectangle,
and verify source navigation/highlight in the running app on Ledger and Held out.
Existing correction fixtures have synthetic absent source files; do not pretend
those files exist. Also add a dedicated Chromium source-navigation regression.
Automatic suspect reading ingestion/admission, native/running-balance revalidation
and graph projection remain outstanding; this segment does not complete them.

### Relational ledger citation endpoint

`c7d3a88` adds authenticated case:view GET
`/api/financial/ledger/{transaction_id}/source?case_id=...` and exported
`ledger_source` / `LedgerSourceError`. A single query joins transaction, financial
source document and evidence file, requiring the same case on all three. It returns
the actual evidence-file ID, original filename, row reference/status, supersession
link and validated stored locator. The internal disk path is never returned.

Recorded evidence SHA-256 must match the valid ingestion SHA-256, otherwise 409;
wrong-case/missing links return 404. `file_bytes_verified:false` explicitly limits
this to recorded metadata comparison. No source bytes are reread. Missing locators
are labelled missing; malformed ones, boolean pages and pages beyond stored page
count are labelled invalid. No highlight is inferred. Valid rectangle coordinates
retain millipoints/pdf_displayed space; page-only, not-positional and unlocated
semantics are preserved. Historical/superseded rows can still cite their originals.

Validation: **3,549 financial tests pass, 12 skipped**. Eight new tests cover identity,
wrong-case ownership, digest drift and invalid digests, historical page references,
rectangle preservation, malformed/missing/out-of-range locations and router refusal.
The first full run caught the required package export omission; fixed exports and
reran the full suite successfully. Python 3.10 syntax and diff checks pass.
Log: `/tmp/loupe-neilbyrne-ledger-source-full.out`. No frontend changes; prior
baselines remain 877 unit / 10 Chromium. No database writes or live endpoint test.
The isolated backend needs restarting to load this new route.

Plan decision: item 10 requires source citations and item 11 explicitly supplies
relational locator navigation. This is that prerequisite, not a claim that automatic
amount/column detection or native/running-balance revalidation is done. Existing
`attach_transaction_locators` interprets graph source_document_id as evidence-file
ID; relational source_document_id identifies a different table and cannot be passed
to it unchanged. Relational rows already store locators in provenance. The new
endpoint resolves their evidence identity first and retains those locators.

Next: add a source action on current and held-out ledger rows using this endpoint
and the existing evidence viewer/highlight components. Validate missing/malformed
locations and digest refusal in the UI, then use a synthetic relational fixture
with a real generated source file for live navigation. Do not guess a source page
from row_index. Graph projection remains a separate later item.

### Source amount assessment verified in the running local app

`1f58ab0` adds repeatable `scripts/check_local_source_amounts.py` and a dedicated
Chromium regression. The script has hard-coded isolated local database/API targets,
creates only labelled synthetic cases/files, checks all three origins, exact decimal
strings, wrong-case 404 and stale/mismatched-source 409, and verifies no transaction
or adjudication rows were created. Canonical source content remains unchanged.
Run it with the backend venv and PYTHON_DOTENV_DISABLED=1, as documented in
`docs/local-application.md`. This is a provenance fixture, not an extraction test.

Live fixture case: **37009e6c-7617-48dd-aef6-9ce1ffab0527**. Files: digital
8cfb58aa-4746-4738-b7db-e85a7c789fba; recognized
551da3d7-4459-4e0f-9e95-aecd4f5e3cf7; unknown
90945d27-a7cd-4dcb-8e87-98b93c4855b0. Metadata also persists in
`data/local-runtime/source-amount-check.json`. In Evidence, select Text in case,
search Synthetic amount review, open the assessment panel, select 1234, enter USD.
The real browser/HTTP round trip succeeded for all three: digital 1234.00 USD;
recognized and unknown both 12.34 and 1234.00 as possible readings. Inspected the
rendered panel screenshot. No real evidence/database changes.

Restarted only the isolated backend on 58002; it now loads both source endpoints.
Current backend exec session 67264, log `/tmp/loupe-neilbyrne-source-backend-runtime.out`.
The engine/worker still need their prior text_origin code restart before extraction
validation. The browser smoke script is `/tmp/loupe-neilbyrne-source-live.cjs`,
successful output `/tmp/loupe-neilbyrne-source-live-retry.out`, screenshots
`/tmp/loupe-neilbyrne-source-live-{0,1,2}.png`. Initial script dispatched select
alone, which React's selection plugin does not observe; dispatching mouseup after
setSelectionRange correctly exercised it. This was a smoke harness issue.

Validation: **10 Chromium tests in 8 files pass**, including canonical CRLF/emoji
selection in a later 12,000-character window, exact proposals and resetting on
navigation. TypeScript, ESLint, Python 3.10 syntax and diff checks pass. HTTP log:
`/tmp/loupe-neilbyrne-source-http.out`; browser log:
`/tmp/loupe-neilbyrne-source-browser-native.out`. Production code unchanged;
prior full-suite baselines remain 3,541 financial (12 skipped), 877 frontend unit.

Next: inspect the agreed item 10 revalidation/ingestion wiring and choose its next
bounded integration. Explicit source assessment and transaction correction now have
separate tested interfaces; automatic amount/column identification and admission
of unresolved source readings are still not wired. Preserve that distinction.

### Source amount review is connected to evidence text search

`6953895` adds “Assess an amount in source text” to each document result in
Evidence text search. The panel reads canonical extracted text in bounded windows,
lets the user select up to 128 code points and supply an ISO currency, then calls
the read-only assessment endpoint. It displays stored origin, explanations and
exact readings/proposals; it never writes corrections or admits amounts.

The new authenticated case:view GET `/api/financial/source-files/{id}/text`
returns content, digest, Unicode code-point offsets and pagination metadata.
It reuses the case-scoped source query and recomputed digest check from assessment.
Windows default to 12,000 code points, maximum 20,000. Wrong-case sources return
404; stale or inconsistent source digests return 409. The UI validates response
identity, offsets and selected text before displaying results. Selection conversion
accounts for textarea CRLF normalization and UTF-16 positions after emoji; raw
canonical text is preserved. Currency or selection changes clear the prior result.

Validation: **3,541 financial tests pass, 12 skipped; 877 frontend unit tests in
89 files and 9 Chromium tests in 7 files pass. TypeScript and ESLint pass.**
New unit tests cover exact selection conversion, the full panel request/result
with currency reset, and wrong-case response refusal. New backend tests cover
bounded windows and scope/size/range refusal. Existing Chromium checks passed;
the new panel has not yet had its own Chromium or live HTTP smoke test. Logs:
`/tmp/loupe-neilbyrne-source-ui-{backend,full,browser}.out` and
`/tmp/loupe-neilbyrne-source-amount-ui-tests.out`.

Next: restart the isolated backend to load both source endpoints, and validate the
panel with a synthetic canonical source through HTTP and Chromium. The existing
correction fixture does not have an EvidenceFile/canonical-text record, so prepare
a separate synthetic fixture in the isolated local database. Engine/worker still
need restarting for the prior text_origin extraction change. Automatic amount and
column identification, review admission, broader revalidation and projection remain
outstanding. No real evidence/database writes occurred in this segment.

### Source-grounded amount assessment endpoint

`b0086d3` adds authenticated case:view POST
`/api/financial/source-files/{evidence_file_id}/amount-assessment?case_id=...`.
It is read-only. Body: start_char/end_char (Unicode code points), expected_text
(1–128 characters), content_sha256 and uppercase currency. Extra fields are
forbidden; the caller cannot supply origin, a proof class or admission.

One case-scoped query loads canonical text and provenance. The service recomputes
the text digest, refuses a stale/corrupt digest or mismatched offsets with 409,
and returns 404 for missing or wrong-case source text. Only one unambiguous covering
page can establish stored text_origin; missing, malformed, overlapping or historical
provenance stays unknown. It calls the existing suspect_amounts.read_amount on the
actual substring. All returned minor-unit figures/proposals are decimal strings.
Currency is explicitly caller-supplied context. The response says applied:false
and limits the assessment to selected text; it does not identify a transaction or
admit any figure to totals. No correction or graph write occurs.

Validation: **3,539 financial tests pass, 12 skipped**, including ten focused
service/router tests plus package export coverage. Real SQLite case isolation,
Unicode offsets (including a preceding emoji), stale/mismatched source refusal,
unknown/overlapping provenance and exact proposal strings are tested. Python 3.10
syntax and diff checks pass. Logs: `/tmp/loupe-neilbyrne-amount-assessment-{tests,full}.out`.
No frontend change; baseline remains 874 unit/9 Chromium tests. No real evidence
or database writes. Backend needs restarting before a live endpoint test.

Next: connect this read-only assessment to an explicit source-text selection in
the UI. Inspect the existing canonical-text read API first; ensure it exposes
the digest and uses the same Unicode code-point offsets. Never derive the raw
reading from a formatted ledger integer. Automatic amount/column identification,
review admission of unresolved source readings and projection remain outstanding.

### PDF text-origin provenance now survives extraction

`f42c8e5` connects the existing financial `page_text_origin` measurement to the
engine's PDF extraction. An embedded text layer is no longer implicitly treated
as digital: full-page raster overlays are labeled recognised_glyphs even when the
engine correctly keeps their usable existing text. Fresh successful Tesseract
output is recognised_glyphs; unavailable reader or failed measurement is unknown.
This is the existing conservative page-level heuristic, not a per-cell certainty
claim. No amount or column is inferred, and extracted content remains unchanged.

`text_origin` travels with each page span and is copied to canonical source_locations
in the existing evidence text storage path. No schema change or backfill. Existing
stored texts without this field must be treated as unknown. The shared backend
reader is loaded lazily like table geometry; standalone engine deployments without
it still start and explicitly record unknown origin.

Validation: **45 PDF extraction/dispatch/geometry tests pass**, including five new
provenance tests and real rotated-page Tesseract checks; **11 canonical-text and
pipeline-state tests pass**. Installed the engine's declared dev dependencies
pytest 8.x and pytest-asyncio <1 into its persistent isolated venv. A pre-existing
table summary test omitted the backend's existing by_table_source field; updated
that expected contract. Logs: `/tmp/loupe-neilbyrne-pdf-origin-{tests,storage}.out`.
Backend financial/frontend code is unchanged; baselines remain 3,528 (12 skipped),
874 unit and 9 Chromium tests. The full engine suite was not run. No real evidence
or database writes. Restart the local engine/worker before testing new extraction
through the app; the running processes still load their previous code.

Next bounded segment: consume stored source text, its page/offset provenance and
text_origin in a source-grounded amount assessment. Identify an explicit amount
span rather than guessing every number is money; missing historical origin remains
unknown. Automatic suspect detection/admission is still not wired. The correction
UI remains complete for current ledger rows, and graph projection is still item 12.

### Correction response consistency and ingestion seam audit

`9c64b15` validates correction-preview verification as a coherent contract:
recordable previews need a proposed class and no refusal reason; class eligibility
must agree with the class, and unresolved reservations cannot accompany automatic
eligibility. Non-recordable previews need a reason and cannot claim a proposed
class or inclusion. Original/proposed magnitudes must be canonical nonnegative
decimal strings within PostgreSQL BIGINT range. Statement deltas remain signed
and unrestricted by a single-row magnitude. These checks validate the server's
claim, never assign a class on behalf of a reviewer.

**874 unit tests in 88 files**, **9 Chromium tests in 7 files**, TypeScript and
ESLint pass. Six new tests cover contradictory responses and malformed magnitudes.
Logs: `/tmp/loupe-neilbyrne-correction-contract-{unit,browser}.out`. Backend is
unchanged; the full 3,528-test baseline was verified in the preceding segment.
No database writes this segment.

Ingestion audit: `native_ingest._transaction_drafts` takes `NativeRow.reading`,
which is already a normalized RowReading, plus its locator; it stores reversal
metadata but no original amount-text/origin pair. `native.py` constructs those
readings from parsed native amount values. `suspect_amounts.read_amount` has no
production caller beyond package export. Passing the integer back as text would
invent evidence and cannot implement item 10. Next: trace the statement/OCR path
in the evidence engine and its original-text provenance, then define the smallest
real connection for suspect readings. Do not claim native control revalidation,
source locators or graph projection are completed; the plan keeps those separate.
The tested correction UI is complete for currently stored rows, while automatic
suspect-amount identification remains unwired.

### Live held-out round trip and Chromium regression verified

The synthetic case `c1da9946-1dfd-413a-a4e9-1828e1c76b72` was exercised through
the running browser: set aside its current 410.00 GBP row with a synthetic reason,
open Held out, preview 400.00 GBP, and record. The replacement is
`TX-44B9-JZ29-DXR4`, remains quarantined with the human-set grounds, and appears
as 400.00 GBP in Held out. The statement difference stayed -400.00 GBP before and
after because the row does not count. The other 20.00 GBP row remains admitted.
No real evidence or database was touched. The live fixture is intentionally left
with one quarantined row for further testing.

Added a repeatable Chromium test for exact amounts beyond JavaScript safe integers,
separate preview/confirmation, repeated-click protection, quarantine disclosure
despite class eligibility, and expanding the original/replacement history.
**9 Chromium tests in 7 files pass**, TypeScript and ESLint pass. Existing unit
baseline remains **868 in 88 files** (no production/unit code changed). The full
backend financial suite was rerun: **3,528 tests, 12 skipped**.
Logs: `/tmp/loupe-neilbyrne-correction-browser-{regression,backend}.out`.

Plan review: item 10 includes suspect-amount detection as well as corrections.
`suspect_amounts.read_amount` requires original amount text plus explicit TextOrigin;
do not apply it to a formatted stored integer or invent OCR provenance. Its module
explicitly leaves column identification to its caller. Next bounded work should
trace the ingestion provenance/raw reading seam and wire suspect readings only
where those inputs are known. Correction revalidation still deliberately withholds
automatic class eligibility for native-control/running-balance reservations.
Item 11 supplies relational source locators; item 12 supplies graph projection.
Do not silently claim either is completed by the correction writer.

### Held-out correction entry connected

`5cd7d94` reuses the correction owner/form for the Held out tab and threads its
action through QuarantinePanel. The panel still fixes its query to quarantined
rows. Correcting a held row does not release it: the preview explicitly says the
replacement remains excluded, even when the proposed document class is eligible.
Confirmation remains mounted if the list refreshes or becomes empty.

The empty quarantine message previously claimed every row counted when none were
quarantined. It now says only that no rows are quarantined and explains that
classification/document status still determine inclusion. Superseded/rejected
rows remain separately excluded.

Validation: **868 unit tests in 88 files**, **8 Chromium tests in 6 files**,
TypeScript and ESLint pass. New integration coverage exercises a held debit's
preview and record request, independent class eligibility, quarantine disclosure,
and confirmation surviving an empty list refresh. Existing backend correction
coverage preserves the quarantine reason on replacement; no backend code changed.
Logs: `/tmp/loupe-neilbyrne-held-correction-{unit,browser}.out`.
No real evidence or database writes in this segment. The synthetic app remains
available. Next: live synthetic held-out round trip, then review the agreed item 10
revalidation scope and implement the next bounded missing piece. Native controls,
running-balance revalidation, source-file navigation and graph synchronization
remain explicitly incomplete. Continue automatically until the 20:00 Dublin cutoff.

### Correction review and reading history connected

`cf89bbb` adds an exact-decimal correction form to each current Ledger row.
Preview and recording are separate actions, with required reason, preserved debit
direction, revision checking, response validation, no automatic write retry and
explicit uncertain-response handling. Editing the proposal discards its preview.
The review shows original citation and amount, proposed amount/direction, statement
difference, document-wide verification consequence, reservations and quarantine.
Unknown source classification withholds confirmation. Recorded corrections show
both citations; Decisions expands the original and replacement reading snapshots.
Proof class remains computed by the backend. No graph writes were added.

All three original-case caches (ledger, decisions and classification) are invalidated
even after a refused or uncertain write. A live browser check caught the missing
classification invalidation; it was fixed and the next synthetic correction verified
the classification counts refreshed immediately alongside both current ledger rows.

Validation: **867 unit tests in 88 files**, **8 Chromium tests in 6 files**,
TypeScript and ESLint pass. The focused eight correction tests passed again after
the cache fix. Logs: `/tmp/loupe-neilbyrne-correction-ui-{unit,browser}.out`.
No backend change this segment; last financial baseline remains 3,528 tests,
12 skipped. The local backend was restarted to load verification previews.

Live browser testing used only synthetic case
`c1da9946-1dfd-413a-a4e9-1828e1c76b72`: 410.00 GBP was corrected back to 400.00
(p3 to p2), history verified, then to 410.00 again (p2 to p3) to confirm refresh.
Current replacement citation is `TX-MQTR-A4PT-J68M`; five stored rows include
historical readings, while two are current. The fixture's ingestion attempt remains
open and its source ID has no real file, so source-file navigation was not tested.

The held-out integration requested after this segment is now complete above.
Continue the agreed wiring plan. The temporary unattended
automation remains active every 15 minutes until the 20:00 Dublin cutoff;
finish a safe checkpoint and pause it then. Neil has left and authorized continued
work without per-segment confirmation. Unrelated untracked files remain untouched.

### Verification consequences now available before confirmation

`b7e1342` supplies `verification` on correction previews: whether recording is
possible, current/proposed class, reservations, class eligibility for default
totals, and document-wide scope. Unknown source shape, malformed reservations or
inconsistent classes produce `can_record: false`, never an invented classification.
All document periods are evaluated freshly, with the proposed amount substituted
only in the affected period; no persisted reconciliation is used as current.

The preview and writer share `correction_verification`. Recording uses the reviewed
reservations and rolls back if its actual reclassification differs from the preview.
Document revisions now include source shape and admissibility reservations, closing
a stale-review gap if those change while the form is open. Quarantine still controls
row inclusion independently of class eligibility; the UI must not say every row
counts merely because the class is eligible.

Full financial suite: **3,528 tests pass, 12 skipped**, Python 3.10 syntax and diff
checks pass. Four new tests cover preview/writer agreement, no preview metadata
writes, source-metadata revision invalidation, unknown source refusal and rollback
on verification disagreement. Log: `/tmp/loupe-neilbyrne-correction-verification-full.out`.
No schema or frontend change. Restart the local backend before UI integration to
load this response field. Next segment is the correction dialog and history display;
the prerequisite verification disclosure is now available. Unattended continuation
is authorized through 20:00 Europe/Dublin today; preserve the tested segment commits.

### Append-only amount correction writer

`e756fbf` adds `correct_transaction` and authenticated case-edit scoped POST
`/api/financial/transactions/{transaction_id}/correction`. It takes exact minor-unit
strings, direction, mandatory reason, and the reviewed document revision. Actor
identity comes from authentication. The preview's document/period/row locks are
held through revision checking, replacement, audit, reconciliation and commit.
Failures roll everything back. Repeated/stale requests cannot append another row.

Original amount and citation remain unchanged. The old row becomes superseded,
points to its replacement, and clears quarantine coherently; the replacement
inherits any existing quarantine and source locator. It has its own derived
content hash/reference and provenance naming the previous row/reference. Historical
occurrences remain occupied, so correcting back to a previously recorded reading
creates another version without overwriting the original citation. The new
`correct_transaction` audit event contains before/after reading snapshots, linkage,
original disposition, authenticated actor/reason and reviewed revision.

Every linked statement period is reconciled from the new admitted row set, with
ownership validation, then the existing machine classifier updates document/row
classes. Unknown source shape or inconsistent row classes are refused. Existing
admissibility reservations survive. Mandatory native control totals and printed
running-balance chains **are not revalidated by this writer**: either adds a durable
reservation withholding automatic inclusion (p3), even when closing arithmetic
balances. There is no reservation-clearance API yet. A correction can therefore
remove the whole document from default verified totals; the UI must explain this
before confirmation. Proof class is never supplied by a person. No graph writes.

Migration `20260906_correction_decision` widens the audit decision vocabulary. Its
downgrade refuses while correction events exist. Applied successfully to isolated
local PostgreSQL. Full backend suite: **3,524 tests, 12 skipped**, including 13 new
correction tests; Python 3.10 syntax and diff checks pass. Real HTTP/PG test created
synthetic case `c1da9946-1dfd-413a-a4e9-1828e1c76b72`: original preserved, replacement
and one correction audit committed, class recomputed to p3, repeat refused with 409.
Logs: `/tmp/loupe-neilbyrne-corrections{,-full,-migrate}.out`.

Next: correction review/record UI plus reading/history display. Include exact money,
separate preview/confirmation, durable success vs uncertain response, original-case
cache invalidation, and the verification limitations above. The later preview
verification segment supplies the projected class; display it before exposing
the final action. No frontend changes in this unit. No push or merge.

### Ledger correction preview foundation

`67fd272` adds `preview_amount_correction` and authenticated, case-edit scoped
POST `/api/financial/transactions/{transaction_id}/correction-preview` with required
`case_id`. Input is an exact decimal **string** of minor units plus explicit
credit/debit direction. Negative, fractional, boolean, unchanged and out-of-BIGINT
amounts are refused. Money in the preview response is also serialized as strings.

The preview locks document, periods and rows in the established order, refreshes
ORM state, and supplies a reviewed document revision for a future writer to
recheck. It only accepts current admitted/quarantined rows in admitted documents,
refuses inconsistent case/period ownership, preserves the original locator and
quarantine, and computes **fresh current/proposed statement balance identities**.
An unlinked row reports unavailable period impact. The endpoint rolls back to
release snapshot locks. No row, reconciliation result, proof class or audit event
is written, even if a direct service caller subsequently commits.

This preview itself is **not a correction writer or a frontend control**.
The existing graph editor is a separate edit-in-place path; it must not be reused
for the relational ledger. The replacement writer is now recorded above; next is
a review/record UI showing both readings. Revalidation must be explained
from the actual source shape: a statement balance identity is not a native file's
control-total validation. The preview explicitly does not claim native controls,
running-balance chains, proof class or graph were revalidated. A passing preview
does not authorize stale data to be written or silently release a quarantined row.

Verification: **3,511 financial backend tests pass, 12 skipped** (14 new tests),
Python 3.10 syntax check, diff check, and real authenticated HTTP/PostgreSQL preview
on the synthetic local case with an unchanged before/after ledger. Full-suite log:
`/tmp/loupe-neilbyrne-correction-preview-full.out`. The first full runs caught the
route-inventory guard and malformed foreign-period error handling; both were
fixed before the final passing run. No frontend changes or new schema migration.
The local application remains running. No push or merge.

### Local application is running

Startup instructions: `docs/local-application.md`. UI at
`http://127.0.0.1:55174`, backend 58002, evidence API 58003, worker active.
Native venvs: `data/local-runtime/backend-venv` and `engine-venv`; launcher
`scripts/local_app.py`. Separate `loupe-local` Docker volumes/loopback ports are
defined in `docker-compose.local.yml`. Existing `owl-pg` and `owl-n4j` containers,
real database storage, repository `.env`, and case evidence were not changed.

The launcher disables dotenv and clears provider credentials, uses a deliberately
invalid OpenAI key and development auth secrets, and confines evidence paths to
the ignored runtime directory. **Synthetic testing only.** The engine's OpenAI
health result only checks key presence and does not prove AI provider access.

Two real startup defects repaired in `0442f17`:

- Evidence engine editable installation failed due to ambiguous package discovery
  (`app`, `evals`, `alembic`). Packaging now explicitly includes `app` and children.
- PostgreSQL rejected the 33-character admission migration ID in Alembic's
  VARCHAR(32). That migration now widens the tracking column to 128 before its
  revision is recorded, preserving existing revision identity. Downgrade leaves
  the wider tracking column in place. Full empty-database migration to head passes.

Verification: both venvs pass `pip check`; backend financial suite **3,497 tests,
12 skipped** passes in the full venv; API health connects to Neo4j/evidence engine;
engine readiness checks PostgreSQL/schema, Neo4j, Chroma, Redis, OCR and storage;
worker connected to Redis; native PDF rendering passes using Homebrew libraries.
Browser login succeeded and synthetic cases are visible under **All Cases**.

`scripts/check_local_duplicates.py` creates labelled synthetic cases and checks
real authenticated HTTP exclusion/repeated request (200/409), restoration and
exact audit/row counts. It also proves **two separate PostgreSQL writers both wait
on held row locks**, then exactly one applies and one gets 409, followed by HTTP
restoration. Last passing case: `37d0fe31-2dad-409e-ab59-946b0fe5dc46`.
The local administrator is `loupe-local@example.com` / `Loupe-local-test-2026`.
Fixtures bypass normal case membership creation, so use **All Cases** to see them.

Logs: `/tmp/loupe-neilbyrne-local-{backend,engine,worker,frontend,migrate,duplicates,financial}.out`.
Services were left running for Neil. No production evidence was ingested; AI,
full UI acceptance, and financial-to-graph projection remain outside this check.
Continue with ledger corrections, following document-first locking and exact
Money/provenance rules. No push or merge was performed.

### Duplicate comparison is connected

The ledger tab now mounts `DuplicateCandidatesPanel` alongside the census and
ledger, in its own error boundary. **Compare documents** starts an on-demand
case-scoped GET `/api/financial/duplicates`; details show filenames, document IDs,
match descriptions, persisted document status/supersession target and row counts
by stored status. Coverage explicitly reports compared and skipped documents.
Skipped files include a reason. An empty comparison never claims no evidence or
no duplicates. The comparison itself changes no disposition or totals.

- `duplicate_query.list_duplicate_candidates` recomputes fingerprints in memory
  for admitted/superseded documents. This includes old imports with null keys and
  avoids stale cached keys after rows change. No backfill, native-ingest changes
  or stored-fingerprint update is needed for this read path.
- Fingerprint v2 includes **all** rows, including payment-file rows with no period
  and unlinked rows beside linked periods, account identities, currencies, period
  bounds/source labels and opening/closing balance observations. Empty documents
  receive `(None, None)` rather than the same empty digest. JSON encoding prevents
  separator ambiguity. Earlier v1 keys are not rewritten; the UI ignores them.
- A same-file/different-reading conflict has its own description. The comparison
  document is an anchor, not a recommended primary. An admitted anchor is preferred
  over a superseded one. Match labels do not assert that evidence is interchangeable.
- **Scope limitation stated in the UI:** grouping requires the same complete
  account/period coverage key. Different coverage is not grouped, even with the
  same file hash. This is a candidate review, not exhaustive pairwise byte detection.
- The synchronous API refuses cases over **500 financial source documents** with
  an explicit 422 and returns no partial result. This protects a potentially costly
  on-demand scan; large-case support needs a bounded asynchronous/full-case design.
- The route inherits authentication and `case:view`. Unexpected failures return a
  generic message. Other-case file names and documents are excluded from queries.
- The hook uses `["financial-ledger", caseId, "duplicates"]`, so existing ledger
  ingestion/adjudication invalidation also refreshes row dispositions here. No
  previous-case placeholder, no automatic retry. Failed refresh hides old results.
  The panel is keyed by case to reset its opened state on navigation.
- `readDuplicateCandidates` validates shape, case, coverage totals, unique IDs and
  group keys, anchor count and safe nonnegative counts; future match/status labels
  remain visible rather than becoming automatic permission to act.

Verification at this implementation:

| Gate | Result |
| --- | --- |
| Financial backend suite, Python 3.12 | **3,481 tests passed, 12 skipped** |
| Frontend unit | **86 files, 854 tests passed** |
| Chromium | **5 files, 7 tests passed** |
| TypeScript / eslint | **exit 0 / exit 0** |
| Python 3.10 syntax parsing | passed for changed backend files |

Backend additions cover historical null fingerprints, no writes even after commit,
case isolation, empty documents, stale stored keys, conflicting readings, actual
supersession/row status, coverage limits, balances and unlinked transactions; route
checks include inherited view permission and error redaction. Frontend checks cover
contract rejection, on-demand GET, ledger invalidation, failed refresh and details
in Chromium. Browser service responses are fixtures, not live backend E2E.

Logs: `/tmp/loupe-neilbyrne-duplicate-query-{backend,unit,browser,tsc,lint}.out`.
The first backend attempt failed the package-export guard; the new public symbols
were then exported and the complete final suite passed. No schema, evidence-engine,
Neo4j or live-evidence writes occurred. No dependency manifests changed.

### Reversible duplicate decisions are connected

`DuplicateDecisionForm` lets a reviewer select which matching admitted document
will remain, then enter a reason and separately **Record decision**. Excluded
documents also appear in their own list, so restoration stays reachable even if
a document no longer belongs to a candidate group. The form survives comparison
refreshes and shows confirmed success, definite refusal or an uncertain response.
It requires a new review after an error instead of automatically retrying.

`POST /api/financial/documents/{document_id}/duplicate-decision` inherits
**authentication and case:edit**. It takes an action, reason, reviewed document
revision, and (for exclusion) retained document/revision. The actor is constructed
from the authenticated user, never supplied by the request. Reasons are required
and retained verbatim; the HTTP body limits them to 4,000 characters.

- `duplicate_decisions.decide_duplicate` owns commit/rollback. It locks documents
  in ID order, then their periods and rows, and refreshes ORM state before checking
  revisions. The revision includes the fingerprint, disposition, row status and
  correction links, proof classes and latest document decision sequence.
- Exclusion requires two distinct admitted documents with equal fresh fingerprints.
  A primary with held/corrected rows, ineligible proof classes, an existing
  supersession or dependent exclusions cannot be displaced. This refuses weak or
  conflicting readings and avoids chains/cycles/all copies disappearing.
- The event records the authenticated actor, reason, reviewed revision digests,
  retained document, and **exact changed row IDs with before/after statuses**.
  Only admitted rows are superseded. Preexisting quarantine, rejection and row
  corrections remain untouched. The event and state commit atomically.
- Restoration requires the latest document decision to be a version-1 exclusion
  from this path with coherent row provenance. It restores only those recorded
  rows if they remain superseded and have no correction replacement. Missing or
  subsequently changed rows cause a refusal, not a partial restoration. Legacy
  exclusions without row provenance are explicitly refused.
- `quarantine_row` now locks the source document before the transaction and refreshes
  both. Quarantine/release refuse a non-admitted source document, preventing release
  of a held row from silently bypassing the document's exclusion. Future correction
  writers must follow the same document -> periods -> rows lock ordering.
- The query returns reviewed revisions, reading fingerprints and a separate list
  of excluded documents. UI choices require matching reading fingerprints; the
  backend remains authoritative and rechecks everything. A viewer attempting a
  write is refused by the endpoint's edit permission.
- A synchronous form lock prevents duplicate submission. Mutation variables capture
  the original case and reviewed documents; settlement invalidates that case's
  ledger (including comparisons) and decision history, including uncertain replies.
  No graph mutation or automatic reconciliation is implied.

Verification at this implementation:

| Gate | Result |
| --- | --- |
| Financial backend suite, Python 3.12 | **3,497 tests passed, 12 skipped** |
| Frontend unit | **87 files, 859 tests passed** |
| Chromium | **6 files, 8 tests passed** |
| TypeScript / eslint | **exit 0 / exit 0** |
| Python 3.10 syntax parsing | passed for changed service/router/test files |

The new backend tests cover round-trip audit provenance, preexisting corrections,
quarantine interaction, stale and repeated requests, weak/conflicting readings,
primary eligibility/dependencies, cross-case access, reason/self-exclusion refusal,
legacy restoration refusal, later corrections and rollback on commit failure.
Router tests cover authenticated actor forwarding, edit permission and error
translation. The existing exhaustive route-list test was updated for this POST.
Frontend tests cover one submission, reviewed revisions, original-case invalidation,
refusal/uncertainty and restoration payloads. Chromium exercises exclusion followed
by restoration through the connected panel and form.

**Limits of verification:** database tests use SQLite, whose FOR UPDATE does not
exercise PostgreSQL locking. Browser responses are fixtures. Run real PostgreSQL
concurrent requests and the full local app workflow before calling this integration
verified. Stored reconciliation results are not automatically refreshed by these
operations; the existing graph remains independent of the ledger. No migrations,
real-case writes, engine changes or dependency-manifest changes occurred.

Logs: `/tmp/loupe-neilbyrne-duplicate-decisions-{backend,unit,browser,tsc,lint}.out`;
focused provenance regressions: `/tmp/loupe-neilbyrne-duplicate-decisions-focused.out`.
The full backend gate was rerun after the final audit-snapshot change and passed.

### Whole-application local test milestone

Neil wants the whole application running locally with the Python backend in a
venv, not just isolated financial tests. This is recorded as the next integration
milestone, not as completed. Establish the actual launch/dependency configuration
from repository source, keep the environment reproducible and separate from global
Python, and start the frontend and required services together. Test with synthetic
case data, including real HTTP permission failures and concurrent duplicate actions.
The temporary test environment and its optional-dependency warnings do not establish
that every application feature can start. Do not reuse historical Linux sandbox
assumptions or claim the app is running from passing unit tests.

### Duplicate detection prerequisite completed

`score_document` called `reconcile_period`, which flushes saved totals, verdicts
and timestamps. Consequently `find_groups`, documented as read-only, performed
writes while nominating candidates. It now calls `total_transactions` and the
pure `evaluate_identity`, reading balances without recording an attempt.
Nomination still evaluates current admitted rows, rather than trusting possibly
stale stored reconciliation. Actual reconciliation remains an explicit writer.

Two new SQLite regression tests failed against the old code and pass with the
fix. They check all period columns survive a preview followed by commit, capture
SQL to assert no writes, and prove current rows govern nomination while a prior
stored result remains unchanged. The focused duplicate/reconciliation set passed
99 tests. The **full financial suite passed 3,468 tests, 12 skipped**. No routes,
UI, schema or production evidence were changed. No live E2E was performed.

Earlier source findings (comparison fixes above supersede the fingerprint gaps):

- `store_fingerprint` has no production caller. `find_groups` skips null keys;
  an empty response cannot mean a checked case has no duplicates. Design explicit
  coverage and a way to fingerprint existing documents as well as future ingest.
- `GroupMember.excluded` is the proposed strong-match policy, not a read of the
  persisted status. A review response must distinguish proposed and actual state.
- Only identical bytes/readings qualify for exclusion; same account/period is
  a candidate only. Do not wire automatic hiding for that weaker match.
- Audit nomination after supersession before exposing mutation: existing scoring
  counts admitted rows, while grouping includes superseded documents. Existing
  idempotence tests cover a simple pair, not every change of nominee or population.
- Fingerprints currently hash period identity and transaction content hashes,
  including all row statuses. Check empty periods, absent bounds, corrections,
  and balance observations before treating a hash match as safe exclusion.
- `cross_matter_sightings` reads other case IDs directly. Do not expose that helper
  without checking authorization for each matter. Purge is separate and destructive;
  it is not necessary for the first reversible review interface.

### Backend runtime now verified on this Mac

The isolated environment is `/tmp/loupe-neilbyrne-backend-venv`, using installed
**Python 3.12**. Changed files additionally pass `ast.parse(feature_version=(3,10))`;
this is a syntax check, not a Python 3.10 runtime test. No global Python packages
or repository dependency manifests were changed.

Installed the pinned bootstrap packages from `CLAUDE.md`, then added missing
`python-dotenv==1.2.3`, `bcrypt==5.0.0`, `cryptography==50.0.1` for configuration
and router imports. Earlier full-suite attempts failed collection for missing
bcrypt/cryptography; the final run collected all 3,468 tests and passed. ChromaDB
and pypdf import warnings remain; this is not evidence those optional features work.

Run from `backend/`:

```
env PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 /tmp/loupe-neilbyrne-backend-venv/bin/python -m unittest discover -s tests -p 'test_financial_*.py' -t .
```

Final output: `/tmp/loupe-neilbyrne-duplicates-backend.out`. Those were the prerequisite-only gates. The subsequent comparison unit gates are
recorded above; historical classification verification follows below.

### What the classification display now does

`ProofStandingPanel` is mounted on the ledger tab above `LedgerPanel`, in its own
error boundary. It remains reachable when the graph is empty/loading and when the
admitted ledger is empty. No new tab or persisted store value was needed.

- The visible summary reports financial source-document and ledger-row counts,
  plus counts in classes requiring a human decision. **Those are class counts,
  not outstanding-review counts.** It explicitly includes held-out, superseded
  and rejected records. A zero census does not claim the case has no financial
  evidence.
- Expand **View all classes and their rules** to see every class, including zeroes,
  with its document/row counts and all four backend-supplied permissions.
  Eligibility for totals is distinguished from a row actually being counted.
  The component offers no classification editor and derives no permissions from
  class labels. Unknown future classes remain visible as unrecognised values.
- `readProofStanding` validates the case, row shape, safe nonnegative integer
  counts, complete known-class set, unique classes, aggregate consistency and
  agreement between `counted_classes` and the reported flags. Incomplete data is
  an error, not a partial census silently presented as complete.
- `useProofStanding` uses `["financial-proof-standing", caseId]`, takes no graph
  filters, and has no cross-case placeholder. Refresh is explicit; background
  refresh labels the retained reading, and a failed refresh hides stale counts.
- `useIngestFile` invalidates the census after `stored: true`. Its mutation
  context preserves the case that started ingestion for cache invalidation,
  even when navigation occurs before the response. A no-op ingest does not
  refetch. Quarantine and file admission do not change this class-only census.
  Future duplicate purge, correction and reclassification writers must refresh
  it when they change the counted records or their classes.
- Shared descriptions now correctly say P0's control totals were checked
  successfully, and that P3 can include native files whose arithmetic failed or
  could not be checked. Both follow `assign_proof_class` in the existing backend.

This is frontend-only. No backend, engine, schema, migration or test-runtime
configuration changed. The classification endpoint and its contract were already
built; they now have a production hook and a rendered consumer.

### What the admission control now does

`ProcessHoldDialog` remains the shared surface for all seven processing entry
points. For each held file it shows the finding and offers a reason field and
**Record decision**. This calls the existing backend admission route. It does not
process anything. A verified `admitted` answer, or a verified
`nothing_to_override` answer, exposes **Process this file** as a separate action.
That action sends only that file with the original profile, worker count and image
provider. Other held and cleared files remain available in the dialog.

- `lib/admission-format.ts` validates the structured 409 refusal and interprets
  admission responses. Unknown, malformed, cross-file or contradictory answers
  cannot enable processing. A 200 refusal is shown as a refusal.
- `use-guarded-process.ts` reads server refusals as well as preliminary route
  checks. Releasing previously cleared files no longer erases a new server hold.
  A single-file refusal retains the rest of the selection and replaces the stale
  admission. Unexpected file ids cannot become actionable selections; repeated
  preliminary-check ids stop the request rather than choosing one finding.
- One synchronous operation lock prevents duplicate submissions and actions
  during an in-flight decision. Held state is scoped to its case. The case id is
  passed as a processing mutation variable so navigation cannot retarget a send.
- A recorded or potentially recorded decision invalidates that case's
  `financial-decisions` cache. Refused/no-op answers do not claim a write.
- Processing retries do not automatically record another admission. An uncertain
  admission or processing response is described as uncertain; there is no
  automatic mutation retry. Successfully requested files cannot be sent again
  within this held request.
- The backend's fresh file finding updates the held row, including the option to
  use the ledger if the recheck identifies a native format.

**Existing backend limitations remain, and this unit does not claim to close them.**
The admission gate checks existence, not per-send consumption. The evidence engine
still independently refuses native bank files; the control says so before the
person records a decision and directs supported native files to Send to ledger.
No backend, engine, schema or migration code changed.

### Verification on this Mac

All four frontend gates ran against the final implementation, with the committed
lockfile's dependencies restored using `npm ci --ignore-scripts`:

| Gate | Result |
| --- | --- |
| `vitest run --project unit` | **84 files, 845 tests passed** |
| `vitest run --project browser` | **4 files, 6 tests passed** |
| `tsc -b --force` | **exit 0** |
| `eslint .` | **exit 0** |

Two financial Chromium tests now exercise the connected UI: admission from a
server refusal through recorded decision to a separate processing click, and the
classification census through loading, expanding the rules and refreshing.
**Service responses are fixtures. These are not live backend or real-case
end-to-end runs.** The classification unit added 36 unit tests and one Chromium
test. The unrelated `__probe.test.ts` still contributes one file and one unit test.

The classification unit changed only frontend code. Backend tests were subsequently
run for the duplicate prerequisite: 3,468 tests with 12 skipped, as recorded above.
Neil's plan to test the full working product when ready remains unchanged.

### Local environment replaces Claude's sandbox assumptions

This session runs on **macOS (Darwin)** in
`/Users/neilbyrne/Documents/Owl/owl-n4j`, not `/sessions/...`. System Python was
3.14.2; disk had about 44 GiB available. `/dev/shm` borrowing recipes and claims
that engine tests are impossible here do not transfer. Keep the project's Python
compatibility targets; establish an appropriate runtime before backend work.

The existing `node_modules` lacked Mac Rollup. A broad `npm install` repaired
platform dependencies but selected newer versions; it was followed by **`npm ci`
to restore the exact lockfile** before the final checks. No package manifest or
lockfile changed. npm needed network approval. Cache:
`/tmp/loupe-neilbyrne-npm`. Do not run dependency upgrades as part of this unit.

The Chromium test server was blocked by sandbox localhost restrictions (`listen
EPERM`), then all browser tests passed outside the sandbox with the installed Mac
Chromium. “No tests” after that failure was not counted as a passing gate. Logs
for the latest classification unit are `/tmp/loupe-neilbyrne-proof-{unit,tsc,lint}.out`
and `/tmp/loupe-neilbyrne-browser.out`. Earlier admission logs are
`/tmp/loupe-neilbyrne-{unit,tsc,lint}.out`.

Git writes need sandbox approval. The implementation used a temporary index,
explicit paths, `commit-tree`, and an atomic `update-ref` with the expected parent;
the real index was restored from the reviewed temporary index. No git config was
changed, no unrelated files were staged, and nothing was pushed.

### Remaining sequence and risks

Phase 1 is connected. In Phase 2, runs, quarantine and decisions have interfaces;
reconciliation remains API-only. Item 8's admission and classification interfaces
are connected. Next are items 9–11: duplicates, ledger corrections, source locators. Phase 3 remains
projection, continuity/coverage, linkage/correlation/flow; Phase 4 remains
exhibit/export and tracing. The original plan's sequence stands.

The graph still is not derived from the ledger. No automatic reconciliation sweep
or reconciliation control exists. Computed quarantine grounds and localisation
still lack their wider production callers. Append-only storage is a service-layer
promise, not a database guarantee. Carry forward the remaining defects and design
decisions in the history and `financial-handoff.md`; this unit did not close them.

---

## Historical running detail through `cb1cd13`

The following is preserved for the reasoning and earlier decisions. Its “current
unit”, uncommitted-work, missing-admission-control and Linux environment statements
are historical and are superseded by the dated update above.


Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**If you have not worked on this subsystem before, read
`docs/financial-handoff.md` first.** It was written at `8a29fd2` on Neil's
instruction, for agents joining the work: what the financial subsystem is, the
sandbox facts that otherwise cost a session, the sixteen-unit plan with each
unit's status verified against source, what remains, and where the two planning
documents are wrong. **It corrects one claim in this file:** the proof-standing
census is *not* on screen. `financialAPI.getCaseProofStanding` exists with its
contract test and has **zero consumers** — no hook, no component renders it, so
item 8 owes two frontend units rather than one.

**Read first, at `2f93da1`+.** The session after `2f93da1` was **not a build
session**. Neil sent "seriously?????? fix this now", it was read as a rebuke
about the admission control, and he corrected it: **"I meant fix the sandbox
space issue."** That is what the session did. The outcome is under **Disk: do
not bootstrap pip either. Borrow that too.** — the short version is that the
151M-per-session pip bootstrap was never necessary, a borrowed `pylibs-*` tree
runs the whole suite, and `/dev/shm` went from 79M free to **244M**. All four
gates are green at this head. **The admission control's chunk 1 was written
before the correction and is uncommitted; it still has no ruling from Neil.**
See Uncommitted.

**Last updated:** 6 September 2026 (records `cbf163e`, the proof class census:
`services/financial/proof_standing.py` and its 28 tests, the package export,
`GET /api/financial/proof-standing` on the **ledger** router with 4 router tests,
and the TypeScript caller with a 15-test contract file. **`requires_adjudication`
had been defined, exported and called by nothing since the proof class rules were
written; it now has a production caller and a way to the screen.** This completes
**chunk 3 of item 8**. **Backend and frontend both moved.** All gates were run at
this head, including the browser project. **The next unit is the admission
control** — see "Current unit" under Build order; it is now the only thing
between item 8 and done, **it is not in the wiring plan, and it needs a ruling
from Neil before it is built.** Read the disk note under Standing flags **before
running anything**: `/dev/shm` is down to **93M free, then 79M by the end of the
session**, which is no longer enough for a pip bootstrap plus a Chromium install,
and this session got the browser gate by **reusing a leftover browser directory
rather than installing one** — see "How to run the browser gate".)

**Standing, from the session before last, and not to be softened.** Neil asked
whether assertion-driven work would hold up "when we get to the real piece", and
whether the passing suites were a happy path. The honest answer: **every
frontend test stubs the network, so none of them demonstrates the product
working against a running backend.** He accepted this and said he will test a
full working version when the system is ready. That is a commitment this build
owes him. See **Verification debt** below.

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `cbf163e`
  (`cbf163e0cd247eed7ce7d059e017be4f9b1812d4`), "Report where a case's evidence
  stands by proof class", parent `d28b9d3` (which was the state-file commit for
  `4e13821`). **Confirm the real tip with `git log --oneline -5`** at the start of
  every session rather than trusting this line — the state-file commit that
  follows this one will already have moved it.
- **Nothing is pushed.** Push is blocked; Neil pushes.
- **The build order lives in `docs/loupe-wiring-plan.md`,** not in this file. Read
  it before picking up work. It is an agreed plan and is not to be resequenced
  without a ruling from Neil.

### Uncommitted

**Two files, and they are chunk 1 of the admission control — written on a
misreading, never ruled on, deliberately not committed.**

- `frontend_v2/src/features/financial/api.ts` — modified. Adds an admission
  section before `financialAPI`: `FILE_ADMISSION_OUTCOMES` and
  `HELD_ROUTE_OUTCOMES` const arrays, the `FileAdmission`, `HeldFile` and
  `UnadmittedFilesRefusal` interfaces with their `*_FIELDS` guards,
  `UNADMITTED_FILES_ERROR`, `AdmitFileParams`, and an `admitFile` caller posting
  to `/api/financial/files/{file_id}/admit?case_id=...` with `{reason}`.
- `frontend_v2/src/features/financial/api.admission.test.ts` — new, **20 tests**,
  the house contract style: half assert the request shape, half `readFileSync`
  the Python and pin the enum members, the `as_dict()` keys, the 404/500 mapping
  and `BLOCKING_OUTCOMES`.

**Both are green.** `tsc -b` 0, `eslint .` 0, unit **79 files / 769 tests**
including this file's 20, browser 2 files / 4 tests. So this is verified work,
not a half-finished edit — it is uncommitted **only** because the flag recorded
at `cbf163e` still stands: *the admission control is not in the wiring plan and
needs a ruling from Neil before it is built.* That ruling has still not been
given. Committing it would smuggle an unplanned item into the build on the
strength of a message that turned out to be about the disk.

**One novel piece worth keeping if it is committed.** `pythonBlock` in the
existing tests ends a block at the next column-one line, which is wrong for a
method inside a class, and `admission_gate.py` declares `as_dict` **twice** — on
`HeldFile` and on `UnadmittedFileError` — so a search from the top of the file
finds whichever comes first regardless of which was asked for. The new file adds
an indent-aware `indentedBlock`/`asDictKeys` pair instead. If chunk 1 is
discarded, that fix should still be lifted into the shared helpers.

**If Neil rules against it,** `git checkout -- frontend_v2/src/features/financial/api.ts`
and delete the test file; nothing else references either.

Still untracked and still un-removable from a session (workspace denies
`unlink`) — Neil has to delete these from his side:

- `backend/services/financial/export_manifest.py.bak`
- `backend/services/financial_export_service.py.bak`
- `frontend_v2/src/__probe.test.ts` — a diagnostic left by the vitest
  investigation ten sessions ago. It is **counted in the frontend baseline
  below** (it contributes 1 file and 1 test), so when it is deleted the unit
  numbers drop by one each and that is expected, not a regression.
- `backend/pytest-cache-files-7jhqubws`. Left at `4e13821` by a pytest run that
  was not given `-p no:cacheprovider`; see the pytest note under "Learned
  recently". It is an **empty directory**, so `git status` does not list it at all
  and it cannot get into a commit — but `rm -rf` on it fails with `Operation not
  permitted`, so it stays until Neil removes it.

**Nothing new was added to that list at `cbf163e`.** The seven files this session
touched are all tracked and all committed.

Also untracked, and **not** mine — Neil's own documents and case material, left
alone. `docs/IP_Protection_Strategy.docx`, `docs/ip-protection-strategy.md`,
`docs/owl-project-brief.md`, and a large amount of Cellebrite and bundle
material at the repo root. **Do not delete any of it to free disk;** see the
disk note under Standing flags.

### Scale

**138 commits** since `c4246c0` (27 August), counting `cbf163e` and the state
commit for `4e13821` that preceded it; 139 once this state-file commit lands on
top. Counted with `git rev-list --count c4246c0..HEAD`, not incremented from the
previous figure.

`backend/services/financial/` **54 modules** excluding `__init__.py` (up one:
`proof_standing.py`); `backend/tests/test_financial_*.py` **61 files**, **3,466
tests**. All three counted at this head with `ls | wc -l` and a full suite run,
not carried forward.

**Re-measured at `cbf163e`, because Neil once asked what the time had gone on and
the figures here were from an older head.** `git diff --shortstat c4246c0..HEAD`:
**235 files changed, 117,811 insertions, 350 deletions**. **97 of the 235 files
have `test` in the path.** So a little over half the output is tests, and the
ratio has held steady as the build has grown. That ratio is defensible for
forensic software, but it is not self-justifying, and it was **spent almost
entirely on internal consistency** rather than on whether the pieces work
together when running. Do not quote the test count to Neil as evidence the system
works.

### Gate baselines as of `cbf163e`

**Every one of these was actually run at this head.** No figure below is carried
forward, which has not been true of this section for several sessions.

- **Backend financial suite: `Ran 3466 tests in 16.145s, OK (skipped=12)`.**
  Up **32** from `4e13821`'s 3,434: **28** in the new
  `test_financial_proof_standing.py` and **4** added to
  `test_financial_ledger_router.py`. That is exactly the two files' own counts,
  and the arithmetic being exact is the check that nothing else moved.
  **There are no expected failures.**
- **`grep -c '^Traceback'` on the run output: 8, unchanged.** Worth recording
  because the suite deliberately exercises logged failure paths, so a rising
  count is a signal a green run will not give you. The new route's 500 path adds
  a **single-line** `logger.error` with no traceback, so it does not move this.
- **`tests.test_financial_exports` alone: 5 tests, OK.** Run separately as well
  as inside the suite, because it is the guard a new module is most likely to
  trip. It is **fully automatic** — see the durable fact below; there is no list
  in it to update, and `proof_standing.py` needed no edit to it.
- **The evidence side was NOT re-run, and did not need to be.** Nothing this
  session touched `services/evidence_processing_service.py` or either evidence
  router; the seven changed paths are all under `services/financial/`,
  `routers/financial_ledger.py`, `backend/tests/` and
  `frontend_v2/src/features/financial/`. Confirmed against `git status`, not
  assumed. Re-run it whenever the gate or the processing service moves.
- **Frontend unit: 78 files, 749 tests, exit 0.** Up one file and 15 tests, which
  is exactly `api.proof-standing.test.ts`.
- **`tsc -b` 0; `eslint .` 0.** Both run at this head.
- **Frontend browser: 2 files, 4 tests, exit 0**, matching the documented
  baseline. Run at this head **without installing anything** — see below.

### How to run the browser gate

**Do not install Chromium. Point at the one that is already there.** This is the
correction established at `cbf163e`, and it replaces the install recipe that
stood here before — which will now fail, because there is no longer room for it.

An earlier session left a full Playwright install in `/dev/shm` and the sandbox
cannot remove it. It is **928M**, it is the single largest thing on that
filesystem, and it is **world-readable and executable**, so it can simply be
used. Verified at this head:

```
ls /dev/shm/pw-inspiring-peaceful-brown
# chromium-1208  chromium_headless_shell-1208  ffmpeg-1011
test -x /dev/shm/pw-inspiring-peaceful-brown/chromium_headless_shell-1208/chrome-linux/headless_shell
```

Then, from `frontend_v2/` with an absolute `cd`:

```
PLAYWRIGHT_BROWSERS_PATH=/dev/shm/pw-inspiring-peaceful-brown \
  VITE_CACHE_DIR=/dev/shm/vite-cache-$(id -un) \
  npx vitest run --project browser
```

That reported **2 files, 4 tests, exit 0 in 3.45s** at `cbf163e`, matching the
documented baseline. Check the directory still exists before relying on this: if
Neil clears `/dev/shm`, this goes with it and the install recipe becomes
necessary again — and possible again, since clearing it frees 928M.

**`--fileParallelism=false` was NOT needed at `cbf163e`.** The flag was recorded
as required at `4e13821`, where the two browser files raced the single vite dev
server and one died with `Failed to fetch dynamically imported module:
.../CaseSettingsPage.tsx`. Run in parallel at this head against the pre-existing
browser directory, both files passed. So the flag is a **remedy for a flake, not
a standing requirement**. If that error appears, add it back; do not chase it as
a code bug in `CaseSettingsPage.tsx`, which passes 3 of 3 alone, was last touched
at `0385354` on 21 July, and whose import graph reaches no financial code.

**The flake now has a cause, and it is a cold vite cache rather than
parallelism.** After `2f93da1` deleted this session's `VITE_CACHE_DIR`, the very
next browser run failed with exactly that `CaseSettingsPage.tsx` dynamic-import
error — 1 file failed, 1 passed. **The immediate re-run, changing nothing but
the cache now being warm, gave 2 files and 4 tests, exit 0.** So the first
browser run after the cache is cleared races the dependency optimiser and should
simply be run twice. Do not read the first failure as a regression, and do not
reach for `--fileParallelism=false` before trying the re-run.

### Disk: do not bootstrap pip either. Borrow that too.

**This is the correction established after `2f93da1`, and it removes the
151M-per-session leak that the note here used to describe as unfixable.**

The reasoning that already applied to Chromium applies to the Python packages
and nobody had noticed. The `pylibs-*` directories other sessions leave behind
are mode `drwxr-xr-x` — **world-readable, like the Playwright install** — so a
session does not need its own copy. Point `PYTHONPATH` at one that is already
there:

```
env PYTHONPATH=/dev/shm/pylibs-sharp-peaceful-ramanujan \
    PYTHONPYCACHEPREFIX=/dev/shm/pyc-$(id -un) \
    PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 \
    python3 -m unittest discover -s tests -p 'test_financial_*.py' -t .
```

**Verified, not assumed.** That tree holds 155 entries against the documented
seventeen packages' 143, so it is a superset; `sqlalchemy 2.0.46`,
`fastapi 0.123.9` and `pydantic 2.12.5` match the pinned versions exactly; and
the whole financial suite ran green on it: **`Ran 3466 tests in 13.535s, OK
(skipped=12)`**. The proof was run *before* this session's own copy was deleted,
which is the order it has to be done in — see the trap below.

**Pick any `pylibs-*` that is not yours and check it first.** Compare its entry
list against the package set with `ls`, then import the seventeen names in one
`python3 -c` before trusting it. `pylibs-cool-relaxed-bohr` carries a different
`langsmith` version; the others were identical. If every candidate is gone,
fall back to the `--target` bootstrap recorded under "Learned recently" — which
now needs about 151M free, so measure before starting it.

**Free your own leavings before you finish.** They are the only thing you can
remove. At `2f93da1` this session deleted its own `pylibs-` (152M), `vite-cache-`
(14M), `tmp-` and pip log, and `/dev/shm` went from **79M free to 244M**. Doing
this every session is what stops the filesystem filling, and it costs nothing
once the tree is borrowed rather than built.

**Measured state after that clean-up**, with `df -h` and `du -shx`:

- **`/dev/shm`: 2.0G, 244M free.** Holds the 928M Playwright install, **five**
  remaining `pylibs-*` at ~151M each, and a scatter of other sessions' vite
  caches and `.out` files.
- **`/sessions`: 9.8G, `0` bytes free — completely full.** `du -x` sees only
  268K because **59 other session directories** are mode `drwxr-x---` owned by
  other users. That is where the 9.3G is. Not deleted-but-open files (`/proc/*/fd`
  scanned, zero found) and not inode exhaustion (20% used).
- **`/`: 9.6G, 126M free.** `/usr` 6.0G, `/tmp` 1.7G, `/var` 1.5G. Of `/tmp`,
  **0.246 MB was this session's and 3,401 MB was not.**

**What only Neil can clear,** because there is no `sudo` and both `/tmp` and
`/dev/shm` carry the sticky bit: the 59 stale `/sessions/*` directories (9.3G,
by far the largest), the 3.4G of other users' `/tmp` files, and the stale
`/dev/shm/pylibs-*` and `pw-*` trees. **This was tested rather than inferred** —
`rm -rf /dev/shm/pylibs-awesome-jolly-clarke` returns `Permission denied` on
every file.

**Two traps when measuring this.**

- **`du` must be given `-x`.** Without it, it follows into the virtiofs repo
  mount and reports **16G for a session directory that holds 24K**. That single
  mistake sends the whole diagnosis after a phantom.
- **Never delete your own `pylibs-` before proving a borrowed one works.**
  Rebuilding costs 151M, and if free space is below that at the moment you
  delete, the session has no backend suite and no way to get one.

**`HOME` is on `/sessions`, which is at zero bytes**, so npm's default cache
cannot be written. Pass `npm_config_cache=/dev/shm/npm-$(id -un)` to every
`npx` invocation. All four gates were run that way after the clean-up and all
four were green.

**Eight tracebacks on stderr during the backend run are expected and are not
failures — this figure was wrong here for several sessions and read "six".** It
was corrected at `2eefc4d` by counting the *baseline* tree at `dfb9715` as well
as this head; both give eight, so the extra two are **not** a regression from any
recent change. Eight `^Traceback` lines, **seven logged events**, because one
event prints a chained pair. In run order:

1. `RuntimeError: database gone`, logged by `routers/financial_ingest.py:214`
   under "Failed to ingest file ...". A router test injects it through a mock
   `side_effect` to exercise the route's error handler. **This is one of the two
   the old "six" omitted.**
2 and 3. One event, two tracebacks. `sqlite3.IntegrityError: UNIQUE constraint
   failed: financial_transactions.case_id, financial_transactions.ref_id`,
   followed by "The above exception was the direct cause of the following
   exception" and the `sqlalchemy.exc.IntegrityError` wrapping it. Raised from
   `native_ingest_file.py:331` and logged as "Writing evidence file ... failed";
   `tests/test_financial_native_ingest_file.py` ingests the same file twice on
   purpose. **The chaining is the other half of the old undercount** — one
   failure, two `Traceback` headers.
4, 5, 6. `test_financial_quarantine_row.py`: two
   `SQLAlchemyError("connection lost")` injected into each writer to exercise the
   `write_failed` path, and — since `35cc6be` — one
   `services.financial.money.MoneyError: currencies do not match` injected into
   the rescue check to prove an unanswerable question does not stop a quarantine.
   `quarantine_row.py` logs all three with `logger.exception`.
7, 8. The reconciliation pair from `dfcef2b`:
   `test_financial_reconcile_case.py` injects an `OperationalError ... locked` on
   a liveness `SELECT 1` and a disk-full failure on `COMMIT`.

All eight are the code working. **Do not spend a session chasing them.** Count
them directly rather than trusting this list:
`grep -c '^Traceback' <run output>`.

Separately, several **single-line** log messages with no traceback also print,
and are equally expected: "Failed to precheck file ... : database gone",
"Failed to list ledger transactions ... : db exploded", and — new at `2eefc4d` —
"Failed to list decisions ... : db exploded", which is the new route's 500 path
being exercised. A `logger.error` without a traceback is not a failure either.

---

## What this session did

**A case can now say how much of its evidence sits in each proof class, and what
each of those classes lets the case do with it, as `cbf163e`.** Seven files,
1,520 insertions, 3 deletions. **Backend and frontend both moved**, which the
previous two units did not.

This is **chunk 3 of item 8**. Three files are new and four were edited:

- `services/financial/proof_standing.py` (292 lines) — `case_proof_standing`,
  `ClassStanding`, `ProofStanding`, `ProofStandingError`.
- `tests/test_financial_proof_standing.py` (639 lines, **28 tests**).
- `frontend_v2/src/features/financial/api.proof-standing.test.ts` (280 lines,
  **15 tests**).
- `services/financial/__init__.py` (+14) — the four names exported.
- `routers/financial_ledger.py` (+54, −3) — `GET /api/financial/proof-standing`,
  plus a rewritten module docstring, because the old one said "three reads" and a
  fourth arriving would have made it false.
- `tests/test_financial_ledger_router.py` (+112) — `GetCaseProofStandingTests`,
  **4 tests**.
- `frontend_v2/src/features/financial/api.ts` (+132) — `ClassStanding`,
  `ProofStandingResponse`, `CLASS_STANDING_FIELDS`, `PROOF_STANDING_FIELDS`,
  `financialAPI.getCaseProofStanding`.

**Why this was the gap.** `requires_adjudication` was defined at
`proof_class.py:206`, exported from the package, and **called by nothing**. That
is not cosmetic. The class labels are two characters each, and the one fact a
reader needs about `p3` — that it is the only class no ingestion run admits by
itself — lives in that predicate and nowhere on the screen. Counts rendered
without it show material nobody has ruled on as though it were part of the
verified ledger, and **that failure is invisible from the screen**, which is why
the frontend contract test asserts the field by name on its own rather than
leaving it to a set comparison that a rename could satisfy.

**What it does.** `case_proof_standing(session, case_id)` counts the case's
source documents and its ledger rows by proof class and attaches, per class, the
four things `proof_class` says that class permits: `admits_automatically`,
`requires_adjudication`, `may_produce_ledger_rows`, `counts_toward_totals`. It
reports every class, present or absent, and the case totals plus the two
"requiring adjudication" figures. The route hands `as_dict()` straight out and
the TypeScript caller hands the response on whole.

### The six things that had to be decided, and how each was settled from source

1. **`requires_adjudication` is a read, not a stored column.** This was the
   question the previous state file left open, and it decided whether chunk 3 was
   a route or a migration. Settled by reading `proof_class.py`: the predicate is
   `proof_class is ProofClass.p3` — a pure total function of a column that is
   already `NOT NULL` on both tables. Storing it would be a denormalised
   duplicate that can disagree with its own source. **A route.**
2. **The route goes on `routers/financial_ledger.py`, not
   `routers/financial_adjudication.py`. This overturns what the previous state
   file predicted**, which was that the adjudication router is "the natural
   home". That is right for a write and wrong for this. Every route on the
   adjudication router resolves to `("case", "edit")` unconditionally via
   `_adjudication_case_permission`, and the ledger router's own docstring already
   says the reason in terms: *"A read dropped in would take a permission it does
   not need, and would make that comment false."* Describing what a case holds
   needs no more permission than reading the rows does. This follows the
   precedent chunk 1 set with `GET /api/financial/decisions`.
3. **The four permissions are imported from `proof_class`, never restated.** A
   second copy of the rules can disagree with the ones the ledger actually
   enforces, and the disagreement would surface as unverified material displayed
   as verified. Asserted from the frontend side too, by reading the Python source
   for the import.
4. **Every class is reported, including the ones holding nothing.** "No p3
   documents here" and "nothing looked at p3" are different facts, and an absent
   key spells them the same way. Implemented as `for member in ProofClass` and
   pinned by a test that reads that line out of the source.
5. **The route takes the case and nothing else — no filters, no `included`.** It
   is a census, so the per-class figures add up to the case's documents and rows,
   and that is the one property that lets a reader check the breakdown at all. A
   filter would break it **while the response looked identical**. The set of
   classes counted toward totals is likewise not a parameter: it is the set the
   ledger's own aggregates use, and it is reported back in `counted_classes` so
   any figure derived from this can state its coverage. A caller free to choose a
   different set is free to display a coverage the totals beside it were never
   computed against. Grepped first to confirm no existing router exposes the
   class set; `tracing.py` and `flow.py` take it as a Python default only.
6. **`ProofStandingError` is deliberately NOT mapped to 400,** unlike
   `DecisionLogError` on the route above it. The difference is who can act on it.
   The decision log refuses things a caller sent — a negative offset, an unknown
   filter — and the caller can send something else. This route sends the service
   nothing but a case, so its only reachable refusal is a stored `proof_class`
   outside the vocabulary: a data-integrity failure no request caused and no
   request can fix. That belongs in the logs as a 500. Pinned by
   `test_a_proof_standing_error_is_a_500_and_not_a_400`.

### One axis, deliberately

The census reports the **class** axis only. It never filters by `status` or
`ledger_status`, because a superseded document is still `p3` — its disposition
changed and its class did not. Asserted by
`test_disposition_does_not_change_the_class_count`.

### Totals are summed from the parts

Not counted separately. So the parts cannot disagree with the whole, and a reader
checking the breakdown against the case totals is checking something that is true
by construction rather than by two queries happening to agree.

### Traps found this session

**A test fixture reused one evidence file across many documents, and the model
forbids it.** Six tests died with `sqlite3.IntegrityError: UNIQUE constraint
failed: financial_source_documents.ingestion_run_id,
financial_source_documents.evidence_file_id`. The table holds at most one
document per file per run — which is the model saying **a run reads a given
upload once**. Fixed by having `make_document` mint a fresh evidence file when
none is named, and recorded in the fixture as a comment about what the constraint
means, not as a workaround.

**A regex scanning a Python signature will happily read `try:` as a parameter.**
The frontend contract test scanned `/^ {4}(\w+):/gm` over the whole route body
and got `['case_id', 'db', 'try']`. Fixed by scoping the scan from `async def` to
the `\n):` that closes the signature. Worth knowing because every one of these
contract files parses Python with regexes, and the failure mode is a test that
fails for a reason that has nothing to do with what it is testing.

**A drafting defect survived into the file:** `_member` was used in a test and
never imported. Caught only by running. Same lesson as the `FileAdmission` trap
recorded below: **grep a new test file for the names it uses before running it.**

---

## The session before this one, in detail

*Compress this into "The previous sessions, in brief" next session.*

**A file the router holds back can no longer reach the document pipeline unless a
named person has said on the record that it should, as `4e13821`.** Six files,
1,054 insertions, 3 deletions. **Backend only; no TypeScript was touched.**

This is **chunk 2b of item 8**, and it completes the admission path. `5fa71a2`
wrote the decision; this refuses without one. Two files are new and four were
edited:

- `services/financial/admission_gate.py` (254 lines) —
  `gate_document_processing`, `held_without_admission`, `admitted_file_ids`,
  `HeldFile`, `UnadmittedFileError`.
- `tests/test_financial_admission_gate.py` (704 lines, **25 tests**).
- `services/financial/__init__.py` — the five names exported.
- `services/evidence_processing_service.py` — the call site, plus a `_stored_path`
  helper that is now the one place a file's path is resolved.
- `routers/evidence.py` and `routers/evidence_folders.py` — a 409 on each of the
  three routes that reach `process_db_files`.

**What it does.** Immediately before the files are marked as processing and handed
to the engine, the gate re-reads each one's leading bytes, keeps the ones the
router holds back, asks the adjudication log whether an
`admit_financial_document` decision exists for each in this case, and raises
`UnadmittedFileError` if any is unaccounted for. The error carries every held
file with the router's finding — the outcome, the detected format, and who claims
it — so one refusal tells the caller everything they have to decide about.

### The eight things that had to be decided, and how each was settled

1. **The gate is called from `process_db_files`, not from a router.** All three
   ways into the pipeline — `POST /api/evidence/process`,
   `POST /api/evidence/process/background` and the folder route — go through that
   one function. A gate on two of the three would be a door with a lock beside
   it. The routers do only the thing routers should do, which is turn the refusal
   into a status code.
2. **It gates `valid_files`, not the requested ids.** By the time the gate is
   reached, files already processing, already processed, or missing from disk
   have been dropped. Gating the request rather than the send would turn today's
   quiet "that one was missing, we skipped it" into a refusal of the whole batch
   over a file nobody was about to process. A file that will not be sent needs no
   decision behind it.
3. **It is the last thing asked before the first thing is written.** So a refusal
   leaves the files exactly as it found them: not marked processing, no snapshot
   stored, nothing sent. This is a fact about *where the call sits*, not about the
   gate, so it is tested through `process_db_files` itself rather than through the
   gate alone.
4. **Nothing blocking means the database is not touched.** `admitted_file_ids`
   returns an empty set for an empty input without querying, and
   `held_without_admission` only reaches it when at least one file blocks. This is
   not an optimisation: `process_db_files` is called in at least one existing test
   with an object that has `commit()` and nothing else, so a gate that queried
   unconditionally would break a caller that never had a held file. The test for
   it uses a session that raises on **every** attribute, so a query written later
   through some other method is caught by the same object.
5. **Path resolution is shared by construction, not by agreement.** `_stored_path`
   is the path the module opens and the one the gate is handed. A gate that
   resolved a path differently from its caller would clear one file and send
   another.
6. **The finding is re-read from the file, never accepted from the caller.** Same
   reason `admit_file` re-reads: a caller that could tell the gate "nothing here
   blocks" is a gate anyone can walk past. Asserted by rewriting the bytes on disk
   under a row that still describes a letter and checking that the gate refuses.
7. **The whole request is refused; the offending files are not silently dropped.**
   A caller who asked for five and got four jobs back, with nothing naming the
   fifth, would reasonably read that as success. The handler above already refuses
   a whole batch over one unknown file id, so this is the behaviour that was
   already there. And the direction a mistake should fall is that nothing happens:
   an unwanted refusal costs a round trip, an unnoticed partial send puts a
   statement's figures into the text index with no decision behind them.
8. **409 Conflict, not 403.** The caller has the permission the route asks for.
   What is missing is not rights but a decision, and the response says which files
   and what was found in each, so an interface can offer the admission.

### The limit this has, stated as a limit and asserted as a test

**The gate asks whether an admission exists, not whether an unused one does.** So
one recorded decision clears the same file for every later send.
`AdjudicationDecision` says an admission "authorises one send" and
`admit_case_file` appends a second event rather than deduplicating; this does not
honour that.

**Nothing in the schema can.** There is no link from an adjudication to a
processing job and no per-file record of a send that a decision could be matched
against. A `consumed` flag on the event is the obvious fix and is the wrong one:
it would make an append-only log mutable, which is the single property the table
exists to have. Closing it is a schema change, not a change to this module.

It is written into the module docstring, and **asserted as a test that describes
the behaviour as it is** — so the limit lives in the suite rather than only in
prose, and a later change that closes it fails a test that says what changed.

### Traps found in that session

**`decisions.record` requires an `Actor`, not a `User`.** A test passed the ORM
user straight through and died with `DecisionError: actor must be an Actor, got
User`. `admit_case_file` accepts a `User` and converts internally, which is why
this is easy to get wrong from a test that has one to hand. Wrap it:
`decisions.Actor(name=..., email=..., user_id=...)`.

**`git` path arguments silently match nothing unless the command starts with an
absolute `cd` to the repo root.** A `git diff -- backend/routers/evidence.py` run
with the working directory at `backend/` returned **empty output and exit 0**,
which reads as "no changes" rather than as an error. `CLAUDE.md` records the cwd
trap; this is the form of it that costs a wrong answer instead of a failure.

**pytest is not in the documented bootstrap, and left a directory that cannot be
removed.** See "Learned recently" for the flags that make it safe.

---

## The session before that one, in detail

*Compress this into "The previous sessions, in brief" next session. It is two
units old now and has been carried once already.*

**A person can now overrule the router about one file, on the record, as
`5fa71a2`.** Five files, 1,115 insertions, 15 deletions. **Backend only.**

That was **chunk 2a of item 8**. Two files were new and three edited:

- `services/financial/admit_file.py` (309 lines) — `admit_case_file`,
  `find_case_file`, `FileAdmission`, `FileAdmissionOutcome`.
- `tests/test_financial_admit_file.py` (453 lines, **20 tests**).
- `services/financial/__init__.py` (+13) — the four names exported.
- `routers/financial_adjudication.py` (112 changed lines, of the 15 deletions) —
  `POST /api/financial/files/{file_id}/admit`, a `_respond_admission` helper, and
  a rewritten module docstring.
- `tests/test_financial_adjudication_router.py` (243 changed, 13 tests → **21**).

**What it does.** `admit_case_file` finds the file in the case, re-reads the
router's finding from the file itself, and appends an
`AdjudicationDecision.admit_financial_document` event carrying the person's name,
their stated grounds, and what the router had found at the moment they overruled
it. Five outcomes: `admitted`, `not_found`, `nothing_to_override`, `refused`,
`write_failed`.

### The four things that had to be decided, and how each was settled from source

1. **The check is re-run inside the service, not accepted from the request.**
   `record_admission` copies the `FileRouteCheck` into the event verbatim — which
   is right, because the finding has to be the one the decision was taken
   against, and a finding re-derived later would describe a different question.
   But it means **whoever supplies the check decides what the record says was
   found**, and a check arriving over the wire could say anything. So the route
   takes no description of the file and no statement of the finding, and this is
   asserted **against the handler's signature**, not against a response: a
   parameter that is merely ignored today is one a later edit can start
   honouring. Cost: one prefix read.
2. **Every blocking outcome is overridable, including `native`.** Admitting a
   native file means its figures get inferred from text rather than parsed, which
   is the failure the whole subsystem exists to prevent — so this needed a reason,
   and `AdjudicationDecision`'s own prose is it: the member is described there as
   being for "a bank statement that arrived on the evidence list ... admitted
   *out* to that pipeline anyway, by a named person who was shown what the router
   found and chose to proceed." That is the native case by name. The detector
   reads a prefix and matches a signature, so it can be wrong, and a file it
   wrongly claims would otherwise have **no path at all**: the ledger cannot parse
   it and the pipeline will not take it. The answer to a fallible detector is a
   person who can say so on the record, not a refusal nobody can get past.
3. **`nothing_to_override` is a 200, not a 4xx.** It means the router was not
   holding the file, so it can be processed with no decision recorded at all —
   something the caller can act on, not something that went wrong. A 4xx would
   send it down the browser's failure path.
4. **`_respond_admission` is written out separately rather than folded into
   `_respond`.** The two outcome enums happen to share `not_found` and
   `write_failed` today, so a shared helper would have to compare
   `outcome.value` as a string and would **go on passing** if one were later
   renamed on only one side. Comparing by identity against the enum the result
   actually carries fails loudly instead, which is the right direction here: the
   branch decides whether a refusal reaches the interface or the error path.

### What that deliberately did not do — CLOSED at `4e13821`

It recorded the override and did not stop a held file being sent without one.
`admission.py` states the rule as *"the event is written before the file is sent,
or it is not sent"*, and 2a was the first half. **The second half landed this
session** as `services/financial/admission_gate.py`. The two together are the
whole rule, subject to the consumption limit recorded above.

### Known gap, and it is in the other service

The engine runs its own pre-stage, `evidence-engine/app/pipeline/orchestrator.py`,
which **fails any job whose file it detects as native**, and it has **no channel
by which an admission recorded here could reach it**. So an admitted native file
is recorded here, sent, and then refused there with a message naming the format.
Nothing is lost and nothing is silent, but **the override does not yet take
effect for that one outcome**. Closing it is an engine change and was not this
unit. It is recorded in `admit_file.py`'s own docstring under a heading, not just
here.

### Three traps found in that session

**A test premise can be impossible and the error will not say so plainly.** A
test built an `EvidenceFile` with `stored_path=None` to exercise the pathless
case and died with `sqlite3.IntegrityError: NOT NULL constraint failed`. Reading
`postgres/models/evidence.py:128` settled it: `stored_path` is
`mapped_column(Text, nullable=False)`, so **a pathless evidence row cannot
exist**. The real condition is a **resolver** that returns `None` — what happens
in a container whose mount differs from the one that took the upload. The test
was replaced with `resolve_path=lambda stored: None`, which is the production
case, and the fixture's now-dead `None` branch was removed.

**The router's route-set test failed, by design, and that is the point.**
`test_both_routes_are_posts_under_a_transaction` compares the **whole** route
dict exhaustively, so adding a third route broke it. It was renamed to
`test_every_route_is_a_post_against_the_thing_it_adjudicates` and its docstring
now says why the comparison is exhaustive: a route added to this module inherits
`case:edit` unconditionally from `_adjudication_case_permission`, so a new route
must fail here, where whoever added it has to say what it is.

**Dead drafting code survived into the committed-to-be file.** An
`absent = FileAdmission(...)` / `del absent` pair was left in a test. Removing it
orphaned the `FileAdmission` import, which was then given a real use —
`assertIsInstance(result, FileAdmission)` — rather than deleted. **Grep the new
file for its own imports before committing.**

---

## Verification debt — read this before quoting any test count

Neil asked, three sessions before this one, whether building to assertions would
hold up "when we get to the real piece", and whether the passing suites were a
happy path. He was right to ask. The answer given, which is not to be softened:

- **Every one of the 749 frontend tests stubs `globalThis.fetch`.** They prove
  the reading, narrowing and caching logic is internally consistent, and they
  catch regressions in it. **Not one of them demonstrates the product working
  against a running backend.**
- **The only genuine bridge is the `api.*.test.ts` contract files** — now
  **five**, with `api.proof-standing.test.ts` added at `cbf163e` — which
  `readFileSync` the Python source off disk and assert the wire field names,
  route signature and enum members still match. That catches drift in *names*,
  not in *behaviour*.
- The backend suite is the stronger half, because it runs the real Python
  against a real SQLite database. But SQLite is not Postgres and synthetic rows
  are not evidence.
- **No session has ever started the backend, pointed the frontend at it, and
  opened a real case.** Combined with the standing flags already recorded below
  — half two has only ever run against synthetic ledgers, and the alembic
  migration has never been applied to a real database — this is the largest open
  risk in the project and it is not a code defect. (The third item that used to
  be listed here, the browser gate, is no longer one: it ran green at `e655a0a`.)
- **STANDING and now sharper at `4e13821`, and a different kind of debt.**
  `POST /api/financial/files/{file_id}/admit` has **no TypeScript caller at
  all** — no `financialAPI` method, no contract test, no hook, no control. The
  service under it has 20 Python tests and the route itself 6, but it is
  reachable in practice only with a hand-made HTTP request. So it is not in the
  frontend debt above, because there is no frontend for it to be stubbed against.
  **A person cannot yet actually overrule the router**; the capability exists and
  the way to it does not.

  `4e13821` made that matter more, not less. Before it, the missing interface
  meant an unused capability. Now the gate refuses, so on a live case a held file
  **cannot be processed at all** from the interface: the 409 comes back carrying
  exactly what a person would need in order to admit the file, and there is no
  screen that reads it or button that acts on it. The backend is complete and
  correct and the loop is not closed.

  **At `cbf163e` this is no longer "next after chunk 3". Chunk 3 is done, so it
  is simply next**, and it is the only thing between item 8 and done. Item 8 must
  not be described as complete without it.

**Neil's ruling: he will test a full working version himself when the system is
ready, and the build continues in the meantime.** So do not re-litigate this. Do
**not** report green gates to him as though they settled whether something
works. When a unit lands, say what was verified and by what means.

**Confirmed by reading the source at `4e13821`: the ingest-to-ledger path exists
end to end, so that test is possible when he wants it.** `docker-compose.yml`
brings up Postgres 16 on 5434, Neo4j, Redis, ChromaDB, and the evidence engine
with its own migration step. The backend exposes `POST /api/financial/precheck`
and `POST /api/financial/ingest` (`routers/financial_ingest.py`) and `GET
/ledger`, `/runs`, `/decisions` and — since `cbf163e` — `/proof-standing`
(`routers/financial_ledger.py`). The frontend
routes `FinancialPage` at `/financial` (`app/routes.tsx:162`) with **seven** tabs
wired — ledger, held out, attempts, decisions, transactions, counterparties,
trends. The first four read Postgres and the last three read the graph. The
entry point for data is on the evidence side: `ProcessHoldDialog` renders
`SendToLedgerDialog`, which calls `usePrecheckFile` then `useIngestFile` from
`hooks/use-ledger-ingest.ts`. **The one known gap for a first real run is
`alembic upgrade head`,** which has never been applied from a session.

---

## The previous sessions, in brief

**`e655a0a`, the decisions screen — chunk 1 of item 8.** Nine files, 1,099
insertions, 18 deletions, frontend only. `DecisionsTable.tsx` (234 lines, 16
tests), `DecisionsPanel.tsx` (117 lines, 14 tests), a seventh tab on
`FinancialPage`, `"decisions"` added to the `mainView` union, and the
invalidation in `use-row-adjudication.ts`. Four things the panel had to get
right, each still pinned by a test: the heading comes from
`describeDecisionPage(page)` and **never** from the row count, because a sentence
composed from `decisions.length` says "12 decisions" over the first twelve of two
hundred; a page past the end must **not** render the empty state, because
"nothing has been decided" and "you have paged past the decisions there are" call
for opposite next moves; the panel deliberately does **not** carry the sibling
`count-disagreement` warning, pinned negatively, because this endpoint pages by
design and the warning would fire on every case with a history; and
`changedStoredState` is three-valued, so null renders as "not recorded" and never
as "no".

That session also wired `use-row-adjudication.ts` to invalidate
`["financial-decisions", caseId]` alongside the ledger's key, gated on a
`decisionWasRecorded` predicate so a response reporting no decision does not evict
a good page. **It is still the only writer wired to this key.** Supersession,
restore, purge and reclassification all append to the same log server-side and
none has a mutation hook in this build; neither does admission, whose service has
no TypeScript caller at all. Each closes its own half when it lands, and the
hook's docstring records this.

Its lasting lesson: **the browser gate's "unrunnable" entry in this file was
false, and cost nothing to disprove.** The claim carried a specific number
("roughly 700M") that was never measured, and then stood unchallenged for several
sessions, carried forward each time as though verified. **A figure in this file
that was estimated rather than measured must say so.** Both replacement figures
have since been wrong in turn — see the disk note, which is now measured every
session.

**`62ff2de`, the decisions hook.** Two files, 505 insertions, frontend only.
`use-case-decisions.ts` (110 lines) plus 395 lines and **14 tests**. Four calls
in it were decisions, not defaults, each recorded in its own docstring: it caches
under `["financial-decisions", caseId, params ?? null]` and **not** under the
ledger's prefix, because the log is append-only and outlives its subjects (a
purge writes its decision then deletes the row, and the log covers subjects that
were never ledger rows, such as `evidence_file`); the page envelope is handed
back **whole**, because `total` and `truncated` are on the envelope and a hook
returning only `decisions` would throw away the fact that a history was cut
short; **no `placeholderData` and no polling**, because holding the previous
page's rows under the new page's heading is exactly the quiet misstatement this
part of the product exists to prevent; and `limit`/`offset` are guarded with
`!== undefined` so `0` reaches the wire instead of being dropped by truthiness.

Two traps found then, both worth more than the commit. **A query with a live
observer clears `isInvalidated` as soon as the refetch it triggered succeeds**,
so a test reading `getQueryState(key)?.isInvalidated` fails against a mounted
hook; `use-row-adjudication.test.tsx` gets away with it only because the keys it
seeds have no observer. **Assert the observable refetch (fetch call count 1 to 2)
instead of the flag.** And **the bash working directory resets to the session
root, and `npx` then silently does the wrong thing**: `npx tsc -b --force` and
`npx eslint .` ran against an almost-empty directory, returned clean, and were
reported to Neil as passing gates. Three rules follow: `cd` with an absolute path
in the same invocation every time; run `./node_modules/.bin/...` directly, never
`npx`; and never read an exit code through a pipe (`${PIPESTATUS[0]}` came back
empty) — redirect to a file and read `$?`.

**One fact established then that is not about that commit.**
`explain_balance_failure` **has no production writer.** The enum, the model, the
migrations and the tests all name it; nothing in `services/financial/` records
one. Every other member has a writer: `admission.py:150`, `documents.py:654`,
`duplicates.py:577/643/783`, `quarantine.py:680/745`. This is **not** a defect —
the member is in the vocabulary, the database accepts it, and
`decision-format.ts` gives it words because a screen must be able to read one if
it appears — but a live case cannot currently produce one, so **its absence from
a case is not a bug in the panel.** Whether a writer is wanted is a question for
Neil when the balance-failure work comes up.

**`71d859d`, the words for the decision vocabulary.** Two files, 784 insertions,
frontend only. `lib/decision-format.ts` (420 lines) beside `ledger-format.ts`
and `run-format.ts`, whose shape it follows, plus 364 lines and **28 tests**.
Exports `DECISION_SOURCE`, `DECISION_ORDER_IS_NOT_SEQUENCE`,
`readDecisionSubject`, `readDecision`, `readDecidedBy`, `formatDecisionTime`,
`describeDecisionPage`. Narrowing goes through `narrow` from `ledger-format.ts`,
so an unrecognised word is named, marked, never blank. Four things settled there
that later work must not undo:

- **Every phrase was written from the writer, not from the member's name**, and
  two of the eight read backwards from theirs. `admit_financial_document` does
  **not** mean a document entered the ledger: it means a file the router held
  back, because indexing a statement as prose turns its figures into searchable
  text no total can be traced to, was sent to that text pipeline anyway by a
  named person against the router's finding. `explain_balance_failure` is
  **not** a disposition: it records why a statement's own figures do not add up
  and changes no status. Both senses are pinned by named tests so a tidy-up
  cannot reverse them quietly. Source: the `AdjudicationDecision` docstring in
  `backend/postgres/models/enums.py`, corroborated against the actual writers.
- **`changedStoredState` is three-valued.** False means the entry recorded a
  view and moved nothing; **null means this build cannot read the member.**
  Collapsing null into false reports an unknown decision as having changed
  nothing, which is the reassuring answer and the one it has not earned. Six
  members change stored state; the two above do not, asserted as a sorted list
  so a third would fail.
- **`by_machine` is read off the record and never re-derived.** The backend
  compares once, in `decision_log.to_record`, case-insensitively against
  `reconciliation@loupe.invalid`. A reader that got it wrong would show software
  moving a document as though an analyst had. A named test pins it.
- **`describeDecisionPage` never claims "showing all" from `truncated` alone.**
  `truncated` is `offset + len(decisions) < total`, which looks **forward only**
  and is false on the last page even though pages came before it. "Showing all N
  decisions" is claimed only when `offset === 0 && !truncated`.

Colour: `DECISION_VARIANT` follows the ledger's so the same event reads the same
on both screens. `warning` is used for **no** member, because the ledger reserves
it for "this build cannot read this value". `purge_duplicate` takes solid
`destructive` as the only member that cannot be undone. The maps are typed
`Record<AdjudicationDecision, ...>` because `Badge` falls through to its loudest
variant for a missing key, so a forgotten member would render as the most
important thing on screen; the compiler catches it instead. There is deliberately
no `needsAttention`: every record is a decision somebody already took, and which
of them matters is a question about the case, not about the word.

**`0fa07d5`, the wire shape and the client call.** Two files, 618 insertions,
frontend only. A new "Reading back what was decided" section in
`features/financial/api.ts` (+208): `ADJUDICATION_SUBJECTS` and
`ADJUDICATION_DECISIONS` as `as const` arrays, `DecisionRecord` (15 fields),
`DECISION_FIELDS`, `DecisionsResponse`, `CaseDecisionsParams`, and
`getCaseDecisions`. Plus `api.decisions.test.ts` (410 lines, 25 tests), which
reads the Python with `readFileSync` and asserts the wire still is what the
TypeScript believes.

Three calls from that session that still bind: **the limit and offset bounds are
not mirrored on the frontend** (`DEFAULT_DECISION_LIMIT` 100 and
`MAX_DECISION_LIMIT` 500 stay in `decision_log.py`; a bound written down twice
drifts the moment one side moves, so the client sends an over-cap limit as asked
and trusts the limit the response reports); **zero is sent, not dropped**
(`!== undefined`, never truthiness — a `if (params.limit)` would swallow
`limit: 0` and `offset: 0` and turn an explicit request into a default); and
**`subject_type` and `decision` are typed `string` on the record**, matching
`LedgerTransaction.ledger_status`, with narrowing pushed to the edge — which is
`decision-format.ts`, landed at `71d859d`.

Two traps in writing contract tests over Python, both still live for anyone
adding one: **`decision_log.py` declares `as_dict` twice** (on `DecisionRecord`
and on `DecisionPage`), so the `pythonBlock(source, header)` idiom from
`api.runs.test.ts` finds the first one both times — key the scan off the class
first. And **the route docstring contains the literal `` le= ``** in the sentence
explaining why a `le=` is absent, so a naive `not.toMatch(/le=/)` fails on the
prose justifying the assertion; scope it to the `limit` parameter. Also:
`api.runs.test.ts` extracts keys with `/"([a-z_0-9]+)":\s*self\./g`, which misses
`DecisionPage`'s list comprehension; `api.decisions.test.ts` uses the looser
`/"([a-z_0-9]+)":/g` scoped to the `as_dict` slice.

**`2eefc4d`, the HTTP read over the adjudication log.** Two files, 309
insertions, 5 deletions, backend only. `GET /api/financial/decisions` on
`routers/financial_ledger.py`, with `case_id` required and `subject_type`,
`subject_id`, `decision`, `limit`, `offset` optional; 8 tests in a new
`GetCaseDecisionsTests` class.

**The route is on the ledger router and not the adjudication one, and that was
the decision of that session.** `routers/financial_adjudication.py` is the
obvious home because the two routes that *write* these records live there, but
`_adjudication_case_permission` resolves **every** route to `("case", "edit")`
unconditionally and its comment says why: anything added there inherits the write
bar. A read dropped in would take a permission it does not need *and* would make
that comment false. `routers/financial_ledger.py` resolves to `("case", "view")`
unconditionally on the stated grounds that none of its routes write, which stays
true of a decisions read. (`routers/financial_reconciliation.py` was read as the
third pattern: it resolves by HTTP method, which is right for a router serving
both a read and a recompute and wrong for either of the other two, each of which
is uniformly one thing.) **Both comments stayed true and neither had to change.**
The ledger router's module docstring did change — it opened "Two reads of the
same store" and now says three, with the router-choice reasoning written into it.
*Reversed by:* the decisions read ever needing something from the adjudication
router that the ledger router does not have.

Three calls from that session worth keeping: **no `ge=1` or `le=` on the `limit`
`Query`**, because the service refuses a low limit and caps a high one and a
`le=` would turn a servable request into a 422; **the page is handed back whole
as `page.as_dict()`** rather than rebuilt field by field, because a hand-built
response is one careless edit away from silently dropping `truncated`; and **the
two existing routes were not refactored** to use the new `_parsed_member` helper,
because changing working routes with tests pinned to them to save four lines is
churn. The reason is in the helper's own docstring so nobody "tidies" it.

No wiring change was needed: `financial_ledger_router` was already registered in
`routers/__init__.py` and `main.py`, and that the new path is actually served was
verified by printing `router.routes` rather than assumed.

**That session is also where the traceback count in this file was found to be
wrong.** It had read "six" for several sessions. The run gave eight; the baseline
tree at `dfb9715` was run and counted as well and also gave eight, so the extra
two are not a regression. The corrected account is under Gate baselines above.


**`a40bb61`, the first half of chunk 1 of item 8: a reader for the adjudication
log, scoped to a case.** Three files, 1,112 insertions, no deletions, backend
only. `adjudications` had had production writers since `150084a` and **no reader
at all**, so every quarantine, release, purge and machine reclassification
written since then was sitting in a table nothing could read back.
`decision_log.py` (new, 372 lines) added `list_case_decisions` plus
`DecisionRecord`, `DecisionPage`, `DecisionLogError`, `DEFAULT_DECISION_LIMIT`
(100) and `MAX_DECISION_LIMIT` (500), with 37 tests.

**Item 8 was split into three there, and the order was decided by reading the
source rather than by preference.** The wiring plan gives item 8 as
"`assign_proof_class`, `requires_adjudication`, `record_admission`, the decisions
surface", which is three separable things. (1) **The decisions surface** first,
because it is data that exists on disk today and is unreachable, so it has the
shortest path from nothing to something worth having, and it is a read, so it
cannot break a write path. (2) **The admission path**, which is what gives
`record_admission` a caller — it has none today, and
`hooks/use-guarded-process.ts` offers `release` and `dismiss` with no "send the
held file through anyway" action at all. (3) **Proof class and
`requires_adjudication`** deliberately last: proof class is already computed and
already rendered, and what is missing is the *explanation* of what a class means
and what an adjudication changed about it, which is easier to write once the
decisions surface exists to point at. *What would reverse this order:* Neil
wanting the admission override in front of a user sooner than a history nobody
has asked to see yet.

**Why `decisions.history()` could not be the reader**, which is the fact the whole
chunk turns on and is not obvious from the function's name.
`history(session, subject, subject_type)` takes a **loaded subject object** and
filters on `subject_type` and `subject_id`. **It never filters on `case_id`.** So
it answers "what happened to this row" and structurally cannot answer "what has
been decided in this matter". It also cannot bound a route: subject ids are
unguessable, but a caller who has already seen one can name it against any case
at all, and `history` would answer. `list_case_decisions` therefore puts the case
**in the filter rather than checking it afterwards**, the pattern
`quarantine_row.find_case_transaction` already uses and states the reason for: a
subject in another matter is indistinguishable from one that does not exist.

**Three things were decided there, not assumed,** each recorded at length in the
module docstring too. *Ordering:* `subject_sequence` is per subject, so comparing
one subject's 3 with another's 1 means nothing, and `created_at` is Postgres
`now()`, which is **transaction start time**, so events written in one transaction
share it exactly. The order is `created_at DESC, subject_type, subject_id,
subject_sequence DESC` — newest first at the resolution the timestamp actually
has, authoritative within any one subject, and **total**, so paging is stable and
a row cannot appear on two pages. The docstring explicitly refuses to claim that
two events about *different* subjects sharing a timestamp happened in the order
shown. *Bounding:* this **diverges from `transaction_query.list_transactions`,
which is unbounded**, for a specific reason — `reclassify_document` is written by
the reconciliation stage on every pipeline run, so the log grows without any
person deciding anything, and the cost of an unbounded read is set by how often
the pipeline ran. `total` is counted over the **same filters**, so a filtered page
describes its own population. *`by_machine`:* derived from the actor address
against `documents.RECONCILIATION_ACTOR_EMAIL` (`reconciliation@loupe.invalid`)
rather than stored, because a second home for the same fact drifts; **surfaced
rather than left to callers**, because a reader that gets the comparison wrong
shows a machine's reclassification as a person's judgement, which is the most
misleading thing this log could be made to say; matched case-insensitively and
**on equality**, so an address merely *containing* the machine's is not the
machine's. The `RECONCILIATION_ACTOR_EMAIL` import is deferred into the function
because `services.financial.documents` is heavy.

**Two smaller calls, so they are not re-litigated.** `to_record` is public in the
module but deliberately **not** in the package `__all__`: at package level a bare
`to_record` is vague, `transaction_query` already contributes a `to_view` there,
and `tests/test_financial_exports.py` states in its own docstring that the guard
is *module reachability*, at least one name per module. And the constants are
`DEFAULT_DECISION_LIMIT` / `MAX_DECISION_LIMIT`, not `DEFAULT_LIMIT` / `MAX_LIMIT`,
because `services.financial.__init__` is a flat surface shared by fifty-one
modules and a bare `DEFAULT_LIMIT` there would read as the package's limit for
anything paged.

**What the 37 tests pin,** grouped by the claim rather than the function. *The
case bounds the read:* another case's decisions are absent, **naming another
case's subject id returns nothing**, an empty case is a page and not an error, a
read with no case is refused. *The order says only what it can support:* newest
first; events sharing a timestamp on one subject come back with the reversal
leading; six events across two subjects on a single shared timestamp, paged two at
a time, yield six **distinct** ids, which is the property that would break first
if the order were not total; the same read twice returns the same order. *Paging
cannot mislead:* `total` counts the population and not the page, `truncated` is
true and false in the right places, an offset past the end is empty with a true
total, a limit over the cap is **capped not refused**, and a limit of `True` is
refused because `isinstance(True, int)` and a boolean reaching a `LIMIT` clause is
a silent 1. *A machine's decision is not read as a person's:* both directions,
plus the case-insensitive match and the substring near-miss. Two fixture routes
were used on purpose: most tests write through `decisions.record`, so what is read
back is what the **real writer** writes, while the ordering tests insert
`AdjudicationEvent` rows directly because `created_at` is a server default and
those tests are precisely about which timestamps events carry.

**`e64c2ca`, chunk 5 of the quarantine screen, which closed Phase 2 item 6.**
Eleven files, 718 insertions, 39 deletions, frontend only. Chunks 1 to 4b built
pieces and wired none of them: the dialog existed and no screen opened it, the
quarantined list existed and no tab showed it. This is the commit that connected
them. The financial page gained a **"Held out"** tab and **every ledger row
gained a button** offering the one change that row admits of, read from a single
place — `changeAvailableFor` in `lib/ledger-format.ts`, with `RowChange` and
`ROW_CHANGE_LABELS`. The action column on `LedgerTable.tsx` is drawn only when
`onAdjudicate` is given, so the general ledger and the held-out list share one
table without the general list growing a control it has no use for. Quarantine is
complete end to end: write path, localisation reader, and screen.

**`519895e`, chunk 4b of the quarantine screen.** Six files, 747 insertions, 9
deletions, frontend only. The list of rows a case is holding out of its own
totals, plus a column saying what put each one there: `readQuarantineGrounds` in
`lib/ledger-format.ts`, the grounds column on `LedgerTable.tsx` behind
`showQuarantineGrounds` (off by default), and `components/QuarantinePanel.tsx`.
**The open question — a conditional column on the existing table or a second
table — was settled in favour of the column by reading `LedgerTable.tsx`:** three
of its seven cells are correctness rather than presentation (the amount cell
marks a figure it could not scale, the balance cell says a running balance was
absent, every closed vocabulary renders an unrecognised member loudly), and a
second table would be a second copy of all three. **The copy is what drifts** —
not on the day it is written, on the day one of the three is corrected in one
place only. *Reversed by:* the quarantined list needing a cell the general list
has no use for. **The status column stays when the grounds column appears**,
because a row that is somehow not quarantined inside a quarantined list is
exactly what a reader must be able to see. **`QuarantinePanel` is its own
component and not `<LedgerPanel params={{ ledgerStatus: "quarantined" }} />`**
because the empty state means the opposite thing: zero rows there means rows are
sitting outside the filter uncounted, zero rows here means nothing is being held
out, which is a good result. A test asserts the borrowed sentence is *not*
present. The rest of its rules are under "And on the frontend" below.

**`66d1e67`, chunk 4 of the quarantine screen.** Two files, 1,103 insertions,
frontend only. Added `components/RowAdjudicationDialog.tsx` (523 lines) plus 28
tests — the first thing in the five a person can see and use. **Chunk 4 as agreed
was the dialog, the table and the panel in one commit; the dialog landed alone
and the rest became chunk 4b**, on measured size: the three chunks before it were
496, 765 and 644 insertions and the dialog alone was 1,103, so the whole of chunk
4 would have been roughly three times the largest thing in the sequence. **Which
of the two changes it offers is read off the row, not passed in** —
`ledger_status === "quarantined"` means release, anything else means set aside;
a verb prop would be a second copy of a fact the row states and the two can
disagree (*reversed by* a screen needing to offer a verb the row does not imply,
which none in the plan does). **A status this build cannot read gets neither
verb**, because the verb is derived from the status and a guess would send a
write nobody asked for. **Non-admitted rows are not screened out:** a superseded
row is offered "set aside", the ledger refuses, and the refusal is shown as the
ledger's own answer rather than pre-empted in the browser, because a second copy
of the ledger's rules in the browser is a second thing to keep in step. **The
empty-`reason` guard deferred from chunk 3 landed here** and is not a rule
invented in the browser: every writer refuses a blank reason, in four separate
places, three of them with an ordinary refusal, so disabling the button spares a
round trip whose only answer is no. The guard is **at least as strict as the
database's own and never looser** — `trim` treats more strings as blank than the
stored check does, so nothing it accepts can hit a constraint the person cannot
see; the asymmetry is deliberate, do not "fix" it. **Whether the row moved is
reported from `applied` alone**, and where `applied` and the outcome word
contradict each other the contradiction is shown rather than settled. **The
statement-balance fact is said here or nowhere:** `rescues_period` is in this
answer and no other, so it is rendered whenever the reading has anything to say
and suppressed only when there is no fact about a statement at all. Two test
traps found the hard way: **a defaulted parameter cannot express "no case is
open"** (use an options object and `"caseId" in options`), and **`isPending` is
not true synchronously after `fireEvent.click`** (wrap in `await waitFor`).

**`610df9b`, chunk 3 of the quarantine screen.** Two files, 644 insertions,
frontend only. Added `hooks/use-row-adjudication.ts` (119 lines) plus 17 tests.
**One mutation over both routes, not two hooks:** `quarantineRow` and
`releaseRow` take the same three parameters and answer with the same shape, so
the verb travels in `variables.action`; two hooks would hand one button two
`isPending` flags and two `data` objects, and the bug that follows is a screen
reading the answer to the call it did not make (*reversed by* a screen needing a
quarantine and a release in flight at once, which none in the plan does). **A
refusal is a resolved promise,** so `isSuccess` means the question was answered
and `data.applied` is the fact a caller wants. **The answer is read whole before
it is handed back** — `mutationFn` maps through `readRowAdjudication`, so `data`
and the promise from `mutateAsync` are both a `RowAdjudicationReading`, which
matters because `rescues_period` is said in that response and nowhere else and a
caller handed the raw object can render the outcome and lose it. Safe to compose
inside `mutationFn` because the readers cannot throw. **`reason` is passed
through unexamined,** settled by reading `routers/financial_adjudication.py`
(`reason: str = Body(..., embed=True)`, required, no `min_length`) and
`quarantine_row.py`, which does not check it either; the guard was left for the
dialog, where the field is filled in, and landed at `66d1e67`. **A missing
`caseId` rejects rather than asserting,** differing from `use-ledger-ingest.ts`
on purpose because this path changes what a case's totals count. One deviation:
the plan said invalidate on `applied` alone, and it invalidates on `applied ||
outcome.changedTheRow === true`, because refetching when nothing moved costs a
request while not refetching when something did leaves a row on screen in a list
it has left, and the costs are not symmetrical (*reversed by* the disagreement
turning out to be reachable in normal operation rather than only across
versions). What a person is told about whether the row moved still comes from
`applied` alone. Two testing decisions worth keeping: the tests stub
`globalThis.fetch` rather than `vi.mock("../api")`, and invalidation is checked
by seeding a real `QueryClient` and reading `getQueryState(key)?.isInvalidated`
rather than by spying on `invalidateQueries`, because a spy goes on passing after
somebody changes the key the reading side uses.

**`19bffae`, chunk 2 of the quarantine screen.** Two files, 765 insertions,
frontend only. Added `lib/adjudication-format.ts` (414 lines) —
`readRowAdjudicationOutcome`, `readRescueOutcome`, `readAdjudicationReason` and
`readRowAdjudication` composing all three — plus 31 tests. It exists to stop a
screen doing three things, each settled by reading `quarantine_row.py` and
`routers/financial_adjudication.py`. **Treating the outcome as a success flag:**
only two of the six outcomes leave the happy path as HTTP errors, so a refusal is
an ordinary 200 carrying the refusal and the outcome is the content. **Labelling
`reason` as the person's stated grounds:** it is one field carrying four
different things and none of them is what the person typed — the system's rescue
note on a quarantine, `str(exc)` on a refusal, a canned sentence on `unchanged`,
and `None` on a release, because `release_case_row` puts the person's words on
the record and defaults `reason` out of the response.
`ADJUDICATION_REASON_IS_NEVER_THE_PERSONS` is the sentence to show beside it.
**Rendering `false` and `null` alike on `rescues_period`:** four presentations and
not three, because `null` on a quarantine means the question was asked and could
not be answered, while `null` on any other outcome means no row came out so it
never arose. Two decisions inside it: `ledger_status` and `quarantine_reason` are
**not** re-narrowed against a new provenance string, against the letter of the
chunk plan, because `_current()` copies both straight off the stored row so "it
came from the ledger" is the true sentence (*reversed by* a backend change that
computes either rather than copying it); and `changedTheRow` is `null` for an
outcome word this build cannot read, with a disagreement against the wire's
`applied` reported through `appliedDisagreesWithOutcome` rather than resolved
(*reversed by* nothing short of `applied` leaving the wire). One inconsistency
found and deliberately not fixed: `UNRECOGNISED_VARIANT` is `"warning"` in
`LedgerTable.tsx`, which is where the rule is actually written down, and
`"outline"` for the same case in `run-format.ts`. New code follows `LedgerTable`.
It is one line in `run-format.ts` if the ledger's rule is meant to be global, and
a question for whoever next touches the runs screen.

**`1894fc4`, chunk 1 of the quarantine screen.** Two files, 496 insertions,
frontend only. Added the two calls (`quarantineRow`, `releaseRow`), the
`RowAdjudication` shape, `ROW_ADJUDICATION_OUTCOMES`, `ROW_ADJUDICATION_FIELDS`
and `RowAdjudicationParams`, plus `api.adjudication.test.ts`. Three things from
it that the rest of the screen rests on. **The wire fields are typed `string`,
not unions**, because a backend one version ahead can send a member this build
has never heard of and a union would let it through while claiming it had been
checked; narrowing is a runtime job, which is what chunk 2 then did. **`reason`
is required on both calls with no default**, because the backend requires it on
both routes. **Sixteen tests, seven of which read the Python off disk** and
assert the enum members match `ROW_ADJUDICATION_OUTCOMES`, the `as_dict()` keys
match `ROW_ADJUDICATION_FIELDS`, both routes still take `case_id` as a `Query`
and `reason` as an embedded `Body`, and the set of outcomes `_respond` raises on
is exactly `{not_found, write_failed}` — so a future change that starts throwing
on a refusal fails there rather than silently turning a shown refusal into a
thrown one.

*Why the screen and the write path were built as one unit:* a read-only screen
would be a permanently empty state by construction. The only production writer of
`ledger_status = "quarantined"` is `quarantine_case_row`, reachable only over the
POST route, so a screen that could only read would have nothing to read. *What
would reverse it:* a production path that writes computed grounds at ingest,
which is Phase 2 item 8.

**`35cc6be`, the arithmetic half of Phase 2 item 6.** Six files, 1,211
insertions. Built `services/financial/localisation.py` — the reader that turns
rows and periods already in the database into the inputs `would_rescue` and
`localise` want, both of which were fully written, fully tested and unreachable
before it. `quarantine_row.py` gained `_rescue` and `RowAdjudication` gained
`rescues_period`. Three rules from that unit that the screen work depends on:
**the chain is walked over `admitted` rows only**, because the residual it is
compared against sums admitted rows; **the identity is recomputed, never read off
the stored `reconciliation_status` column**, which on a live case is usually
`not_attempted`; and **the system refuses nothing and warns about nothing** when a
removal makes a period balance, it only records the fact, because that balance is
an arithmetic necessity whatever the row was and so is not evidence on its own.
The `rescues_period` authorship rule and its recorded gap are under Standing
decisions.

**`74d9bdf`, the run reaper test race.** No build item moved; one test file
changed. The suite was intermittently failing with `no logs of level WARNING or
higher triggered on services.financial.run_reaper` and the state file was
claiming green. Cause: `reap_stale_runs_forever` runs its sweep on a worker
thread via `asyncio.to_thread`, and **everything the loop says about a sweep is
logged afterwards, back on the event loop.** The harness released the waiting
test from the worker thread, so the test could cancel the loop before the line it
asserted on was written. Measured, not reasoned about: the old harness failed
**5 runs in 30**, the fixed one passed **30 in 30**. Four assertions rode on the
race; a fifth used `assertNoLogs` and so never failed — it had simply stopped
testing. Fix is in the harness only; no production code was touched. The general
lesson is in Durable facts.

**`dfcef2b`, Phase 2 item 7, reconciliation.** Seven files, 2,126 insertions.
Built `services/financial/reconcile_case.py` (the driver `reconcile_period` never
had, plus the read) and `routers/financial_reconciliation.py` (GET reports the
stored column, POST recomputes). The finding that shaped it: **`reconcile_period`
had never run in production**, its only caller being an unwired module, so every
period sat at `not_attempted` for the life of a case. **All the durable rules
from that unit are in "The reconciliation subsystem's own rules" below** and are
not repeated here.

---

## Durable facts, kept so no one rediscovers them

The bootstrap, the baselines, the storybook limitation and the git procedure all
live in **`CLAUDE.md`**. Deliberately not duplicated here.

### Learned recently, newest first

These accumulate. The heading used to say "new this session", which stopped being
true the first time a session added to the list instead of replacing it.

- **There is already a Playwright install on `/dev/shm` and it must be reused,
  not reinstalled.** `/dev/shm/pw-inspiring-peaceful-brown` is 928M, left by an
  earlier session, world-readable and executable. Point at it with
  `PLAYWRIGHT_BROWSERS_PATH` and the browser gate runs. **Installing a fresh one
  is no longer possible** — the headless shell is 106.4 MiB and there was 79M
  free at the end of this session. Verify before relying on it:
  `test -x /dev/shm/pw-inspiring-peaceful-brown/chromium_headless_shell-1208/chrome-linux/headless_shell`.
  Full instructions under "How to run the browser gate".
- **`--fileParallelism=false` is not required for the browser project.** This
  file has said since `4e13821` that it was. At `cbf163e` the gate was run
  without it and passed 2 files / 4 tests in 3.45s. It is a **remedy for a flake,
  not a standing requirement**, and carrying it as a requirement made the gate
  look more fragile than it is.
- **A Python route signature cannot be read with an unbounded regex, because a
  `try:` inside the body matches as a parameter.** The contract tests scrape
  `^ {4}(\w+):` to list a route's parameters. Run against the whole route body
  that returns `["case_id", "db", "try"]`. Slice from `async def` to the first
  `\n):` first, and assert that the slice was found so a reformatted signature
  fails loudly instead of silently matching nothing.
- **`financial_source_documents` has a UNIQUE constraint that catches fixtures
  building several documents for one case.** A test that inserts two rows meaning
  to differ only by proof class dies at the insert, not the assertion. Vary the
  identifying column, not just the class.
- **A census must report every enum member, including the empty ones.** Written
  down because the first draft of `proof_standing.py` returned only occupied
  classes and it read as correct. *"No p3 documents here"* and *"nothing looked
  at p3"* are different facts about a case, and an absent key spells them the
  same way. `for member in ProofClass` is pinned by a contract test for this
  reason.
- **`git` path arguments match nothing unless the command begins with an
  absolute `cd` to the repo root — and it fails silently.**
  `git diff -- backend/routers/evidence.py` run with the working directory at
  `backend/` returned **empty output and exit 0**, while `git status` in the same
  session showed the file modified. Pathspecs are resolved relative to the
  current directory, so from `backend/` the path `backend/routers/...` simply
  does not exist. `CLAUDE.md` records that the bash cwd resets unpredictably;
  this is the form of it that produces a **wrong answer rather than an error**,
  and it very nearly meant committing a diff that had never been reviewed. Every
  git invocation gets `cd <repo root> &&` in the same command, including the
  read-only ones.
- **pytest is not in the documented bootstrap, and a plain run leaves a directory
  that cannot be removed.** The financial suite is `unittest`, but the evidence
  tests are pytest and are worth running whenever a service or router is touched.
  Install `pytest==8.3.4` and `pytest-asyncio==0.25.0` into the same `--target`
  as the rest. Then **always pass `-p no:cacheprovider --basetemp=/dev/shm/pt-$(id -un)`.**
  Without them, pytest writes `backend/pytest-cache-files-*`, then hits the
  workspace `unlink` denial trying to clean it up and dies in a
  `RecursionError` **after the tests have already passed** — so the run reports
  failure when nothing failed. The directory it leaves is empty, so `git status`
  does not show it and it cannot get into a commit, but `rm -rf` on it fails with
  `Operation not permitted` and it stays for good.
- **`decisions.record` requires a `decisions.Actor` and rejects a `User` with
  `DecisionError: actor must be an Actor, got User`.** `Actor` is a dataclass
  with `name`, `email` and an optional `user_id`. `admit_case_file` takes a
  `User` and converts internally, so a test written against that helper and then
  adapted to call `record` directly fails on exactly this.
- **`test_financial_exports.py` is fully automatic. There is no list in it to
  update.** This file said for several sessions that "a new module exported from
  `__init__.py` must be added there", and `CLAUDE.md` still says it. Reading the
  source settles it: the guard walks the package with the `ast` module and
  asserts that every module contributes at least one name to `__all__`, that
  every name in `__all__` resolves, that no name is exported twice, that no name
  is imported twice, and that no submodule declares its own `__all__`. Adding a
  module means editing **`__init__.py` only** — both the import block and
  `__all__` — and the guard then either passes or tells you exactly what is
  missing. 5 tests.
- **`evidence_files.stored_path` is `NOT NULL`** (`postgres/models/evidence.py:128`,
  `mapped_column(Text, nullable=False)`). So **there is no such thing as a
  pathless evidence row**, and a test that builds one dies at the insert with a
  constraint error rather than at the assertion. The condition that actually
  exists in production is a **resolver that cannot place the path** and returns
  `None` — a container whose mount differs from the one that took the upload.
  Test that instead.
- **`routers/evidence._resolve_stored_path` is already imported across routers,
  so importing it again is not a circular-import risk.**
  `routers/financial_ingest.py:33` does exactly that. It reconciles a stored DB
  path against host and Docker evidence-engine layouts, trying the markers
  `evidence-data/`, `data/evidence/` and `ingestion/data/` against
  `EVIDENCE_ROOT_DIR`, and **returns `None`** when it cannot. It is the right
  `resolve_path` to hand a service, and the reason such a service must never
  default that argument to "use the path as written": that works in development
  and fails quietly in a container.
- **`/dev/shm` does not start empty, and no free-space figure in this file
  survives a session.** It was 1.5G, then 398M, and is **244M free of 2.0G** at
  this head — the fall from 398M is this session's own `pylibs-*` directory plus
  pytest. It carries other users' leftovers,
  which cannot be removed from inside a session: a **928M Chromium directory**
  (recorded elsewhere in this file as 106.4 MiB, because that is the size of the
  *shell*, not the installed tree) and **five `pylibs-*` directories at 151M
  each**, one per previous backend session, this session's being the fifth. **So the pip bootstrap is 151M, not
  the ~463M this file claimed, and free space falls by 151M with every backend
  session that runs it.** Run `df -h /dev/shm` and `du -sh /dev/shm/*` before the bootstrap and
  before any Chromium install, and do not trust a free-space figure in this file.
- **The evidence-engine suite cannot be run in this sandbox at all.** Its
  `pyproject.toml` declares `requires-python = ">=3.12"` and the sandbox is
  Python **3.10.12**; `pytest` is also not installed and is not in the documented
  bootstrap. So a finding about engine behaviour — such as the native-file
  pre-stage above — is established **by reading the source**, and must be
  recorded as such rather than as something a gate confirmed.
- **The browser gate runs. Chromium is 106.4 MiB, not the 700M this file
  asserted.** With `PLAYWRIGHT_BROWSERS_PATH` and `TMPDIR` both on `/dev/shm`.
  Commands under **How to run the browser gate**, which at `cbf163e` changed to
  reusing an existing install rather than making one. The general lesson: **a
  number in this file that was estimated rather than measured has to say so**,
  because once written it gets carried forward as though it were verified.
- **The browser project's two files can race the single vite dev server, but
  usually do not.** When they do, one dies with `Failed to fetch dynamically
  imported module` naming whichever file lost. It is not a defect in that file:
  it passes alone, a warm cache does not help, and the named file's import graph
  reaches nothing that changed. `--fileParallelism=false` clears it. **It is not
  needed by default** — at `cbf163e` the gate passed without it in 3.45s — so
  reach for it only when that error actually appears.
- **A `describe` block added to `FinancialPage.test.tsx` must mock the new
  panel's hook, or the page renders green with a dead tab behind it.** Unmocked,
  the panel's hook reaches for a `QueryClientProvider` the page render does not
  supply and throws — and **the panel's own `ErrorBoundary` catches the throw**,
  so nothing fails and nothing is on screen. The existing per-tab blocks all
  mock theirs for this reason; follow them rather than discovering it again.
- **`selectTab` in that file uses `fireEvent.mouseDown`, not `click`.** Radix
  tab triggers change on `mousedown` and have no `onClick`. A `click` silently
  does nothing and the assertion that follows fails on the wrong thing.
- **Adding a tab breaks three assertions in `FinancialPage.test.tsx`, and one
  docstring.** Two `getAllByRole("tab")` length checks and one `toEqual` over
  the tab names. The docstring above the strip test states how many tabs read
  Postgres versus the graph, and **is part of the change** — a comment left
  contradicting the code beneath it is worse than no comment.
- **`mainView` in `financial.store.ts` is deliberately excluded from the
  persisted slice, so a new member needs no migration.** Confirmed by reading
  the store, not assumed. This is why the seventh tab cost sixteen lines rather
  than a versioned migration.
- **`TMPDIR` must be moved to `/dev/shm` as well as `--target`, or pip fails
  with `[Errno 28] No space left on device` even though the target has room.**
  This file previously recorded only the `--target /dev/shm/pylibs-$(id -un)`
  half, and that half alone still fails: pip builds and unpacks in `TMPDIR`,
  which defaults to `/tmp` on the root filesystem, and the root filesystem is
  99% full. The whole install aborts having written nothing, so the failure
  looks like the package list being wrong rather than a disk problem. The
  working form is the bootstrap line with
  `TMPDIR=/dev/shm/tmp-$(id -un)` in front of it — and the directory has to
  exist first. Note the error names `[Errno 28]` and **not** the path that ran
  out, which is what makes it misleading.
- **The expected-traceback count in the backend run was wrong in this file for
  several sessions, and the way it was wrong is worth remembering.** It said six;
  a `grep -c '^Traceback'` gives eight. Two causes, neither a regression. One
  logged failure prints **two** `Traceback` headers because it is a chained
  exception ("The above exception was the direct cause of the following
  exception"), so counting headers and counting failures give different numbers.
  And one traceback — the ingest router's injected `RuntimeError: database gone`
  — was simply never listed. **The method that settled it is the reusable part:
  when a count on stderr does not match this file, run the *baseline* tree at
  the previous head and count there too before assuming your own change caused
  it.** Both gave eight.
- **In this feature a panel test mocks the hook, not the network.**
  `vi.mock("../hooks/use-ledger-transactions", ...)` with a `vi.hoisted` factory,
  which is what `LedgerPanel.test.tsx` already does. What is under test is the
  panel's reading of a query result, not the query, and the query has its own
  tests. The `fetch` stub stays right for api and hook tests, `vi.spyOn` on the
  API object for component tests that assert what was sent. **Still never
  `vi.mock("../api")`** — it replaces the closed vocabularies the format readers
  import and every outcome silently becomes "unrecognised".
- **A prop type that excludes a field does not prove the runtime excludes it.**
  Where a component fixes a value a caller must not override, cast past the type
  in one test (`const params = { ledgerStatus: "admitted" } as never`) and assert
  the fixed value still went out. The compile-time guarantee protects this
  repository; the runtime one protects the screen from anything else.
- **Guard an enum once.** `api.ledger.test.ts` already reads the Python off disk
  and closes `QUARANTINE_REASONS` against the backend enum, so a new member fires
  there. A second copy of that assertion elsewhere is a second thing to update.
  What is worth testing separately is **coverage of a derived table** — a member
  present in the list but missing from a `Record<Member, T>` lookup would report
  as unrecognised while being perfectly recognised, and nothing else catches it.
  In TypeScript a `Record<Member, T>` already fails `tsc` on a missing key, so the
  test is the runtime belt to that braces.
- **A test helper cannot express "not supplied" with a defaulted parameter.**
  Passing `undefined` to `caseId: string | undefined = CASE_ID` **takes the
  default**, so a test written to prove the no-case rejection ran with a case
  open and failed on a real `fetch` instead — which reads like a broken harness,
  not like the test asserting the wrong thing. Take an options object and read it
  with `"caseId" in options`. This applies to every fixture that has an
  "absent" case to test.
- **`isPending` on a mutation is not true synchronously after the click that
  starts it.** It arrives a microtask later. Reading a disabled state straight
  after `fireEvent.click` fails with `expected false to be true`; wrap it in
  `await waitFor`. The same shape as the `result.current.data` trap below, and
  worth assuming for anything React Query sets.
- **`vi.spyOn(financialAPI, "quarantineRow")` works because the hook calls it as
  a property of the exported object,** confirmed by reading
  `use-row-adjudication.ts` before writing the test rather than by trying it.
  This is the right stub for a **component** test in this feature, because it
  lets the trimmed reason and the chosen verb be asserted directly
  (`toHaveBeenCalledWith({ caseId, transactionId, reason })`). The `fetch` stub
  stays the right one for **api and hook** tests. Both precedents exist; neither
  is `vi.mock("../api")`, which is still forbidden here for the reason below.
- **A `new Promise(() => {})` used to hold a mutation in flight must be typed.**
  `mockReturnValue(new Promise(() => {}))` infers `Promise<unknown>` and fails
  `tsc` against a `Promise<RowAdjudication>` return. Write
  `new Promise<RowAdjudication>(() => {})`.
- **`result.current.data` on a mutation is not flushed when
  `await act(async () => { await mutateAsync(...) })` returns**, even though
  `onSuccess` has already run. Three tests failed with `expected undefined to
  be ...` before this was understood, and the ones that passed did so only
  because they happened to have a `waitFor` in front of them. **Put every
  assertion on `result.current.data` inside `await waitFor(...)`.** Where the
  value matters, assert on what `mutateAsync` resolved to as well: the two are
  separate paths a caller can take, and either one carrying the raw wire object
  instead of the reading would let a fact be dropped silently.
- **`vi.mock("../api")` is the wrong tool in this feature and would fail
  quietly.** `api.ts` exports both the callers and the closed vocabularies
  (`ROW_ADJUDICATION_OUTCOMES`, `LEDGER_STATUSES`, `QUARANTINE_REASONS`) that the
  `lib/*-format.ts` readers import. Mocking the module replaces the vocabularies
  with nothing, every value then narrows against an empty list, and **every
  outcome in the file becomes "unrecognised" while the tests still look like they
  are exercising the real thing.** Stub `globalThis.fetch` instead; there is no
  `importOriginal` precedent anywhere in `src`.
- **Test invalidation by seeding a real `QueryClient` and reading
  `getQueryState(key)?.isInvalidated`, not by spying on `invalidateQueries`.** A
  spy asserts the argument the hook passed, so it goes on passing after somebody
  changes the key the reading side uses, which is the exact failure the test is
  there to catch. Seed both the key that should move and one that should not.
- **`routers/financial_adjudication.py` declares `reason: str = Body(...,
  embed=True)` with no `min_length`, and `quarantine_row.py` does not check it
  either.** So the ledger requires the field and requires nothing of its
  contents. Read before writing the hook, not assumed. A client-side non-empty
  rule is a rule the backend does not have, and belongs at the layer where a
  person fills the field in.
- **`mockResolvedValue(new Response(...))` hands every call the same object, and
  a `Response` body can only be read once.** The second call in a test dies with
  `TypeError: Body is unusable: Body has already been read`, thrown from inside
  `fetchAPI` at `api-client.ts:86` — **which reads exactly like the code under
  test having failed**, not like a bad stub. Cost a debugging round here. Use
  `mockImplementation(() => Promise.resolve(new Response(...)))` so a fresh
  response is built per call. `api.ledger.test.ts` never hit this because every
  one of its tests makes exactly one call; `api.adjudication.test.ts` compares
  the two routes, so several of its tests make two.
- **The repo is on a different filesystem from `/sessions`.** See the expanded
  environment note above: tens of gigabytes free on the repo mount, so the gates run
  even while `/sessions` reports zero bytes. The state file previously implied
  the whole environment was blocked; only the backend bootstrap is.
- **Two rows identical in amount, date and direction inside one document collide
  on the content hash.** `uq` is `(source_document_id, content_hash)` and the
  hash is computed from the reading, so a fixture making several rows on one
  period must vary something real — `description=f"row {i}"` is what the
  localisation and rescue fixtures use. Real statements tell such rows apart by
  narrative, so this is the schema being right, not the fixture being awkward.
- **A fixture making several periods for one document and account must vary the
  dates,** for the same reason: the uniqueness rule is
  `(source_document_id, account_id, period_start, period_end)`. A month counter
  is enough. And **a `closing=None` that means "the statement printed none" needs
  a sentinel default**, not `None` as the default, or the helper cannot tell "not
  supplied" from "deliberately absent".
- **`rescue_if_removed` is imported by name into `quarantine_row`'s namespace**
  (`quarantine_row.py:65`), so `patch.object(quarantine_row, "rescue_if_removed",
  ...)` is the working patch target. Checked by reading the import before writing
  the test rather than by trying and debugging.
- **`_UNANSWERABLE` in `quarantine_row.py` is
  `(QuarantineError, ReconciliationError, PeriodError, MoneyError)`.** Anything
  outside that tuple propagates and stops the quarantine.
- **`routers/financial_adjudication._respond` returns `result.as_dict()` with no
  response model,** so a new field on `RowAdjudication` reaches the interface with
  no schema work — **and breaks any router test asserting an exact response
  dict.** There are two, both named
  `test_the_service_is_called_with_the_row_case_actor_and_reason`. Expect to
  update them whenever that dataclass grows a field.
- **`services/financial/localisation.py` has no `__all__`.** The package surface
  comes from the import block and `__all__` in
  `services/financial/__init__.py`, and `tests/test_financial_exports.py` checks
  the module contributes at least one name. Confirmed again here.
- **The bootstrap in `CLAUDE.md` cannot complete: `/sessions` has zero bytes
  free.** Install to `/dev/shm` instead and carry `PYTHONPATH`. **Check
  `df -h /sessions` and `df -h /dev/shm` before assuming either.** The commands
  are written out here rather than referenced, because the section they used to
  be quoted from gets rewritten every session. Two steps, and **both** matter —
  `--target` alone still fails, for the `TMPDIR` reason recorded at the top of
  this list:

  ```
  mkdir -p /dev/shm/pylibs-$(id -un) /dev/shm/tmp-$(id -un)
  TMPDIR=/dev/shm/tmp-$(id -un) pip install --break-system-packages --quiet \
    --target /dev/shm/pylibs-$(id -un) <the seventeen packages from CLAUDE.md>
  ```

  Then every Python invocation carries:

  ```
  env PYTHONPATH=/dev/shm/pylibs-$(id -un) \
      PYTHONPYCACHEPREFIX=/dev/shm/pyc-$(id -un) \
      PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 python3 ...
  ```

  About twenty seconds and roughly 150M installed. Verify by importing
  `sqlalchemy` and `fastapi` and printing their versions before trusting it —
  a partial install fails later in a way that looks like a code error.
- **`PYTHONPYCACHEPREFIX` must not point at `/tmp` either.** `/tmp` is on the
  root filesystem, which is at 99% with about 120M free. Send it to `/dev/shm`.
  Same reasoning as `TMPDIR`: anything that defaults to `/tmp` in this sandbox
  has to be moved by hand.
- **A "no logs ... triggered" failure from a loop test is a scheduling race, not
  a broken loop.** Anything the reaper loop logs is written on the event loop
  after `asyncio.to_thread` returns, so a harness that releases from the worker
  thread can cancel the task first. Fixed for `run_reaper`; **the same shape
  would appear in any future test of a loop built the same way.**
- **A racing `assertNoLogs` does not fail, it stops testing.** Worth checking
  for wherever a negative log assertion sits over a thread hand-off.
- **To compare against an original file without dirtying the tree,** write
  `git show HEAD:<path>` into `/dev/shm`, add `/dev/shm` to `PYTHONPATH`, and
  run it by module name from `backend/`. The workspace denies `unlink`, so a
  scratch copy placed in the repo could not have been removed afterwards.
- **`unittest discover` needs the current working directory to be `backend/`,**
  and the bash cwd resets between invocations, so a run that reports a
  plausible-looking test count may still not be the suite you meant. Put the
  absolute `cd` in the same command every time.

### From the reconciliation session

- **`services/financial/__init__.py` re-exports a *function* named
  `reconcile_case`, which shadows the submodule of the same name.** This is a
  live trap for any test that needs the module object:
  `from services.financial import reconcile_case` binds the **function**, so
  `patch.object(that, "reconcile_period")` fails with "does not have the
  attribute". **And the obvious alternative fails identically** —
  `patch("services.financial.reconcile_case.reconcile_period")` resolves a dotted
  target with `getattr` before it falls back to importing, so it hits the same
  function. The working form is
  `import services.financial.reconcile_case` followed by
  `module = sys.modules["services.financial.reconcile_case"]`. **Any future
  module whose name matches one of its own exported callables has this problem.**
- **Use `session.expire(obj)` and never `session.refresh(obj)` to throw away an
  in-flight mutation.** `refresh` autoflushes first, which writes the thing you
  are trying to discard. This matters wherever a service mutates an ORM object
  and then hits a validation that can raise.
- **`reconcile_period` mutates before it validates.** It assigns
  `reconciliation_status` and then calls `_fits(...)`, which raises
  `LedgerOverflowError`. **`MixedCurrencyError` is different** — it is raised
  inside `evaluate_identity`, *before* any mutation. Any caller has to handle
  both, and only one of them leaves state behind.
- **Ordering a period list needs `nullslast()` and a secondary key on `id`.**
  `period_start` is nullable, and NULL ordering differs between SQLite and
  Postgres, so an ordering without it is not portable **and** not total. This is
  the same class of bug as the runs list needing a secondary sort on `id`.
- **`IdentityOutcome`'s field order is `status, totals, opening,
  printed_closing, computed_closing, delta, independent, unavailable_reason`,**
  with properties `is_balanced`, `was_attempted`, and `proves_completeness`
  (balanced **and** independent **and** `totals.is_complete`). Constructing one
  by hand in a test needs all eight.
- **`PeriodBounds` has exactly three constructors:** `printed(start, end)`,
  `derived(start, end)`, `absent()`. `supports_continuity` requires **both**
  bounds be `printed`.
- **`financial_statement_periods` has a second uniqueness rule for the undated
  case.** Beyond
  `uq_financial_statement_periods_document_account_period` on
  `(source_document_id, account_id, period_start, period_end)`, nulls are
  distinct inside a unique constraint, so there is a **partial** index
  `uq_financial_statement_periods_document_account_undated` on
  `(source_document_id, account_id)` `WHERE period_start IS NULL AND period_end
  IS NULL`. A fixture that makes two undated periods for one document and account
  will collide.
- **Four coherence check constraints tie each balance to its source**, of the
  form `(opening_balance_source = 'absent') = (opening_balance_minor IS NULL)`,
  for opening and closing, start and end. A fixture cannot set a source of
  `printed` and leave the amount null.

### From earlier sessions, still true

- **The `playwright install chromium` fix recorded here previously has stopped
  working, and the reason is different from the one it fixed.** The old failure
  was `os.tmpdir()` pointing at the full root filesystem, cured by
  `TMPDIR=/sessions/<session>/tmpdl`. The failure now is that **`/sessions`
  itself is full**, against a 179.6M download that then has to extract. It fails
  with `ENOSPC: no space left on device` **after** downloading 100%, twice, once
  per mirror, so it looks like a network problem and is not. **The free-space
  figure in this bullet was going stale every session, so it now lives in one
  place only: the disk note under Standing flags.** As of `e655a0a` it is still
  zero. **But `/sessions` is the wrong destination anyway:** send the install to
  `/dev/shm` with `PLAYWRIGHT_BROWSERS_PATH` and stage the download there with
  `TMPDIR`, and it costs 106.4 MiB. **As of `cbf163e` even that no longer fits**
  — 79M free — so the working move is to reuse the install another session left
  on `/dev/shm` rather than make one. See **How to run the browser gate**, which
  carries the current instruction; this bullet is history.
- **The repo mount is a different, much larger filesystem** —
  `/sessions/<session>/mnt/owl-n4j` is 461G with 39G free — but **do not stage
  the browser download there.** It is Neil's working repo, the workspace denies
  `unlink`, and the binaries would be left undeletable in his tree.
- **When only backend files change, say so and skip the browser project rather
  than reporting a stale figure as fresh.** Check with
  `git status --porcelain` before deciding.
- **`quarantine.py`'s two writers return the transaction, not the event.** So
  naming the adjudication that was just appended means reading it back:
  `history(session, transaction, AdjudicationSubject.transaction)[-1]`. Safe
  because `decisions.record` ends in `session.flush()` and `history` orders by
  `subject_sequence`, which is assigned, rather than by `id`, which is a random
  uuid4, or `created_at`, which two rows can share.
- **`quarantine_row.actor_from_user` builds a `decisions.Actor` from a logged-in
  user.** It uses `getattr` rather than importing the auth model, the same way
  `runs.py` deliberately does, so nothing under `services/financial/` gains a
  dependency on `postgres.models.user`.
- **`_current()` in the quarantine driver reads the row's attributes after
  `session.commit()`.** With `expire_on_commit=True` that triggers a refresh
  round trip. It works and is tested, but it is worth knowing before anyone
  moves the commit.
- **The permission templates define far less than the routers use.**
  `postgres/permissions.py` defines only `case:{view,edit,delete}`,
  `collaborators:{invite,remove}` and `evidence:upload`. **`evidence:process`
  and `evidence:delete` are referenced by existing routers and do not exist in
  the templates at all.** Do not assume a permission string is real because a
  router asks for it.
- **A component that throws for want of a provider does not fail a
  `FinancialPage` test — it vanishes.** Every panel on that page is wrapped in
  its own `ErrorBoundary`, which catches the throw and renders a fallback, so
  the suite stays green while the thing under test is dead. Mock every hook the
  page reaches for, and assert presence explicitly.
- **`tsc -b` alone is not enough after writing test fixtures.** Vitest does not
  typecheck. Use `--force`; the incremental build will otherwise skip a project
  it thinks is current.
- **The git ref file must be `Read` before it can be `Write`n.** `Write` refuses
  with "File has not been read yet" unless that exact path was `Read` earlier in
  the same session. Read it first; its contents are the old head.
- **`Edit`'s read precondition is inconsistent about slices, so do not plan
  around it.** Try a slice on a large file — it may be enough — and fall back to
  a full read rather than assuming either way.
- **The vitest unit project takes about 80 seconds** at 67 files. Not a hang.
- **Never read a "no tests" result as green.** A stale vite cache path, a
  missing chromium and the `unlink` denial all produce it.
- **Radix tab triggers activate on `mousedown`, not `click`.** `fireEvent.click`
  leaves the tab where it was, and **every assertion after it silently describes
  the previous tab** — the test still passes, it just tests the wrong panel.
- **`TooltipProvider` is mounted app-wide at `app/providers.tsx:13`,** so any
  page test rendering a component that uses a tooltip needs one too.
- **A `Transaction` fixture needs six fields minimum.** `BaseFinancialRecord`
  (`financial/api.ts:3–86`) requires `key`, `amount`, `from_entity`,
  `to_entity`, `financial_record_kind`, `financial_view_mode` and
  `is_financial_event`; `TransactionRecord` adds
  `is_evidence_backed_transaction`.
- **A bare account number does not identify an account.** `AccountDraft.observed`
  (`accounts.py:400`) requires an IBAN, a routing number, or an identifier
  **plus an institution name**; otherwise `_account_draft`
  (`native_subjects.py:202`) falls back to `AccountDraft.unidentified` with
  `distinguisher = f"{sha256}:{ordinal}"`. So a BAI2 or MT940 statement that
  prints an account number and names no bank lands **unidentified with the
  number still visible**. **Do not describe the flag as "no account number
  found" anywhere in the interface.**
- **The `distinguisher` is the file's own sha256,** stable across re-reads, so a
  precheck account key equals the key that gets written.
- **The ledger cannot silently double, and it is the schema that guarantees it.**
  `ref_id` is deterministic from `(file sha256, row content)` and
  `uq_financial_transactions_case_ref` is on `(case_id, ref_id)`. **Do not
  restate the old claim that a second run doubles the money; it is wrong.**
- **A failure inside a `with ingestion_run(...)` block must roll back the
  caller's session before it leaves.** Otherwise the open write transaction
  contends with the run's own bookkeeping session, `_terminate_quietly` swallows
  it by design, and the run is left `running`.
- **`IntegrityError` text is not portable.** SQLite names the offending
  **columns**, Postgres names the **constraint**. Assert the table name.
- **`completed_at` cannot be asserted against a literal.** The column is
  `DateTime(timezone=True)`: Postgres returns it with its offset, SQLite returns
  it naive. Assert against the row's own value plus a prefix check.
- **DB-backed financial tests need file-on-disk SQLite, not `:memory:`** — and
  doubly so for anything that runs on a worker thread.
- **`financial_source_documents` is unique on
  `(ingestion_run_id, evidence_file_id)`** — one row per file per run.
- **`evidence_files.stored_path` is `NOT NULL`.** The pathless file that
  production can actually hold is the **empty string**, not `None`.
- **Prefer `ingestion_run` (the context manager) over `open_ingestion_run`.**
- **No module under `services/financial/` imports `config`.** That is why the
  financial tests need no environment. A new module takes its knobs as
  arguments.
- **NACHA yields accounts and no periods.** camt 3/3 rows and a period, BAI2 3/3
  and a period, MT940 2/2 and a period, NACHA 1/1 and **no** period. Junk bytes
  give `unrecognised`.
- **The century window is required and never defaulted.** Max span
  `CENTURY_WINDOW_MAX_SPAN_YEARS = 99`; wider, or backwards, is a 400.
- **A precheck verdict is not a promise the write will succeed.**
  `contradictory_period` and `already_ingested` are decided against rows already
  stored, not against the file.
- **`wouldStore` and `didStore` read the endpoint's flag, never the outcome
  word.** The same applies to `applied` on the adjudication and reconciliation
  endpoints.
- **An unrecognised vocabulary member is named, never rendered blank,** and **no
  outcome maps to the `default` badge variant** — `Badge` falls through to
  `default` for an unmapped key, so a forgotten member would arrive looking like
  the most important thing on screen.
- **The exports guard is automatic.** `tests/test_financial_exports.py` globs
  `*.py` in the package and asserts each module contributes at least one name to
  `__all__`. A new module needs **no manual list entry**, contrary to the note
  in `CLAUDE.md`. Confirmed at `dfcef2b`: `reconcile_case` was picked up with no
  edit to that file.
- **Every Bash command needs its own absolute `cd`.** Where a `cd` is awkward,
  `PYTHONPATH=<abs>/backend` works for one-liners.
- **Any scratch file in `/tmp` needs a per-user name,** including the git index,
  the vite cache, and any file used only to capture output.
- **`GIT_INDEX_FILE` does not survive between Bash invocations.** Staging and
  `git write-tree` must happen in one command. `commit-tree` can be a second
  command **provided it passes the tree hash you already verified.** A commit
  message with awkward punctuation is safest passed with `-F <file>`.
- **A compound `cmd; echo "exit: $?"` inside a longer `&&` chain can report an
  empty exit code**, and `$?` after a pipe is the pipe's status.
- **`&&`-chaining a `grep` that finds nothing silently kills the rest of the
  line.** Use `;` between verification steps.
- **`backend/venv/` poisons every repo-wide grep.** Always pass
  `--exclude-dir=venv --exclude-dir=__pycache__`, and `--exclude-dir=tests` when
  the question is whether something is wired in production.
- **Counting bare name occurrences does not tell you whether something is
  reached.** Grep for the import and list the files. **This is what found the
  central fact of both the reconciliation unit and the one before it.**
- **The house component-test conventions** are `render`/`screen` from
  `@testing-library/react`, `MemoryRouter`/`Routes`/`Route` for a routed page,
  `vi.hoisted` for a mock that has to capture something, `data-testid` for
  anything a test needs to find, and `fireEvent` never `userEvent`.
- **Radix `DialogContent` renders a corner X carrying an `sr-only` "Close",** so
  a footer button named "Close" makes `getByRole` ambiguous. Tell them apart by
  `data-slot="dialog-close"`. Related: **`TooltipTrigger asChild` overwrites the
  child's `data-slot`**, so a badge inside a tooltip is found by `data-variant`.
- **`Badge` spreads `React.ComponentProps<"span">`.** Variants are `default`,
  `secondary`, `destructive`, `outline`, `success`, `danger`, `warning`, `info`,
  `amber`, `slate`.
- **`tsconfig` has `strict: true` but not `noUncheckedIndexedAccess`.**
- **React Query is `^5.90.21`**, so `isPending`, not `isLoading`.
- **Any new code touching `amount_minor` must use `formatLedgerAmount`,** whose
  `currency` parameter is a **required `string`**.
- **SQLAlchemy flush ordering does not follow raw ForeignKeys.** With no ORM
  `relationship()`, commit the parent row first, then the dependent row.
- **The full engine pytest suite cannot run on 3.10** — pre-existing
  `from datetime import UTC` in
  `evidence-engine/app/services/pipeline_run_state.py` is 3.11+ only.
- **The storybook vitest project cannot run here** and no story covers financial
  code. "vitest is green" only ever means the unit and browser projects.
- **`--reporter=basic` is not a valid vitest v4 reporter.** Use the default.
- **`chromadb` is deliberately absent from the bootstrap.** `VectorDBService`
  degrades and warns; the warning is expected output.
- **No live Postgres is needed for the financial suite.**

### The reconciliation subsystem's own rules

New section. Read it before touching item 6's remaining half or item 8.

- **The identity is `opening + (credits - debits) = closing`, in exact integer
  minor units.** The answer is yes or no, never a score. It is the **only** check
  in the subsystem that can detect a transaction that is simply missing: a
  dropped row does not arrive flagged as doubtful, it does not arrive at all, and
  the printed closing balance is the only witness to it.
- **It declines rather than assumes.** A missing balance gives `unavailable` with
  a reason, never a zero. A zero would make the arithmetic close and would be a
  lie.
- **It counts only `admitted` rows,** and the excluded counts travel with the
  result. This is what makes the identity live: quarantine a row and re-running
  changes the answer.
- **`independent` says whether it proved anything.** An identity computed against
  a balance carried forward from the neighbouring period is arithmetic against
  *that period's figure*, not against this document. Worth having, but not
  evidence that this statement was read completely. `proves_completeness` is
  balanced **and** independent **and** the totals complete.
- **The recompute is a POST and the read is a GET, and the split is load
  bearing.** The stored result is the one recorded against the run that produced
  it, at the time it was produced. If a read recomputed, a figure an analyst
  quoted would be a figure that no longer exists anywhere, and two people opening
  the same case minutes apart could see different arithmetic with nothing to say
  which was which.
- **`not_attempted` is reported, not filtered.** It is the default of the read
  and it is the point of the read: **a ledger nobody has reconciled must not be
  able to present itself as a reconciled one.**
- **A refusal leaves the previously stored verdict alone.** It is not reset to
  `not_attempted`. That verdict was a real result when it was taken, and a
  failure to re-derive it today is not evidence that it was wrong.
- **Nothing here moves a proof class.** Deliberately. Moving a class on this
  result is `assign_proof_class` and `record_admission`, which is Phase 2 item 8.
  Two code paths writing that column on two definitions of the same word is how
  it comes to mean neither.
- **A sweep is safe to run repeatedly.** Re-running after nothing changed
  rewrites the same numbers and a new timestamp.
- **`no_periods` and an all-refused sweep are both `200`.** They are facts about
  the case, and an interface has to render them beside the ledger rather than in
  an error path. Only a failed write is a `500`.
- **The parse-time verdict at `native_ingest.py:249` is a different claim from
  this one** and the two can legitimately disagree. That one is about whether the
  file parsed; this one is about whether the stored, admitted rows add up. **Do
  not reconcile them.**

### The localisation reader's own rules

New at `35cc6be`. Read before anything touches `localisation.py` or the rescue
report.

- **`localisation.py` is a reader and nothing else.** It writes no column and
  takes no decision. It turns stored rows and periods into the inputs
  `localise` and `would_rescue` already wanted. **Do not give it a write path**;
  anything that records a verdict belongs with the thing that owns the column.
- **The chain is walked over `admitted` rows only,** because the residual it is
  measured against comes from `total_transactions`, which sums admitted rows.
  Walking a wider population would prove something about a set nobody is looking
  at. **Consequence: the localisation answer moves when a row is quarantined,
  and that is correct.**
- **The identity is recomputed on every call, never read off
  `period.reconciliation_status`.** That column holds whatever the last sweep
  wrote, and on a live case it is usually `not_attempted`, because nothing calls
  the sweep automatically. A reader that trusted it would report against
  arithmetic from another moment or against none at all.
- **Removing the row whose amount equals the residual makes the period balance by
  arithmetic necessity.** This is true whatever the row was and whatever the
  grounds were, so **the balance is not evidence.** Never build anything that
  treats a post-quarantine balance as confirmation that the quarantine was right.
- **The report refuses nothing and warns about nothing.** It states what happened
  so the grounds and the effect can be weighed together. There is a named test
  holding the write path to not refusing a quarantine that rescues a period.
- **`rescues_period` is three-valued and `None` is meaningful.** `True`/`False`
  are findings; `None` means no finding was reached, by one of four routes: no
  period on the row, an unanswerable check, a refused quarantine, or a release.
  **Anything rendering it must distinguish "does not balance" from "no answer".**
- **An unanswerable check never blocks the write.** `_rescue` catches
  `_UNANSWERABLE`, logs with `logger.exception` and returns `(None, None)`. The
  quarantine still happens; the question is recorded as unanswered.
- **The rescue sentence is returned, not logged.** See the authorship rule in the
  quarantine section immediately below — this is the same rule and it is the one
  most likely to be broken by a well-meaning change.

### The quarantine subsystem's own rules

Read it before touching anything in item 6's remaining half.

- **A machine observation must never be merged into a string attributed to a
  person.** `QuarantineBasis.from_adjudication` stores its detail as
  `"<actor>: <reason>"`. Appending the rescue sentence to `reason` would produce
  a log entry in which the person appears to have written words nobody wrote.
  **An evidence log cannot do that.** There is a test asserting the stored reason
  is exactly what the person typed, prefixed only by their name.

- **Grounds are a proof or a person, and nothing else.** `QuarantineBasis` has
  three constructors and **none of them takes a `Candidate`**, by design. A
  class a person can raise must not be able to pass for one the arithmetic
  proved, which is the settled rule that proof class is computed and never set
  by hand. The endpoints therefore always record `QuarantineReason.adjudicated`
  and the computed grounds are unreachable from HTTP.
- **`ck_financial_transactions_quarantine_coherent` is
  `(quarantine_reason IS NOT NULL) = (ledger_status = 'quarantined')`.** A
  released row **must** have its reason nulled, so a row that was quarantined
  and let back in is, on the row alone, indistinguishable from one that was
  never held. **The adjudication log is the only place that history exists.**
  Anything reporting on quarantine has to read the log, not the row.
- **`quarantine_transaction` refuses a row that is not `admitted`.** So a
  superseded or rejected row cannot be quarantined, and the driver reports that
  as `refused` with the writer's own words.
- **`quarantine_transaction` is idempotent for identical grounds and refuses
  different ones.** Same grounds: returns the row, appends nothing. Different
  grounds: raises `UngroundedQuarantineError` containing "already quarantined".
  The refusal is deliberate — it stops a person's opinion overwriting a computed
  class.
- **`release_transaction` refuses a row that is not quarantined** with a message
  containing "nothing to release", and requires both a real `Actor` and a
  non-empty reason.
- **An unchanged row is reported separately from a changed one.** Reporting an
  idempotent no-op as `quarantined` would hand back an `adjudication_id` naming
  **somebody else's earlier decision** as though it were this request's. The
  status is read before the call and that case comes back `unchanged` with no id.
- **The 404 is worded identically for a row in another case and a row that does
  not exist,** so asking cannot be used to learn what a case the caller cannot
  see contains. There is a test asserting the two routes word it the same.

### The ledger screen's own rules

- **The ledger read defaults to `admitted`** (`transaction_query.py`). Zero rows
  does not mean no financial material; quarantined, superseded and rejected rows
  sit outside the filter. The empty state names the status it filtered on.
- **`total` is `len(transactions)` of the same response.** No paging behind it.
  The panel takes its count from `rows.length` and surfaces a disagreement.
- **Rows arrive ordered by `ordering_date.asc(), row_index.asc()`.** The table
  does not sort. **Do not add client-side sorting without dealing with that.**
- Three things in the table are correctness, not presentation: an unscaled
  amount is marked, an absent running balance is stated in words rather than
  left blank, and an unrecognised vocabulary member renders loudly with
  `data-unrecognised="true"`.
- **The ledger query key is `["financial-ledger", caseId, ...]`,** deliberately
  outside `["financial", caseId, ...]`. `useIngestFile` invalidates the former
  only.

### The runs subsystem's own rules

- **`GET /api/financial/runs` returns every status by default,** the opposite of
  the ledger read. Anything built on top must not "helpfully" filter to
  completed runs; the failures are the payload.
- **The run read makes no staleness judgement, and must not start.** Deciding a
  run is abandoned is the reaper's call and the reaper writes it down.
- **The counts on a run are historical.** `documents_seen`,
  `transactions_admitted` and `transactions_quarantined` were true when the run
  ended. **Adjudication moves rows afterwards**, and **so does a reconciliation
  sweep's effect on what those rows mean**, so they will legitimately disagree
  with a `COUNT(*)` over the ledger today. **Do not reconcile them.**
- **`started_by_email` outlives `started_by_user_id`.** The FK is
  `ON DELETE SET NULL`. Prefer the email.
- **`reap_stale_runs` is global, not case-scoped.** This is why it is a lifespan
  loop and not an endpoint.
- **Ordering runs needs the secondary sort on `id`.** `started_at` alone is not
  a total order. Same rule now applies to ordering periods.

### And on the frontend, as of `e64c2ca`

Rules from the quarantine screen, now complete in six commits.

From the wiring, `FinancialPage.tsx`, `LedgerTable.tsx`, `financial.store.ts` and
`ledger-format.ts`:

- **`RowAdjudicationDialog` is mounted by `FinancialPage`, on page state, outside
  `Tabs` and outside both panels. Do not move it into either.** A successful
  change invalidates `["financial-ledger", caseId]`, which is a prefix of both
  lists, so the row leaves the list it was clicked in and the panel returns its
  early empty state; and Radix `Tabs` mounts only the active tab's content, so a
  tab change would do the same one level up. Either way the dialog is torn down
  at the moment its answer arrives, **and `rescues_period` with it**, which is
  said in that one response and on no record.
- **Two tests pin the mount point, one per panel:** the row goes on being passed
  to the dialog after it has left every list on screen. **There is no test for a
  tab change while the dialog is open and there cannot be one** — the dialog is
  modal, Radix marks the rest of the document `aria-hidden`, and the tab strip
  cannot be reached by role behind it. Do not file this as missing coverage.
- **`changeAvailableFor` in `lib/ledger-format.ts` is the single reading of which
  change a row admits of,** and `ROW_CHANGE_LABELS` the single source of the two
  words. It is in `lib/` and not a hook because **`lib/` must not import from
  `hooks/`** and both the table and the dialog need it. A second copy of either
  lets the word on the row and the word on the confirm button disagree.
- **`null` from it means "this build cannot read the status", not "no change is
  possible".** The cell says "Status unread, no change offered" rather than going
  blank; a blank cell in a column of buttons reads as *nothing can be done to
  this row*, when what is true is that the build cannot tell whether the row
  counts toward the totals. **Do not render an empty cell here.**
- **Every readable status other than `quarantined` is offered a setting aside,
  including `superseded` and `rejected`.** The ledger may refuse; the refusal is
  the answer and it arrives in the response. **Do not add a client-side status
  filter to the button** — same rule as the dialog's, one layer up.
- **The action column is drawn only when `onAdjudicate` is passed.** A column of
  buttons that do nothing states that a change can be asked for from a screen
  that cannot ask for one.
- **`LedgerTable` never mutates.** It hands the row back and stops, which is what
  keeps every case in its test file assertable against rows alone.
- **`changeAvailableFor`'s tests loop over `LEDGER_STATUSES`,** so a fifth member
  added to the backend enum cannot silently fall through to `"quarantine"`. **The
  table's tests assert `data-change`, not the button text,** so the labels can be
  reworded without the rule going quiet.
- **`mainView` is omitted from `partialize` and deleted in `merge`, so it is
  never persisted and a new member needs no migration.** Read there, not assumed.
  **If `mainView` is ever added to `partialize`, that changes: the store then
  needs a version and a migration**, and a browser holding an older value could
  otherwise put the page in a state the build cannot render.

From the list, `QuarantinePanel.tsx`, `LedgerTable.tsx` and `ledger-format.ts`:

- **`QuarantinePanel` fixes `ledger_status=quarantined` and its `params` type
  excludes the field.** Every sentence on it is only true of quarantined rows,
  starting with the empty state. Do not turn it back into `<LedgerPanel
  params={{ ledgerStatus: "quarantined" }} />`; that panel's empty copy states
  the reverse of what was checked.
- **Zero quarantined rows is a good result and must read as one.** "Nothing is
  being held out of this case's totals", not "no rows found". The general ledger
  panel's "change the status filter to see them" must never appear here, and a
  test asserts it does not.
- **The count on it comes from `rows.length`; `total` disagreeing is reported as
  a fault.** The endpoint returns `total` as `len(transactions)` of the same
  response, so a mismatch can only mean paging appeared without this screen
  knowing, and a page of quarantined rows shown as the whole set understates what
  is being excluded.
- **`showQuarantineGrounds` on `LedgerTable` moves the reason out of the status
  cell into a column; it does not duplicate it, and the status column stays.** A
  row that is somehow not quarantined inside a quarantined list is precisely what
  a reader has to be able to see. The default is off, so the general ledger list
  is unaffected.
- **`readQuarantineGrounds`, not `readQuarantineReason`, wherever the
  classification matters.** It wraps the other and adds `decidedByPerson`
  (three-valued: `true`, `false`, `null`) and `origin`. `adjudicated` is the only
  member that is a person's decision — `from_adjudication` is its only
  constructor and `quarantine_case_row` refuses to let a person type any other.
- **The words behind an adjudicated hold are not on the ledger read, so any
  screen showing the category must say where they are.** `AdjudicationEvent`
  (`adjudications` table) carries `reason` as `Text, nullable=False`; the ledger
  row carries the category and no detail field. Saying "a person decided" and
  stopping reads as a decision with no reason given.
- **Quarantine badges stay outline in both positions.** Filled reads as a second
  status when stacked under one; colouring them once they have their own column
  ranks five different grounds as a severity scale, which they are not.

From the dialog, `RowAdjudicationDialog.tsx`:

- **`RowAdjudicationDialog` must be kept mounted until the person closes it.** A
  successful change invalidates the ledger lists, so the row leaves the list the
  dialog was opened from. The mutation, and therefore the answer, lives in the
  dialog: unmounting it when the row disappears destroys the answer before it has
  been read, **and the statement-balance fact with it**, which exists nowhere
  else. Its `open` and `onClose` are what the caller drives, not conditional
  rendering on the row still being present.
- **It takes `row`, not a verb.** Which change it offers is derived from
  `row.ledger_status`. Do not add an `action` prop; two copies of that fact can
  disagree, and the disagreement asks the ledger to do something already done
  while telling the person otherwise.
- **A status it cannot read offers no change at all,** deliberately, and still
  draws the row and the raw value. Not a client-side refusal — there is simply
  nothing to derive the verb from.
- **It does not screen out rows the ledger will refuse.** A superseded row is
  offered "set aside" and the refusal is displayed as the ledger's answer. **Do
  not add a client-side status check;** it is a second copy of the ledger's rules
  and it is the copy that drifts.
- **The non-empty `reason` guard lives here and nowhere else,** and it is
  `trim()`-based, which is **stricter than** the database's own blank check on
  purpose. The asymmetry is the safe direction: nothing the dialog accepts can
  hit a constraint the person cannot see. Do not "fix" it into an exact match.
  What is sent is the trimmed text, which is what the writer would store anyway.
- **The sentence about whether the row moved comes from `applied` only.** Where
  `applied` and the read outcome word contradict, the contradiction is rendered,
  not resolved.
- **`rescues_period` is rendered whenever the reading has anything to say and
  suppressed only where no statement was checked** — in practice the release
  path. It is in this answer and on no record. A screen that drops it loses it.

From the hook and the layers below it:

- **`useRowAdjudication(caseId)` is the only way a component asks for a row to be
  set aside or let back in.** One mutation for both routes; the verb is
  `variables.action`, `"quarantine"` or `"release"`. It resolves to a
  `RowAdjudicationReading`, already mapped — **do not re-read the wire object,
  there isn't one to read.**
- **`isSuccess` on it does not mean anything moved.** `data.applied` does. A
  screen that reports off the mutation's success flag will tell a person a row
  was held when the ledger refused.
- **It invalidates `["financial-ledger", caseId]` and nothing else,** which is a
  prefix of both the admitted and the quarantined list — right, because an
  adjudication moves a row between them rather than adding or removing one. The
  Neo4j keys under `["financial", caseId, ...]` are a different store and are
  deliberately untouched.
- **It rejects when `caseId` is undefined** rather than sending
  `case_id=undefined`. This differs from `use-ledger-ingest.ts`, which asserts;
  that difference is intended and is not to be tidied away.
- **`reason` is not validated here.** The backend requires the field and not its
  content. The non-empty guard goes in the dialog.
- **Never `vi.mock("../api")` in this feature's tests.** It replaces the closed
  vocabularies the format readers import from the same module, and every outcome
  in the file silently becomes "unrecognised" while the tests still look real.
  Stub `globalThis.fetch`, building a **fresh `Response` per call** — a shared
  one reads its body once and the second call dies with "Body is unusable",
  which looks exactly like the code under test failing.

- **`financialAPI.quarantineRow` and `.releaseRow` exist and are the only way to
  change a stored row's standing.** Both take `{ caseId, transactionId, reason }`,
  all three required. `case_id` goes in the query string, `reason` in the JSON
  body under its own key, the row id percent-encoded into the path.
- **A refusal is a 200, not a throw.** Only `not_found` (404) and `write_failed`
  (500) leave the happy path. Callers must read the returned `outcome`, not treat
  a resolved promise as success. `applied` is true for exactly `quarantined` and
  `released`.
- **`RowAdjudication.reason` is overloaded by outcome and must not be presented
  as one thing.** Established by reading `quarantine_row.py` at `19bffae`, and
  the earlier wording of this bullet was wrong on two of the four: on
  `quarantined` it is the machine's rescue note or null; on `refused` it is
  `str(exc)` from the writer; on `unchanged` it is a canned sentence; on
  `released` it is **`None`**, because `_current()` defaults it and the person's
  words go to the record instead. On the two error outcomes it does arrive — as
  the `detail` of the 404 or the 500.
- **None of the four is the person's own words**, on any outcome. A screen that
  labels the field as somebody's stated grounds is putting words in their mouth.
  `ADJUDICATION_REASON_IS_NEVER_THE_PERSONS` in `lib/adjudication-format.ts` is
  the sentence to show beside it.
- **`ledger_status` and `quarantine_reason` on an adjudication answer are ledger
  values, not adjudication values.** `_current()` copies both straight off the
  stored row, so they narrow through `readLedgerStatus` / `readQuarantineReason`
  and their unrecognised copy correctly says the value came from the ledger.
  Only `outcome` gets its own provenance string.
- **`ROW_ADJUDICATION_FIELDS` is typed `readonly (keyof RowAdjudication)[]`** so
  a name the interface does not declare fails to compile, and
  `api.adjudication.test.ts` closes the other direction against the Python.
  **A new field on the backend `as_dict()` must be added to both.**
- **`UNRECOGNISED_VARIANT` is `"warning"` in `LedgerTable.tsx` and
  `adjudication-format.ts`, and `"outline"` in `run-format.ts`.** The two
  disagree and neither is wrong on its own; `LedgerTable` is the one that states
  the rule ("used for nothing else"), so new code follows it. Left as is.
- **`outcome`, `ledger_status` and `quarantine_reason` are `string` on purpose.**
  Narrowing is `adjudication-format.ts`'s job. Do not "fix" them into unions.

Everything below is from `bc23570`, **except the two `FinancialMainView` bullets,
which were updated at `e64c2ca` when the sixth tab landed.**

- **`readRunStatus(raw).needsAttention`** is true for `pending`, `running`,
  `failed`, `aborted`, and **false for an unrecognised status**, deliberately,
  with a named test.
- **`RUN_COUNTS_ARE_HISTORY` must accompany the three counts** wherever they are
  shown; `IngestionRunsTable` renders it itself so a caller cannot separate them.
- **`readRunStarter` prefers the email**, falls back to `User <id>`, and says
  "Not recorded" rather than rendering an empty cell.
- **`formatRunTime` is fixed to `en-GB`,** matching `formatLedgerAmount`. An
  unparseable value is shown as it arrived, not as "Invalid Date".
- **`runDuration` returns `null` rather than `0`,** with two distinct
  presentations keyed `run-no-end` and `run-no-duration`. Do not collapse them.
- **`IngestionRunNotice` calls `useIngestionRuns(caseId)` with no params,** so
  its cache entry is `["financial-runs", caseId, null]`. **Anything else wanting
  every attempt on the case must call it the same way** or it opens a second
  cache entry and a second request for identical data.
- **The runs query key is outside both other keys, and nothing invalidates it.**
  Ruled closed by Neil.
- **The notice is a sibling of `LedgerPanel`, not inside it.** `LedgerPanel`'s
  four early returns would otherwise hide it exactly when the ledger is empty.
  **Do not "tidy" this by nesting them.**
- **`FinancialMainView` has seven members** as of `e655a0a`, `"ledger" | "runs" |
  "quarantine" | "decisions" | "transactions" | "counterparties" | "trends"`.
  **The order is load bearing:** the first four read Postgres, the last three
  read the graph, and `"quarantine"` and `"decisions"` are placed with the first
  group for that reason.
- **The ledger, attempts, held-out and decisions tabs take no graph chrome.** A
  case with an empty graph must still reach all four.
- **`api.runs.test.ts` reads the Python source** to prove the two languages
  still agree. A backend change to the route, the parameters, the envelope keys
  or the ordering clause fails a frontend test. That is the intended alarm.

### The decisions screen's own rules, as of `e655a0a`

From `DecisionsPanel.tsx` and `DecisionsTable.tsx`. This screen is the one place
that shows **how** the ledger came to stand as it does, so several of the rules
below are about not letting a partial view read as a complete one.

- **`DecisionsPanel` calls `useCaseDecisions(caseId)` with nothing after it,**
  keying at `["financial-decisions", caseId, null]`. Passing `{}` or an explicit
  undefined field opens a second cache entry for identical data — same rule
  `IngestionRunNotice` states. A test asserts the call has one argument.
- **There is no count-disagreement warning here, and its absence is
  deliberate.** `LedgerPanel`, `QuarantinePanel` and `IngestionRunsPanel` all
  compare `total` against the rows they were sent, because their endpoints do
  not page. **This one pages by design**, so `total !== decisions.length` is the
  ordinary case and the warning would fire on every case with a history. **Do
  not add one.** What that warning does elsewhere is done here in words, by
  `describeDecisionPage`.
- **The heading is `describeDecisionPage(data)` and must never be composed from
  `decisions.length`.** A sentence built from the row count says "12 decisions"
  over the first twelve of two hundred. The trap that makes this hard is in the
  format module: **`truncated` only looks forward** and is false on the last page
  of many, so "showing all of them" cannot be read off it alone.
- **The empty state is gated on `data.total === 0`, not on the length of the
  page.** A page that came back with no rows while `total` is positive means the
  read landed past the end of the log, and "nothing has been decided" and "you
  have paged past the decisions there are" call for opposite next moves. A test
  pins the two apart.
- **The failed-read message names what is lost** — that nothing on screen says
  why anything was set aside, hidden or removed — rather than drawing nothing.
  An empty screen where the record should be reads as a case nothing was ever
  decided about, which is exactly what a person would say to defend a total.
- **`DECISION_ORDER_IS_NOT_SEQUENCE` is rendered by `DecisionsTable` itself,**
  for the same reason `RUN_COUNTS_ARE_HISTORY` is rendered by
  `IngestionRunsTable`: whoever draws the rows draws the caveat, so a caller
  cannot separate them. `recorded_at` is written at the start of the transaction,
  so decisions taken in one act share it exactly and sit adjacent in an arbitrary
  order. `subject_sequence` **is** reliable, and is the numbering shown per row.
- **The effect of a decision is rendered in words, never as a tick or a cross.**
  `changedStoredState` is three-valued and `null` means this build does not
  recognise the decision, so it cannot say whether anything moved. `readDecision`
  resolves all three into `effect`, which is always safe to render. The raw value
  is exposed as `data-changed-stored-state`, and **the null case is written as
  the string `"null"` rather than as an absent attribute**, so a test for the
  unknown case fails if the attribute stops being written rather than passing on
  its absence.
- **`UNRECOGNISED_VARIANT` here is `"warning"`, following `LedgerTable`,** and
  both the decision badge and the subject cell carry `data-unrecognised`. A
  stored word this build cannot read must not be drawn as though it were a label.
- **`reason` is shown whole, never truncated, and an empty one is named.** It is
  what the person typed at the time and the part of the entry that has to survive
  being read back months later. Blank space where the grounds go reads as no
  reason having been given; the row says "No grounds recorded" instead, with the
  distinction spelled out in the title.

### The proof standing reader's own rules, as of `cbf163e`

`services/financial/proof_standing.py`, `GET /api/financial/proof-standing`, and
`financialAPI.getCaseProofStanding`. Anything reading this census later inherits
these, and each is held by a test.

- **The four permissions are imported from `proof_class`, never restated.**
  `admits_automatically`, `requires_adjudication`, `may_produce_ledger_rows` and
  `counts_toward_totals` are asked of the module that owns the rules. A copy here
  could disagree with what the ledger actually enforces, and the disagreement
  would surface as material shown as verified that is not. The contract test
  pins the import.
- **The permissions travel with the counts, and they are the payload.** `p3` is
  two characters. The fact it names — the one class no ingestion run admits by
  itself — arrives only in `requires_adjudication`. If that field stops arriving,
  the counts keep coming and every screen goes on rendering, showing material
  nobody has ruled on as part of the verified ledger. **That failure is invisible
  from the screen**, which is why it is asserted on its own rather than left to a
  field-set comparison that a rename would pass.
- **Every class is reported, including the empty ones.** *"No p3 documents here"*
  and *"nothing looked at p3"* are different facts and an absent key spells them
  the same way.
- **It is a census, so it takes the case and nothing else.** No filter reaches
  the endpoint, from either side. A filter would break the property that the
  per-class figures add up to the case's documents and rows — which is the only
  thing that lets a reader check the breakdown at all — and the response would
  look identical.
- **The counted set is the backend's, not a parameter.** A screen that could
  choose its own set would be free to show a coverage the totals beside it were
  never computed against.
- **Totals are summed from the parts, not queried separately.** A second query
  could return a total the rows beneath it do not reach.
- **The route is on the ledger router, not the adjudication one.** Describing the
  ledger needs the permission to read it, not to change it. This is the whole
  reason chunk 3 did not go where the plan predicted.
- **`ProofStandingError` is deliberately not mapped to 400.** It means this build
  and the database disagree about what classes exist, which is a fault here, not
  a bad request from the caller.

---

## Build order

The order lives in **`docs/loupe-wiring-plan.md`**, committed as `c88533f`, on
Neil's instruction: "I need you to build everything. Have a think about the best
order and make this the plan and stick to it."

Sixteen units in four phases. One unit per session, finished, tested and
committed before the next begins. **Do not reorder without a ruling.** If a unit
turns out to depend on something later in the list, stop and ask.

- **Phase 1, make rows exist — COMPLETE.** Precheck endpoint ✅ `a4eb3dc`,
  ingest endpoint ✅ `43f8358`, the interface action on a held file ✅ `17d94ac`,
  mount the ledger ✅ `4324b24`.
- **Phase 2, make the rows trustworthy** — runs ✅ item 5 complete (backend
  `cde43c5`, notice `8924668`, attempts list `bc23570`); quarantine ✅ item 6
  **complete end to end** (write path `150084a`, localisation reader and rescue
  reporting `35cc6be`, screen chunks 1 to 5 `1894fc4`, `19bffae`, `610df9b`,
  `66d1e67`, `519895e` and `e64c2ca`); reconciliation ✅ item 7 (`dfcef2b`).
  **Item 8, adjudication and proof class: all three planned chunks are now
  done** — **chunk 1, the decisions surface** (reader `a40bb61`, route `2eefc4d`,
  wire `0fa07d5`, words `71d859d`, hook `62ff2de`, screen `e655a0a`); **chunk 2,
  the admission path** — 2a the record (`5fa71a2`), 2b the gate (`4e13821`);
  **chunk 3, proof class and `requires_adjudication`** (`cbf163e`). **The item is
  still not done**, because the admission control on the frontend is owed and is
  in no chunk — see the next section. Then duplicates, suspect amounts,
  locators.
- **Phase 3, make the ledger the source of the graph** — projection, continuity
  and coverage, linkage and correlation and flow.
- **Phase 4, get it out** — exhibit and export, tracing.

### Current unit: the admission control — the last thing between item 8 and done

**Start here.** All three chunks the wiring plan named for item 8 are finished
(`e655a0a`, `5fa71a2`, `4e13821`, `cbf163e`). What is left is a unit the plan
never named, and it is owed because a previous unit created it.

**What is actually wrong, in plain terms.** A file that arrives in a form the
system cannot verify is held rather than processed. A named person can overrule
that hold and say on the record that the file should go through anyway — the
backend for that landed at `5fa71a2`, and at `4e13821` the send began refusing
any file that has not been so admitted. Both halves are enforced. But nothing on
the screen calls the admitting route. So a held file **cannot be processed from
the interface at all**: the refusal comes back carrying everything a person would
need in order to admit it, and there is nothing that reads it and no button that
acts on it. The backend is right and the door has no handle.

**Concretely:** `POST /api/financial/files/{file_id}/admit` has zero TypeScript
callers. The 409 body from the three refusing routes names each held file and
what was found in it. That body is the input the control needs, and it is
already correct — this unit is a reader, a hook, and a control, not a backend
change.

**This is a frontend unit and it is not in the wiring plan, so it needs a ruling
from Neil about where it sits in the order.** Do not resequence around it and do
not fold it into another item. Open the session by telling him, in the plain
terms of the paragraph above, that the hold is enforced and the way to lift it
was never built, and ask whether to build it now or move to Phase 3. Bring that
recommendation: **build it now**, because until it exists a held file is stuck
for good, which is a worse state than before the gate landed.

**Read before building it:** `services/financial/admit_file.py`,
`services/financial/admission_gate.py`, the admit route on
`routers/financial_adjudication.py`, and the three 409 responders. The shape of
the 409 is the contract this unit consumes; pin it in a contract test the way
the five existing `api.*.test.ts` files pin theirs.

**It is a frontend unit, so the backend pip bootstrap is not needed** unless the
409 shape turns out to be wrong. The vitest cache and the browser gate are what
matter, and both have new instructions this session — see "How to run the
browser gate" above, and read the disk warning there before assuming anything
can be installed.

**Known gap neither chunk closes, and it is in the other service.** The engine's
own pre-stage, `evidence-engine/app/pipeline/orchestrator.py`, independently
fails any job whose file it detects as native, and no admission recorded on this
side can reach it. So an admitted **native** file is now recorded, passed by the
gate, sent, and then refused by the engine by name. **Do not treat this as an
open question and do not add it to the plan.** The position, taken here so it is
not re-argued: the backend half is correct as built, the refusal is loud rather
than silent, and closing it is a change to a service whose suite **cannot be run
in this sandbox at all** (see Durable facts). It is recorded as a standing flag.
What would reverse it: Neil saying an admitted native file must actually reach
the pipeline, at which point it becomes an engine unit he runs the gates for.

---

### The whole item, and the one thing it still needs

The wiring plan's own words for the item:
*"`assign_proof_class`, `requires_adjudication`, `record_admission`, the
decisions surface. Proof class is computed and never set by hand; the interface
shows it and shows what an adjudication changed, and never offers a control that
sets it."*

**The chunking, decided at `a40bb61`:**

1. ✅ **The decisions surface — complete.**
   `services/financial/decision_log.py` `a40bb61`;
   `GET /api/financial/decisions` on the **ledger** router `2eefc4d`;
   `financialAPI.getCaseDecisions` and its contract test `0fa07d5`;
   `lib/decision-format.ts` and its test `71d859d`;
   `use-case-decisions.ts` and its test `62ff2de`;
   `DecisionsTable`, `DecisionsPanel`, the seventh tab and the invalidation
   `e655a0a`. **A user can now read the record of what was decided about a case
   and on what grounds.**
2. **The admission path**, split in two once it was planned from the source,
   because `admission.py` states its rule in two halves:
   *"the event is written before the file is sent, or it is not sent."*
   - ✅ **Chunk 2a, the writing — complete, `5fa71a2`.**
     `services/financial/admit_file.py` gives `record_admission` its first
     production caller; `POST /api/financial/files/{file_id}/admit` on the
     adjudication router lets a person reach it. **A named person can now
     overrule the router about one file, on the record.**
   - ✅ **Chunk 2b, the enforcement — complete, `4e13821`.**
     `services/financial/admission_gate.py` is called from `process_db_files`
     immediately before the send, and all three routes that reach it answer 409
     naming each held file and what was found in it. **No held file reaches the
     document pipeline without a named person having said on the record that it
     should.** Not delivered: every send separately authorised — see the
     consumption flag under Standing flags.
   - **Still owed and in no chunk: the control.** Neither 2a nor 2b touched
     TypeScript, so there is still no way for a person to actually admit a file.
     Its own section is above, under "Current unit".
3. ✅ **Proof class and `requires_adjudication` — complete, `cbf163e`.**
   `services/financial/proof_standing.py` gives `requires_adjudication` its first
   production caller; `GET /api/financial/proof-standing` on the **ledger** router
   answers with a census of every class; `financialAPI.getCaseProofStanding` and
   `api.proof-standing.test.ts` hold the contract. **A user can now see how much
   of a case rests on material nobody has ruled on, and the four permissions that
   say what each class is allowed to do arrive with the counts rather than being
   restated on the screen.**

**Facts established by grepping the source, not remembered.** The first two were
found at `e64c2ca`; the rest were corrected at `cbf163e` and the corrections are
the point of keeping them:

- **`assign_proof_class` already has production callers and is not dark code.**
  It is called from `camt053.py`, `bai2.py`, `mt940.py`, `nacha.py` and
  `documents.py` (three call sites there, including `proof_class=...` on a draft).
  So proof class is **already being computed and stored at parse time**. Chunk 3
  was not "start computing it"; it was the surface that shows it.
- **`requires_adjudication` had zero production callers — no longer true as of
  `cbf163e`.** It was defined at `proof_class.py:206` and exported from
  `__init__.py`, and nothing else called it. That was the gap chunk 3 closed. Its
  caller is `services/financial/proof_standing.py`, which imports it rather than
  restating what it decides.
- **`record_admission` had zero production callers — no longer true as of
  `5fa71a2`.** It was defined at `admission.py:104`, exported, and referenced
  only in docstrings; `reconcile_case.py:28` and
  `routers/financial_reconciliation.py:33` both said in so many words that it was
  *"a later unit"*. Chunk 2a was that later unit. Its one caller is
  `services/financial/admit_file.py:admit_case_file`. **Left here as written
  because the two docstrings still say "a later unit" and will read as stale to
  the next person; they were not touched by `5fa71a2`, `4e13821` or `cbf163e`,
  and correcting them is a loose end, not a unit.**
- **`routers/financial_adjudication.py` has three routes and still no
  proof-class one, and that is now permanent.** Item 6 put two there
  (`POST /transactions/{id}/quarantine` and `.../release`) and `5fa71a2` added
  `POST /files/{file_id}/admit`. **The prediction recorded here — that chunk 3
  would add a fourth and deliberately fail
  `test_every_route_is_a_post_against_the_thing_it_adjudicates` — did not
  happen and cannot now happen.** Chunk 3 read the two routers and put its route
  on the **ledger** one instead, because that router's every route resolves to
  `("case", "view")` and a census needs no more permission to describe the ledger
  than reading it does. Putting it on the adjudication router would have made it
  demand the permission to *change* the ledger in order to *describe* it. The
  exhaustive route-set test is untouched and still passes. **The design point it
  encodes is unchanged and still applies to any genuine write:** a route added to
  the adjudication router inherits `case:edit` unconditionally, so whoever adds
  one has to say what it is.

**The rule this corrects, worth keeping.** The wiring plan and this file both
named the adjudication router as "the natural home" for the proof-class work.
That was right for a write and wrong for a read, and no amount of re-reading this
file would have found it — only reading the two routers did. **Plan a unit from
the source files, not from this one.**

**When a unit touches the frontend**, the vitest cache must go on `/dev/shm`
carrying the current user, and the browser gate must **reuse** the existing
Chromium rather than install one — see "How to run the browser gate" above, which
was rewritten at `cbf163e` and now contradicts what this section used to say.
All of the frontend failure modes report a silent "no tests", so **never read
"no tests" as green.**

**When a unit touches the backend it needs the pip bootstrap.** The documented
`CLAUDE.md` one still fails on `ENOSPC`; the working form is under "Carried
forward", including the `TMPDIR` flag that was missing from it. It was run and
re-measured at `cbf163e`, so the backend baseline above is real and not carried:
**3,466**. Re-measure rather than trusting this line, and check the arithmetic
against the number of tests the unit adds. **If the unit touches
`services/evidence_*` or any router, run the evidence tests too** —
`python3 -m pytest tests/ -k "evidence or cellebrite"`, 59 passing. The financial
suite does not cover them, which `4e13821` found out the useful way round.
**Read the disk warning under "How to run the browser gate" first: the bootstrap
is 151M and there was 79M free at the end of this session.**

**The settled rule that constrains the whole unit** is already in `CLAUDE.md`:
*proof class is computed, never set by hand, including by us. A class a person
can raise is an opinion.* So the surface shows the class and shows what an
adjudication changed; it never offers a control that sets a class.

### The quarantine screen, as built — item 6 is closed

Six commits, the last of them `e64c2ca`. The screen was planned in five; chunk 4
was split in two because the dialog alone came to 1,103 insertions. **Nothing in
this list is outstanding.** It is kept because the chunk boundaries record where
each rule was decided, and the rules themselves are under "And on the frontend"
above.

- **Chunk 1 ✅ `1894fc4`.** `api.ts`: the two calls, the `RowAdjudication` shape,
  `ROW_ADJUDICATION_OUTCOMES`, `ROW_ADJUDICATION_FIELDS`, `RowAdjudicationParams`,
  plus `api.adjudication.test.ts` holding the contract against the Python.
- **Chunk 2 ✅ `19bffae`.** `lib/adjudication-format.ts` plus its tests.
  `readRowAdjudicationOutcome`, `readRescueOutcome`, `readAdjudicationReason`,
  `readRowAdjudication`. What chunk 3 and chunk 4 need to know about it: **read
  the whole answer with `readRowAdjudication`, not the outcome on its own** —
  it composes the rescue reading in deliberately, because `rescues_period` is
  said nowhere else and a caller reading only the outcome would drop it.
  `ADJUDICATION_REASON_IS_NEVER_THE_PERSONS` must be shown wherever `reason` is.
  The reading exposes `outcome.changedTheRow` (this build's reading, `null` when
  it cannot read the word) separately from `applied` (the wire's own), and
  `appliedDisagreesWithOutcome` when they contradict.
- **Chunk 3 ✅ `610df9b`.** `hooks/use-row-adjudication.ts` plus its tests. One
  mutation over both routes, the verb in `variables.action`. What chunk 4 needs
  to know: it resolves to a **`RowAdjudicationReading`, already mapped**;
  `isSuccess` means the question was answered and **`data.applied` is the fact**;
  it invalidates `["financial-ledger", caseId]` itself, so a caller does not; and
  it does **not** check that `reason` says anything, because the backend does not
  either. The plan's "invalidate on `applied` only" was widened to `applied ||
  outcome.changedTheRow === true`; the reasoning and what would reverse it are in
  the session notes above and in the commit message.
- **Chunk 4a ✅ `66d1e67`.** `components/RowAdjudicationDialog.tsx` plus its
  tests. The first surface a person can see. **The empty-`reason` guard deferred
  from chunk 3 landed here.** What 4b and 5 need to know: it takes `row`, not a
  verb, and derives the change from `row.ledger_status`; it must be **kept
  mounted until the person closes it**, because the answer lives in its mutation
  and the row will leave the list underneath it; and it reports movement from
  `applied` alone. Its rules are under "And on the frontend" above.
- **Chunk 4b ✅ `519895e`.** `readQuarantineGrounds` in `lib/ledger-format.ts`,
  the grounds column on `LedgerTable.tsx` behind `showQuarantineGrounds`, and
  `components/QuarantinePanel.tsx`, plus tests. The conditional-column-versus-
  second-table question was **answered against `LedgerTable.tsx` in favour of the
  column**; reasoning and reversal in the session notes above and in Standing
  decisions below. **`QuarantinePanel` takes `caseId: string | undefined` and an
  optional `params` that cannot carry `ledgerStatus`**, and it handles the
  no-case, loading, error and empty states itself, so a caller mounts it and
  passes the case.
- **Chunk 5 ✅ `e64c2ca`.** The "Held out" tab wired into `financial.store.ts`
  and `FinancialPage.tsx`, the action column on `LedgerTable.tsx` driven by
  `changeAvailableFor`, and the dialog mounted on page state outside `Tabs` and
  outside both panels. `FinancialMainView` took its sixth member with **no
  migration**, because `mainView` is omitted from `partialize` and deleted in
  `merge`. Rules under "And on the frontend" above.

**One guard considered and not written, recorded so it is not silently
forgotten.** The row identity the dialog sends is `row.key`, which the backend
sets at `services/financial/transaction_query.py:184` as `key=str(row.id)` — read
there, not remembered. A test walking the Python to prove the adjudication route
and the ledger read still name the same identity, the way `api.runs.test.ts`
does, would be a real guard and does not exist. **It is not blocking anything;
pick it up if a session has room.**

### Two questions settled by reading the source, not open

**The two-value grounds column ships now.** `from_proof` is reachable from the
reader but **no production path calls it** — computed grounds are unreachable
from HTTP by design — so on a live case every quarantined row currently reads
`adjudicated`. The column is correct and costs nothing. **The claim that its
second value "arrives with item 8" is now known to be wrong**: item 8 is complete
on the backend and produced no such path, because chunk 3 turned out to be a read
rather than a writer. See the standing flag on `QuarantineBasis.from_proof`. That
does not reopen this decision — the column still ships and still costs nothing —
it only removes the unit that was expected to fill it. **Settled; do not raise it
with Neil.**

**The screen and the write path are one unit.** A read-only screen would be a
permanently empty state by construction: `quarantine_case_row`, over the
adjudication route, is the only production writer of `quarantined`. **Still the
only one at `cbf163e`;** item 8 did not give the list a second source. *What
would reverse it:* a later item doing so.

### The screen question, settled by reading the source

- **The read is the same endpoint.** `GET /api/financial/ledger` already takes
  `ledger_status`, and `ledger_status=quarantined` returns exactly the
  quarantined population. **No new read endpoint is needed and none was built.**
- **But a quarantined row carries a field an admitted row structurally cannot.**
  `quarantine_reason` is non-null for exactly the quarantined rows and null for
  everything else, guaranteed by the check constraint. A column that is
  meaningful for one status and structurally empty for every other is a column
  that does not belong in the shared table *by default*.
- **So: a filter on the read, and the column behind a flag rather than a second
  table.** Settled at `519895e` by reading `LedgerTable.tsx`, which is what this
  bullet used to defer. `showQuarantineGrounds` is off by default, so the general
  ledger list is unchanged; `QuarantinePanel` turns it on. `FinancialMainView`
  gained its sixth member at `e64c2ca`, placed with the first two because it reads
  Postgres. **This bullet is now history rather than plan; nothing here is
  outstanding.**

### Where the old numbering went

Items 1–10a and their commits are unchanged history and stay listed here.

1–7 done through `3784dbe`. 8 done, the Alex description, 1 September. 9 done,
suspect-amount detection, `0910d9f`. 10 done, per-transaction source locator,
`0d6b399`. 10a closed 1 September with no code; triage is out of the build.

11, correction storage, **is no longer blocked.** It maps onto Phase 2 item 10,
and the direction is settled in Standing decisions below.

12 is absorbed into Phase 1, which is now complete.

13, user-defined view tabs, is **not in the wiring plan** — new capability
rather than connecting built capability, so it stays parked. Two things, not
one: named persisted snapshots of filter state, and exposing source document
type onto the transaction row. **This interacts with a decision already
taken:** the financial page no longer persists which tab you were on.

14 money movement over time, 15 follow the money: both still parked, both still
new capability rather than wiring. 16 tracing and 17 exhibit tagging are **no
longer parked** — they are Phase 4 of the plan.

---

## Standing decisions, and what would reverse each one

**This section is not a queue of questions for Neil.** By standing instruction, a
session does not open by asking him to rule on things. Every entry below states
the direction the build takes by default, so a session can proceed without a
conversation. Each one also says exactly what evidence or instruction would
reverse it. Raise one with Neil only when the unit in front of you actually
turns on it, and then raise it oriented and with a recommendation.

**New: a route goes on the router whose permission it actually needs, and the
wiring plan does not get to decide that.** Every route on
`routers/financial_ledger.py` resolves to `("case", "view")`; every route on
`routers/financial_adjudication.py` resolves to `("case", "edit")`
unconditionally, and its docstring says so. So the question is never "which
router is this feature about" but "does this operation change the ledger or
describe it". `GET /api/financial/proof-standing` describes it, so it went on the
ledger router at `cbf163e` even though both the wiring plan and this file had
named the adjudication router as the natural home. On the adjudication router it
would have demanded the permission to change the ledger in order to report on
it — a person allowed to read a case would have been refused a count of what the
case contains. **What would reverse it:** nothing about a read. For a write the
answer flips, and the adjudication router's exhaustive route-set test exists to
make whoever adds one say what it is.

**New: a read whose cost is set by a machine writer is bounded and reports its
own total; a read whose cost is set by the evidence is not.**
`transaction_query.list_transactions` is unbounded, and stays unbounded, because
its size is the size of the bank statements someone actually produced.
`decision_log.list_case_decisions` is bounded at 100 by default and 500 at the
cap, because `reclassify_document` is written by the reconciliation stage on
every pipeline run, so the log grows without any person deciding anything and the
cost of an unbounded read is set by how often the pipeline ran. Wherever a read
is bounded, `total` is returned beside the page and counted over the **same**
filters, because a truncated history that does not say it was truncated is worse
than no history. **What would reverse it:** a decision log that stops taking
machine writes, at which point its growth is bounded by human effort like the
ledger's is.

**New: a fact that can be derived from a stored field is derived, but it is
derived once, in the service, not by each caller.** `by_machine` on a decision
record is the actor address compared with `RECONCILIATION_ACTOR_EMAIL`. It is not
stored, because a second home for the same fact drifts. It is also not left to
callers, because a caller that gets the comparison wrong shows a machine's
reclassification as a person's judgement, which is the most misleading thing that
log can be made to say. The comparison is case-insensitive and **on equality**,
never `in` — an address that merely contains the machine's is not the machine's.
**What would reverse it:** more than one machine writer, at which point the
service needs a set of addresses rather than one, but still one place that knows
them.

**New: an ordering across subjects claims only what its columns can support.**
`subject_sequence` is per subject, so one subject's 3 is not comparable with
another's 1; Postgres `created_at` is transaction-start time, so events written
together share it exactly. So a cross-subject read orders by `created_at DESC`
then by subject then by `subject_sequence DESC`: newest first at the resolution
the timestamp actually has, authoritative within any one subject, and **total**,
so paging cannot show a row twice. The docstring states plainly that two events
about different subjects sharing a timestamp are **not** claimed to have happened
in the order shown. `decisions.history` carries the same warning from its own
history: an earlier draft ordered by `created_at` with an `id` tiebreak, and that
"looked authoritative and was a coin toss." **What would reverse it:** a
monotonic per-case sequence being added to the log, which would make a true
cross-subject order available for the first time.

**New: a list that differs from the ledger list by one column is a flag on
`LedgerTable`, not a table of its own.** Three of that table's seven cells are
correctness rather than presentation — the amount cell marks a figure it could
not scale rather than printing a plausible wrong one, the balance cell says a
running balance was absent rather than leaving a blank, and every closed
vocabulary renders an unrecognised member loudly rather than going empty. A
second table is a second copy of all three, and the copy is what drifts: not on
the day it is written, on the day one of the three is corrected in one place
only. So `showQuarantineGrounds` is a prop, off by default, and the general
ledger list is byte-for-byte unaffected. **What would reverse it:** a
status-specific list needing cells the general ledger list has no use for, at
which point the shared table is carrying a second layout rather than a second
column and the copy has become the cheaper of the two.

**New: a panel whose copy is only true of one population fixes that population
rather than defaulting it.** `QuarantinePanel` sets `ledger_status=quarantined`
and types its `params` so a caller cannot pass it. This is not defensiveness
about a prop: `LedgerPanel`'s empty state tells a reader that quarantined rows
are outside the filter and to change the filter to see them, which is the exact
reverse of what was checked when the filter *is* quarantine. A panel that can be
repointed is a panel whose every sentence can become false. **What would reverse
it:** a screen that genuinely needs one panel over two populations, which would
mean the copy had been made status-neutral first, and status-neutral copy is what
`LedgerPanel` already is.

**New: "a person decided this" and "a check established this" are three-valued,
and the third value is not "a check".** `readQuarantineGrounds` returns
`decidedByPerson: null` for a member this build cannot read, surfaced as
`data-decided-by-person="unknown"`. `false` is the more trusted of the two real
answers — it means the ledger's own arithmetic against the source document — and
a member arriving from a backend one version ahead has not earned it. Same
reasoning as the closed-vocabulary rule it sits on top of. **What would reverse
it:** nothing; this is the unrecognised-member rule applied to a derived fact,
and if it ever looks like noise the fix is to teach the build the member.

**New: a cache refetch is decided on the wider of the two "did the row move"
readings; what a person is told is decided on the narrower one.**
`useRowAdjudication` invalidates the ledger when `applied` is true **or** when
this build's reading of the outcome word says the row moved. The two cannot
disagree on a backend of the same version, and `readRowAdjudication` already
raises `appliedDisagreesWithOutcome` when they do — but a disagreement must not
be settled at the call site by picking a winner. The costs are not symmetrical:
refetching when nothing moved costs one request, while failing to refetch when
something did leaves a row on screen in a list it has left, and a person reads
that stale screen as the ledger's answer. **What is reported to a person about
whether the row moved still comes from `applied` alone**, which is the standing
rule and did not change. **What would reverse it:** the disagreement turning out
to be reachable in normal operation rather than only across versions, at which
point it needs handling rather than absorbing.

**New: the rescue sentence travels in the response and is not written into the
adjudication log.** `QuarantineBasis.from_adjudication` stores its detail as
`"<actor>: <reason>"`, so anything appended to the reason is read afterwards as
words the person wrote. A machine observation attributed to a person is the one
thing an evidence log must not contain, and that outweighs durability here.
**The cost is stated plainly: the fact is on screen at the moment of the decision
and does not survive in the record.** **What would reverse it:** a durable home
for the observation that is neither the person's reason nor the row's
`before`/`after` columns — a third field on the adjudication event, which is a
change to `quarantine_transaction` and a schema change, not a change to this call
site. Worth doing when item 8 touches the adjudication log anyway.

**New: the rescue check is asked of every quarantine, not only suspicious ones.**
Whether a removal is legitimate is not visible in the arithmetic — a row proved
wrong by the statement's own chain *should* come out and the period *should* then
balance. So the check cannot be used as a filter and is not one. **What would
reverse it:** nothing short of a demonstrated performance problem, and the check
is one pass over a period's admitted rows.

**New: the check runs before the write, inside the same `try`.** Afterwards the
residual has already moved, and recovering it would mean adding the row's own
effect back onto the new figure — a reconstruction rather than an observation,
and wrong the moment anything else about the period changed in between. Being
inside the same block means a database fault reading the period is handled by the
same clause as a fault writing the row. **What would reverse it:** nothing.

**New: reconciliation is a fourth financial router rather than a route on an
existing one.** Decided by reading the two neighbours' docstrings.
`routers/financial_ledger` states that every route resolves to `case:view`
because none of them writes; the recompute writes.
`routers/financial_adjudication` states that every route resolves to `case:edit`
because all of them do; the read does not. Either merge would make an existing
module's stated rule false. **What would reverse it:** a decision to let a router
carry mixed permissions and drop those docstring claims, which would be a
readability judgement rather than a correctness one and is not worth making now.

**New: the recompute requires `case:edit`, not `evidence:upload`.** Nothing is
added to the case — rows already in the ledger are summed and the answer is
written onto periods already in the ledger. That is the case's own content being
edited, which is the bar the adjudication routes already apply for the same kind
of change. **What would reverse it:** the same new adjudication permission
category that would reverse the adjudication decision below; they should move
together.

**New: the read reports the stored column and never recomputes.** So a period
that has never been checked comes back `not_attempted`, and re-running is an act
a person takes. **What would reverse it:** a demonstrated case where a stale
stored figure is worse than an unstable one. Note the asymmetry — the current
choice is recoverable by pressing a button, and the reverse is not recoverable at
all, because a figure that was quoted and then silently recomputed cannot be got
back.

**New: a refusal during a sweep leaves the stored verdict alone.** It is not
reset to `not_attempted`. **What would reverse it:** evidence that a stale
`balanced` on a period whose data has since become unreadable misleads someone in
practice. The counter-argument, and why the current direction was taken, is that
resetting throws away a real result on the strength of a transient failure.

**The adjudication endpoints require `case:edit`, not `evidence:upload`.**
Decided by reading `postgres/permissions.py`, which defines only
`case:{view,edit,delete}`, `collaborators:{invite,remove}` and
`evidence:upload`. Ingest asks for the evidence permission because it **adds
evidence** to the case. Nothing is added by quarantine or release; an existing
row is moved out of every total or moved back into them, which is the case's own
content being edited. **What would reverse it:** a new permission category for
adjudication, which would be reasonable if Owl ever wants a role that can load
evidence but not change what counts. That is a schema and seeding change, not a
one-line one, and nothing needs it today.

**Quarantine's write path was built before its screen.** Not a resequencing —
item 6 is still item 6 — but a decision about which half of it comes first, taken
because **nothing in production wrote `ledger_status='quarantined'`**, so a
screen built first would have listed an empty set forever. **What would reverse
it:** nothing; the write path is landed. Recorded so the order is not later
mistaken for an oversight.

**Correction storage: a correction inserts a replacement row, it does not edit
the row.** This is the direction for Phase 2 item 10, and item 11 of the old
numbering is unblocked by it. Researched on 5 September by reading the source.

- **The relational ledger has no correction columns at all.** Verified against
  `postgres/models/financial.py`: no `amount_corrected`, no `original_amount`,
  no `correction_reason`. What it has is supersession —
  `ledger_status IN ('admitted', 'quarantined', 'superseded', 'rejected')` with
  `superseded_by_id` on `FinancialTransaction` (line 807) and the same pair on
  `FinancialSourceDocument` (line 321). The model docstring at line 21 states
  the intended behaviour outright.
- **Corrections today happen only on the graph side**, in
  `services/neo4j/financial_service.py:599`, `update_transaction_amount`. That
  is edit-in-place, and it is the competing design. It is not wrong for the
  graph; `projection.py` lists those properties in `USER_OWNED_PROPERTIES` and
  refuses to write them, so a projection run cannot undo a person's work.
- **The citation reference decides it.** `references.py` computes the reference a
  report cites a row by from the row's content, deliberately, so a row whose
  figure changed gets a new one. Under supersession that falls out for free.
  Under edit-in-place the reference either changes underneath a report that
  already cited it, or is frozen and then names a figure it was not computed
  from. `ref_id` also carries `UniqueConstraint("case_id", "ref_id")`, so the
  two designs collide rather than merely differ.
- **The cost, stated honestly:** two rows exist for one corrected transaction,
  and every reader of the ledger has to be status-aware. The ledger endpoint
  already defaults to `admitted`, so existing readers are correct by default;
  new ones are the risk.
- **What would reverse it:** an instruction from Neil, or a downstream unit that
  genuinely cannot work across a supersession pair. The graph's edit-in-place
  path is not evidence against it — the graph is not the ledger.

**Whether a correction re-runs the arithmetic: still not decided, and it is now
one item away from being decidable.** The proposal is that a correction re-runs
the balance identity and only a re-run that closes moves the proof class. It has
support in the source: `adjudication.py`'s `restated_opening` (line 332) and
`restatement_delta` (line 357). It is consistent with the settled rule that proof
class is computed and never set by hand. **But it makes a correction an event
that can change how much of a document is trusted, not a local edit.**
Reconciliation is now built, so half the machinery exists and
`reconcile_case(db, case_id, account_id=...)` is the call a correction would
make. **Proof class (item 8) still lands before the correction unit. Decide it
then, from the built code.**

**Removing `reingest` stands.** The override could not succeed for unchanged
bytes, and where it could succeed it would leave two contradictory readings of
one file in one case with nothing able to resolve them until `duplicates.py` is
wired at Phase 2 item 9. **Reversible at any time and cheap to reverse** — item
9 is the natural moment to revisit it.

**Content-hash de-duplication stays call-scoped.** `document_content_hashes`
disambiguates duplicate content within one `record_transactions()` call and not
across two calls. **What would reverse it:** an override existing. If `reingest`
comes back, this has to be answered in the same session, not after.

**The engagement period stays off the case.** The dialog asks for the window
every time. If a case ever grows a date range, the dialog **defaults from it and
keeps asking** rather than stopping, because a file can legitimately fall
outside the engagement period and the reader has to be able to say so.

**`exhibit.py` stays in the plan at Phase 4 item 15.** Its provenance is a
proposed build order rather than a stated Owl requirement, and that is recorded
so nobody later mistakes it for a requirement Neil gave.

**The financial page will say nothing about the two stores disagreeing until
Phase 3 item 12.** Explaining a disagreement before the thing that removes it is
built means shipping an explanation with a short life. **What would reverse
it:** a real case where the two visibly disagree in front of an investigator
before item 12 lands.

---

## Standing flags

- **CLEARED at `e655a0a`: `["financial-decisions", ...]` is now invalidated.**
  This flag read, at `62ff2de`, that nothing swept the key, so a user could
  quarantine a row with the panel open and watch the log fail to grow.
  `use-row-adjudication.ts` now invalidates `["financial-decisions", caseId]`
  alongside the ledger's key, gated on a `decisionWasRecorded` predicate so a
  response reporting no decision does not evict a good page. **It is still the
  only writer wired to this key** — supersession, restore, purge and
  reclassification all append to the same log server-side and none has a
  mutation hook in this build yet. That is recorded in the hook's docstring, so
  each closes its own half when it lands.
- **No live end-to-end run has ever been done.** See
  **Verification debt** near the top of this file. Neil has ruled that he will
  test a full working version himself when the system is ready; do not
  re-litigate it, and do not present green gates as evidence the system works.
- **Phase 1 is closed: a bank file can be sent to the ledger from seven places
  and the rows it creates are now visible.**
- **The balance identity now runs, but only through the API.** Nothing in the
  interface calls either reconciliation endpoint yet, and **nothing calls the
  recompute automatically** — not ingestion, not adjudication. So on a live case
  every period stays `not_attempted` until somebody POSTs to
  `/api/financial/reconciliation/run`. **That is deliberate for this unit** (the
  recompute is an act a person takes) **but it means the read will report
  `not_attempted` everywhere until a caller exists.** Do not read that as a
  defect in the arithmetic.
- **Whether ingestion should trigger a sweep at the end of a run is not
  decided and was not decided here.** It is the obvious next caller, and item 8
  (proof class) is the unit that will actually need one. Flagged, not parked.
- **CLEARED at `4e13821`: an admission is now consulted.** This flag read, at
  `5fa71a2`, that a decision could be recorded and that the processing route did
  not check for one, so a held file could still be sent with nothing behind it.
  `services/financial/admission_gate.py` is called from `process_db_files`
  immediately before the send, and all three routes that reach it return 409 with
  the file named and the finding attached. **The admission path now enforces**,
  subject to the one flag below.
- **NEW at `4e13821`: an admission is not consumed, and nothing in the schema can
  express consumption.** The gate asks whether an `admit_financial_document`
  decision **exists** for a file in this case, not whether an **unused** one
  does. So one recorded decision clears the same file for every later send, while
  `AdjudicationDecision` and `admit_case_file` both say an admission authorises
  **one** send. There is no link from an adjudication to a processing job and no
  per-file record of a send that a decision could be spent against. A `consumed`
  flag on the event would make an append-only log mutable, which is the one
  property the table exists to have, so it is the wrong fix. **What the gate does
  deliver in full: no held file reaches the document pipeline without a named
  person having said on the record that it should. What it does not deliver:
  every send separately authorised.** Say it that way when the item is described.
  Closing it is a **schema change** and a unit of its own; it is not a defect in
  this module and is not parked as a question. It is written into the module
  docstring and asserted as a test, so a change that closes it fails a test that
  says what changed.
- **NEW at `5fa71a2`: the engine has its own native-file refusal and no override
  channel.** `evidence-engine/app/pipeline/orchestrator.py` fails any job whose
  file it detects as native, and an admission recorded on the backend cannot
  reach it. So a file admitted on the `native` outcome specifically is recorded,
  sent, and then refused by the engine with a message naming the format. Nothing
  is lost and nothing is silent, but **for that one outcome the override does not
  yet take effect.** Closing it is an engine change, the engine requires Python
  3.12 and this sandbox has 3.10, so it **cannot be built or tested from a
  session** and needs Neil. Not parked as a question: the backend half is correct
  as built and the gap is in the other service.
- **CLEARED at `e655a0a`: the adjudication log is on screen.** This flag stood
  for five commits and read that the log was readable over HTTP, callable from
  TypeScript, readable as English, and visible to nobody. It said it would clear
  "when a panel renders it, not before". `DecisionsPanel` renders it, under a
  "Decisions" tab on `FinancialPage`, and a user can now see who decided what
  about a case's evidence and on what grounds. **Two things stay true and are
  worth carrying forward.** The page is a page: `total` and `truncated` are on
  screen precisely so a reader cannot take a hundred rows for the record. And
  `explain_balance_failure` still has no production writer (see the session
  detail above), so a live case cannot yet produce one and its absence from a
  case is not a defect in the panel.
- **The quarantine screen is reachable as of `e64c2ca`, and this flag is
  cleared.** It read, for four commits, that every part existed and none of it
  was reachable. That is no longer true: the "Held out" tab is in the tab strip,
  `QuarantinePanel` renders under it, every ledger row carries an action button,
  and `RowAdjudicationDialog` is mounted on the page and opened by it. The two
  calls, the reader, the hook, the dialog and the grounds column are all wired
  end to end. **What remains true and still worth stating: the ledger tab's own
  totals exclude quarantined rows.** That is the point of quarantine, but it
  means the held-out tab is the only place the excluded population is visible,
  and nothing on the ledger tab says a total is net of anything.
- **The write path reports when a quarantine is what makes a statement balance,
  and as of `66d1e67` something finally renders it.** The fact is deliberately
  not stored in the log, so if it is not on screen at the moment of the decision
  it is not anywhere. `readRescueOutcome` gives all four readings words,
  `readRowAdjudication` composes it in so a caller cannot read the outcome and
  quietly drop it, `useRowAdjudication` hands the composed reading back on both
  `data` and the `mutateAsync` promise, and `RowAdjudicationDialog` renders it
  whenever the reading has anything to say. **This is closed as a gap, and it
  converts into the keep-mounted rule:** the only copy of the fact lives in the
  dialog's mutation, so a caller that unmounts the dialog when the row leaves the
  list destroys it. **`e64c2ca` is the commit that had to honour that, and does:**
  the dialog is mounted on `FinancialPage` outside `Tabs`, not inside either
  panel, so an invalidation that empties the list the row came from cannot take
  the answer with it. Two tests hold it, one per panel. Anything that later moves
  the mount point back inside a panel breaks this silently.
- **`QuarantineBasis.from_proof` is still unreachable from HTTP,** by design —
  computed grounds must not be settable by a person. So on a live case every
  quarantined row's reason reads `adjudicated`, and the second value in that
  column arrives with item 8. **Do not read the single value as evidence the
  distinction is not implemented** — the grounds column, its `decidedByPerson`
  classification and the tests over all five members are all built and, as of
  `e64c2ca`, on screen; there is simply only one member a live case can currently
  produce. **This file predicted item 8 chunk 3 would produce the second one. It
  did not, and no unit currently scheduled will.** Chunk 2a (`5fa71a2`) could
  not, because an admission is a decision about a file rather than a row. Chunk 3
  (`cbf163e`) could not either, for a reason worth writing down: it turned out to
  be a **read**, a census of where a case's evidence stands, and a read cannot
  quarantine anything. Producing a `from_proof` basis needs something that
  quarantines a row **on computed grounds** at ingestion time, and item 8 does
  not contain such a thing. **This flag now has no owning unit.** It stays open.
- **`localisation.py` has no production caller except `_rescue`.**
  `localise_period` and `current_identity` are reachable and tested but nothing
  in the product asks them anything yet. **This file expected item 8 chunk 3 to
  be the first caller. It was not** — `cbf163e` reads proof class and its four
  permissions and has no reason to localise a period. Chunk 2a came and went
  without touching it too. **There is no longer a unit expected to call it.**
- **The Neo4j financial view is not a projection of the ledger.**
  `projection.py` has zero production callers. The two stores can disagree and
  nothing detects it. Phase 3 item 12 closes this. **Do not describe the graph
  as derived from the ledger until it is.** Note that quarantining a row and
  reconciling a period both change the ledger and **do not** touch the graph, so
  this gap now has two more ways to show itself.
- **A run whose process died is now closed, but only by the loop.** Six hours
  stale, five minute interval. **Until it fires, a dead run and a live one are
  indistinguishable through the API**, deliberately: the read declines to guess.
  The threshold is a knob (`FINANCIAL_RUN_STALE_AFTER_HOURS`).
- **The notice is only on the ledger tab, and the attempts list only on its
  own.** Deliberate for now, because the other three tabs read the graph, but it
  stops being defensible at Phase 3 item 12. **Revisit the mounting then.**
- **Nothing on screen explains that the tab strip spans two stores.** Deliberate
  and already ruled. Listed only so it is not rediscovered as an oversight.
- **No row in the corpus carries a running-balance column.** 30,570 rows across
  325 documents. So on real data **every** row will show "No running balance".
  That is the component working, not failing. **This bears directly on
  reconciliation:** a period whose balances are absent reconciles `unavailable`,
  not `unbalanced`, and on the current corpus that will be the common answer.
- **P0 is unreachable on the current corpus.** No document carries its own
  control totals in a form that qualifies.
- **Half two has only ever run against synthetic ledgers.**
- **The item-1 geometry machinery IS reached in production** at the
  evidence-engine layer, verified end to end 1 September.
- **The alembic migration `20260902_evidence_table_geometry` has not been
  applied to any real database from a session** — the sandbox has no Postgres.
  First deployment needs an `alembic upgrade head` on Neil's side.
- **Disk: `/sessions` is completely full and this is the first thing to check
  every session.** Measured again at `2eefc4d`: 9.8G of 9.8G, **zero bytes
  available** — unchanged for ten sessions, against 129M eleven sessions ago.
  Root is at 99% with 120M free. **`/dev/shm` does not start empty and 1.5G free
  is not a safe assumption** — an older wording here said it was. Measured at
  `4e13821`: 2.0G total, **1.7G used, 244M free**, and it does not start empty.
  It was 398M one session ago and 1.5G before that, so **no free-space figure in
  this file survives a session.**
  Full breakdown, including what is leaving the leftovers behind and how fast, is
  under **How to run the browser gate** above. Measure it with `df -h /dev/shm`
  at the start of any session that needs room rather than trusting a figure in
  this file.
  - **This does not block the repo, and an older wording implied it did.**
    `df -h` on the repo path shows a **separate virtiofs mount with 35G free**
    (36G at `e64c2ca`, 37G at `19bffae`; it drifts a little and is nowhere near
    tight). The working tree writes normally and the **frontend gates run
    normally**, provided the vite cache goes to `/dev/shm` rather than
    `CLAUDE.md`'s `/tmp`, which is on the 99%-full root.
  - **The backend suite is runnable** via the `/dev/shm` bootstrap recorded
    above, and that workaround was exercised in full at this head: bootstrap,
    baseline, and two complete suite runs, all clean. It is reliable. A session
    that touches Python must still budget the twenty seconds for the bootstrap
    rather than assuming a warm environment — **`/dev/shm` does not survive
    between sessions**, so it is a fresh install every time.
  - **The browser gate IS runnable, but at `cbf163e` it stopped being
    installable and had to be borrowed instead.** The "roughly 700M" figure this
    bullet once carried was never measured; the Chromium headless shell is
    **106.4 MiB**. It used to install into `/dev/shm` in seconds with
    `PLAYWRIGHT_BROWSERS_PATH` and `TMPDIR` pointed there, and ran green that way
    at `e655a0a`. **At `cbf163e` there was 93M free falling to 79M, so 106.4 MiB
    no longer fits.** The gate still ran, green in 3.45s, by pointing
    `PLAYWRIGHT_BROWSERS_PATH` at a **928M install another session left behind**
    at `/dev/shm/pw-inspiring-peaceful-brown`. That directory is not this
    session's and cannot be relied on to survive; verify it exists and is
    executable before the gate, and read **How to run the browser gate** near the
    top, which carries the check and the fallback position.
  - **None of this is Loupe's doing and no session can clear it.** The space is
    held by other session directories that are not readable or removable from
    inside a session. **This needs Neil to reclaim space on his side**, and
    until he does, every session starts by working around it.
  - The repo mount has room but is Neil's tree, and the workspace denies
    `unlink`, so anything staged there could not be removed. **Do not use it as
    scratch.** Use `/dev/shm`.

---

## Defects raised and not yet ruled on

Small, real, none blocking:

- **`reconcile_period` mutates the period before it validates.** It assigns
  `reconciliation_status` and then calls `_fits(...)`, which can raise
  `LedgerOverflowError`, leaving a half-written verdict in the session.
  `reconcile_case` defends against it with `session.expire(period)` and there is
  a named test for the path, **so nothing is broken today** — but the ordering is
  a trap for the next caller, and the next caller is item 8. **Direction: swap
  the order inside `reconcile_period` when item 8 touches it**, rather than
  making every caller remember to expire.
- **`docs/loupe-wiring-plan.md`'s premise for item 6 is wrong.** It says
  quarantined rows are written today and never shown. Nothing in production ever
  wrote one. **And item 7's premise was wrong in the same way** — the plan
  treats reconciliation as something that runs and needs surfacing, when
  `reconcile_period` had no reachable production caller at all. The plan text is
  left in place as history. **Do not build from those sentences.** Assume other
  items carry the same kind of error: the plan describes intent, and the source
  is what is true.
- **The graph's correction path takes the new amount as a `float`.**
  `services/neo4j/financial_service.py:599`. The ledger side handles money
  exactly through `Money`, so a corrected figure entered on the graph and a
  total computed from the ledger can disagree at the cent. **Direction: fix it
  as part of Phase 2 item 10.** If anything starts relying on graph corrections
  before then, fix it immediately instead.
- **`IngestionRunHandle.terminate()` does not check the row's stored status.** A
  run the reaper closed as `failed` that then turns out to be alive and finishes
  will overwrite the status with `completed` **while leaving the reaper's
  abandonment text in `run.error`.** **If the six-hour threshold is ever
  lowered, fix this first.**
- **`evidence:process` and `evidence:delete` are asked for by routers and are
  not defined in `postgres/permissions.py`.** Whether those routes are
  therefore open, closed, or handled elsewhere was not established, and it
  should be before anyone relies on them.
- `evidence-engine/tests/test_pdf_table_geometry.py::test_the_summary_agrees_with_the_payload_it_summarises`
  fails against current code: it asserts the summary's exact key set without
  `by_table_source`, which `geometry_summary` has emitted since `3784dbe`.
- Model class is named `AdjudicationEvent`, not `Adjudication` (`ef9e33d`).
- Bulk processing above 50 files cannot work: `MAX_BATCH_SIZE = 50` against list
  paging at 250.
- 11 Capital One pages carry a full-page white image XObject, most likely
  whole-page redaction.
- `merging_properties` missing from `_ACTIVE_JOB_STATUSES`, plus a silent
  fall-through in `_sync_db_record_from_job`.
- `safe_float` does `round(f, 2)` and defaults to `0`.
- The `7d8289b` commit message understates what the commit did.
- Append-only is not enforced at the database.
- The p3 early-return limitation.
- `_get_dataset_metadata` uses all-or-nothing legacy detection.
- `execute_cypher_batch` takes unparameterised strings.
- `get_financial_transactions` compares `n.date` as a string.
- `RECOMMENDED_CONSTRAINTS` and `RECOMMENDED_INDEXES` need out-of-band
  application.
- Two defects in the mutation harness.
- `scripts/categorize_transactions.py:443` hardcodes `national telegraph`.
- `ProcessConfirmDialog.tsx` contains dead code.
- `frontend_v2/node_modules/.__dom_probe_leftover` left behind.
- The engine docstring in `evidence-engine/app/pipeline/pdf_extraction.py` claims
  table text is byte-identical to the pre-geometry path; false whenever the
  recovery pass replaces a `table_rectangle_only` reading.
- Recovered text-alignment chunks collapse empty cells in the `" | "` join and
  sweep footer prose into the table chunk. Geometry unaffected; full diagnosis
  in the `72d1b1a` revision of this file.
- **`docs/loupe-wiring-plan.md` lines 117–123 are superseded** by the work and by
  two rulings. Left in place as history; do not act on them.
- **The wiring plan names `_cleanup_stale_chunks` as the loop shape to copy.**
  It is the wrong precedent (no error handling); `poll_forever` is the right one.
