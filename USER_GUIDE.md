# Owl Investigation Platform - User Guide

## Table of Contents

1. [Getting Started](#getting-started)
2. [Case Management](#case-management)
3. [Evidence Processing](#evidence-processing)
4. [Graph View](#graph-view)
5. [Timeline View](#timeline-view)
6. [Map View](#map-view)
7. [Graph Analysis Tools](#graph-analysis-tools)
8. [AI Assistant](#ai-assistant)
9. [Snapshots](#snapshots)
10. [File Management](#file-management)
11. [Background Tasks](#background-tasks)

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
- **Evidence Files**: List of uploaded and processed files
- **Processing History**: Logs showing file processing activity
- **Versions**: All saved versions of the case (most recent first)
- **Cypher Queries**: The database queries used to recreate the graph
- **Snapshots**: Saved snapshots associated with each version

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

- **Overview Panel**: Shows details of selected nodes (left side in split view).
- Click on a node to see:
  - Node name and type
  - Properties and values
  - Connected relationships
  - Summary and notes

### Adding/Removing from Subgraph

- **Add to Subgraph**: Button in Entity Types legend adds selected nodes to subgraph
- **Remove from Subgraph**: Button removes selected nodes from subgraph
- **Make All Subgraph Nodes Selected**: Button in subgraph header selects all subgraph nodes

### Context Menu

Right-click on a node to see options:
- View details
- Remove from subgraph
- Focus on node

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

## Support

For technical support or questions, please contact your system administrator or refer to the technical documentation.

---

*Last Updated: 2024*


