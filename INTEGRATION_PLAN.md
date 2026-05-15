# OWL Branch Reunion Integration Plan

This document is the working plan for bringing `main` and `evidence-engine-migration` back onto one branch while preserving the valuable work from both.

The integration is not a normal textual merge. The branches now represent two different app architectures. The safe approach is to use `evidence-engine-migration` as the integration spine, then manually port Neil's `main` work into that architecture.

## Current Decision

Create a new integration branch from `evidence-engine-migration`, port Neil's work into it, verify end to end, then make it the new `main`.

Preferred final history strategy:

1. Back up both current branch tips with tags and/or branches.
2. Build and verify the integration branch.
3. Record `main` as integrated using an `ours` merge, so Git history knows the lines are reunited while preserving the integration branch tree.
4. Fast-forward or update `main` from the integration branch where possible.
5. Use `--force-with-lease` only as a fallback, after branch freeze and backups.

## Non-Negotiable Constraints

These are hard constraints for the integrated result.

- Runtime app state must be Postgres-backed.
- No JSON file storage as a source of truth.
- Neo4j remains the graph store.
- JSON can exist for static configuration, prompts, test fixtures, migration inputs, or import/export artifacts, but not for live app state.
- Neil's UI must be reimplemented in `frontend_v2`.
- Do not revive `frontend/src` as a live UI surface.
- Legacy React files from `frontend/src` are reference material only.
- Keep the evidence-engine branch's frontend, backend service split, Docker stack, and Postgres evidence/workspace/chat architecture where there is contradiction.
- Keep `backend/services/neo4j_service.py` as the thin facade over `backend/services/neo4j/*`.
- Do not reintroduce Neil's monolithic `backend/services/neo4j_service.py`.

## Branch Facts From Investigation

- Current branch: `evidence-engine-migration`
- Other branch: `main`
- Merge base: `a73da708df1671cf111801a692758ed241c9266e`
- `main` unique commits: 129 after the 2026-05-15 fetch
- `evidence-engine-migration` unique commits: 74
- Files changed from merge base on `main`: 246
- Files changed from merge base on `evidence-engine-migration`: 402
- Shared changed files: 19
- Dry merge reports conflicts in backend routers, backend services, `backend/main.py`, `backend/routers/__init__.py`, and `deploy/deploy.sh`.
- Current worktree had an unrelated dirty path: `.claude/worktrees/funny-jepsen-d4d19f`. Do not touch it unless explicitly needed.

Shared changed files observed:

- `.claude/settings.local.json`
- `backend/config.py`
- `backend/main.py`
- `backend/requirements.txt`
- `backend/routers/__init__.py`
- `backend/routers/cases.py`
- `backend/routers/chat.py`
- `backend/routers/chat_history.py`
- `backend/routers/evidence.py`
- `backend/routers/financial.py`
- `backend/routers/graph.py`
- `backend/routers/workspace.py`
- `backend/services/evidence_storage.py`
- `backend/services/financial_export_service.py`
- `backend/services/neo4j_service.py`
- `backend/services/rag_service.py`
- `backend/services/workspace_service.py`
- `deploy/deploy.sh`
- `frontend/src/components/financial/FinancialTable.jsx`

## Latest Remote Fetch Note

Before starting implementation, `origin/main` was fetched again on 2026-05-15. It had moved from `903b9a2` to `07192f3`, adding 21 commits. `origin/evidence-engine-migration` had no new commits relative to the local branch.

The new `main` commits are almost entirely Cellebrite/product-workflow changes. These must be included in the integration plan:

- Unified contacts across phones by canonical phone number.
- New `backend/services/phone_normalise.py` helper.
- Cellebrite contacts endpoint: `/api/cellebrite/contacts/unified`.
- Direction-agnostic participant filtering using `participant_keys`.
- Thread detail `anchor_key` support for opening a conversation around a specific message.
- Comms participants picker with "Any direction" involvement mode.
- Comms compact toolbar.
- Resizable panes in Comms, Locations, and Events.
- Slide-in / flyout right rail behavior.
- Rail scroll-to-message and missing-message handling.
- Overview "Filter Comms" actions on rows.
- Overview calls/messages/emails/locations opening full conversations in the rail.
- Locations trajectory toggle and fly-to behavior.
- Overview locations limit cap raised to 10,000.
- Backend performance work for unified contacts and slow Cellebrite tabs.

These additions reinforce the earlier conclusion: the legacy `frontend/src` code should be treated as product reference, and the resulting experience should be rebuilt in `frontend_v2`.

## High-Level Integration Shape

The integrated app should look like this:

- Backend API from `evidence-engine-migration`, with Neil's routes ported in.
- Postgres as source of truth for cases, evidence metadata, chat, workspace, tasks, triage state, case profiles, background task state, and any other runtime state.
- Neo4j for graph nodes/relationships, including Cellebrite-derived graph data.
- Evidence Engine for generic evidence processing.
- Cellebrite as a structured custom ingestion path that registers media/evidence in Postgres and writes phone-derived graph data to Neo4j.
- `frontend_v2` as the only active frontend.
- Neil's phone viewer, triage, case profiles, and financial additions rebuilt as v2 features.

## Backup And Branch Procedure

Before implementation:

```powershell
git fetch origin
git switch evidence-engine-migration
git pull --ff-only

git tag backup/main-before-reunion origin/main
git tag backup/evidence-engine-before-reunion evidence-engine-migration

git branch backup/main-before-reunion origin/main
git branch backup/evidence-engine-before-reunion evidence-engine-migration

git switch -c integration/evidence-main-reunion
```

Push backups if this will be shared:

```powershell
git push origin backup/main-before-reunion
git push origin backup/evidence-engine-before-reunion
git push origin refs/tags/backup/main-before-reunion
git push origin refs/tags/backup/evidence-engine-before-reunion
```

Preferred finalization after verification:

```powershell
# From integration/evidence-main-reunion, record main history without changing the tree.
git merge -s ours origin/main -m "Record main as integrated into evidence engine reunion"

# Then update main through PR or protected-branch process if possible.
```

Force-push fallback:

```powershell
git push --force-with-lease origin integration/evidence-main-reunion:main
```

Only use the fallback after everyone has stopped pushing to `main`, backups are pushed, and the integration branch is verified.

## Workstream 1: Runtime Storage Must Become Postgres-Only

This is the first real dependency. Several files on `evidence-engine-migration` and `main` still use JSON-backed runtime services. They cannot remain active in the final app.

### Must Replace Or Retire

These are currently JSON-backed runtime state or state-like services:

- `backend/services/evidence_storage.py`
- `backend/services/evidence_log_storage.py`
- `backend/services/background_task_storage.py`
- `backend/services/case_storage.py`
- `backend/services/chat_history_storage.py`
- `backend/services/snapshot_storage.py`
- `backend/services/snapshot_chunk_storage.py`
- `backend/services/last_graph_storage.py`
- `backend/services/wiretap_tracking.py`
- `backend/services/presence_service.py`
- `backend/services/geo_rescan_service.py`
- `backend/services/system_log_service.py`
- `main:backend/services/triage/triage_storage.py`

Important caveat: some of these may be legacy-only routes that can be removed instead of ported. Do not blindly port unused legacy behavior.

### Active Imports To Audit

Observed JSON-backed imports still appear in:

- `backend/main.py`
- `backend/routers/backfill.py`
- `backend/routers/background_tasks.py`
- `backend/routers/cases_legacy.py`
- `backend/routers/evidence.py`
- `backend/routers/graph.py`
- `backend/routers/snapshots.py`
- `backend/routers/workspace.py`
- `backend/services/backup_service.py`
- `backend/services/evidence_service.py`

### Replacement Tables Needed

Add Postgres models and Alembic migrations for:

- Background tasks and task progress/files/metadata.
- Snapshots and snapshot chunks, unless snapshots are removed or redesigned.
- Wiretap processing tracking.
- Presence sessions.
- Last graph / generated cypher state, if still needed.
- Triage cases and triage stages.
- Evidence tags.
- Evidence-to-case-profile links.
- Case profiles/entities, unless their full state is moved into existing Postgres workspace models.
- System logs, if "no JSON storage" applies to logs as well.

### Existing Postgres Strengths To Keep

Already present in `evidence-engine-migration`:

- Cases and memberships.
- Evidence folders/files/logs.
- Chat conversations/messages/revisions.
- Workspace contexts, witnesses, theories, tasks, notes, findings, pinned items, deadlines.
- Cost records and AI pricing.
- Graph recycle bin items.
- Merge jobs.
- Processing profiles.
- Geocoding cache.

## Workstream 2: Backend Service Architecture

### Keep From Evidence Engine Branch

Keep these as the spine:

- `backend/main.py`
  - Evidence engine client lifecycle.
  - Redis close.
  - Evidence websocket router.
  - Job status subscriber.
  - Direct split Neo4j driver health check.
  - Evidence engine health check.
- `backend/services/neo4j_service.py`
  - Thin facade only.
- `backend/services/neo4j/*`
  - Split domain services.
- `backend/routers/chat.py`
  - Postgres conversations.
  - `conversation_id`.
  - `scope`.
  - `selected_entity_keys`.
  - `append_conversation_turn`.
  - `create_case_revision`.
  - Per-request LLM context and cost tracking.
- `backend/routers/chat_history.py`
  - Postgres chat history.
- `backend/routers/evidence.py`
  - Evidence engine uploads and job endpoints.
  - `EvidenceDBStorage`.
  - `process_db_files`.
  - `/engine/jobs*`.
- `backend/routers/evidence_folders.py`
  - Folder tree and folder processing.
- `backend/routers/graph.py`
  - Evidence-engine merge flow.
  - Merge jobs.
  - Advisory locks.
  - DB-aware recycle-bin behavior.
- `backend/routers/workspace.py`
  - Postgres/JSONB workspace storage.
  - Unified workspace build-graph endpoint.
- `backend/services/workspace_service.py`
  - Postgres workspace models.

### Port From Main

Port these into the evidence branch architecture:

- `backend/routers/cellebrite.py`
- `backend/services/cellebrite_service.py`
- `backend/services/cellebrite_intersection_service.py`
- `backend/services/geocoder.py`
- `backend/services/phone_normalise.py`
- `ingestion/scripts/cellebrite/*`
- `backend/routers/triage.py`
- `backend/models/triage_models.py`
- `backend/services/triage/*`
- `backend/services/triage_processors/*`
- `backend/routers/case_entities.py`
- `backend/services/case_entity_service.py`
- Case archive/unarchive behavior.
- Financial auto extract, notes upload, richer PDF sections.
- Chat view context.
- Workspace note/profile linking and related workflow improvements.
- Graph `/nodes-by-type` if still wanted.

### Do Not Port As-Is

- Neil's monolithic `backend/services/neo4j_service.py`.
- Main's JSON-backed workspace service.
- Main's JSON-backed evidence storage/tag/entity link helpers.
- Main's global LLM mutation pattern in chat.
- Main's legacy `/bulk-merge-entities` without redesign.
- `data_version/audit_status` financial filtering as-is; reconcile with v2 `mode=transactions|intelligence`.

## Workstream 3: Cellebrite Integration

Cellebrite is Neil's largest feature and the most important non-textual merge.

### Desired Final Shape

- Cellebrite report detection and ingestion are custom structured ingestion flows.
- UFED XML parsing writes phone-specific graph data to Neo4j.
- Cellebrite media/files register into Postgres evidence tables.
- Cellebrite attachment resolution uses Postgres evidence metadata.
- Generic document processing remains evidence-engine-owned.
- Cellebrite media attachments can later be processed by Evidence Engine as normal evidence files, but the phone report graph import should not be pushed through generic document extraction.

### Backend Pieces To Port

From `main`:

- `backend/routers/cellebrite.py`
- `backend/services/cellebrite_service.py`
- `backend/services/cellebrite_intersection_service.py`
- `backend/services/geocoder.py`
- `backend/services/phone_normalise.py`
- `ingestion/scripts/cellebrite/__init__.py`
- `ingestion/scripts/cellebrite/file_linker.py`
- `ingestion/scripts/cellebrite/ingestion.py`
- `ingestion/scripts/cellebrite/models.py`
- `ingestion/scripts/cellebrite/neo4j_writer.py`
- `ingestion/scripts/cellebrite/parser.py`

### Evidence Router Pieces To Port

From `main:backend/routers/evidence.py`:

- `/api/evidence/cellebrite/check`
- `/api/evidence/cellebrite/process`
- Duplicate detection and 409 force/replace behavior.
- Cellebrite artifact filtering during filesystem sync.
- Chunked/streaming safeguards for large report trees.
- Tag endpoints.
- Entity-link endpoints.
- `/api/evidence/by-entity`

### Neo4j Service Pieces To Port

Create:

- `backend/services/neo4j/cellebrite_service.py`

Expose methods through:

- `backend/services/neo4j/__init__.py`

Port methods from `main:backend/services/neo4j_service.py`, including:

- `get_cellebrite_reports`
- `find_existing_phone_report`
- `delete_phone_report`
- `get_cellebrite_cross_phone_graph`
- `get_cellebrite_timeline`
- `get_cellebrite_communication_network`
- `get_cellebrite_comms_entities`
- `get_cellebrite_comms_source_apps`
- `get_cellebrite_comms_threads`
- `get_cellebrite_thread_detail`
- `get_cellebrite_comms_between`
- `get_cellebrite_comms_envelope`
- `search_cellebrite_comms_messages`
- `get_cellebrite_events`
- `get_cellebrite_event_types`
- `get_cellebrite_location_tiles`
- `get_cellebrite_locations_in_tile`
- `get_cellebrite_event_tracks`
- `get_cellebrite_event_detail`
- `get_event_related`
- `get_overview_contacts`
- `get_overview_calls`
- `get_overview_messages`
- `get_overview_locations`
- `get_overview_emails`
- `get_overview_contact_detail`
- `get_unified_contacts`
- Attachment parent/model resolution helpers.

Also port required helpers:

- `_decode_reconciliation`
- `_normalize_date_bound`
- `resolve_file_parents`
- query builders and cursor helpers used by comms/events APIs.
- participant involvement filtering helpers used by `participant_keys`.
- anchor-window helpers used by `anchor_key` thread detail requests.
- phone-number normalisation helpers or imports from `phone_normalise.py`.

### Postgres Evidence Contract For Cellebrite

Current `EvidenceFile` has `metadata_` JSONB, but current `EvidenceDBStorage.add_files()` does not persist arbitrary metadata or flatten it in API output.

Final design should add explicit tables/columns where important for querying:

- `source_type`
- `cellebrite_report_key`
- `cellebrite_file_id`
- `cellebrite_model_id`
- `cellebrite_category`
- `tags`
- entity/profile links

Recommended approach:

- Use real columns for fields frequently filtered/sorted by Cellebrite UI.
- Use `metadata_` only for flexible low-value extras.
- Add proper indexes for report key, file id, model id, case id, and source type.
- Keep `legacy_id` if old exported/imported records need stable string references.

Required storage methods:

- `add_cellebrite_files(...)`
- `get_by_cellebrite_file_ids(case_id, file_ids)`
- `delete_by_cellebrite_report_key(case_id, report_key)`
- `list_cellebrite_files(...)`
- `add_tags(...)`
- `remove_tags(...)`
- `set_tags(...)`
- `get_tag_counts(...)`
- `link_entities(...)`
- `unlink_entities(...)`
- `list_by_entity(...)`
- `unlink_entities_from_all(...)`

### Cellebrite Caveats

- Neil's `file_linker.py` writes directly to `evidence_storage._records`; this must be refactored.
- Current evidence branch IDs are UUIDs; Neil's JSON storage IDs are `ev_<hash>` strings. UI and APIs must tolerate UUID evidence IDs.
- Current v2 frontend has no Cellebrite feature at all.
- `backend/routers/cellebrite.py` imports `evidence_storage`; this must be replaced before mounting.
- Latest `origin/main` also adds `phone_normalise.py`; port it or replace it with an equivalent backend helper.
- Deleting a phone report must delete Neo4j data and Postgres evidence rows/links for that report.
- Duplicate ingest flow must work before users can safely reprocess reports.
- Large UFED folders must not be registered as thousands of ordinary evidence files during generic filesystem sync.
- `reverse-geocoder>=1.5.1` and `ijson==3.5.0` may need to stay if Cellebrite/geocoder/parser paths need them.

## Workstream 4: Triage Integration

### Desired Final Shape

- Triage state lives in Postgres.
- Triage UI is reimplemented in `frontend_v2`.
- Triage can scan/classify/profile source files, then ingest selected outputs into an Owl case/evidence folder.
- Triage ingestion must register resulting evidence through the new Postgres/evidence-engine APIs.

### Backend Pieces To Port

From `main`:

- `backend/routers/triage.py`
- `backend/models/triage_models.py`
- `backend/services/triage/*`
- `backend/services/triage_processors/*`

### Postgres Tables Needed

Minimum:

- `triage_cases`
- `triage_stages`
- `triage_artifacts` or `triage_files`
- `triage_templates`
- `triage_scan_results`
- `triage_processor_results`

Use JSONB columns only for structured payloads inside Postgres, not for file storage.

### Triage Caveats

- `main:backend/services/triage/triage_storage.py` is JSON-backed and cannot be used.
- `ingest_bridge.py` calls legacy evidence service paths; adapt to `EvidenceDBStorage` and Evidence Engine.
- Triage uses server-side directory browsing. Path traversal, Windows path normalization, and permission checks are important.
- Triage is top-level, not case-nested, because triage cases are independent and later ingest into Owl cases.
- Triage should probably be a later slice after Cellebrite backend contracts are stable.

## Workstream 5: Case Profiles / Entities

Neil added investigator-curated profiles/entities. These must be preserved, but not using JSON evidence links.

### Desired Final Shape

- Use "Case Profiles" naming in UI to avoid conflict with v2 admin "Profiles" / processing profiles.
- Store profile state in Postgres, or store only graph projection in Neo4j and canonical profile state/links in Postgres.
- Link profiles to graph nodes, evidence files, workspace notes, and findings.
- Reimplement UI in `frontend_v2`.

### Backend Pieces To Port

From `main`:

- `backend/routers/case_entities.py`
- `backend/services/case_entity_service.py`

### Required Adaptations

- Replace `evidence_storage.list_by_entity`, `link_entities`, and `unlink_entities_from_all` with Postgres evidence/profile link tables.
- Decide whether `CaseEntity` remains a Neo4j node label or becomes Postgres-first with Neo4j projection.
- Keep the routes mounted at both:
  - `/api/case-profiles`
  - `/api/entities`
  if backwards compatibility is useful.

### Caveats

- Main's case entity service currently depends on JSON evidence links.
- V2 has admin processing profiles already, so do not label the UI simply "Profiles".
- Evidence-to-profile links should be queryable from both evidence and profile pages.

## Workstream 6: Frontend V2 Reimplementation

### Rule

Neil's UI must be reimplemented in `frontend_v2`. Do not merge or revive `frontend/src` as the live frontend.

Legacy files are product references only:

- `frontend/src/components/cellebrite/*`
- `frontend/src/components/triage/*`
- `frontend/src/components/entities/*`
- `frontend/src/context/PhoneReportsContext.jsx`
- `frontend/src/utils/cellebriteSearch.js`
- `frontend/src/utils/phoneIdentity.js`
- `frontend/src/services/api.js`

### Current V2 Already Has

- Case routes: graph, timeline, map, table, financial, evidence, chat, workspace, reports, settings.
- Evidence folder/file browser.
- Evidence uploads, delete, processing, jobs, previews.
- Financial v2 page with typed API/hooks/state.
- Workspace v2 page with context, witnesses, notes, findings, theories, tasks, deadlines, pinned evidence, documents, timeline.
- Graph/table/map/timeline pages.
- Admin users/profiles/logs/tasks/AI costs.

### New V2 Features To Build

#### Cellebrite

- Add route: `/cases/:id/cellebrite`
- Add active case nav item, likely near Evidence and Timeline.
- Treat Cellebrite like Graph: self-managed layout, probably no generic right `CaseSidePanel`.
- Build `frontend_v2/src/features/cellebrite`.
- Add typed APIs/hooks for:
  - reports
  - report delete/rename/patch
  - timeline
  - cross-phone graph
  - communication network
  - unified contacts
  - participants/involvement filters
  - comms entities/source apps/threads/thread detail/between/envelope/search
  - attachments
  - events/types/tracks/detail/related
  - locations tiles/in-tile
  - intersections
  - files/files-tree
  - overview contacts/calls/messages/locations/emails/detail
- Add phone selection state, selection rail, status bar, and search behavior using v2 patterns.
- Add unified contacts surfaces and "Filter Comms" actions from overview rows.
- Add direction-agnostic participants filtering.
- Add thread rail/flyout behavior with `anchor_key` scroll-to-message support.
- Add resizable panes and compact Comms toolbar behavior in v2 style.
- Add locations trajectory toggle/fly-to behavior.
- Preserve lazy loading and pagination/envelope API usage. Do not fetch the entire report at once.

#### Triage

- Add top-level protected route: `/triage`
- Add global/app navigation item.
- Build `frontend_v2/src/features/triage`.
- Reimplement:
  - triage case list
  - directory browser
  - scan progress
  - classification progress
  - custom stage view
  - template manager
  - advisor
  - dashboard/workbench
  - ingest-to-case flow

#### Case Profiles

- Build `frontend_v2/src/features/case-profiles` or integrate into Workspace.
- Preferred UI name: "Case Profiles".
- Add list/detail/editor.
- Add graph-node linking.
- Add evidence linking.
- Add note/profile linking.
- Add archive/delete.
- Add aliases, tags, contact/device/address fields.

#### Financial Gaps

Keep existing v2 financial page. Add missing Neil capabilities:

- Auto-extract from/to preview/apply.
- Notes CSV upload.
- Export section picker.
- Money flow perspective if still required.
- Richer PDF sections.

Do not blindly add Neil's `dataVersion` toggle. Reconcile it with v2's `transactions` and `intelligence` modes.

### Frontend Caveats

- Legacy wrappers call `/cellebrite/...`; v2 `fetchAPI` expects `/api/...`.
- Cellebrite needs careful layout; its rails/status bar can fight the generic case side panel.
- The latest `origin/main` has shifted Cellebrite from a static right rail to slide-in/flyout rail behavior. Preserve the workflow, but implement it in v2 layout primitives.
- V2 "Profiles" already means processing profiles. Use "Case Profiles".
- Financial sign semantics need verification before changing labels. Neil's comments imply negative means outgoing/payment and positive means incoming/receipt, while v2 may label differently.
- Triage path browsing must not expose unsafe server filesystem paths.
- V2 currently has no wrappers for Cellebrite, triage, case profiles, evidence tags/entity-links, or note-profile links.

## Workstream 7: Financial Integration

### Keep From Evidence Branch

- `mode=transactions|intelligence`.
- Current v2 frontend financial store/hooks/components.
- Evidence-backed financial model and legacy fallback.
- `render_financial_export()` public service shape.

### Port From Main

- `/api/financial/auto-extract-from-to`
- `/api/financial/upload-notes`
- Rich PDF export sections:
  - summary
  - money flow
  - charts
  - entity flow
  - transactions
  - filters
  - entity notes
- Export filters:
  - `types`
  - `money_flow_entities`
  - `sections`
- `from_to_extraction_service.py`
- `bulk_append_notes_by_ref_id` functionality, adapted into split `financial_service`.

### Caveats

- Main's `data_version` / `audit-v2` filtering should not override v2 dataset mode.
- Main's `financial_export_service.py` has richer rendering but different entrypoint naming; fold it into evidence branch service shape.
- Verify amount sign semantics before changing summary labels.

## Workstream 8: Chat And RAG Integration

### Keep From Evidence Branch

- Postgres conversations/messages.
- Case revisions.
- SQLAlchemy `User` auth.
- Per-request LLM context.
- AI cost tracking.

### Port From Main

- View context:
  - `ViewContext`
  - `view_context_used`
  - `view_context_summary`
  - `_build_view_context_block()`
- Case-scoped result node extraction:
  - `extract_nodes_from_answer(..., case_id=...)`

### Caveats

- Main's chat path uses dict auth and global LLM config mutation; do not port that pattern.
- Integrate view context into the evidence branch's existing persisted message and cost flow.

## Workstream 9: Workspace Integration

### Keep From Evidence Branch

- Postgres-backed `WorkspaceService`.
- Workspace JSONB model fields in Postgres.
- Existing v2 Workspace UI.
- Unified workspace build-graph endpoint.

### Port From Main

- `WitnessInterview.interviewed_by`.
- Note profile link/unlink routes.
- Arbitrary text graph support, if not already covered by unified build-graph.
- Any workflow additions not already reimplemented in v2 findings/theories/notes.

### Caveats

- Do not replace current `backend/services/workspace_service.py` with main's JSON file service.
- Implement new fields in Postgres JSONB or explicit columns as appropriate.

## Workstream 10: Cases And Archive State

### Port From Main

- `cases.archived`
- `include_archived`
- `/archive`
- `/unarchive`
- `archived` field in case responses.

### Alembic Resolution

Current `evidence-engine-migration` head:

- `20260429_merge_robust`

Current `main` head:

- `20260319_add_case_archived`

Naive merge creates Alembic head divergence.

Recommended:

1. Keep evidence branch migrations unchanged.
2. Bring in `main` migration `20260319_add_case_archived.py` unchanged if preserving released revision id matters.
3. Add a no-op Alembic merge revision with:

```python
down_revision = ("20260429_merge_robust", "20260319_add_case_archived")
```

4. Verify `alembic heads` reports one head.
5. Add `archived` field to `backend/postgres/models/case.py`.
6. Update cases router and v2 frontend case list filters.

Alternative:

- Create a new migration on top of `20260429_merge_robust` adding `cases.archived`.
- Do this only if there are no deployed DBs that already applied Neil's `20260319_add_case_archived`.

## Workstream 11: Docker, Env, Deploy

### Keep From Evidence Branch

The v2 Docker stack wins.

Current v2 stack:

- Backend API: `8002`
- Frontend: `5174`
- Neo4j container: `owl-v2-n4j`
- Neo4j host ports: `7475`, `7688`
- Postgres container: `owl-v2-pg`
- Postgres host port: `5434`
- ChromaDB: `8101`
- Redis: `6380`
- Evidence Engine API: `8003`
- Evidence Engine worker.

### Deploy Conflict

Only actual infra conflict observed was `deploy/deploy.sh`.

Resolve by:

- Taking v2 deploy script as base.
- Preserving Neil's longer health check intent:
  - `HEALTH_RETRIES=30`
  - `HEALTH_DELAY=5`
  or equivalent.

### Deploy Order

Preferred order:

1. Start infra containers.
2. Run backend Alembic.
3. Build/start Evidence Engine API and worker.
4. Restart backend.
5. Build/start frontend.

### Caveats

- Backend Alembic should be the single schema owner for shared DB tables.
- Do not run `evidence-engine/alembic` against the same shared DB if it overlaps backend-owned `jobs` tables.
- Evidence Engine Python environment should remain isolated. Its dependency ranges conflict with backend pins.
- Root `requirements.txt` was deleted on evidence branch; keep it deleted unless tooling references it.
- `.env.example` should keep v2 defaults and add Neil's new required env vars.

### Dependencies

Keep:

- `redis==7.4.0`

Likely needed if preserving Neil's features:

- `ijson==3.5.0`
- `reverse-geocoder>=1.5.1`

Add only after confirming the ported Cellebrite/geocoder paths import them.

## Workstream 12: Backfill, Legacy Routes, And Cleanup

### Legacy Routes To Review

- `backend/routers/cases_legacy.py`
- `backend/routers/backfill.py`
- old evidence processing paths in `backend/services/evidence_service.py`
- snapshot routes
- backup/restore service

### Decisions Needed

For each legacy route/service:

- Port to Postgres.
- Keep as migration-only/admin-only.
- Remove or disable.

No active route should depend on JSON runtime storage.

### Migration Scripts

Existing scripts can remain if they are one-time migrations:

- `backend/scripts/migrate_evidence_to_postgres.py`
- `backend/scripts/migrate_workspace_to_postgres.py`

They may read old JSON files as migration input, but runtime code should not.

## Suggested Implementation Slices

### Slice 0: Branch And Guardrails

- Create backups.
- Create integration branch.
- Add this plan.
- Add a temporary integration checklist issue/doc if needed.
- Establish "no runtime JSON storage" search check.

### Slice 1: Postgres Runtime State Foundation

- Add/finish Postgres replacements for active JSON runtime services.
- Remove active imports from JSON storage services.
- Decide which legacy routes are removed, disabled, or ported.
- Add tests for background tasks, snapshots if kept, evidence logs, tags, and links.

Exit criteria:

- `rg "evidence_storage|background_task_storage|case_storage|snapshot_storage|triage_storage|chat_history_storage" backend/routers backend/services` has only migration-only or explicitly deprecated references.

### Slice 2: Cases/Alembic/Docker Reconciliation

- Add archived case schema and API.
- Resolve Alembic heads.
- Resolve `deploy/deploy.sh`.
- Update `.env.example`.
- Verify migrations.

Exit criteria:

- One backend Alembic head.
- Backend imports successfully.
- Docker stack still starts.

### Slice 3: Cellebrite Backend

- Add Postgres Cellebrite evidence fields/tables.
- Port ingestion scripts.
- Add `neo4j/cellebrite_service.py`.
- Port `cellebrite_service.py`.
- Port `cellebrite_intersection_service.py`.
- Port `geocoder.py`.
- Port and mount `routers/cellebrite.py`.
- Port evidence check/process endpoints.
- Add tests for duplicate detect, report delete, attachment lookup, file registration, and a synthetic report.

Exit criteria:

- Backend imports with Cellebrite router mounted.
- Sample Cellebrite check/process reaches background task creation.
- Attachment resolution reads Postgres.
- Deleting a report cleans graph and Postgres evidence links.

### Slice 4: Cellebrite Frontend V2

- Add `features/cellebrite`.
- Add route and nav.
- Build reports, overview, timeline, comms, events, locations, files, and intersections incrementally.
- Add evidence folder detection/process UI and duplicate 409 replace flow.

Exit criteria:

- V2 route loads.
- Reports list works.
- Main drilldowns use lazy APIs.
- Ingestion flow visible from evidence UI.

### Slice 5: Triage Backend And Frontend V2

- Add Postgres triage tables.
- Port triage services.
- Port router.
- Reimplement v2 triage UI.

Exit criteria:

- `/triage` route works.
- Scan/classify/profile pipeline persists in Postgres.
- Ingest-to-case creates Postgres evidence and, where appropriate, evidence-engine jobs.

### Slice 6: Case Profiles

- Add Postgres case profile/link schema.
- Port service/router.
- Reimplement v2 UI.
- Add evidence/profile and note/profile linking.

Exit criteria:

- Case profiles CRUD works.
- Evidence/profile links work both ways.
- Workspace note/profile links work.

### Slice 7: Financial, Chat, Workspace Smaller Ports

- Port financial auto-extract.
- Port notes upload.
- Port PDF section picker and richer export rendering.
- Port chat view context.
- Port workspace note/profile and witness additions.
- Port graph `/nodes-by-type` if wanted.

Exit criteria:

- Existing v2 financial page still works.
- New financial tools work.
- Chat persists and includes view context.
- Workspace v2 flows still work.

### Slice 8: Full Verification And Main Update

- Run backend tests.
- Run frontend v2 tests/build.
- Run Alembic upgrade on clean DB.
- Start Docker stack.
- Smoke test core routes.
- Smoke test Cellebrite ingest.
- Smoke test triage.
- Smoke test financial export.
- Smoke test case archive/unarchive.
- Record `main` history with an `ours` merge if using non-force strategy.
- Update `main`.

## Verification Checklist

### Static Checks

- No unresolved merge markers:

```powershell
rg "<<<<<<<|=======|>>>>>>>" .
```

- No active runtime JSON storage imports:

```powershell
rg "evidence_storage|evidence_log_storage|background_task_storage|case_storage|snapshot_storage|triage_storage|chat_history_storage|last_graph_storage|wiretap_tracking|presence_service" backend/routers backend/services
```

- Alembic one-head check:

```powershell
cd backend
alembic heads
```

### Backend Checks

- Backend imports.
- FastAPI starts.
- `/health` returns Neo4j and evidence engine status.
- Auth still works.
- Cases list/detail works.
- Case archive/unarchive works.
- Evidence upload/list/folder processing works.
- Evidence engine job sync works.
- Chat creates and resumes conversations.
- Workspace pages load data from Postgres.
- Financial summary/transactions/export work.
- Cellebrite check/process/report APIs work.
- Triage APIs work.

### Frontend Checks

- `frontend_v2` typecheck/build.
- Case navigation works.
- Evidence page works.
- Graph page works.
- Chat page works.
- Workspace page works.
- Financial page works.
- New Cellebrite route works.
- New Triage route works.
- New Case Profiles UI works.

### Docker Checks

- `docker compose up` starts:
  - Neo4j
  - Postgres
  - ChromaDB
  - Redis
  - Evidence Engine API
  - Evidence Engine worker
- Backend connects to Postgres, Neo4j, Redis, Evidence Engine.
- Frontend proxy points to backend port `8002`.

## Known Risks

### Biggest Risks

- Accidentally reintroducing JSON storage through Neil's ported services.
- Mounting Neil's routers before their dependencies are Postgres-safe.
- Copying monolithic `neo4j_service.py` and losing the split service architecture.
- Treating Cellebrite as generic evidence-engine ingestion and losing structured phone graph data.
- Registering a whole UFED export as thousands of normal evidence files.
- Breaking v2 frontend architecture by copying legacy JSX directly.
- Ending with multiple Alembic heads.
- Force-pushing `main` without branch freeze/backups.

### Backend Risks

- Evidence branch still contains JSON-backed legacy services.
- `backend/routers/evidence.py` has mixed old and new paths.
- Main's Cellebrite router expects facade methods that do not exist yet.
- Case profiles depend on JSON evidence link helpers.
- Triage storage is JSON-backed.
- Main's chat uses a different auth and LLM context model.
- Financial export APIs differ by branch.
- Evidence IDs changed from `ev_*` strings to UUIDs.

### Frontend Risks

- Cellebrite layout may conflict with `CaseLayout` right side panel.
- Legacy UI API paths do not match v2 API client paths.
- Legacy UI state providers should be redesigned in v2 style.
- Financial mode/data-version semantics conflict.
- "Profiles" naming collision with admin processing profiles.

### Infra Risks

- Evidence Engine dependencies conflict with backend dependencies if installed into one shared environment.
- Backend and Evidence Engine Alembic ownership may overlap if run incorrectly.
- Deploy script/docs may disagree about target branch.
- Old app and v2 app use different ports/container names.

## Open Questions To Resolve During Implementation

- Which JSON-backed legacy routes can be deleted instead of ported?
- Should snapshots remain a product feature? If yes, what should the Postgres schema be?
- Should case profiles be Postgres-first with Neo4j projection, or Neo4j-first with Postgres link tables?
- Should Cellebrite evidence metadata be explicit columns, separate table, or JSONB plus indexes? Recommendation: explicit columns for filtered fields.
- Should system logs move to Postgres, or are file logs acceptable under "no JSON storage"? Current user instruction suggests Postgres.
- Is `data_version` still a business concept, or should all financial filtering be through v2 `mode`?
- What is the final branch protection process for updating `main`?

## Final Success Criteria

The integration is done when:

- All Neil features selected for preservation work in the v2 app.
- The app has one active frontend: `frontend_v2`.
- Runtime state is Postgres-backed.
- Neo4j service remains split by domain.
- Evidence Engine remains the generic evidence processing path.
- Cellebrite structured ingestion works and is visible in v2.
- Triage works and persists to Postgres.
- Case profiles work and link to evidence/notes/graph data.
- Financial additions are present without regressing v2 mode behavior.
- Alembic has one head.
- Docker stack starts cleanly.
- Tests/builds/smoke checks pass.
- `main` has a clear backup and update path.
