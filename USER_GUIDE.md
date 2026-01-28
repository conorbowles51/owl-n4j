# Owl Investigation Platform - User Guide

**Version:** 3.0  
**Last Updated:** January 2026

## Table of Contents

1. [Getting Started](#getting-started)
2. [Case Management](#case-management)
3. [Workspace View](#workspace-view)
4. [Case Overview](#case-overview)
5. [Evidence Processing](#evidence-processing)
6. [LLM Profile Management](#llm-profile-management)
7. [Graph View](#graph-view)
8. [Table View](#table-view)
9. [Timeline View](#timeline-view)
10. [Map View](#map-view)
11. [Graph Analysis Tools](#graph-analysis-tools)
12. [Entity Management](#entity-management)
13. [AI Assistant](#ai-assistant)
14. [Theories and Reports](#theories-and-reports)
15. [Snapshots](#snapshots)
16. [File Management](#file-management)
17. [Background Tasks](#background-tasks)
18. [Case Backup and Restore](#case-backup-and-restore)
19. [Cost Analysis](#cost-analysis)

---

## Getting Started

### Login

1. When you first access the platform, you'll see the login screen with the Owl Consultancy Group logo.
2. Enter your username and password.
3. Default users available:
   - `admin` / `owlinvestigates`
   - `neil` / `owlinvestigates`
   - `conor` / `owlinvestigates`
   - `alex` / `owlinvestigates`
   - `arturo` / `owlinvestigates`
4. Click **Login** to access the platform.
5. After login, you'll be taken to the **Case Management** view.

### Logout

- Click on the **Owl logo** in the top left corner of any view.
- Select **Logout** from the dropdown menu.

### Documentation

- Click on the **Owl logo** in the top left corner of any view.
- Select **Documentation** from the dropdown menu to view this user guide.

#### Searching Documentation

The documentation viewer includes a powerful search feature:

1. **Search Bar**: Located at the top of the documentation viewer, below the header
2. **Real-time Search**: As you type, the system searches through all documentation content
3. **Result Highlighting**: All matching terms are highlighted in yellow
4. **Navigation Controls**: 
   - Use the **Previous** (↑) and **Next** (↓) buttons to jump between results
   - The counter shows "X / Y" where X is the current result and Y is the total number of matches
5. **Keyboard Shortcuts**:
   - **Enter**: Jump to next search result (when search input is focused)
   - **Shift+Enter**: Jump to previous search result
6. **Clear Search**: Click the X button in the search input to clear the search and remove highlights
7. **Auto-scroll**: When navigating results, the document automatically scrolls to show the current match

---

## Case Management

The Case Management view is your starting point for organizing investigations.

### Viewing Cases

- After login, you'll see a list of your cases on the left side.
- The header shows "[Your Name]'s Cases" (e.g., "Neil's Cases").
- Click on any case to view its details in the right panel.

### Case Details

When you select a case, you'll see:

- **Case Information**: Name, creation date, update date, and version count
- **Evidence Files**: List of uploaded and processed files (collapsible section)
- **Processing History**: Logs showing file processing activity (collapsible section)
- **Versions**: All saved versions of the case (collapsible section, most recent first)
- **Cypher Queries**: The database queries used to recreate the graph
- **Snapshots**: Saved snapshots associated with each version (collapsible section)

### Collapsible Sections

All major sections in the case details can be collapsed or expanded:

- Click the section header to toggle visibility
- **Evidence Files** and **Processing History** sections are expanded by default
- **Versions** section is expanded by default
- Use the chevron icon to see the current state (down = expanded, right = collapsed)

### Filtering and Pagination

#### Evidence Files Filtering

- **Text Filter**: Enter text in the filter box to search by filename
- **File Type Pills**: Click file type pills (e.g., "pdf", "txt", "docx") to filter by file extension
  - Selected file types are highlighted in blue
  - Click multiple pills to filter by multiple types
  - Click "Clear" to remove all file type filters
- **Pagination**: Lists with more than 10 files show pagination controls
  - Use "Previous" and "Next" buttons to navigate
  - Page indicator shows current page and total count

#### Versions Filtering

- **Text Filter**: Enter text to search by version number or notes
- **Pagination**: Lists with more than 10 versions show pagination controls
- **Default State**: Only the latest version is expanded by default
  - Older versions are collapsed but still show their notes
  - Click "Expand" on any version to see full details
  - Click "Collapse" to hide details again

#### Snapshots Filtering

- **Text Filter**: Enter text to search by snapshot name or notes
- **Pagination**: Lists with more than 10 snapshots show pagination controls
- **Default State**: Only the latest snapshot of each version is expanded by default
  - Older snapshots are collapsed
  - Click "Expand" on any snapshot to see full details

### Version Display

- **Sorting**: Versions are automatically sorted by version number (most recent first)
- **Notes Visibility**: Version notes are always visible, even when collapsed
- **Details Visibility**: Full details (snapshot count, Cypher count) are only shown when expanded
- **Latest Badge**: The most recent version shows a "Latest" badge

### Creating a New Case

1. Click the **Create New Case** button in the header.
2. Enter a case name.
3. (Optional) Add save notes.
4. Click **Save**.
5. You'll be taken to the **Evidence Processing** screen for the new case.

### Loading a Case

1. Select a case from the list.
2. Choose a version (latest is shown first, older versions are in a collapsible list).
3. Click **Load Version** to load the case into the workspace view.

### Opening Case in Workspace

- Click **Open in Workspace** to open the case in the full workspace view with all investigation tools.

### Deleting a Case

1. Click the **trash icon** on any case in the list.
2. Confirm the deletion (this will delete all versions of the case).

---

## Workspace View

The Workspace View is the main investigation interface where you work with your case data. It provides a comprehensive view of all case information and investigation tools.

### Accessing Workspace View

1. From **Case Management**, select a case and click **Open in Workspace**.
2. Or, after loading a case version, you'll automatically enter the workspace.

### Workspace Layout

The workspace is organized into several key areas:

- **Case Header Bar**: Shows case name, client information, and key actions at the top
- **Case Context Panel**: Left sidebar with case information, client profile, and quick actions
- **Main Investigation Area**: Center panel showing graph, timeline, map, or table views
- **Investigation Panel**: Right sidebar with theories, evidence, notes, tasks, and other case materials
- **Activity Timeline**: Bottom panel showing recent case activity

### Navigation Tabs

The main investigation area has several tabs:

- **Graph**: Visual network diagram of entities and relationships
- **Timeline**: Chronological view of events
- **Map**: Geographic visualization of locations
- **Table**: Spreadsheet-style view of all entities
- **Case Overview**: Comprehensive dashboard of all case information

### Case Context Panel

The left sidebar provides quick access to:

- **Client Profile**: Client name, case type, trial date, and other key information
- **Quick Actions**: Common tasks like adding notes, creating tasks, or pinning evidence
- **Case Information**: Case metadata and statistics

### Investigation Panel

The right sidebar contains:

- **Theories**: Investigation theories and hypotheses
- **Evidence**: All case evidence files
- **Witnesses**: Witness information and interviews
- **Notes**: Investigative notes
- **Tasks**: Investigation tasks and to-dos
- **Deadlines**: Important case deadlines
- **Documents**: Case documents
- **Snapshots**: Saved investigation states
- **Audit Log**: System activity log

### Switching Between Views

- Click the tabs at the top of the main investigation area to switch between Graph, Timeline, Map, Table, and Case Overview
- Each view maintains your current selection and filters
- The workspace remembers your preferences as you switch views

---

## Case Overview

The Case Overview provides a comprehensive dashboard view of all case information in one place. It's perfect for getting a complete picture of your investigation at a glance.

### Accessing Case Overview

1. In the **Workspace View**, click the **Case Overview** tab at the top of the main investigation area.
2. The overview displays all case sections side-by-side in a horizontal scrollable layout.

### Overview Sections

The Case Overview displays the following sections as cards that you can scroll through horizontally:

#### Client Profile
- Client name and case type
- Trial date and other key dates
- Case metadata

#### Theories
- List of all investigation theories
- Theory titles and hypotheses
- Quick access to theory details

#### Pinned Evidence
- Evidence items you've marked as important
- Quick reference to key documents

#### Witnesses
- All witnesses in the case
- Interview summaries
- Witness credibility ratings

#### Deadlines
- Important case deadlines
- Upcoming dates
- Deadline status

#### Investigative Notes
- All case notes
- Organized chronologically
- Searchable content

#### Tasks
- Investigation tasks
- Task status and assignments
- Priority items

#### All Evidence
- Complete list of all evidence files
- File types and processing status
- Quick access to evidence details

#### Documents
- Case documents
- Document summaries
- File previews

#### Graph Visualization
- Visual network diagram
- Interactive graph view
- Entity relationships

#### Timeline Visualization
- Chronological event timeline
- Date-based organization
- Event connections

#### Map Visualization
- Geographic locations
- Location markers
- Geographic relationships

#### Snapshots
- Saved investigation states
- Snapshot summaries
- Quick access to saved views

#### Audit Log
- System activity log
- User actions
- Case changes

### Including Sections in Export

Each section card has a checkbox at the top:

- **Checkbox**: Use the checkbox to include or exclude that section from case reports
- **Default**: All sections are included by default
- **Custom Selection**: Uncheck sections you don't want in your reports

### Exporting Case Reports

1. Click the **Export Case** button in the toolbar at the top of the Case Overview.
2. The export modal opens showing:
   - **Sections Tab**: List of all sections with inclusion status
   - **Graph Tab**: Preview of graph visualization
   - **Graph Timeline Tab**: Preview of timeline visualization
   - **Graph Map Tab**: Preview of map visualization
   - **Timeline Tab**: Preview of investigation timeline
3. Review which sections are included (based on your checkbox selections).
4. Click **Export** to generate the report.
5. A progress bar shows the export generation progress.
6. The report downloads as an HTML file containing:
   - All selected sections with full details
   - Visual representations (graphs, timelines, maps)
   - Witness interviews with complete information
   - Audio transcriptions and translations (if available)
   - All evidence, notes, tasks, and other case materials

### Scrolling Through Overview

- **Horizontal Scroll**: Scroll left and right to see all sections
- **Vertical Scroll**: Each section card can scroll vertically if content is long
- **Fixed Toolbar**: The export toolbar stays fixed at the top while you scroll

---

## Evidence Processing

The Evidence Processing view allows you to upload and process documents for your case.

### Uploading Files

1. Click the **Choose files** area or drag and drop files.
2. Supported formats: PDF, TXT, Word documents (.docx), Excel files (.xlsx, .xls), CSV files, and other document types.
3. Files are uploaded immediately and appear in the **Unprocessed Files** list.

### Processing Files

#### Single File Processing

1. Select one or more files from either list (unprocessed or processed).
2. Click **Process Selected Files**.
3. A progress bar shows processing status.
4. Logs appear in real-time showing the ingestion progress.
5. Once complete, files move to the **Processed & Duplicate Files** list.

#### Multiple File Processing (Background)

1. Select multiple files (2 or more).
2. Click **Process Selected Files**.
3. Files are processed in the background, allowing you to continue working.
4. Click the **Background Tasks** icon in the header to monitor progress.
5. When complete, click **View in Case** on the completed task to see results.

### File Status

- **Unprocessed**: Files waiting to be processed
- **Processed**: Files that have been successfully ingested
- **Duplicate**: Files with the same content (identified by hash)
- **Failed**: Files that encountered errors during processing

### Opening Case in Workspace

- Click **Open Case in Workspace** to load the processed case into the workspace view.
- If data exists for the case, it will be loaded. Otherwise, an empty workspace will be shown.

### Loading Processed Graph

- After processing completes, a **Load Processed Graph** button appears.
- Click it to load the newly generated graph immediately.

### LLM Profile Selection

Before processing files, you can select an LLM profile that determines how the AI processes your documents:

1. **Select Profile**: Use the **LLM Profile** dropdown at the top of the Evidence Processing view.
2. **Profile Details**: When you select a profile, its description appears below the dropdown.
3. **Profile Information**: Each profile shows:
   - Case type
   - Agent description
   - Instructions for the AI
   - Characteristics
   - Entity types and colors
   - Relationship examples

The selected profile guides the AI in:
- What entities to look for
- How to identify relationships
- What to prioritize in the analysis
- The creativity level (temperature) of responses

### Folder Upload and Processing

You can upload entire folders of documents for processing:

1. **Upload Folder**: Use folder upload to preserve folder structure
2. **Folder Profiles**: Configure how different folder types are processed
3. **Automatic Detection**: The system automatically detects folder types (e.g., wiretap folders)
4. **Batch Processing**: Process entire folders in the background

### Wiretap Audio Processing

The platform supports processing wiretap audio recordings with automatic transcription and translation.

#### Understanding Wiretap Folders

Wiretap folders contain:
- **Audio files**: `.wav`, `.mp3`, `.m4a`, or `.flac` files containing recorded conversations
- **Metadata files**: `.sri` files with call information (time, contact IDs, session length)
- **Interpretation files**: `.rtf` files with prosecutor interpretations/notes

#### Uploading Wiretap Folders

1. In the **Evidence Processing** view, use the **File Navigator** to browse your case's file system
2. Navigate to folders containing wiretap audio files
3. Folders suitable for wiretap processing are automatically detected and marked
4. You can upload wiretap folders using the standard file upload (folder upload preserves structure)

#### Identifying Wiretap Folders

The system automatically checks folders for wiretap suitability:
- **Suitable folders** show a "Wiretap Processing" indicator in the File Info panel
- The indicator shows:
  - Whether the folder is suitable for processing
  - Whether it has been processed before
  - File statistics (total files, processed count, unprocessed count)
  - Available file types in the folder

#### Processing Wiretap Folders

1. **Select a Wiretap Folder**:
   - Click on a folder in the File Navigator
   - The File Info panel shows wiretap processing options

2. **Check Folder Suitability**:
   - The system automatically checks if the folder contains audio files
   - A message indicates if the folder is suitable or what's missing

3. **Process Single Folder**:
   - Click **Process as Wiretap** button in the File Info panel
   - Select Whisper model size (tiny, base, small, medium, large)
   - Processing starts in the background

4. **Process Multiple Folders**:
   - Select multiple folders (Ctrl/Cmd+Click)
   - Click **Process All [N] Folders as Wiretaps** button
   - Each folder is processed in a separate background task

#### Whisper Model Selection

Choose the Whisper model size based on your needs:
- **Tiny**: Fastest, least accurate (good for quick processing)
- **Base**: Balanced speed and accuracy (recommended default)
- **Small**: Better accuracy, slower
- **Medium**: High accuracy, significantly slower
- **Large**: Best accuracy, slowest (requires more memory)

#### Monitoring Wiretap Processing

1. **Background Tasks Panel**: Click the background tasks icon to monitor progress
2. **Task Details**: Each wiretap processing task shows:
   - Folder name being processed
   - Progress status
   - Estimated completion time
3. **Processing Logs**: Real-time logs appear in the Ingestion Log panel
4. **Task Completion**: When complete, the folder is marked as processed

#### Processed Wiretap Tracking

- **Processed Wiretap List**: View all successfully processed wiretap folders
- **Status Indicators**: Processed folders show a checkmark in the File Navigator
- **Avoid Duplicate Processing**: The system prevents reprocessing already-processed folders

#### What Happens During Processing

1. **Audio Transcription**: Whisper AI transcribes audio to text (Spanish and English)
2. **Metadata Extraction**: System extracts call metadata from `.sri` files
3. **RTF Parsing**: Prosecutor interpretations are parsed from `.rtf` files
4. **Entity Extraction**: AI extracts entities (people, locations, events) from transcriptions
5. **Relationship Creation**: Relationships between entities are identified
6. **Graph Integration**: All data is added to the Neo4j knowledge graph
7. **Case Versioning**: A new case version is automatically saved after successful processing

#### Troubleshooting Wiretap Processing

- **Missing Dependencies**: If processing fails, check that `openai-whisper`, `striprtf`, and `ffmpeg` are installed
- **Error Messages**: Check the Background Tasks panel for detailed error messages
- **Processing Logs**: Review the Ingestion Log for specific error details
- **Folder Requirements**: Ensure folders contain at least one audio file

---

## LLM Profile Management

LLM Profiles allow you to customize how the AI processes evidence files. Each profile defines entity types, relationship patterns, and AI behavior.

### Accessing Profile Management

1. In the **Evidence Processing** view, click **Edit Profile** or **New Profile** button.
2. The Profile Editor modal opens.

### Creating a New Profile

1. Click **New Profile** in the Evidence Processing view.
2. Optionally select **Clone from Existing Profile** to start with an existing profile's settings.
3. Enter a **Profile Name** (lowercase, alphanumeric, hyphens, underscores only).
4. Fill in the profile details (see Profile Fields below).
5. Click **Save Profile**.

### Editing a Profile

1. Click **Edit Profile** next to the profile dropdown.
2. Select the profile you want to edit.
3. Modify any fields as needed.
4. Click **Save Profile**.

### Profile Fields

#### Basic Information
- **Profile Name**: Unique identifier (cannot be changed after creation)
- **Description**: Brief description of the profile's purpose

#### Agent Configuration
- **Case Type**: Type of investigation (e.g., "Fraud Investigation", "Money Laundering Case")
- **Agent Description**: Description of what kind of agent this is and its role
- **Instructions**: Specific instructions on how the agent should behave and what to look for
- **Characteristics**: Characteristics the agent should have

#### Entity Types
- **Add Entity**: Click to add a new entity type
- **Entity Name**: Type of entity (e.g., "Person", "Company", "Transaction")
- **Color Picker**: Select the color for nodes of this entity type in the graph
- **Description**: Instructions for the LLM on how to identify this entity type

**Note**: New entities are added to the top of the list for easy access.

#### Relationship Examples
- **Add Example**: Click to add relationship examples
- Enter examples like "Person works for Organisation" or "Event occurred at Location"
- The LLM uses these examples to identify similar relationships in documents
- The system can create new relationship types dynamically based on document content

#### LLM Configuration
- **Provider**: Choose AI provider (OpenAI, Ollama, etc.)
- **Model**: Select specific AI model to use
- **Temperature**: Controls AI creativity (0.0-2.0)
  - **Lower (0.0-0.5)**: More deterministic, consistent outputs
  - **Higher (1.0-2.0)**: More creative, varied outputs
  - **Default**: 1.0

#### Chat Configuration
- **System Context**: Context for chat interactions
- **Analysis Guidance**: Guidance for analysis and responses

### Profile Cloning

When creating a new profile:
1. Select an existing profile from the **Clone from Existing Profile** dropdown.
2. All settings are copied except the profile name.
3. Modify any fields as needed.
4. Save with a new name.

### Dynamic Entity and Relationship Types

The system supports dynamic creation of entity and relationship types:

- **New Entity Types**: If the LLM finds entities that don't fit predefined types, it can create new descriptive types (e.g., "Vehicle", "Account", "Meeting").
- **New Relationship Types**: The LLM can create relationship types based on document context (e.g., "OWNS", "TRANSFERRED_TO", "MET_WITH", "EMAILED").
- **Automatic Display**: All entity types found in the database are displayed in the graph legend, regardless of whether they were predefined in a profile.

### Profile Best Practices

1. **Start with Cloning**: Clone an existing profile (like "generic" or "fraud") and modify it.
2. **Clear Descriptions**: Provide clear entity descriptions to help the LLM identify entities accurately.
3. **Relationship Examples**: Give concrete examples rather than abstract relationship types.
4. **Temperature Tuning**: Lower temperature for factual extraction, higher for creative analysis.
5. **Test and Iterate**: Process sample documents and adjust the profile based on results.

---

## Graph View

The Graph View is the main workspace for visualizing and analyzing relationships between entities in your case.

### Navigation

- **Pan**: Click and drag the background
- **Zoom**: Use mouse wheel or pinch gesture
- **Center**: Click the **Center Graph** button to center and zoom to fit all nodes
- **Single/Double Click**: Select nodes (see Selection below)

### Selection Methods

#### Click Selection

- **Single Click**: Select a single node
- **Command+Click (Mac) / Ctrl+Click (Windows)**: Add nodes to selection
- Clicking a node selects it and adds it to the subgraph

#### Drag Selection Box

1. Toggle selection mode using the button above the Entity Types legend.
2. Click and drag on the graph to create a selection box.
3. Release to select all nodes within the box.
4. The selection box stays visible until you change selection mode.

#### Entity Type Selection

1. In the **Entity Types** legend (bottom left), click an entity type.
2. All nodes of that type on the visible graph are selected and added to the subgraph.
3. The graph highlights all selected nodes.

#### Select All Visible

1. Click **Select All Visible** in the Entity Types legend.
2. All visible nodes are added to the subgraph.
3. The button toggles to **Deselect All Visible** when all nodes are selected.

#### Timeline Selection

- In Timeline view, use **Command+Click** to select multiple events/nodes
- Selected nodes become the subgraph and selected nodes

### Subgraph Panel

- **Toggle**: Click the arrow button (right arrow when closed, left arrow when open) in the Entity Types legend to show/hide the subgraph panel.
- **Split View**: The subgraph appears in a right-side panel showing only selected nodes and their connections.
- **Center Subgraph**: Click the center button to focus the subgraph view.

### Search and Filters

#### Graph Search Filter

Located in the top toolbar:

1. **Mode Dropdown**: Choose between:
   - **Filter**: Filters as you type (real-time)
   - **Search**: Requires clicking a search button, supports advanced queries
2. **Search Options**:
   - Simple text search matches node names and properties
   - **Boolean Logic**: Use `AND`, `OR`, `NOT` (e.g., `John AND Smith`, `Company OR Organization`)
   - **Wildcards**: Use `*` for partial matches (e.g., `John*`)
   - **Fuzzy Matching**: Finds similar but not exact matches
3. **Apply Filter**: In Search mode, click the search button to execute.

**Note**: The search filter replaces the "Search entities" box in graph and table views for more powerful filtering capabilities.

#### Date Range Filter

Located in the top left (above the graph):

1. Click the calendar icon to open the date filter.
2. Set **Start Date** and **End Date** using:
   - Date picker
   - Time inputs
   - Visual timeline slider
3. Click **Apply** to filter the graph.
4. The graph shows only nodes with timestamps in the range or connected to such nodes.

### Node Details

The **Selected Nodes Panel** (right side of the graph view) displays detailed information about selected nodes.

#### Basic Node Information

When you select a node, the panel shows:
- **Node Name and Type**: The entity name and its type (Person, Company, Location, etc.)
- **Key**: Unique identifier for the node
- **Summary**: Brief factual summary of the node

#### Verified Facts Section

The **Verified Facts** section displays confirmed information about the node:

- **Fact Display**: Each verified fact shows:
  - Fact text (confirmed information)
  - Source citation (document name and page number, if available)
  - Verification badge (showing who verified it, if verified by a user)
  - Quote from source document (if available)
  - Pin/unpin button (star icon)

- **Viewing Source Documents**:
  - Click the **source citation link** (document name with page number) next to any fact
  - The Document Viewer opens showing the original source document
  - The document opens to the specific page referenced
  - Use page navigation buttons to move through the document
  - Click **Open in new tab** to view in a separate browser window

- **Pinning Facts**:
  - Click the **star icon** next to a fact to pin it
  - Pinned facts appear at the top of the list
  - Pinned facts have a highlighted background
  - Click again to unpin

- **Collapsible Section**: Click the section header to expand/collapse
- **Show All**: If there are more than 5 facts, click "Show all" to see all facts

#### AI Insights Section

The **AI Insights - Unverified** section displays AI-generated inferences that haven't been confirmed:

- **Insight Display**: Each insight shows:
  - Insight text (AI inference)
  - Confidence level (high, medium, low)
  - Reasoning (why the AI made this inference)
  - "Mark as Verified" button

- **Verifying Insights**:
  1. Click **Mark as Verified** on an insight
  2. Optionally add:
     - **Source document**: Name of the document that confirms this insight
     - **Page number**: Specific page reference
  3. Click **Confirm Verification**
  4. The insight is converted to a verified fact
  5. Your username is recorded as the verifier

- **Important**: AI insights are inferences, not confirmed facts. Always verify before marking as verified.

- **Collapsible Section**: Click the section header to expand/collapse
- **Empty State**: If there are no insights, the section shows "No AI insights."

#### Viewing Source Documents

When viewing node details, you can access source documents in several ways:

1. **From Verified Facts**:
   - Click any citation link (document name with page number)
   - Example: "report.pdf, p.5" opens the document at page 5

2. **Document Viewer Features**:
   - **Page Navigation**: Use Previous/Next buttons or type page number
   - **Open in New Tab**: Click the external link icon
   - **Keyboard Shortcut**: Press `Esc` to close the viewer
   - **Scroll Navigation**: Use mouse wheel or scrollbar within the document

3. **Supported File Formats**:
   - PDF documents (most common)
   - Text files (.txt)
   - Word documents (.doc, .docx)
   - Images (.png, .jpg, .jpeg)

#### Connections Section

- **Relationship Display**: Shows all relationships connected to the node
- **Direction Indicators**: 
  - Right arrow (→) for outgoing relationships
  - Left arrow (←) for incoming relationships
- **Click to Navigate**: Click any connection to select that connected node
- **Relationship Type**: Shows the type of relationship (e.g., "WORKS_FOR", "OWNS")

#### Properties Section

- **Additional Properties**: Displays other node properties not shown in main sections
- **Key-Value Pairs**: Shows property names and their values
- **Technical Data**: May include internal identifiers and metadata

#### Editing Node Information

- **Edit Button**: Click the **Edit** button in the Selected panel header
- **Edit Summary and Notes**: Modify the node's summary and detailed notes
- **Searchable Content**: Both summary and notes are searchable and available to the AI assistant
- **Multi-Node Editing**: When multiple nodes are selected, editing applies to all selected nodes

### Adding/Removing from Subgraph

- **Add to Subgraph**: Button in Entity Types legend adds selected nodes to subgraph
- **Remove from Subgraph**: Button removes selected nodes from subgraph
- **Make All Subgraph Nodes Selected**: Button in subgraph header selects all subgraph nodes

### Adding Nodes Manually

You can manually add nodes to the graph:

1. Click the **Add Node** button (Plus icon) in the top-left corner of the graph view
2. Enter:
   - **Name**: The node's name
   - **Type**: Entity type (e.g., "Person", "Company") - you can type a new type or select from existing types
   - **Summary**: Brief summary of the node
   - **Description**: Detailed description
3. Click **Create Node**
4. The node is added to the graph and Cypher is generated automatically

**Note**: New entity types can be created by typing them in the Type field. They will appear in the entity legend.

### Editing Node Information

You can edit summary and notes for existing nodes:

1. Select one or more nodes on the graph
2. In the **Selected** panel, click the **Edit** button
3. Enter or modify:
   - **Summary**: Brief summary
   - **Notes**: Detailed notes
4. Click **Save Changes**
5. The information is saved and becomes searchable

**Note**: When editing multiple nodes, the same summary and notes are applied to all selected nodes.

### Creating Relationships

You can manually create relationships between nodes:

1. Right-click on a source node
2. Select **Add a Relationship**
3. Click on a target node (the relationship mode indicator appears at the top)
4. Enter:
   - **Relationship Type**: Type of relationship (e.g., "WORKS_FOR", "OWNS")
   - **Notes**: Optional notes about the relationship
5. Click **Create Relationship**
6. The relationship is added to the graph

**Note**: Duplicate relationships are automatically prevented. Existing relationships are preserved when adding new ones.

### Relationship Analysis

The AI can analyze a node and suggest relationships with existing nodes:

1. Right-click on a node
2. Select **Relationship Analysis**
3. The AI analyzes the node and suggests potential relationships
4. Review the suggested relationships in the dialog
5. Select which relationships to add using checkboxes
6. Click **Add Selected Relationships**
7. Only the selected relationships are added to the graph

**Note**: This feature uses the AI to understand context and suggest meaningful relationships based on node properties and existing graph structure.

### Context Menu

Right-click on a node to see options:
- **Show Details**: View full node information
- **Expand Connections**: Show all connected nodes
- **Add a Relationship**: Start relationship creation mode
- **Relationship Analysis**: Analyze node for potential relationships

---

## Table View

The Table View provides a spreadsheet-style view of all entities in your case, making it easy to review and analyze data in a structured format.

### Accessing Table View

1. In the **Graph View** or **Workspace View**, click the **Table** tab at the top.
2. The graph is replaced with a tabular view of all entities.

### Table Features

- **Rows**: Each row represents one entity (person, company, location, etc.)
- **Columns**: Each column shows a different property of the entities (name, type, summary, notes, etc.)
- **All Data Visible**: All entity information is displayed in columns, making it easy to review and compare entities
- **Horizontal Scroll**: Scroll left and right to see all columns
- **Vertical Scroll**: Scroll up and down to see all entities

### Relations Column

The rightmost column is the **Relations** column, which is always visible (sticky on the right):

- **Expand Relations**: For entities that have relationships, you'll see a button showing the number of relations (e.g., "▶ 5")
- **No Relations**: Entities without relationships show "—"
- **Always Visible**: The Relations column stays fixed on the right side when you scroll horizontally

### Expanding Relations

To see related entities:

1. Find an entity with relations (shows a number in the Relations column)
2. Click the **▶** button with the relation count
3. A new panel opens to the right showing all related entities
4. Each related entity appears as a row with the same column structure
5. The panel header shows "Relations of [Entity Name]"

### Expanding Further Relations

You can continue expanding relations:

1. In a relations panel, find an entity that has its own relations
2. Click the **▶** button for that entity
3. Another panel opens further to the right
4. This creates a chain of related entities, helping you explore connections

### Collapsing Relations

To collapse relation panels:

1. Each relations panel has an **X** button in its header
2. Click the **X** to collapse that panel
3. All panels to the right of the collapsed panel are also removed
4. This helps you focus on specific relationship chains

### Relation Types

In relation panels, you'll see:

- **Relation Column**: Shows the type of relationship connecting entities (e.g., "KNOWS", "OWNS", "WORKS_FOR")
- **Multiple Types**: If an entity is connected via multiple relationship types, they're all listed

### Filtering in Table View

The table view uses the same powerful filter as the graph view:

1. **Filter Input**: Located in the top toolbar (replaces the "Search entities" box)
2. **Filter Mode**: Filters as you type in real-time
3. **Search Mode**: Click search button for advanced queries
4. **Boolean Logic**: Use `AND`, `OR`, `NOT` for complex searches
5. **Wildcards**: Use `*` for partial matches
6. **Results**: The table updates to show only matching entities

### Selecting Entities in Table

- **Click Row**: Click any row to select that entity
- **Multi-Select**: Hold **Ctrl** (Windows) or **Command** (Mac) and click multiple rows
- **Selected Highlighting**: Selected rows are highlighted
- **Node Details**: Selected entities appear in the node details panel (if available)

### Table Layout

- **Multiple Panels**: You can have multiple relation panels open side-by-side
- **Horizontal Scroll**: Scroll horizontally to see all panels
- **Panel Headers**: Each panel shows its title (e.g., "All nodes" or "Relations of [Name]")
- **Fixed Relations Column**: The Relations column stays visible on the right in each panel

### Use Cases

The Table View is useful for:

- **Data Review**: Quickly review all entity information in a structured format
- **Finding Entities**: Use filters to find specific entities
- **Exploring Connections**: Expand relations to discover how entities are connected
- **Data Export**: Review data before exporting case reports
- **Comparison**: Compare multiple entities side-by-side

---

## Timeline View

The Timeline view provides a chronological view of events and entities.

### Switching to Timeline

1. Click the **Timeline** button in the top toolbar.
2. The graph is replaced with a timeline visualization.

### Timeline Features

- **Events**: All entities with dates are displayed chronologically.
- **Swim Lanes**: Events are organized by entity type or entity.
- **Zoom**: Use zoom controls to adjust the time scale.
- **Selection**: Command+Click to select multiple events/nodes.

### Timeline Filters

- **Search Filter**: Same as graph search (Filter or Search mode with boolean logic).
- **Date Range Filter**: Same date range filter as graph view.

### Timeline Actions

- **Multi-Select**: Command+Click events to select them.
- **Create Subgraph**: Selected events become the subgraph.
- **Query with AI**: Selected events become context for AI queries.
- **Save Snapshot**: Selected events can be saved as a snapshot.

---

## Map View

The Map view shows geocoded entities on an interactive map.

### Accessing Map View

1. Click the **Map** button in the top toolbar (if available).
2. Entities with location data are displayed as markers.

### Map Features

- **Clustering**: Nearby markers are grouped into clusters.
- **Filters**: Filter by entity type.
- **Click Markers**: View entity details.
- **Connections**: View relationships between locations.
- **Heatmap**: Visualize location density.
- **Proximity Analysis**: Analyze distances between locations.

---

## Graph Analysis Tools

The platform includes several graph analysis algorithms accessible from the subgraph menu.

### Shortest Path

Finds the shortest path between two selected nodes.

1. Select exactly two nodes on the graph.
2. Open the subgraph menu (three dots or menu icon).
3. Click **Shortest Path**.
4. The path is highlighted and shown in the subgraph panel.

### PageRank (Influential Nodes)

Identifies the most influential nodes in the graph or subgraph.

1. Select nodes or have a subgraph visible (optional - analyzes full graph if none selected).
2. Open the subgraph menu.
3. Click **PageRank (Influential Nodes)**.
4. Top influential nodes are displayed in the subgraph.
5. An analysis overview appears below the subgraph header, explaining the results.

### Louvain (Communities)

Detects communities or clusters of closely connected nodes.

1. Select nodes or have a subgraph visible (optional).
2. Open the subgraph menu.
3. Click **Louvain (Communities)**.
4. Nodes are colored by community.
5. An analysis overview explains the community structure.

### Betweenness Centrality (Bridge Nodes)

Identifies nodes that act as bridges between different parts of the graph.

1. Select nodes or have a subgraph visible (optional).
2. Open the subgraph menu.
3. Click **Betweenness Centrality (Bridge Nodes)**.
4. Bridge nodes are highlighted.
5. An analysis overview explains the significance.

### Analysis Overview

- After running PageRank, Louvain, or Betweenness Centrality, an analysis panel appears.
- Click to expand/collapse the analysis.
- The analysis includes:
  - Scope of analysis (subgraph, selected nodes, or full graph)
  - Summary statistics
  - Interpretation of results
  - Key findings

---

## Entity Management

The platform provides tools for managing entities, including resolving duplicates and merging entities.

### Entity Resolution

Entity resolution helps identify when multiple entries in your case refer to the same real-world entity (person, company, etc.).

#### Finding Similar Entities

1. Select a node on the graph
2. Right-click and select **Find Similar Entities** (or use the button in the graph controls)
3. The system scans the graph for entities that might be the same
4. Results show potential matches with similarity scores

#### Reviewing Matches

- **Similarity Score**: Each match shows how similar it is to the selected entity
- **Entity Details**: Review name, type, and summary of potential matches
- **Select Matches**: Check boxes next to entities you want to merge

### Merging Entities

When you've identified duplicate entities, you can merge them:

1. **Select Entities**: Select two or more entities you want to merge
2. **Open Merge Dialog**: Right-click and select **Merge Entities** (or use the merge button)
3. **Review Merge**:
   - The system shows what will be combined
   - Choose which entity's name, type, and summary to keep
   - Review relationships that will be preserved
4. **Confirm Merge**: Click **Merge Entities**
5. **Result**: All entities are combined into one, with all relationships preserved

#### What Gets Merged

- **Properties**: Name, type, summary, and notes are combined
- **Relationships**: All relationships from all merged entities are preserved
- **Verified Facts**: All verified facts are combined
- **AI Insights**: All AI insights are combined
- **Source Citations**: All source document citations are preserved

#### Validation

The system validates merges to prevent errors:
- **Type Compatibility**: Ensures entities of compatible types are merged
- **Relationship Preservation**: Verifies all relationships will be maintained
- **Data Integrity**: Checks that no information will be lost

### Deleting Entities

You can remove incorrect or unwanted entities:

1. **Select Entity**: Select the entity you want to delete
2. **Delete Option**: Right-click and select **Delete Entity** (or use delete button)
3. **Confirm Deletion**: Confirm that you want to delete the entity
4. **Result**: The entity and all its relationships are removed from the graph

**Warning**: Deleting an entity permanently removes it and all its relationships. This action cannot be undone.

### Graph Expansion

Graph expansion automatically discovers related entities:

1. **Select Starting Point**: Select one or more nodes
2. **Expand Connections**: Right-click and select **Expand Connections** (or use expand button)
3. **Choose Depth**: Select how many levels of connections to explore (1-3 levels recommended)
4. **Review Results**: New related entities are added to the graph
5. **Continue Exploring**: You can expand from the newly discovered entities

#### Expansion Options

- **Expand Selected**: Expands connections from currently selected nodes
- **Expand Subgraph**: Expands all entities in the Spotlight Graph
- **Expand Result Graph**: Expands entities in analysis result graphs
- **Expand All**: Expands the entire visible graph (use with caution on large graphs)

#### What Expansion Finds

- **Direct Connections**: Entities directly connected to your starting point
- **Indirect Connections**: Entities connected through intermediate entities
- **Relationship Types**: All types of relationships are explored
- **New Entities**: Previously unknown entities are discovered and added

---

## AI Assistant

The AI Assistant helps you query and understand your investigation data.

### Opening the Chat Panel

1. Click the **Chat/AI Assistant** icon in the top toolbar.
2. The chat panel opens on the right side.

### Asking Questions

1. Type your question in the input field.
2. Press **Enter** or click **Send**.
3. The AI responds based on:
   - **Focused Context**: If nodes are selected, answers focus on those nodes
   - **Global Context**: If no nodes are selected, answers consider the entire graph

### Suggested Questions

- The AI provides suggested questions based on your current selection.
- Click a suggestion to use it as your query.

### Context Indicators

- Messages show whether they used focused or global context.
- Icons indicate the context mode used.

### Chat History

- All questions and answers are saved in the chat history.
- Chat history is included when saving snapshots and exporting reports.

### Model Selection

- You can select different AI models for chat interactions
- Different models may provide different styles of analysis
- Model selection is available in the chat interface

---

## Theories and Reports

The platform allows you to create investigation theories and generate comprehensive reports.

### Creating Theories

1. In the **Workspace View**, go to the **Theories** section in the Investigation Panel
2. Click **New Theory** or **Add Theory**
3. Enter:
   - **Theory Title**: A descriptive name for your theory
   - **Hypothesis**: Your investigation hypothesis
   - **Theory Type**: Category of theory (optional)
4. Click **Save**

### Building Theory Graphs

1. **Select Entities**: Select entities relevant to your theory on the graph
2. **Build Theory Graph**: Use the theory tools to create a focused graph
3. **Review**: The theory graph shows only entities related to your theory
4. **Refine**: Add or remove entities as your theory develops

### Theory Export

Generate comprehensive reports for your theories:

1. **Open Theory**: Select a theory from the Theories section
2. **View Attached Items**: See all evidence, witnesses, notes, and other materials attached to the theory
3. **Export Report**: Click **Export Report** button
4. **Select Sections**: Choose which sections to include:
   - Theory details
   - Attached evidence
   - Witness interviews (with full details)
   - Notes and tasks
   - Graph visualization
   - Timeline visualization
   - Map visualization
   - Investigation timeline
5. **Generate**: Click export to generate the report
6. **Progress**: A progress bar shows report generation status
7. **Download**: The report downloads as an HTML file

#### Theory Report Contents

Theory reports include:
- **Theory Information**: Title, hypothesis, type, and description
- **Attached Evidence**: All evidence files with summaries and source citations
- **Witness Interviews**: Complete interview details including:
  - Interview date and duration
  - Interviewer information
  - Interview notes and summary
  - Witness statement
  - Status and credibility rating
  - Risk assessment
- **Audio Transcriptions**: Spanish transcriptions from wiretap processing (if available)
- **Audio Translations**: English translations of wiretap audio (if available)
- **Notes and Tasks**: All investigative notes and tasks
- **Visualizations**: Graph, timeline, and map images
- **Investigation Timeline**: Chronological events

### Case Export

Generate comprehensive case-level reports:

1. **Open Case Overview**: Go to the Case Overview tab in Workspace View
2. **Select Sections**: Use checkboxes on each section card to include/exclude from export
3. **Export Case**: Click **Export Case** button in the toolbar
4. **Review Selection**: The export modal shows which sections are included
5. **Preview Visualizations**: View graph, timeline, and map previews
6. **Generate**: Click export to generate the report
7. **Progress**: A progress bar shows report generation progress
8. **Download**: The report downloads as an HTML file

#### Case Report Contents

Case reports include all selected sections:
- **Client Profile**: Client information and case details
- **Theories**: All investigation theories
- **Pinned Evidence**: Evidence marked as important
- **Witnesses**: All witnesses with complete interview details
- **Deadlines**: Important case deadlines
- **Investigative Notes**: All case notes
- **Tasks**: Investigation tasks
- **All Evidence**: Complete evidence list with summaries
- **Documents**: Case documents
- **Graph Visualization**: Network diagram of entities
- **Graph Timeline**: Text-readable timeline of graph events
- **Graph Map**: Map visualization with text explanation of locations
- **Investigation Timeline**: Chronological investigation events
- **Snapshots**: Saved investigation states
- **Audit Log**: System activity log

#### Audio Content in Reports

When wiretap audio has been processed:
- **Spanish Transcriptions**: Full Spanish text of audio recordings
- **English Translations**: English translations of audio content
- Both are included in evidence sections when the source evidence file is included

---

## Snapshots

Snapshots allow you to save the current state of your investigation for later reference.

### Creating a Snapshot

1. Set up your graph/subgraph as desired (select nodes, run analyses, etc.).
2. Click the **Hard Drive** icon in the top toolbar to open the File Management Panel.
3. Click **Save Snapshot**.
4. Enter:
   - **Name**: A descriptive name for the snapshot
   - **Notes**: Optional description or explanation
5. The snapshot saves:
   - Current subgraph nodes and relationships
   - Selected nodes
   - Timeline data (if applicable)
   - AI chat history
   - Overview information

### Loading a Snapshot

1. Open the **File Management Panel** (Hard Drive icon).
2. Expand the **Snapshots** section (if collapsed).
3. Click **Load** on the desired snapshot.
4. The subgraph, selected nodes, and timeline context are restored.

### Exporting to PDF

1. In the File Management Panel, click **Export PDF** on a snapshot.
2. A PDF is generated containing:
   - Subgraph visualization (as image)
   - Overview of selected nodes
   - AI chat questions and answers
   - Timeline information
   - Your notes

### Deleting Snapshots

1. In the File Management Panel, click **Delete** on a snapshot.
2. Confirm the deletion.

---

## File Management

The File Management Panel (Hard Drive icon) consolidates all file operations.

### Accessing File Management

- Click the **Hard Drive** icon in the top toolbar (beside Settings).

### Panel Sections

1. **Save Snapshot** (top, always visible)
2. **Save/New Case** (top, always visible)
3. **Snapshots** (collapsible list)
4. **Cases** (collapsible list)

### Current Case Information

- Shows the name of the currently loaded case.
- Shows "No Case Loaded" if no case is active.

### Return to Case Management

- Click **Return to Case Management** to navigate back to the case management view.

---

## Background Tasks

Background tasks allow you to process multiple files without blocking your work.

### Viewing Background Tasks

1. Click the **Background Tasks** icon (spinner) in the top toolbar.
2. A panel slides in from the right showing active and recent tasks.

### Task Information

Each task shows:
- **Status**: Running, Completed, Failed, or Pending
- **Progress Bar**: For running tasks
- **File List**: Individual file status (processing, completed, failed)
- **Timestamps**: Start and completion times

### Completed Tasks

- **View in Case** button appears on completed tasks.
- Click to navigate to Case Management and view the processed case.
- The new case version with generated Cypher is automatically visible.

### Task Actions

- **Delete**: Remove a task from the list (doesn't affect processed files).

### Auto-Refresh

- The panel automatically refreshes every 2 seconds while open.
- Active tasks are shown first, followed by recent completed/failed tasks.

---

## Case Backup and Restore

The platform includes a case backup and restore system to protect your investigation data.

### Creating a Backup

1. In **Case Management**, select a case
2. Look for **Backup** or **Export Case** options
3. The system creates a backup file containing:
   - All case data
   - Evidence files metadata
   - Graph data
   - Case versions
   - Snapshots

### Restoring a Backup

1. Use the **Restore** or **Import Case** feature
2. Select your backup file
3. The system restores:
   - Case information
   - All evidence
   - Graph data
   - Versions and snapshots

### Backup Best Practices

- **Regular Backups**: Create backups before major changes
- **Version Control**: Each case version is automatically saved
- **Export Reports**: Export case reports as additional documentation
- **Multiple Copies**: Keep backups in multiple locations

---

## Cost Analysis

The platform tracks AI processing costs and generates cost reports for client billing.

### Viewing Costs

1. Access the **Cost Analysis** feature (location varies by view)
2. View cost breakdowns by:
   - Case
   - Date range
   - Processing type
   - AI model used

### Cost Reports

1. Generate detailed cost reports
2. Reports include:
   - Total costs
   - Cost per file
   - Cost by processing type
   - Time period breakdown
3. Reports can be exported as documents for client billing

### Cost Tracking

- **Automatic Tracking**: All AI processing is automatically tracked
- **Real-time Updates**: Costs update in real-time as processing occurs
- **Historical Data**: View costs for past processing
- **Forecasting**: Estimate costs for future processing

---

## Tips and Best Practices

### Organizing Your Work

1. **Create Cases Early**: Start by creating a case before uploading evidence.
2. **Use Descriptive Names**: Name cases and snapshots clearly.
3. **Save Snapshots Regularly**: Save important analysis states as snapshots.
4. **Version Your Cases**: Each save creates a new version, preserving history.

### Efficient Selection

1. **Use Entity Types**: Quickly select all nodes of a type.
2. **Combine Methods**: Use drag selection, then refine with individual clicks.
3. **Timeline Selection**: Great for selecting events by time period.
4. **Table View**: Use table view for structured data review.

### Analysis Workflow

1. **Start Broad**: Begin with the full graph or a large selection.
2. **Use Filters**: Narrow down with search and date filters.
3. **Run Analyses**: Use algorithms to discover patterns.
4. **Expand Connections**: Use graph expansion to discover related entities.
5. **Resolve Duplicates**: Use entity resolution to clean up duplicate entities.
6. **Save Results**: Save interesting findings as snapshots.

### Report Generation

1. **Theory Reports**: Generate focused reports for specific investigation theories.
2. **Case Reports**: Create comprehensive case reports from Case Overview.
3. **Select Sections**: Choose only relevant sections to keep reports focused.
4. **Include Visualizations**: Always include graph, timeline, and map visualizations.
5. **Review Before Export**: Check your section selections before generating reports.

### Collaboration

- Each user's cases and snapshots are private to their account.
- Cases are organized by username (e.g., "Neil's Cases").
- Use case exports to share information with team members.

### Performance

- **Large Graphs**: Use filters to reduce node count for better performance.
- **Background Processing**: Process multiple files in the background to continue working.
- **Subgraph Focus**: Work with subgraphs to focus on relevant data.
- **Table View**: Use table view for faster data review on large datasets.

---

## Keyboard Shortcuts

- **Command+Click (Mac) / Ctrl+Click (Windows)**: Multi-select nodes
- **Enter**: Send chat message
- **Mouse Wheel**: Zoom graph/timeline
- **Click + Drag**: Pan graph / Create selection box (when in selection mode)
- **Right-Click**: Context menu on nodes
- **Esc**: Close document viewer or modals

---

## Troubleshooting

### Graph Not Loading

- Check that a case is loaded or evidence has been processed.
- Try refreshing the page.
- Check the browser console for errors.

### Search Not Working

- Ensure you're in the correct mode (Filter vs Search).
- In Search mode, click the search button after entering your query.
- Check query syntax for boolean searches.

### Files Not Processing

- Check the processing logs for error messages.
- Verify file format is supported.
- Check background tasks panel for detailed status.

### Snapshots Not Loading

- Ensure the snapshot contains valid data.
- Try reloading the case first.
- Check that nodes still exist in the current graph.

### Table View Issues

- If relations don't appear, check that entities have relationships in the graph.
- Use the filter to narrow down large tables.
- Collapse relation panels if you have too many open.

### Export Issues

- Ensure you have selected at least one section for export.
- Wait for the progress bar to complete.
- Check that you have sufficient browser storage for large reports.

---

## New Features in Version 3.0

### Workspace View

- **Comprehensive Interface**: New workspace view with integrated case management
- **Case Overview Dashboard**: Complete case information in one scrollable view
- **Section Cards**: Organized sections for all case materials
- **Quick Navigation**: Easy switching between graph, timeline, map, and table views

### Case Export

- **Comprehensive Reports**: Export complete case reports with all selected sections
- **Section Selection**: Choose which sections to include via checkboxes
- **Progress Tracking**: Real-time progress bar during report generation
- **Audio Content**: Includes Spanish transcriptions and English translations from wiretap processing
- **Witness Details**: Complete witness interview information in reports
- **Visualizations**: Graph, timeline, and map images included automatically

### Theory Export

- **Theory Reports**: Generate focused reports for investigation theories
- **Attached Items**: Include all evidence, witnesses, and materials attached to theories
- **Full Interview Details**: Complete witness interview information
- **Audio Content**: Wiretap transcriptions and translations when available

### Table View

- **Spreadsheet Interface**: View all entities in a structured table format
- **All Data Visible**: All entity properties displayed as columns
- **Expandable Relations**: Click to expand and see related entities
- **Multiple Panels**: Open multiple relation panels side-by-side
- **Collapsible Panels**: Collapse relation panels to focus on specific chains
- **Sticky Relations Column**: Relations column always visible on the right
- **Powerful Filtering**: Same advanced filter as graph view

### Enhanced Filtering

- **Unified Search**: Graph and table views use the same powerful filter
- **Replaces Search Box**: Filter replaces the "Search entities" input in graph/table modes
- **Real-time Filtering**: Filter mode updates as you type
- **Advanced Search**: Search mode with boolean logic and wildcards

### Entity Management

- **Entity Resolution**: Find and identify duplicate entities
- **Entity Merging**: Merge duplicate entities with validation
- **Entity Deletion**: Remove incorrect entities from the graph
- **Graph Expansion**: Automatically discover related entities

### Enhanced File Support

- **Excel Files**: Process .xlsx and .xls spreadsheet files
- **CSV Files**: Process comma-separated value files
- **Word Documents**: Process .docx Word documents
- **Folder Processing**: Upload and process entire folders with structure preservation

### Case Backup and Restore

- **Data Protection**: Backup case data for safety
- **Restore Functionality**: Restore cases from backup files
- **Version History**: Automatic versioning preserves case history

### Cost Analysis

- **Cost Tracking**: Automatic tracking of AI processing costs
- **Cost Reports**: Generate detailed cost reports for client billing
- **Export Reports**: Export cost reports as documents

### Enhanced Map Features

- **Extended Functionality**: Improved geographic visualization
- **Location Analysis**: Better tools for analyzing location data
- **Connection Visualization**: See relationships between locations

### Document Summaries

- **Folder Summaries**: Automatic summaries for document folders
- **File Summaries**: Enhanced summaries for individual files
- **Preview Improvements**: Better file preview functionality

---

## Support

For technical support or questions, please contact your system administrator or refer to the technical documentation.

---

*Last Updated: January 2026*
