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

### FEAT-001 · [HIGH] Feature: File summaries in Workspace view
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** File summaries are now shown in Case Management but the same treatment is needed in the Workspace view. Users should see inline AI summaries beneath each file in the Workspace evidence/files section without needing to click.

### FEAT-002 · [HIGH] Feature: More comprehensive document summaries
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Current AI-generated document summaries are too short and barebones. Summaries should be more detailed — covering key facts, entities mentioned, financial figures, dates, and relationships. May require changing the LLM prompt and/or increasing the input context window from the current 5000 characters.

### FEAT-003 · [HIGH] Feature: Workspace Findings section with linked evidence
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Workspace needs a dedicated Findings section (separate from Notes) where users can create findings and link evidence files, entity profiles, and documents to each finding. Findings should appear first in exported reports. Should support easy "add finding + link evidence" workflow.

### FEAT-004 · [HIGH] Feature: Bulk entity merge from Table view
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Allow selecting multiple duplicate entities in the Table view and merging them in one operation. Currently limited to 2-at-a-time merge which took a user 45 minutes to merge 8 duplicates. Should combine all summaries/facts/insights and let user set the final name and type.

### FEAT-005 · [HIGH] Feature: Financial search bar separate from filter panel
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** The search bar (name, entity, notes, date range) is inside the filter dropdown. On smaller screens, users must close filters to see transactions but then lose the ability to search. Search should be a persistent bar visible even when the filter panel is collapsed.

### FEAT-006 · [MEDIUM] Feature: Transaction ID column for printout reference
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Add a visible transaction ID (simple sequential number) to each transaction in the financial table. The ID should persist in exports/printouts so when meeting clients in person, they can reference specific transactions by number and the team can log notes back into the platform.

### FEAT-007 · [MEDIUM] Feature: Cost Ledger improvements — case ID, PDF export, simplified line items
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Cost Ledger needs: (1) case ID or name so costs can be billed back by case to courts, (2) PDF export capability, (3) simplified line items — consolidate multiple "Document Ingestion: None" entries for the same document into a single line to avoid pushback when billing.

### FEAT-008 · [MEDIUM] Feature: Snapshot reports — source citations and confidentiality labels
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Exported snapshot reports should cite their source documents (which files/evidence the events came from). Reports should also be labeled as "Confidential" or "Attorney Work Product — Privileged & Confidential".

### FEAT-009 · [MEDIUM] Feature: Report section ordering and brand guidelines
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Users should be able to organize the order of sections in exported reports. Brand guidelines: blue should be HEX #222248 spectrum, titles in Cinzel Black font, body text in Lato font.

### FEAT-010 · [MEDIUM] Feature: Witness matrix improvements — compact view and interviewer field
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** (1) Witness matrix is too verbose when statements are added — show only name, credibility rating, status, phone, address by default with expand for details. (2) Add "Interviewed by" field to capture who conducted the interview (police, deposition, trial, investigator). (3) Rename "Witness Interview" to "Interview or Statement" to cover wiretaps, recordings, depositions etc.

### FEAT-011 · [MEDIUM] Feature: Workspace section reorganization
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Reorganize workspace sections in this order: Case Deadlines & Tasks, Findings, Client Profile & Exposure, Investigative Theories, Notes, Snapshots, Witness Matrix, Entity Summary, Pinned Evidence, Case Files, Graph, Timeline (simplified), Map, Audit Log. Left pane should match this order. Rename "Investigation Timeline" to "Comprehensive Audit Log". Remove "Chain of Custody" label (legal term conflict). Remove audit log and investigation timeline from exported reports.

### FEAT-012 · [LOW] Feature: Archive completed cases
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Ability to archive cases that are done so they don't clutter the active case list. Archived cases should still be accessible but hidden from the default view.

### FEAT-013 · [LOW] Feature: Better text message processing
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Improve the ingestion pipeline's handling of text message exports. Current processing may not properly parse conversation threads, timestamps, or sender/recipient metadata from common text message export formats.

### FEAT-014 · [MEDIUM] Feature: AI facts and insights consolidation
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** AI-generated facts and insights are "getting out of control" — too many individual items cluttering the view. Need a better way to view them, possibly integrated into a more comprehensive per-entity or per-document summary rather than individual fact cards.

### BUG-006 · [HIGH] Fix: Popup/modal dismissal loses unsaved work
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Clicking outside a popup/modal window accidentally dismisses it and loses all work in progress. This is extremely frustrating for users writing long notes or filling out forms. Fix: require explicit Save or X to close modals. Add a confirmation prompt if there are unsaved changes, or auto-save drafts.

### BUG-007 · [HIGH] Fix: Notes disappearing from workspace
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** User creates investigative notes but they keep disappearing from the workspace. The audit log shows the notes were created but they don't appear in the Notes section. May be a display/fetch issue or a data persistence problem. Needs investigation.

### BUG-008 · [HIGH] Fix: Failure to save notes
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** User gets "Failed to save note" error when trying to save an investigative note. Screenshot shows the error occurs during the save operation. Related to BUG-007 — notes system needs reliability audit.

### BUG-009 · [HIGH] Fix: Snapshots not showing and crash on save
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Snapshots are not showing in the workspace view. Additionally, the platform crashes (freezes) when trying to save a snapshot. The save snapshot and save note from AI chat both cause timeouts. Needs investigation — likely a backend timeout or data serialization issue.

### BUG-010 · [MEDIUM] Fix: Audit log shows actions from all cases
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** The audit log in the workspace is showing actions from ALL cases instead of being scoped to the currently selected case. Needs case_id filtering on the audit log query.

### BUG-011 · [MEDIUM] Fix: Upload fails during concurrent ingestion
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Uploading files while ingestion is running on the same case causes a server error. The error persists even after cancelling ingestion — user cannot upload anything else until the server is restarted. Likely related to BUG-001 race condition but a different code path.

### BUG-012 · [MEDIUM] Fix: Exported snapshot report — blurry graph and irrelevant events
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** When exporting a snapshot report: (1) the graph image comes out blurry (resolution/DPI issue in html2canvas), (2) the export includes all events from the case rather than only the relevant ones for the snapshot. BUG-003 fixed blank graph but blurriness and event scoping are separate issues.

### BUG-013 · [LOW] Fix: AI result graph faded nodes confusing to users
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** When the AI chat returns a result graph, some nodes appear faded/dimmed. The purpose (showing relevance hierarchy) is unclear to users and causes confusion. Need better visual explanation or simplified presentation.

### BUG-014 · [LOW] Fix: "Attach to theory" dialog appears behind map
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** When attaching a document to an investigative theory, the dialog pops up behind the map layer. Z-index issue — dialog should appear on top of all other elements.

### BUG-015 · [MEDIUM] Fix: Graph legend entity type selection should query full graph
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** When graph is capped at 100 nodes, clicking an Entity Type in the legend should query ALL nodes of that type from the backend and add them to the spotlight graph, not just filter the visible 100. Currently misleading as it only operates on the loaded subset.

### BUG-016 · [LOW] Fix: Ability to edit existing notes
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Users cannot edit notes after creation. Need an edit mode for existing investigative notes.

---

## Done

### ✅ PERF-001 · [HIGH] Feature: Two-phase graph loading with node cap and info banner
- **Completed:** 2026-03-18
- **Description:** Graph view now loads a lightweight top-100 node preview for instant rendering, then fetches full data in the background. When the graph is capped, an info banner shows the total entity count and guides users to search or Spotlight Graph for entities not shown.
- **Commits:** e0fbb24, b0c4319

### ✅ PERF-002 · [HIGH] Feature: Financial table pagination
- **Completed:** 2026-03-18
- **Description:** Added pagination to the financial transaction table with page size selector (50/100/200/500 rows per page). Prevents browser freezing on cases with 13,000+ transactions. Stats and totals still computed from the full filtered dataset.
- **Commits:** e0fbb24

### ✅ UI-003 · [MEDIUM] Feature: Collapsible filter chips with show more/less
- **Completed:** 2026-03-18
- **Description:** Transaction Type and Category filter chip lists in the Financial view now collapse by default, showing a limited set with a "show more/less" toggle. Prevents rendering hundreds of chips simultaneously, improving load performance.
- **Commits:** e0fbb24

### ✅ UI-004 · [MEDIUM] Feature: Financial table layout improvements
- **Completed:** 2026-03-18
- **Description:** Widened the transaction table to 80% of the view width (charts reduced to 20%). Removed max-width constraint on AI summaries so they wrap to full width. Always-visible AI summaries in financial table rows. Fixed-width table columns to prevent layout shifts during interaction.
- **Commits:** e0fbb24, b0c4319

### ✅ CHORE-001 · [LOW] Chore: Chunk upload cache TTL cleanup
- **Completed:** 2026-03-18
- **Description:** Added background task to clean up stale chunk upload cache entries older than 30 minutes. Prevents memory buildup from abandoned or failed uploads.
- **Commits:** e0fbb24

### ✅ DEPLOY-002 · [LOW] Fix: Data directory ownership after git pull
- **Completed:** 2026-03-18
- **Description:** Deploy script now fixes ownership of the data directory after git pull runs as root, preventing "Permission denied" errors when the backend (running as conorbowles51) tries to write evidence logs.
- **Commits:** e0fbb24

### ✅ CHORE-002 · [LOW] Chore: Transaction categorization script
- **Completed:** 2026-03-18
- **Description:** Added `scripts/categorize_transactions.py` — a utility script for bulk categorization of financial transactions. Supports dry-run preview and `--apply` mode.
- **Commits:** e0fbb24

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
