# 5. Loupe landing zone for a fresh port of v1

Read-only, 2026-10-29, on `integration/evidence-main-reunion`. Scope set by Neil: Loupe's existing Cellebrite
code is outdated and is replaced; this report covers how a fresh port should fit Loupe.

## 0. What a port replaces

- **Engine:** `evidence-engine/app/pipeline/cellebrite/*.py` (about 4,000 lines, a copy of v1's
  `ingestion/scripts/cellebrite/` taken around 2026-05-15) and `pipeline/cellebrite_ingestion.py`, which runs
  the job and turns log lines into progress by regex (`:80-101`); `recovery.py` (a JSON checkpoint and a
  per-report file lock, `:22-52`); engine routes `api/routes/cellebrite.py:59,113`; arq function
  `worker.py:64-73`.
- **Backend:** `backend/routers/cellebrite.py` (35 routes against v1's 45);
  `backend/services/neo4j/cellebrite_service.py` (4,759 lines); `cellebrite_intersection_service.py`; upload
  detection in `routers/evidence.py:267-428,491-546,1204-1260` and `evidence_upload_groups.py:238-284`;
  `/api/evidence/cellebrite/check|process` at `evidence.py:2022,2054`; migrations `20260515_…`,
  `20260518_…` adding `cellebrite_*`, tag and geotag columns to `evidence_files`.
- **Frontend:** `frontend_v2/src/features/cellebrite/` (about 15,800 lines, 9 tabs); route
  `app/routes.tsx:163`; nav `components/ui/sidebar.tsx:64`. v1's Report, Search & Discovery, identity merge,
  callouts, timezone and PDF export are absent.
- **How far v1 moved on:** about 50 Cellebrite commits since 2026-05-15; v1's writer handles 46 types against
  Loupe's 30 (Notification, Voicemail, DictionaryWord, NetworkUsage, InstalledApplication, Journey, Note,
  ActivitySensorData and others missing, v1 `neo4j_writer.py:1175-1228`).

Defects in the old Loupe code, read from source: a Person shared across phones keeps only its first report
key (`neo4j_writer.py:246-251`), so shared-contact detection (`cellebrite_service.py:487,673-676`) cannot see
a contact on two phones, and `delete_phone_report` (`:371-377`) removes contacts another phone uses;
duplicate media skipped for attachment lookup (`file_linker.py:211`); report hashes trusted over bytes
(`:204-206`); unused hooks `useCheckCellebriteFolder` and `useProcessCellebriteFolder`
(`hooks/use-cellebrite.ts:447-474`).

## 1. How Loupe's evidence engine ingests evidence

**Getting files in (backend):**
- `POST /api/evidence/upload` (`evidence.py:1150-1290`): staging at `EVIDENCE_ROOT_DIR/_staging` (`:60`);
  safe zip extraction (`_extract_archive_to_staging`, `:335-394`); normal files become `evidence_files` rows;
  phone reports detected by the UFED namespace in the first 4 KB (`:65,267-275`), moved into the case
  directory without rows (`:1224-1231`) and queued (`:1248-1268`).
- Resumable uploads through `/api/evidence-upload-groups` (`frontend_v2/src/features/evidence/resumable-upload-groups.ts:27`):
  `register_payload` (`evidence_upload_groups.py:238-268`) removes nested phone roots and records a dispatch
  receipt with `request_id = uuid5(group, 'processing:'+root)`; `dispatch_reports` (`:278-286`) sends it to
  the engine.
- Ordinary processing via `evidence_engine_client.upload_file*` (`services/evidence_engine_client.py:65-148`);
  phone reports have their own call (`:150,186`).

**Queue and workers (engine):**
- arq on Redis; `WorkerSettings` with `max_jobs=4`, 4-hour `job_timeout`, `max_tries=3`, cron jobs for the
  stale-job janitor, dispatch recovery and chunk recovery (`worker.py:72-88`).
- Financial PDFs have their own queue and worker (`PdfReviewWorkerSettings`, `:91-102`). **A phone report
  should copy this pattern** so a multi-hour extraction does not hold a general slot.
- Containers `owl-v2-evidence-worker` (`docker-compose.yml:152-224`) and `owl-v2-evidence-pdf-worker`
  (`:226-229`); files under `STORAGE_PATH=/data/files`; phone reports use `CELLEBRITE_DATA_ROOT=/data/evidence`
  (bind mount of `./evidence-data`, the backend's `EVIDENCE_ROOT_DIR`); `stop_grace_period: 14500s`.
- Durable idempotent dispatch through an outbox (`services/batch_dispatch.py:17`,
  `pipeline_run_state.transition_batch_dispatch`).
- `Job` model (`models/job.py:28-80`) with `job_type`, `merge_payload`, `pipeline_state`, pause fields,
  `quality_report`, transcription fields, `source_evidence_file_id`.

**Progress, pause, recovery:** fixed `JobStatus` enum (`job.py:14-25`) with no phone stages; progress on Redis
`job:{id}:progress`, relayed by `backend/routers/evidence_ws.py:6`; `run_controlled`
(`services/ingestion_control.py`) gives cooperative pause, resume and heartbeat (`:14-26`), reaped by the
janitor; `services/ingestion_checkpoints.py` gives durable JSON work units with atomic rename and fcntl
locks. The engine's own pipeline (`pipeline/orchestrator.py`): financial pre-stage first (native bank files
refused, `:95-118`); text extraction, summary, chunking, embedding into ChromaDB `case_{id}_documents`,
entity extraction; the grounded-claim ledger (`:251-272`, `services/claim_ledger.py`); resolution,
summaries, graph write.

**Where data lands:** Postgres `jobs`, `evidence_files`, `evidence_document_texts` (content, sha256,
`source_locations`, `job.py:82-100`), `evidence_claims` (quote, `source_location`, confidence, status,
`job.py:128-155`), `evidence_table_geometry`; Neo4j entities merged by `key`/`case_id`; ChromaDB one
collection per case; files on disk. `extract_text.py` already handles audio, video and images (`:36-39`), but
phone media registered today get `status="unprocessed"` (`evidence_db_storage.py:617`), are hidden from the
evidence list unless `include_cellebrite_artifacts` (`evidence.py:811-832`), and are skipped by financial
auto-read (`financial/auto_read.py:107,515`): none is ever transcribed, OCR'd or embedded.

## 2. Financial patterns a phone port must follow

- **Proof class computed, never set:** `ProofClass` p0 to p4 (`postgres/models/enums.py:20-39`, "never
  user-settable"); `assign_proof_class(shape, reconciliation)` (`financial/proof_class.py:144-209`).
  Chat, email and interviews are `SourceShape.unstructured_narrative`, always p4, never admitted or counted
  (`:186-187`). A dollar amount in a WhatsApp message enters as a p4 assertion with a speaker. Any grading of
  phone records themselves must likewise be computed by a pure function.
- **Corrections appended, never overwritten** (`financial/corrections.py:1-6`): original fields and locators
  kept, a supersession chain, a revert is another correction; every decision written through
  `decisions.record` with a named `Actor` (`decisions.py:127,252`); only the current row
  (`superseded_by_id IS NULL`) feeds totals and the graph (`identity_graph.py:110-111`). The old Loupe phone
  code writes `device_name_override` straight into Neo4j with no audit (`neo4j_writer.py:471-473`).
- **Citation:** `references.py` gives a stable `ref_id` from the document sha256 and row content hash
  (`:338,394`); `locators.py` integer-millipoint page boxes; generic evidence uses `evidence_claims.quote`
  plus `source_location`. Phone records carry natural locators: model id, report key, report XML sha256
  (computed today only in `recovery.py:14-19`), file id and sha256.
- **Flag, don't refuse:** `suspect_amounts.py` (`:143,178`). Phone equivalents: carved or deleted records,
  low decoding confidence, missing or ambiguous timestamps.
- **Custody:** `custody.py` states reported custody is not a finding of authenticity; record what the UFED
  report states as reported.

## 3. Cross-evidence features phone data should feed

- **Graph, timeline, map** (`graph_service.py`, `timeline_service.py`, `geo_service.py`) query without label
  filters, scoped by `active_node_predicate` (`driver.py:20-28`), so phone nodes already land unfiltered and
  could swamp them; the timeline reads `timestamp` or `date` and filters on `labels(n)[0]`
  (`timeline_service.py:24-43,127`). A port needs a deliberate policy.
- **Search, chat, workspace AI:** `search_case_text` reads `evidence_document_texts.source_locations`
  (`evidence_text_search_service.py:133-190`); workspace AI cites claims (`workspace_ai_service.py:569-654`);
  RAG uses ChromaDB. Phone messages reach none of these. The seam: write threads and transcripts as
  `evidence_document_texts` rows with per-message `source_locations`.
- **People and counterparties:** `financial/identity_graph.py` writes reviewed links (`REVIEWED_SAME_IDENTITY`,
  `HOLDS_ACCOUNT`) from the SQL audit chain (`:77-128,153-258`) to any case entity by `key`, validated unique
  (`validate_graph_targets`, `:131-151`; requests from `account_identity.py:42-57,135-142`). Nothing links
  phone contacts to counterparties today; `account_mentions.py` deliberately does not read telephone numbers
  as account numbers.
- **Entity resolution:** document entities resolve through ChromaDB `case_{id}_entities`; phone Persons never
  join it.

## 4. frontend_v2 conventions

Feature folders `src/features/<name>/{api.ts, hooks/, components/, lib/, types.ts, stores/}`; all calls via
`fetchAPI` (`src/lib/api-client.ts:20`), protected media via `lib/protected-file.ts`; lazy routes
`src/app/routes.tsx:155-170`; nav `components/ui/sidebar.tsx:62-66`; shortcuts
`hooks/use-global-shortcuts.ts:36-43`; vitest `unit` and `browser` projects (`frontend_v2/vitest.config.ts`);
`fireEvent` not `userEvent`; user-facing text follows the Alex rules.

## 5. Constraints

`CLAUDE.md`: enterprise grade; read the source; one unit at a time; Python 3.10 in the backend; case material
never committed; commits through a temporary index; flag don't refuse; corrections keep both values; proof
class computed. `docs/loupe-build-state.md`: the engine suite needs Python 3.12 or later. `evidence-engine/CLAUDE.md`:
Neo4j writes merge on `id`; every entity needs `source_quote` and `confidence`; progress via Redis pub/sub;
storage `{STORAGE_PATH}/{case}/{job}/{file}`. Fragility: the phone job imports the backend in-process and
rewrites `DATABASE_URL` (`cellebrite_ingestion.py:35-51`); the detector imports `services.neo4j_service`
(`detection.py:46`).

## 6. Recommended seams (recommendations at the time; the specifications settle them)

1. Keep the upload and dispatch path; replace the engine job body; give phone jobs their own queue and worker.
2. Port v1's knowledge; keep Loupe's pause and checkpoint wrapper; structured progress; no in-process backend import.
3. Provenance on every record: source digest, model id, report key, deleted state, decoding confidence, run id;
   verify media hashes and flag mismatches.
4. Separate what was read from what was decided: decisions through `decisions.record`, projected into Neo4j.
5. Feed text into the shared stores.
6. Financial link only through the reviewed identity path; money in messages is p4.
7. Fix shared-Person ownership with membership.
8. Rebuild v1's components in Loupe's conventions.

Not determined at the time: runtime behaviour; v1's delete path for shared Persons (later verified
destructive, report 1); memory on large reports.
