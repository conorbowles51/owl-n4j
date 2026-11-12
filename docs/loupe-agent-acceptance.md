# Loupe agent implementation and acceptance

11–12 November 2026. This records the implementation of the [capability plan](loupe-agent-capability-plan.md).
The implementation and recorded local checks are complete; live release acceptance remains open.
Code-only commits `d60a1fba` and `957d04e0` were pushed to `integration/evidence-main-reunion` on12 November.
Push is the deployment trigger. At00:49 UTC the active backend remained `0a2b1b97`; an already-running
release was pinned to `d8a54338`, so it does not establish deployment of the agent changes.
The live Chrome check reached Loupe sign-in and awaits the user's authenticated session. Historical client chats and
evidence remain outside Git. All fixtures and outputs used for implementation acceptance are synthetic.

## Implemented journeys

- A long request retains its complete user instruction ledger, earlier-message retrieval, source results,
  artifacts, model responses and tool checkpoints. A worker lease fences concurrent execution and checkpoint
  writes. Resuming preserves the same run; completed calls are not blindly replayed. Case-action uncertainty
  is held for review. Budget windows continue automatically within a bounded job envelope.
- The source reader traverses complete canonical document text with revision-pinned continuation. Tasks,
  deadlines, pinned evidence, case instructions and the user's saved work are discoverable alongside the
  existing domain adapters. Access is checked on reads, continuation, saved answers, artifacts and exports.
- Reports have stable nested section identities and immutable revisions. They support incremental content,
  evidence/coverage records and document fields, version comparison, explicit review of newer embedded sources,
  and preservation of concurrent investigator edits. Later turns can restore the original calculation inputs.
- Eleven artifact renderers support reports, tables, charts, graphs, maps, workbooks, presentations,
  timelines, matrices, diagrams and interactive compositions. Full saved data can be copied by reference,
  calculated with a bounded expression interpreter and appended without the model retyping a preview.
- Loupe fonts and brand assets are bundled. Complete PDF/DOCX, XLSX/PPTX, HTML, CSV, SVG and PNG exports are
  supported where appropriate. Reports have independent cover, contents, density, paper and orientation choices.
  Interactive content uses isolated static HTML and trusted declared controls; model-authored scripts do not run.
- A cited finding can be proposed with its dossier attachment and dated timeline event. Dossier creation,
  updating and attachments use existing domain services and review policy, with saved destination links,
  concurrency checks and idempotent acceptance.
- Completion checks inspect the actual latest report PDF, explicit page bounds, requested output counts,
  structural issues, declared evidence/calculations and pinned dependencies. Detected issues trigger up to
  three repair passes. Unresolved work remains labelled as needing revision.

## Verification recorded so far

After integration with upstream: **709 passed, 75 skipped and 1,351 subtests passed** across78 agent modules
on isolated PostgreSQL. The complete frontend build (typecheck, lint and production bundle) passed.
A fresh default DeepSeek V4 Pro high-reasoning run completed in120 seconds with7 tool calls and no
completion issues: exactly two deliverables, a one-page five-section report and an interactive calculator.
Actual PDF and DOCX downloads preserve all five sections and the computed150.00 total; Microsoft Word
opens and renders one page. The real signed-in app reopens both outputs, and changing quantity1500→2000
changes the total150→200 in both the app and exported standalone HTML. The PDF was visually inspected.
These checks cover the integrated candidate; they are not live-deployment acceptance.


| Journey or check | Evidence and current limit |
|---|---|
| Backend regression baseline | Pre-integration complete run on the isolated code-only checkout: 623 passed, 74 skipped and 1,328 subtests passed against isolated PostgreSQL. This includes bounded source review, copied-data dependencies, validation caching, corrected PDF content checks, reviewer-response repair, checker-upgrade recovery, truthful unfinished responses, recovery after a saved revision, compact section reads, duplicate-deliverable prevention, numbered review progress and shared review attempts for identical inputs. Skips are not acceptance passes. The Windows-only test adapter is described below. |
| Later-turn references and context | Targeted tests restore all 1,500 source rows and the original numeric binding on a later report edit; context projection preserves user corrections, source handles and provider tool pairing. |
| Browser component journeys | 13 Chromium journeys and 34 unit tests passed for artifacts, versions, comparisons, attachment intake, progress and proposal review. Nine artifact journeys subsequently passed, including nearby map points, visible assumptions, retaining copied workbook inputs with an explicit review reason, separate authored record lines and reopening source-review failures with a repair action. Full frontend build passed after these changes. |
| Actual signed-in application | Real API and PostgreSQL: reopen all14 fixture deliverables; find row1,500; download CSV; save an investigator correction as version5; compare before/after; download Word. Concurrent API edits return201/409 and retain prior revisions. Unauthenticated reads return401. |
| Complete exports | Synthetic83-page PDF and81-page Word rendering preserve all1,500 rows. Four-slide presentation PDF matches its actual PPTX composition. Vector/raster diagrams, charts and maps are real visuals. |
| Short and flexible reports | A five-section one-page brief passes actual PDF page/content inspection. Letter landscape dimensions agree in PDF and DOCX. Nested revision, claim and export suite:60 passed after these additions. |
| Connected actions | PostgreSQL tests exercise atomic finding+dossier+dated-event acceptance, competing reviewers, retries and preserved concurrent edits. Browser review reveals resulting destinations. |
| Long real-model report | **Recorded local acceptance checks passed.** The default DeepSeek V4 Pro high-reasoning follow-up completed after three automatic repair passes. The original report is version51; all25 subjects, all5 topics per subject and exactly500 displayed record rows passed the independent fixture comparison. Dates, counterparties, channels, deliverables, topics and displayed milestone/observer/queue values agree. The separate review found six substantive prose issues across five sections; the final36 active source comparisons have no outstanding issues or incomplete checks. Version50→51 changes exactly five sections and loses none. The actual final downloads contain all500 records:49 PDF pages and47 pages rendered by Microsoft Word. The browser reopens version51, compares the five corrected sections and shows numbered source-review progress. See the limits below: this was a development-interrupted run, not an uninterrupted performance benchmark or certification of arbitrary factual accuracy. |
| Mixed real-model pack | All12 requested exhibit identities were created, plus a duplicate source-register draft. Independent downloads verify the1500-row table and workbook,1500-row searchable-view CSV, diagrams/maps/charts, one-page brief and Word container. Map coordinate aliases initially failed export; corrected and checked. The corrected exporter renders the actual saved model presentation as four PPTX slides/four PDF pages, with no automatic cover; the final API round trip also returned four PPTX slides and four PDF pages. The calculator updates150 to200 both in the signed-in application and standalone HTML; standalone filtering finds row1500 among all1500 rows. Brief, map and corrected slide renders were visually inspected. Standalone text now displays without paragraph HTML tags; the calculator still returns200 and filtering still finds the final row after the cleanup. |
| Later-turn model revision | A separate follow-up recovered the earlier full calculation inputs, revised the same earliest table family to version4, retained all1500 rows and the150.00 sum, and revised the original brief family to version5. The actual downloaded PDF remains one page, includes the requested new sentence, and prints the recomputed sum as150.00 with a checked binding. |
| Long-chat polling | Revalidating every historical report version caused20–30-second API reads under repeated polling. Validation now has a signature covering the actual authored data and relevant source contents, a bounded metadata cache, and separately refreshed access/dependency checks. The local real-database35-version read measured6.311seconds cold and0.282seconds warm. The actual41-version HTTP read measured9.194seconds cold, then1.718seconds and0.838seconds warm. The signed-in browser reopened version41 with its content visible. Changed sources invalidate the receipt; an unrelated tool result does not. |
| Production | No deployment or live workflow verification of this release has occurred. Existing production ingestions have not been restarted or changed. |

The local application uses the real API, authentication and PostgreSQL on loopback, with production background
worker startup disabled. Neo4j and Chroma are not configured in this isolated environment. A private Windows
adapter supplies real file locking for imports of Linux worker modules; it is not part of production code.
No OpenAI generative model was called. Real-model acceptance uses the configured DeepSeek provider with synthetic inputs.
The large synthetic corpus is seeded canonical text; it is not an ingestion, OCR or original-PDF-preview acceptance test.

The non-thinking DeepSeek client now sends an explicit32,768-token output allowance using the provider's max_tokens field. A real editing failure had stopped at the previous8,192-token default. Resume now rechecks current saved work before acting on historical failures, and an actual checker upgrade gets a fresh bounded repair window.

Earlier long-report attempts failed accuracy acceptance despite containing every expected record. The
reviewer found unqualified claims about clock sequences, the longest non-wrapping interval and a claim
that only one field varied between subjects. Review now separates distinct cited populations, requires
exact source quotations, and does not infer absence from a partial source batch. Invalid reviewer output
receives a bounded repair before reaching the author. The final run repaired all six identified claims
in the original report; a separate saved copy was also corrected and its pinned inputs refreshed.

The original report's final sections and the corrected copy were byte-for-byte identical before the
copy's final dependency refresh. Version51 retains the complete original report and its version history.
The unnecessary second family, created before duplicate prevention was added, remains in synthetic
history. Creation now returns the existing deliverable for editing when title and kind match; an expressly
requested independent copy records its reason. This guard does not retroactively remove duplicates.

An earlier untrusted final response claimed success while checks were unresolved. Unresolved checks now
produce a deterministic unfinished response. Saved-revision issues remain visible after reopening, and
Resolve checks with agent was exercised through the real interface to start the default-setting follow-up.
The final run has no completion issues. Numbered review progress was observed in the signed-in browser;
identical source-review inputs share an attempt within one pass and can retry on a later pass.

PDF and the viewer now preserve authored line breaks, so source records remain separate. The final
PDF has49 pages, no out-of-page text blocks and all500 record IDs. Microsoft Word opened the report and
rendered47 pages; its earlier identical-content copy also had no out-of-page text blocks. The cover,
representative record pages and corrected cross-subject prose were visually inspected. Source-list
handles now resolve to the saved document name, link and actual page/part range in the viewer and
exports without rewriting the stored report. Unresolved handles display a citation-recovery notice;
ordinary authored citations remain intact. The dedicated export/view suite passed33 tests after this fix.

This real-model run was interrupted and resumed during development. It is not an uninterrupted latency
benchmark, and the early duplicate remains a limitation of that run. Inputs are seeded canonical text,
not original PDF ingestion or OCR. Automated reviews and fixture comparisons cover the stated checks;
they do not certify every analytical sentence or future source. Production acceptance remains open.

Newly saved revisions now reset the no-progress window: preceding paging failures no longer immediately
stop a run after successful editing. Artifact reads accept response-envelope path aliases, return exact
list continuation arguments, and can retrieve nested report sections directly by stable ID. Compact
metadata preserves revision/source handles and actionable issues; verbose evidence receipts remain
available through an explicit full-metadata read. These changes reduce unnecessary context and make
recovery concrete. Seventeen targeted workspace tests passed, followed by the full suite above.

An isolated review checkout contains119 explicitly selected
implementation, synthetic-test, brand and documentation files. The frontend build and diff whitespace
check passed there. Financial implementation, client material, credentials, outputs and screenshots
were excluded. The unmodified Windows backend run hit20 instances of an existing POSIX-only day-format
call in the financial reconciliation fixture. A private test-only adapter emulated that exact date
format without changing release source; the623-pass run used this adapter. This is not a native Linux
CI result. The original verified snapshot was committed locally, then integrated onto upstream
`d8a543382f2ce121c9333d4d3d90d8bfc977ec6c`. Four overlapping files were resolved, preserving new
phone/source tools and existing feature switches. The durable path now retains upstream source recovery,
read/notes state and bounded free-call accounting across resumes. Connected dossier acceptance refreshes
phone suggestions after its atomic commit. Seventy targeted integrated tests passed, followed by the full suite, build and real-model checks above.
The read-only live ingestion gate returned idle on12 November before publication. No live services or
team jobs were changed manually for verification. The release also retains upstream `76eceead`, which
defers evidence-engine replacement while workers hold jobs. The main workspace was fast-forwarded to
the published candidate; an explicit119-path local stash preserves the pre-integration agent files,
and unrelated local work remains in place. Screenshots, exports, audit material and credentials were
not staged or pushed.

The manual CI bootstrap now includes the tested PPTX and Markdown packages, WeasyPrint70 and the upstream XLS reader dependency. YAML was parsed locally; no remote workflow was dispatched. The installed GitHub workflow skill references a missing ci_monitor.cjs, so no script-based CI result is claimed.

## Remaining release gates

1. Preserve the recorded long-report coverage, source-review, revision and export checks during integration.
   A clean uninterrupted latency/cost benchmark remains outstanding.
2. Mixed real-model artifact acceptance and the later-turn revision have passed the recorded checks; preserve these journeys through final review.
3. Integrated regression, build and the fresh real-model/browser checks above have passed. Preserve them
   through publication; native Linux CI and live deployment checks remain separate.
4. Upstream integration and scoped code-only review are complete; publish only the inspected paths,
   independently of unrelated existing workspace changes. Preserve client
   evidence, private audit material, screenshots, exports and credentials outside Git staging.
5. Code is pushed. Wait for the automatic release to include the agent commits, verify the deployed
   revision, and repeat the affected investigator journeys in an authenticated live verification case.
   Do not interrupt the older in-flight release or bypass sign-in to complete this gate.

Deterministic checks establish content presence, reference consistency and arithmetic. They do not establish
the truth of every source, the soundness of every inference, or visual quality without inspecting the render.
Reference PDF/DOCX intake preserves extracted text, headings and tables, and explicitly identifies unread visual
content; it does not promise pixel-perfect reproduction of an arbitrary supplied template.
