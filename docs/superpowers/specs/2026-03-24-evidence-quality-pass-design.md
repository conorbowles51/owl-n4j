# Evidence Section Quality Pass — Design Spec

**Date:** 2026-03-24
**Scope:** Evidence section end-to-end — frontend_v2, backend, evidence-engine
**Approach:** Targeted quality pass (Approach B) — fix bugs, overhaul summaries, improve UX and progress transparency, polish

## Context

The evidence section allows investigators to upload files, organize them into folders with context profiles, process them through an NLP pipeline, and explore the resulting knowledge graph. The architecture is sound (backend owns files, engine processes, Redis/WebSocket for status), but several subsystems need targeted improvements to deliver a polished, professional experience.

**User priorities:**
- Extraction quality — specifically richer entity summaries that grow over time with source references
- User experience — bugs, misplaced UI elements, general polish
- Progress transparency — granular feedback during processing, not bulk completion jumps

**Explicitly out of scope:**
- Pipeline prompt tuning / dedup threshold adjustments (save for when real data exists to benchmark against)
- Reliability/recovery improvements (not a current pain point)
- Architectural changes to the backend-owns-files / engine-processes split

---

## Section 1: Bug Fixes

### 1.1 Cross-Case State Leak

**Problem:** The Zustand evidence store (`evidence.store.ts`) persists `currentFolderId`, `expandedFolderIds`, and other state across case switches. When navigating from Case A to Case B, stale folder IDs from Case A cause files to display under the wrong folder name in Case B's view.

**Root cause:** Store state is global and never reset when `caseId` changes.

**Fix:**
- Add a `resetForCase(caseId: string)` action to the evidence store
- Clears: `currentFolderId`, `expandedFolderIds`, `selectedFileIds`, `selectedFolderIds`, `detailFileId`, `detailOpen`, `searchTerm`, `statusFilter`, `typeFilter`
- Call from `EvidenceExplorer` via a `useEffect` that fires when `caseId` changes
- Verify all React Query cache keys include `caseId` to prevent stale data

### 1.2 Root Folder Context Menu

**Problem:** The "All Files" root item in `FolderTreeSidebar` has no right-click context menu, so users can't create a folder at root level from the tree.

**Fix:**
- Add a context menu to the "All Files" item with a "New Folder" action
- Triggers the create folder dialog with `parent_id: null`
- Keep minimal — root doesn't need "Set Profile" or "Process All" (those are folder-specific)

### 1.3 Entity Count Display

**Problem:** `FileRow.tsx` shows `"--"` for entity count regardless of processing status. The processed branch should show counts but `entity_count` / `relationship_count` aren't stored on the `evidence_files` table.

**Fix:**
- Add `entity_count` (Integer, nullable) and `relationship_count` (Integer, nullable) columns to `evidence_files` table via Alembic migration
- Update `JobStatusSubscriber._handle_message()` to populate these fields when a job completes (the engine already reports these counts)
- Update `FileRow.tsx` to display counts when `status === 'processed'`
- Update the `EvidenceFileRecord` TypeScript type (in `frontend_v2/src/types/evidence.types.ts`) to include `entity_count` and `relationship_count` fields — this is the type used by `FileRow` and `EvidenceDetailSheet`

---

## Section 2: Summary System Overhaul

### 2.1 Document Summaries — Improved but Static

Document summaries are generated once per file at processing time. No growth mechanism needed.

**Changes to `generate_document_summary.py`:**
- Increase context window from 8,000 to ~30,000 characters (text + tables combined)
- Generate structured markdown output with sections:
  - **Overview** — what this document is and why it matters
  - **Key Entities** — people, organizations, accounts mentioned with brief context
  - **Key Facts & Dates** — timeline-relevant details
  - **Notable Connections** — relationships or patterns observed
  - **Source References** — specific quotes or page references from the document
- Store as markdown in the existing `summary` TEXT column on `evidence_files`

### 2.2 Entity Summaries — Living Intelligence Briefs

Entity summaries are what investigators rely on to understand a person, organization, or account across all evidence. These should grow richer as more documents are processed.

**Changes to `generate_summaries.py` and prompts:**

**Structured format by category.** Each entity summary is markdown with category-appropriate sections:
- **Person:** Background, known associates, financial activity, timeline of involvement, source references
- **Organization:** Structure, key personnel, activities, linked transactions, source references
- **Transaction:** Parties, amounts, dates, context, linked accounts, source references
- **Other categories:** Appropriate section structures following the same pattern

**Source references.** Each claim in the summary links back to the source document:
- Format: `[see source](evidence://{file_id})` or `[invoice_march.pdf](evidence://{file_id})`
- The `source_files` data on each entity already tracks which files contributed — use this to generate links
- The LLM prompt instructs: "For each factual claim, include a source reference linking to the document it came from"
- **Implementation note:** The pipeline currently passes `source_files` as filename strings, not file IDs. The frontend must resolve filenames to file IDs at render time (via the existing `GET /api/evidence/by-filename/{filename}` endpoint or a batch lookup) to construct `evidence://{file_id}` links. Alternatively, the pipeline can be updated to pass a `{filename: file_id}` mapping into the summary generation step. Either approach works — the implementer should pick whichever is simpler.

**Cumulative growth.** The existing merge prompt (`entity_summary_merge.txt`) is improved:
- Explicitly preserve all prior source references — never drop facts from earlier evidence
- Integrate new evidence into the existing section structure rather than rewriting from scratch
- Maintain chronological ordering within sections where relevant
- Merge prompt receives the existing structured summary + new evidence and produces an updated structured summary

**No length cap.** An entity mentioned in 20 documents should have a substantial summary. One mentioned once gets a short one. The prompt instructs: "Be as thorough as the evidence warrants."

### 2.3 Frontend Markdown Rendering

- Add `react-markdown` (or equivalent) to render summaries in:
  - `FileSummaryPanel` / `EvidenceDetailSheet` (document summaries)
  - Entity detail views wherever entity summaries appear
- **Note:** `FileSummaryPanel` currently fetches summaries via a separate API call (`GET /api/evidence/summary/{filename}`). Since document summaries are now stored as markdown on the `evidence_files.summary` column, `FileSummaryPanel` can read directly from the file record instead — eliminating the redundant API call.
- Intercept `evidence://` protocol links:
  - Parse `file_id` from the URL
  - Open the document viewer (`DocumentViewer` component) for that file
  - If page/chunk anchors are present, navigate to that location
- Style rendered markdown consistently with the app's design system (headings, lists, blockquotes, code)

---

## Section 3: Jobs Panel Relocation & Progress Transparency

### 3.1 Move Jobs Panel to Sidebar

**Current state:** `JobsPanel` is a bottom resizable panel inside `EvidenceExplorer`.

**New state:** Jobs/progress becomes a tab in the existing right sidebar alongside file details and AI chat.

**Layout change:**

Current layout is a two-panel horizontal split: `[FolderTree | FileList]` with `EvidenceDetailSheet` rendered as a `<Sheet>` portal overlay and `JobsPanel` as a bottom resizable panel.

New layout is a three-panel horizontal split: `[FolderTree | FileList | ContextSidebar]`
- The `ContextSidebar` is a new `ResizablePanel` (25-35% width, collapsible) on the right side of the `ResizablePanelGroup`
- It replaces both the `<Sheet>` overlay and the bottom `JobsPanel`
- When collapsed, the file list expands to fill the space (same as today when the Sheet is closed)
- Minimum width ~320px to accommodate content; collapse below that threshold

**Implementation:**
- Remove the bottom `JobsPanel` from `EvidenceExplorer`'s `ResizablePanelGroup`
- Remove `jobsPanelOpen` toggle from the evidence store (no longer needed)
- Replace `EvidenceDetailSheet` (`<Sheet>` component) with inline content inside the new `ContextSidebar` panel
- New `ContextSidebar` component with tab state management:
  - **Details** — file detail view (adapted from `EvidenceDetailSheet` content, no longer a `<Sheet>`)
  - **Processing** — relocated `JobsPanel` content (active + completed jobs)
  - **AI Chat** — existing chat feature
- Auto-switch behavior:
  - Clicking a file in the table → opens sidebar (if collapsed) + switches to Details tab
  - Kicking off processing → opens sidebar + switches to Processing tab
  - Manual tab switching always available
- When no jobs are active, Processing tab shows "No active processing" with recent completed jobs below

### 3.2 Granular Progress Reporting

**Pipeline-side changes (evidence-engine):**

Each pipeline stage reports weighted progress:

| Pipeline Stage | Weight | Range |
|----------------|--------|-------|
| Text extraction (Stage 1) | 15% | 0–15% |
| Document summary (Stage 1.5) | 5% | 15–20% |
| Chunking/embedding (Stage 2) | 10% | 20–30% |
| Entity extraction (Stage 3) | 25% | 30–55% |
| Entity consolidation (Stage 3.5) | 5% | 55–60% |
| Entity resolution (Stage 4) | 10% | 60–70% |
| Relationship resolution (Stage 5 + 5.5) | 5% | 70–75% |
| Summary generation (Stage 6) | 10% | 75–85% |
| Graph write (Stage 7) | 15% | 85–100% |

This is the **authoritative** weight table — all progress reporting in orchestrator, batch_orchestrator, and the data flow below must use these ranges.

Within-stage granularity for heavy stages:
- Entity extraction: report per-chunk completion (e.g., "chunk 3/12")
- Resolution: report per-phase (blocking → embedding → LLM confirmation)
- Graph write: report per-batch (e.g., "writing batch 2/5")

Publish more frequently via Redis `job:{job_id}:progress` — within stages, not just at transitions.

**WebSocket message enrichment:**

Existing fields: `job_id`, `status`, `progress`, `message`

Enhanced `message` field carries stage-specific context:
- `"Extracting entities (chunk 8/12)"`
- `"Resolving entities across 5 files — embedding similarity phase"`
- `"Writing to graph (batch 3/5)"`

No new fields needed — just richer, more frequent publishes through the existing infrastructure.

**Frontend job card upgrade:**

Show current stage name + sub-progress:
```
invoice_march.pdf
████████░░░░ 65%
Extracting entities (chunk 8/12)
```

For batch-level unified stages:
```
Resolving entities across 5 files
██████████░░ 78%
Embedding similarity phase
```

---

## Section 4: Detail Panel Upgrade

### 4.1 Post-Processing Content Sections

When a file has `status: 'processed'`, the `EvidenceDetailSheet` gains additional collapsible sections:

1. **Document Summary** — rendered as markdown (Section 2.1), full structured summary with source links
2. **Extracted Entities** — compact list of entities sourced from this file, grouped by category. Each entity shows: name, category icon, confidence badge. Clickable to navigate to that entity in the graph explorer.
3. **Key Relationships** — most significant relationships extracted from this file, displayed as `Entity A → RELATIONSHIP_TYPE → Entity B` rows
4. **Processing Info** — when processed, which profile was used, entity count, relationship count, time taken

All sections are collapsible. Entities and relationships are loaded lazily.

### 4.2 New Backend Endpoints

- `GET /api/evidence/{evidence_id}/entities` — queries Neo4j for entities where `source_files` contains this file's name. Returns: `[{id, name, category, specific_type, confidence}]`
- `GET /api/evidence/{evidence_id}/relationships` — queries Neo4j for relationships where `source_files` contains this file's name. Returns: `[{source_entity_name, target_entity_name, type, detail, confidence}]`

Both endpoints are lightweight projections — no full entity data, just what the detail panel needs.

### 4.3 Status-Dependent Views

Clear visual distinction in the detail panel by file status:

- **Unprocessed:** Metadata + prominent "Process this file" call-to-action button
- **Processing:** Metadata + live progress indicator from WebSocket (current stage + percentage)
- **Processed:** Full intelligence view (all sections from 4.1)
- **Failed:** Metadata + error details card + "Retry" button

---

## Section 5: UI Polish

### 5.1 Empty States

- **Empty folder:** Friendly message with upload dropzone — "Drop files here or click Upload to get started"
- **No jobs:** "No processing activity" with subtle icon in the Processing sidebar tab
- **No summary available:** Styled card explaining the file needs processing first
- **Empty entity/relationship list:** "Process this file to extract entities and relationships"

### 5.2 Consistent Interactions

- **Drag-and-drop:** Improve `InlineDropZone` overlay with clearer visual feedback for folder vs general drop targets
- **Selection action bar:** When files are selected, show a floating action bar at bottom of file list with count + "Process X files" button (more discoverable than toolbar-only)
- **Loading skeletons:** Replace spinners with skeleton placeholders in file list, folder tree, and detail panel

### 5.3 Small Fixes

- Consistent file type icons across file list, detail panel, and document viewer
- Tooltips on truncated filenames in file list
- Keyboard shortcuts: Enter to open detail, Delete for delete dialog, Escape to close detail panel
- Visual indent lines in folder tree for nesting depth clarity

### 5.4 Sidebar Tab Consolidation

With jobs relocated (Section 3.1), the sidebar becomes the central context panel:
- **Details** tab — `EvidenceDetailSheet` content
- **Processing** tab — relocated `JobsPanel` content
- **AI Chat** tab — existing chat

Tab indicator shows activity (e.g., pulsing dot on Processing tab when jobs are active).

---

## Data Flow Summary (Post-Changes)

```
Upload → Backend disk + DB record (status: processing)
  → Engine receives file + folder context + sibling metadata
    → Stage 1: Extract text (progress: 0-15%)
    → Stage 1.5: Generate document summary as markdown (progress: 15-20%)
    → Stage 2: Chunk + embed to ChromaDB (progress: 20-30%)
    → Stage 3: Extract entities + relationships per chunk (progress: 30-55%)
    → Stage 3.5: Consolidate entities across batch (progress: 55-60%)
    → Stage 4: Resolve entities with cross-job dedup (progress: 60-70%)
    → Stage 5 + 5.5: Resolve relationships + link transaction parties (progress: 70-75%)
    → Stage 6: Generate entity summaries as structured markdown with source links (progress: 75-85%)
    → Stage 7: Write to Neo4j + embed for RAG (progress: 90-100%)
  → Redis pub/sub → WebSocket → Frontend progress updates (per-stage, within-stage)
  → JobStatusSubscriber syncs: status, entity_count, relationship_count, document_summary → DB
  → Frontend detail panel shows: summary (markdown), entities, relationships, processing info
```

---

## Files Affected

**Frontend (frontend_v2/src/):**
- `features/evidence/evidence.store.ts` — add `resetForCase()`, remove `jobsPanelOpen`
- `features/evidence/components/EvidenceExplorer.tsx` — remove bottom jobs panel, add case reset effect
- `features/evidence/components/FolderTreeSidebar.tsx` — add root context menu
- `features/evidence/components/FileRow.tsx` — fix entity count display
- `features/evidence/components/EvidenceDetailSheet.tsx` — major upgrade (status-dependent views, entities, relationships)
- `features/evidence/components/FileSummaryPanel.tsx` — markdown rendering
- `features/evidence/components/JobsPanel.tsx` — adapt for sidebar tab placement
- `features/evidence/components/JobCard.tsx` — enhanced progress display
- `features/evidence/components/FileListPanel.tsx` — empty states, selection action bar, loading skeletons
- `features/evidence/hooks/use-job-progress.ts` — handle enriched WebSocket messages
- New: sidebar tab container component
- New: markdown renderer with `evidence://` link interception
- New: hooks for fetching entities/relationships per file

**Backend:**
- `postgres/models/evidence.py` — add `entity_count`, `relationship_count` columns
- New Alembic migration for the new columns
- `routers/evidence.py` — add `/evidence/{id}/entities` and `/evidence/{id}/relationships` endpoints
- `services/job_status_subscriber.py` — populate entity_count, relationship_count on completion
- `services/evidence_db_storage.py` — update relevant queries

**Evidence Engine:**
- `app/pipeline/orchestrator.py` — more frequent progress publishes with richer messages
- `app/pipeline/batch_orchestrator.py` — same progress improvements
- `app/pipeline/extract_entities.py` — per-chunk progress reporting
- `app/pipeline/resolve_entities.py` — per-phase progress reporting
- `app/pipeline/write_graph.py` — per-batch progress reporting
- `app/pipeline/generate_document_summary.py` — increased context, structured markdown output
- `app/pipeline/generate_summaries.py` — structured markdown format, source references, improved merge logic
- `app/prompts/entity_summary.txt` — restructured prompt for markdown output with source links
- `app/prompts/entity_summary_merge.txt` — improved merge prompt preserving structure and sources
