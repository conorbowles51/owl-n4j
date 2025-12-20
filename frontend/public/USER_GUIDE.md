# Owl Investigation Platform - User Guide

**Version:** 2.0  
**Last Updated:** 20/12/2025

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

---

## Version History

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

*Last Updated: 20/12/2025*


