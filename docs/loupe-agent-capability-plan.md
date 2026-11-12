# Loupe agent capability and quality plan

11 November 2026. Implementation plan for product, engineering and investigator acceptance. Broad implementation is local; end-to-end and live release acceptance remain open. See the [implementation and acceptance record](loupe-agent-acceptance.md) for verified outcomes and remaining gates.

## Product outcome

An investigator should be able to give Loupe a substantial request, let it work, and receive the requested result: accurate analysis, useful actions and professionally designed deliverables. The agent should plan, read, calculate, create, inspect and revise its work, carry progress across long tasks, and recover without making the user repeatedly restate the assignment.

This scope includes general capability improvements as well as the failures exposed by the historical conversation review. Fixing clarification loops alone does not meet the goal. Beautiful long reports, flexible artifacts, complete data access within the user's permissions, and connected actions are first-class requirements.

The user chooses the subject, coverage, length, format and audience. A request for a long report covering five topics must result in that report, with all five topics developed to the requested depth. A report template, context window or tool response limit must not silently turn it into a brief summary. Templates are optional starting points, not a catalogue of permitted assignments.

“General capability” means a flexible execution environment with useful tools, rather than a promise of unlimited resources or access. If a requested source, operation or format is unavailable, identify the specific gap, retain the requested scope and completed work, and provide a concrete recovery route. Do not invent information to make a deliverable look finished.

## Investigator journeys

The complete workflow is **request → visible plan and progress → evidence and analysis → draft → content and layout checks → saved result → revision or export → reopen**. The user can return to the original conversation or source at every stage.

1. **Commission a long report.** From Agent, attach a reference or select case material and request a detailed report with named topics, people, tables, diagrams, language and intended audience. Loupe identifies the deliverables, starts without unnecessary approval, and shows what it has covered. The result opens in a navigable report viewer with an outline, source links, revision history and the requested exports.
2. **Revise a specific part.** From the report or conversation, ask to expand a chapter, correct a name, change an assumption, add a graph or follow an attached template. Loupe updates the same deliverable, preserves unrelated text and investigator edits, explains material changes, and retains earlier versions.
3. **Create a custom artifact.** Ask for an ownership tree, money-flow diagram, evidence matrix, chronology, comparison dashboard, scenario calculator, workbook or presentation. Loupe chooses or composes an appropriate representation, creates it, tests its interactions and calculations, and offers the matching export. The request need not fit one of five fixed artifact types.
4. **Perform connected casework.** Ask for an evidence-backed finding, note, timeline addition, dossier update or report assembled from existing work. Loupe resolves the actual destination, follows the action's authorization policy, saves or proposes the change as appropriate, and opens the resulting object. Proposed, saved and confirmed work remain visibly distinct.
5. **Resume a substantial job.** Close the tab, return later, change devices or encounter a worker interruption. The same job retains its sources, decisions, completed steps and draft. It resumes outstanding work rather than repeating the investigation. Cancel stops future work while preserving saved progress.

## Existing foundations and constraints

The implementation already has a broad capability registry, case-scoped reads, opt-in cross-case reads, tool traces, source links, artifacts, report exports, background run tracking, cancellation and reviewed proposals for casework changes. Reuse and extend these foundations. Existing tools still need end-to-end tests showing the agent chooses and uses them correctly.

The repository inspection identified specific constraints to remove or redesign:

| Current behavior | Required change |
|---|---|
| Recent conversation context is limited to 20 messages; the runner receives only a small recent artifact set | Durable task state and retrieval of relevant history, decisions, evidence and any prior artifact |
| Fixed per-run tool budget; fresh execution state on subsequent requests; interrupted workers are recorded rather than durably resumed | Resumable jobs with checkpoints, bounded work steps, retained results and explicit resource budgets |
| Five artifact types; only the first five result artifacts are selected for persistence in service paths | Extensible artifact registry and persisted output manifest; no silent loss of requested outputs |
| Reports accept at most 24 sections, with per-section content and embedding caps | Incremental structured document editing, with resource limits managed as jobs rather than document truncation |
| Chat messages have a 12,000-character input ceiling | Brief/reference attachments and structured task ingestion that preserve lengthy requirements |
| Small inline table/chart limits | Full datasets stored separately; paginated previews and complete exports |
| PDF and Word embeds currently select at most 20 table rows and eight columns; charts and graphs become tables or descriptions | Faithful visual export, complete data or explicitly requested excerpts, readable multipage tables |
| Generic report export styling | Shared Loupe document design system across previews and exports |

These are observations of inspected code, not a claim that every historical failure still reproduces on the latest release. Newer final-answer and partial-answer safeguards already exist. Verify deployed behavior before replacing them. Keep the private audit and client evidence outside Git; repository fixtures must be synthetic.

## 1. A persistent agent workspace

Store a durable task specification: objective, requested outputs, audience, language, required subjects and sections, source scope, length/depth, accepted assumptions, explicit exclusions and the user's corrections. Preserve the distinction between a case mandate and the current assignment. New explicit user instructions refine the task; a broad mandate must not replace it.

Each job needs a plan, completed and pending work, source inventory, source revisions, result references, calculations, draft artifacts and outstanding decisions. Compact chat history around this state, while retaining access to the original messages. Do not rely on an increasingly long transcript as the only memory.

Run bounded steps in durable workers. Resume from committed checkpoints after interruption; use leases and idempotent operations to avoid duplicate work. Cache reads against source and query revisions, detect repeated no-progress calls, and refresh stale results deliberately. A tool budget is an execution boundary, not an instruction to abandon the assignment or ask the user to say “Continue” again.

Repair recoverable tool failures inside the job: validate arguments and identifiers, preserve paging tokens, pair model tool calls with their results, and retry transient failures within a bounded policy. If recovery fails, retain the work and explain the affected step in ordinary language. The investigator should not have to diagnose API schemas or provider message formatting.

Proceed automatically through ordinary read, calculation, drafting and verification steps within the job's resource envelope. Show understandable progress such as “18 of 25 profiles drafted; checking citations.” Ask only when a missing decision materially changes the result, an action requires confirmation, or additional resources need an explicit choice. Preserve accepted answers.

Retain cost, time and cancellation controls. Start with measured budgets for each job class, expose an estimate and progress, and persist work before a limit. Large jobs may need a larger approved budget; they must never silently lose chapters or become a different assignment.

## 2. Read across Loupe and act through supported services

Make every user-visible case domain discoverable and readable: original evidence and processing state, full document passages, transcripts and speaker/timestamp context, phones, entities and aliases, financial readings and confirmed transactions, timelines, maps, dossiers, findings, observations, notes, decisions, reports, artifacts and relevant case configuration.

Use a capability registry with a tested adapter for each domain. Reads return source identity, stable locators, revisions, coverage, pagination and relevant uncertainty or review state. A small model-facing page must not limit the underlying analysis. Requests for “all” require an enumerated population and a coverage record, not just semantic search results. Support full-document and full-transcript reading when excerpts cannot answer the question.

Distinguish uploaded, readable, indexed, selected, imported, reviewed, excluded and inaccessible material. “No imported transactions” is not “no financial documents.” Search names and aliases without silently merging distinct identities. State “not found in the material searched” unless exhaustive coverage supports a stronger conclusion.

Access remains that of the user: current case by default, existing explicit cross-case mode when requested, and permission checks on every read, action, resume and export. External research, when requested, is separately sourced and labelled. Uploaded documents and web content are evidence, not authority to alter permissions or execute instructions.

Build an action matrix covering create, read, revise, attach, organize and export for each domain. Start with existing notes/findings, timeline additions, dossier work and reports; then close the remaining user-visible action gaps. Each action identifies its target, required permission, confirmation policy, audit entry, result link and retry behavior. Missing a dedicated tool becomes an implementation gap in this matrix, not an unexplained refusal.

Use existing domain services rather than model-authored direct database mutations. Ordinary authorized creation and reversible editing should not acquire extra approval loops. Preserve confirmation where the existing product requires it; destructive, bulk, sharing and external actions receive an explicit consequence preview. Applying a proposal must not duplicate it on retry or overwrite concurrent investigator changes.

## 3. Flexible reports of the requested depth

Replace the one-shot report payload with a structured document model. Give sections, paragraphs, tables, figures, captions, citations, footnotes, appendices and cross-references stable identities. Support nested sections and incremental insert, move, revise and delete operations. Generate a long document in parts, then check the whole document for consistency and coverage.

Report types are open-ended: investigative reports, entity profiles, witness comparisons, financial analyses, chronologies, interview packs, internal working papers, due-diligence reports, counsel briefs and novel combinations. Do not force executive summaries, legal analysis or other boilerplate when the user excludes them. Distinguish generating a new report from revising an existing one or filling a supplied reference structure.

Honor requested depth, approximate length, language, terminology, scope and structure. If page count is requested, check it after rendering. Use meaningful evidence and analysis to reach the requested depth; do not pad unsupported sections. Where sources are insufficient, keep the requested section, describe the actual gap and complete everything supported.

Support reference reports and approved templates, reusable house styles, and user-provided examples. Loupe is the default visual identity; an explicit alternative style or template is followed where authorized. Keep content requirements separate from visual styling so changing a theme cannot change a number or conclusion.

Each deliverable has one stable identity with versioned content and pinned dependencies. “Add this to the report” changes that report. Embeds refer to specific data/artifact revisions, and a change affecting a dependent table or conclusion marks it for review. Preserve human edits, show a meaningful revision comparison, and resolve conflicts instead of overwriting them.

## 4. Loupe document and artifact design system

Build shared design primitives from the existing Loupe brand assets, tokens, logo and document examples, reconciling them with the current application before implementation. The older rebrand exploration is not the authority for finished outputs. Use the approved heading, body and evidence typography, restrained red accents, consistent entity colors and professional print layouts.

Create reusable covers, title pages, contents, section hierarchy, page headers/footers, table styles, figure captions, source notes and appendices. Apply document metadata and confidentiality labels only when appropriate to the task. Long documents need page numbers, bookmarks, working cross-references, repeated table headers and deliberate landscape pages for wide exhibits. A chart must remain legible in print; a graph must remain a graph.

Brand consistency does not mean identical compositions. An interview pack, board briefing, detailed chronology and financial appendix require different pacing and layouts. Use approved components to compose for the audience. Print defaults to a readable light treatment; the interactive viewer can support the application's themes. Bundle usable fonts and assets so export does not depend on a third-party font request succeeding.

Verify the actual render, not just the document data. Check clipping, overflow, broken glyphs, crowded diagrams, awkward page breaks, missing fonts, empty pages, inaccessible contrast and lost content. Include visual inspection of representative rendered pages and all flagged pages. Test a realistic desktop viewport, a smaller viewport and the exported files themselves.

## 5. An extensible artifact and computation environment

Keep existing graph, table, map, report and chart artifacts compatible. Add structured support for timelines, matrices, ownership trees, money-flow diagrams, workbooks, presentations and source collections. Add a sandboxed custom interactive artifact route for combinations that do not merit a new built-in type: dashboards, scenario calculators, filtered comparison views and bespoke diagrams.

Each artifact declares its schema, renderer, revision, underlying data, source references, supported interactions and export options. It must be reopenable and revisable without rebuilding the investigation. Users can request new combinations in natural language instead of choosing an output type before the agent understands the task.

Provide an isolated per-job computation workspace for calculations, transformations, charts and generated files. The agent can write and run bounded analysis code against explicitly supplied, case-scoped data. Use managed packages, resource limits, controlled network access and a capability broker; no application credentials or unrestricted production shell. Code results, inputs and logs are retained with the job and can be inspected. Arbitrary interactive content is isolated from the application origin and cannot mutate case data directly.

Do calculations with code or domain services. Let the model interpret results and compose the presentation. Interactive calculators must label assumptions, distinguish scenario values from recorded facts and recompute from the same calculation definitions used by the report. Source evidence is never altered by experimenting with a scenario.

## 6. Accurate content and faithful delivery

Keep a traceable connection from source → extracted/confirmed value → calculation → claim → artifact. Version the inputs and record scope, units, currency, dates and rounding. Financial totals must preserve population rules and avoid double-counting transfers, card payments or repeated evidence. Contradictory sources remain visible rather than being averaged into certainty.

Use separate checks for:

- **Coverage:** every requested subject, section, time range and deliverable is included or explicitly unresolved.
- **Evidence:** citations resolve to the intended passage, quotations match it, and material claims are supported at the strength stated. Reported allegations, investigator assumptions and derived conclusions are distinguishable.
- **Calculations:** figures in prose, tables, charts and scenario endpoints agree with reproducible results and the same source revision.
- **Consistency:** corrections, names, dates, currencies, conclusions and document references agree across the entire deliverable.
- **Execution:** saved objects exist, embeds resolve, and final responses accurately describe what was created or updated.
- **Presentation and export:** layout is readable and the exported output retains the requested content and visuals.

Deterministic checks establish arithmetic and structural facts; a separate model review can help find omissions and unsupported inference but is not proof of factual truth. Repair detected failures before declaring the task complete. Allow clearly labelled partial drafts to remain useful when data is missing. Distinguish “generated,” “checks passed” and “reviewed by an investigator”; never imply that automated checks replace professional review.

PDF and editable DOCX are core report outputs. Workbooks use XLSX and CSV; presentations use PPTX and PDF; diagrams support suitable vector/raster exports; interactive artifacts have a portable HTML option where technically supported, plus a useful static view and underlying data. Every requested format must be opened and checked. If interactivity cannot survive a static format, explain that specific difference and provide the corresponding static rendering.

For large datasets, keep the full data available and use readable pagination or appendices. An excerpt is permissible when requested or visibly identified as such, with the complete dataset linked. Never silently export only the first rows or columns, or replace a requested visual with a prose description.

## Delivery sequence

Deliver vertical journeys with working screens, saved state, exports and recovery paths. Build the brand/rendering foundation alongside persistent execution so professional output is present in the first report milestone. General capability is part of the committed scope throughout, not a speculative follow-up.

| Stage | Complete user outcome | Dependencies and acceptance |
|---|---|---|
| 0. Baseline and contracts | Existing reads, actions, report/export behavior and private audit failures are mapped to explicit acceptance scenarios | Confirm current deployed behavior; inventory capability gaps; establish synthetic corpus, task/output contracts and approved visual samples |
| 1. Durable long report | A substantial requested report completes across multiple work steps, opens in Loupe, and resumes after interruption | Persistent task/checkpoint state, full requested-subject tracking, incremental document model and brand foundation; first complete PDF/DOCX workflow |
| 2. Complete and accurate analysis | The report uses relevant evidence layers, exposes missing coverage and reconciles figures throughout | Source adapters, complete-population traversal, deterministic calculation records, claim/citation checks and completion gates |
| 3. Professional revision and export | Users revise the same report, retain edits/corrections, and obtain polished, faithful outputs | Stable versions, pinned embeds, conflict handling, render inspection, full table/visual export and supplied-template support |
| 4. Broad artifact creation | A novel artifact request becomes a tested workbook, deck, diagram or interactive composition | Extensible artifact registry, isolated computation workspace, format-specific renderers and portable/static delivery |
| 5. Connected case actions | The agent creates or updates the requested casework and opens the saved result | Domain action matrix, current permission/proposal rules, audit trail, retry safety and concurrent-edit handling |
| 6. Integrated release | Investigators complete mixed research, report, artifact and action requests on the deployed product | Multi-turn acceptance, cost/performance measurements, backward compatibility, ingestion-safe deployment and live verification |

Stage 0 must size the work and provide a credible schedule from measured renderer/runtime prototypes. This plan does not invent a delivery date before those dependencies are checked. Failures in acceptance remain explicit; shipping an intermediate stage does not mark the overall agent improvement complete.

## Acceptance scenarios and release gates

Use synthetic cases that reproduce the failure structures without copying private client material. Test through the real model/tool path and browser, with outputs reopened in their target formats.

| Scenario | Required result |
|---|---|
| A requested 40–60-page report covering 25 subjects and five analytical topics | Every subject and topic has the requested depth; stable outline and citations; correct pagination and exhibits; no forced 24-section limit or summary substitution |
| A one-page brief, a detailed interview pack and a free-form report using a supplied template | Each follows its own requested form, language and audience, with coherent Loupe styling where requested; no mandatory unwanted sections |
| A custom dashboard with filters, a relationship diagram and a scenario calculator | Interactions work, source/scenario values are distinguishable, figures reconcile, saved state reopens and static delivery is useful |
| A workbook and presentation generated from the same analysis | Requested editable formats open; formulas and chart values match the analysis; slides and sheets are visually checked |
| Twelve separately named exhibits, followed by a revision to the earliest after ten newer outputs | Every requested artifact persists and reopens; the original is retrieved by identity and revised correctly, with no first-five or last-eight loss |
| A 1,500-row dataset with a wide table, chart, graph and map | Complete data export, readable page layout and real visuals; no silent 20-row/eight-column loss |
| An 80-message investigation with changed assumptions and a correction to an earlier diagram | Original requirements and later explicit changes survive; irrelevant history does not override the task; all dependent outputs use the intended revisions |
| A budget boundary, worker restart, cancellation and resumed job | Completed work is retained; no repeated-search loop, duplicated output or duplicated write; progress and partial state are truthful |
| Evidence exists in files but has not entered a financial ledger; another document is unreadable | The agent distinguishes those states, searches the relevant material and identifies the real limitation without claiming absence |
| A deliberately mismatched narrative total and embedded table | The contradiction is caught before completion, repaired from the calculation record, and the exports use the repaired revision |
| A report revision made while an investigator edits the same section | Human changes survive; the agent applies compatible edits and presents any genuine conflict with a recovery path |
| Create a cited finding, attach it to a dossier and add a dated event | Existing policies are obeyed; resulting saved/proposed states and destinations are explicit; reopening and retry are correct |
| A custom artifact and a resume after permissions are revoked | No unauthorized source read or data export; sandbox boundaries and destination checks hold without losing the user's task record |

Mandatory gates: no silent truncation; no missing required output disguised as completion; no unresolved numerical contradictions in completed deliverables; no cross-case access bypass; no lost investigator edits. Readable charts/tables, valid exports, traceable claims and all requested sections are acceptance requirements, not optional polish.

Measure task completion, user repair turns, unnecessary clarification, repeated reads, citation/claim failures, calculation mismatches, render defects, elapsed time and cost per completed task. Compare model/provider choices on the same synthetic multi-turn cases, including long-context and tool-protocol failures. Select routing based on measured performance; do not assume a model swap alone solves orchestration or export defects.

## Rollout and continuity

Keep existing conversations, artifacts, citations, URLs and exports working during migration. Prefer versioned schemas and additive adapters; migrate historical artifacts without rewriting their evidentiary content. Read-only historical review is not authorization to reprocess or mutate live case records.

Develop and verify with synthetic fixtures, then run authorized investigator acceptance in an isolated verification case. Protect active ingestions during worker transitions. Follow the repository's applicable release authorization; record implementation, local verification, deployed revision and live verification separately. Preserve a rollback route that does not discard new saved work.

The historical conversation audit is supporting evidence for this plan; raw chats, client identities, amounts and extracts remain in the private local audit outside Git. The existing coverage baseline remains useful for comparing read-tool behavior but does not substitute for the journeys above.

Open engineering decisions are the durable worker/checkpoint mechanism, isolated artifact runtime and package policy, shared rendering implementation, and measured job budgets/model routing. Resolve them through Stage 0 prototypes. The product scope is already established: broad capability, requested depth, professional Loupe presentation, accurate information and complete artifacts.
