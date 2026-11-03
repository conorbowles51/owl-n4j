# Audio transcript review implementation plan

Date: 26 October 2026

Status: release prepared; isolated workflow verification recorded; deployed workflow verification not recorded
Source baseline: repository revision `76f7848f`

This plan is for engineers implementing the optional audio review workflow and investigators accepting it. The delivery objective is to let an investigator transcribe a recording, identify its speakers, correct its transcript, and deliberately send that saved version through the existing text pipeline. It must work when recordings are selected alongside documents, across entire folders, and when review takes several sessions.

The original uninterrupted Process option remains available. Transcript review is a preparation stage, not a separate extraction engine. This work does not redesign how the text pipeline judges statements or distinguishes allegations from established facts.

Implementation and verification evidence, operating instructions and remaining release checks are recorded in [Audio transcript review acceptance](audio-transcript-review-acceptance.md). The sections below retain the agreed design and its acceptance contract; the acceptance record describes the final implementation.

## 1. Agreed scope and implementation decisions

### Accepted product requirements

- Call the preparation activity **Transcript review**.
- Reuse existing transcription, diarization, audio playback, speaker naming and reversible speaker merges.
- Add optional links from speakers to existing entities in the current case.
- Allow transcript text corrections and individual-turn speaker reassignment. Preserve original machine output and audio separately from investigator edits.
- Stop the review path before document summaries, embeddings, entity extraction and graph publication.
- Process the enriched transcript through the regular text pipeline after the investigator chooses to continue.
- Include the audio choice in selected-file, individual-file, folder and case-root processing. Mixed batches must let documents continue while audio waits for review.
- Distinguish saved drafts, reviewed recordings, processing and completed evidence. Include filters, counts, a review queue and a scoped bulk action for ready recordings.
- Reuse saved transcripts instead of charging for unnecessary retranscription.
- Record the exact transcript revision used for processing. Later changes must be visible and must not silently change a running job's input.
- Unknown speakers and speakers without entity links are valid. Review completion is an explicit investigator action, not a completeness score.

### Technical choices proposed by this plan

1. Use a finite **audio preparation job** that completes after durable transcription storage. Do not keep a worker or mixed batch suspended while waiting for a person.
2. Represent transcription sources and investigator revisions separately, with immutable revision content and explicit review/publication pointers.
3. Keep existing job execution statuses. Add transcript-specific evidence metadata and derive the new visible states; do not treat preparation completion as full evidence processing.
4. Build one deterministic enriched document from a saved revision and pass it into both existing text orchestration paths. Propagate explicit entity bindings as structured, validated metadata.
5. Preview and execute bulk processing against a server-resolved set of files. Changes since preview must be identified before accepting changed work.
6. Leave successful published results in place until an explicit update succeeds. Do not introduce automatic graph deletion or wholesale graph rebuilding.

These choices make the accepted workflow concrete. They are design proposals, not claims that the corresponding code exists.

## 2. Current implementation and required integration points

| Existing area | Current behaviour | Required change |
| --- | --- | --- |
| Evidence processing service | Sends original files and folder/profile snapshots; accepts full ingestion or PDF preparation | Add audio preparation and saved-transcript input; freeze revision and bindings at acceptance |
| Audio extraction | Produces plain transcript text and separate timestamped speaker turns | Retain this as immutable source output and support reuse without another provider call |
| Batch and single-job orchestrators | Continue from extraction into summaries, chunks and extraction | Accept the same enriched document adapter before all downstream stages |
| AudioTranscriptViewer and TranscriptSpeakerManager | Playback, search, naming and reversible merges | Extend with correction editing, turn reassignment, entity selection, review actions and persistence state |
| Transcript speaker update endpoint | Saves names and merges on the evidence record | Route through revision creation, preserve concurrency and remain compatible with existing callers |
| Entity consolidation and resolution | Probabilistic matching and cross-job deduplication | Preserve authoritative speaker bindings through consolidation and resolution without name-only matching |
| Job subscriber and reconciliation service | Several completion paths mark evidence processed and copy transcript data | Apply completion by job purpose; delayed preparation must not overwrite a newer draft or successful ingestion |
| File list and filters | General unprocessed, processing, processed and failed states | Add transcript lifecycle display and server-side filters/counts |
| Selected-file and folder Process All actions | Different frontend entry points converge on backend processing | Share preparation choices and eligibility rules across every entry point |
| Checkpoints and publication | Durable work units, revisioned chunks and guarded publication | Include transcript revision, binding changes and renderer version in relevant identities |

PDF preparation is a useful precedent for stopping before ingestion. Its financial queue, eligibility rules and completion wording must stay specific to PDF review.

## 3. Investigator journeys

### Mixed selection or Process All

1. The investigator uploads files into Evidence. Uploading does not itself start review or ingestion.
2. They select files, choose Process All on a folder, or choose Process All at the case root.
3. The server resolves the exact scope, eligibility and counts, including subfolders when requested. It separates documents, recordings needing transcription, recordings awaiting review, reviewed recordings, active jobs, completed files and existing admission holds.
4. If unreviewed audio is eligible, show one processing dialog. For example: **25 files: 20 documents and 5 audio recordings**. Explain that documents follow their existing route and offer:
   - **Transcribe, then review**: prepare missing transcripts; keep existing drafts; stop audio before summaries and graph extraction.
   - **Process without review**: use each latest saved transcript, or transcribe if needed, and continue through regular processing. Say explicitly that transcript review is being skipped.
5. Reviewed audio always uses its reviewed revision. Audio that already has a transcript must not be retranscribed simply because the selection is mixed.
6. Confirmation shows the actual actions and skipped/held counts. Existing admission decisions remain effective; no audio option overrides them. If the existing hold UI must remain separate, retain the original scope and audio choice through it.
7. Accepted documents and ready recordings run independently of audio preparation. Their normal batch consolidation remains available. Transcription-only work gets a separate finite dispatch scope.
8. Show an outcome such as **20 files queued for processing; 5 recordings queued for transcription**. If some requests fail, name the accepted and unaccepted groups and offer retry only for the latter.

No audio choice is necessary for a selection containing only ordinary documents or only already-reviewed recordings. A selection containing existing drafts still needs an explicit choice before it can bypass review. The dialog must not assume that selecting a file authorizes discarding its draft or approved version.

### Review one recording

1. Open **Review transcript** from a file row, the details panel, or the awaiting-review filter. Reveal and focus the transcript viewer.
2. Keep the case, recording name, review state and save state visible alongside playback and transcript navigation.
3. Rename a voice, combine duplicate labels, restore a merge, optionally select a case entity, edit a turn's text or reassign that turn's speaker.
4. Use **Save draft** to persist changes without approving them. Show Saving, Saved or Save failed truthfully. Keep unsaved edits available on failure.
5. Use **Mark reviewed** to approve the current saved revision, even if some speakers remain unknown. Unsaved edits must be saved successfully before approval.
6. Use **Mark reviewed and process** to save, approve and enqueue the exact revision. If saving or approval fails, do not enqueue. If enqueue fails, keep the approved revision ready to process and make retry safe.
7. Use **Next recording** to continue the review queue. On leaving with unsaved edits, provide Save and continue, Discard unsaved edits, or Stay. Never silently discard or infer approval.
8. Returning to Evidence restores folder, filters, page and selection where applicable. Returning to the queue restores its position; completed reviews leave the awaiting-review list without losing the next item.

Save and review controls must remain visible for long transcripts, without scrolling to the final turn. Existing timestamp seeking, search, playback and virtualized rendering must continue working while editing.

### Process reviewed recordings together

1. Filter to **Ready to process**, or choose **Process ready audio (N)** from Evidence.
2. Label the scope: current folder, current folder and subfolders, or entire case. Default to the current working scope and never expand silently.
3. Resolve all matching files server-side, not only the visible page. Show the count and a paginated affected-file list before submission.
4. At acceptance, recheck review versions, permissions, source availability, active jobs and existing admission requirements.
5. Enqueue eligible revisions through regular ingestion. If another investigator edited a file, report that file as changed and require a fresh decision for it; do not process the changed revision under the earlier confirmation.
6. Leave awaiting-review recordings alone. Completed recordings need an explicit update/reprocess action rather than routine ready-audio processing.

### Edit after processing

Saving a new draft retains the last successful graph/search publication and displays **Transcript changed since processing**. The investigator can review it and choose **Update processed transcript**. That action uses the existing reprocessing/publication mechanisms and preserves investigator graph edits. It does not mean deleting the original file or every graph entity associated with it.

## 4. States and transition rules

Keep three independent concepts in the API: execution state, current transcript review state and last successful publication. A single status string cannot describe all three correctly.

| Condition | Primary visible label | Supporting information and action |
| --- | --- | --- |
| No saved transcript, no active job | Not transcribed | Transcribe or Process |
| Audio preparation job queued/running | Queued for transcription / Transcribing | Progress, pause/resume where supported |
| Transcript exists; current revision has no matching review approval | Awaiting transcript review | Review transcript; show whether a draft is saved |
| Current revision is explicitly reviewed; not yet published | Ready to process | Process |
| Ingestion job queued/running | Queued for processing / Processing | Show the accepted revision and current stage |
| Latest revision successfully published | Processed | Reviewed / Transcript not reviewed remains a separate label |
| Current revision differs from last successful publication | Transcript changed since processing | Review changes or explicitly update |
| Preparation or ingestion attempt failed | Transcription failed / Processing failed | Retry the failed stage; retain transcript and previous publication |

Rules:

- No transcript, awaiting review and ready to process must not create a misleading Processed timestamp.
- Successful direct processing does not mark a transcript reviewed. Show **Processed · Transcript not reviewed** where appropriate.
- Approval belongs to one revision. A saved content, name, merge, turn-assignment or entity-binding change produces a new draft and invalidates readiness of the current version.
- No-op saves do not create revisions or invalidate approval. Playback position and search are not transcript edits.
- An already published revision must not appear in the ordinary ready-to-process count just because it was reviewed.
- A new edit while a job runs is permitted. The running job keeps its frozen revision, and completion still shows the newer draft as needing review/update.
- A failed attempt never clears the last successful publication pointer or destroys approved content.
- Returning an unchanged draft to an earlier revision is an explicit restore operation that creates a traceable revision; it is not history deletion.

## 5. Persistence and revision model

### Immutable transcription sources

Add a transcription-source record for each completed machine generation, with evidence/case identity, original file digest, provider/model metadata, raw text, raw segments, language/duration when available, engine job identity and creation time. Stable segment IDs belong to that source. A generation is made active only after validation and atomic storage succeeds.

Existing EvidenceFile transcription and segment fields remain compatibility representations of the machine source during migration. Investigator corrections must never overwrite those raw values. A later explicit retranscription creates another source generation and retains the previous source and revisions.

### Immutable investigator revisions

Add an append-only transcript-revision record containing:

- Case, evidence file, source generation, revision ID, parent revision ID, author and time.
- Text overrides keyed by stable segment ID, plus a body-text override for legacy unsegmented transcripts.
- Per-turn speaker overrides, names and reversible canonical-speaker merges.
- Optional canonical-speaker bindings to exact case entity IDs, with a captured display name/category for review history.
- Schema and renderer versions; a deterministic input digest covering source identity, ordered turns, edits, names, merges and entity bindings.

Store a complete revision payload rather than requiring an unbounded replay of small patches to reconstruct processing input. UI requests may be partial; the service validates and materializes the next complete version. Any comparison view can derive changes from parent revisions.

Keep a current working revision pointer, reviewed revision pointer with actor/time, and last successfully ingested revision/digest on the evidence record or its one-to-one transcript-state record. Store a durable review event for each approval. These pointers must update under optimistic concurrency; review metadata must not mutate immutable revision content.

Use the following proposed relational layout:

| Record | Identity and constraints | Contents |
| --- | --- | --- |
| `evidence_transcription_sources` | Primary source ID; case/evidence foreign keys; unique completed engine-job generation | Immutable machine output and source digest |
| `evidence_transcript_revisions` | Primary revision ID; source/evidence/case relationship validated together; parent constrained to the same source/evidence | Complete immutable correction/settings payload, content digest and author |
| `evidence_transcript_state` | One row per evidence file; optimistic lock version | Active source, working/reviewed/published revision pointers, review actor/time, optional-review opt-in and active job references |
| Review receipt | Existing case audit event plus stable review-request identity | Revision, actor, time and idempotent approval outcome |
| Processing plan and execution receipt | Case/user-scoped IDs; unique idempotency key per operation and principal | Frozen candidate set, expected revisions, execution intent, accepted job groups and retry outcomes |

Keep existing evidence status and processed_at as compatibility summaries of full ingestion. Update transcript-state and evidence summaries transactionally when applying job results. Add nullable compatibility references before introducing foreign keys/backfill requirements, and migrate in bounded transactions. Source/revision deletion follows the existing evidence lifecycle; this feature adds no automatic evidence cleanup.

An ingestion job records its selected revision, source digest, renderer version, binding digest, effective processing profile and request identity. Do not rely solely on the current EvidenceFile engine-job pointer: preparation and ingestion jobs need purpose-aware lineage, and both historical attempts must remain inspectable.

Indexes must support case/folder queries for awaiting review and ready audio. Filtering/counting must not require loading every transcript body. Large bodies and segment lists are fetched only for the opened recording or worker input.

### Validation and history

- Reject unknown segment IDs, invalid/cyclic merges and out-of-case entity bindings.
- Restrict entity selection to compatible person identities supported by the current case ontology. Reuse existing search/access systems; do not introduce a new entity directory.
- A merge of two groups with different entity bindings requires choosing the resulting binding. Do not silently choose one, delete one or merge graph entities.
- Editing a bound speaker's display name does not rename the graph entity. Explain label versus linked identity in the speaker controls; unlinking is explicit.
- A turn may move to another detected speaker or a newly added unidentified speaker. Preserve its original speaker and timestamps. Word-level timing and arbitrary timeline editing are outside this release.
- Empty text overrides, repeated words, Unicode and overlapping source turns need deterministic handling. Do not silently remove a turn; retain its identity/history even if an investigator clears its text.
- Register new records and review events with the existing audit conventions. Ordinary audit/progress logs store identities, counts and digests rather than complete transcript bodies or voice samples.

## 6. Backend and engine contracts

Names below are proposed contracts to implement within the existing authenticated API conventions. Additive schemas and generated OpenAPI updates must be reviewed with the implementation.

### Transcript API

| Operation | Proposed contract | Success and important errors |
| --- | --- | --- |
| Open transcript | `GET /api/evidence/{evidence_id}/transcript` | 200: source metadata, current revision, review/publication state and revision token; 404: unavailable or inaccessible source |
| Save draft | `PATCH /api/evidence/{evidence_id}/transcript` with expected revision and changed overrides/settings | 200: canonical saved revision/state; 409: revision conflict; 422: invalid segment/merge/binding |
| Mark reviewed | `POST /api/evidence/{evidence_id}/transcript/reviews` with revision ID and idempotency key | 201: review receipt, or 200 for the identical retry; 409: revision no longer current |
| Inspect history | `GET /api/evidence/{evidence_id}/transcript/revisions?cursor=...&limit=...` | 200: metadata and next cursor; bounded maximum 100; fetch one revision body separately |
| Read revision | `GET /api/evidence/{evidence_id}/transcript/revisions/{revision_id}` | 200: immutable revision and provenance; 404: wrong evidence/case or missing revision |

Example draft input:

```json
{
  "expected_revision_id": "revision-12",
  "text_overrides": {"turn-7": "I spoke to Eric yesterday."},
  "turn_speaker_overrides": {"turn-7": "B"},
  "speakers": {"A": "John", "B": "Eric"},
  "speaker_merges": {},
  "speaker_entity_ids": {"A": "case-person-john", "B": "case-person-eric"}
}
```

The identities above are synthetic placeholders. Preserve the graph's actual entity ID representation; do not assume graph IDs are UUIDs. Document field replacement versus merge/null removal semantics explicitly in the request schema. Missing maps leave existing settings unchanged; supplied settings maps replace that map, and null override values restore the corresponding original value.

Extend the existing transcript-speakers endpoint as a compatibility adapter to the same revision service. Old clients that submit names/merges cannot erase text corrections or bindings. Require revision concurrency on new clients; an unversioned legacy write that could overwrite an existing reviewed/draft change must return a conflict instead of overwriting it.

Every operation resolves the evidence's real case and enforces current case roles. Reading requires case view; editing/reviewing uses existing evidence-edit authorization; starting processing requires evidence-process authorization. Verify exact permission names in the current access layer instead of inventing a parallel permission model. Read-only viewers get playback and saved content without edit controls.

### Processing preview and execution

Add a common processing-preview operation, for example `POST /api/evidence/processing-plans`, accepting one explicit selection: file IDs, folder plus recursive flag, or case root. An optional `ready_audio_only` selector uses server-side eligibility. Return 201 with a plan ID, scope, expiry, action counts, held/skipped reasons and a paginated file listing. Do not return all transcript bodies. Use a maximum page size of 100; folder/case selection remains server-side. Chunk internal work for large selections without reinstating the selected-file processing cap previously removed from this application.

Expose `GET /api/evidence/processing-plans/{plan_id}` for the authorized caller's summary and `GET /api/evidence/processing-plans/{plan_id}/files?cursor=...&limit=...` for the bounded affected-file list; both return 200 and enforce current case access. Include selection/filter snapshots and file-version expectations in the plan. Plan expiry is a configured server value returned explicitly to the caller.

Complete the same plan with `POST /api/evidence/processing-plans/{plan_id}/executions`, an idempotency key and `audio_mode: "review_first" | "direct"` when unreviewed audio needs a choice. A normal acceptance returns 202 with an execution receipt and job groups. A repeated identical key returns that receipt; reuse with changed input returns 409. Expired plans or changed revisions return 409 with affected files and a refresh action. Do not expand the selected set to newly uploaded files.

The plan resolves candidate IDs and relevant revisions; execution rechecks authorization and current eligibility. A stale-revision conflict is detected before any new dispatch for that execution; refresh the plan or explicitly exclude the changed files. Once accepted, freeze the actual per-file inputs and folder/profile snapshots. Report per-file acceptance, deferral, skips and failures if separate engine dispatches have different outcomes. Durable receipts/outbox recovery must make a lost acknowledgement safe without duplicate paid work.

Use existing admission errors and recovery controls, adding stable audio-specific reason codes inside the existing error envelope. Use 401/403 for authentication/authorization, 404 for unavailable resources, 409 for state/revision conflicts, 422 for invalid content and 503 for temporary unavailability where appropriate. Return private transcript data with private/no-store caching. No stack traces, storage paths or provider credentials in client errors.

### Existing callers and per-file modes

Keep current processing endpoints compatible and make them delegate to the same eligibility/dispatch service. Add optional audio modes and revision references to their request models. Omitted mode keeps the uninterrupted behaviour for legacy recordings that have never entered the optional review workflow. For an opted-in recording awaiting review, an omitted mode must return a review-choice conflict, not silently bypass it.

At the engine boundary add an `audio_review` preparation purpose beside full ingestion and PDF review. Full ingestion may reference a saved transcript revision. Validate evidence, case, source digest and revision identity server-side; never trust arbitrary client-supplied text or graph IDs as an authorized saved revision. Prefer reading an immutable snapshot through the existing shared database boundary with an engine-side model, rather than putting transcript bodies in general processing metadata.

## 7. Job lifecycle and mixed-batch orchestration

### Audio preparation

1. Acquire the existing processing exclusion for the source and create a durable accepted request.
2. Run existing audio extraction with its model, chunking, speaker references, progress and checkpoint behaviour.
3. Atomically store the immutable machine generation and initial working revision; publish a preparation-completed event only after commit.
4. Mark the preparation job completed. Set transcript state to awaiting review. Do not set evidence processed_at, clear successful graph metadata or generate a summary.
5. Release the worker. Awaiting review is an evidence state, not a running or paused ARQ job.

When a saved transcript already exists, review-first processing returns it for review without a new transcription job. Do not change existing drafts or reviewed records merely to make the batch uniform.

Preparation must work without Neo4j, embeddings or graph-index initialization. Use existing general ingestion capacity with bounded concurrency initially; do not reuse the dedicated financial PDF queue or change live queue capacity as part of this feature. A separate audio queue is a later capacity decision if measured workload requires it.

### Full ingestion

For fresh direct audio, transcribe once, store its source/initial revision and feed that revision through the enriched document adapter. For saved audio, load the accepted immutable revision and skip audio extraction. Then execute existing summary generation, chunking/embedding, extraction, consolidation, resolution and publication.

Partition a mixed execution into independent preparation and ingestion groups while retaining a parent receipt for the UI. Review-first recordings must not participate in a document batch's combined extraction or deduplication until the investigator starts their later ingestion. Prepared audio can join other full-ingestion files in a later ordinary batch.

Dispatch each transcription-only recording as a finite `process_file` job with purpose `audio_review`, using the durable outbox's existing function override and stable queue-job identity. Add the purpose to worker dispatch, schemas, pause/resume support and startup/retry allow-lists. Keep those jobs out of `run_batch_pipeline` until that pipeline is handling full ingestion. This avoids accidentally routing preparation through the current default batch function, which would continue into extraction.

### Synchronization and restart recovery

Centralize completion application so case reconciliation, live subscriber updates, polling and startup recovery all use the same job-purpose rules. Preparation completion must never be interpreted as graph completion. Include purpose, source generation and input revision in job detail schemas and progress events.

Preserve request/generation guards against delayed events. Separate active preparation/ingestion tracking from last successful publication. A late event may enrich its own history but cannot replace a newer draft, newer request, names or overrides. Reconnect/restart reconciliation must reconstruct the same visible state as live delivery, without relying on Redis delivery alone.

Continue honoring pause/resume and checkpoint recovery for active work. Existing janitor rules must recognize finite preparation jobs and must not reap records awaiting human review. Failed preparation retains the prior source/draft; failed ingestion retains the approved revision and last successful results. Retry resumes available work units and does not delete or retranscribe saved material unnecessarily.

## 8. Enriched document and exact entity bindings

Build one versioned, deterministic renderer that accepts a source plus saved revision and returns the existing ExtractedDocument representation. Render turns in source order with timestamps and resolved speaker labels, for example:

```text
[00:12.400–00:16.100] John
I spoke to Eric yesterday.

[00:16.200–00:19.000] Eric
We met at the office.
```

The text contains the approved words and speaker labels. Structured metadata contains source generation, revision, raw/canonical speaker IDs, optional exact entity IDs, original time ranges and character spans for each turn. Keep generated labels distinguishable from spoken text in provenance. Preserve existing extraction and claim-validation policy; this is not a new truth-assessment feature.

Use this same effective document for summaries, canonical document text, embeddings, extraction and source navigation. Draft storage is private preparation state; it must not silently replace the successfully published search/AI document before processing. The transcript viewer can show a saved draft independently. Consumers such as Dossier and Workspace source views must deliberately select current working versus last processed revision and display that distinction when relevant.

Carry speaker/turn spans into chunks, retaining context when a long turn crosses a boundary. Repeated context must not corrupt canonical quote offsets. Source locations must resolve from processed quotes to revision, segment IDs and original audio times, including edits that change text length.

Exact entity binding requires more than adding names to a prompt:

1. Validate each selected target against the case and compatible ontology type at save and job acceptance. Recheck before publication; a removed/merged target must produce a visible conflict or use an established, auditable redirect.
2. Carry binding evidence through raw entities, claim projection, consolidation, resolution and checkpoint serialization. Use explicit speaker/turn identity to bind the speaker mention; never bind every occurrence of a common name in the transcript.
3. Protect conflicting explicit bindings from name/embedding/LLM merging. Two speakers both displayed as John but bound to different people must remain distinct through intra-batch and cross-job deduplication.
4. Respect a validated explicit target when resolving the corresponding speaker entity and relationship endpoints. Do not let a probabilistic match silently replace it.
5. Leave unbound names to the existing resolver. Do not create entities during transcript review, rename existing entities, or automatically merge graph people because labels were combined.

The revision/content identity must include bindings even when the rendered text is unchanged. Summary/chunk/extraction caches must also include renderer/schema versions and effective context. Preserve expensive source-transcription checkpoints when only investigator edits change. Old checkpoints for earlier rendering rules must not be replayed as reviewed output.

After reprocessing, existing publication mechanisms must activate the new search revision only after success. Test source-contribution replacement in the graph explicitly: if current reprocessing leaves old assertions attached to a source, define a scoped reconciliation that preserves other sources and manual edits before accepting the update journey. Do not claim that changed transcript processing removes obsolete graph contributions until this is verified.

## 9. Frontend delivery

- Extend shared evidence types with transcript/review/publication summaries and job purpose. Avoid sending full revisions with every file row.
- Share one processing coordinator across file rows, details, selection toolbar, selection action bar, folder menus and root Process All. Reuse existing profile/admission UI and preserve decisions across retries.
- Add **Transcript review** filtering with awaiting-review and ready counts; keep ordinary processing-status filters meaningful. Apply filters, sorting, pagination and counts on the server across folder/subfolder/case scopes.
- Add a secondary review badge to audio rows; do not make every new audio upload look failed or defective. Display Not transcribed rather than Not cleaned up.
- Extend existing speaker management with a case-scoped entity picker, visible linked identity, unlink action and merge-conflict resolution. Search the existing entity service with pagination/debouncing rather than downloading the graph.
- Add per-turn text edit, speaker reassignment and Restore original actions. Preserve playback, search, timestamp clicks and virtualization. Support legacy transcripts without segments as editable body text; clearly label unavailable turn-level timing/assignment.
- Add persistent save/review/process controls and a changed-since-processing message. Prevent double submission and expose revision conflicts without discarding local drafts.
- Add review queue previous/next controls, explicit scope/counts and a return-to-list action. Preserve URL/store navigation state across reopening as appropriate.
- Update JobCard and processing activity wording to distinguish transcription preparation from full ingestion. Offer Review transcript on successful preparation and stage-specific retry on failure.
- Update DossierSourceViewer and other shared transcript entry points to use the same effective transcript model and permissions; do not leave one view displaying stale labels silently.
- Verify keyboard access, focus after opening/closing dialogs, screen-reader state announcements, and desktop/narrow layouts with long names and many turns. Do not put essential controls below the transcript.

## 10. Existing data and backward compatibility

Use additive migrations. Legacy audio with raw transcription becomes a source generation and initial revision lazily or in a bounded, restartable backfill. Include existing names/merges as investigator settings. Do not mark legacy content reviewed simply because it has names or has already been processed.

For previously processed recordings, the exact historical processing input may be unknown. Record that limitation as an unknown legacy input rather than claiming current labels were used. Showing a saved enriched draft must not automatically reprocess the recording. If legacy name edits cannot be dated relative to ingestion, use Review before update rather than asserting a change time.

Preserve unsegmented transcript support and current playback. Where diarization is unavailable, text correction still works; explain that turn-level speaker assignment requires a source with speaker turns. Retranscription is an explicit replacement-generation action with a preview of draft/review consequences, never a side effect of Process or Retry.

Ensure all existing audio formats supported by the reader remain supported. Determine support using the existing reader/media detection, without creating a second extension allow-list. Video transcript review, word-level time editing, translation review and automatic voice identity recognition are outside the initial UI scope; shared code must retain current video processing behaviour.

Old clients continue reading raw compatibility fields. New readers use the transcript API. Old speaker-write callers go through the compatibility adapter and cannot bypass review/version protections. Do not remove compatibility fields in this release.

## 11. Ordered implementation work

Each stage must include its stated verification before dependent work relies on it. These are delivery checkpoints for the complete feature, not permission to publish an incomplete investigator journey.

| Stage | Deliverable | Dependency and acceptance checkpoint |
| --- | --- | --- |
| 1. Persistence and state | Source/revision models, review/publication pointers, migrations, state derivation, compatibility reads and audit integration | Start here. Prove raw preservation, revision conflicts, no-op saves and legacy state mapping |
| 2. Saved review service | Transcript read/save/review/history, validation, compatibility speaker writes and permissions | After 1. Save/reopen text, names, merges, assignments and bindings; reject stale/cross-case changes |
| 3. Finite preparation | Audio-review job purpose, extraction reuse, purpose-aware sync/subscriber/restart recovery | After 1; integrates 2. Transcribe once, stop before all downstream AI, release worker and reopen awaiting review |
| 4. Standard ingestion adapter | Deterministic enriched document, per-turn citations, frozen revision inputs, exact entity constraints and cache identities | After 1–2. Both orchestration paths use corrected content; same-name bound people stay distinct |
| 5. Batch coordinator | Processing plans/receipts, partitioned dispatch, folder/root integration, safe retries and ready-only queries | After 3–4. Mixed batches finish documents while audio waits; lost responses and stale plans are safe |
| 6. Complete investigator UI | Existing viewer enhancements, processing choice, badges, filters/counts, review queue, bulk-ready and update actions | Build against 2–5. Full save/leave/reopen/review/process/return journey works at realistic viewports |
| 7. Regression and release | Existing-data rehearsal, real-service integration, browser acceptance, deployment compatibility and operating notes | After all above. Every acceptance item below has evidence or an explicit unresolved gap |

Implementation should remain behind a server capability/feature gate until the complete journey is ready. The frontend must not offer review controls against an engine/backend lacking the required capability. Do not release a UI that can approve transcripts while ingestion still ignores them.

## 12. Verification and acceptance matrix

Use synthetic recordings, transcripts and case identities for automated tests and repository fixtures. Keep client source material, extracted records, screenshots, exports and credentials outside Git. Mocked-provider tests prove routing and identity contracts; they do not prove transcription accuracy or model attribution quality.

| ID | Scenario | Required evidence |
| --- | --- | --- |
| A01 | Fresh direct audio | Existing uninterrupted action finishes; one transcription; regular downstream stages; transcript not automatically reviewed |
| A02 | Review-first audio | Raw source/turns saved; awaiting review persists; zero document-summary, embedding, extraction or graph calls before continuation |
| A03 | Mixed documents/audio | Documents complete while recordings wait; independent progress/failure; counts and outcomes match actual accepted files |
| A04 | Save/reopen/review | Names, merges, text, turn assignments and entity links survive refresh/navigation/restart; original source unchanged |
| A05 | Review semantics | Save draft does not approve; unknown speakers permitted; later material edit invalidates current readiness; no-op save does not |
| A06 | Correct processing input | Summary, chunks, extraction and published search all consume the selected revision; both single and batch paths tested |
| A07 | Explicit identity | Two distinct case people with the same name remain distinct; intended speaker resolves to selected ID; unrelated named mentions are not forced |
| A08 | Merge and entity conflicts | Cycles, conflicting group bindings, deleted targets, graph redirects and cross-case IDs handled visibly and safely |
| A09 | Ready-only bulk action | Correct scope/count beyond one page; awaiting-review and already-published files excluded; no hidden subfolder/case expansion |
| A10 | Stale/concurrent changes | Simultaneous edits conflict without loss; changed revision after preview cannot be silently substituted; active job input stays frozen |
| A11 | Retries and duplicate requests | Lost save/review/dispatch responses, repeated process clicks and partial batch acceptance create no duplicate work or false completion |
| A12 | Failure and restart | Failed transcription preserves old drafts; failed ingestion preserves publication; polling/subscriber/startup recovery converge to same state |
| A13 | Long and legacy recordings | Chunk boundary speakers, overlapping turns, large virtualized transcripts, Unicode, missing diarization and unsegmented transcripts covered |
| A14 | Source navigation | Quotes resolve to correct processed revision and audio time after text-length changes and turn reassignment; shared source viewers are consistent |
| A15 | Post-processing update | Changed badge appears; explicit update uses revised content; old search revision retires only on success; manual/other-source graph material preserved |
| A16 | Permissions | Read-only investigator can view but not edit/review/process; case isolation enforced on every resource, plan and entity binding |
| A17 | Existing workflows | Ordinary document, video, financial PDF preparation, admission guards, folder profiles, upload retention and pause/resume remain functional |
| A18 | Real-browser journey | Upload mixed files → choose review → documents finish → open audio → edit/link/save → leave/reopen → review next → process ready → open graph/source → return |
| A19 | Worker isolation | Awaiting review occupies no worker; preparation works without graph; unrelated active ingestion and financial reading remain active |
| A20 | Migration and rollback | Legacy named/unnamed/processed sources migrate without fabricated approvals; mixed-version capability checks prevent unsupported job consumption |

Run targeted backend pytest and engine pytest suites for the touched services, followed by relevant existing audio, job-sync, checkpoint, dispatch, admission and publication regressions. Run frontend unit/browser-component tests, `npm run typecheck`, `npm run lint` and the production `npm run build`. Address new failures before broader testing; document unrelated baseline failures precisely.

In addition, run integration against the actual local database, queue, worker, graph and vector store. Use an authorized synthetic recording for at least one actual-provider end-to-end transcription/review/ingestion comparison. Check selected entity identity and navigable source output; do not present mocked calls as model-quality evidence.

Perform the full browser journey at a realistic desktop viewport, such as 1440×900, and a narrow viewport, including failure, refresh, reopening existing data and returning from graph/source views. Component tests and build success alone do not close A18.

Implementation evidence should be recorded against each acceptance ID with revision, environment, fixture, result and limitation. All items are currently pending. Product agreement and this plan are not verification of the feature.

## 13. Rollout and operating requirements

1. Rehearse additive migrations and legacy reads locally. New tables/columns must not require rewriting original evidence or stopping current jobs.
2. Establish compatibility between old and new workers before enabling dispatch of new job purposes. The accepted release procedure must drain/transition capable consumers safely or route new-purpose work only to compatible workers; an application flag alone cannot stop an old worker consuming an unsupported job.
3. Preserve active ingestions and dedicated financial processing. Do not cancel, clear, move or retry live case jobs as a release side effect. Preserve deployment ingestion guards and checkpoint storage.
4. Use existing repository-triggered deployment: push is the deployment trigger when code release is authorized and verified. Do not substitute an unnecessary manual deployment/login procedure. This planning task itself does not start a release or modify live services.
5. Enable review only when backend, engine and frontend capabilities agree. Observe preparation/ingestion counts, failed-stage rates, duplicate-request suppression and worker capacity using sanitized operational metadata.
6. Verify the deployed revision and repeat the affected journey on the live deployment using an authorized synthetic case. Report implemented, locally tested, deployed and live verified separately. Respect a separate live-origin access denial.
7. Rollback disables new review dispatch first, preserves every source/revision/review receipt, and leaves compatible readers available for saved data. Do not drop new data tables as routine rollback. In-flight work requires the same safe worker transition as rollout.

## 14. Completion boundary and follow-up decisions

The feature is complete only when an investigator can use the mixed-batch and review-queue journeys, process the intended saved revision through the existing pipeline, recover from failures without losing work, and inspect the selected people and original audio through the resulting source links.

Truth/claim-policy redesign, automatic speaker recognition, cross-recording voice identity, video review, translation editing and a new audio-specific extraction engine remain outside scope. Ordinary safety checks, existing grounding policy and preservation of investigator edits remain in force.

Resolve implementation discoveries within this plan and retain the accepted workflow. In particular, stage 4 must settle exact binding propagation and source-contribution replacement before accepting post-processing updates. If either requires additional work, record that work and its acceptance evidence rather than silently dropping identity linking or the update journey.

No additional product question is required to start implementation from this plan. Final endpoint naming, migration shape and renderer schema can follow the decisions above and repository conventions, with any material departure recorded here.
