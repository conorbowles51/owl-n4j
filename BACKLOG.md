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
<!-- No pending tasks -->

---

## Done

### ✅ UI-002 · [MEDIUM] Feature: File summaries expanded by default in Case Management
- **Completed:** 2026-03-15
- **Description:** Added inline file summaries below each filename in the Case Management evidence file list. Summaries (already batch-fetched from Neo4j by the existing `list_evidence()` endpoint) are displayed as 4-line truncated snippets using `line-clamp-4`. Layout restructured so the summary spans full row width beneath the filename/status header row, rather than competing for space with metadata. No backend changes needed — frontend-only change to `CaseManagementView.jsx`. Unprocessed files without summaries render as before. Click-to-preview still works.

### ✅ BUG-001 · [HIGH] Fix: Evidence processing crashes mid-ingestion during parallel file processing
- **Completed:** 2026-03-15
- **Description:** Fixed race condition in ThreadPoolExecutor — added file existence validation before ingestion, specific FileNotFoundError handling with descriptive error messages, per-case active processing tracking (`_active_processing_cases` dict with thread-safe guards), and delete protection (HTTP 409 Conflict) for files currently being processed.
- **Commits:** fd9c941

### ✅ BUG-002 · [HIGH] Fix: Merged entities still appear as duplicates in workspace Entity Summary
- **Completed:** 2026-03-15
- **Description:** Added `entities-refresh` window event dispatch after merge in App.jsx `handleMergeEntities`. Added event listener in EntitySummarySection to auto-refetch entities when the event fires. Neo4j merge logic was already correct (DETACH DELETE on source nodes).
- **Commits:** fd9c941

### ✅ BUG-003 · [MEDIUM] Fix: Case export report shows blank graph
- **Completed:** 2026-03-15
- **Description:** Added 2000ms extraWait for graph capture (was 0), blank-image detection with automatic retry, enhanced canvas fallback with additional wait, and pre-warming by switching to graph tab on modal open so ForceGraph2D starts rendering before export capture.
- **Commits:** fd9c941

### ✅ BUG-004 · [MEDIUM] Fix: File uploads stuck in "Unprocessed" state with errors
- **Completed:** 2026-03-15
- **Description:** "Unprocessed" is by design (user must click Process), but UX was unclear. Added helper text for first-time users, "Select All" convenience button in toolbar, and error surfacing for failed upload/processing background tasks during polling.
- **Commits:** fd9c941

### ✅ BUG-005 · [LOW] Fix: Deadline emoji rendering broken in CaseDeadlinesSection
- **Completed:** 2026-03-15
- **Description:** Not actually emojis — Lucide SVG icons had `inline-block align-text-bottom` which doesn't reliably align with text across browsers. Changed to `inline align-middle -mt-0.5` on all 4 icon instances.
- **Commits:** fd9c941

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
