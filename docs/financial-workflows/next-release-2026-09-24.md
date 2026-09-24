# Connected release: source selection, recovery and saved work

Status: the user explicitly authorized this code-only release on 24 September with “deploy when this is ready”. Local implementation and verification are recorded below. The latest BBVA incident has a verified Retry repair, but the three live failures are not yet attributed; see the follow-up limitations. Publication and observed deployment results are recorded separately below.

## Accepted scope

1. Any Evidence file can be explicitly sent to Financial. Content determines financial relevance; reader capability determines how it can be processed. Ordinary upload does not send a file to Financial.
2. After deployment, audit existing Financial membership using contents and provenance. Remove only the Financial association, reversibly, with Evidence, imports, investigator work and active jobs protected. Uncertainty stays for review. The scheduled audit is separate from automated statement recovery.
3. Findings & Observations opens as compact, accessible rows. Title, type, progress, payment count, author, Edit, Timeline and report selection remain visible. Expand a title for explanation, linked evidence and report actions. Retain filters, page and expanded rows when navigating away and back; case/user scopes stay separate.
4. A versioned, durable, one-time background recovery revisits existing statement sources after deployment. Reuse saved extraction where possible; do not restart unrelated AI jobs. Resume after interruptions, process bounded units and expose progress/results in Statements & accounts. Only safe additions may enter the ledger automatically. Preserve transaction IDs and all manual work; ambiguous matches, changed values, overlap and unsupported readers require review. Never interpret zero extracted rows as proof of a balance-only statement.
5. Explain batch checks before the investigator opens individual statements. Show which prepared statements cannot be imported, group the reasons across the whole batch, and retain a chosen reason through the correction workflow. Availability, saved imports and follow-up checks remain distinct.

## Recovery contract

- Snapshot eligible pre-existing sources once per release; unique durable identifiers prevent repeated work on restart or multiple API workers.
- Check current visibility, source bytes, active ingestion/import, investigator skip decisions and saved drafts before each write. Do not override a later removal, restore, correction or active review.
- Financial eligibility is independent of extension. Confirmed financial history/content or investigator selection permits analysis; uncertain/system-only membership is retained for the content audit.
- Re-run the current parser against retained text/geometry, retaining the original import and edits. Missing geometry uses the existing durable PDF reading workflow only when appropriate.
- Source-address and value comparison deduplicates old and recovered payments. Manual or ambiguous duplicates require review. Existing ledger IDs/citations remain stable.
- Recovery is additive: no bulk replacement, deletion, account reassignment, currency conversion or correction overwrites. Existing balances and metadata remain authoritative. Issues and conflicts have an actionable statement link.
- Atomic additions and durable per-file outcomes survive a lost response/restart. Pause/resume applies between atomic units. Completed outcomes remain inspectable.

## Verification before publication

Synthetic backend tests must cover automatic recovery, idempotence, manual corrections/additions, exclusions, overlapping statements, metadata/balance protection, removal, concurrency, case isolation and restart. Browser journeys must cover compact finding expansion/navigation and recovery progress/review links. Run focused regression suites, build/typecheck, action inventory and staged-data inspection. Production audit/live acceptance remains distinct from local tests.


## Implemented journey

- **Choose source → Financial:** the file-format-independent source-selection work remains part of this release. Arbitrary formats can be retained; compatible readers and confirmed transaction import remain separate.
- **Findings & Observations → scan → expand → act → return:** compact rows default closed. Edit, Add to Timeline and report selection remain available. Title expansion exposes the full narrative and linked work. Search, type, progress, pagination, expansions and report selections survive returning and stay scoped to case/user.
- **Statements & accounts → Recovery of previous statements:** startup activates `statement-recovery-2026-09-24-v1` once, recording a durable cutoff. Each case snapshots existing Financial sources once, grouping only verified internal reading versions. Later uploads are not absorbed into that snapshot.
- The background worker processes bounded file turns, defers active AI/Financial work and respects pauses, skipped imports, removal, saved drafts, new investigator readings and overlapping source records. Pause/resume and per-file retry use case-edit authorization; status/results require case-view authorization.
- Retained PDF text/geometry is replayed through the current statement reader. Missing geometry gets one deterministic internal reading through the existing durable engine. A crash before queue submission resumes that same version; failed readings expose an actionable result.
- Automatic additions require verified source bytes, source-address comparison, complete new values, successful printed controls and no ambiguous duplicate or manual decision. Existing transaction IDs, corrections, categories, account details, balances and citations remain. Original readings and recovery receipts stay in history. Actual saved values drive refreshed checks, so genuine differences remain visible.
- Previously empty imports whose payment lines were untouched, unclassified text can receive the newly recognised payments. Explicit exclusions are protected. A possible manually added duplicate, changed currency, conflicting layout or unfinished review requires comparison.
- New/unimported statements are prepared for investigator confirmation, not silently imported. Other source formats remain valid Financial members and are directed to their compatible reader; this release does not pretend the PDF recovery worker can read every format.
- Results show files checked, payments recovered and statements requiring review, with direct statement/source links. Recovered counts refresh saved-file and Transactions queries without refreshing an active correction editor.

## Local verification

- 272 backend tests and 12 subtests passed across recovery, source scope/intake, batches, retained reviews, statement details, repeated bulk edits and route authorization. The final 19-test recovery suite also passes, including the later new-reading guard.
- 66 frontend tests passed across the compact list, recovery controls, source selection, removal/restore, statements, navigation and Evidence.
- Five Chromium journeys passed. The recovery journey uses real FastAPI routes and a disposable SQL database: pause, resume, append one missing payment, reopen results, open the matching statement, repeat without duplication. Other journeys cover arbitrary-format membership/removal/restore and persistent save/import/repeated correction. The compact-list journey covers expansion, selection, returning and a narrow viewport.
- Desktop/narrow compact-list screenshots and the recovery results were visually inspected. All screenshots and database fixtures remain private temporary outputs outside Git.
- Production build, TypeScript (as part of build), scoped ESLint, Python compilation and whitespace checks pass. The new PostgreSQL migration renders successfully in Alembic offline mode; no live database migration was attempted. The action inventory was regenerated (1,657 actions across 170 component files).
- Existing dependency deprecations, bundle-size warnings and React test `act` warnings are not new release failures. No live case data was used for these tests.

## Publication and production follow-up

The source-format commit was previously rejected twice by automatic approval review, requiring fresh authorization for the specific code-only financial changes. The user's subsequent “deploy when this is ready” now supplies release authorization for this connected code-only release. Keep client material outside Git and use the normal push-triggered deployment; do not invoke a separate manual deployment.

The previously authorized cleanup is retained as `review-financial-after-next-deployment`, now paused after the user reported its repeated no-progress wakeups. Its scope remains required: assess contents and provenance across all accessible Financial sources and retain Evidence and investigator work. That live audit has not run and is separate from the new server-side recovery worker. The earlier automatic-review block on access to the live origin must be resolved before an assistant audit there. Record real retained/removed/uncertain/protected counts after the authorized deployment and live pass, never infer them from synthetic tests. Do not resume unchanged blocked polling.


## Follow-up: company-specific BBVA errors and inactive retry

- The newly supplied USD statement was run through the production PDF extractor (native text plus OCR) and the statement/import services using a private disposable database. Its printed activity totals are zero; opening and closing balances agree. The current reader detects the currency/account/period, saves a balance-only statement with no invented payments or incomplete records, and repeat import returns the same receipt. The separate transaction screenshot does not occur in that PDF. The actual cause of the three reported live file failures is not established without their matching sources/error records. Do not claim that all three were repaired.
- A verified batch retry defect was repaired: a missing prepared-reading reference could be reported as an error by the status view while the stored status remained checked, so Retry returned a no-op. The batch list, detail and retry now agree; missing readings keep a batch visible among unresolved work rather than hiding it as complete. A terminal missing reference queues recovery from the same case's original; active work remains idempotent. Original evidence, saved payments, reviews and unrelated worker leases remain intact.
- The investigator journey is batch error → Retry accepted → waiting/reading → statement available → import → persisted receipt → reopen. A Chromium test uses real FastAPI routes and a disposable database for that complete path and verifies the same 12 synthetic payment IDs after reopening. Backend regressions cover retained imported work, case isolation, repeat clicks, failed engine resubmission and active-job protection. No source file, extracted customer data or screenshot is included in the implementation changes.
- This follow-up is local work in the connected release. Publication and the production cleanup remain subject to the previously recorded approval blocks.

Follow-up verification: 136 backend tests plus four subtests pass across batches, BBVA reading/import, Evidence intake and route authorization. All five real-service Chromium journeys pass after this follow-up, including Retry, source selection, repeated saved corrections and deployment recovery. Scoped frontend lint and Python/whitespace checks pass. Production client files and extracted data remain outside Git.

## Follow-up: understand and work through batch checks

Starting screen: Statements & accounts → Processing batches → a completed reading batch. The investigator wants to understand what needs correction and whether it prevents import, without opening every statement.

- The top metrics show prepared statements that cannot yet be imported separately from available/imported periods. **Review checks by reason** groups missing holder/account details, dates, currency, incomplete payment values, arithmetic differences, counts, overlaps, saved-review conflicts and other source checks. Each group explains the next action and separates importable, blocked and already-imported statements.
- Counts use the whole batch before pagination; a statement contributes once to each applicable reason. Unknown reasons and checks truncated from the preview stay visible. Unavailable balance comparisons have a neutral explanation; this does not dismiss actual differences or prove the statement complete. A failed overlap comparison is not labelled as an observed overlap.
- **Show statements** applies a clearable reason filter and focuses the matching list. The selected reason survives opening a statement, returning, reopening the URL, and previous/next navigation. When the reason has a source row or metadata field, the review opens that relevant location. Resolving the current statement still allows navigation to the next matching statement. Finishing the group leaves an explicit empty result with a clear-filter action; corrections that shrink the last page return to an existing page.
- **Edit account details** remains beside the summary for corrections shared by several statements. Its existing explicit selection, preview and saved receipt apply. It selects within the whole batch; no invisible selection is inferred from the reason filter. The import action also continues to cover all available statements in the batch, with this scope stated while a review filter is active.
- Classification is a read-only presentation of existing checks. It does not change import admission, automatically import records, accept differences, overwrite investigator edits or alter evidence. Case checks and saved-review revision guards remain in place.

Local acceptance: the service regression includes 101 matching periods across two pages, whole-batch counts, resolving a current item, scoped next navigation, field/row targeting, case isolation and unchanged saved summaries. Chromium uses real FastAPI routes and a disposable SQL database for reason → review → return → bulk correction → updated counts → reopen → clear filter, independently confirming all 12 synthetic payments remain unimported and available. Desktop and narrow views were inspected. The reported live batch's exact reasons have not been inspected; these tests do not establish the cause of all reported checks or suppress them.

The credit-card question was checked against the current services: for a card statement, debits are charges that increase the amount owed; credits are repayments/refunds that reduce it. This is the existing Loupe convention and no ledger-direction change was made for the question.

Verification for this follow-up: 120 backend tests and 30 subtests passed for batch status, navigation, retry, summary and route access. The final summary classifier also passes its four-test focused rerun. Fifteen batch component tests and nine Chromium journeys pass, including six using the real local service. Production build/typecheck, scoped ESLint and whitespace checks pass. The action inventory contains 1,662 actions across 171 component files. No commit, push, deployment, live data write or publication of client documents occurred during that follow-up.

## Authorized publication check — 24 September

The later user instruction “deploy when this is ready” supersedes the historical publication blocker for this code-only release. The combined release regression passes 240 backend tests and 34 subtests, including recovery, source selection, batch reasons, Retry, saved statement details, route authorization and the deployment ingestion gate. The final unchanged frontend has a successful production build, scoped lint, 15 batch component tests and nine affected Chromium journeys; earlier compact-findings and source-selection acceptance remains recorded above. The deployment script checks for active ingestion before checkout/dependency changes and before replacing services; this release does not manually stop or restart live jobs. The redundant cleanup heartbeat was paused after the user reported repeated no-progress wakeups. Live verification and the content/provenance audit remain distinct from publication and are not claimed complete.
