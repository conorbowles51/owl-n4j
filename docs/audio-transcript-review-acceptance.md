# Audio transcript review: implementation and acceptance

Original acceptance: 26 October 2026, baseline `76f7848f` plus the local implementation. Release preparation is recorded below on 3 November. **The verification in this document is local; deployed workflow acceptance has not been recorded.** No client evidence was used, and no running installation ingestion was interrupted.

## Investigator workflow

The normal Process entry points share the existing admission guard. When a selection contains unreviewed audio and compatible review services are available, the investigator chooses once:

- **Transcribe, then review:** documents continue through their normal pipeline. Each recording runs a finite transcription job, saves its original text and turns, and releases its worker. Existing saved transcripts are reused and wait for review.
- **Process without review:** new recordings keep the original uninterrupted text-processing behavior. Previously saved recordings use their selected immutable revision without another transcription. This action does not mark a transcript reviewed.

Transcript review reuses the existing player, speaker naming and reversible speaker grouping. It adds word corrections, turn reassignment, optional selection of an existing case Person, explicit Save draft and Mark reviewed actions, review-and-process, original-text inspection, and navigation between recordings. A selected Person's summary/notes help distinguish matching names. Linking retains the actual graph ID; changing a display name does not rename that case entity.

The toolbar's **Audio review** button shows a pending count and opens the scoped queues for the current folder, its subtree, or the entire case. Inside the panel, **Preview ready audio** previews the exact saved revisions and files before processing; it excludes already published recordings. Changed recordings use **Update processed transcript** individually. The viewer distinguishes the working revision from the last processed revision. Unsaved changes are protected when closing, following the file-location link, or leaving the browser.

Read-only case members can read transcripts and original text. Edit, review and processing are enforced on the server using the existing evidence-upload permission. A plain-text legacy transcript remains editable without fabricated speaker turns. Ordinary Process and Retry do not regenerate an existing transcript.

An already processed legacy recording keeps its processed status when adopted into saved revisions. Later material edits show the changed-since-processing badge. Its historical processed revision is not invented if the older system did not record one. Transcription format support remains that of the existing audio reader; this change does not add new decoders or an automatic retranscription operation.

### Compact Evidence toolbar, 3 November 2026

Replaced the three persistent audio controls with one **Audio review** button.
Its panel contains scope selection, separate awaiting-review and ready counts,
review navigation and the existing explicit processing preview. An empty scope
explains when transcripts appear and how to prepare recordings; loading and
recoverable errors appear inside the panel. Search/filters and file actions have
separate rows. Delete appears when files are selected.

Checked the local Chrome interface at its original size and a 1280 × 900 viewport:
the panel fits, scope selection works, Review transcripts opens the saved viewer,
and closing returns to Evidence. Selection reveals Delete and enables Process;
clearing selection removes Delete. Restored the original browser size, folder
scope and Processing sidebar. No transcript was edited or approved, no processing
was requested, and no service was restarted. TypeScript and ESLint checks passed.
The bulk-ready confirmation remains in place but was not exercised in this
layout check. This UI refinement is local, not a deployed verification claim.

## Implementation

| Area | Final behavior |
| --- | --- |
| Persistence | Additive source, immutable revision, state-pointer, review-receipt and processing-plan tables. Original machine text/turns remain separate from investigator overrides. Case/file composite foreign keys and immutable-update triggers protect identities. |
| Audit | New records append private digests and revision/actor references to the existing case audit chain. Transcript bodies, processing context and original recordings are omitted from ordinary audit payloads. |
| Concurrency | Saves require the expected revision. Conflicting edits return 409. Retrying the same saved edit or review receipt is idempotent; it cannot approve a newer draft. A no-op save preserves readiness. |
| Processing selection | A 30-minute plan freezes file IDs, folders, hashes, transcript revisions and effective folder context. Execution rechecks case access, bindings, admission and file state. Actor-owned receipts, file reservations and bounded dispatch leases prevent duplicate acceptance. |
| Recovery | Existing durable engine outbox, stable ARQ identities, upload-response recovery, reconciliation and pause/resume are reused. Accepted groups survive a later group failure. Retrying a receipt skips its previously accepted jobs, including completed jobs. |
| Preparation | `audio_review` uses the existing extractor/diarizer through `process_file`, then stops. No document summary, chunks, embeddings, entity extraction or graph writing occur in this stage. |
| Ingestion | Both orchestrators adapt a saved revision into the ordinary text pipeline. Names, corrections and bindings participate in its content identity. Speaker context survives a turn that spans text chunks. |
| Identity | Explicit speaker headers and unambiguous first-person attribution retain the selected Person ID through consolidation, resolution and graph writing. Other people mentioned in speech remain separately resolved. Missing, cross-case or recycled targets are rejected. |
| Sources | Corrected character offsets and original audio times travel with grounded source locations. Searchable canonical audio text is published after graph writing, rather than when a private draft is saved. |
| Updates | Superseded **ledger-backed** audio contributions are reconciled in the same Neo4j transaction as replacement graph writes. Other file claims and manual fields are preserved. Immutable claims remain historical records. Chunk publication retains its durable retry mechanism. |
| Large inputs | Queue/history/selection lists are paginated; preview context is shared per folder. More than 150 transcript turns use virtualization, with a bounded conversation overview. Playback, search and edit controls remain outside the turn list. |

The existing PostgreSQL/Neo4j/ChromaDB stores do not form a single distributed transaction. Graph replacement is transactional, and chunk publication is recoverable through the existing outbox. This is not a claim of an atomic three-store commit. Unprovenanced legacy graph material is retained rather than assigned to a source by filename and deleted speculatively.

## Verification performed

The full local service exercise used separate PostgreSQL, Redis/ARQ, Neo4j and ChromaDB instances, isolated API/worker processes and Chromium. All names, PDFs, text documents and recordings were synthetic. Production services and case data were not changed.

Two provider boundaries were tested explicitly:

1. Deterministic transcription/model adapters exercised the complete processing journey through real queues, databases, graph writes and vector publication. They let the checks assert the exact text, IDs, revision and number of transcription calls.
2. The existing real transcription client/extractor processed a generated spoken recording using `gpt-4o-transcribe-diarize`. It returned seven timestamped turns and two speaker labels, recognizing the expected synthetic dialogue. This was a real-provider smoke test, not a transcription-accuracy benchmark or an evaluation of downstream model quality.

### Automated checks

| Check | Result |
| --- | --- |
| Backend transcript, synchronization, upload recovery, legacy speaker naming, admission guard, deployment gate and folder-context regressions | 64 passed |
| Engine transcript/binding/replacement, audio reader, summaries, chunk publication, pipeline state, consolidation, upload security, dispatch and canonical text regressions | 74 passed |
| Evidence unit tests plus admission API/response regressions | 184 passed |
| Chromium transcript review, document viewer, admission hold, ingestion isolation and file-location journeys | 13 passed |
| Frontend production build and TypeScript | Passed; existing large-chunk/dynamic-import advisories remain |
| ESLint on changed/new frontend sources; `git diff --check`; Compose configuration | Passed |
| Shared PostgreSQL migration rehearsal | Upgraded through `20261026_audio_integrity`; current head confirmed |

The PDF viewer browser assertion now waits for pages to finish remounting after zoom before checking its bounded page count. Existing deprecation warnings and development WebSocket cancellations during fast completion/reload were observed; no application console errors occurred in the final mixed-batch runs.

### Acceptance evidence

| ID | Evidence and boundary |
| --- | --- |
| A01 | Fresh audio, PDF and TXT selected together; Process without review completed all three. Audio used `machine_text_v1`; its revision was published without a review receipt. |
| A02 | Review-first audio saved its machine source and became unprocessed/awaiting review. The preparation test stops immediately after source storage; actual preparation released its worker. |
| A03 | In the final mixed browser run, both documents completed while the recording remained awaiting review. |
| A04 | Browser corrected the typo, linked John and Eric to exact case people, saved, closed, reloaded and reopened. Correction and links survived; original text and recording hash were unchanged. |
| A05 | Tests distinguish draft/review/publication, preserve no-op readiness, invalidate readiness after edits, and reject a repeated review of a superseded draft. |
| A06 | Actual published canonical text and active Chroma chunks contained the correction. Saved-revision jobs skipped transcription. Both single and batch adapters have regression coverage. |
| A07 | Same-name bound speakers remain separate through deduplication/merging tests. Real graph checks confirmed both selected Person IDs received the appropriate recording provenance. |
| A08 | Cycles, unknown turns and conflicting group identities are rejected without changing the saved revision. Case/Person/recycle-bin binding checks are enforced at review/dispatch and final graph writing; these last checks were also reviewed in code. |
| A09 | Scoped queue test covers 103 recordings across root/subfolder/publication states, including a second page. Browser confirmed the ready-only preview and processed its one listed recording. |
| A10 | Stale edit and stale processing previews return conflicts. A test edits a draft during handoff and confirms the job still receives the originally selected revision. |
| A11 | Lost save/review responses are covered by tests. Two simultaneous real HTTP submissions of one plan created one engine job. A changed idempotency key is rejected. |
| A12 | An injected failure after replacement graph writes, before commit, preserved the previous graph, canonical text and published pointer. Both a changed revision and an unchanged, already active revision were exercised; the latter retained its active search chunks during failure. Resume completed the same job/revision without another transcription. Earlier isolated-worker restart recovery was also exercised. |
| A13 | Chromium searched and edited the final turn of a 2,000-turn transcript while keeping rendered turns bounded. Legacy unsegmented text, turn corrections and chunk-continuation attribution have coverage. This is not an hours-long audio quality benchmark. |
| A14 | Real graph source locations retained both revision identity and original audio times after a length-changing correction. From the entity table, the source button opened the corrected recording, and Open file location returned to its Evidence row. |
| A15 | Explicit update retired older audio claims and the older active search revision. A synthetic investigator description and claims from other documents survived. Historical claims remained in the ledger. The injected failure test verified preservation before successful continuation. |
| A16 | Actual router tests enforce view-only restrictions and reject another case's evidence/history. Plan ownership and entity-ID validation are server-side. |
| A17 | Real PDF/TXT processing completed in both mixed modes. Admission, folder context, upload recovery, PDF viewing and isolated reading/ingestion regressions passed. No live financial or video evidence was processed for this test. |
| A18 | Synthetic files uploaded through the normal HTTP API, followed in Chromium by mixed selection → review choice → documents complete → edit/link/save → close/reload/reopen → mark reviewed → bulk-ready → published graph/search → entity source → Evidence return. Narrow viewport and unsaved-close behavior were also exercised. |
| A19 | Preparation is a finite job on its own compatible audio queue; waiting for review has no queued/running job. General ingestion and financial reading retain their queues. Existing ingestion-isolation browser regressions passed. |
| A20 | Additive migrations were rehearsed on isolated PostgreSQL. Attempted source/revision/review mutation and an invalid revision pointer were rejected and rolled back. The recorded case audit chain verified. Feature controls require the versioned worker heartbeat; application rollback retains data/schema. Live rollout remains pending. |

## Focused security review

Read-only review of the new HTTP surfaces, shared source/revision service, handoff metadata, engine adapter and graph replacement found no unresolved high or critical finding in this feature. This is not an audit of the entire platform.

- `backend/routers/transcripts.py`: every evidence/revision/queue read authorizes current case access; mutations require evidence upload; processing plans are bound to the initiating actor. IDs in a URL or body do not authorize access.
- `backend/services/transcript_review.py`: saved revisions are immutable, source/file/case identity is checked, expected-revision conflicts preserve drafts, and edit payload/speaker/name limits are enforced.
- `backend/postgres/alembic/versions/20261026_audio_integrity.py`: composite foreign keys prevent cross-evidence revision pointers; prospective audit records contain digests rather than transcript bodies.
- `evidence-engine/app/pipeline/audio_review.py`: the selected revision must belong to the requested file and case, and uploaded bytes must match the preserved recording hash.
- Binding lookup and final graph validation use parameterized IDs and case scope. Recycled or missing people cannot silently be recreated from a stale selection.
- Existing upload filename/path controls, authentication/service-key boundaries, admission checks and text-prompt security remain in use. A speaker label does not introduce a different truth-assessment policy.

## Release and operating instructions

### Release preparation, 3 November 2026

The user authorized committing and pushing the audio ingestion and UI changes.
Prepared the code-only release in an isolated checkout on the shared branch,
preserving concurrent phone capture, file-picker improvements and the database
thread-pool changes. Transcript-plan routes and mixed audio preparation keep
database work off the API event loop. Ordinary document completion retains its
existing behavior; a publication catch-up also persists the transcript pointer
when the file already has a processed status.

Fresh checks: 83 backend tests, 55 engine tests, 170 Evidence unit tests and 16
Chromium workflow tests passed. The production frontend build (including
TypeScript and zero-warning ESLint) passed, with existing bundle advisories.
The upload-toolbar browser tests isolate the audio panel's query dependency,
and PDF browser fixtures reset their shared page cache between tests.

The additive merge revision `20261103_merge_audio_review` joins the preserved
audio migration history with `20261103_phone_result_snapshots`. Existing local
audio installations retain their applied revision IDs. A fresh isolated
PostgreSQL database upgraded through the shared phone revision, then both audio
migrations and the merge; Alembic reports one current head. Release uses the existing
ingestion-idle deployment guard; no active local jobs were stopped or retried.
Client evidence, generated screenshots, credentials and unrelated workspace
changes are excluded. Publication and deployed workflow verification are
separate from these local checks; live acceptance is not claimed here.

### Local missing-schema repair, 28 October 2026

The local installation was still at `20261019_workspace_setup` while the new
routes were running. Processing preview creation and transcript reads returned
HTTP 500 because `evidence_processing_plans` and `evidence_transcript_state`
did not exist. Applied the two existing additive migrations through
`20261026_audio_integrity` using `alembic upgrade head` from `backend`, with
3-second lock and 30-second statement timeouts. No services were restarted and
no evidence processing jobs were submitted or retried.

Verified the configured local database reports the current schema, an ORM
transcript-state query succeeds, and a synthetic processing-plan insert succeeds
and is fully rolled back. The already-running backend's `/health` reports
`status: ok`, `postgres: connected`, and `database_schema: current`. This is a
local database repair, not a deployment or a claim of live workflow acceptance.
The schema migration step below remains required before running the new routes
on another installation.

### Local manual-test startup, 2 November 2026

At the user's request, started the Windows development frontend at
`http://localhost:5174` and backend at `http://127.0.0.1:8002`, using the existing
local Docker databases and evidence API on port 8003. Ran `alembic upgrade head`;
the configured database was already at `20261026_audio_integrity`. All five
transcript-review/processing-plan tables were confirmed present.

The ingestion guard reported no queued or running work both before the rebuild
and immediately before switching containers. Rebuilt the engine API and general,
PDF and audio-review workers from the current working tree. Enabled
`AUDIO_TRANSCRIPT_REVIEW_ENABLED=1` in the ignored local `.env` and the matching
containers. The audio worker uses `gpt-4o-transcribe-diarize`; FFmpeg, FFprobe and
an existing provider-key configuration were confirmed available.

Startup verification confirmed the login screen renders in Chromium, the
frontend API proxy responds, backend health is `ok` with a current schema, and an
authenticated capability request through the frontend returns `enabled: true`,
`configured: true` and `engine_compatible: true`. The dedicated audio worker's
readiness heartbeat was present. These are local startup checks; no recording
was submitted, no new provider request was made, and deployed workflow
verification remains pending. Existing accounts are retained for manual testing.

The feature is **off by default** in the example configuration; the local
installation above is enabled for manual testing. This implementation does not
authorize cancelling or restarting the team's active ingestion to activate it.

1. Use the existing authorized release process and ingestion-idle guard. Preserve active general, audio and financial work. Push remains the installation's deployment trigger when this feature is released; no separate manual deployment was performed here.
2. Run `alembic upgrade head` to apply shared backend migrations through `20261103_merge_audio_review`, including both audio migrations. Retain a backup and the additive tables during application rollback. The downgrade guards intentionally refuse to discard saved transcripts/audit coverage.
3. Deploy matching backend/engine code and the Compose service `evidence-audio-review-worker` (`arq app.worker.AudioReviewWorkerSettings`). It consumes `arq:audio-review-v1`; older general workers never consume that queue. Mixed batches containing revision-aware audio are routed to that compatible queue as well.
4. Set `AUDIO_TRANSCRIPT_REVIEW_ENABLED=1` for the backend, engine API and compatible audio worker when activation is authorized. The API advertises protocol 1 only while the audio worker's 90-second readiness heartbeat is present. The authenticated backend capability must report `enabled: true` before review controls are expected.
5. Repeat the synthetic mixed-batch, saved-review, source-return and failure/retry journey on the deployed revision. Record the deployed revision and live verification separately. Those checks have not been performed on the live installation.
6. To pause new review use, disable the capability flag. Retain source/revision tables and a compatible worker for already accepted jobs. Saved drafts/history remain readable; disabling controls does not erase them. Do not send queued revision-aware work to an older general worker.

Provider fixtures, runtime prompts, generated recordings, local credentials, browser state, screenshots and integration databases are local test artifacts and must not be staged or pushed. Unrelated financial/landing/workspace changes were not included in this feature's verification claim.
