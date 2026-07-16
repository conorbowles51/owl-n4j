# DKT-504 Export Endpoint Inventory

Version: 2026-07-16

Decision: server-side download, print, file, and export endpoints that expose case data must derive their case scope from trusted server-side state and require `case.view` before generating or serving bytes. A caller-supplied case name or case ID is not sufficient for authorization when the artifact record already has a case owner.

## In Scope

| Endpoint | File | Decision |
| --- | --- | --- |
| `GET /api/evidence/{evidence_id}/file` | `backend/routers/evidence.py` | Load the `EvidenceFile`, authorize `case.view` against `EvidenceFile.case_id`, then resolve and serve `stored_path`. |
| `GET /api/evidence/{evidence_id}/frames` | `backend/routers/evidence.py` | Load the `EvidenceFile`, authorize `case.view`, then resolve the video path or generate cached frames under a canonical `record.id` cache directory. |
| `GET /api/evidence/{evidence_id}/frames/{filename}` | `backend/routers/evidence.py` | Validate `frame_NNNN.jpg`, load the `EvidenceFile`, authorize `case.view`, then serve the cached image from the canonical cache path with legacy fallback only after authorization. |
| `GET /api/financial/export/pdf` | `backend/routers/financial.py` | Parse `case_id` as UUID, require `case.view`, fetch/render transactions only after authorization, and use the database case title for report label and filename instead of trusting `case_name`. |
| `GET /api/filesystem/list` | `backend/routers/filesystem.py` | Parse `case_id` as UUID, require `case.view`, then resolve and list only the trusted case root. This closes the legacy case-file browser route that previously only required authentication. |
| `GET /api/filesystem/read` | `backend/routers/filesystem.py` | Parse `case_id` as UUID, require `case.view`, then resolve and read the requested text file under the trusted case root. This closes the legacy case-file preview route that previously only required authentication. |
| `GET /api/evidence/by-filename/{filename}` | `backend/routers/evidence.py` | Require caller-supplied `case_id`, require `case.view`, and scope `EvidenceDBStorage.find_by_filename` to the authorized case before returning file metadata or summaries. Cross-case filename search without case authorization is not allowed. |
| `GET /api/evidence/summary/{filename}` | `backend/routers/evidence.py` | Require `case.view` for the requested case before reading the Postgres evidence summary scoped to that case. |
| `GET /api/evidence/folder-summary/{folder_name}` | `backend/routers/evidence.py` | Require `case.view` for the requested case before reading folder summary metadata from Neo4j. |
| `GET /api/evidence/transcription-translation` | `backend/routers/evidence.py` | Require `case.view` for the requested case before reading transcription or translation summaries from Neo4j. |
| `POST /api/timeline/export` | `backend/routers/timeline.py` | Verified already protected: `export_case_timeline` calls `get_case_if_allowed(..., case_id=request.case_id, user=current_user)` before `export_timeline`, and `export_timeline` writes a case-operation audit log. No DKT-504 code change required. |
| `GET /api/agent/artifacts/{artifact_id}/export` | `backend/routers/agent.py` | Verified already protected: `agent_service.export_artifact` loads the artifact through `storage.get_artifact_for_user`, which resolves the owning thread and calls `check_case_access(..., required_permission=("case", "view"))`; the service logs `agent_artifact_exported`. No DKT-504 code change required. |
| `GET /cases/{case_id}/files` | `evidence-engine/app/api/routes/files.py` | Require a backend JWT and `case.view` before listing evidence-engine jobs for the case. This route exposes case file metadata, so it is treated as in-scope for DKT-504 despite not serving bytes. |
| `GET /cases/{case_id}/files/{job_id}` | `evidence-engine/app/api/routes/files.py` | Require a backend JWT, load the engine `Job`, require `case.view` against `Job.case_id` in shared Postgres, then check disk and serve bytes. This closes the active engine file-serving route that bypassed the main backend. |

## Exclusions

| Surface | Rationale | Follow-up |
| --- | --- | --- |
| `cases_legacy.py` backup ZIP | Legacy module is not mounted by `backend/main.py`; no active server route in the mounted FastAPI app. | Excluded for DKT-504. Reassess if the router is mounted again. |
| Testing hub `FileResponse` | Serves a non-case static shell, not case data or export content. | Excluded for DKT-504. |
| Graph `StreamingResponse` | Server-sent event stream, not a file/download/print/export endpoint. | Excluded for DKT-504. |
| Browser-generated v2 table/map CSV exports | Generated client-side from data already returned by case-scoped APIs; no server file/export endpoint to protect in this task. | Product/security approval required before release, or open a release-blocking follow-up if the CSV promise must be treated as an export surface. |
| Evidence-engine upload/delete file management routes | These do not generate, fetch, or enumerate export/file content for a case in the same way as the list/download routes above. They remain backend-mediated operational endpoints and are explicitly outside this DKT-504 corrective pass. | Product/security approval required before release if these must be treated as export surfaces; otherwise track broader service-to-service hardening outside DKT-504. |
| Other artifact/report export concerns from text search | No additional mounted server file/export route requiring a DKT-504 permission change was found beyond the rows above. | IDOR, cached artifact boundaries, and full regression coverage remain owned by DKT-506 and DKT-508. |

## Implementation Evidence

DKT-504 implemented server-side `case.view` checks for the evidence file/frame, financial PDF, backend filesystem list/read, evidence metadata/summary, evidence folder/transcription metadata, and evidence-engine file list/byte endpoints that lacked them. Timeline and agent artifact exports were verified to already have server-side case authorization and audit logging. The backend evidence file-byte endpoints authorize from `EvidenceFile.case_id`, not caller input, and authorization now happens before disk path resolution, frame extraction, or cached frame lookup. Filename and summary lookups now require an authorized case scope before Postgres access, and folder/transcription summary endpoints require an authorized case before Neo4j access. The backend filesystem endpoints authorize the requested case before resolving, listing, or reading the case-root path. The evidence-engine download endpoint authorizes from `Job.case_id` before disk lookup or `FileResponse`; the evidence-engine list endpoint authorizes the requested case before job enumeration. The financial PDF endpoint authorizes before Neo4j reads and renders with the trusted `Case.title`.

Minimal audit breadcrumbs were added via `system_log_service.log` with actor email, case ID, export type, scope parameters, and result. Evidence content, file bytes, transaction contents, and report bodies are not logged.

## Owned Follow-ups

| Ticket | Ownership |
| --- | --- |
| DKT-505 | Full audit schema and persistence expectations, including actor, case, export type, scope, result, correlation ID, and no evidence content. DKT-504 only adds best-effort breadcrumbs. |
| DKT-506 | IDOR and guessed artifact/report IDs, cross-case cached files, and deeper cache/artifact hardening. DKT-504 closes direct cached-frame fetches by requiring evidence authorization before cache lookup. |
| DKT-507 | Safe filenames, content types, no-sniff/cache headers, and expiring download URLs. DKT-504 preserves existing content-type and filename behavior except for using trusted financial case title. |
| DKT-508 | Negative security tests across the broader export set plus dataset-to-export count/hash assertions. DKT-504 adds focused authorization-order regression tests for the touched endpoints. |
