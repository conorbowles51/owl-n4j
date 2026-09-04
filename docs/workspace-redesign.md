# Workspace Redesign

> Status: Implemented through Phase 8 application cutover. This remains the source of truth for the Workspace product model, acceptance criteria, verification record, and the separately gated legacy-table contract migration.

## Reader and intended outcome

This document is for the product and engineering team designing and implementing the new case workspace. A reader should be able to understand the intended role of the workspace, see what has already been agreed, identify unresolved product decisions, and eventually implement the redesign without relying on meeting memory or chat history.

## 1. Role of the workspace

The platform has four distinct product areas:

- **Evidence** is where source material is ingested, processed, reviewed, and managed.
- **Viewers** such as graph, timeline, map, table, and financial provide different ways to explore the evidence.
- **AI** helps investigators interrogate evidence, perform analysis, and produce working outputs.
- **Workspace** is where investigators actively organise their work and build the case.

The workspace is not another evidence browser and is not merely an AI interface. It is the investigator-authored layer that sits on top of the underlying evidence.

## 2. Design principles

### 2.1 Investigation-focused, not criminal-defence-specific

The platform must support investigations generally. Its only current customer primarily conducts criminal-defence work, but that workflow must not become the universal product model.

The workspace must walk a deliberate line:

- Structured and specific enough to guide real investigative work.
- General enough to support different investigation types, industries, jurisdictions, and outcomes.
- Capable of adding investigation-specific structure without forcing irrelevant legal fields into every case.

### 2.2 One coherent interaction language

The same action should work the same way throughout the workspace. Creating content, linking evidence, attaching entities, editing an entry, and finding related material must not be reimplemented differently for notes, findings, and theories.

### 2.3 Evidence remains objective; workspace content may be interpretive

Evidence ingestion and its extracted facts should remain objective and traceable to source material. The workspace is where investigators may record interpretation, judgment, strategy, confidence, risk, and competing explanations.

### 2.4 Source material lives in Evidence

The workspace should reference evidence, not reproduce the evidence repository. It must remain usable when a case contains thousands of files.

### 2.5 The overview is an orientation surface

The overview should help someone opening a case understand:

1. What is this case?
2. What currently matters?
3. What does the investigative team know or believe?
4. What needs to happen next?

It should not attempt to display every record from every workspace subsystem.

## 3. Agreed product direction

### 3.1 Case overview

- Keep a prominent case-context area, but redesign its information model and presentation.
- Keep upcoming deadlines prominent.
- Surface current findings, theories, important witnesses, tasks, and other active case work in a concise form.
- Remove duplicated summary sections.
- Treat the workspace overview as a potential case landing page rather than a dense document summary.

### 3.2 Case context

The current context fields are too closely modelled on criminal-defence work. Charges, allegations, denials, defence strategy, legal exposure, court information, and client profile will not be universally relevant.

Agreed direction:

- Define a small universal core containing **Case summary**, **Background or triggering event**, **Investigation type**, and optional **Relevant jurisdiction or operating context**.
- Support additional structured context based on investigation type or configuration.
- Use optional investigation templates and typed custom fields for specialised context. Empty template fields should not clutter the overview.
- Migrate existing criminal-defence fields into an appropriate template rather than preserving them as universal fields.
- Avoid raw JSON entry fields in the user interface.
- Avoid making the context so generic that it becomes an unstructured description box with no operational value.

### 3.3 Notes, findings, and theories

Notes, findings, and theories remain distinct concepts, but they should share one underlying authoring and linking system.

Common characteristics include:

- Title and body content.
- Author and timestamps.
- Tags or categorisation.
- Links to evidence, entities, and other relevant case objects.
- A consistent create, edit, search, and attach experience.

Type-specific characteristics include:

- **Note:** primarily freeform investigative content.
- **Finding:** required High, Medium, or Low significance and a lightweight lifecycle.
- **Theory:** confidence, supporting material, counterarguments, and potentially status or next steps.

Agreed direction:

- Use the notebook side panel as the common entry point for authoring all three types.
- Let the user choose Note, Finding, or Theory when creating an entry.
- Reveal only the fields relevant to the selected type.
- Continue to provide dedicated filtered views for findings and theories in the workspace.
- Use one consistent linking interface rather than maintaining separate attachment implementations.
- Replace the notebook-note and legacy workspace note, finding, and theory stores with one canonical typed-entry system.
- Notes may omit a title. Findings and theories require one.
- Use a simple formatted-text editor backed by Markdown-compatible content; do not store arbitrary author-provided HTML.
- Keep authored entries case-wide. Users with case-view permission may read them, while users with case-edit permission may create, update, convert, and delete them.
- Display the original author and most recent editor.
- Remove Public, Private, and Attorney Only entry options until the platform has a genuine visibility model. Do not imply that personal or privileged notes are protected when they are not.
- Retain immutable revisions of entry content and type-specific fields so investigative work cannot be silently overwritten. Entry revision history is not a substitute for a future case-wide audit trail.

### 3.4 Notebook and linking

The newer notebook is the strongest existing foundation because it already supports authorship, search, soft deletion, and typed links to case objects.

Required direction:

- An investigator must be able to search for and attach entities while composing or editing an entry.
- Selecting an entity elsewhere and then creating an entry should remain a useful shortcut, but must not be the only reliable attachment path.
- Evidence and entity attachments should use readable search results and labels, never require manually entered internal IDs or keys.
- The same attachment component and interaction should be reused across notes, findings, and theories.
- An attachment relationship may be selected while attaching the item or changed afterwards.
- Normalise document attachments into evidence attachments rather than preserving two names for the same source-material concept.

Known bug:

- Entity search inside the notebook composer currently returns no available entities. At present, the practical workaround is to select an entity first and then create the note.

### 3.5 Documents and case files

- Remove the Documents section from the workspace.
- Remove the Case Files section from the workspace.
- Do not render large evidence lists inside the workspace overview.
- Evidence remains the canonical location for browsing and managing all source files.

### 3.6 Pinned evidence

- Keep a concise Pinned Evidence area in the workspace.
- Add **Pin to workspace** to individual evidence actions.
- Add a bulk pin action using the existing evidence checkbox-selection pattern.
- Consider equivalent pin actions from relevant entity or viewer menus.
- The workspace should retrieve only the pinned items and their display metadata, not load the entire evidence collection to resolve their names.
- Treat Pinned Evidence as shared case curation. Everyone with case access sees the same pins; users with case-edit permission may pin and unpin.
- Permit at most one active pin for the same evidence item in a case and record who pinned it and when.
- Keep Pinned Evidence evidence-only. Important entities belong in Significant or Dossiers; personal bookmarks are a separate future feature.

### 3.7 Tasks and deadlines

- Keep deadlines prominent and preserve their use in sorting cases by next deadline.
- Tasks must support one optional assignee drawn from actual users on the case.
- Tasks support an optional due date and time and visible priority.
- Task assignment should reference a case member, not store an arbitrary display string.
- Tasks and deadlines should be presented as one coherent work-management experience without assuming they must be the same underlying record type.
- Task statuses are **To Do**, **In Progress**, **Blocked**, **Done**, and **Cancelled**.
- Task priorities are **Low**, **Standard**, **High**, and **Urgent**.
- Tasks support one level of subtasks. Derive progress from task and subtask status rather than storing a manually maintained completion percentage.
- Tasks may link to typed workspace entries, dossiers, evidence, and an optional canonical deadline.
- Store creator, most recent editor, and completion timestamps.

Agreed distinction:

- A deadline may exist without an associated task.
- A task may have an optional due date.
- Multiple tasks may relate to one deadline.
- Removing a deadline must not remove its related tasks.
- The overview may combine both into a single upcoming-work view.

### 3.8 Workspace navigation

The current tabs mirror legacy data types rather than a deliberate set of investigative jobs. The navigation should become smaller and more stable as individual features evolve.

Agreed case-navigation direction:

- Make **Workspace** the first case-specific section in the left-hand navigation, ahead of viewers, full case data, and AI.
- Opening a case should land on **Workspace** rather than Graph.
- Move the existing Profiles destination out of Full Case Data, redesign it as **Dossiers**, and place it directly beneath Workspace.
- Keep Reports in the same Workspace navigation group.
- Use the following left-hand navigation hierarchy within that group:
  - **Workspace:** case orientation, current priorities, authored casework, and operational work.
  - **Dossiers:** investigator-curated case dossiers around selected people, organisations, devices, vehicles, locations, events, and other important subjects.
  - **Reports:** existing report outputs and report workflows.
- Within Workspace, provide stable views for **Overview**, **Casework**, and **Work**. Casework presents findings and theories as distinct views over the common authored-entry system. Work combines tasks and deadlines into one operational experience.

The notebook remains a persistent side-panel tool available while working across the case. It is not another top-level workspace destination. Pinned evidence remains a concise overview section.

Agreed removal:

- Remove the current Timeline tab from the workspace.
- Do not rename it to Audit Trail and carry it forward. It is not a reliable audit implementation.
- A genuine audit trail is a separate future project and is outside the scope of this redesign.
- The platform's evidence Timeline remains a separate viewer for chronological evidence and events.

**Casework** and **Dossiers** are the agreed working labels. Labels may still be usability-tested before public release without changing the underlying information architecture.

### 3.9 Dossiers, graph entities, witnesses, and interviews

The underlying need represented by Witnesses should remain, but “witness” is too narrow to be the universal concept for an investigations platform. The existing Case Profiles implementation is a useful foundation, but its current purpose and relationship to graph entities are unclear. The redesign should turn it into a deliberate dossier layer rather than preserve it unchanged or create another competing identity system.

Agreed conceptual boundary:

- A graph entity is the evidence-derived representation of a person, organisation, device, vehicle, location, event, or other subject. Its identity facts, aliases, relationships, and source-grounded facts remain canonical in the graph.
- A dossier is the investigator-curated casework layer around a selected subject. It explains why that subject matters to the investigation and brings together relevant evidence, authored casework, interviews, tasks, assessments, and current status.
- Evidence-derived identity data must not be copied into a dossier as a competing source of truth. Corrections to a canonical graph entity should be reflected by its dossier.
- Subjective or strategic material belongs to the dossier overlay rather than the graph entity.
- Not every graph entity becomes a dossier. Investigators deliberately promote important entities using an action such as **Add to Dossiers**.
- There should normally be no more than one active dossier for the same canonical entity within a case.
- A dossier may be created before a matching graph entity exists. It must be visibly marked as unlinked and support later connection to a canonical entity.
- Dossiers must not be used to conceal unresolved duplicate graph entities. Duplicate identities should ultimately be resolved in the graph, and the dossier association must follow graph merge, deletion, restoration, and replacement lifecycles.
- The existing Case Profiles storage and linking foundations should be evolved and migrated into this model rather than introducing another standalone People or Witness identity table.
- Give each dossier one or more case-specific roles rather than assuming every person is a witness.
- Keep identity facts and aliases grounded in the canonical entity and its source evidence.
- Store investigator-authored assessments, strategy, status, and case-specific role as an overlay rather than writing them back as objective evidence.
- Let investigators create or update a dossier from an evidence item, an existing graph entity, or another workspace flow.
- Let Dossiers support multiple subject types while opening on People by default.
- Link interview evidence directly to the relevant dossier.
- Accumulate multiple interviews or statements on the same dossier over time.
- Generate a detailed statement summary from the linked source material, with citations.
- Compare multiple statements and surface consistencies, contradictions, and material changes with source references.
- Require human review of generated summaries and assessments.

The existing shared Significant-entity layer already provides useful case-level entity curation and handles entity merge, deletion, and restoration lifecycles. Dossiers should integrate with that lifecycle machinery, but Significant and Dossiers remain distinct concepts: Significant curates important graph entities for analytical views, while a dossier organises investigator-authored casework around a subject.

#### 3.9.1 Dossier media

Images and other media remain evidence even when they are not processed by the graph-ingestion pipeline. A dossier may curate and present that media without copying it or becoming a second evidence repository.

Agreed direction:

- Evidence owns the original file, folder placement, metadata, access control, and provenance.
- A dossier owns a contextual link to the evidence item and its presentation within that dossier.
- Support one primary dossier cover image and a gallery of additional relevant images.
- Allow an investigator to choose or replace the cover, add optional captions, and configure a non-destructive crop or focal point without modifying the source evidence.
- Let investigators add one or more selected evidence items to a dossier from Evidence, including through the existing bulk-selection interaction pattern.
- Permit unprocessed images to be attached to linked or unlinked dossiers.
- Every displayed media item must navigate back to its original evidence record.
- Removing dossier media or changing the cover must never delete or alter the evidence item.
- Dossier media, pinned evidence, and evidence links on authored entries remain separate relationships with different meanings.
- Design the underlying link model so it can later support video frames, clips, and other media anchors, while keeping the initial rich gallery experience focused on images.
- Keep interviews and statements in a dedicated dossier section rather than mixing them into the visual gallery.
- Treat future computer-vision, object-detection, or facial-comparison capabilities as evidence enrichment, not as a prerequisite for dossier media.

Additional agreed behaviour:

- Permit any genuine graph entity to be promoted deliberately; do not hard-code Dossiers to a narrow entity taxonomy.
- Merely linking an entity to casework does not silently create a dossier. Provide an explicit **Add to Dossiers** action.
- Adding an entity-backed dossier also adds the entity to Significant. Archiving or removing the dossier does not automatically remove it from Significant.
- Provide neutral built-in person roles: **Subject**, **Witness**, **Source**, **Complainant**, **Affected Party**, **Expert**, **Client**, **Key Contact**, and **Custodian**. Allow additional custom roles and allow multiple roles on one dossier.
- Friendly, Neutral, and Adverse classifications are available only through suitable litigation templates.
- Represent reliability, credibility, risk, and strategy as dated investigator assessments with authorship and supporting links. Clearly label them as assessment rather than objective fact.
- Model an interview as a structured record connected to one dossier and one or more source-evidence items, with date, participants, interviewers, status, and working notes.
- Store AI statement summaries and cross-statement comparisons as versioned, cited outputs pending human review. Acceptance records the reviewer without presenting the AI draft as investigator-authored text.

### 3.10 Meaningful evidence links

Linking evidence to a finding, theory, note, person, or other workspace object should optionally describe what the evidence means in that specific context.

Agreed direction:

- Relationship tagging is optional. Investigators may attach evidence without classifying the link.
- Keep the relationship vocabulary small and understandable: **Unclassified**, **Supports**, **Contradicts**, and **Context**.
- The relationship belongs to the link, not to the evidence globally. The same evidence may support one theory, contradict another, and provide background to a third entry.
- Investigators can add or change the relationship after attaching the evidence.
- Where possible, a link should identify the relevant page, passage, timestamp, transcript segment, or other source anchor rather than point only to an entire file.
- Visual treatment may use restrained colour to improve scanning, but colour must remain subtle and must not be the only way a relationship is communicated. A readable label or icon must accompany it.
- A finding or theory detail view should make supporting and contradicting material easy to compare without hiding unclassified contextual evidence.

Interaction details:

- Exact viewer integrations used to capture anchors for each supported evidence format.
- Exact visual treatment for support, contradiction, context, and unclassified links.

Agreed relationship model:

- Use one vocabulary across typed workspace entries: **Unclassified**, **Supports**, **Contradicts**, and **Context**.
- Keep relationship tagging optional; an attachment without a classification is Unclassified.
- Allow relationship selection during attachment and later editing.
- Support links to evidence, graph entities, dossiers, other workspace entries, tasks, deadlines, evidence-timeline events, and agent artifacts.
- Store source anchors on the link using an extensible structured representation. Depending on the source, an anchor may identify a page and excerpt, transcript segment, timestamp range, video frame, or image region.
- Permit whole-item links when a more precise anchor is unavailable.

### 3.11 Finding and theory lifecycle

Findings and theories should evolve as the investigation develops rather than remain static text with a single current score.

Agreed direction:

- Theories use the states **Proposed**, **Investigating**, **Substantiated**, **Weakened**, **Rejected**, and **Converted**.
- Rejected and Weakened theories may be reopened. Lifecycle transitions should not prevent investigators from revising their assessment as evidence changes.
- Findings use the states **Draft**, **Active**, **Superseded**, and **Withdrawn**.
- Record the actor, timestamp, previous state, new state, and an optional rationale for every lifecycle transition.
- Theory confidence is optional and ranges from 0 to 100 in increments of five. The interface should pair the number with a qualitative description and support an explicit **Not assessed** state.
- Require a short rationale when an existing theory's confidence changes. An initial confidence assessment may be saved without one.
- Replace the finding field **priority** with required **significance**, using **High**, **Medium**, and **Low**.
- Converting a theory creates a linked finding rather than changing the theory's type.
- Begin conversion with an editable finding draft populated from the theory's title, body, tags, and links.
- Mark the source theory Converted only after the finding has been saved successfully.
- Preserve a permanent relationship between the source theory and resulting finding. Later changes to either entry do not silently synchronise the other.
- Do not require peer approval before a finding can become Active.
- AI-generated summaries, comparisons, and proposed casework remain visibly pending human review until an authorised investigator accepts them.

Detailed transition controls, confirmation messages for destructive transitions, and the visual treatment of confidence and review state remain interaction-design decisions.

### 3.12 Attention-driven overview

The overview must describe what is happening in the case now rather than behave like a generic dashboard of record counts.

Agreed direction:

- Prioritise actionable and time-sensitive information over decorative metrics.
- Combine case-wide awareness with information relevant to the current user.
- Surface upcoming deadlines, overdue work, urgent work, and tasks assigned to the current user.
- Surface meaningful recent changes, such as a material theory update or newly identified contradiction, rather than every low-value edit.
- Surface case items requiring review, such as a new statement comparison or an important interview summary awaiting human confirmation.
- Keep findings, theories, people, and pinned evidence concise and selective rather than displaying exhaustive lists.
- Avoid building the page around totals unless a count directly helps the investigator make a decision.

Agreed overview model:

- Present two visibly distinct areas: **Case right now** for shared case awareness and **Your work** for current-user responsibilities.
- Case right now includes shared deadlines, urgent or overdue work, important findings, material theory changes, contradictions, and pending human reviews.
- Your work includes assigned tasks, approaching due dates, the investigator's drafts, and reviews awaiting that investigator.
- Rank attention deterministically: overdue or urgent first; then due soon; required human review; high-significance findings or material lifecycle changes; and recent meaningful updates.
- Allow users to dismiss or snooze personal attention items. Shared case-critical items are resolved by changing the underlying record and cannot be globally dismissed from the overview.

### 3.13 Case mandate and persistent AI context

Case context should include a concise investigative mandate that guides both the team and the platform's AI tools.

Agreed direction:

- Capture the investigation's objective, scope, relevant posture or perspective, and the outcome or questions the team is expected to address.
- Keep the mandate general enough for different investigation types while providing more operational value than a generic description.
- Treat the mandate as working instructions and case orientation, not as objective evidence.
- Provide the mandate as persistent context to AI Chat and Agent work so the AI does not lose the team's role or begin reasoning from an unintended perspective.
- Let authorised investigators edit the mandate and make the active framing visible rather than hiding it inside an AI prompt.
- AI assistance on theories should actively examine both supporting and contradicting material to reduce confirmation bias.
- AI suggestions must remain distinguishable from investigator-authored conclusions and must not silently change workspace entries.

Agreed mandate model:

- Store **Objective**, **Key questions**, **In scope**, **Out of scope**, **Perspective or posture**, **Expected output or success criteria**, and **Constraints or special instructions**.
- Automatically provide the active mandate to case Chat and Agent interactions and show a visible **Using case mandate** indicator.
- Allow a temporary per-request override without silently changing the saved case mandate.
- Version mandates. A new AI conversation uses the current active version, and an active run retains the version with which it started.
- If the mandate changes, existing conversations show that a newer version exists and allow the investigator to adopt it for subsequent turns. Completed outputs retain the mandate-version reference under which they were produced.
- Defer narrower workstream-specific mandates until a separate need is established.

## 4. Current-state findings

### 4.1 Fragmented authored-content systems

- Workspace notes, findings, and theories use separate frontend components, API families, services, and database tables.
- The newer notebook is a fourth system operating alongside them.
- Entity and evidence linking behaves differently across these systems.
- Findings currently expose manual evidence ID, document ID, and entity-key inputs.
- Theory attachment fields exist in the data shape, but the visible theory workflow does not provide a coherent attachment experience.
- An unused attachment dialog treats pinned items as attachments, conflating two different concepts.

### 4.2 Duplicated overview content

- Findings appear both as a preview section and as a summary card.
- Legacy notes appear in multiple places while the newer notebook is also available in the side panel.
- Documents, Case Files, and Pinned Evidence all derive from the same underlying evidence collection.

### 4.3 Inefficient evidence loading

- Documents and Case Files independently fetch the complete evidence collection and split it using filename and extension heuristics.
- Pinned Evidence fetches the complete collection again to resolve pinned IDs into filenames.
- This approach will degrade as cases grow to thousands of files.

### 4.4 Competing deadline sources

- The proper case-deadline system drives the current deadline UI and next-deadline case sorting.
- A separate older workspace deadline configuration still exists.
- Trial date also exists inside case context.
- The redesign needs one canonical ownership model for dates and deadlines.

### 4.5 Incomplete task implementation

- The task data shape already contains due date and assignee fields.
- The task creation interface exposes only title and priority.
- Assignee is currently free text rather than a case-member reference.
- Low priority and subtasks are not currently supported.

### 4.6 Case-context mismatch

- The interface edits a case summary, but the current backend update schema does not accept that field.
- Several context fields are presented as raw JSON or free text parsed into JSON.

### 4.7 Permissions

- Newer notebook and deadline mutations use explicit case-edit permission checks.
- Many legacy workspace mutations only verify that the user can access the case.
- The redesign must consistently distinguish view permission from edit permission.

### 4.8 Disconnected witness records

- A current witness is a standalone workspace record with a manually entered name, role, organisation, category, and assessment fields.
- It is not linked to a canonical graph entity.
- Its interview list is embedded manual data rather than a relationship to evidence records.
- Statement summary, credibility, risk assessment, and strategy notes are manually edited fields with no citations or provenance.
- Friendly, neutral, and adverse grouping assumes a litigation stance that does not generalise across investigations.
- The current “build graph” action searches from the handwritten profile text rather than navigating the investigator from the profile to its canonical person and linked source material.

### 4.9 Overlapping Case Profiles

- A generic Case Profiles subsystem already supports people, organisations, devices, addresses, vehicles, events, and other profile types.
- It already stores investigator-curated summaries, importance, aliases, tags, graph-entity links, evidence links, note links, and finding links.
- It currently appears under Full Case Data rather than Workspace, and its relationship to graph entities is not clearly explained to users.
- It duplicates some identity fields that should remain canonical in the graph and still depends on legacy workspace note and finding records.
- The redesign should migrate and specialise this subsystem into Dossiers instead of building a separate People implementation.

### 4.10 Mislabelled workspace timeline

- The current Timeline is an on-demand aggregation of workspace creation dates, latest update dates, task due dates, evidence activity, and selected system-log events.
- It is neither the platform's chronological evidence viewer nor a reliable audit trail.
- Because much of it is reconstructed from current record state, deleting a record can remove its apparent history and repeated edits are not represented as a durable sequence.
- Its name conflicts directly with the existing evidence Timeline elsewhere in the platform.
- The current feature should be removed from the workspace rather than repaired during this redesign.

## 5. Target information model

### 5.1 Typed workspace entry

A common authored-entry model is the agreed canonical model for notes, findings, and theories.

Common data:

- Case.
- Entry type: Note, Finding, or Theory.
- Optional title for Notes and required title for Findings and Theories.
- Markdown-compatible body content.
- Original author and most recent editor.
- Created and updated timestamps.
- Soft-deletion state.
- Tags.
- Case-wide visibility governed by existing case-view and case-edit permissions.
- Links to evidence, graph entities, dossiers, other entries, tasks, deadlines, evidence-timeline events, and agent artifacts.

Type-specific data:

- Required Finding significance and Finding lifecycle state.
- Optional Theory confidence, confidence rationale, and Theory lifecycle state.
- Provenance relationship between converted theories and resulting findings.

Supporting records:

- Immutable entry revisions containing the content and type-specific state at each saved version.
- Structured lifecycle and confidence events containing actor, timestamp, before and after values, and rationale.
- Entry links with optional relationship meaning and structured source anchor.
- Explicit AI-review state for generated material awaiting human acceptance.

Use normal typed columns for fields involved in filtering, sorting, lifecycle logic, permissions, or reporting. Structured data may be used for extensible source-anchor details, but core entry semantics must not be hidden in arbitrary blobs.

### 5.2 Links are separate from pins

- A link explains which case objects support, contextualise, or relate to an entry.
- A pin curates an item for quick access in the workspace.
- Linking an item must not automatically pin it, and pinning it must not imply it supports a particular finding or theory.

### 5.3 Dossier

A dossier is a case-level, investigator-curated aggregation around an important subject.

Core data should include:

- Case and dossier type.
- Optional canonical graph-entity reference.
- Explicit unlinked state when no canonical entity is available.
- Case-specific roles, tags, importance, status, summary, and assessments.
- Links to evidence, authored workspace entries, tasks, interviews, and other relevant case objects.
- Cover-media selection and ordered dossier-media links, each retaining source-evidence provenance.
- Creator, updater, timestamps, and archive state.

Identity facts sourced from evidence should be resolved through the canonical graph entity rather than duplicated as dossier-owned truth. Constraints and lifecycle handlers should prevent duplicate active dossiers for one canonical entity and preserve associations through graph merges, deletion, and restoration.

## 6. Implementation details and deferred scope

### 6.1 Interaction details to resolve during implementation

The following choices may be refined through implementation and usability testing without changing the agreed product model:

- Exact responsive layout and hierarchy for Overview, Casework, and Work.
- Detailed formatted-text toolbar and keyboard behaviour.
- Findings and Theories filtering, sorting, list density, and detail layouts.
- Evidence-viewer integrations used to capture source anchors.
- Accessible visual treatment of Supports, Contradicts, Context, and Unclassified links.
- Presentation of context templates and typed custom fields.
- Dossier gallery layout, image focal-point controls, and empty states.
- Attention-card density, wording, and snooze durations.
- Confirmation language for lifecycle changes, conversion, archive, and deletion.

### 6.2 Explicitly deferred capabilities

- Potential-duplicates workspace.
- AI risk-assessment questionnaires and strategy generation.
- Significant graph relationships.
- Workstream-specific mandates.
- Case-wide audit trail.
- Private or privilege-scoped workspace entries.
- Personal evidence bookmarks.
- Computer-vision, facial-comparison, and object-detection workflows for dossier media.

## 7. Technical migration considerations

- Existing workspace notes and findings are consumed by case-profile functionality.
- Existing Case Profiles should be migrated in place or through an explicit compatibility layer into Dossiers; their graph, evidence, note, and finding links must be preserved.
- The current `/profiles` case route should redirect safely to the Dossiers destination after the navigation move so existing bookmarks do not fail.
- Existing theory attachments are consumed by evidence-relevance functionality.
- Notebook notes and all legacy workspace notes, findings, and theories must migrate into the canonical typed-entry model with stable compatibility identifiers for existing consumers during rollout.
- Existing case-profile note and finding links must be repointed to canonical entry identifiers without losing relationship metadata.
- Existing theory evidence-relevance behaviour must read canonical entry links before the legacy theory store is retired.
- Legacy privilege labels may be retained only as migration metadata; they must not be presented as enforced access control.
- Legacy data must be migrated or supported through a deliberate compatibility layer before old tables and endpoints are removed.
- Notebook links currently support entities, evidence, documents, timeline events, and agent artifacts; the target model may need additional link types.
- Obsolete workspace deadline configuration and duplicate context dates need a safe migration or retirement plan.
- Pin records need uniqueness rules, hydrated responses, and a deliberate collaboration scope.

## 8. Decision log

### 2026-09-01

- Treat Workspace as the investigator-authored case-building layer.
- Make the overview an orientation and active-work surface.
- Generalise case context beyond criminal-defence workflows without reducing it to vague freeform text.
- Converge notes, findings, and theories on one authoring and linking system while preserving their semantic differences.
- Use the notebook side panel as the leading foundation for that system.
- Remove Documents and Case Files from Workspace.
- Move evidence pinning into Evidence and support bulk selection.
- Preserve Pinned Evidence as a curated workspace section.
- Keep proper case deadlines as an important platform concept.
- Make tasks assignable to real case members.
- Record the broken notebook entity-search path as a redesign requirement and current bug.
- Remove the current workspace Timeline; do not treat it as an audit trail.
- Retire the standalone Witness identity system into Dossiers, with canonical graph-entity and source-evidence links.
- Use Overview, Casework, and Work as the agreed internal Workspace views.
- Make evidence-link relationships optional and contextual, with support, contradiction, and context as the initial concepts to refine.
- Add lightweight lifecycles for theories and findings, including a path from theory to finding that preserves provenance and links.
- Make the overview attention-driven and relevant to the current investigator rather than a dashboard of counts.
- Add a visible case mandate and use it as persistent AI context, including balanced searches for supporting and contradicting material.
- Define Dossiers as the investigator-curated casework layer around selected canonical graph entities, while keeping evidence-derived identity and facts canonical in the graph.
- Evolve the existing Case Profiles foundation into Dossiers rather than creating a separate People or Witness identity system.
- Allow deliberately promoted entity-backed dossiers and visibly unlinked dossiers for subjects not yet represented in the graph.
- Keep dossier associations intact through graph merge, deletion, and restoration lifecycles.
- Add evidence-backed dossier cover images and media galleries without copying source files or requiring image ingestion.
- Move Workspace to the first case-specific sidebar section, make it the default case landing page, and place Dossiers and Reports beneath it.
- Use one canonical typed-entry system for Notes, Findings, and Theories, with case-wide visibility, consistent permissions, Markdown-compatible content, attribution, and immutable revisions.
- Use Unclassified, Supports, Contradicts, and Context as the optional shared link vocabulary, with extensible source anchors.
- Adopt the agreed Finding and Theory lifecycles, optional numeric Theory confidence with change rationale, and required High, Medium, or Low Finding significance.
- Convert a Theory by creating a linked Finding draft while retaining the source Theory and its provenance.
- Require human acceptance of AI-generated casework without forcing peer approval of investigator-authored Findings.
- Use a small universal Case Context with optional templates and typed custom fields, and migrate criminal-defence-specific data into an appropriate template.
- Version the investigative mandate and provide it automatically and visibly to Chat, Agent, and workspace AI, with explicit temporary overrides and stale-version handling.
- Allow any genuine graph entity to be promoted deliberately into Dossiers, add entity-backed Dossiers to Significant, and never create Dossiers silently from ordinary casework links.
- Model Dossier assessments as subjective, authored, source-linked records and Interviews as structured records linked to one or more evidence items.
- Normalise Tasks with real case-member assignees, agreed statuses and priorities, optional due dates, related Deadlines, and one level of subtasks.
- Make Pinned Evidence shared, evidence-only case curation rather than personal bookmarks.
- Divide the overview into shared **Case right now** and personal **Your work** areas using deterministic attention ranking.
- Include cited statement summaries, cross-statement comparison, and balanced Theory analysis; defer duplicate resolution, AI risk and strategy generation, workstream mandates, and a general audit trail.

## 9. Implementation plan

### 9.1 Delivery strategy and phase order

Implement the redesign as a sequence of vertical, independently verifiable phases. Do not replace all workspace systems in one release. Each phase must leave the application in a usable state and must preserve unrelated case data.

| Phase | Outcome                                                           | Depends on       |
| ----- | ----------------------------------------------------------------- | ---------------- |
| 0     | Baseline, safety rails, and known defect repair                   | None             |
| 1     | Canonical typed-casework backend and migrated records             | Phase 0          |
| 2     | Unified Notebook and Casework experience                          | Phase 1          |
| 3     | Dossiers, media, assessments, and interviews                      | Phases 1–2       |
| 4     | General case context, mandate versioning, and AI propagation      | Phase 0          |
| 5     | Normalised tasks, canonical deadlines, and shared pinned evidence | Phases 1 and 3   |
| 6     | New navigation and attention-driven Workspace Overview            | Phases 2–5       |
| 7     | Cited, reviewable AI assistance                                   | Phases 2–4 and 6 |
| 8     | Cutover, reconciliation, and legacy retirement                    | Phases 1–7       |

Phases 3 and 4 may be developed in parallel once Phase 1 is stable. The final navigation and overview must not become the default case entry point until their underlying Casework, Dossiers, context, and Work contracts are available.

### 9.2 Migration and compatibility rules

All schema work follows an expand, backfill, switch, and contract sequence:

1. **Expand:** add new tables, columns, constraints, indexes, APIs, and compatibility identifiers without removing legacy storage.
2. **Backfill:** migrate legacy records with an idempotent operation that emits per-table counts, skipped rows, conflicts, and unresolved references.
3. **Switch:** make the new models the sole write target. Temporary legacy endpoints translate requests to the canonical services instead of dual-writing two stores.
4. **Verify:** compare source and target counts, sample migrated records, validate links, and exercise every dependent consumer.
5. **Contract:** remove obsolete code and tables only in a later release after the new path has operated successfully and rollback is no longer required.

Cross-cutting migration requirements:

- Preserve original identifiers through explicit legacy-source and legacy-identifier fields or a dedicated mapping table.
- Preserve original created and updated timestamps, authorship where known, soft-deletion state, and source relationship metadata.
- Never guess when identity or link resolution is ambiguous. Preserve the record, mark it for review, and include it in the migration report.
- Normalise evidence identifiers to canonical evidence-file identifiers. Record unresolved legacy identifiers without dropping the authored entry.
- Make every backfill safe to rerun and test it against empty, representative, and production-shaped databases.
- Do not automatically deduplicate separate legacy notes merely because their text matches.
- Keep downgrade support while a phase is pre-cutover. After canonical writes begin, rollback should switch the application back while retaining the expanded schema rather than deleting newly written user data.
- Require one Alembic head throughout the work.

### 9.3 Phase 0 — baseline and safety rails

#### Objective

Establish a reliable baseline, repair the known Notebook entity-search defect, and prevent legacy permission behaviour from being carried into new services.

#### Implementation

- Correct the graph-search contract so the Notebook attachment picker receives and displays graph search results.
- Add response-shape contract tests between graph search and all consumers.
- Inventory every read and write consumer of legacy workspace notes, findings, theories, witnesses, tasks, deadline configuration, pins, and Case Profiles.
- Add characterisation tests for current migration-sensitive behaviour, including Case Profile links and evidence relevance derived from theories.
- Define shared case-view and case-edit authorisation helpers for all new workspace and dossier routes.
- Add a temporary rollout switch that can expose the new Workspace by environment and, if necessary, by case while the legacy UI remains available.
- Produce a read-only preflight report containing legacy record counts, malformed identifiers, orphaned links, duplicate pins, duplicate profile-to-entity associations, and conflicting deadline sources.

#### Data migration

No records move in this phase. The preflight report establishes the reconciliation baseline for later phases.

#### Acceptance criteria

- Entity search returns readable entity results from inside the Notebook without requiring prior graph selection.
- Users with case-view but not case-edit permission cannot mutate any new or existing workspace route covered by the redesign.
- The preflight report completes without changing database state.
- Every known legacy consumer has an owner and a planned replacement or compatibility path.

#### Verification

- Run targeted backend tests for Notebook, graph search, route authorisation, Case Profiles, Significant, and deadlines.
- Run frontend component tests for the entity picker and selected-context attachment shortcut.
- Manually search for an entity, attach it to a note, save, reopen, and navigate to the linked entity.
- Run the preflight report twice and confirm identical results.

### 9.4 Phase 1 — canonical typed casework

#### Objective

Introduce one durable backend model and API for Notes, Findings, and Theories, migrate all authored casework into it, and protect existing dependent features.

#### Implementation

Add canonical persistence for:

- `workspace_entries`, containing common content, type, lifecycle state, significance, confidence, authorship, edit attribution, timestamps, review state, soft deletion, and legacy identity.
- `workspace_entry_revisions`, containing immutable saved versions of content and type-specific fields.
- `workspace_entry_links`, containing target type and identifier, optional relationship meaning, readable snapshot label, source anchor, creator, and timestamps.
- `workspace_entry_events`, containing lifecycle, confidence, conversion, review, and restoration events.
- A provenance relationship connecting a source Theory to a resulting Finding.

Add constraints and indexes for case/type/state queries, recent updates, author filters, soft deletion, target lookups, and unique links. Validate lifecycle values and type-specific fields at both service and database boundaries where practical.

Expose a canonical paginated API supporting:

- List, search, filter, sort, create, update, soft-delete, restore, and retrieve revision history.
- Type-specific lifecycle operations and confidence changes with rationale.
- Atomic Theory-to-Finding conversion.
- Link creation, update, removal, relationship classification, and source anchors.
- Explicit conflict detection when editing a stale revision.

#### Data migration

- Migrate Notebook notes and legacy workspace notes as Note entries. Preserve them as separate entries when no authoritative relationship proves they are duplicates.
- Migrate legacy findings as Finding entries. Map High, Medium, and Low priority values to Significance and default malformed or missing values to a flagged migration state requiring review rather than silently inventing meaning.
- Migrate legacy findings as Active and legacy theories as Proposed because the legacy systems have no equivalent lifecycle history. Record those initial states as migration events.
- Permit Significance to remain unset only for migrated malformed records carrying a needs-review marker. New and subsequently edited Findings must satisfy the required Significance rule.
- Migrate legacy theories as Theory entries, preserving confidence and supported attachment data. Retain old Primary, Secondary, Note, and privilege labels as migration metadata only.
- Convert evidence and document identifier arrays into canonical evidence links. Convert entity keys into graph-entity links. Preserve other valid legacy attachments using their canonical target types.
- Repoint Case Profile note and finding relationships to canonical entry identifiers through the migration map.
- Change evidence relevance derived from a Theory to read canonical entry links.
- Replace legacy write behaviour with adapters that write through the canonical service. Legacy read shapes may remain temporarily for old screens and dependent code.

#### Acceptance criteria

- Every active and soft-deleted Notebook note and every legacy Note, Finding, and Theory is represented once in the canonical store or is explicitly reported as rejected with a recoverable reason.
- Original timestamps, available authorship, tags, content, confidence, significance, and supported links survive migration.
- Notes allow an omitted title; Findings and Theories reject an omitted title.
- Viewers can read but cannot mutate entries. Editors can perform all intended casework actions.
- Confidence changes require a rationale after initial creation and create an immutable event.
- Theory conversion creates a Finding draft atomically, copies the agreed fields and links, and preserves the source Theory.
- Revision conflicts do not silently overwrite another investigator's changes.
- Case Profile context and evidence-relevance behaviour continue working from canonical entries.

#### Verification

- Run migration upgrade on an empty database and on a representative legacy-data copy.
- Run downgrade and re-upgrade before cutover and confirm one migration head.
- Compare source and target counts by case and source type.
- Run backend service, API, permission, lifecycle, conversion, revision, and compatibility tests.
- Verify database constraints with negative tests for invalid types, states, cross-case links, and duplicate links.

### 9.5 Phase 2 — unified Notebook and Casework experience

#### Objective

Replace the fragmented authoring interfaces with one consistent Notebook composer and dedicated Casework views backed by canonical entries.

#### Implementation

- Extend the persistent Notebook panel so New creates a Note, Finding, or Theory from the same composer.
- Provide a simple formatting toolbar over Markdown-compatible content and render it safely without arbitrary HTML.
- Build one attachment picker for evidence, graph entities, Dossiers, other entries, tasks, deadlines, evidence-timeline events, and agent artifacts.
- Support both explicit search and the existing attach-current-selection shortcut.
- Allow Unclassified, Supports, Contradicts, and Context to be selected during attachment or changed later.
- Integrate precise anchors where current viewers expose them; otherwise create a whole-item link.
- Add paginated Casework views for Findings and Theories with search, lifecycle, significance, confidence, author, and recent-activity filters.
- Add detail experiences for revision history, lifecycle events, linked evidence comparison, confidence rationale, conversion, soft deletion, and restoration.
- Clearly distinguish AI-pending material from accepted investigator casework.
- Remove the duplicate legacy Notes and Findings summaries from the overview once their canonical replacements are in use.

#### Data migration

No new backfill should be required beyond Phase 1. The frontend switches from legacy APIs to the canonical API. Compatibility reads remain until Phase 8.

#### Acceptance criteria

- A user can create, find, edit, link, classify, and reopen each entry type through the same interaction language.
- Entity and evidence attachments never require manual internal identifiers.
- Relationship meaning and source anchors survive save, edit, and reload.
- Casework lists remain responsive with thousands of entries through server pagination and indexed queries.
- Converting a Theory to a Finding works from the interface and visibly preserves provenance.
- Keyboard navigation, focus management, labels, status communication, and non-colour relationship indicators are usable.
- The Notebook remains available while moving between supported case views.

#### Verification

- Run frontend unit and component tests for the composer, attachment picker, Markdown rendering, filtering, conversion, lifecycle changes, conflicts, and permissions.
- Run browser tests for Note, Finding, and Theory creation; attachment from search and current selection; conversion; revision history; and soft-delete restoration.
- Test narrow and wide layouts and both colour themes.
- Run frontend type checking, linting, tests, and production build.

### 9.6 Phase 3 — Dossiers, media, assessments, and interviews

#### Objective

Turn Case Profiles and Witnesses into a coherent Dossier system that curates casework around selected subjects without competing with canonical graph identity.

#### Implementation

Introduce or evolve normalised persistence for:

- Dossiers with case, type, optional canonical graph-entity key, explicit unlinked state, status, summary, importance, creator, editor, and archive state.
- Dossier roles, including built-in and custom values.
- Dossier assessments with category, authored content, author, timestamps, and supporting links.
- General dossier links to canonical entries, tasks, evidence, and other supported case objects.
- Dossier media with evidence-file reference, cover/gallery role, order, caption, focal point or crop metadata, and source anchor.
- Interviews with dossier, date, participants, interviewers, status, and working notes.
- Interview-to-evidence links supporting more than one source file per interview.

For entity-backed dossiers, hydrate names, aliases, entity type, source facts, and relationships from the graph. Any stored source-label snapshot is a fallback and migration aid, not editable competing identity truth.

Enforce at most one active dossier per canonical entity in a case. Add graph lifecycle handlers so entity merge, deletion, restoration, and replacement update dossier associations safely. Explicitly adding a dossier also adds the canonical entity to Significant; archiving a dossier leaves Significant unchanged.

Expose **Add to Dossiers** from graph and relevant evidence contexts. Do not create a dossier merely because an entity is attached to an entry.

#### Data migration

- Migrate Case Profiles with exactly one graph link to entity-backed Dossiers.
- Migrate profiles with no graph link to unlinked Dossiers, retaining the working display name and marking their linkage state visibly.
- Preserve profiles with multiple candidate graph links without choosing a canonical identity. Migrate them as unlinked Dossiers with candidate links and a needs-link-review marker.
- When multiple Case Profiles claim the same canonical entity, preserve all authored material and flag the group for resolution rather than silently merging or deleting records. Apply the active uniqueness constraint after conflicts are resolved or represented safely.
- Preserve legacy aliases and attributes that are not canonical graph facts as clearly labelled casework metadata or candidate corrections; do not write them into the graph as verified identity data during migration.
- Migrate handwritten Witness records to person Dossiers. Preserve category, status, statement summary, risk, strategy, and embedded interview material as clearly labelled legacy assessments or interview records.
- Preserve Friendly, Neutral, and Adverse legacy categories as litigation-template values where that template applies, or as labelled legacy metadata elsewhere.
- Repoint legacy Theory-to-Witness and equivalent subject links through the Dossier migration map.
- Repoint migrated profile links to canonical entry identifiers from Phase 1.
- Preserve archive state and available authorship.

#### Acceptance criteria

- An investigator can explicitly promote any genuine graph entity into one Dossier and can create an unlinked Dossier for a subject not yet present in evidence.
- Linked Dossiers always display current canonical identity data from the graph.
- Graph merge, delete, and restore operations do not orphan or duplicate Dossiers.
- Users can attach evidence-backed images, select one cover image, reorder the gallery, add captions, and change focal presentation without modifying source evidence.
- Removing Dossier media leaves evidence untouched and preserves navigation to every remaining source.
- Dossiers support multiple roles, custom roles, assessments with supporting links, and structured interviews with multiple evidence sources.
- Existing Case Profile and Witness content remains discoverable after migration.

#### Verification

- Run backend tests for Dossier uniqueness, unlinked state, role handling, assessment provenance, media ownership, interview relationships, permissions, and graph lifecycle hooks.
- Rehearse migrations covering zero, one, multiple, duplicate, deleted, and merged graph links.
- Run browser tests for promotion from Graph, creation from Evidence, unlinked creation, later linking, cover selection, gallery editing, interview creation, and source navigation.
- Confirm source evidence checksums and metadata remain unchanged after all media operations.

### 9.7 Phase 4 — case context and persistent mandate

#### Objective

Replace criminal-defence-specific context with a useful universal model, preserve specialised fields through templates, and make the active mandate durable and visible to AI systems.

#### Implementation

- Add typed storage for the universal Case summary, Background or triggering event, Investigation type, and Relevant jurisdiction or operating context.
- Add template definitions and typed custom values supporting at least short text, long text, date, number, boolean, single choice, multiple choice, and Dossier reference.
- Provide a generic default investigation template and a criminal-defence template capable of preserving current customer data.
- Add immutable mandate versions containing Objective, Key questions, In scope, Out of scope, Perspective or posture, Expected output or success criteria, and Constraints or special instructions.
- Track the active mandate version and the author and timestamp of every version.
- Create one shared mandate-context service used by Chat, Agent, and later workspace AI features.
- Attach the mandate-version identifier to AI conversations, runs, and generated outputs.
- Show a visible mandate indicator, temporary per-request override, and a stale-version banner with an explicit adopt-current action.

#### Data migration

- Map the existing summary to Case summary where available.
- Preserve charges, allegations, denials, legal exposure, defence strategy, court information, client profile, and similar fields in the criminal-defence template.
- Make canonical Case Deadlines the owner of trial and other significant dates. If a legacy trial date has no matching canonical deadline, create a Trial deadline. If dates conflict, preserve both source values, do not overwrite the canonical deadline, and report the conflict for review.
- Create an initial mandate version only when meaningful source content exists; otherwise leave the mandate visibly incomplete rather than inventing instructions.

#### Acceptance criteria

- A general investigation can use Case Context without seeing irrelevant criminal-defence fields.
- A criminal-defence case retains all existing specialised context through its template.
- Users never edit raw JSON.
- Every new Chat and Agent conversation automatically uses the active mandate and visibly identifies that fact.
- A temporary override affects only the requested interaction.
- Existing conversations retain their original mandate version until an investigator explicitly adopts the current one.
- Active runs and completed outputs remain traceable to the mandate version that framed them.

#### Verification

- Run migration tests for empty context, general context, criminal-defence context, and conflicting dates.
- Run backend tests for custom-field validation, template isolation, mandate versioning, permission checks, and AI context construction.
- Run Chat and Agent contract tests proving that the same mandate service is used and that overrides do not mutate saved context.
- Run browser tests for editing context, changing templates, creating a new mandate version, stale-conversation behaviour, and temporary override.

### 9.8 Phase 5 — Work, canonical deadlines, and shared pins

#### Objective

Create a coherent operational area for Tasks and Deadlines and replace personal, unhydrated pins with shared case curation.

#### Implementation

- Replace JSON task records with normalised Tasks containing title, description, status, priority, case-member assignee, optional due date and time, creator, editor, completion timestamp, and soft-deletion state.
- Support one level of subtasks through a parent-task relationship and prevent deeper or cyclic nesting.
- Add task links to Dossiers, canonical entries, evidence, and an optional Case Deadline.
- Keep Case Deadlines as the only canonical deadline store and reuse the existing next-deadline case sorting.
- Build the Work view with combined upcoming dates and separate Task and Deadline filters.
- Replace completion percentage with status and derived subtask progress.
- Make pins case-shared, evidence-only, unique per case and evidence item, and attributable to the member who pinned them.
- Return hydrated pin responses containing the display metadata needed by Workspace without listing the full evidence collection.
- Add individual and bulk **Pin to workspace** actions in Evidence and clear already-pinned states.

#### Data migration

- Migrate legacy JSON tasks, mapping Pending, In Progress, and Completed to To Do, In Progress, and Done. Preserve unfamiliar status text as migration metadata and flag it for review.
- Resolve assignee strings to case members only on an unambiguous user identifier or exact unique email match. Leave ambiguous assignees unassigned and report the original value.
- Migrate Low, Standard, High, and Urgent priorities; map missing legacy priority to Standard.
- Migrate obsolete workspace deadline items into Case Deadlines, deduplicating only exact case/name/date matches.
- Convert the union of existing personal evidence and document pins into shared evidence pins, deduplicate by case and canonical evidence file, preserve the earliest valid pin attribution where possible, and report unresolved items.
- Repoint canonical entry links that still contain legacy Task or Deadline identifiers through the Phase 5 migration maps.

#### Acceptance criteria

- Tasks accept only current case members as assignees and retain their user identifier if the display name changes.
- Task and Deadline lifecycle operations enforce case-edit permission.
- One-level subtasks work and deeper or cyclic relationships are rejected.
- Deleting a Deadline does not delete Tasks.
- Case sorting by next Deadline continues to work from the canonical store.
- Every case member sees the same pinned evidence, and repeated pin actions remain idempotent.
- The pinned section performs a bounded hydrated query independent of total evidence volume.

#### Verification

- Run backend tests for task validation, status transitions, assignee membership, subtasks, links, deadlines, pins, permissions, and migration conflict handling.
- Test migration with duplicate deadlines, unknown assignees, duplicate personal pins, legacy document identifiers, and missing evidence.
- Run browser tests for task assignment, filtering, subtasks, linked deadlines, bulk pinning, unpinning, and visibility from a second case member.
- Load-test pin and Work queries using a case with thousands of evidence files and tasks.

### 9.9 Phase 6 — navigation and attention-driven overview

#### Objective

Make Workspace the effective case landing page and replace the legacy overview with a concise, query-efficient orientation and action surface.

#### Implementation

- Move the Workspace sidebar group above other case-specific sections and order it as Workspace, Dossiers, Reports.
- Make the case index route redirect to Workspace.
- Move the current Case Profiles destination to Dossiers and retain a redirect from the old case Profiles URL.
- Provide stable Workspace views for Overview, Casework, and Work.
- Remove the workspace Timeline, Documents, Case Files, duplicated Notes, and duplicated Findings surfaces.
- Build a backend attention service returning separate shared and current-user collections with deterministic reason codes and ranks.
- Rank overdue or urgent items first, followed by due soon, required review, material casework changes, and recent meaningful updates.
- Add per-user state for dismissing or snoozing personal attention items only.
- Build **Case right now** from shared deadlines, urgent or overdue work, high-significance active findings, material Theory changes, contradictions, and pending reviews.
- Build **Your work** from assigned Tasks, approaching due dates, the user's drafts, and reviews awaiting that user.
- Present concise context, mandate status, selective Casework, Dossier highlights, and Pinned Evidence without turning the page into a count dashboard.
- Use bounded summary APIs and avoid loading full evidence, casework, or dossier collections to render the overview.

#### Data migration

No source records move. Personal attention state starts empty. Existing URLs receive redirects rather than failing.

#### Acceptance criteria

- Opening a case lands on Workspace and all existing major case areas remain reachable.
- The sidebar shows Workspace, Dossiers, and Reports in the agreed order and no longer lists case Profiles under Full Case Data.
- The overview clearly separates shared case awareness from personal work.
- Ranking is deterministic, explainable, and covered by tests for ties and boundary dates.
- Personal dismiss and snooze never hide an item from other investigators or mutate the underlying case record.
- Shared critical items disappear only when their source state is resolved.
- A case with thousands of evidence items renders the overview without full-collection evidence requests or duplicated workspace fetches.
- The removed workspace Timeline cannot be confused with the evidence Timeline, which remains available.

#### Verification

- Run frontend route, sidebar, overview, empty-state, permission, and attention-component tests.
- Run backend attention-ranking tests with fixed clocks, time zones, ties, overdue boundaries, review state, and user assignment.
- Run browser journeys beginning at the case list for an owner, editor, and viewer.
- Inspect network requests on a production-shaped case and confirm bounded response sizes and no repeated full evidence loads.
- Verify old Profiles links redirect to Dossiers and evidence Timeline links remain unchanged.

### 9.10 Phase 7 — cited and reviewable AI assistance

#### Objective

Add AI assistance that expands investigative work while preserving citations, mandate framing, human control, and the distinction between generated analysis and accepted casework.

#### Implementation

- Add durable generated-output records containing case, output type, target Dossier or Theory, content, citations and source anchors, model metadata, mandate version, requester, timestamps, version, and review status.
- Run statement summarisation against explicitly linked interview evidence and require detailed source citations.
- Compare selected statements or interviews and produce cited consistencies, contradictions, omissions, and material changes.
- Add balanced Theory analysis that deliberately searches for both supporting and contradicting evidence.
- Present suggested links and analysis as pending proposals. Acceptance is explicit and uses canonical entry or assessment services; rejection retains enough metadata for traceability without altering casework.
- Prevent an output lacking resolvable source citations from being accepted as a reviewed summary or comparison.
- Keep jobs durable when the user navigates away and show progress and failure states when they return.
- Reuse the shared mandate-context service and retain the mandate-version identifier on every output.

#### Data migration

No legacy AI text is silently promoted into reviewed outputs. Existing manually pasted statement summaries remain as migrated legacy assessments or content. Investigators may explicitly regenerate or review them later.

#### Acceptance criteria

- Every generated factual claim intended for a statement summary or comparison has a navigable source reference where the source format supports it.
- Theory assistance visibly returns both supporting and contradicting material or explicitly states that one side was not found.
- AI never changes a Theory, Finding, Dossier assessment, or evidence link without explicit investigator acceptance.
- Pending, accepted, and rejected states are visually and semantically distinct.
- Accepted output records the reviewer and preserves AI provenance; it does not falsely attribute generation to the reviewer.
- Changing pages does not cancel a running workspace AI job.
- Outputs remain tied to the mandate version and source set used to create them.

#### Verification

- Run service tests with deterministic model stubs for citation validation, balanced retrieval, mandate propagation, output versioning, review, acceptance, rejection, cancellation, and retry.
- Run integration tests against representative PDFs, transcripts, audio-derived transcripts, and multiple interviews with conflicting statements.
- Run browser tests for starting work, navigating away, returning to progress, reviewing citations, accepting, rejecting, and regenerating without overwriting an earlier version.
- Manually review a sample of generated outputs for citation accuracy and adequate depth before enabling the feature by default.

### 9.11 Phase 8 — cutover and legacy retirement

#### Objective

Make the redesigned Workspace canonical, prove migration completeness, and remove obsolete systems without leaving hidden consumers or destructive rollback paths.

#### Implementation

- Enable the new Workspace for internal cases, then selected customer cases, then all cases after acceptance evidence is collected.
- Run shadow-read comparisons while legacy read adapters remain available.
- Produce a final reconciliation report by case covering entries, links, revisions, Dossiers, interviews, Tasks, Deadlines, pins, and unresolved migration markers.
- Remove legacy frontend components, unused attachment dialogs, duplicate overview sections, and obsolete data-fetching paths.
- Remove legacy write endpoints once all callers use canonical services.
- Retain redirects for old user-facing URLs.
- Remove legacy tables only in a separate contract migration after an agreed retention period and a verified database backup.
- Update operational documentation, release notes, and support guidance for the new concepts and migrations.

#### Data migration

- Rerun idempotent backfills before final cutover and reconcile zero unexpected differences.
- Resolve or explicitly accept every migration warning. No unresolved record is deleted merely to satisfy a count.
- Take and verify a restorable database backup before any contract migration.
- Preserve legacy identifier mappings for support and historical links even after old business tables are removed.

#### Acceptance criteria

- All agreed Workspace, Casework, Dossier, Work, context, mandate, pinning, overview, and AI workflows pass their phase criteria in the production-like environment.
- No active application code writes legacy workspace stores.
- Reconciliation accounts for every source record and every unresolved source reference.
- Existing cases retain their authored content, meaningful attachments, dates, profiles, witnesses, tasks, and pins.
- Viewer and editor permissions are consistent across every new mutation route.
- The rollback procedure has been rehearsed and does not delete canonical user writes.
- Product and engineering sign off before legacy tables are dropped.

#### Verification

- Run the complete backend test suite.
- From the frontend package, run `npm run typecheck`, `npm run lint`, `npm run test`, `npm run test:browser`, and `npm run build`.
- From the backend package, run `python -m pytest`, migration upgrade, migration downgrade where still supported, re-upgrade, and the single-head check.
- Run the full browser acceptance suite for owner, editor, and viewer roles on empty, small, and production-shaped cases.
- Restore the pre-contract backup into an isolated environment and prove that it boots and passes migration preflight.

### 9.12 Whole-redesign acceptance criteria

The redesign is complete only when all of the following are true:

- Workspace is the default case landing page and explains what the case is, what matters now, what the team believes, and what happens next.
- Notes, Findings, and Theories use one authoring, linking, permission, revision, and search system.
- Dossiers clearly separate investigator curation from evidence-derived graph identity and preserve source provenance.
- Evidence remains the canonical repository; Workspace never recreates exhaustive evidence listings.
- Tasks use real case members, and canonical Deadlines continue driving case sorting.
- Pinned Evidence is shared, hydrated, idempotent, and performant at large case sizes.
- Case Context is useful for general investigations, specialised fields are template-driven, and raw JSON is absent from the user interface.
- Chat, Agent, and workspace AI use visible, versioned mandate context.
- AI material is cited, reviewable, and incapable of silently becoming investigator-authored casework.
- Legacy data is reconciled and recoverable, permissions are enforced consistently, and obsolete systems have no remaining consumers.

### 9.13 Verification policy

Verification is part of every phase, not a final cleanup activity.

- **Database:** test constraints, indexes, migrations, idempotent backfills, reconciliation, and rollback on PostgreSQL rather than relying only on SQLite test behaviour.
- **Backend:** add service and route tests for success, permission denial, cross-case isolation, invalid state transitions, conflicts, missing targets, and partial failures.
- **Frontend:** add unit and component tests for state, rendering, keyboard behaviour, errors, empty states, optimistic conflicts, and permissions.
- **Browser:** cover critical owner, editor, and viewer journeys with real routing and backend contracts.
- **Performance:** exercise production-shaped cases with thousands of evidence items, entities, entries, and tasks. Verify pagination, bounded overview queries, and the absence of repeated full-collection loads.
- **Migration:** run every backfill against anonymised production-shaped data and retain machine-readable reconciliation reports as release evidence.
- **Human product review:** inspect the orientation quality of the overview, Dossier comprehensibility, citation usability, and the distinction between evidence, assessment, and AI suggestion.

## 10. Implementation record

This is a living engineering record. It does not replace the product decisions or acceptance criteria above.

| Phase | Status | Current evidence |
| --- | --- | --- |
| 0 — baseline and safety rails | Complete | `output/workspace-redesign/preflight-baseline.json` and the migration inventory capture the starting stores, consumers, heads, and safety checks. |
| 1 — canonical typed casework | Complete | Canonical entry, link, revision, lifecycle, review, backfill, compatibility, and reconciliation tests; `phase1-entry-reconciliation.json`; `phase1-postgres-migration-rehearsal.json`. |
| 2 — unified Notebook and Casework | Complete | Notebook and Workspace use the canonical entry API and shared composer/linking language; focused unit and browser-component coverage verifies creation, editing, linking, filtering, revisions, and permissions. |
| 3 — Dossiers | Complete | Dossier models, APIs, graph promotion, media, assessments, interviews, compatibility, authorization, and PostgreSQL rehearsal; `phase3-postgres-migration-rehearsal.json`. |
| 4 — context and mandate | Complete | Template-driven context and immutable mandate versions are shared by Workspace, Chat, and Agent; `phase4-postgres-migration-rehearsal.json` plus mandate traceability tests. |
| 5 — Work, deadlines, and pins | Complete | Canonical Tasks, case-member assignment, canonical Deadline links, shared Evidence pins, scale verification, and PostgreSQL rehearsal; `phase5-api-verification.json` and `phase5-postgres-migration-rehearsal.json`. |
| 6 — navigation and overview | Complete | Default Workspace routing; Workspace/Dossiers/Reports navigation; stable Overview, Casework, and Work views; bounded deterministic shared/personal attention; per-user dismiss/snooze; actionable deep links; and viewer-safe entry points. `phase6-api-verification.json` and `phase6-postgres-migration-rehearsal.json` pass. Focused frontend typecheck, lint, and 18 tests pass. Real-browser journeys pass for owner, editor, and viewer on empty, small, and 2,500-record cases, with no console warnings or errors. |
| 7 — cited and reviewable AI | Complete | Durable, versioned Dossier and Theory outputs; bounded cited source sets; balanced Theory retrieval; explicit canonical acceptance and retained rejection; persisted progress, cancellation, retry, mandate, requester, reviewer, and provenance state. `phase7-postgres-migration-rehearsal.json`, `phase7-api-verification.json`, and `phase7-browser-verification.json` pass. |
| 8 — cutover and legacy retirement | Complete | Canonical frontend and backend cutover, final idempotent backfill, per-case reconciliation, isolated backup/restore boot proof, route-contract retirement tests, operational/support documentation, and the full automated and browser matrix pass. Legacy table deletion remains correctly deferred behind retention, real-environment backup, and explicit product/engineering sign-off. |

### Phase 6 verification details

- Opening a case from the case list lands on Workspace for owner, editor, and viewer roles.
- The overview uses one bounded summary response. On the production-shaped fixture it returned 12 shared items, 12 personal items, six recent Casework items, and three pins in 20,882 bytes without loading the full 2,500-record Evidence, Task, or Casework collections.
- Owner and editor can manage context; viewers cannot. Viewers also receive no deadline or snapshot mutation controls from the case-list detail panel.
- An editor dismissal hid only that editor's personal item while the same source remained visible in shared case awareness and unchanged for other investigators.
- Overview links open their intended Dossier, Task, Finding, or Theory. The old case Profiles URL redirects to Dossiers, while the separate evidence Timeline remains reachable and labelled Timeline.
- The Phase 6 PostgreSQL rehearsal passes empty upgrade, representative populated upgrade, downgrade, re-upgrade, source preservation, per-user isolation, and the single-head invariant at `20260902_workspace_attention`.

### Phase 7 verification details

- Workspace AI outputs are durable PostgreSQL records with immutable versions, target and source snapshots, bounded evidence excerpts, source hashes and anchors, model metadata, mandate version, requester, reviewer, job state, review state, and accepted-target provenance.
- Statement summaries require an explicitly selected linked interview; comparisons require at least two. PDF pages and audio transcript times become navigable citation anchors. Every generated factual item is rejected at validation time unless it cites a resolvable source from the saved source set.
- Theory assistance performs separate supporting and contradicting candidate searches and requires either cited material or a specific not-found explanation for each side. Explicit acceptance uses the canonical entry-link service atomically; it never rewrites the Theory body or attributes generation to the reviewer.
- Accepting a Dossier proposal creates an assessment through the canonical Dossier service with `ai_assisted` provenance and the generated-output identifier. Rejection changes no casework and retains the reviewer, timestamp, and reason. Retry creates a new version without overwriting its parent.
- The Phase 7 service and authorization regression gate passes 26 backend tests. Frontend type checking and linting pass, and 12 focused unit/browser-component tests cover review states, role controls, exact evidence anchors, audio seeking, Dossier integration, and Theory integration.
- The PostgreSQL rehearsal proves empty and populated upgrade, recoverable downgrade archives, re-upgrade restoration of canonical AI output and accepted-assessment provenance, preservation of legacy manual assessments and old generated text without silent promotion, and one Alembic head at `20260902_workspace_ai`.
- The live API verification passes real owner/editor/viewer permissions, cross-case isolation, citation resolution to source files, explicit acceptance and rejection, canonical Dossier and Theory side effects, version preservation, mandate traceability, and navigation-independent running state.
- Real-browser review verified viewer read-only behaviour; editor start, cancellation, acceptance, rejection, and return-to-progress; PDF navigation to the cited page; visibly distinct pending, accepted, rejected, running, failed, and cancelled states; accepted AI provenance; and balanced Theory support and contradiction. A fresh diagnostics tab produced zero warnings and zero errors.
- Human review of deterministic outputs against the representative source PDFs confirmed that the claims matched the cited excerpts, the citation affordance was usable, the fixture analysis had adequate depth, and evidence, investigator assessment, and generated proposal remained visually distinct.

### Phase 8 verification details

- `WorkspacePage` now has one canonical implementation for every case. The temporary environment flag and case allow-list, all legacy Workspace frontend components, obsolete API clients and hooks, and duplicate Timeline/Documents/Case Files/Notes/Findings/Witness surfaces were removed.
- The backend Workspace router now owns only canonical context and mandate operations. Legacy Workspace Note, Finding, Theory, Witness, Task, Deadline, pin, reconstructed Timeline, presence, and graph-building endpoints were removed, together with the unused legacy business service and compatibility-only adapters. A route-contract test requires the canonical API families and rejects the retired paths.
- Cellebrite single-file and bulk **Add to Dossier** actions now write canonical `DossierLink` records, and file-list hydration/filtering reads those links in one case-bounded query. The obsolete Case Profiles router, service, frontend module, and evidence entity-link endpoints were removed. Historical `EvidenceFile.linked_entity_ids` values remain inert source data for migration only.
- No active router or business service writes a legacy Workspace store. Legacy model reads remain intentionally limited to migration preflight, backfill, and reconciliation. Stable mappings remain available for historical support.
- The final idempotent cutover backfill creates truthful recovery history only for canonical Entries that lack every revision or event, resolves migration markers only after a same-case canonical target is proven, and copies any historical evidence/Profile associations into same-case Dossier links without altering their source arrays. Malformed, missing, and cross-case historical references become explicit review items. `phase8-backfill-idempotence.json` records identical first- and second-pass fingerprints.
- `phase8-reconciliation.json` passes across all 18 retained cases after isolated verification-fixture cleanup: zero unexpected differences, zero review items, zero unaccepted items, and zero unknown acceptance keys. Reconciliation covers Entries, links, revisions, events, Dossiers and children, interviews and evidence, Tasks and links, Deadlines, shared pins, Context, Mandates, source mappings, parent integrity, and cross-case targets.
- All Phase 1, 3, 4, 5, 6, and 7 PostgreSQL rehearsals pass empty and representative upgrades, their supported downgrade/re-upgrade paths, stable source snapshots, cleanup, and the single-head invariant at `20260902_workspace_ai`.
- `phase8-backup-restore.json` proves a PostgreSQL custom-format backup of empty, small, and production-shaped canonical data restores into a fresh isolated database with matching source/target counts, clean reconciliation, the same migration head, and a bootable API. Both disposable databases were removed. This fixture proof does not replace the required real-environment backup before a future contract migration.
- The complete backend suite passes 268 tests and five subtests. Frontend type checking and linting pass; 317 tests pass; the explicit browser-component project passes 11 tests; and the production build succeeds.
- `phase8-browser-verification.json` records the real Chromium owner/editor/viewer matrix across empty, small, and 2,500-entry/2,500-task cases. Viewer mutation controls remain absent, editor and owner controls remain present, and the production-shaped overview returns bounded collections without exhaustive evidence or casework loads.
- Operational runbooks, release notes, support guidance, migration inventory, review-acceptance rules, application rollback, and the future contract-migration gate are documented in `workspace-redesign-operations.md`, `workspace-redesign-release-notes.md`, `workspace-redesign-support.md`, and `workspace-redesign-migration-inventory.md`.
- Legacy business tables were not dropped. Their removal remains a separate destructive contract migration after retention, a verified real-environment backup, support review, and explicit product and engineering sign-off. Application rollback keeps canonical writes and never restores an older database over them.
