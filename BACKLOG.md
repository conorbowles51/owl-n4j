# Owl Backlog

> Project management document for bugs, features, and chores.
>
> **Format:** `[PRIORITY] Type: Short description`
> - Priority: `[CRITICAL]`, `[HIGH]`, `[MEDIUM]`, `[LOW]`
> - Type: `Fix:`, `Feature:`, `Chore:`
> - Status: Pending, In Progress, Done
> - Each task includes scope, files, issue description, and acceptance criteria

---

## In Progress
<!-- Move tasks here when actively working on them -->

## Pending

### BUG-001 · [HIGH] Fix: Evidence processing crashes mid-ingestion during parallel file processing
- **Reported:** 2026-03-09 (Alexandra)
- **Scope:** Backend — complex (thread-safety + path validation)
- **Files:**
  - `backend/services/evidence_service.py` (ThreadPoolExecutor, `process_single_file`)
  - `backend/services/evidence_storage.py` (stored_path retrieval)
  - `backend/routers/evidence.py` (upload endpoint)
- **Issue:** Platform gets stuck mid-ingestion when processing files in parallel. Background Tasks panel shows red `FileNotFoundError` and path-related tracebacks. Observed when working on deduplication in another tab for the same case simultaneously. Screenshots show multiple workers crashing with "No such file or directory" errors.
- **Likely Root Cause:** Race condition in `ThreadPoolExecutor` — multiple threads access `stored_path` from evidence records before files are fully written. The lock at line ~750 only protects counter updates, not file access. Concurrent operations (e.g., dedup in another tab) on the same case may also invalidate file references mid-processing.
- **Acceptance:**
  - [ ] Evidence processing completes without path errors when processing files in parallel
  - [ ] Concurrent case operations (dedup, merge) don't cause processing crashes
  - [ ] Failed files are properly reported with clear error messages, not silent crashes
  - [ ] Processing can be retried for failed files

---

### BUG-002 · [HIGH] Fix: Merged entities still appear as duplicates in workspace Entity Summary
- **Reported:** 2026-03-09 (Alexandra)
- **Scope:** Frontend + Backend — moderate
- **Files:**
  - `backend/services/neo4j_service.py` (`merge_entities` method)
  - `frontend/src/components/workspace/EntitySummarySection.jsx` (entity list loading)
  - `backend/routers/graph.py` (entity summary endpoint)
- **Issue:** After merging duplicate entities (e.g., multiple "Eric Tate" / "Eric TATAR" variants), the workspace Entity Summary still shows all the old duplicates. Screenshot shows ~15 "Eric Tate/TATAR" entries that should have been consolidated into one.
- **Likely Root Cause:** Two possible issues: (1) Frontend `EntitySummarySection` loads entities on mount and doesn't refetch after a merge operation completes. (2) Neo4j `merge_entities` may not fully delete source entity nodes or redirect all relationships, leaving orphaned nodes visible in queries.
- **Acceptance:**
  - [ ] After merging entities, the Entity Summary refreshes and shows only the merged target entity
  - [ ] Source entities are fully removed from Neo4j (no orphaned nodes)
  - [ ] All relationships from source entities are properly redirected to the target
  - [ ] Entity count in workspace header updates after merge

---

### BUG-003 · [MEDIUM] Fix: Case export report shows blank graph
- **Reported:** 2026-03-09 (Alexandra)
- **Scope:** Frontend — moderate
- **Files:**
  - `frontend/src/components/workspace/CaseExportModal.jsx` (graph data fetching, line ~166)
  - `backend/routers/graph.py` (graph API endpoint)
  - `frontend/src/utils/graphDataConverter.js` (export utilities)
- **Issue:** When exporting a case report with all sections checked, the graph appears blank. Graph timeline and graph map are also exported but may be empty. User noted they had tested AI graph with investigative theories prior, which may have affected state.
- **Likely Root Cause:** The export modal fetches graph data via `graphAPI.getGraph({ case_id: caseId })` with a fallback to `{ nodes: [], links: [] }` on failure. The API call may be failing silently (auth, scoping, or timeout), or the graph data isn't being passed correctly to the HTML export renderer.
- **Acceptance:**
  - [ ] Exported report renders the full case graph with all nodes and links
  - [ ] Graph timeline and map render correctly in export
  - [ ] Export works regardless of previous AI assistant/theory interactions
  - [ ] Error is surfaced to user if graph data cannot be fetched

---

### BUG-004 · [MEDIUM] Fix: File uploads stuck in "Unprocessed" state with errors
- **Reported:** 2026-03-09 (Alexandra)
- **Scope:** Backend + Frontend — simple to moderate
- **Files:**
  - `backend/routers/evidence.py` (`upload_evidence` endpoint, lines ~281-386)
  - `backend/services/evidence_service.py` (`add_uploaded_files`, lines ~65-122)
  - `frontend/src/components/EvidenceProcessingView.jsx` (upload UI)
- **Issue:** Uploaded files remain stuck in "Unprocessed Files" list. Screenshot shows files uploaded but never transitioning to processing or completed state. No clear error message shown to user.
- **Likely Root Cause:** Background upload tasks fail silently without updating progress or status. Evidence records may not be created if path validation fails during storage. Frontend doesn't auto-refresh after upload completion, showing stale state.
- **Acceptance:**
  - [ ] Uploaded files transition from "Unprocessed" to processing/completed states
  - [ ] Upload errors are clearly displayed to the user with actionable messages
  - [ ] Frontend auto-refreshes file status after upload completes
  - [ ] Retry mechanism available for failed uploads

---

### BUG-005 · [LOW] Fix: Deadline emoji rendering broken in CaseDeadlinesSection
- **Reported:** 2026-02 (development team)
- **Scope:** Frontend — simple
- **Files:**
  - `frontend/src/components/workspace/CaseDeadlinesSection.jsx`
- **Issue:** Emoji characters render incorrectly on certain browsers.
- **Acceptance:**
  - [ ] Deadlines display with proper icons
  - [ ] Test on Chrome, Firefox, and Safari

---

## Done

### ✅ RAG-001 · [HIGH] Feature: Document-scoped RAG retrieval
- **Completed:** 2026-03-08
- **Description:** When a user selects a Document node and asks the AI assistant a question, the pipeline now prioritizes that document's chunks and entities while still allowing cross-document discovery. Implemented two-phase chunk retrieval, LLM prompt enhancement with selected document focus, doc-affinity scoring in result graph, and negation-aware mention scoring.
- **Commits:** 8ce3b25, 687255c, d5f122f, fae6466

### ✅ RAG-002 · [MEDIUM] Feature: Relevance reasoning for result graph nodes
- **Completed:** 2026-03-09
- **Description:** Added human-readable explanations for why entities appear in the result graph. Hover tooltip on graph nodes, "Why This Entity?" section in NodeDetails panel. Captures graph-traversal parent info for "Connected to X via Y" explanations. Removed noisy answer-similarity entity search.
- **Commits:** b1d1550, 7c9a96a

### ✅ RAG-003 · [MEDIUM] Feature: Document sources moved to collapsible dropdown
- **Completed:** 2026-03-09
- **Description:** Moved the document relevance list from being prepended to the AI answer to a separate collapsible "Sources" dropdown button alongside Pipeline Trace. Returned as a separate `document_summary` field from the backend instead of being embedded in the answer text.
- **Commits:** b1d1550, ee3d731

### ✅ DEPLOY-001 · [HIGH] Fix: Deploy rollback leaves dirty git working tree
- **Completed:** 2026-03-09
- **Description:** Fixed deploy rollback to use `git reset --hard` instead of `git checkout -- .` which was leaving the working tree in a dirty state, causing subsequent `git pull` to say "Already up to date" even though HEAD pointed to a newer commit. Also added initial 10s delay and curl timeout to health check for backend startup.
- **Commits:** b1d1550, acd94f4

### ✅ UI-001 · [LOW] Feature: Build name visible throughout app
- **Completed:** 2026-03-08
- **Description:** Added deterministic funny build names (e.g., "Grumpy Unicorn") generated from git commit hash, visible as a subtle footer across all views (login, case management, workspace, graph, evidence).
- **Commits:** c13fd2c, bd0367f
