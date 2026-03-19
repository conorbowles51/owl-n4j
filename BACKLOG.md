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

### FEAT-003 · [HIGH] Feature: Workspace Findings section with linked evidence
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Workspace needs a dedicated Findings section (separate from Notes) where users can create findings and link evidence files, entity profiles, and documents to each finding. Findings should appear first in exported reports. Should support easy "add finding + link evidence" workflow.

### FEAT-004 · [HIGH] Feature: Bulk entity merge from Table view
- **Source:** Platform Feedback PDF (18 Mar)
- **Description:** Allow selecting multiple duplicate entities in the Table view and merging them in one operation. Currently limited to 2-at-a-time merge which took a user 45 minutes to merge 8 duplicates. Should combine all summaries/facts/insights and let user set the final name and type.

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

---

## Done

### ✅ FEAT-010 · [MEDIUM] Feature: Witness matrix — compact view and interviewer field
- **Completed:** 2026-03-19
- **Description:** Compact default view showing name, status, credibility, interview count. Full details (statement, risk, strategy) on expand. Added interviewed_by field to WitnessInterview model and modal. Renamed section to "Interviews & Statements".
- **Commits:** a301288

### ✅ BUG-012 · [MEDIUM] Fix: Exported snapshot report blurry graph
- **Completed:** 2026-03-19
- **Description:** Increased html2canvas scale from 2 to 3 for sharper graph capture in exports. Event scoping deferred to snapshot-specific export feature.
- **Commits:** a301288

### ✅ BUG-013 · [LOW] Fix: AI result graph faded nodes confusing
- **Completed:** 2026-03-19
- **Description:** Removed opacity-based fading on result graph nodes and links. Relevance now shown via border thickness — thick blue border for mentioned entities, thin border for high-confidence context nodes. All nodes fully visible.
- **Commits:** a301288

### ✅ BUG-011 · [MEDIUM] Fix: Upload fails during concurrent ingestion
- **Completed:** 2026-03-19
- **Description:** Added cleanup of _active_processing_cases in outer exception handler (was missing, causing permanent state corruption). Task deletion endpoint now also clears active processing state. Processing state no longer gets permanently stuck.
- **Commits:** be2dd4c

### ✅ BUG-015 · [MEDIUM] Fix: Graph legend entity type selection queries full graph
- **Completed:** 2026-03-19
- **Description:** Added /graph/nodes-by-type backend endpoint that returns all nodes of a type from Neo4j. Legend click handler now fetches all nodes from backend when graph is capped, not just visible subset.
- **Commits:** be2dd4c

### ✅ FEAT-014 · [MEDIUM] Feature: AI facts/insights consolidation
- **Completed:** 2026-03-19
- **Description:** AI insights now grouped by confidence level (High/Medium/Low) with collapsible groups showing counts. Insights section collapsed by default. Reduces visual noise from 30+ individual cards to 3 group headers.
- **Commits:** be2dd4c

### ✅ FEAT-001 · [HIGH] Feature: File summaries in Workspace view
- **Completed:** 2026-03-19
- **Description:** Added inline file summaries below filenames in Workspace CaseFilesSection, full width, matching CaseManagementView pattern. Summary data already returned by evidenceAPI.list().
- **Commits:** 3861f4d

### ✅ FEAT-002 · [HIGH] Feature: More comprehensive document summaries
- **Completed:** 2026-03-19
- **Description:** Rewrote summary LLM prompt to request structured output: overview, key entities, financial details, important dates, relationships. Increased input from 5000 to 15000 characters. Output now 4-8 sentences.
- **Commits:** 3861f4d

### ✅ FEAT-005 · [HIGH] Feature: Financial search bar separate from filter panel
- **Completed:** 2026-03-19
- **Description:** Moved search bar, date range, and entity filter outside the collapsible filter panel so they're always visible. Filter chips (type/category) remain inside the collapsible section.
- **Commits:** 3861f4d

### ✅ FEAT-006 · [MEDIUM] Feature: Transaction ID column for printout reference
- **Completed:** 2026-03-19
- **Description:** Added sequential # column to financial table after checkbox. IDs are page-aware (page 2 at 100/page starts at 101). Updated all colSpan values.
- **Commits:** 3861f4d

### ✅ BUG-010 · [MEDIUM] Fix: Audit log shows actions from all cases
- **Completed:** 2026-03-19
- **Description:** Added case_id query parameter to system logs endpoint and filtering logic in system_log_service. Audit log now only shows actions for the currently selected case.
- **Commits:** 3861f4d

### ✅ BUG-014 · [LOW] Fix: "Attach to theory" dialog appears behind map
- **Completed:** 2026-03-19
- **Description:** Raised z-index from z-50 to z-[9999] on AttachToTheoryModal so it renders above the Leaflet map layer. Also removed backdrop onClick.
- **Commits:** 3861f4d

### ✅ BUG-016 · [LOW] Fix: Ability to edit existing notes
- **Completed:** 2026-03-19
- **Description:** Added Edit button (pencil icon) to each note card in InvestigativeNotesSection. Opens AddInvestigativeNoteModal pre-filled with existing content. Updated modal to accept editNote prop, changed onSave to pass noteId for updates via workspaceAPI.updateNote.
- **Commits:** 3861f4d

### ✅ BUG-006 · [HIGH] Fix: Popup/modal dismissal loses unsaved work
- **Completed:** 2026-03-19
- **Description:** Removed `onClick={onClose}` backdrop handlers from 5 form modals (AddInvestigativeNoteModal, AddNoteModal, WitnessModal, LinkEntityModal, ChatPanel save-note modal). Users must now explicitly click X or Cancel to close — no more accidental data loss from misclicks.

### ✅ BUG-007 · [HIGH] Fix: Notes disappearing from workspace
- **Completed:** 2026-03-19
- **Description:** ChatPanel was not dispatching `notes-refresh` event after saving a note from AI chat. Added `window.dispatchEvent(new Event('notes-refresh'))` after successful save so InvestigativeNotesSection auto-refreshes.

### ✅ BUG-008 · [HIGH] Fix: Failure to save notes
- **Completed:** 2026-03-19
- **Description:** ChatPanel sent `{ title, content, tags }` but NoteCreate Pydantic model only accepted `content` and `tags`, causing a 422 validation error. Added `title: Optional[str] = None` to the NoteCreate model.

### ✅ BUG-009 · [HIGH] Fix: Snapshots not showing and crash on save
- **Completed:** 2026-03-19
- **Description:** Fixed snapshot save retry to properly close progress dialog on failure (was freezing for 10+ minutes on double timeout). Added `snapshots-refresh` event listener to SnapshotsSection so it auto-updates after save. Dispatched event from App.jsx after successful snapshot save.

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
