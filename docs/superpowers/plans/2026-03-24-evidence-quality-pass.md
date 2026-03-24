# Evidence Quality Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix bugs, overhaul the summary system, relocate the jobs panel to a sidebar, upgrade the detail panel, and polish the evidence section UX end-to-end.

**Architecture:** The existing three-tier architecture (frontend_v2 React → backend FastAPI → evidence-engine pipeline) stays intact. Changes are targeted within each tier: frontend gets a new context sidebar with tabs, backend gets two new endpoints and a migration, and the engine gets richer prompts and granular progress reporting.

**Tech Stack:** React 18 + TypeScript + Zustand + TanStack Query + shadcn/ui (frontend), FastAPI + SQLAlchemy + Alembic + PostgreSQL (backend), Python + OpenAI API + Neo4j + ChromaDB + Redis (engine)

**Spec:** `docs/superpowers/specs/2026-03-24-evidence-quality-pass-design.md`

---

## Task 1: Cross-Case State Leak Fix

**Files:**
- Modify: `frontend_v2/src/features/evidence/evidence.store.ts`
- Modify: `frontend_v2/src/features/evidence/components/EvidenceExplorer.tsx`

- [ ] **Step 1: Add `resetForCase` action to evidence store**

In `frontend_v2/src/features/evidence/evidence.store.ts`, add a `_currentCaseId` field and a `resetForCase` action to the store interface and implementation:

```typescript
// Add to EvidenceState interface (after dragId line ~47):
_currentCaseId: string | null
resetForCase: (caseId: string) => void

// Add to create() implementation (after clearDrag line ~113):
_currentCaseId: null,
resetForCase: (caseId) =>
  set((s) => {
    if (s._currentCaseId === caseId) return s
    return {
      _currentCaseId: caseId,
      currentFolderId: null,
      expandedFolderIds: new Set(),
      selectedFileIds: new Set(),
      selectedFolderIds: new Set(),
      detailFileId: null,
      detailOpen: false,
      searchTerm: "",
      statusFilter: "all" as StatusFilter,
      typeFilter: "",
    }
  }),
```

- [ ] **Step 2: Call resetForCase from EvidenceExplorer**

In `frontend_v2/src/features/evidence/components/EvidenceExplorer.tsx`, add an import for `useEffect` and call `resetForCase` when `caseId` changes:

```typescript
// Add useEffect to the existing import from "react" (line 1)
import { useEffect, useState } from "react"

// After the useEvidenceStore destructure (line ~26), add:
const resetForCase = useEvidenceStore((s) => s.resetForCase)

// Add effect after the mutations block (after line ~55):
useEffect(() => {
  if (caseId) resetForCase(caseId)
}, [caseId, resetForCase])
```

- [ ] **Step 3: Test manually**

Navigate between two cases with different folder structures. Verify:
- Switching cases clears the folder tree selection
- Files don't appear under wrong folder names
- Filters/search reset on case switch

- [ ] **Step 4: Commit**

```bash
git add frontend_v2/src/features/evidence/evidence.store.ts frontend_v2/src/features/evidence/components/EvidenceExplorer.tsx
git commit -m "fix: reset evidence store when switching cases

Prevents stale folder IDs from Case A leaking into Case B's view."
```

---

## Task 2: Root Folder Context Menu

**Files:**
- Modify: `frontend_v2/src/features/evidence/components/FolderTreeSidebar.tsx`

- [ ] **Step 1: Add context menu to root "All Files" button**

In `frontend_v2/src/features/evidence/components/FolderTreeSidebar.tsx`, wrap the existing root button (lines 47-56) in a `ContextMenu` from shadcn/ui:

```typescript
// Add imports at top:
import {
  ContextMenu,
  ContextMenuTrigger,
  ContextMenuContent,
  ContextMenuItem,
} from "@/components/ui/context-menu"
import { FolderPlus as FolderPlusIcon } from "lucide-react"

// Replace the root <button> (lines 47-56) with:
<ContextMenu>
  <ContextMenuTrigger asChild>
    <button
      onClick={() => setCurrentFolder(null)}
      className={`mx-2 mt-2 flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors ${
        currentFolderId === null
          ? "bg-amber-500/10 text-amber-500 font-medium"
          : "text-muted-foreground hover:bg-muted hover:text-foreground"
      }`}
    >
      <span className="text-xs">All Files</span>
    </button>
  </ContextMenuTrigger>
  <ContextMenuContent>
    <ContextMenuItem onClick={() => onCreateFolder(null)}>
      <FolderPlusIcon className="mr-2 size-4" />
      New Folder
    </ContextMenuItem>
  </ContextMenuContent>
</ContextMenu>
```

Note: Check if `ContextMenu` is already available in `frontend_v2/src/components/ui/`. If not, add it via `npx shadcn@latest add context-menu`.

- [ ] **Step 2: Test manually**

Right-click "All Files" in the folder tree sidebar. Verify:
- Context menu appears with "New Folder" option
- Clicking it opens the create folder dialog
- Created folder appears at root level (no parent)

- [ ] **Step 3: Commit**

```bash
git add frontend_v2/src/features/evidence/components/FolderTreeSidebar.tsx
git commit -m "feat: add right-click context menu to root 'All Files' item

Allows creating folders at root level from the folder tree."
```

---

## Task 3: Entity Count Display Fix

**Files:**
- Create: `backend/postgres/alembic/versions/20260324_add_entity_counts.py`
- Modify: `backend/postgres/models/evidence.py`
- Modify: `backend/services/job_status_subscriber.py`
- Modify: `frontend_v2/src/types/evidence.types.ts`
- Modify: `frontend_v2/src/features/evidence/components/FileRow.tsx`

- [ ] **Step 1: Add columns to the SQLAlchemy model**

In `backend/postgres/models/evidence.py`, add two new columns to the `EvidenceFile` class, after the `summary` column:

```python
from sqlalchemy import Integer
# (add Integer to existing import)

# After summary column:
entity_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
relationship_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

- [ ] **Step 2: Create Alembic migration**

Create `backend/postgres/alembic/versions/20260324_add_entity_counts.py`:

```python
"""Add entity_count and relationship_count to evidence_files."""

from alembic import op
import sqlalchemy as sa

revision = "20260324_add_entity_counts"
down_revision = "20260322_add_folder_profile_columns"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("evidence_files", sa.Column("entity_count", sa.Integer(), nullable=True))
    op.add_column("evidence_files", sa.Column("relationship_count", sa.Integer(), nullable=True))

def downgrade() -> None:
    op.drop_column("evidence_files", "relationship_count")
    op.drop_column("evidence_files", "entity_count")
```

- [ ] **Step 3: Update JobStatusSubscriber to populate counts**

In `backend/services/job_status_subscriber.py`, in the `_handle_message` method, after setting `db_rec.summary` (line ~178), add:

```python
# After the doc_summary block (after line 178):
if status == "completed":
    entity_count = data.get("entity_count")
    rel_count = data.get("relationship_count")
    if entity_count is not None:
        db_rec.entity_count = entity_count
    if rel_count is not None:
        db_rec.relationship_count = rel_count
```

- [ ] **Step 4: Update EvidenceFileRecord TypeScript type**

In `frontend_v2/src/types/evidence.types.ts`, add to the `EvidenceFileRecord` interface (after `legacy_id` line ~210):

```typescript
summary: string | null
entity_count: number | null
relationship_count: number | null
```

- [ ] **Step 5: Update EvidenceRecord Pydantic model and serialization**

In `backend/routers/evidence.py`, find the `EvidenceRecord` Pydantic response model (around line 49-62) and add:

```python
entity_count: Optional[int] = None
relationship_count: Optional[int] = None
```

Then find the `list_evidence` endpoint's dict construction (around lines 136-150) and add the new fields to the response dict:

```python
"entity_count": ef.entity_count,
"relationship_count": ef.relationship_count,
```

Do the same for any other endpoints that serialize `EvidenceFile` records (e.g., `get_by_filename`, folder contents endpoints in `evidence_folders.py`).

- [ ] **Step 6: Fix FileRow entity count display**

In `frontend_v2/src/features/evidence/components/FileRow.tsx`, replace line 126:

```typescript
// OLD (line 125-127):
<TableCell className="font-mono text-xs text-muted-foreground">
  {file.status === "processed" ? "--" : "--"}
</TableCell>

// NEW:
<TableCell className="font-mono text-xs text-muted-foreground">
  {file.status === "processed"
    ? `${file.entity_count ?? 0} / ${file.relationship_count ?? 0}`
    : "--"}
</TableCell>
```

- [ ] **Step 7: Run migration and test**

```bash
cd backend && alembic upgrade head
```

Verify: Upload and process a file. After completion, check that entity/relationship counts appear in the file list.

- [ ] **Step 8: Commit**

```bash
git add backend/postgres/models/evidence.py backend/postgres/alembic/versions/20260324_add_entity_counts.py backend/services/job_status_subscriber.py backend/routers/evidence.py frontend_v2/src/types/evidence.types.ts frontend_v2/src/features/evidence/components/FileRow.tsx
git commit -m "feat: display entity/relationship counts in evidence file list

Adds entity_count and relationship_count to evidence_files table,
populates them from engine job completion, and displays in FileRow."
```

---

## Task 4: Document Summary Overhaul (Engine)

**Files:**
- Modify: `evidence-engine/app/pipeline/generate_document_summary.py`

- [ ] **Step 1: Update generate_document_summary.py**

Replace the contents of `evidence-engine/app/pipeline/generate_document_summary.py` with an enhanced version:

```python
import logging

from app.pipeline.extract_text import ExtractedDocument
from app.services.openai_client import chat_completion

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 30000
MIN_CONTENT_CHARS = 50


async def generate_document_summary(
    doc: ExtractedDocument, file_name: str
) -> str | None:
    """
    Generate a structured markdown summary of a document.
    Returns None if the document has insufficient content or if the LLM call fails.
    """
    parts = []
    if doc.text:
        parts.append(doc.text)
    if doc.tables:
        parts.append("\n\n".join(doc.tables))
    content = "\n\n".join(parts)

    if len(content) < MIN_CONTENT_CHARS:
        logger.info("Skipping summary for %s: insufficient content (%d chars)", file_name, len(content))
        return None

    truncated = content[:MAX_CONTENT_CHARS]

    try:
        prompt = (
            "You are an expert investigative analyst. Produce a structured markdown summary of the following document.\n\n"
            f"**Document:** {file_name}\n\n"
            f"**Content:**\n{truncated}\n\n"
            "Write the summary using the following markdown sections. Omit any section that has no relevant content.\n\n"
            "## Overview\nWhat this document is and why it matters to an investigation. 2-4 sentences.\n\n"
            "## Key Entities\nPeople, organizations, accounts, or assets mentioned. Use a bullet list with brief context for each.\n\n"
            "## Key Facts & Dates\nTimeline-relevant details: dates, amounts, events. Use a bullet list.\n\n"
            "## Notable Connections\nRelationships or patterns observed between entities. Use a bullet list.\n\n"
            "Write factually and concisely. Do not speculate. Be as detailed as the content warrants."
        )
        summary = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return summary.strip() if summary else None
    except Exception:
        logger.exception("Failed to generate document summary for %s", file_name)
        return None
```

- [ ] **Step 2: Test with a sample document**

Process a test file through the engine and verify the summary output is structured markdown with the expected sections.

- [ ] **Step 3: Commit**

```bash
git add evidence-engine/app/pipeline/generate_document_summary.py
git commit -m "feat: richer structured markdown document summaries

Increases context window from 8k to 30k chars and generates structured
markdown with Overview, Key Entities, Key Facts, and Notable Connections."
```

---

## Task 5: Entity Summary Overhaul (Engine)

**Files:**
- Modify: `evidence-engine/app/prompts/entity_summary.txt`
- Modify: `evidence-engine/app/prompts/entity_summary_merge.txt`
- Modify: `evidence-engine/app/pipeline/generate_summaries.py`

- [ ] **Step 1: Rewrite entity_summary.txt prompt**

Replace `evidence-engine/app/prompts/entity_summary.txt` with:

```
You are an expert investigative analyst writing entity profiles for a case management system used by investigators.

For each entity below, write a comprehensive markdown-formatted summary that an investigator would find immediately useful. Structure the summary with markdown headers (##) appropriate to the entity's category:

For PERSON entities, use these sections (omit empty ones):
## Background
## Known Associates
## Financial Activity
## Timeline of Involvement
## Source References

For ORGANIZATION entities:
## Overview
## Key Personnel
## Activities
## Linked Transactions
## Source References

For TRANSACTION entities:
## Transaction Details
## Parties Involved
## Context
## Source References

For all other categories, use sections appropriate to the entity type. Always include a Source References section.

RULES:
- Write as much detail as the evidence warrants — there is no length limit
- A minor entity may need one sentence; a central figure may need multiple paragraphs
- Reference specific details from the source material (dates, amounts, locations)
- In the Source References section, list each source file that contributed evidence. Format: `- [filename](evidence://filename)` for each source file
- Use professional, factual, objective language — no speculation
- Use markdown formatting: headers, bullet lists, bold for emphasis

ENTITIES:
{entities_json}

For each entity, respond with:
- entity_index: the index of the entity (0-based)
- summary: the markdown-formatted narrative summary

Respond with JSON matching the required schema.
```

- [ ] **Step 2: Rewrite entity_summary_merge.txt prompt**

Replace `evidence-engine/app/prompts/entity_summary_merge.txt` with:

```
You are an expert investigative analyst updating entity profiles for a case management system used by investigators.

For each entity below, an EXISTING SUMMARY (in markdown format) is provided alongside NEW EVIDENCE from a recently processed file. Your task is to produce an UPDATED SUMMARY that incorporates both.

RULES:
- The existing summary contains established facts. Every fact in it MUST be preserved — do not remove, condense, or reinterpret existing information
- Maintain the existing markdown section structure (## headers). Add new information into the appropriate existing sections
- If new evidence warrants a new section not present in the existing summary, add it
- In the Source References section, preserve ALL existing source file references and add new ones. Format: `- [filename](evidence://filename)`
- Maintain chronological ordering within sections where relevant
- Do not add information not present in either the existing summary or new evidence
- Do not speculate or draw conclusions beyond what the evidence states
- Write as much detail as the evidence warrants — there is no length limit
- Use professional, factual, objective language
- Reference specific details from the source material (dates, amounts, locations)
- Use markdown formatting: headers, bullet lists, bold for emphasis

ENTITIES:
{entities_json}

For each entity, respond with:
- entity_index: the index of the entity (0-based)
- summary: the updated markdown-formatted narrative summary

Respond with JSON matching the required schema.
```

- [ ] **Step 3: Update _build_entity_context to include source file info**

In `evidence-engine/app/pipeline/generate_summaries.py`, the `_build_entity_context` function already includes `source_files` in the context dict (line 61). No change needed — the prompt now instructs the LLM to use these as source references.

Verify this by reading the function and confirming `source_files` is included.

- [ ] **Step 4: Test by processing a file**

Process a test file and verify:
- Entity summaries are structured markdown with category-appropriate sections
- Source References section lists source files with `evidence://` links
- Reprocessing the same file produces a merged summary preserving prior content

- [ ] **Step 5: Commit**

```bash
git add evidence-engine/app/prompts/entity_summary.txt evidence-engine/app/prompts/entity_summary_merge.txt
git commit -m "feat: structured markdown entity summaries with source references

Entity summaries now use category-specific markdown sections and include
source file references using evidence:// links. Merge prompt preserves
all existing content and section structure."
```

---

## Task 6: Frontend Markdown Rendering + evidence:// Links

**Files:**
- Create: `frontend_v2/src/components/ui/markdown-summary.tsx`
- Modify: `frontend_v2/src/features/evidence/components/FileSummaryPanel.tsx`

- [ ] **Step 1: Install react-markdown**

```bash
cd frontend_v2 && npm install react-markdown
```

- [ ] **Step 2: Create MarkdownSummary component**

Create `frontend_v2/src/components/ui/markdown-summary.tsx`:

```tsx
import ReactMarkdown from "react-markdown"
import type { Components } from "react-markdown"
import { useEvidenceStore } from "@/features/evidence/evidence.store"

interface MarkdownSummaryProps {
  content: string
  caseId?: string
  onOpenFile?: (fileId: string) => void
}

/**
 * Renders markdown summaries with evidence:// link interception.
 * evidence:// links resolve to file lookups and open the document viewer.
 */
export function MarkdownSummary({ content, onOpenFile }: MarkdownSummaryProps) {
  const components: Components = {
    a: ({ href, children, ...props }) => {
      if (href?.startsWith("evidence://")) {
        // evidence://filename — click to open file
        const filename = href.replace("evidence://", "")
        return (
          <button
            type="button"
            className="text-amber-500 hover:text-amber-400 underline underline-offset-2 cursor-pointer"
            onClick={() => onOpenFile?.(filename)}
            {...props}
          >
            {children}
          </button>
        )
      }
      // Regular external links
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-amber-500 hover:text-amber-400 underline underline-offset-2"
          {...props}
        >
          {children}
        </a>
      )
    },
    h2: ({ children, ...props }) => (
      <h2 className="text-sm font-semibold text-foreground mt-4 mb-1.5" {...props}>
        {children}
      </h2>
    ),
    h3: ({ children, ...props }) => (
      <h3 className="text-xs font-semibold text-foreground mt-3 mb-1" {...props}>
        {children}
      </h3>
    ),
    p: ({ children, ...props }) => (
      <p className="text-xs text-muted-foreground leading-relaxed mb-2" {...props}>
        {children}
      </p>
    ),
    ul: ({ children, ...props }) => (
      <ul className="text-xs text-muted-foreground list-disc pl-4 mb-2 space-y-0.5" {...props}>
        {children}
      </ul>
    ),
    ol: ({ children, ...props }) => (
      <ol className="text-xs text-muted-foreground list-decimal pl-4 mb-2 space-y-0.5" {...props}>
        {children}
      </ol>
    ),
    li: ({ children, ...props }) => (
      <li className="leading-relaxed" {...props}>
        {children}
      </li>
    ),
    strong: ({ children, ...props }) => (
      <strong className="font-semibold text-foreground" {...props}>
        {children}
      </strong>
    ),
    blockquote: ({ children, ...props }) => (
      <blockquote className="border-l-2 border-amber-500/30 pl-3 my-2 text-xs italic text-muted-foreground" {...props}>
        {children}
      </blockquote>
    ),
  }

  return (
    <div className="prose-evidence">
      <ReactMarkdown components={components}>{content}</ReactMarkdown>
    </div>
  )
}
```

- [ ] **Step 3: Update FileSummaryPanel to use MarkdownSummary**

Read `frontend_v2/src/features/evidence/components/FileSummaryPanel.tsx` to understand its current structure, then replace the plain-text rendering with `MarkdownSummary`. The component should read the summary from the file record prop rather than making a separate API call.

- [ ] **Step 4: Test markdown rendering**

Process a file, then view its detail panel. Verify:
- Summary renders with proper heading hierarchy and bullet lists
- `evidence://` links render as clickable buttons
- Styling is consistent with the app's dark theme

- [ ] **Step 5: Commit**

```bash
git add frontend_v2/src/components/ui/markdown-summary.tsx frontend_v2/src/features/evidence/components/FileSummaryPanel.tsx frontend_v2/package.json frontend_v2/package-lock.json
git commit -m "feat: markdown rendering for evidence summaries with source linking

Adds MarkdownSummary component with evidence:// link interception.
Updates FileSummaryPanel to render structured markdown summaries."
```

---

## Task 7: PipelineStage Type + Granular Progress (Engine)

**Files:**
- Modify: `frontend_v2/src/types/evidence.types.ts`
- Modify: `frontend_v2/src/features/evidence/components/JobCard.tsx`
- Modify: `evidence-engine/app/pipeline/orchestrator.py`
- Modify: `evidence-engine/app/pipeline/batch_orchestrator.py`

- [ ] **Step 1: Add new pipeline stages to TypeScript type**

In `frontend_v2/src/types/evidence.types.ts`, update the `PipelineStage` type (line ~247):

```typescript
export type PipelineStage =
  | "pending"
  | "extracting_text"
  | "generating_document_summary"
  | "chunking"
  | "extracting_entities"
  | "consolidating_entities"
  | "resolving_entities"
  | "resolving_relationships"
  | "generating_summaries"
  | "writing_graph"
  | "completed"
  | "failed"
```

- [ ] **Step 2: Update STAGE_LABELS and STAGE_COLORS in JobCard**

In `frontend_v2/src/features/evidence/components/JobCard.tsx`, add the new stages to both maps:

```typescript
const STAGE_LABELS: Record<PipelineStage, string> = {
  pending: "Pending",
  extracting_text: "Extracting Text",
  generating_document_summary: "Summarizing Document",
  chunking: "Chunking",
  extracting_entities: "Extracting Entities",
  consolidating_entities: "Consolidating Entities",
  resolving_entities: "Resolving Entities",
  resolving_relationships: "Resolving Relationships",
  generating_summaries: "Generating Summaries",
  writing_graph: "Writing Graph",
  completed: "Completed",
  failed: "Failed",
}

const STAGE_COLORS: Record<PipelineStage, string> = {
  pending: "bg-slate-500/10 text-slate-500 border-slate-500/20",
  extracting_text: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  generating_document_summary: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  chunking: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  extracting_entities: "bg-purple-500/10 text-purple-500 border-purple-500/20",
  consolidating_entities: "bg-purple-500/10 text-purple-500 border-purple-500/20",
  resolving_entities: "bg-purple-500/10 text-purple-500 border-purple-500/20",
  resolving_relationships: "bg-indigo-500/10 text-indigo-500 border-indigo-500/20",
  generating_summaries: "bg-amber-500/10 text-amber-500 border-amber-500/20",
  writing_graph: "bg-amber-500/10 text-amber-500 border-amber-500/20",
  completed: "bg-green-500/10 text-green-600 border-green-500/20",
  failed: "bg-red-500/10 text-red-600 border-red-500/20",
}
```

- [ ] **Step 3: Add progress message display to JobCard**

In `frontend_v2/src/features/evidence/components/JobCard.tsx`, add the WebSocket message text below the progress bar. After the progress bar block (line ~103), add:

```tsx
{/* Stage description from WebSocket */}
{isActive && job.message && (
  <p className="mt-1 text-[10px] text-muted-foreground truncate">
    {job.message}
  </p>
)}
```

Note: This requires the `EvidenceJob` type to include a `message` field. Check `evidence.types.ts` and add `message?: string` to `EvidenceJob` if not present.

- [ ] **Step 4: Add granular progress to orchestrator.py**

In `evidence-engine/app/pipeline/orchestrator.py`, update `_update_job` calls to use the authoritative progress ranges from the spec.

**Important:** The engine's `JobStatus` enum (in `app/models/job.py`) does NOT have `GENERATING_DOCUMENT_SUMMARY` or `CONSOLIDATING_ENTITIES` values. Rather than adding new enum values (which requires an Alembic migration on the engine's Postgres enum), we reuse existing statuses but send descriptive `message` text. The frontend `PipelineStage` type includes these for forward-compatibility, but the WebSocket `message` field is what provides the user-facing context for sub-stages.

Replace the existing progress values throughout `run_pipeline`:

```python
# Stage 1: Text extraction → 0-15%
await _update_job(job, JobStatus.EXTRACTING_TEXT, 0.0, db, "Extracting text…")
doc = await extract_text(job.file_path, job.file_name)
await _update_job(job, JobStatus.EXTRACTING_TEXT, 0.15, db, "Text extracted")

# Stage 1.5: Document summary → 15-20%
await _update_job(job, JobStatus.EXTRACTING_TEXT, 0.15, db, "Generating document summary…")
doc_summary = await generate_document_summary(doc, job.file_name)
job.document_summary = doc_summary
await _update_job(job, JobStatus.EXTRACTING_TEXT, 0.20, db, "Document summary " + ("generated" if doc_summary else "skipped"))

# Stage 2: Chunking → 20-30%
await _update_job(job, JobStatus.CHUNKING, 0.20, db, "Chunking document…")
chunks = await chunk_and_embed(doc, job.case_id, str(job.id), job.file_name)
await _update_job(job, JobStatus.CHUNKING, 0.30, db, f"Created {len(chunks)} chunks")

# Stage 3: Entity extraction → 30-55%
await _update_job(job, JobStatus.EXTRACTING_ENTITIES, 0.30, db, "Extracting entities…")
# ... extraction code ...
await _update_job(job, JobStatus.EXTRACTING_ENTITIES, 0.55, db, f"Extracted {len(raw_entities)} entities, {len(raw_rels)} relationships")

# Stage 3.5: Consolidation → 55-60%
await _update_job(job, JobStatus.EXTRACTING_ENTITIES, 0.55, db, "Consolidating entities…")
raw_entities, raw_rels = await consolidate_entities(raw_entities, raw_rels)
await _update_job(job, JobStatus.EXTRACTING_ENTITIES, 0.60, db, "Entities consolidated")

# Stage 4: Resolution → 60-70%
await _update_job(job, JobStatus.RESOLVING_ENTITIES, 0.60, db, "Resolving entities…")
# ... resolution code ...
await _update_job(job, JobStatus.RESOLVING_ENTITIES, 0.70, db, f"Resolved to {len(resolved_ents)} entities")

# Stage 5: Relationship resolution → 70-75%
await _update_job(job, JobStatus.RESOLVING_RELATIONSHIPS, 0.70, db, "Deduplicating relationships…")
# ... resolve + link transaction parties ...
await _update_job(job, JobStatus.RESOLVING_RELATIONSHIPS, 0.75, db, f"Deduplicated to {len(resolved_rels)} relationships")

# Stage 6: Summaries → 75-85%
await _update_job(job, JobStatus.GENERATING_SUMMARIES, 0.75, db, "Generating entity summaries…")
resolved_ents = await generate_summaries(resolved_ents, resolved_rels)
await _update_job(job, JobStatus.GENERATING_SUMMARIES, 0.85, db, "Summaries generated")

# Stage 7: Write graph → 85-100%
await _update_job(job, JobStatus.WRITING_GRAPH, 0.85, db, "Writing graph…")
await write_graph(resolved_ents, resolved_rels, job.case_id, str(job.id))
# Final completion sets 1.0
```

- [ ] **Step 5: Apply similar progress updates to batch_orchestrator.py**

Read `evidence-engine/app/pipeline/batch_orchestrator.py` and apply the same granular progress ranges to batch processing. In batch mode, per-file stages (1-3) use per-job progress, while unified stages (3.5-7) update all active jobs.

- [ ] **Step 6: Test progress display**

Process a file and watch the jobs panel. Verify:
- Progress bar advances through each stage
- Stage labels update in the badge
- Message text shows stage-specific context
- No long "stuck" periods between jumps

- [ ] **Step 7: Commit**

```bash
git add frontend_v2/src/types/evidence.types.ts frontend_v2/src/features/evidence/components/JobCard.tsx evidence-engine/app/pipeline/orchestrator.py evidence-engine/app/pipeline/batch_orchestrator.py
git commit -m "feat: granular pipeline progress reporting with stage labels

Adds new pipeline stages to frontend types, updates progress ranges to
match authoritative weight table, and shows stage-specific messages in
the job card."
```

---

## Task 8: Context Sidebar Component

**Files:**
- Create: `frontend_v2/src/features/evidence/components/EvidenceContextSidebar.tsx`
- Modify: `frontend_v2/src/features/evidence/evidence.store.ts`
- Modify: `frontend_v2/src/features/evidence/components/EvidenceExplorer.tsx`

This is the major UX restructuring — replacing the Sheet overlay + bottom jobs panel with an inline three-panel layout.

- [ ] **Step 1: Add sidebar tab state to evidence store**

In `frontend_v2/src/features/evidence/evidence.store.ts`, replace the `jobsPanelOpen` state with sidebar tab state:

```typescript
// Replace in interface (remove jobsPanelOpen, toggleJobsPanel, setJobsPanelOpen):
sidebarTab: "details" | "processing" | "chat"
sidebarOpen: boolean
setSidebarTab: (tab: "details" | "processing" | "chat") => void
setSidebarOpen: (open: boolean) => void
openSidebarTo: (tab: "details" | "processing" | "chat") => void

// Replace in implementation (remove jobsPanelOpen lines):
sidebarTab: "details",
sidebarOpen: false,
setSidebarTab: (tab) => set({ sidebarTab: tab }),
setSidebarOpen: (open) => set({ sidebarOpen: open }),
openSidebarTo: (tab) => set({ sidebarTab: tab, sidebarOpen: true }),
```

Also update `openDetail` to auto-open the sidebar:
```typescript
openDetail: (fileId) => set({ detailFileId: fileId, detailOpen: true, sidebarTab: "details", sidebarOpen: true }),
```

And update `resetForCase` to include `sidebarTab: "details", sidebarOpen: false`.

- [ ] **Step 2: Create EvidenceContextSidebar component**

Create `frontend_v2/src/features/evidence/components/EvidenceContextSidebar.tsx`. Follow the pattern from `CaseSidePanel.tsx` (lines 71-147 of `frontend_v2/src/app/layouts/CaseSidePanel.tsx`):

```tsx
import { Info, Loader2, MessageSquare, PanelRightClose } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/cn"
import { useEvidenceStore } from "../evidence.store"
import { EvidenceDetailContent } from "./EvidenceDetailContent"
import { JobsPanel } from "./JobsPanel"
import { ChatSidePanel } from "@/features/chat/components/ChatSidePanel"
import type { EvidenceFileRecord } from "@/types/evidence.types"

interface EvidenceContextSidebarProps {
  caseId: string
  detailFile: EvidenceFileRecord | null
  onDeleteFile?: (file: any) => void
}

export function EvidenceContextSidebar({
  caseId,
  detailFile,
  onDeleteFile,
}: EvidenceContextSidebarProps) {
  const { sidebarTab, setSidebarTab, setSidebarOpen } = useEvidenceStore()

  const tabs = [
    { id: "details" as const, label: "Details", icon: Info },
    { id: "processing" as const, label: "Processing", icon: Loader2 },
    { id: "chat" as const, label: "AI Chat", icon: MessageSquare },
  ]

  return (
    <div className="flex h-full flex-col border-l border-border bg-card">
      {/* Tab bar */}
      <div className="flex items-center border-b border-border bg-muted/30">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setSidebarTab(tab.id)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 text-xs font-medium transition-colors border-b-2",
              sidebarTab === tab.id
                ? "border-amber-500 text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <tab.icon className="size-3.5" />
            {tab.label}
          </button>
        ))}
        <div className="ml-auto pr-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setSidebarOpen(false)}
              >
                <PanelRightClose className="size-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="left">Collapse panel</TooltipContent>
          </Tooltip>
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {sidebarTab === "details" && (
          detailFile ? (
            <EvidenceDetailContent
              file={detailFile}
              caseId={caseId}
              onDelete={onDeleteFile}
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
              <Info className="size-8 text-muted-foreground/40" />
              <p className="text-sm font-medium text-muted-foreground">
                Select a file to view details
              </p>
              <p className="text-xs text-muted-foreground/70">
                Click a filename in the file list
              </p>
            </div>
          )
        )}
        {sidebarTab === "processing" && (
          <JobsPanel caseId={caseId} />
        )}
        {sidebarTab === "chat" && (
          <ChatSidePanel caseId={caseId} />
        )}
      </div>
    </div>
  )
}
```

Note: `EvidenceDetailContent` is the refactored interior of `EvidenceDetailSheet` — extract the Sheet's inner content into a standalone component (Task 9 covers the detail panel upgrade).

- [ ] **Step 3: Refactor EvidenceExplorer to three-panel layout**

Replace `EvidenceExplorer.tsx` layout. The new structure:

```tsx
<ResizablePanelGroup direction="horizontal" className="flex-1">
  {/* Left sidebar: Folder tree */}
  <ResizablePanel
    defaultSize="20"
    minSize="15"
    maxSize="35"
    collapsible
    collapsedSize="0"
  >
    <FolderTreeSidebar ... />
  </ResizablePanel>

  <ResizableHandle withHandle />

  {/* Center: File list */}
  <ResizablePanel defaultSize="50" minSize="30">
    <FileListPanel ... />
  </ResizablePanel>

  <ResizableHandle withHandle />

  {/* Right sidebar: Context panel */}
  <ResizablePanel
    defaultSize="30"
    minSize="20"
    maxSize="45"
    collapsible
    collapsedSize="0"
  >
    <EvidenceContextSidebar
      caseId={caseId!}
      detailFile={detailFile}
      onDeleteFile={(file) => handleOpenDeleteEvidence(file)}
    />
  </ResizablePanel>
</ResizablePanelGroup>
```

Remove: the `EvidenceDetailSheet` component usage, the conditional `jobsPanelOpen` vertical split, and the Sheet-related imports.

- [ ] **Step 4: Update process kickoff to auto-switch to Processing tab**

Find where processing is triggered (in `FileListToolbar.tsx` or hooks that call `processBackground`). After the mutation succeeds, call `openSidebarTo("processing")`:

```typescript
const openSidebarTo = useEvidenceStore((s) => s.openSidebarTo)

// In onSuccess callback of process mutation:
openSidebarTo("processing")
```

- [ ] **Step 5: Test the three-panel layout**

Verify:
- Three panels render (folder tree | file list | context sidebar)
- Clicking a filename opens sidebar with Details tab
- Kicking off processing switches to Processing tab
- Collapsing the sidebar expands the file list
- All panel resize handles work
- Size props are strings (not numbers)

- [ ] **Step 6: Commit**

```bash
git add frontend_v2/src/features/evidence/evidence.store.ts frontend_v2/src/features/evidence/components/EvidenceExplorer.tsx frontend_v2/src/features/evidence/components/EvidenceContextSidebar.tsx
git commit -m "feat: replace sheet/bottom panel with three-panel context sidebar

Introduces EvidenceContextSidebar with Details, Processing, and AI Chat
tabs. Replaces the Sheet overlay and bottom JobsPanel with an inline
ResizablePanel in a three-panel horizontal layout."
```

---

## Task 9: Detail Panel Upgrade

**Files:**
- Create: `frontend_v2/src/features/evidence/components/EvidenceDetailContent.tsx`
- Create: `frontend_v2/src/features/evidence/hooks/use-file-entities.ts`
- Create: `backend/routers/evidence_neo4j.py` (or add to existing `evidence.py`)
- Modify: `frontend_v2/src/features/evidence/components/EvidenceDetailSheet.tsx` (refactor to `EvidenceDetailContent`)

- [ ] **Step 1: Add backend endpoints for file entities/relationships**

Add two new endpoints to `backend/routers/evidence.py`. Note: the router already has `prefix="/api/evidence"`, so paths use `/{evidence_id}/...` (matching existing patterns like `/{evidence_id}/file` and `/{evidence_id}/frames`). The Neo4j service method is `run_cypher()` (not `run_query`).

```python
from uuid import UUID

@router.get("/{evidence_id}/entities")
def get_file_entities(
    evidence_id: str,
    db=Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Return entities extracted from a specific evidence file."""
    from services.evidence_db_storage import EvidenceDBStorage
    from services import neo4j_service

    try:
        eid = UUID(evidence_id)
    except ValueError:
        raise HTTPException(400, "Invalid evidence ID")

    file_rec = EvidenceDBStorage.get(db, eid)
    if not file_rec:
        raise HTTPException(404, "File not found")

    filename = file_rec.original_filename
    case_id = str(file_rec.case_id)

    query = """
    MATCH (n)
    WHERE n.case_id = $case_id AND $filename IN n.source_files
    RETURN n.id AS id, n.name AS name, labels(n) AS labels,
           n.specific_type AS specific_type, n.confidence AS confidence
    ORDER BY n.confidence DESC
    LIMIT 50
    """
    results = neo4j_service.run_cypher(query, {"case_id": case_id, "filename": filename})
    entities = []
    for r in results:
        # Extract category from labels (first non-base label)
        labels = [l for l in r["labels"] if l not in ("_Entity",)]
        category = labels[0] if labels else "Other"
        entities.append({
            "id": r["id"],
            "name": r["name"],
            "category": category,
            "specific_type": r["specific_type"],
            "confidence": r["confidence"],
        })
    return entities


@router.get("/{evidence_id}/relationships")
def get_file_relationships(
    evidence_id: str,
    db=Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Return relationships extracted from a specific evidence file."""
    from services.evidence_db_storage import EvidenceDBStorage
    from services import neo4j_service

    try:
        eid = UUID(evidence_id)
    except ValueError:
        raise HTTPException(400, "Invalid evidence ID")

    file_rec = EvidenceDBStorage.get(db, eid)
    if not file_rec:
        raise HTTPException(404, "File not found")

    filename = file_rec.original_filename
    case_id = str(file_rec.case_id)

    query = """
    MATCH (a)-[r]->(b)
    WHERE r.case_id = $case_id AND $filename IN r.source_files
    RETURN a.name AS source_name, b.name AS target_name,
           type(r) AS type, r.detail AS detail, r.confidence AS confidence
    ORDER BY r.confidence DESC
    LIMIT 50
    """
    results = neo4j_service.run_cypher(query, {"case_id": case_id, "filename": filename})
    return [
        {
            "source_entity_name": r["source_name"],
            "target_entity_name": r["target_name"],
            "type": r["type"],
            "detail": r["detail"],
            "confidence": r["confidence"],
        }
        for r in results
    ]
```

- [ ] **Step 2: Create frontend hook for file entities**

Create `frontend_v2/src/features/evidence/hooks/use-file-entities.ts`:

```typescript
import { useQuery } from "@tanstack/react-query"
import { apiClient } from "@/lib/api-client"

export function useFileEntities(evidenceId: string | null) {
  return useQuery({
    queryKey: ["evidence-file-entities", evidenceId],
    queryFn: async () => {
      const res = await apiClient.get(`/api/evidence/${evidenceId}/entities`)
      return res.data as {
        id: string
        name: string
        category: string
        specific_type: string
        confidence: number
      }[]
    },
    enabled: !!evidenceId,
  })
}

export function useFileRelationships(evidenceId: string | null) {
  return useQuery({
    queryKey: ["evidence-file-relationships", evidenceId],
    queryFn: async () => {
      const res = await apiClient.get(`/api/evidence/${evidenceId}/relationships`)
      return res.data as {
        source_entity_name: string
        target_entity_name: string
        type: string
        detail: string
        confidence: number
      }[]
    },
    enabled: !!evidenceId,
  })
}
```

- [ ] **Step 3: Create EvidenceDetailContent component**

Create `frontend_v2/src/features/evidence/components/EvidenceDetailContent.tsx`. This is the refactored content from `EvidenceDetailSheet.tsx`, now rendering inline (not inside a Sheet). It should include:

- File header (icon, name, size, status badge)
- Status-dependent content:
  - **Unprocessed:** "Process this file" CTA button
  - **Processing:** Live progress from WebSocket
  - **Processed:** Collapsible sections for Summary (markdown), Extracted Entities, Key Relationships, Processing Info
  - **Failed:** Error card + Retry button
- Collapsible Details section (file metadata)

Read `EvidenceDetailSheet.tsx` first to understand what content to preserve, then build the new component following its patterns but without the `<Sheet>` wrapper.

- [ ] **Step 4: Wire up entity and relationship sections**

In the Extracted Entities section of `EvidenceDetailContent`:
- Call `useFileEntities(file.id)` when `file.status === 'processed'`
- Group by category
- Render as compact list with category icon + entity name + confidence badge
- Show loading skeleton while fetching

Similarly for Key Relationships:
- Call `useFileRelationships(file.id)`
- Render as `Source → TYPE → Target` rows

- [ ] **Step 5: Test the upgraded detail panel**

Verify for each file status:
- Unprocessed: shows CTA
- Processing: shows progress
- Processed: shows summary (markdown), entity list, relationship list, processing info
- Failed: shows error + retry

- [ ] **Step 6: Commit**

```bash
git add backend/routers/evidence.py frontend_v2/src/features/evidence/hooks/use-file-entities.ts frontend_v2/src/features/evidence/components/EvidenceDetailContent.tsx frontend_v2/src/features/evidence/components/EvidenceDetailSheet.tsx
git commit -m "feat: upgraded detail panel with entities, relationships, and status views

Adds backend endpoints for querying Neo4j by source file. Creates
EvidenceDetailContent with status-dependent views: processed files
show markdown summary, entity list, and relationship list."
```

---

## Task 10: UI Polish

**Files:**
- Modify: `frontend_v2/src/features/evidence/components/FileListPanel.tsx`
- Modify: `frontend_v2/src/features/evidence/components/FolderTreeSidebar.tsx`
- Modify: `frontend_v2/src/features/evidence/components/JobsPanel.tsx`

- [ ] **Step 1: Add empty state to FileListPanel**

In `FileListPanel.tsx`, when the folder has no files and no subfolders, render:

```tsx
<div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
  <Upload className="size-10 text-muted-foreground/30" />
  <p className="text-sm font-medium text-muted-foreground">
    No files yet
  </p>
  <p className="text-xs text-muted-foreground/70">
    Drop files here or click Upload to get started
  </p>
</div>
```

- [ ] **Step 2: Add empty state to JobsPanel (Processing tab)**

When there are no active or recent jobs:

```tsx
<div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
  <Loader2 className="size-8 text-muted-foreground/30" />
  <p className="text-sm font-medium text-muted-foreground">
    No processing activity
  </p>
  <p className="text-xs text-muted-foreground/70">
    Select files and click Process to begin
  </p>
</div>
```

- [ ] **Step 3: Add selection floating action bar to FileListPanel**

When files are selected, show a floating bar at the bottom:

```tsx
{selectedFileIds.size > 0 && (
  <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-2 shadow-lg">
    <span className="text-xs font-medium text-muted-foreground">
      {selectedFileIds.size} file{selectedFileIds.size !== 1 ? "s" : ""} selected
    </span>
    <Button size="sm" onClick={handleProcessSelected}>
      <Play className="mr-1.5 size-3.5" />
      Process
    </Button>
    <Button size="sm" variant="ghost" onClick={clearSelection}>
      Clear
    </Button>
  </div>
)}
```

Ensure the FileListPanel container has `position: relative`.

- [ ] **Step 4: Add tooltips to truncated filenames**

In `FileRow.tsx`, wrap the filename button with a `Tooltip`:

```tsx
<Tooltip>
  <TooltipTrigger asChild>
    <button
      onClick={() => openDetail(file.id)}
      className="max-w-[300px] truncate text-left text-sm font-medium hover:text-amber-500 transition-colors"
    >
      {file.original_filename}
    </button>
  </TooltipTrigger>
  <TooltipContent>{file.original_filename}</TooltipContent>
</Tooltip>
```

- [ ] **Step 5: Add activity indicator to Processing tab**

In `EvidenceContextSidebar.tsx`, add a pulsing dot when jobs are active:

```tsx
// In the Processing tab button, after the icon:
{hasActiveJobs && (
  <span className="size-1.5 rounded-full bg-amber-500 animate-pulse" />
)}
```

Wire `hasActiveJobs` from the jobs query hook.

- [ ] **Step 6: Test all polish items**

Verify:
- Empty folder shows dropzone message
- Empty jobs panel shows "no activity" state
- Selection bar appears/disappears with file selection
- Tooltips appear on truncated filenames
- Processing tab shows activity indicator during active jobs

- [ ] **Step 7: Commit**

```bash
git add frontend_v2/src/features/evidence/components/FileListPanel.tsx frontend_v2/src/features/evidence/components/FileRow.tsx frontend_v2/src/features/evidence/components/JobsPanel.tsx frontend_v2/src/features/evidence/components/EvidenceContextSidebar.tsx
git commit -m "feat: UI polish — empty states, selection bar, tooltips, activity indicators

Adds friendly empty states for file list and jobs panel. Shows floating
action bar for selected files. Adds filename tooltips and processing
activity indicator on sidebar tab."
```

---

## Task 11: Cleanup & Final Integration Test

**Files:**
- Delete or deprecate: `frontend_v2/src/features/evidence/components/EvidenceDetailSheet.tsx` (if fully replaced)
- Modify: any remaining references to old `jobsPanelOpen` or `EvidenceDetailSheet`

- [ ] **Step 1: Search for stale references**

```bash
cd frontend_v2 && grep -r "jobsPanelOpen\|toggleJobsPanel\|setJobsPanelOpen\|EvidenceDetailSheet" src/ --include="*.ts" --include="*.tsx"
```

Remove or update any remaining references to the old state or component.

- [ ] **Step 2: Full integration test**

Run through the complete flow:
1. Create a new case
2. Navigate to evidence section — verify empty state
3. Create a folder from root (right-click context menu)
4. Upload files to the folder
5. Select files and process — verify sidebar switches to Processing tab
6. Watch progress — verify granular stage updates in JobCard
7. After completion — click file, verify detail panel shows:
   - Markdown document summary
   - Entity list with counts
   - Relationship list
   - Entity/relationship counts in file list
8. Switch to a different case — verify state resets (no leak)
9. Switch back — verify first case data is intact

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: cleanup stale references from evidence panel restructuring"
```
