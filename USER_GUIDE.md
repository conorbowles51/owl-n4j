# Owl Investigation Platform - User Guide

**Version:** 2.2  
**Last Updated:** 24/12/2025

## Table of Contents

1. [Getting Started](#getting-started)
2. [Case Management](#case-management)
3. [Evidence Processing](#evidence-processing)
4. [LLM Profile Management](#llm-profile-management)
5. [Graph View](#graph-view)
6. [Timeline View](#timeline-view)
7. [Map View](#map-view)
8. [Graph Analysis Tools](#graph-analysis-tools)
9. [AI Assistant](#ai-assistant)
10. [Snapshots](#snapshots)
11. [File Management](#file-management)
12. [Background Tasks](#background-tasks)

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
3. Click **Load Version** to load the case into the graph view.

### Deleting a Case

1. Click the **trash icon** on any case in the list.
2. Confirm the deletion (this will delete all versions of the case).

---

## Evidence Processing

The Evidence Processing view allows you to upload and process documents for your case.

### Uploading Files

1. Click the **Choose files** area or drag and drop files.
2. Supported formats: PDF, TXT, and other document types.
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

### Opening Case in Graph

- Click **Open Case in Graph** to load the processed case into the graph view.
- If Cypher exists for the case, it will be loaded. Otherwise, an empty graph will be shown.
- The button is disabled while files are processing.

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

- **Missing Dependencies**: If processing fails, check that `openai-whisper`, `striprtf`, and `ffmpeg` are installed (see WIRETAP_DEPENDENCIES.md)
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

The Graph View is the main workspace for visualizing and analyzing relationships.

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
- Chat history is included when saving snapshots.

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

### Analysis Workflow

1. **Start Broad**: Begin with the full graph or a large selection.
2. **Use Filters**: Narrow down with search and date filters.
3. **Run Analyses**: Use algorithms to discover patterns.
4. **Save Results**: Save interesting findings as snapshots.

### Collaboration

- Each user's cases and snapshots are private to their account.
- Cases are organized by username (e.g., "Neil's Cases").

### Performance

- **Large Graphs**: Use filters to reduce node count for better performance.
- **Background Processing**: Process multiple files in the background to continue working.
- **Subgraph Focus**: Work with subgraphs to focus on relevant data.

---

## Keyboard Shortcuts

- **Command+Click (Mac) / Ctrl+Click (Windows)**: Multi-select nodes
- **Enter**: Send chat message
- **Mouse Wheel**: Zoom graph/timeline
- **Click + Drag**: Pan graph / Create selection box (when in selection mode)
- **Right-Click**: Context menu on nodes

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

---

## New Features

This section provides a release-by-release overview of major features and enhancements added to the Owl Investigation Platform.

### Version 2.2 (24/12/2025)

**Wiretap Audio Processing:**
- **Wiretap Folder Detection**: Automatically detect folders suitable for wiretap processing based on audio files (.wav, .mp3, .m4a, .flac), metadata files (.sri), and interpretation files (.rtf)
- **Wiretap Processing**: Process wiretap folders with Whisper AI for audio transcription and translation
- **Background Processing**: Wiretap folders are processed in the background with real-time progress tracking
- **Multiple Folder Processing**: Process multiple wiretap folders simultaneously, each in its own background task
- **Whisper Model Selection**: Choose Whisper model size (tiny, base, small, medium, large) for transcription accuracy vs. speed trade-off
- **Processed Wiretap Tracking**: Track which wiretap folders have been successfully processed
- **Automatic Case Versioning**: Automatically save new case versions after successful wiretap processing
- **Wiretap Metadata Extraction**: Extract metadata from .sri files including call times, contact IDs, session lengths, and participants
- **RTF Interpretation Parsing**: Parse prosecutor interpretation files (.rtf) for additional context
- **Error Handling**: Comprehensive error messages with detailed output for troubleshooting wiretap processing issues
- **Dependency Checking**: Automatic detection of missing dependencies (openai-whisper, striprtf, ffmpeg) with helpful error messages

**File System Browser:**
- **Case File System Navigation**: Browse files and directories within case data folders
- **File System API**: New filesystem router for listing directories and reading files
- **Recursive Folder Navigation**: Navigate through nested folder structures
- **File Information**: View file sizes, modification dates, and file types
- **Text File Reading**: Read text file contents directly from the file system browser

**Document Viewer Enhancements:**
- **Evidence File Serving**: Direct access to evidence files via evidence ID endpoint
- **Find Evidence by Filename**: Search for evidence files by original filename to locate evidence IDs from citations
- **Improved File Access**: Secure file serving with ownership verification and proper content-type headers
- **Multiple File Format Support**: Support for PDFs, text files, Word documents, and images in document viewer

**Background Tasks Improvements:**
- **Wiretap Task Tracking**: Dedicated task type for wiretap processing with progress monitoring
- **Task Icons**: Visual indicators for different task types (file upload, wiretap processing)
- **Enhanced Error Messages**: Detailed error output included in task failure messages for better debugging
- **Multiple Task Management**: Support for processing multiple wiretap folders with separate background tasks

**Error Handling and Diagnostics:**
- **Dependency Validation**: Pre-flight checks for required dependencies before starting wiretap processing
- **Detailed Error Logging**: Full error output captured and displayed in evidence logs
- **Script Output Capture**: Last 10 lines of script output included in error messages for troubleshooting
- **Installation Guide**: Comprehensive dependency installation guide (WIRETAP_DEPENDENCIES.md) for server setup

### Version 2.1 (21/12/2025)

**Manual Graph Editing:**
- **Manual Node Creation**: Add nodes directly to the graph with custom properties (name, type, summary, description)
- **Node Editing**: Edit summary and notes for selected nodes from the Selected Panel
- **Manual Relationship Creation**: Create relationships between nodes with custom relationship types
- **AI-Powered Relationship Analysis**: Right-click on a node to get AI suggestions for relationships with existing nodes
- **Create Snapshot from Selected Panel**: Camera icon button in Selected Panel to quickly create snapshots
- **Center Graph Button**: New center/focus button in top-left graph controls that focuses on selected nodes if any are selected, otherwise centers the whole graph

**Graph Controls and UI Improvements:**
- **Vertical Graph Controls**: Graph control buttons (center, add node, selection mode, settings) are now arranged vertically in the top-left corner
- **Minimizable Entity Type Legend**: Entity type legend on graph and subgraph can be collapsed/expanded with a minimize button
- **Smart Center Behavior**: Center graph button automatically focuses on selected nodes when available, falls back to centering entire graph

**Subgraph Enhancements:**
- **Subgraph Node Selection**: Select single or multiple nodes directly in the subgraph view (single click or Ctrl/Cmd+click)
- **Remove from Subgraph**: Button in subgraph legend to remove selected nodes from the subgraph
- **Subgraph Selection Management**: Clear selection by clicking background in subgraph view

**Analysis Overview Improvements:**
- **Clickable Node Names**: All node names listed in analysis results (PageRank, Betweenness Centrality) are clickable to select them
- **Clickable Communities**: Community names in Louvain analysis are clickable to select all nodes in that community
- **Multi-Select Support**: Hold Ctrl/Cmd while clicking node names or communities to toggle them in selection
- **No Text Truncation**: Analysis overview text, node summaries, and community descriptions are displayed in full without truncation
- **Full Text Display**: All analysis descriptions and summaries show complete text with proper word wrapping

**Case Management Enhancements:**
- **Collapsible Sections**: Evidence Files, Processing History, Versions, and Snapshots can be collapsed/expanded
- **Pagination**: All lists support pagination with 10 items per page for better navigation
- **Text Filters**: Filter Evidence Files by filename, Versions by version number/notes, Snapshots by name/notes
- **File Type Filter Pills**: Visual filter buttons for Evidence Files based on file extensions
- **Smart Defaults**: Only latest version/snapshot expanded by default, older items collapsed
- **Version Notes Visibility**: Version notes always visible even when collapsed

**Documentation Viewer Improvements:**
- **Expandable Subsections**: Table of contents supports expandable sections with subsections
- **Hierarchical Navigation**: Click main sections to expand/collapse subsections
- **Direct Subsection Navigation**: Click subsections to jump directly to that section in the documentation
- **Version History in TOC**: Version History section now appears in the table of contents for easy navigation

### Version 2.0 (20/12/2025)

**LLM Profile Management:**
- **Profile Creation and Editing**: Create custom LLM profiles for different case types
- **Profile Cloning**: Clone existing profiles as a starting point for new ones
- **Custom Entity Types**: Define entity types with custom colors and descriptions
- **Relationship Examples**: Provide relationship examples instead of predefined types
- **Temperature Control**: Adjust AI creativity level (0.0-2.0) for different use cases
- **Profile Selection**: Choose which profile to use when processing evidence files

**Enhanced Evidence Processing:**
- **Dynamic Entity Creation**: System automatically creates new entity types found in documents
- **Dynamic Relationship Creation**: New relationship types are created based on document content
- **Profile-Based Colors**: Entity colors in graph are determined by selected profile
- **Comprehensive Entity Legend**: All entity types in database are displayed in legend
- **Improved Cypher Validation**: Better error handling and validation for generated queries

**User Experience:**
- **Password Visibility Toggle**: Show/hide password during login
- **Documentation Viewer**: Access user guide directly from platform
- **Improved Profile Editor**: New entities added to top of list for better UX

### Background Tasks System (3 days ago)

**Asynchronous Processing:**
- **Background Task Management**: Process multiple files without blocking the UI
- **Task Monitoring**: View task progress in dedicated flyout panel
- **File-by-File Progress**: See individual file processing status
- **Auto-Refresh**: Task panel automatically updates every 2 seconds
- **View in Case**: Navigate directly to case after task completion

### User Accounts and Case Management (3 days ago)

**User-Specific Data:**
- **User Authentication**: Multiple user accounts (admin, neil, conor, alex, arturo)
- **Personal Case Lists**: Each user sees only their own cases ("Username's Cases")
- **Case Ownership**: All case components (files, versions, snapshots) are user-specific
- **Secure Access**: JWT-based authentication for all API endpoints

**Case Management:**
- **Case Creation**: Create new cases with custom names and notes
- **Case Loading**: Load cases into graph view with automatic graph clearing
- **Version Management**: Automatic versioning when saving cases
- **Evidence File Integration**: Files associated with cases and visible in case details

### File Processing and Ingestion (3 days ago)

**Evidence File Handling:**
- **File Upload**: Drag-and-drop or select files for upload
- **File Hashing**: Automatic duplicate detection using file hashes
- **Processing Integration**: Files automatically added to case after processing
- **Ingestion Logs**: Real-time feedback during file processing
- **Status Tracking**: Files show processing status (unprocessed, processed, duplicate, failed)

### Graph Analysis Features

**Advanced Algorithms:**
- **Shortest Path**: Find shortest path between two selected nodes
- **PageRank (Influence)**: Identify most influential nodes in graph
- **Louvain Communities**: Detect communities/clusters of connected nodes
- **Betweenness Centrality**: Find bridge nodes connecting different graph regions
- **Analysis Overview**: Detailed explanations of analysis results

**Subgraph Management:**
- **Add to Subgraph**: Build custom subgraphs by adding selected nodes
- **Remove from Subgraph**: Remove nodes from subgraph
- **Subgraph View**: Dedicated split-pane view for subgraph visualization
- **Subgraph Menu**: Consolidated menu for all subgraph operations

### Timeline and Search Enhancements

**Timeline View:**
- **SwimLane Visualization**: Chronological view with swim lanes
- **Event Organization**: Events organized by entity type or entity
- **Multi-Select**: Select multiple events/nodes with Command+Click
- **Timeline Context**: Selected timeline events become subgraph context

**Search and Filter:**
- **Complex Search**: Advanced search with boolean logic (AND, OR, NOT)
- **Wildcard Support**: Use `*` for partial matches
- **Fuzzy Matching**: Find similar but not exact matches
- **Filter Mode**: Real-time filtering as you type
- **Date Range Filter**: Filter nodes by timestamp with visual timeline slider

### Map and Geocoding

**Geographic Visualization:**
- **Geocoding Service**: Automatic geocoding of location entities during ingestion
- **Map View**: Interactive map showing geocoded entities
- **Marker Clustering**: Nearby markers grouped into clusters
- **Entity Type Filtering**: Filter map markers by entity type

### Authentication and Security

**Login System:**
- **User Authentication**: Secure login with username and password
- **Session Management**: JWT tokens for authenticated sessions
- **Logout**: Secure logout with token cleanup
- **Password Security**: Password visibility toggle with secure storage

### Foundation Features

**Core Graph Visualization:**
- **Force-Directed Graph**: Interactive force-directed graph layout
- **Node Selection**: Single and multi-select node selection
- **Relationship Labels**: Toggle relationship labels in subgraph view
- **Graph Controls**: Force simulation controls for customizing layout
- **Zoom and Pan**: Mouse wheel zoom and drag-to-pan navigation

---

## Support

For technical support or questions, please contact your system administrator or refer to the technical documentation.

---

---

## Version History

### Version 2.2 (24/12/2025)

**New Features:**
- Wiretap Audio Processing System
  - Automatic detection of wiretap folders suitable for processing
  - Background processing with Whisper AI for transcription and translation
  - Support for multiple wiretap folders processed simultaneously
  - Whisper model selection (tiny, base, small, medium, large)
  - Metadata extraction from .sri files (call times, contact IDs, participants)
  - RTF interpretation file parsing
  - Processed wiretap tracking and history
  - Automatic case versioning after successful processing
  - Comprehensive error handling with detailed diagnostics

- File System Browser
  - Browse case file systems with directory navigation
  - View file information (size, modification date, type)
  - Read text file contents directly
  - Recursive folder navigation support

- Document Viewer Enhancements
  - Direct evidence file serving by evidence ID
  - Find evidence files by original filename
  - Improved file access with ownership verification
  - Support for multiple file formats (PDF, text, Word, images)

- Background Tasks Improvements
  - Dedicated wiretap processing task type
  - Visual task type indicators
  - Enhanced error messages with script output
  - Multiple concurrent task support

**Improvements:**
- Better error diagnostics for wiretap processing failures
- Dependency validation before processing starts
- Comprehensive installation guide for server dependencies
- Improved error logging with full output capture

### Version 2.1 (21/12/2025)

**New Features:**
- Enhanced Case Management Interface
  - Collapsible sections for Evidence Files, Processing History, Versions, and Snapshots
  - Pagination (10 items per page) for all lists
  - Text filters for Evidence Files, Versions, and Snapshots
  - File type filter pills for Evidence Files with dynamic type detection
  - Default collapsed state: only latest version/snapshot expanded
  - Version notes always visible, even when collapsed
  - Automatic sorting: versions by version number, snapshots by timestamp

- Manual Graph Editing
  - Add nodes manually with custom properties
  - Edit node summary and notes directly from the graph
  - Create relationships between selected nodes
  - AI-powered relationship analysis for nodes
  - Node information (summary and notes) is searchable and available to AI

- Graph Interaction Improvements
  - Add Node button in top-left corner of graph view
  - Edit button in Selected panel for quick node editing
  - Context menu options for relationship creation and analysis
  - Relationship mode indicator when creating relationships

**Improvements:**
- Better organization of case details with collapsible sections
- Improved navigation with pagination for large lists
- Enhanced filtering capabilities for finding specific items
- More intuitive version and snapshot display

### Version 2.0 (20/12/2025)

**New Features:**
- LLM Profile Management System
  - Create, edit, and clone LLM profiles
  - Custom entity types with color pickers
  - Relationship examples instead of predefined types
  - Temperature control for AI creativity
  - Profile selection in evidence processing

- Enhanced Evidence Processing
  - Dynamic entity and relationship type creation
  - All entity types displayed in graph legend
  - Profile-based entity colors in graph visualization
  - Improved Cypher query validation

- User Experience Improvements
  - Password visibility toggle in login
  - Profile cloning for easy profile creation
  - New entities added to top of list
  - Documentation viewer accessible from platform

**Improvements:**
- Better error handling for Cypher queries
- Enhanced string escaping in Cypher generation
- Improved entity type sanitization for Neo4j
- More flexible LLM prompt system

---

*Last Updated: 21/12/2025*


