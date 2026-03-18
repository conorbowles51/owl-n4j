# OWL Investigation Platform — User Workflow Guides

> **Version:** February 2026  
> These guides walk you through common investigation workflows step by step. Each workflow builds on the previous one, so we recommend reading them in order the first time through.

---

## Table of Contents

1. [Getting Started — Your First Case](#1-getting-started--your-first-case)
2. [Uploading Evidence Files](#2-uploading-evidence-files)
3. [Processing Evidence with the LLM](#3-processing-evidence-with-the-llm)
4. [Working with the Knowledge Graph](#4-working-with-the-knowledge-graph)
5. [Investigating Entities — Facts, Insights & Source Documents](#5-investigating-entities--facts-insights--source-documents)
6. [Building Investigation Theories](#6-building-investigation-theories)
7. [Marking Evidence as Relevant](#7-marking-evidence-as-relevant)
8. [Finding & Merging Duplicate Entities](#8-finding--merging-duplicate-entities)
9. [Using the Investigation Workspace](#9-using-the-investigation-workspace)
10. [Saving & Comparing Snapshots](#10-saving--comparing-snapshots)
11. [Financial Transaction Analysis](#11-financial-transaction-analysis)
12. [Wiretap Folder Processing](#12-wiretap-folder-processing)
13. [Using the AI Chat Assistant](#13-using-the-ai-chat-assistant)
14. [Exporting & Reporting](#14-exporting--reporting)
15. [Backfilling Summaries & Embeddings](#15-backfilling-summaries--embeddings)
16. [Administration & User Management](#16-administration--user-management)

---

## 1. Getting Started — Your First Case

### What you'll learn
How to create a new investigation case, set it up with context, and invite collaborators.

### Steps

**Step 1 — Sign In**

When you first open OWL, you'll see the sign-in panel in the top-left corner. Enter your username and password and click **Sign In**. If you need to change your password later, click **Change Password** from the account dropdown (your initials icon in the top-left corner after logging in).

**Step 2 — Create a Case**

After signing in, you land on the **Case Management** view. This shows all cases you have access to.

```
┌──────────────────────────────────────────────┐
│  📂 My Cases                    [+ Create]   │
│  ─────────────────────────────────────────── │
│  No cases yet. Create your first case above. │
└──────────────────────────────────────────────┘
```

Click the **+ Create** button in the top-right. A modal appears:

- **Title** — Give your case a name (e.g., "Smith Financial Fraud Investigation")
- **Description** — Briefly describe the case
- **Save Notes** — Optional internal notes

Click **Save** to create the case.

**Step 3 — Add Collaborators (Optional)**

On your case card, click the **people icon** to open the **Collaborators** modal. Here you can:

- Invite other users by email
- Set permission levels: **Owner**, **Editor**, **Viewer**, or **Guest**
- Editors can modify case data; Viewers can only read

**Step 4 — Enter the Case**

Click **Load Case** on the case card. A progress dialog shows while the case loads. You'll arrive at the **Workspace View** — the main investigation screen.

---

## 2. Uploading Evidence Files

### What you'll learn
How to upload individual files, folders, and large batches of evidence into a case.

### Steps

**Step 1 — Open Evidence Processing**

From the Case Management screen, click the **Evidence Processing** button on your case card. This opens the full-screen Evidence Processing view.

```
┌─────────────────────────────────────────────────────┐
│  Evidence Processing — Smith Investigation          │
│  ──────────────────────────────────────────────────  │
│  [📤 Upload Files]  [📁 Upload Folder]              │
│  ──────────────────────────────────────────────────  │
│                                                     │
│  ┌──────────────┐  ┌──────────────────────────────┐ │
│  │ File         │  │  Unprocessed Files            │ │
│  │ Navigator    │  │  ─────────────────────        │ │
│  │              │  │  (empty)                      │ │
│  │              │  │                               │ │
│  │              │  │  LLM Processed Files          │ │
│  │              │  │  ─────────────────────        │ │
│  │              │  │  (empty)                      │ │
│  └──────────────┘  └──────────────────────────────┘ │
│  ──────────────────────────────────────────────────  │
│  📋 Ingestion Log                                   │
└─────────────────────────────────────────────────────┘
```

**Step 2 — Upload Individual Files**

Click **Upload Files** and select one or more files. Supported formats include:
- **Documents:** PDF, Word (.doc/.docx), text, RTF
- **Images:** JPG, PNG, GIF, WebP, BMP, SVG
- **Audio:** MP3, WAV, OGG, FLAC, AAC, M4A
- **Video:** MP4, WebM, MOV, AVI, MKV
- **Data:** CSV, Excel, JSON

Files appear in the **Unprocessed Files** section after upload.

**Step 3 — Upload a Folder**

Click **Upload Folder** to upload an entire directory. This preserves the folder structure, which is important for wiretap processing workflows. Large folder uploads run as background tasks — you can continue working while they upload.

**Step 4 — Browse with the File Navigator**

The **File Navigator** on the left shows your case's file tree. Navigate folders by clicking to expand them. Look for these indicators:

- 📻 **Green radio icon** — Wiretap-processed folder
- ✅ **Checkmark** — Processed file

Click the **ℹ️** icon on any file or folder to see detailed metadata in the File Info panel.

**Step 5 — Understand File Status**

Each file has a processing status:
- **Unprocessed** — Uploaded but not yet analysed by the LLM
- **Processing** — Currently being analysed
- **Processed** — LLM analysis complete, entities extracted to graph
- **Failed** — Processing encountered an error

If you upload the same file twice, you'll see a **×2** badge next to it indicating how many copies exist in the system.

---

## 3. Processing Evidence with the LLM

### What you'll learn
How to run LLM analysis on your evidence files to extract entities and relationships into the knowledge graph. This is where images, audio, and video become part of your investigation — they're converted to text first, then entities are extracted just like from documents.

### Steps

**Step 1 — Select Files to Process**

In the Unprocessed Files section, use the checkboxes to select files. You can:

- **Select All** — Click the "Select All" button to select everything
- **Select individually** — Click checkboxes on specific files
- **Filter by type** — Use the type pills (Image, Document, Audio, etc.) to narrow the list

**Step 2 — Choose a Processing Profile**

At the top of the Evidence Processing view, select a **Processing Profile** from the dropdown. Profiles control how the LLM analyses documents:

- **generic** — General-purpose entity extraction
- **fraud** — Optimised for financial fraud investigations
- Custom profiles you've created

**Step 3 — Start Processing**

Click **Process Selected**. Processing runs in the background — you can:

- Watch the **Ingestion Log** at the bottom for real-time progress
- Check the **Background Tasks** panel (briefcase icon) for task status
- Continue working on other parts of the case

**Step 4 — What Happens During Processing**

The LLM processes each file type differently, but all paths end with entity extraction:

| File Type | Processing Steps |
|-----------|-----------------|
| **PDF / Word / Text** | Text extraction → chunking → entity extraction → graph |
| **Images** | OCR or GPT-4 Vision analysis → text → entity extraction → graph |
| **Audio** | Whisper transcription → text → entity extraction → graph |
| **Video** | Audio extraction + transcription + frame analysis → text → entity extraction → graph |

Every entity extracted links back to its source document. This means if an entity was found in an audio recording, you can click through to listen to the original audio.

**Step 5 — Verify Processing**

Processed files move to the **LLM Processed Files** section. The graph view now shows the entities and relationships extracted from your evidence.

---

## 4. Working with the Knowledge Graph

### What you'll learn
How to navigate, search, filter, and interact with the knowledge graph that the LLM builds from your evidence.

### Steps

**Step 1 — View the Graph**

From the Workspace, the centre panel shows the interactive knowledge graph. Entities appear as coloured nodes, relationships as connecting lines.

```
┌─────────────────────────────────────────┐
│        🔴 Person: John Smith            │
│           /          \                  │
│    🟡 Company:    🔵 Account:           │
│    Acme Corp      CH-12345              │
│        \           /                    │
│     🟢 Transaction:                     │
│     $50,000 wire                        │
└─────────────────────────────────────────┘
```

Each node colour represents an entity type (Person, Company, Account, Transaction, etc.). The **Entity Legend** at the bottom shows the colour mapping.

**Step 2 — Navigate the Graph**

| Action | How |
|--------|-----|
| **Select a node** | Click on it |
| **Select multiple nodes** | Hold `Ctrl/Cmd` and click each |
| **Drag-select** | Switch to drag mode (crosshair icon), drag a rectangle |
| **Zoom in/out** | Mouse wheel |
| **Pan** | Click and drag the background |
| **Centre view** | Click the centre button (crosshair icon) |

**Step 3 — Search & Filter**

The search bar at the top of the graph supports two modes:

- **Filter Mode** (default): Nodes that match remain visible; non-matches fade. Results update as you type.
- **Search Mode**: Manually click "Search" to find matches.

**Advanced query syntax:**
- `john AND smith` — Both terms must match
- `bank OR financial` — Either term matches
- `NOT closed` — Exclude matches
- `smith*` — Wildcard: starts with "smith"
- `~john` — Fuzzy match: similar to "john"

**Step 4 — Expand Relationships**

To see what connects to a specific entity:

1. **Right-click** the node
2. Select **Expand** from the context menu
3. Choose the number of hops (1–5) — how many relationship steps to follow
4. New connected nodes appear in the graph

You can also double-click a node to expand its immediate connections.

**Step 5 — Use the Spotlight Graph**

The **Spotlight Graph** lets you build a focused subgraph:

1. Select one or more nodes
2. Right-click → **Add to Spotlight Graph**
3. A split panel appears showing only your selected nodes and their connections
4. Add more nodes as you investigate
5. Use the spotlight graph to isolate specific relationship chains

**Step 6 — Switch View Modes**

Use the view mode switcher to see your data differently:

- 🔗 **Graph** — Force-directed network visualization
- 📊 **Table** — Tabular view with expandable relationship panels
- 📅 **Timeline** — Events arranged chronologically
- 🗺️ **Map** — Geographic visualization (when location data exists)
- 💰 **Financial** — Transaction analysis view

---

## 5. Investigating Entities — Facts, Insights & Source Documents

### What you'll learn
How to examine entity details, verify AI insights, pin important facts, and view source documents for any file type (PDF, image, audio, video).

### Steps

**Step 1 — Open Entity Details**

Click any node in the graph. The **Node Details** panel appears on the right showing:

- **Entity name and type** (e.g., "John Smith — Person")
- **Summary** — AI-generated summary of the entity
- **Verified Facts** — Confirmed pieces of information
- **AI Insights** — Unverified observations the LLM identified

**Step 2 — View Source Documents**

Every fact and insight has a source citation. Click the **source document link** (blue text with file icon) to preview the original document:

```
✅ John Smith transferred $50,000 to Account CH-12345 on March 15
   📎 bank_statement_march.pdf, p.3
```

The **Document Viewer** opens as a modal and supports all file types:

| Source Type | What You See |
|-------------|-------------|
| **PDF** | Full PDF viewer with page navigation |
| **Image** | Image viewer (photos, scanned documents, screenshots) |
| **Audio** | Audio player with playback controls |
| **Video** | Video player with playback controls |
| **Text** | Formatted text content |

This means if the LLM extracted an entity from a phone recording, you can click through and listen to the exact source.

**Step 3 — Verify AI Insights**

AI Insights are observations the LLM made but hasn't confirmed. Each shows a **confidence level** (High, Medium, Low).

To verify an insight:
1. Click **Mark as Verified** on the insight
2. Optionally add the source document and page number
3. The insight converts to a **Verified Fact** and gains higher trust

**Step 4 — Pin Important Facts**

Click the **star icon** next to any verified fact to pin it. Pinned facts appear in the **Pinned Evidence** section of your workspace and are highlighted in exports.

**Step 5 — View Relationships**

Scroll down in the Node Details panel to see the entity's relationships. Click any related entity to navigate to it in the graph.

---

## 6. Building Investigation Theories

### What you'll learn
How to create theories, attach evidence, and use the AI to find entities that support your theory.

### Steps

**Step 1 — Create a Theory**

In the Workspace, open the **Theories** section in the left sidebar. Click the **+** button.

Fill in the Theory Editor:
- **Title** — Name your theory (e.g., "Smith was laundering funds through Acme Corp")
- **Type** — Primary, Secondary, or Note
- **Hypothesis** — Describe your theory in detail
- **Confidence Score** — Rate your confidence (0–100%)
- **Supporting Evidence** — List evidence points
- **Counter Arguments** — Note weaknesses
- **Next Steps** — Planned investigation actions
- **Privilege Level** — Public, Attorney Only, or Private

Click **Save**.

**Step 2 — Attach Items to the Theory**

Your theory can link to evidence, witnesses, notes, tasks, and snapshots:

1. Click the **link icon** (🔗) on the theory card
2. The **Attached Items** modal opens
3. Browse available items and click **Attach** to link them
4. Attached items appear grouped by type

You can also attach items from other sections — look for the **Attach to Theory** button (link icon) on files, witnesses, notes, and tasks.

**Step 3 — Build a Theory Graph**

This is a powerful AI feature. Click the **network icon** (🔗) on your theory card:

1. The Build Theory Graph modal appears
2. Choose whether to use **theory text only** or **include attached items**
3. Click **Build Graph**
4. The AI searches the knowledge graph for entities semantically related to your theory
5. The graph view updates to highlight these relevant entities

This helps you discover connections you might have missed.

**Step 4 — Mark Linked Files as Relevant**

Click the **star icon** (⭐) on the theory card to mark all files attached to the theory as **Relevant**. This systematically classifies evidence that supports your investigation.

---

## 7. Marking Evidence as Relevant

### What you'll learn
How to classify evidence files as relevant or non-relevant to organise your investigation.

### Context

When files are first uploaded, they are all marked as **Non-Relevant** by default. As you investigate and identify which files support your theories, you mark them as **Relevant**. This creates a clear distinction between files that matter and background noise.

### Steps

**Step 1 — Open Case Files**

In the Workspace, open the **Case Files** section. You'll see three tabs:

```
┌───────────────┬──────────────┬─────────────────┐
│ ⊞ All Files   │ ★ Relevant   │ ☆ Non-Relevant  │
│     (47)      │    (12)      │      (35)       │
└───────────────┴──────────────┴─────────────────┘
```

**Step 2 — Mark Files Individually**

Each file row has a **star icon** on the right side:

- **☆ Empty star** — File is non-relevant (click to mark as relevant)
- **★ Filled star** (amber) — File is relevant (click to remove relevance)

The change takes effect immediately. A "Relevant" badge appears on the file.

**Step 3 — Bulk Mark from a Theory**

For a faster workflow, use the theory-based bulk marking:

1. Go to **Theories** section
2. Find your theory with attached evidence
3. Click the **⭐ star button** on the theory card
4. All files linked to the theory are marked as relevant
5. A confirmation tells you how many files were marked

**Step 4 — Filter by Relevance**

Use the tabs to quickly focus:
- **All Files** — Everything in the case
- **Relevant** — Only files you've flagged as important
- **Non-Relevant** — Files not yet flagged

Within each tab, you can further filter by **Processed** or **Unprocessed** status.

**Step 5 — Spot Duplicates**

Files that have been uploaded more than once show a **×N** badge (e.g., "×2" means two copies exist). This helps you identify redundant uploads without cluttering a separate section.

---

## 8. Finding & Merging Duplicate Entities

### What you'll learn
How to use the AI to scan for similar entities in your graph and merge duplicates to keep your investigation clean.

### Why this matters

When processing many documents, the LLM may create separate entities for the same real-world person or company (e.g., "John Smith", "J. Smith", "Smith, John"). Merging these gives you a complete picture.

### Steps

**Step 1 — Launch Similar Entity Scan**

In the graph view, click the **Find Similar Entities** button in the toolbar (magnifying glass with double arrows).

**Step 2 — Configure the Scan**

A dialog appears:
- Select which **entity types** to scan (Person, Company, etc.)
- Set the **similarity threshold** (lower = more matches, higher = stricter)
- Click **Start Scan**

**Step 3 — Review Results**

A progress dialog shows the scan running. When complete, results show pairs of similar entities with similarity scores:

```
┌─────────────────────────────────────────────┐
│  Similar Entities Found: 8 pairs            │
│  ───────────────────────────────────────     │
│  "John Smith" ↔ "J. Smith"        95%       │
│  "Acme Corp" ↔ "Acme Corporation" 87%       │
│  "First Bank" ↔ "1st Bank Ltd"    72%       │
│  ...                                        │
└─────────────────────────────────────────────┘
```

**Step 4 — Compare and Merge**

Click any pair to open the **Entity Comparison** modal:

1. Side-by-side view shows both entities with their facts, insights, and relationships
2. Review the details to confirm they're the same entity
3. Click **Merge** to combine them:
   - Choose which name to keep
   - Select which facts and insights to include
   - All relationships migrate to the surviving entity
4. Or click **Reject** if they're genuinely different entities

**Step 5 — Manual Merge**

You can also merge entities manually:
1. Select two or more nodes in the graph (Ctrl/Cmd+Click)
2. Right-click → **Merge Selected Entities**
3. Follow the same merge workflow

---

## 9. Using the Investigation Workspace

### What you'll learn
How to use the workspace's many investigation tools: witnesses, tasks, deadlines, notes, timeline, and the case overview.

### The Workspace Layout

```
┌──────────────┬────────────────────────┬──────────────┐
│  Case        │                        │  Node        │
│  Context     │    Graph / Table /     │  Details     │
│  Panel       │    Timeline / Map /    │  Panel       │
│  (left)      │    Financial View      │  (right)     │
│              │    (centre)            │              │
│  • Overview  │                        │  • Facts     │
│  • Quick     │                        │  • Insights  │
│    Actions   │                        │  • Relations │
│  • Theories  │                        │              │
│  • Witnesses │                        │              │
│  • Tasks     │                        │              │
│  • Deadlines │                        │              │
│  • Notes     │                        │              │
│  • Files     │                        │              │
│  • Timeline  │                        │              │
│  • Snapshots │                        │              │
│  • Audit Log │                        │              │
└──────────────┴────────────────────────┴──────────────┘
```

### Quick Actions — Add Evidence on the Fly

At the top of the left panel, three quick action buttons let you add evidence without leaving the workspace:

- 📸 **Photo** — Upload a photo directly from your device
- 📝 **Note** — Create an investigative note with tags
- 🔗 **Link** — Save a URL with title and description

These are handy for capturing information during live investigation sessions.

### Witnesses

1. Click **Witnesses** in the left sidebar
2. Click **+** to add a witness
3. Fill in: name, role, contact info, risk assessment, strategy notes
4. Add **interviews** — record interview date, summary, and notes
5. Attach witnesses to theories to track which witnesses support which theory

### Tasks

1. Click **Tasks** in the left sidebar
2. Click **+** to create a task
3. Set: title, description, assignee, due date, priority
4. Mark tasks as **Complete** when done
5. View pending vs. completed tasks

### Deadlines

1. Click **Deadlines** in the left sidebar
2. Add court dates, filing deadlines, and other time-sensitive dates
3. Set the **trial date** to anchor your timeline

### Investigative Notes

1. Click **Notes** in the left sidebar
2. Click **+** to add a note
3. Write your note and add **tags** for categorisation
4. Notes are timestamped and can be attached to theories

### Entity Summaries

The **Key Entities** section shows a summarised view of all entities grouped by type. Click any entity to navigate to it in the graph. Click to **expand** an entity summary to read the full AI-generated description.

### Case Overview

Click **Case Overview** at the top of the left panel for a horizontal dashboard showing all sections at a glance. Each section card can be toggled for export. This is useful for getting a bird's-eye view before a meeting or report.

### Investigation Timeline

The **Timeline** section shows all investigation events arranged chronologically across threads:

- **Witnesses** (blue) — When witnesses were added, interviewed
- **Tasks** (green) — Task creation, completion, due dates
- **Theories** (yellow) — When theories were created or updated
- **Evidence** (orange) — File upload and processing dates
- **Deadlines** (red) — Court dates and filing deadlines
- **Snapshots** (purple) — When investigation states were saved

Use the zoom controls to focus on specific date ranges.

---

## 10. Saving & Comparing Snapshots

### What you'll learn
How to save the state of your investigation at key points and compare how it has evolved.

### Steps

**Step 1 — Save a Snapshot**

At any point during your investigation, click the **camera icon** in the toolbar or go to **Snapshots** in the workspace sidebar.

1. Click **Save Snapshot**
2. Give it a name (e.g., "Pre-interview state", "After financial analysis")
3. Add notes describing what this snapshot captures
4. Click **Save**

The snapshot captures: the graph state, selected nodes, node positions, chat history, and table configuration.

**Step 2 — Load a Previous Snapshot**

1. Open the **Snapshots** section
2. Each snapshot shows: name, date, node/link counts
3. Click **Load** on any snapshot
4. A progress dialog shows while the state restores
5. Your graph and workspace return to that exact point in time

**Step 3 — Compare Two Snapshots**

1. In the Snapshots section, select two snapshots
2. Click **Compare**
3. A side-by-side view highlights:
   - New entities added
   - Entities removed
   - Changed relationships
   - Modified properties

This is valuable for tracking investigation progress over time.

**Step 4 — Export a Snapshot to PDF**

Click **Export PDF** on any snapshot to generate a PDF report containing the graph visualization and entity details at that point in time.

---

## 11. Financial Transaction Analysis

### What you'll learn
How to use the financial view to analyse transactions, identify patterns, and group related transactions.

### Steps

**Step 1 — Switch to Financial View**

In the view mode switcher, select **Financial** (💰 icon). The financial view shows:

- **Summary cards** — Key metrics (total transactions, amounts, date ranges)
- **Transaction table** — All financial entities in tabular form
- **Charts** — Visual breakdowns by category

**Step 2 — Filter Transactions**

Use the category filter pills at the top to focus on specific transaction types. You can also:
- Sort by any column (amount, date, counterparty)
- Search by text in the filter bar

**Step 3 — Group Sub-Transactions**

When you identify transactions that belong together (e.g., a series of payments that form part of a larger scheme):

1. Find the **parent transaction** in the table
2. Click the **⋯ actions menu** on that row
3. Select **Group as Sub-Transaction**
4. A modal opens — search and select the child transactions
5. Click **Group**

The parent row now shows an **expand arrow**. Click it to reveal the sub-transactions nested underneath.

**Step 4 — Edit Transaction Details**

Click into any transaction to edit:
- **Purpose** — What the transaction was for
- **Counterparty** — Who was involved
- **Notes** — Your analysis or findings

---

## 12. Wiretap Folder Processing

### What you'll learn
How to process structured wiretap folders containing audio, metadata, and interpretation files.

### Context

Wiretap data typically comes in folders containing:
- Audio recordings (.mp3, .wav)
- Metadata files (.sri)
- Interpretation documents (.rtf)

OWL can process these as a unit, extracting transcriptions, translations, and entities.

### Steps

**Step 1 — Upload Wiretap Folders**

Use **Upload Folder** in the Evidence Processing view. Select the parent folder containing your wiretap call folders. The folder structure is preserved.

**Step 2 — Navigate to a Wiretap Folder**

In the **File Navigator**, browse to a wiretap folder. The system automatically detects if a folder contains wiretap-suitable files.

**Step 3 — Create a Processing Profile (First Time)**

Click the **ℹ️** icon on the folder. In the File Info panel:

1. Click **Create Custom Profile**
2. The **Folder Profile Modal** opens showing all files in the folder
3. Choose **Instructions mode** and describe how to process the folder in plain language, or
4. Configure manually:
   - Assign file roles (audio, metadata, interpretation, ignore)
   - Set transcription language
   - Set translation language
   - Configure LLM settings
5. Click **Test Profile** to preview results
6. Click **Save Profile** when satisfied

**Step 4 — Process the Folder**

1. Select the folder(s) in the File Navigator
2. Choose your profile from the dropdown
3. Click **Process as Wiretap** (or **Process All Folders** for batch)
4. Processing runs as a background task

**Step 5 — Monitor Progress**

Click the **Background Tasks** panel to watch progress. Processing involves:
1. Audio transcription (Whisper)
2. Metadata extraction
3. Interpretation parsing
4. Entity extraction
5. Graph integration

Completed wiretap folders show a **green radio icon** (📻) in the File Navigator.

---

## 13. Using the AI Chat Assistant

### What you'll learn
How to ask the AI questions about your case and get answers grounded in your evidence.

### Steps

**Step 1 — Open the Chat Panel**

Click the **chat icon** in the right sidebar to open the Chat Assistant.

**Step 2 — Choose a Context Mode**

The context mode controls what information the AI has access to:

| Mode | What the AI Sees |
|------|-----------------|
| **Full Graph** | All entities and relationships in the case |
| **Selected Nodes** | Only the entities you've selected in the graph |
| **Spotlight Graph** | Only entities in your spotlight/subgraph |
| **No Context** | General knowledge only (no case data) |

**Step 3 — Ask Questions**

Type your question and press Enter. Examples:

- "What is the relationship between John Smith and Acme Corp?"
- "Summarise all financial transactions over $10,000"
- "What evidence links the suspect to the offshore accounts?"
- "What are the key facts about witness Maria Rodriguez?"

**Step 4 — Review Answers with Citations**

The AI's response includes **citations** linking back to source documents. Click any citation to open the **Document Viewer** and see the original evidence.

**Step 5 — Use Debug Mode**

Toggle **Debug** to see the RAG (Retrieval-Augmented Generation) pipeline trace — which documents were retrieved, how they were ranked, and what context was provided to the LLM. This helps you understand the AI's reasoning.

---

## 14. Exporting & Reporting

### What you'll learn
How to export your investigation findings for reports, court filings, or team briefings.

### Export Options

**Case Overview Export**

1. Go to **Case Overview** in the workspace
2. Each section card has an **Include in export** checkbox
3. Select the sections you want
4. Click **Export Case**
5. A PDF is generated with all selected sections

**Snapshot PDF Export**

1. Go to **Snapshots** in the workspace
2. Click **Export PDF** on any snapshot
3. A PDF is generated showing the graph state and entity details at that point

**Theory Export**

1. Go to **Theories** in the workspace
2. Open the **Attached Items** modal on a theory
3. Click **Export**
4. An HTML report is generated with the theory and all attached evidence

---

## 15. Backfilling Summaries & Embeddings

### What you'll learn
How to generate missing AI summaries and embeddings for documents that were uploaded before these features were added. This is an admin-level workflow.

### When to use this

If you notice that some documents or entities are missing summaries, or that the AI chat isn't finding relevant documents, you may need to backfill.

### Steps

**Step 1 — Open the Database Modal**

From the settings or admin area, click **Database**. The Database Modal opens.

**Step 2 — Run Gap Analysis**

Click the **RAG Pipeline** tab. This shows cards indicating what's missing:

```
┌─────────────────────────┬─────────────────────────┐
│  Missing Embeddings     │  Missing Summaries      │
│  ───────────────        │  ───────────────        │
│  47 chunks need         │  12 documents need      │
│  embeddings             │  summaries              │
│                         │                         │
│  [Backfill Embeddings]  │  [Backfill Summaries]   │
└─────────────────────────┴─────────────────────────┘
```

**Step 3 — Run Backfill Operations**

Click the appropriate button:

- **Backfill Chunk Embeddings** — Generates vector embeddings for document chunks (needed for semantic search and RAG)
- **Backfill Document Summaries** — Generates AI summaries for documents (uses LLM, takes longer)
- **Backfill Entity Metadata** — Adds case_id to entities that are missing it
- **Backfill Case IDs** — Assigns case ownership across Neo4j and ChromaDB

Monitor progress below each button. Embedding backfill is fast; summary backfill is slower as it calls the LLM.

---

## 16. Administration & User Management

### What you'll learn
How to manage users, monitor system activity, and maintain the platform.

### Creating Users

1. From the admin area, click **Create User**
2. Fill in: username, email, password, role (admin, investigator, viewer)
3. Click **Create**

### System Logs

The **System Logs** panel shows all platform activity:
- User logins and actions
- Evidence uploads and processing
- Entity modifications
- Case operations

Filter by user, action type, or date range.

### Case Audit Log

Within each case's workspace, the **Audit Log** section shows case-specific activity — who did what and when.

---

## Workflow Cheat Sheet

Here's a quick reference for common investigation workflows:

### New Case Setup
`Create Case → Upload Evidence → Process with LLM → Explore Graph → Save Snapshot`

### Daily Investigation
`Load Case → Review Graph → Investigate Entities → Verify Insights → Pin Facts → Save Snapshot`

### Building a Theory
`Create Theory → Attach Evidence → Build Theory Graph → Review Entities → Mark Files Relevant → Export`

### Data Cleanup
`Find Similar Entities → Compare Pairs → Merge Duplicates → Backfill Summaries`

### Preparing for Court
`Review Relevant Files → Export Case Overview → Export Theory Reports → Export Snapshot PDFs`

### Wiretap Processing
`Upload Folders → Create Profile → Process Wiretaps → Review Transcriptions → Explore Entities in Graph`

---

## Tips & Best Practices

1. **Save snapshots often** — Before and after major analysis steps. They're your investigation's version history.

2. **Use theories as organisational anchors** — Attach all related evidence, witnesses, and notes to a theory. Then use "Build Theory Graph" to discover connections you might have missed.

3. **Verify AI insights promptly** — The LLM makes observations but doesn't confirm them. Verified facts carry more weight in exports.

4. **Mark relevant files early** — This makes it much easier to find important evidence later, especially in cases with hundreds of files.

5. **Use the spotlight graph** — When investigating a specific chain (e.g., money flow), add those entities to the spotlight graph to see them in isolation.

6. **Check for duplicates after batch uploads** — Run "Find Similar Entities" after processing large evidence batches to keep your graph clean.

7. **Use context modes in chat** — "Selected Nodes" context focuses the AI on exactly what you're looking at. "Full Graph" gives the broadest answers.

8. **Name your snapshots descriptively** — "Before merging entities" is much more useful than "Snapshot 4".

9. **Explore the table view** — The table view with its expanding relationship panels is often faster for systematic review than the graph.

10. **Run backfill after updates** — After a platform update, check the Database Modal for any gaps that need backfilling.
