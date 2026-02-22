# Owl Platform — Agent Build Prompts
**14 Priority Features · Ready-to-Run Agent Instructions**
*February 2026*

---

## How to Use This Document

Each section below is a self-contained prompt you can paste directly into a coding agent (Claude Code, Cursor, etc.). Each prompt:

- Tells the agent exactly what to build
- Gives it the precise files to touch
- Provides the exact function names, endpoint paths, and patterns already in the codebase
- Explains what already exists so it doesn't duplicate work
- States the acceptance criteria (how you know it's done)

**Run order:** Sprint 1 items can run in parallel. Sprint 2 and 3 items have dependencies noted.

---

## SPRINT 1 — Quick Wins

---

### AGENT PROMPT 1.1 — Fix: Document Viewer Opens Behind Modal

**Estimated time:** 2–4 hours
**Files to touch:** 2–3 frontend files only
**Can run in parallel with:** All other Sprint 1 prompts

---

```
You are working on the Owl Investigation Platform — a React/FastAPI legal investigation tool.

TASK: Fix the bug where the DocumentViewer opens behind the MergeEntitiesModal (and any other modal).
The same bug also affects the MapView — popup panels open behind the modal layer.

PROBLEM:
When a user is in the Merge Entities modal and clicks to view a source document, the DocumentViewer
opens but appears behind the modal overlay. The user has to close the merge modal to see the document,
losing their progress. The same issue occurs on the MapView.

CODEBASE CONTEXT:
- Frontend framework: React 18, Tailwind CSS, Vite
- Project root: /Users/neilbyrne/Documents/Owl/owl-n4j
- Frontend source: /Users/neilbyrne/Documents/Owl/owl-n4j/frontend/src

KEY FILES:
- /frontend/src/components/MergeEntitiesModal.jsx (684 lines) — the modal that triggers the bug
- /frontend/src/components/DocumentViewer.jsx — the viewer that opens behind it
- /frontend/src/components/MapView.jsx — also has popup-behind-modal issue

SOLUTION APPROACH:
Use React Portals (ReactDOM.createPortal) to render the DocumentViewer outside the modal's DOM
subtree, at the document.body level. This makes z-index work correctly regardless of where in the
DOM tree the modal is.

IMPLEMENTATION STEPS:

1. Open /frontend/src/components/DocumentViewer.jsx
   - Find the outermost wrapper div (the overlay/backdrop)
   - Wrap the entire component's return in: ReactDOM.createPortal(<existing JSX>, document.body)
   - Add import: import ReactDOM from 'react-dom'
   - Ensure the overlay div has className including: fixed inset-0 z-[9999]
   - The z-index MUST be 9999 or higher (modals use z-50 which is 50)

2. Open /frontend/src/components/MergeEntitiesModal.jsx
   - Find where DocumentViewer is rendered (search for <DocumentViewer)
   - Ensure it is NOT wrapped in any div with overflow:hidden (this clips portals)
   - The modal itself should have z-index z-50 (keep as-is)
   - The DocumentViewer rendered via portal will automatically appear above it

3. Open /frontend/src/components/MapView.jsx
   - Find any detail panels, popups, or drawer components that open when clicking map markers
   - Apply the same ReactDOM.createPortal pattern to those components
   - Or if they're inline JSX, wrap them in a portal with z-[9999]

ACCEPTANCE CRITERIA:
- Open the Merge modal → click to view a source document → document appears ON TOP of the merge modal
- Close the document → merge modal is still open with state preserved (do not lose merge progress)
- On MapView: open a detail panel → it appears above any overlapping modals
- No visual regressions in normal (non-modal) document viewing
- No console errors about portals or DOM

DO NOT:
- Change any backend code
- Change the merge logic or any non-UI functionality
- Use z-index values less than 9000 for the DocumentViewer overlay
```

---

### AGENT PROMPT 1.2 — Reduce AI Entity Extraction Noise

**Estimated time:** 4–6 hours
**Files to touch:** 2 backend files (prompt + config)
**Can run in parallel with:** All other Sprint 1 prompts
**⚠️ Note:** Only affects NEW document ingestions. Existing case graphs are not changed.

---

```
You are working on the Owl Investigation Platform — a React/FastAPI legal investigation tool.

TASK: The AI entity extraction pipeline creates too many low-quality, noisy entities.
Update the extraction prompt and configuration to produce fewer, higher-quality entities.

PROBLEM:
When processing legal discovery documents, the LLM extracts too many entities — including
minor mentions, individual table rows as separate entities, and generic references.
This produces a noisy, cluttered knowledge graph that is hard for attorneys to use.
Target: reduce entity count by 30-50% while keeping all significant entities.

CODEBASE CONTEXT:
- Project root: /Users/neilbyrne/Documents/Owl/owl-n4j
- Backend ingestion: /Users/neilbyrne/Documents/Owl/owl-n4j/backend/ingestion/scripts/
- Profiles: /Users/neilbyrne/Documents/Owl/owl-n4j/profiles/

KEY FILES TO MODIFY:

1. /backend/ingestion/scripts/llm_client.py
   - The extraction system prompt is around lines 477-535
   - The entity guidance section is around lines 404-472
   - Line 425-429 specifically instructs extraction of EACH TABLE ROW as a separate entity — this
     is the biggest source of noise

2. /profiles/*.json (all profile JSON files in the profiles directory)
   - These configure LLM behavior per investigation type
   - Look for ingestion-related settings

CHANGES TO MAKE:

### Change 1: Update extraction prompt in llm_client.py

Find the system prompt for entity extraction. Add/replace with these CRITICAL RULES immediately
before the JSON format instruction:

```
ENTITY QUALITY RULES - FOLLOW STRICTLY:
1. SIGNIFICANCE THRESHOLD: Only extract entities that play an active, named role in the events
   described. Skip passing mentions, generic job titles without names, and background references.

2. TABLES: Do NOT create one entity per table row. Instead:
   - Identify the 2-3 most significant parties in the table (e.g., the main account holder,
     the primary counterparty)
   - Create entities only for those named parties
   - Summarize the table's content in the verified_facts of those entities
   - Exception: if a table row represents a unique named person or organization not seen elsewhere,
     extract them

3. IMPORTANCE SCORING: Before including an entity, ask yourself: "Would an attorney investigating
   this case need to click on this entity?" If no, do not extract it.

4. FINANCIAL TRANSACTIONS: Extract the transaction itself (as a Transfer/Payment node) and
   the key parties (from_entity, to_entity). Do not create separate entities for every
   account number, reference number, or transaction ID mentioned in passing.

5. DEDUPLICATION: If you see the same person or organization referred to by slightly different
   names in the same document (e.g., "John Smith" vs "Mr. Smith" vs "J. Smith"), create ONE
   entity with the most complete name. List the aliases in verified_facts.

6. MINIMUM THRESHOLD: An entity must appear in at least one of these contexts to be extracted:
   - Named party to a transaction, agreement, or legal proceeding
   - Person who made or received a communication
   - Organization directly involved in the matter (not just mentioned in passing)
   - Location that is a key site of events (not just an address on a letterhead)
```

### Change 2: Modify the table extraction instruction (llm_client.py ~line 425-429)

Find the instruction about tabular data (currently something like "extract each row as separate
entity with own date/amount"). Replace with:

```
TABULAR DATA: For tables, identify the KEY PARTIES involved (typically 2-4 entities maximum
for the whole table), extract them as entities, and capture the table's key facts in their
verified_facts field. Only create individual transaction nodes for high-value or particularly
significant individual transactions (e.g., amounts over a threshold relevant to the case,
or transactions with unusual counterparties).
```

### Change 3: Add entity importance scoring step (llm_client.py)

After the extraction JSON is returned from the LLM, add a filtering step:
- For each entity in the returned list, check:
  - Does it have at least 1 verified fact? (If not, it's probably not significant)
  - Is the name a real named entity (not a generic term like "The Company" or "Bank Branch")?
  - Filter out entities where name length < 3 chars or name is purely numeric
- Log how many entities were filtered: "Filtered X low-quality entities from Y extracted"

### Change 4: Raise entity resolution fuzzy match threshold

Find the entity resolution script at /backend/ingestion/scripts/entity_resolution.py
- Find the fuzzy matching threshold (likely 0.7, 0.75, or 0.8 similarity)
- Raise it to 0.88 (more aggressive merging of similar names)
- This reduces duplicate entities created for the same real-world entity

ACCEPTANCE CRITERIA:
- Process a test document and count entities before vs. after changes
- Entity count should be 30-50% lower for typical legal discovery documents
- No named parties, key organizations, or significant transactions should be missing
- The extraction prompt change is backwards-compatible (no DB schema changes)
- Add a comment in llm_client.py above your changes: # QUALITY FILTER - Feb 2026

DO NOT:
- Change any Neo4j schema or existing entity data
- Modify the frontend
- Delete or modify existing case data
- Change the relationship extraction logic (only entity extraction)
```

---

### AGENT PROMPT 1.3 — Save AI Chat Response as Case Note

**Estimated time:** 2–4 hours
**Files to touch:** 1 frontend file
**Can run in parallel with:** All other Sprint 1 prompts
**Depends on:** Nothing (Notes API already exists)

---

```
You are working on the Owl Investigation Platform — a React/FastAPI legal investigation tool.

TASK: Add a "Save as Note" button to AI chat responses so attorneys can save useful AI
answers directly to their case notes.

CODEBASE CONTEXT:
- Frontend framework: React 18, Tailwind CSS
- Project root: /Users/neilbyrne/Documents/Owl/owl-n4j
- Frontend source: /Users/neilbyrne/Documents/Owl/owl-n4j/frontend/src

EXISTING INFRASTRUCTURE (already built, do not rebuild):
- Notes API endpoints already exist in the backend at /api/workspace/{case_id}/notes
- The frontend API wrapper already exists: api.workspace.createNote(caseId, {content, tags})
  (found in /frontend/src/services/api.js around line 1858)

KEY FILES TO MODIFY:
- /frontend/src/components/ChatPanel.jsx — the main chat component
  - Message rendering is around lines 750-850
  - Assistant messages are rendered with light background, left-aligned
  - User messages are blue background, right-aligned

WHAT TO BUILD:

In ChatPanel.jsx, add a "Save as Note" action to each ASSISTANT message:

1. Find the assistant message rendering block (around lines 775-805)
   Look for the section that renders ai/assistant role messages

2. Add a small toolbar below each assistant message with a bookmark/pin icon button:
   - Icon: use BookmarkPlus or Pin from lucide-react (already imported)
   - Style: small, subtle, grey, appears on hover of the message
   - Tooltip: "Save as case note"

3. When clicked, show a small inline confirmation modal or popover with:
   - Title: "Save to Case Notes"
   - A text field pre-filled with the AI response content (editable so attorney can trim it)
   - A title field pre-filled with the first 60 characters of the USER'S question that
     triggered this response (look at the message before this one in the messages array)
   - Save button and Cancel button

4. On Save:
   - Call: api.workspace.createNote(caseId, {
       content: editedContent,
       tags: ['ai-chat']
     })
   - The caseId should already be available as a prop or from context in ChatPanel
   - Show a success toast: "Saved to case notes ✓"
   - Close the modal

5. Error handling:
   - If the API call fails, show: "Failed to save note. Please try again."

STYLING GUIDANCE:
- Follow existing Tailwind patterns in the file
- The save button should be subtle — not distracting during normal chat use
- Use the same modal/dialog pattern used elsewhere in the file if one exists
- Look for existing toast/notification patterns in the file and use the same approach

ACCEPTANCE CRITERIA:
- Hover over an AI response → see a bookmark icon appear
- Click the icon → modal opens with pre-filled content from AI response
- Edit content if desired → click Save → success toast appears
- Open the case notes panel → the saved note appears there
- The note has the tag "ai-chat"
- Cancel button closes modal without saving anything

DO NOT:
- Change any backend code
- Modify any other components
- Change the chat functionality itself
- Remove or modify existing chat UI elements
```

---

### AGENT PROMPT 1.4 — Financial Dashboard: Bulk Categorization UI

**Estimated time:** 3–5 hours
**Files to touch:** 1 frontend file
**Can run in parallel with:** All other Sprint 1 prompts
**Depends on:** Nothing (Batch categorize API endpoint already exists)

---

```
You are working on the Owl Investigation Platform — a React/FastAPI legal investigation tool.

TASK: The backend bulk categorization endpoint already exists but has no UI.
Add checkboxes and a batch action toolbar to the Financial Transactions table.

CODEBASE CONTEXT:
- Frontend framework: React 18, Tailwind CSS
- Project root: /Users/neilbyrne/Documents/Owl/owl-n4j
- Frontend source: /Users/neilbyrne/Documents/Owl/owl-n4j/frontend/src

EXISTING INFRASTRUCTURE (already built, do not rebuild):
- Batch categorize API: PUT /api/financial/batch-categorize
  Request body: { node_keys: string[], category: string, case_id: string }
- Frontend API call: api.financial.batchCategorize(nodeKeys, category, caseId)
  (in /frontend/src/services/api.js around line 794)
- The FinancialTable component already has:
  - selectedKeys state (array of selected transaction node_keys)
  - onSelectionChange prop (callback to update selectedKeys in parent)
  - onBatchCategorize prop (callback for batch categorization)
  These are passed DOWN from FinancialView.jsx

KEY FILES TO MODIFY:
- /frontend/src/components/financial/FinancialTable.jsx (primary file)
  - The batch action toolbar already exists (lines 345-379) for from/to operations
  - Table rows already have checkboxes (lines 386-392)
  - Selection toggle logic exists (lines 306-322)
- /frontend/src/components/financial/FinancialView.jsx (may need minor wiring)
  - This is the parent component that manages selectedKeys state
  - The batchCategorize handler should be here — check if it calls the API

WHAT TO BUILD / FIX:

1. READ both files carefully first to understand exactly what's already built vs. what's missing.

2. In FinancialTable.jsx, in the existing batch action toolbar (lines 345-379):
   - CHECK: Is there a category dropdown in the toolbar? If not, ADD one:
     - A <select> or custom dropdown showing all available categories
     - Categories come from the `categories` prop already passed to FinancialTable
     - An "Apply Category" button that calls onBatchCategorize(selectedKeys, selectedCategory)

3. Ensure the toolbar clearly shows:
   - "{N} transactions selected" count
   - Category dropdown (if missing, add it)
   - "Apply Category" button
   - "Clear Selection" button/link

4. In FinancialView.jsx:
   - Find or add the handleBatchCategorize function:
     ```javascript
     const handleBatchCategorize = async (nodeKeys, category) => {
       await api.financial.batchCategorize(nodeKeys, category, caseId);
       // refresh transactions
       loadTransactions();
       setSelectedKeys([]);
     };
     ```
   - Make sure this is wired as the onBatchCategorize prop on <FinancialTable>

5. Visual feedback:
   - Selected rows should have a visible highlight (light blue background or checkbox checked)
   - After successful batch categorize: show success toast and clear selection
   - While applying: show loading state on the Apply button

ACCEPTANCE CRITERIA:
- Can select individual rows with checkboxes
- "Select All" checkbox in header selects/deselects all visible rows
- When 1+ rows selected: batch toolbar appears with category dropdown and Apply button
- Select a category → click Apply → all selected transactions update to that category
- Table refreshes showing new categories without full page reload
- Selection is cleared after successful batch operation
- "Clear Selection" link/button deselects all

DO NOT:
- Remove or change the existing from/to batch operations in the toolbar
- Change any backend code
- Change the individual row categorization (single-row dropdown should still work)
```

---

### AGENT PROMPT 1.5 — Map: Edit and Remove Location Pins

**Estimated time:** 4–6 hours
**Files to touch:** 3 files (1 backend service, 1 backend router, 1 frontend component)
**Can run in parallel with:** All other Sprint 1 prompts

---

```
You are working on the Owl Investigation Platform — a React/FastAPI legal investigation tool.

TASK: Allow users to right-click map location markers to edit the location name/coordinates
or remove the location pin entirely (without deleting the entity from the graph).

CODEBASE CONTEXT:
- Backend: FastAPI/Python, Neo4j graph database
- Frontend: React 18, Leaflet maps (react-leaflet)
- Project root: /Users/neilbyrne/Documents/Owl/owl-n4j

KEY FILES TO MODIFY:

BACKEND:
- /backend/services/neo4j_service.py — add two new methods
- /backend/routers/graph.py — add two new endpoints

FRONTEND:
- /frontend/src/components/MapView.jsx — add right-click context menu on markers
  (first 100+ lines show imports and color constants; marker rendering is further in the file)

BACKEND CHANGES:

### 1. In neo4j_service.py — add two methods to the Neo4jService class:

```python
async def update_entity_location(self, node_key: str, case_id: str,
                                  location_name: str = None,
                                  latitude: float = None,
                                  longitude: float = None) -> dict:
    """Update location properties on an entity node."""
    async with self.driver.session() as session:
        result = await session.run("""
            MATCH (n {key: $key, case_id: $case_id})
            SET n.location_name = $location_name,
                n.latitude = $latitude,
                n.longitude = $longitude
            RETURN n.key as key, n.name as name,
                   n.location_name as location_name,
                   n.latitude as latitude,
                   n.longitude as longitude
        """, key=node_key, case_id=case_id,
             location_name=location_name,
             latitude=latitude, longitude=longitude)
        record = await result.single()
        return dict(record) if record else None

async def remove_entity_location(self, node_key: str, case_id: str) -> bool:
    """Remove location data from entity (entity stays in graph, just no map pin)."""
    async with self.driver.session() as session:
        await session.run("""
            MATCH (n {key: $key, case_id: $case_id})
            REMOVE n.latitude, n.longitude, n.location_name
        """, key=node_key, case_id=case_id)
        return True
```

Note: Check how the existing neo4j_service methods handle sessions — use the same pattern
already in the file (it may use a different session management approach).

### 2. In graph.py router — add two new endpoints:

Look at existing PUT endpoint patterns in the file (e.g., around PUT /graph/node/{node_key}).
Follow the exact same structure for authentication, case_id validation, and error handling.

```python
class UpdateLocationRequest(BaseModel):
    case_id: str
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

@router.put("/node/{node_key}/location")
async def update_node_location(
    node_key: str,
    request: UpdateLocationRequest,
    # ... match existing auth params pattern
):
    result = await neo4j_service.update_entity_location(
        node_key, request.case_id,
        request.location_name, request.latitude, request.longitude
    )
    if not result:
        raise HTTPException(status_code=404, detail="Node not found")
    return result

@router.delete("/node/{node_key}/location")
async def remove_node_location(
    node_key: str,
    case_id: str,
    # ... match existing auth params pattern
):
    await neo4j_service.remove_entity_location(node_key, case_id)
    return {"success": True, "message": "Location removed"}
```

FRONTEND CHANGES:

### 3. In MapView.jsx — add right-click context menu on markers:

Read the existing marker rendering code carefully. Leaflet markers likely use <Marker> from react-leaflet.

a) Add state for context menu:
```javascript
const [contextMenu, setContextMenu] = useState(null);
// { nodeKey, nodeName, x, y } or null

const [editingLocation, setEditingLocation] = useState(null);
// { nodeKey, nodeName, locationName, lat, lng } or null
```

b) Add right-click handler to each <Marker>:
```javascript
eventHandlers={{
  contextmenu: (e) => {
    e.originalEvent.preventDefault();
    setContextMenu({
      nodeKey: location.key,  // adjust to match your data structure
      nodeName: location.name,
      x: e.originalEvent.clientX,
      y: e.originalEvent.clientY
    });
  }
}}
```

c) Render context menu (as a fixed-position div):
```jsx
{contextMenu && (
  <div
    className="fixed bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-[9999]"
    style={{ left: contextMenu.x, top: contextMenu.y }}
    onMouseLeave={() => setContextMenu(null)}
  >
    <button
      className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 flex items-center gap-2"
      onClick={() => { setEditingLocation({...contextMenu}); setContextMenu(null); }}
    >
      ✏️ Edit Location
    </button>
    <button
      className="w-full px-4 py-2 text-left text-sm hover:bg-red-50 text-red-600 flex items-center gap-2"
      onClick={() => handleRemoveLocation(contextMenu.nodeKey)}
    >
      🗑️ Remove from Map
    </button>
  </div>
)}
```

d) Location Editor Modal:
```jsx
{editingLocation && (
  <div className="fixed inset-0 bg-black/50 z-[9998] flex items-center justify-center">
    <div className="bg-white rounded-lg p-6 w-96 shadow-xl">
      <h3 className="font-semibold text-lg mb-4">Edit Location — {editingLocation.nodeName}</h3>
      <div className="space-y-3">
        <div>
          <label className="text-sm font-medium text-gray-700">Location Name</label>
          <input type="text" className="mt-1 w-full border rounded-md px-3 py-2 text-sm"
            value={editingLocation.locationName || ''}
            onChange={(e) => setEditingLocation(prev => ({...prev, locationName: e.target.value}))}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-sm font-medium text-gray-700">Latitude</label>
            <input type="number" step="0.000001" className="mt-1 w-full border rounded-md px-3 py-2 text-sm"
              value={editingLocation.lat || ''}
              onChange={(e) => setEditingLocation(prev => ({...prev, lat: parseFloat(e.target.value)}))}
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Longitude</label>
            <input type="number" step="0.000001" className="mt-1 w-full border rounded-md px-3 py-2 text-sm"
              value={editingLocation.lng || ''}
              onChange={(e) => setEditingLocation(prev => ({...prev, lng: parseFloat(e.target.value)}))}
            />
          </div>
        </div>
      </div>
      <div className="flex gap-3 mt-6">
        <button onClick={handleSaveLocation} className="flex-1 bg-blue-600 text-white rounded-md py-2 text-sm font-medium">
          Save Changes
        </button>
        <button onClick={() => setEditingLocation(null)} className="flex-1 border rounded-md py-2 text-sm">
          Cancel
        </button>
      </div>
    </div>
  </div>
)}
```

e) Handler functions:
```javascript
const handleRemoveLocation = async (nodeKey) => {
  setContextMenu(null);
  // Call DELETE /api/graph/node/{nodeKey}/location?case_id={caseId}
  // On success: remove the location from local state so marker disappears immediately
  // without needing to reload all data
};

const handleSaveLocation = async () => {
  // Call PUT /api/graph/node/{editingLocation.nodeKey}/location
  // Body: { case_id: caseId, location_name, latitude, longitude }
  // On success: update local state and close modal
  setEditingLocation(null);
};
```

Add the API calls using the existing fetch pattern used elsewhere in the file
(look for how other components call /api/graph/* endpoints for the pattern).

ACCEPTANCE CRITERIA:
- Right-click on any map marker → context menu appears with "Edit Location" and "Remove from Map"
- Edit Location → modal opens with current name, lat, lng pre-filled
- Save → marker moves to new coordinates and name updates (no page refresh needed)
- Remove from Map → marker disappears immediately; entity still exists in graph/table views
- Context menu dismisses when mouse leaves it
- No crashes or errors in console

DO NOT:
- Delete entities from the graph (only remove location properties)
- Change any other map functionality
- Modify the entity detail panel or graph view
```

---

## SPRINT 2 — High Impact Features

---

### AGENT PROMPT 2.1 — Financial Dashboard: Editable Transaction Amounts

**Estimated time:** 1 day
**Files to touch:** 3 files (neo4j service, financial router, FinancialTable)
**Depends on:** Nothing
**⚠️ Important:** Must preserve original amounts for legal audit trail

---

```
You are working on the Owl Investigation Platform — a React/FastAPI legal investigation tool.

TASK: Allow attorneys to manually correct transaction amounts shown in the Financial Dashboard.
Transaction amounts extracted by AI may be wrong; attorneys need to correct them.
CRITICAL: Must preserve the original AI-extracted amount as an audit trail.

CODEBASE CONTEXT:
- Backend: FastAPI/Python, Neo4j
- Frontend: React 18, Tailwind CSS
- Project root: /Users/neilbyrne/Documents/Owl/owl-n4j

EXISTING PATTERN TO FOLLOW:
The `update_transaction_details` endpoint already handles purpose/notes updates.
Follow its exact pattern for the new amount endpoint.

- Existing service method: neo4j_service.update_transaction_details()
- Existing endpoint: PUT /api/financial/details/{node_key}
- Existing API call: api.financial.updateDetails(nodeKey, {caseId, purpose, notes})
- Transaction display is in: /frontend/src/components/financial/FinancialTable.jsx

KEY FILES TO MODIFY:
- /backend/services/neo4j_service.py
- /backend/routers/financial.py
- /frontend/src/components/financial/FinancialTable.jsx

BACKEND CHANGES:

### 1. neo4j_service.py — add new method:

Find the update_transaction_details method in neo4j_service.py and add a new method
immediately after it with the same session/driver pattern:

```python
async def update_transaction_amount(
    self, node_key: str, case_id: str,
    new_amount: float, correction_reason: str = None
) -> dict:
    """
    Update a transaction's amount while preserving the original for audit trail.
    Stores: amount (new), original_amount (preserved), amount_corrected (flag).
    """
    async with self.driver.session() as session:
        # First, get the current amount to preserve as original
        result = await session.run("""
            MATCH (n {key: $key, case_id: $case_id})
            RETURN n.amount as current_amount,
                   n.original_amount as existing_original
        """, key=node_key, case_id=case_id)
        record = await result.single()
        if not record:
            return None

        # Only set original_amount on FIRST correction (preserve the AI-extracted value)
        original_amount = record['existing_original'] if record['existing_original'] else record['current_amount']

        # Apply the correction
        update_result = await session.run("""
            MATCH (n {key: $key, case_id: $case_id})
            SET n.amount = $new_amount,
                n.original_amount = $original_amount,
                n.amount_corrected = true,
                n.correction_reason = $correction_reason
            RETURN n.key as key, n.amount as amount,
                   n.original_amount as original_amount,
                   n.correction_reason as correction_reason
        """, key=node_key, case_id=case_id,
             new_amount=new_amount,
             original_amount=original_amount,
             correction_reason=correction_reason)

        record = await update_result.single()
        return dict(record) if record else None
```

Use the same async/session pattern used in surrounding methods in the file.

### 2. financial.py router — add new endpoint:

Find DetailsRequest model and the PUT /details/{node_key} endpoint.
Add a new endpoint immediately after it, following the exact same structure:

```python
class UpdateAmountRequest(BaseModel):
    case_id: str
    new_amount: float
    correction_reason: Optional[str] = None

@router.put("/transactions/{node_key}/amount")
async def update_transaction_amount(
    node_key: str,
    request: UpdateAmountRequest,
    # ... copy auth parameters from the existing details endpoint
):
    if request.new_amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be a positive number")

    result = await neo4j_service.update_transaction_amount(
        node_key=node_key,
        case_id=request.case_id,
        new_amount=request.new_amount,
        correction_reason=request.correction_reason
    )
    if not result:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return result
```

Also add the API call to the frontend api.js file:
In the financial section (around line 838-850), add:
```javascript
updateAmount: async (nodeKey, { caseId, newAmount, correctionReason }) => {
  const response = await fetchAPI(`/api/financial/transactions/${nodeKey}/amount`, {
    method: 'PUT',
    body: JSON.stringify({
      case_id: caseId,
      new_amount: newAmount,
      correction_reason: correctionReason
    })
  });
  return response;
},
```

FRONTEND CHANGES:

### 3. FinancialTable.jsx — add inline amount editor:

a) Find where the Amount column is rendered in the table row (look for `formatAmount` call or
   the amount display cell).

b) Replace the static amount display with an editable component:

```jsx
// AmountCell component (add inside or before the main component)
const AmountCell = ({ transaction, caseId, onAmountChange }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const handleStartEdit = () => {
    setEditValue(String(transaction.amount || ''));
    setIsEditing(true);
  };

  const handleSave = async () => {
    const newAmount = parseFloat(editValue.replace(/[,$]/g, ''));
    if (isNaN(newAmount) || newAmount <= 0) return;

    setIsSaving(true);
    try {
      await api.financial.updateAmount(transaction.node_key, {
        caseId,
        newAmount,
        correctionReason: 'Manual correction by attorney'
      });
      onAmountChange(transaction.node_key, newAmount);
    } finally {
      setIsSaving(false);
      setIsEditing(false);
    }
  };

  if (isEditing) {
    return (
      <div className="flex items-center gap-1">
        <input
          autoFocus
          type="number"
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleSave(); if (e.key === 'Escape') setIsEditing(false); }}
          className="w-28 border rounded px-2 py-0.5 text-sm"
        />
        <button onClick={handleSave} disabled={isSaving} className="text-green-600 text-xs">✓</button>
        <button onClick={() => setIsEditing(false)} className="text-gray-400 text-xs">✕</button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1 group cursor-pointer" onClick={handleStartEdit}>
      <span className={transaction.amount_corrected ? 'font-medium' : ''}>
        {formatAmount(transaction.amount)}
      </span>
      {transaction.amount_corrected && (
        <span
          className="text-amber-500 text-xs"
          title={`Original: ${formatAmount(transaction.original_amount)} — ${transaction.correction_reason || 'Manually corrected'}`}
        >
          ✎
        </span>
      )}
      <span className="opacity-0 group-hover:opacity-100 text-gray-400 text-xs ml-1">✏️</span>
    </div>
  );
};
```

c) In the table row rendering, replace the amount display cell with:
```jsx
<AmountCell
  transaction={transaction}
  caseId={caseId}
  onAmountChange={(nodeKey, newAmount) => {
    // Update local state so UI reflects change immediately
    // Find the pattern used by other onXChange handlers in this component
  }}
/>
```

ACCEPTANCE CRITERIA:
- Click on any amount in the financial table → it becomes an editable input
- Type new amount → press Enter or ✓ → amount updates in table
- Corrected amounts show a ✎ amber indicator
- Hover the ✎ icon → tooltip shows original AI-extracted amount and correction note
- Press Escape → editing cancels, original value restored
- Refresh page → corrected amount persists (stored in Neo4j)
- Original amount is never lost (stored in node.original_amount)

DO NOT:
- Remove original amounts from the database
- Change the category or from/to editing functionality
- Modify any other financial endpoints
```

---

### AGENT PROMPT 2.2 — Entity Summary Panel on Case Dashboard

**Estimated time:** 1–2 days
**Files to touch:** 3 files (neo4j service, graph router, new React component + CaseOverviewView)
**Depends on:** Nothing

---

```
You are working on the Owl Investigation Platform — a React/FastAPI legal investigation tool.

TASK: Add an "Entities" section to the Case Dashboard (CaseOverviewView) showing a structured
list of all entities in the case — People, Companies, Banks, Accounts, Organisations —
with their summaries, fact counts, and insight counts.

CODEBASE CONTEXT:
- Backend: FastAPI/Python, Neo4j
- Frontend: React 18, Tailwind CSS
- Project root: /Users/neilbyrne/Documents/Owl/owl-n4j
- Frontend source: /Users/neilbyrne/Documents/Owl/owl-n4j/frontend/src

KEY FILES TO MODIFY:
- /backend/services/neo4j_service.py — add get_case_entity_summary() method
- /backend/routers/graph.py — add GET /graph/cases/{case_id}/entity-summary endpoint
- /frontend/src/components/workspace/CaseOverviewView.jsx — add section
- CREATE NEW: /frontend/src/components/workspace/EntitySummarySection.jsx

BACKEND CHANGES:

### 1. neo4j_service.py — add method:

Add this method to the Neo4jService class, following the same session/driver pattern
used in surrounding methods:

```python
async def get_case_entity_summary(self, case_id: str) -> list:
    """
    Return a summary of all significant entities in a case.
    Groups by type: Person, Company, Organisation, Bank, BankAccount
    Returns name, type, summary snippet, verified_facts count, ai_insights count.
    """
    async with self.driver.session() as session:
        result = await session.run("""
            MATCH (n {case_id: $case_id})
            WHERE (n:Person OR n:Company OR n:Organisation OR n:Bank OR n:BankAccount)
              AND n.name IS NOT NULL
            RETURN
                n.key as key,
                n.name as name,
                labels(n)[0] as type,
                n.summary as summary,
                n.verified_facts as verified_facts,
                n.ai_insights as ai_insights,
                size(COALESCE(n.verified_facts, [])) as facts_count,
                size(COALESCE(n.ai_insights, [])) as insights_count
            ORDER BY type, n.name
        """, case_id=case_id)

        records = []
        async for record in result:
            vf = record['verified_facts']
            ai = record['ai_insights']
            # verified_facts and ai_insights are stored as JSON strings in some cases
            facts_count = len(vf) if isinstance(vf, list) else 0
            insights_count = len(ai) if isinstance(ai, list) else 0

            records.append({
                'key': record['key'],
                'name': record['name'],
                'type': record['type'],
                'summary': record['summary'] or '',
                'facts_count': facts_count,
                'insights_count': insights_count,
            })
        return records
```

Note: The verified_facts and ai_insights fields may be stored as JSON strings.
Check how other service methods parse them (look for parse_json_field usage) and
use the same approach.

### 2. graph.py router — add endpoint:

Find the /graph/summary endpoint pattern and add a new endpoint following the same
authentication and error handling pattern:

```python
@router.get("/cases/{case_id}/entity-summary")
async def get_case_entity_summary(
    case_id: str,
    # ... copy auth params from existing endpoints
):
    entities = await neo4j_service.get_case_entity_summary(case_id)
    return {"entities": entities, "total": len(entities)}
```

FRONTEND CHANGES:

### 3. Create new file: /frontend/src/components/workspace/EntitySummarySection.jsx

```jsx
import React, { useState, useEffect } from 'react';
import { Users, Building2, Landmark, CreditCard, Network } from 'lucide-react';

const TYPE_CONFIG = {
  Person: { icon: Users, label: 'People', color: 'text-blue-600 bg-blue-50' },
  Company: { icon: Building2, label: 'Companies', color: 'text-red-600 bg-red-50' },
  Organisation: { icon: Network, label: 'Organisations', color: 'text-purple-600 bg-purple-50' },
  Bank: { icon: Landmark, label: 'Banks', color: 'text-amber-600 bg-amber-50' },
  BankAccount: { icon: CreditCard, label: 'Accounts', color: 'text-green-600 bg-green-50' },
};

const TABS = ['All', 'People', 'Companies', 'Organisations', 'Banks', 'Accounts'];

export default function EntitySummarySection({ caseId, onEntityClick }) {
  const [entities, setEntities] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('name'); // 'name', 'type', 'facts', 'insights'

  useEffect(() => {
    const loadEntities = async () => {
      setIsLoading(true);
      try {
        const response = await fetch(`/api/graph/cases/${caseId}/entity-summary`);
        const data = await response.json();
        setEntities(data.entities || []);
      } catch (err) {
        console.error('Failed to load entities:', err);
      } finally {
        setIsLoading(false);
      }
    };
    if (caseId) loadEntities();
  }, [caseId]);

  // Count per type for tab badges
  const typeCounts = entities.reduce((acc, e) => {
    acc[e.type] = (acc[e.type] || 0) + 1;
    return acc;
  }, {});

  // Filter by tab and search
  const filtered = entities
    .filter(e => {
      if (activeTab === 'People') return e.type === 'Person';
      if (activeTab === 'Companies') return e.type === 'Company';
      if (activeTab === 'Organisations') return e.type === 'Organisation';
      if (activeTab === 'Banks') return e.type === 'Bank';
      if (activeTab === 'Accounts') return e.type === 'BankAccount';
      return true;
    })
    .filter(e => !searchQuery || e.name.toLowerCase().includes(searchQuery.toLowerCase()))
    .sort((a, b) => {
      if (sortBy === 'facts') return b.facts_count - a.facts_count;
      if (sortBy === 'insights') return b.insights_count - a.insights_count;
      if (sortBy === 'type') return a.type.localeCompare(b.type);
      return a.name.localeCompare(b.name);
    });

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-gray-900">Key Entities</h3>
          <p className="text-xs text-gray-500 mt-0.5">People, companies, and organizations identified in case documents</p>
        </div>
        <span className="text-sm text-gray-400">{entities.length} total</span>
      </div>

      {/* Tabs */}
      <div className="px-5 pt-3 pb-0 flex gap-1 border-b border-gray-100 overflow-x-auto">
        {TABS.map(tab => {
          const typeKey = tab === 'People' ? 'Person' : tab === 'Companies' ? 'Company' :
                          tab === 'Organisations' ? 'Organisation' : tab === 'Accounts' ? 'BankAccount' : tab;
          const count = tab === 'All' ? entities.length : (typeCounts[typeKey] || 0);
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px whitespace-nowrap flex items-center gap-1.5 ${
                activeTab === tab
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab}
              {count > 0 && (
                <span className={`text-xs rounded-full px-1.5 py-0.5 ${
                  activeTab === tab ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-500'
                }`}>{count}</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Search + Sort */}
      <div className="px-5 py-3 flex gap-3 border-b border-gray-50">
        <input
          type="text"
          placeholder="Search entities..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="flex-1 border border-gray-200 rounded-md px-3 py-1.5 text-sm"
        />
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="border border-gray-200 rounded-md px-2 py-1.5 text-sm"
        >
          <option value="name">Sort: Name</option>
          <option value="type">Sort: Type</option>
          <option value="facts">Sort: Most Facts</option>
          <option value="insights">Sort: Most Insights</option>
        </select>
      </div>

      {/* Entity List */}
      <div className="divide-y divide-gray-50 max-h-96 overflow-y-auto">
        {isLoading ? (
          <div className="py-8 text-center text-gray-400 text-sm">Loading entities...</div>
        ) : filtered.length === 0 ? (
          <div className="py-8 text-center text-gray-400 text-sm">No entities found</div>
        ) : filtered.map(entity => {
          const config = TYPE_CONFIG[entity.type] || TYPE_CONFIG.Person;
          const Icon = config.icon;
          return (
            <div
              key={entity.key}
              className="px-5 py-3 hover:bg-gray-50 cursor-pointer flex items-start gap-3"
              onClick={() => onEntityClick && onEntityClick(entity.key)}
            >
              <span className={`mt-0.5 p-1.5 rounded-md ${config.color} flex-shrink-0`}>
                <Icon size={14} />
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm text-gray-900 truncate">{entity.name}</span>
                  <span className="text-xs text-gray-400 flex-shrink-0">{config.label.slice(0, -1)}</span>
                </div>
                {entity.summary && (
                  <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{entity.summary}</p>
                )}
              </div>
              <div className="flex gap-3 flex-shrink-0 text-xs text-gray-400">
                {entity.facts_count > 0 && (
                  <span title="Verified facts">{entity.facts_count} facts</span>
                )}
                {entity.insights_count > 0 && (
                  <span title="AI insights">{entity.insights_count} insights</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

### 4. CaseOverviewView.jsx — integrate the new component:

Read the existing CaseOverviewView.jsx structure carefully (especially the scrollable content area
around lines 136-150).

Add the EntitySummarySection:
- Import it at the top of the file
- Add it in the scrollable content area, after the Client Profile section
- Pass `caseId={caseId}` prop
- Pass `onEntityClick` handler (can be a no-op initially, or open entity detail if that exists)

ACCEPTANCE CRITERIA:
- Case dashboard shows "Key Entities" section
- Tabs filter by entity type with count badges
- Search filters entities by name in real-time
- Sorting by name, type, facts count works
- Each entity shows: type icon, name, truncated summary, fact/insight counts
- Clicking an entity (optional if detail panel exists) navigates to entity detail
- Loading state shown while fetching
- Empty state shown if no entities in case

DO NOT:
- Remove or modify existing dashboard sections
- Change any existing entity or graph functionality
- Modify the graph view or table view components
```

---

### AGENT PROMPT 2.3 — AI Chat: Remove Document Limit

**Estimated time:** 4–6 hours
**Files to touch:** 2–3 backend files, 1 frontend file
**Depends on:** Nothing

---

```
You are working on the Owl Investigation Platform — a React/FastAPI legal investigation tool.

TASK: The AI chat currently limits how many documents it analyzes. Remove or raise this limit
so attorneys can analyze their full case document set in one conversation.

CODEBASE CONTEXT:
- Backend: FastAPI/Python
- Project root: /Users/neilbyrne/Documents/Owl/owl-n4j

KEY FILES TO INVESTIGATE AND MODIFY:
- /backend/services/rag_service.py — main RAG/chat service
- /backend/services/vector_db_service.py — ChromaDB vector search
- /frontend/src/components/ChatPanel.jsx — document selection UI

INVESTIGATION STEP (do this first before making changes):

Search these files for the following patterns and report exactly what you find:
- "n_results"
- "top_k"
- "limit="
- "[:10]" or "[:20]"
- "CHUNK_SEARCH_TOP_K"
- "VECTOR_SEARCH_TOP_K"
- "ENTITY_SEARCH_TOP_K"
- "max_docs"
- "max_documents"
- Document selector in ChatPanel that might cap the list

Known findings from codebase analysis:
- vector_db_service.py: search() has top_k=10, search_entities() has top_k=10, search_chunks() has top_k=15
- rag_service.py: uses CHUNK_SEARCH_TOP_K and VECTOR_SEARCH_TOP_K constants
- rag_service.py line 667: verified_facts[:10] — limits facts per entity
- rag_service.py line 486: filtered[:10] — limits search results sample

CHANGES TO MAKE:

### 1. vector_db_service.py — raise default top_k values:

Find the three search functions and increase defaults:
- search(query_embedding, top_k=10, ...) → change default to top_k=50
- search_entities(query_embedding, top_k=10, ...) → change default to top_k=50
- search_chunks(query_embedding, top_k=15, ...) → change default to top_k=50

### 2. rag_service.py — raise all search limits:

For any TOP_K constants or defaults you find:
- CHUNK_SEARCH_TOP_K → set to 50 (was probably 10 or 15)
- VECTOR_SEARCH_TOP_K → set to 50
- ENTITY_SEARCH_TOP_K → set to 50

For the line verified_facts[:10]:
- Change to verified_facts[:20] (more facts per entity in context)

For any filtered[:10] result slicing:
- Change to filtered[:50] or remove the slice if it's just debug logging

### 3. Context token budget:

Find the CONTEXT_TOKEN_BUDGET constant in rag_service.py.
- If it's set to a value that would limit 50 document chunks, increase it
- GPT-4 supports 128,000 tokens context window
- A reasonable budget for context is 80,000 tokens (leaving room for the question and response)
- Set CONTEXT_TOKEN_BUDGET = 80000 (or whatever the current variable name is)

### 4. ChatPanel.jsx — check document selector:

Read the document selection UI in ChatPanel.jsx.
If there's a checkbox list of documents that is visually or programmatically capped at 10:
- Remove the cap
- Add a "Select All Documents" toggle checkbox at the top of the list
- If the list is very long (50+ docs), add a search/filter input

ACCEPTANCE CRITERIA:
- AI chat can analyze all documents in a case (not capped at 10)
- "Select All" toggle selects every document in the case
- Response quality remains good with larger document sets
- No timeout errors on normal hardware with up to 50 documents
- Token budget errors are handled gracefully (e.g., "Too many documents selected, please narrow your selection" message if limit genuinely exceeded)

NOTE: If Ollama local models are used (smaller context windows ~32K tokens), the larger top_k
values may cause issues. Add a note in the code comment:
"# Increased from 10 to 50 — works with GPT-4 128K. For Ollama models with smaller context,
# reduce to 15-20 if you experience context length errors"

DO NOT:
- Change how documents are stored or indexed
- Modify the ingestion pipeline
- Break the existing chat functionality for cases with fewer than 10 documents
```

---

### AGENT PROMPT 2.4 — Clarify Case Dashboard: Files vs Evidence

**Estimated time:** 4–6 hours
**Files to touch:** 2–3 frontend workspace components
**Depends on:** Nothing (UI-only change)

---

```
You are working on the Owl Investigation Platform — a React/FastAPI legal investigation tool.

TASK: The Case Dashboard has a confusing distinction between "Case Files" and "All Evidence"
that users (attorneys) don't understand. Clarify the UI labels, add descriptive subtitles,
and reorder sections to make the information hierarchy logical.

CODEBASE CONTEXT:
- Frontend: React 18, Tailwind CSS
- Project root: /Users/neilbyrne/Documents/Owl/owl-n4j
- Frontend source: /Users/neilbyrne/Documents/Owl/owl-n4j/frontend/src

KEY FILES TO READ AND MODIFY:
- /frontend/src/components/workspace/CaseOverviewView.jsx — main dashboard layout
- /frontend/src/components/workspace/DocumentsSection.jsx — "Case Files" section
- /frontend/src/components/workspace/AllEvidenceSection.jsx — "All Evidence" section

STEP 1 — READ AND UNDERSTAND BEFORE CHANGING:

Read all three files completely. Understand exactly:
1. What data does DocumentsSection actually display? (What API does it call? What does it show?)
2. What data does AllEvidenceSection actually display? (What API? What does it show?)
3. Are they showing different data, or the same data differently?
4. What does the user see when looking at the dashboard right now?

STEP 2 — APPLY THESE CHANGES:

Based on what you find, apply these clarifications:

A) Rename "Case Files" section:
   - New heading: "Uploaded Documents"
   - Add subtitle below heading: "Files you've added to this case and processed for analysis"
   - If there's an upload button, keep it — it belongs here

B) Rename "All Evidence" section:
   - If it shows extracted entities/relationships: rename to "Extracted Evidence"
   - Add subtitle: "Entities and relationships automatically identified from your uploaded documents"
   - If it shows something else (be honest about what you find), rename it to accurately describe what it actually shows

C) In CaseOverviewView.jsx, reorder sections so the user journey is logical:
   1. Case Summary / Client Profile (who is this case about?)
   2. Uploaded Documents (what documents are in this case?)
   3. Key Entities [new section from Prompt 2.2 if built, otherwise skip] (what was found?)
   4. Notes / Tasks / Timeline (working materials)

D) If "Case Files" and "All Evidence" show essentially the same thing from different angles:
   - Consider merging them into one clear "Documents" section
   - Add a simple explanation: "X documents uploaded · Y entities extracted"
   - This is better than two confusing sections

E) Add a help tooltip (?) icon next to any section title that might be confusing:
   - Hover tooltip: clear one-sentence explanation of what the section shows

STYLING:
- Use the existing Tailwind patterns and color scheme in the files
- Section headings should be consistent (same font size, weight) across all sections
- Subtitles should be text-sm text-gray-500

ACCEPTANCE CRITERIA:
- An attorney seeing the dashboard for the first time understands immediately what
  "Uploaded Documents" means vs. "Extracted Evidence"
- No section uses the word "Evidence" to mean "uploaded files" (a file is not evidence —
  the extracted facts from it are evidence)
- The section order flows logically from "what is this case" → "what documents exist" →
  "what was found" → "working tools"
- No functionality is broken — all existing buttons and actions still work
- Existing export/include checkboxes still work (they're in the IncludeBar component)

DO NOT:
- Change any backend code
- Remove any functionality
- Change what data is displayed — only labels, descriptions, and order
- Break the section export/include functionality
```

---

### AGENT PROMPT 2.5 — Export Financial Transactions to PDF

**Estimated time:** 1–2 days
**Files to touch:** 3 files (new service, financial router, FinancialView)
**Depends on:** WeasyPrint is already installed

---

```
You are working on the Owl Investigation Platform — a React/FastAPI legal investigation tool.

TASK: Add a "Export to PDF" button to the Financial Dashboard that generates a formatted PDF
of the current transaction view, including any manually corrected amounts and sub-transaction
groupings.

CODEBASE CONTEXT:
- Backend: FastAPI/Python
- Frontend: React 18, Tailwind CSS
- Project root: /Users/neilbyrne/Documents/Owl/owl-n4j
- WeasyPrint is already installed (pip package available)

EXISTING PATTERNS TO FOLLOW:
- Look at /backend/ingestion/scripts/generate_docx_report.py for how reports are currently generated
- Look at how the financial.py router fetches transactions (GET /api/financial endpoint)
- Look at how FinancialView.jsx handles filters — the PDF should respect the same filters

KEY FILES TO CREATE/MODIFY:
- CREATE: /backend/services/financial_export_service.py
- MODIFY: /backend/routers/financial.py — add export endpoint
- MODIFY: /frontend/src/components/financial/FinancialView.jsx — add export button
- MODIFY: /frontend/src/services/api.js — add export API call

BACKEND CHANGES:

### 1. Create /backend/services/financial_export_service.py:

```python
"""
Financial Transaction PDF Export Service
Generates formatted PDF reports of case financial transactions.
"""
import weasyprint
from datetime import datetime
from typing import Optional, List


def format_currency(amount) -> str:
    """Format a number as currency string."""
    if amount is None:
        return "N/A"
    try:
        return f"${float(amount):,.2f}"
    except (ValueError, TypeError):
        return str(amount)


def generate_financial_pdf(
    transactions: list,
    case_name: str,
    filters_description: str = "All transactions",
    categories_map: dict = None
) -> bytes:
    """
    Generate a PDF report of financial transactions.

    Args:
        transactions: List of transaction dicts from Neo4j
        case_name: Name of the case for the header
        filters_description: Human-readable description of active filters
        categories_map: Optional dict of category colors

    Returns:
        PDF file as bytes
    """

    # Build summary stats
    total_transactions = len(transactions)

    # Separate parent and child transactions for display
    parent_transactions = [t for t in transactions if not t.get('parent_transaction_key')]

    total_value = sum(
        float(t.get('amount', 0) or 0)
        for t in transactions
        if not t.get('parent_transaction_key')  # don't double-count sub-transactions
    )

    # Category breakdown
    category_counts = {}
    for t in transactions:
        cat = t.get('category', 'Uncategorized') or 'Uncategorized'
        category_counts[cat] = category_counts.get(cat, 0) + 1

    category_summary = ' | '.join([f"{cat} ({count})" for cat, count in
                                   sorted(category_counts.items(), key=lambda x: -x[1])[:5]])

    # Build transaction rows HTML
    def build_transaction_row(t, is_child=False):
        corrected = t.get('amount_corrected', False)
        original = t.get('original_amount')
        amount_display = format_currency(t.get('amount'))

        correction_note = ''
        if corrected and original:
            correction_note = f'<span class="correction-note" title="Original: {format_currency(original)}">†</span>'

        indent = 'child-row' if is_child else ''
        prefix = '↳ ' if is_child else ''

        name = t.get('name', '') or t.get('description', '') or 'Transaction'
        from_entity = t.get('from_entity_name', '') or t.get('from_name', '') or '—'
        to_entity = t.get('to_entity_name', '') or t.get('to_name', '') or '—'
        date = t.get('date', '') or t.get('transaction_date', '') or '—'
        category = t.get('category', '—') or '—'
        notes = t.get('notes', '') or t.get('purpose', '') or ''

        return f'''
        <tr class="{indent}">
            <td class="date-col">{date}</td>
            <td>{prefix}{from_entity}</td>
            <td>{to_entity}</td>
            <td class="amount-col">{amount_display}{correction_note}</td>
            <td><span class="category-badge">{category}</span></td>
            <td class="notes-col">{notes[:100] + '…' if len(notes) > 100 else notes}</td>
        </tr>
        '''

    # Build all rows, with sub-transactions indented under parents
    children_by_parent = {}
    for t in transactions:
        parent_key = t.get('parent_transaction_key')
        if parent_key:
            if parent_key not in children_by_parent:
                children_by_parent[parent_key] = []
            children_by_parent[parent_key].append(t)

    rows_html = ''
    for t in parent_transactions:
        rows_html += build_transaction_row(t, is_child=False)
        # Add children if this transaction has sub-transactions
        children = children_by_parent.get(t.get('key') or t.get('node_key'), [])
        for child in children:
            rows_html += build_transaction_row(child, is_child=True)

    has_corrections = any(t.get('amount_corrected') for t in transactions)
    correction_footnote = '<p class="footnote">† Amount has been manually corrected. Original AI-extracted value shown on hover.</p>' if has_corrections else ''

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 9pt; color: #1a1a2e; margin: 0; }}

  .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%); color: white; padding: 32px 40px 28px; }}
  .header .logo {{ font-size: 9pt; font-weight: 700; letter-spacing: 3px; text-transform: uppercase; color: #e94560; margin-bottom: 10px; }}
  .header h1 {{ font-size: 20pt; font-weight: 700; color: white; margin: 0 0 6px; }}
  .header .case-name {{ font-size: 12pt; color: rgba(255,255,255,0.7); margin-bottom: 20px; }}
  .header .meta {{ font-size: 8pt; color: rgba(255,255,255,0.5); }}
  .header .meta strong {{ color: rgba(255,255,255,0.8); }}

  .content {{ padding: 20px 40px 40px; }}

  .summary-box {{ background: #f7f9fc; border: 1px solid #e0e8f0; border-radius: 8px; padding: 16px 20px; margin-bottom: 20px; }}
  .summary-box h3 {{ font-size: 8pt; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: #0f3460; margin: 0 0 10px; }}
  .summary-stats {{ display: flex; gap: 32px; }}
  .stat {{ }}
  .stat .value {{ font-size: 16pt; font-weight: 700; color: #0f3460; }}
  .stat .label {{ font-size: 8pt; color: #888; margin-top: 2px; }}
  .category-line {{ font-size: 8.5pt; color: #666; margin-top: 10px; }}
  .filters-line {{ font-size: 8pt; color: #999; margin-top: 6px; }}

  table {{ width: 100%; border-collapse: collapse; margin-top: 4px; font-size: 8.5pt; }}
  th {{ background: #0f3460; color: white; padding: 8px 10px; text-align: left; font-weight: 600; font-size: 8pt; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid #eef0f3; vertical-align: top; }}
  tr:nth-child(even) td {{ background: #fafbfc; }}
  tr.child-row td {{ background: #f5f8ff; font-size: 8pt; color: #555; }}

  .date-col {{ white-space: nowrap; width: 80px; }}
  .amount-col {{ white-space: nowrap; font-weight: 600; text-align: right; width: 90px; }}
  .notes-col {{ color: #666; font-size: 8pt; }}

  .category-badge {{ background: #e8f0fe; color: #1a56db; border-radius: 3px; padding: 1px 5px; font-size: 7.5pt; white-space: nowrap; }}
  .correction-note {{ color: #e67e22; font-weight: 700; margin-left: 3px; cursor: help; }}

  .footnote {{ font-size: 7.5pt; color: #999; margin-top: 16px; border-top: 1px solid #eee; padding-top: 8px; }}

  @page {{
    size: A4 landscape;
    margin: 15mm 15mm 18mm;
    @bottom-right {{
      content: "Page " counter(page) " of " counter(pages);
      font-size: 7pt; color: #aaa; font-family: Arial, sans-serif;
    }}
    @bottom-left {{
      content: "Owl Investigation Platform · Financial Report · CONFIDENTIAL";
      font-size: 7pt; color: #aaa; font-family: Arial, sans-serif;
    }}
  }}
  @page :first {{
    @bottom-right {{ content: ""; }}
    @bottom-left {{ content: ""; }}
  }}
</style>
</head>
<body>

<div class="header">
  <div class="logo">🦉 Owl Investigation Platform</div>
  <h1>Financial Transaction Report</h1>
  <div class="case-name">{case_name}</div>
  <div class="meta">
    <strong>Generated:</strong> {datetime.now().strftime('%B %d, %Y at %I:%M %p')} &nbsp;·&nbsp;
    <strong>Classification:</strong> Attorney-Client Privileged &amp; Confidential
  </div>
</div>

<div class="content">
  <div class="summary-box">
    <h3>Summary</h3>
    <div class="summary-stats">
      <div class="stat">
        <div class="value">{total_transactions}</div>
        <div class="label">Transactions</div>
      </div>
      <div class="stat">
        <div class="value">{format_currency(total_value)}</div>
        <div class="label">Total Value</div>
      </div>
    </div>
    <div class="category-line">Categories: {category_summary}</div>
    <div class="filters-line">Filter: {filters_description}</div>
  </div>

  <table>
    <thead>
      <tr>
        <th>Date</th>
        <th>From</th>
        <th>To</th>
        <th style="text-align:right">Amount</th>
        <th>Category</th>
        <th>Notes / Purpose</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>

  {correction_footnote}
</div>

</body>
</html>"""

    doc = weasyprint.HTML(string=html)
    return doc.write_pdf()
```

### 2. financial.py router — add export endpoint:

```python
from fastapi.responses import Response
from backend.services.financial_export_service import generate_financial_pdf

@router.get("/export/pdf")
async def export_transactions_pdf(
    case_id: str,
    case_name: str = "Case",
    categories: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    entity_key: Optional[str] = None,
    # ... copy auth params from existing endpoints
):
    # Fetch transactions using existing service method (same as GET /api/financial)
    transactions = await neo4j_service.get_financial_transactions(
        case_id=case_id,
        types=None,
        start_date=start_date,
        end_date=end_date,
        categories=categories.split(',') if categories else None
    )

    # Build filter description for the PDF header
    filter_parts = []
    if categories: filter_parts.append(f"Categories: {categories}")
    if start_date: filter_parts.append(f"From: {start_date}")
    if end_date: filter_parts.append(f"To: {end_date}")
    if entity_key: filter_parts.append(f"Entity filter active")
    filters_desc = ' · '.join(filter_parts) if filter_parts else "All transactions"

    pdf_bytes = generate_financial_pdf(
        transactions=transactions,
        case_name=case_name,
        filters_description=filters_desc
    )

    from datetime import date
    filename = f"transactions_{case_name.replace(' ', '_')}_{date.today()}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
```

### 3. FinancialView.jsx — add Export button:

In the header/toolbar area (around lines 338-354), add an Export button:

```jsx
<button
  onClick={handleExportPDF}
  className="flex items-center gap-2 px-3 py-1.5 text-sm border border-gray-200 rounded-md hover:bg-gray-50"
>
  <Download size={14} /> Export PDF
</button>
```

Add the handler:
```javascript
const handleExportPDF = () => {
  // Build URL with current filters matching what's on screen
  const params = new URLSearchParams({ case_id: caseId, case_name: caseName });
  if (selectedCategories.length > 0) params.set('categories', selectedCategories.join(','));
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);

  // Open in new tab to trigger download
  window.open(`/api/financial/export/pdf?${params.toString()}`, '_blank');
};
```

Import `Download` from lucide-react (add to existing imports).

ACCEPTANCE CRITERIA:
- "Export PDF" button appears in Financial Dashboard toolbar
- Clicking it generates and downloads a PDF
- PDF shows: case name, generation date, summary stats, all transaction rows
- Current filters (categories, date range) are reflected in the PDF
- Corrected amounts show a † marker with original value note in footnote
- Sub-transactions (if any) are indented under their parent
- PDF is A4 landscape format (fits wide tables)
- "Attorney-Client Privileged" disclaimer appears in footer
- Works with 0 to 500+ transactions

DO NOT:
- Change any existing financial data fetching
- Require any npm package installation (use only existing packages)
- Change the financial table display or other UI
```

---

## SPRINT 3 — Complex New Systems

---

### AGENT PROMPT 3.1 — Sub-Transactions: Group Related Transactions

**Estimated time:** 5–7 days
**Files to touch:** neo4j_service, financial router, api.js, FinancialTable, new modal
**Depends on:** Prompt 2.1 (amount editing) ideally done first
**⚠️ Schema change — test on a copy of the case first**

---

```
You are working on the Owl Investigation Platform — a React/FastAPI legal investigation tool.

TASK: Allow attorneys to group related transactions under a parent transaction.
Example: A $1.3M house purchase can be broken down into: Loan ($900K) + Gift ($200K) + Fees ($200K).
The parent transaction ($1.3M) contains the children, showing how the total is composed.

CODEBASE CONTEXT:
- Backend: FastAPI/Python, Neo4j graph database
- Frontend: React 18, Tailwind CSS
- Project root: /Users/neilbyrne/Documents/Owl/owl-n4j

DATA MODEL DESIGN:
- Use a property on child transaction nodes: `parent_transaction_key` (string)
- Create a Neo4j relationship: (child)-[:PART_OF]->(parent)
- This is a soft link — both transactions remain full nodes in the graph
- Parent transaction gets `is_parent: true` flag when it has children

KEY FILES TO MODIFY:
- /backend/services/neo4j_service.py — 3 new methods
- /backend/routers/financial.py — 3 new endpoints
- /frontend/src/services/api.js — 3 new API calls
- /frontend/src/components/financial/FinancialTable.jsx — expandable parent rows
- CREATE: /frontend/src/components/financial/SubTransactionModal.jsx

BACKEND CHANGES:

### 1. neo4j_service.py — add 3 methods to Neo4jService class:

```python
async def link_sub_transaction(
    self, parent_key: str, child_key: str, case_id: str
) -> bool:
    """Mark child_key as a sub-transaction of parent_key."""
    async with self.driver.session() as session:
        # Validate both exist and belong to case
        check = await session.run("""
            MATCH (parent {key: $parent_key, case_id: $case_id})
            MATCH (child {key: $child_key, case_id: $case_id})
            RETURN parent.key as pk, child.key as ck
        """, parent_key=parent_key, child_key=child_key, case_id=case_id)
        record = await check.single()
        if not record:
            return False

        # Create the relationship and set properties
        await session.run("""
            MATCH (parent {key: $parent_key, case_id: $case_id})
            MATCH (child {key: $child_key, case_id: $case_id})
            MERGE (child)-[:PART_OF]->(parent)
            SET child.parent_transaction_key = $parent_key,
                parent.is_parent = true
        """, parent_key=parent_key, child_key=child_key, case_id=case_id)
        return True

async def unlink_sub_transaction(
    self, child_key: str, case_id: str
) -> bool:
    """Remove a child transaction from its parent grouping."""
    async with self.driver.session() as session:
        await session.run("""
            MATCH (child {key: $child_key, case_id: $case_id})-[r:PART_OF]->(parent)
            WITH child, parent, r
            DELETE r
            SET child.parent_transaction_key = null
            WITH parent
            // Check if parent has any remaining children
            OPTIONAL MATCH (remaining)-[:PART_OF]->(parent)
            WITH parent, count(remaining) as remaining_count
            SET parent.is_parent = CASE WHEN remaining_count > 0 THEN true ELSE false END
        """, child_key=child_key, case_id=case_id)
        return True

async def get_transaction_children(
    self, parent_key: str, case_id: str
) -> list:
    """Get all sub-transactions for a given parent transaction."""
    async with self.driver.session() as session:
        result = await session.run("""
            MATCH (child)-[:PART_OF]->(parent {key: $parent_key, case_id: $case_id})
            RETURN child.key as key, child.name as name, child.amount as amount,
                   child.date as date, child.category as category,
                   child.from_entity_name as from_entity_name,
                   child.to_entity_name as to_entity_name,
                   child.purpose as purpose, child.notes as notes,
                   child.amount_corrected as amount_corrected,
                   child.original_amount as original_amount
            ORDER BY child.date
        """, parent_key=parent_key, case_id=case_id)

        children = []
        async for record in result:
            children.append(dict(record))
        return children
```

Also update get_financial_transactions() to include `is_parent` and `parent_transaction_key`
in its RETURN clause so the frontend knows which transactions are parents/children.

### 2. financial.py router — add 3 endpoints:

```python
class LinkSubTransactionRequest(BaseModel):
    case_id: str
    child_key: str

@router.post("/transactions/{parent_key}/sub-transactions")
async def link_sub_transaction(
    parent_key: str,
    request: LinkSubTransactionRequest,
    # ... copy auth params
):
    if parent_key == request.child_key:
        raise HTTPException(status_code=400, detail="Cannot link a transaction to itself")
    success = await neo4j_service.link_sub_transaction(
        parent_key, request.child_key, request.case_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Transaction(s) not found")
    return {"success": True}

@router.delete("/transactions/{child_key}/parent")
async def unlink_sub_transaction(
    child_key: str,
    case_id: str,
    # ... copy auth params
):
    await neo4j_service.unlink_sub_transaction(child_key, case_id)
    return {"success": True}

@router.get("/transactions/{parent_key}/sub-transactions")
async def get_sub_transactions(
    parent_key: str,
    case_id: str,
    # ... copy auth params
):
    children = await neo4j_service.get_transaction_children(parent_key, case_id)
    return {"children": children, "count": len(children)}
```

### 3. Add to api.js financial section:

```javascript
linkSubTransaction: async (parentKey, childKey, caseId) => {
  return fetchAPI(`/api/financial/transactions/${parentKey}/sub-transactions`, {
    method: 'POST',
    body: JSON.stringify({ case_id: caseId, child_key: childKey })
  });
},
unlinkSubTransaction: async (childKey, caseId) => {
  return fetchAPI(`/api/financial/transactions/${childKey}/parent?case_id=${caseId}`, {
    method: 'DELETE'
  });
},
getSubTransactions: async (parentKey, caseId) => {
  return fetchAPI(`/api/financial/transactions/${parentKey}/sub-transactions?case_id=${caseId}`);
},
```

FRONTEND CHANGES:

### 4. FinancialTable.jsx — expandable parent rows:

Read the current table row rendering carefully.

For parent transactions (where `transaction.is_parent === true`):
- Add a ▶/▼ expand toggle button at the start of the row
- When expanded, fetch and show child rows indented below
- Parent row shows total amount (sum should equal children sum — show warning if not)
- Add visual indicator: slightly different background for parent rows

For all transactions, add a "Group as Sub-Transaction" option in the row actions dropdown:
- Opens SubTransactionModal to select a parent

For child transactions (where `transaction.parent_transaction_key` exists):
- Show indented with ↳ prefix
- Show "Remove from group" action in row actions

### 5. CREATE /frontend/src/components/financial/SubTransactionModal.jsx:

Build a modal for grouping transactions:

Props: `isOpen`, `onClose`, `parentTransaction`, `allTransactions`, `caseId`, `onSave`

Features:
- Shows the PARENT transaction at top (amount, name, from→to, date)
- Shows a list of all OTHER transactions with checkboxes to select as children
- Filters out: the parent itself, transactions already assigned to a different parent
- Shows running total of selected children vs. parent amount
- Warning if children total ≠ parent amount (not blocking, just informational)
- Save button: calls linkSubTransaction for each selected child
- Cancel button

```jsx
// Basic structure:
<div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center">
  <div className="bg-white rounded-xl w-3xl max-h-[80vh] overflow-hidden flex flex-col shadow-xl">

    {/* Header */}
    <div className="px-6 py-4 border-b">
      <h2 className="font-semibold text-lg">Group Sub-Transactions</h2>
      <p className="text-sm text-gray-500">Select transactions that are components of this transaction</p>
    </div>

    {/* Parent transaction display */}
    <div className="px-6 py-3 bg-blue-50 border-b">
      <div className="text-xs text-blue-600 font-medium mb-1">PARENT TRANSACTION</div>
      <div className="flex items-center justify-between">
        <span className="font-medium">{parentTransaction.name}</span>
        <span className="font-bold text-blue-700">{formatAmount(parentTransaction.amount)}</span>
      </div>
    </div>

    {/* Transaction list with checkboxes */}
    <div className="flex-1 overflow-y-auto divide-y">
      {eligibleTransactions.map(t => (
        <label key={t.node_key} className="flex items-center gap-3 px-6 py-2.5 hover:bg-gray-50 cursor-pointer">
          <input type="checkbox" checked={selectedKeys.includes(t.node_key)}
                 onChange={() => toggleSelection(t.node_key)} />
          <div className="flex-1">
            <span className="text-sm">{t.from_entity_name} → {t.to_entity_name}</span>
            <span className="text-xs text-gray-400 ml-2">{t.date}</span>
          </div>
          <span className="text-sm font-medium">{formatAmount(t.amount)}</span>
        </label>
      ))}
    </div>

    {/* Summary and actions */}
    <div className="px-6 py-4 border-t bg-gray-50">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-gray-600">
          Selected total: <strong>{formatAmount(selectedTotal)}</strong>
          {Math.abs(selectedTotal - parentTransaction.amount) > 0.01 && (
            <span className="text-amber-600 ml-2">
              ⚠️ Differs from parent by {formatAmount(Math.abs(selectedTotal - parentTransaction.amount))}
            </span>
          )}
        </span>
      </div>
      <div className="flex gap-3">
        <button onClick={handleSave} disabled={selectedKeys.length === 0 || isSaving}
                className="flex-1 bg-blue-600 text-white rounded-md py-2 text-sm font-medium">
          {isSaving ? 'Saving...' : `Group ${selectedKeys.length} Transaction${selectedKeys.length !== 1 ? 's' : ''}`}
        </button>
        <button onClick={onClose} className="flex-1 border rounded-md py-2 text-sm">Cancel</button>
      </div>
    </div>
  </div>
</div>
```

ACCEPTANCE CRITERIA:
- Can right-click or use row action to "Group as Sub-Transaction" on any transaction
- Modal opens showing all eligible transactions to select as children
- Running total shows as children are selected
- Warning shown (not blocking) if children don't sum to parent
- After saving: parent row shows ▶ expand indicator
- Click ▶: child rows appear indented below parent with ↳ prefix
- Child rows show "Remove from group" action
- Un-grouping a child removes it from the parent (both in UI and database)
- PDF export shows sub-transactions indented under parent

DO NOT:
- Delete any transaction nodes from the database
- Break existing transaction display for non-grouped transactions
- Make grouping permanent/irreversible (must be able to unlink)
```

---

### AGENT PROMPT 3.2 — Table View: Performance + Bulk Edit

**Estimated time:** 5–7 days
**Files to touch:** GraphTableView.jsx (major), graph.py, neo4j_service.py
**Depends on:** Nothing
**⚠️ Large file — GraphTableView.jsx is 97KB. Read it entirely before touching it.**

---

```
You are working on the Owl Investigation Platform — a React/FastAPI legal investigation tool.

TASK: Fix performance issues in the Graph Table View and add bulk edit/merge capabilities.
The table currently renders all entities at once causing slowness with large graphs.

CODEBASE CONTEXT:
- Frontend: React 18, Tailwind CSS
- Project root: /Users/neilbyrne/Documents/Owl/owl-n4j

KEY FILE (read ENTIRELY before editing):
- /frontend/src/components/GraphTableView.jsx (~97KB, large component)

ADDITIONAL FILES:
- /backend/routers/graph.py — add batch update endpoint
- /backend/services/neo4j_service.py — add batch update method

STEP 1 — ANALYSIS (do before coding):
Read GraphTableView.jsx completely. Document:
1. How does it currently render rows? (map() over an array? nested loops?)
2. What state variables manage selection?
3. How large can the data set get? (how many entities typical?)
4. What existing sort/filter logic must be preserved?
5. Does it already use react-window or any virtualization?

STEP 2 — PERFORMANCE FIX:

Option A: React Virtualization (recommended if >500 rows possible)
- Install react-window: add to package.json and run npm install
- Replace the row rendering with FixedSizeList from 'react-window'
- Each row rendered as a separate memoized component: React.memo(TableRow)
- The list itself should be in a div with fixed height (e.g., calc(100vh - 300px))

Option B: Pagination (simpler, always works)
- Add page/pageSize state: const [page, setPage] = useState(1); const pageSize = 100;
- Slice the sorted/filtered data: data.slice((page-1)*pageSize, page*pageSize)
- Add pagination controls below table: "< 1 2 3 ... >" with page numbers
- Show total count: "Showing 1-100 of 847 entities"

Implement whichever approach fits better with the existing code structure.
Add React.memo() to individual row components to prevent unnecessary re-renders.
Add useMemo() for any expensive computations (sort, filter) that don't need to run on every render.

STEP 3 — BULK SELECTION:

Read the existing selection state in GraphTableView.jsx.
Add or enhance:
- Checkbox column as first column in table
- "Select All" checkbox in header (selects all VISIBLE/filtered rows, not all data)
- Selected row count indicator: "47 rows selected"
- Keyboard shortcut: Ctrl+A selects all visible rows
- Click row checkbox: toggle selection
- Shift+click: select range

STEP 4 — BULK ACTION TOOLBAR:

When 2+ rows selected, show a sticky toolbar above the table:

```jsx
{selectedKeys.size > 0 && (
  <div className="sticky top-0 z-10 bg-blue-50 border border-blue-200 rounded-lg px-4 py-2.5 mb-3 flex items-center gap-4">
    <span className="text-sm font-medium text-blue-800">
      {selectedKeys.size} {selectedKeys.size === 1 ? 'entity' : 'entities'} selected
    </span>

    <div className="flex gap-2 ml-auto">
      {selectedKeys.size === 2 && (
        <button onClick={handleBulkMerge}
                className="px-3 py-1.5 text-sm bg-white border border-blue-300 rounded-md hover:bg-blue-50">
          Merge 2 Entities
        </button>
      )}

      <button onClick={() => setShowBulkEditModal(true)}
              className="px-3 py-1.5 text-sm bg-white border border-blue-300 rounded-md hover:bg-blue-50">
        Edit Property
      </button>

      <button onClick={() => setSelectedKeys(new Set())}
              className="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700">
        Clear ✕
      </button>
    </div>
  </div>
)}
```

STEP 5 — BULK EDIT MODAL:

When "Edit Property" clicked with multiple rows selected, show a modal:
- Dropdown: select which property to set (Name, Summary, Type, or custom)
- Input: new value
- Preview: "This will update [N] entities"
- Apply button

On apply, call PUT /api/graph/batch-update (new endpoint below).

STEP 6 — BULK MERGE (2 entities only):

When exactly 2 entities selected and "Merge 2 Entities" clicked:
- Open the existing MergeEntitiesModal with entity1 and entity2 pre-populated
- This reuses existing merge functionality

BACKEND CHANGES:

### neo4j_service.py — add batch_update_entities method:

```python
async def batch_update_entities(
    self, updates: list, case_id: str
) -> int:
    """
    Update properties on multiple entity nodes in a single query.
    updates: list of {key: str, property: str, value: str}
    Returns: count of updated nodes
    """
    async with self.driver.session() as session:
        result = await session.run("""
            UNWIND $updates as update
            MATCH (n {key: update.key, case_id: $case_id})
            CALL apoc.create.setProperty(n, update.property, update.value)
            YIELD node
            RETURN count(node) as updated_count
        """, updates=updates, case_id=case_id)
        record = await result.single()
        return record['updated_count'] if record else 0
```

Note: If APOC is not available, use a simpler approach with conditional property setting.
Check if APOC is used elsewhere in neo4j_service.py. If not, use:
```python
# Without APOC - handle the most common properties
result = await session.run("""
    UNWIND $updates as update
    MATCH (n {key: update.key, case_id: $case_id})
    SET n += {[update.property]: update.value}
    RETURN count(n) as updated_count
""", updates=updates, case_id=case_id)
```

### graph.py router — add batch update endpoint:

```python
class BatchUpdateItem(BaseModel):
    key: str
    property: str
    value: str

class BatchUpdateRequest(BaseModel):
    case_id: str
    updates: List[BatchUpdateItem]

@router.put("/batch-update")
async def batch_update_entities(
    request: BatchUpdateRequest,
    # ... copy auth params
):
    if len(request.updates) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 updates per batch")

    # Validate property names (prevent injection)
    allowed_properties = {'name', 'summary', 'notes', 'type', 'description'}
    for update in request.updates:
        if update.property not in allowed_properties:
            raise HTTPException(status_code=400, detail=f"Property '{update.property}' cannot be bulk updated")

    updates_dict = [u.dict() for u in request.updates]
    count = await neo4j_service.batch_update_entities(updates_dict, request.case_id)
    return {"success": True, "updated_count": count}
```

ACCEPTANCE CRITERIA:
- Table renders 100+ entities without noticeable lag (< 500ms)
- Table renders 1000+ entities without browser freeze
- Checkboxes appear on each row
- Select All selects all filtered/visible rows
- Batch toolbar appears when rows selected
- With exactly 2 selected: "Merge" button opens existing MergeEntitiesModal
- "Edit Property" opens modal to set same value on all selected entities
- Bulk update persists to database and table refreshes
- Existing sort, filter, and individual-row editing all still work
- No console errors or React rendering warnings

DO NOT:
- Remove any existing table functionality
- Change how individual entity editing works
- Change the entity detail panel
- Modify the graph visualization view
```

---

### AGENT PROMPT 3.3 — Insights System: Generate, Review, Accept/Reject

**Estimated time:** 4–5 days
**Files to touch:** New service, graph router, new React component, CaseOverviewView
**Depends on:** Nothing (insight storage already exists in Neo4j)

---

```
You are working on the Owl Investigation Platform — a React/FastAPI legal investigation tool.

TASK: Build an Insights system that lets attorneys generate, review, and accept or reject
AI-generated investigative insights about entities and the overall case.

BACKGROUND:
- Entities already have an `ai_insights` JSON array stored on them in Neo4j
- The `verify_insight` endpoint already exists (POST /graph/node/{key}/verify-insight)
  which converts an insight into a verified fact
- What's MISSING: a way to GENERATE new insights on demand, and a UI to REVIEW and
  ACCEPT/REJECT them across the whole case

CODEBASE CONTEXT:
- Backend: FastAPI/Python, Neo4j, OpenAI/Ollama LLM
- Frontend: React 18, Tailwind CSS
- Project root: /Users/neilbyrne/Documents/Owl/owl-n4j

EXISTING VERIFY ENDPOINT (already works, do not rebuild):
- POST /api/graph/node/{key}/verify-insight
- Request: { case_id, insight_index, username, source_doc?, page? }
- Converts insight to verified fact

KEY FILES TO READ FIRST:
- /backend/services/neo4j_service.py — find verify_insight() and how ai_insights are stored
- /backend/routers/graph.py — find verify_insight endpoint (~line 1236-1265)
- /backend/services/ — look for llm_service.py or similar for how LLM calls are made
- /frontend/src/components/workspace/CaseOverviewView.jsx — where to add the insights section

KEY FILES TO CREATE/MODIFY:
- CREATE: /backend/services/insights_service.py
- MODIFY: /backend/routers/graph.py — add generate and reject endpoints
- CREATE: /frontend/src/components/workspace/InsightsPanel.jsx
- MODIFY: /frontend/src/components/workspace/CaseOverviewView.jsx

BACKEND CHANGES:

### 1. CREATE /backend/services/insights_service.py:

Read how LLM calls are made elsewhere in the codebase (check rag_service.py or llm_service.py
for the exact pattern of calling OpenAI/Ollama). Use the SAME pattern.

```python
"""
Insights Service — Generate investigative insights for entities using LLM.
"""
import json
from typing import Optional


INSIGHT_GENERATION_PROMPT = """You are an expert investigative analyst helping a legal defense team
analyze evidence in a criminal case.

Review the following information about an entity and generate 3-5 investigative insights that would
be valuable to the defense attorney.

Entity Information:
{entity_info}

Verified Facts:
{verified_facts}

Related Entities and Connections:
{related_entities}

Generate insights that:
1. Identify potential inconsistencies or gaps in the evidence
2. Highlight connections to other entities that may be significant
3. Note any patterns that warrant further investigation
4. Point out anything that could help the defense (alibi, alternative explanations, etc.)
5. Flag any potential Brady/Giglio issues (evidence that might be favorable to the defense)

For each insight, provide:
- "text": The insight (1-3 sentences, specific and actionable)
- "confidence": "high", "medium", or "low"
- "reasoning": Brief explanation of why this is significant (1 sentence)
- "category": One of: "inconsistency", "connection", "pattern", "defense_opportunity", "disclosure_concern", "other"

Respond with valid JSON only:
{{"insights": [
  {{"text": "...", "confidence": "high", "reasoning": "...", "category": "..."}},
  ...
]}}"""


async def generate_entity_insights(
    entity_data: dict,
    verified_facts: list,
    related_entities: list,
    llm_call_fn  # The LLM calling function from your existing service
) -> list:
    """
    Generate AI insights for a specific entity.
    Returns list of insight dicts with text, confidence, reasoning, category.
    """
    # Format entity info
    entity_info = f"Name: {entity_data.get('name', 'Unknown')}\n"
    entity_info += f"Type: {entity_data.get('type', 'Unknown')}\n"
    if entity_data.get('summary'):
        entity_info += f"Summary: {entity_data['summary']}\n"

    # Format verified facts
    facts_text = '\n'.join([
        f"- {f.get('text', f) if isinstance(f, dict) else f}"
        for f in verified_facts[:10]  # limit context
    ]) or "No verified facts yet"

    # Format related entities
    related_text = '\n'.join([
        f"- {r.get('name', 'Unknown')} ({r.get('type', 'Unknown')}): {r.get('relationship', '')}"
        for r in related_entities[:10]
    ]) or "No related entities found"

    prompt = INSIGHT_GENERATION_PROMPT.format(
        entity_info=entity_info,
        verified_facts=facts_text,
        related_entities=related_text
    )

    # Call LLM — use the same pattern as the rest of the codebase
    # This will depend on how llm_call_fn is structured in your codebase
    response_text = await llm_call_fn(
        system_prompt="You are an expert investigative analyst for legal defense teams. Always respond with valid JSON.",
        user_prompt=prompt
    )

    # Parse JSON response
    try:
        # Handle response that might have markdown code blocks
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0]
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0]

        data = json.loads(response_text.strip())
        insights = data.get('insights', [])

        # Validate and clean each insight
        cleaned = []
        for insight in insights:
            if isinstance(insight, dict) and 'text' in insight:
                cleaned.append({
                    'text': str(insight.get('text', '')),
                    'confidence': insight.get('confidence', 'medium'),
                    'reasoning': str(insight.get('reasoning', '')),
                    'category': insight.get('category', 'other'),
                    'status': 'pending'  # pending | accepted | rejected
                })
        return cleaned
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Failed to parse insight response: {e}")
        return []
```

### 2. neo4j_service.py — add methods:

```python
async def get_entities_for_insights(self, case_id: str) -> list:
    """Get all significant entities with their verified facts and related entities."""
    async with self.driver.session() as session:
        result = await session.run("""
            MATCH (n {case_id: $case_id})
            WHERE (n:Person OR n:Company OR n:Organisation OR n:Bank OR n:BankAccount)
              AND n.name IS NOT NULL
            OPTIONAL MATCH (n)-[r]-(related {case_id: $case_id})
            WITH n, collect({
                name: related.name,
                type: labels(related)[0],
                relationship: type(r)
            })[..10] as related_entities
            RETURN n.key as key, n.name as name, labels(n)[0] as type,
                   n.summary as summary, n.verified_facts as verified_facts,
                   n.ai_insights as ai_insights,
                   related_entities
        """, case_id=case_id)

        entities = []
        async for record in result:
            entities.append(dict(record))
        return entities

async def save_entity_insights(
    self, node_key: str, case_id: str, new_insights: list
) -> bool:
    """Append new insights to an entity's ai_insights array."""
    async with self.driver.session() as session:
        # Get current insights
        result = await session.run("""
            MATCH (n {key: $key, case_id: $case_id})
            RETURN n.ai_insights as current_insights
        """, key=node_key, case_id=case_id)
        record = await result.single()
        if not record:
            return False

        # Parse existing insights
        existing = parse_json_field(record['current_insights'], [])

        # Mark existing ones as not new, append new ones
        updated = existing + new_insights

        await session.run("""
            MATCH (n {key: $key, case_id: $case_id})
            SET n.ai_insights = $insights
        """, key=node_key, case_id=case_id,
             insights=json.dumps(updated))
        return True

async def reject_entity_insight(
    self, node_key: str, case_id: str, insight_index: int
) -> bool:
    """Mark an insight as rejected (remove from pending list)."""
    async with self.driver.session() as session:
        result = await session.run("""
            MATCH (n {key: $key, case_id: $case_id})
            RETURN n.ai_insights as insights
        """, key=node_key, case_id=case_id)
        record = await result.single()
        if not record:
            return False

        insights = parse_json_field(record['insights'], [])
        if 0 <= insight_index < len(insights):
            insights.pop(insight_index)  # Remove rejected insight

        await session.run("""
            MATCH (n {key: $key, case_id: $case_id})
            SET n.ai_insights = $insights
        """, key=node_key, case_id=case_id,
             insights=json.dumps(insights))
        return True

async def get_all_pending_insights(self, case_id: str) -> list:
    """Get all pending insights across all entities in a case."""
    async with self.driver.session() as session:
        result = await session.run("""
            MATCH (n {case_id: $case_id})
            WHERE n.ai_insights IS NOT NULL AND n.ai_insights <> '[]'
            RETURN n.key as key, n.name as name, labels(n)[0] as type,
                   n.ai_insights as ai_insights
        """, case_id=case_id)

        all_insights = []
        async for record in result:
            insights = parse_json_field(record['ai_insights'], [])
            for i, insight in enumerate(insights):
                if isinstance(insight, dict):
                    all_insights.append({
                        'entity_key': record['key'],
                        'entity_name': record['name'],
                        'entity_type': record['type'],
                        'insight_index': i,
                        'text': insight.get('text', ''),
                        'confidence': insight.get('confidence', 'medium'),
                        'reasoning': insight.get('reasoning', ''),
                        'category': insight.get('category', 'other'),
                    })
        return all_insights
```

### 3. graph.py router — add 3 endpoints:

Find where verify_insight endpoint is (~line 1236) and add these nearby:

```python
@router.post("/cases/{case_id}/generate-insights")
async def generate_case_insights(
    case_id: str,
    max_entities: int = 10,  # limit to prevent very long operations
    # ... auth params
):
    """Generate AI insights for top entities in the case."""
    entities = await neo4j_service.get_entities_for_insights(case_id)

    # Prioritize entities with most verified facts
    entities_sorted = sorted(entities,
                              key=lambda e: len(parse_json_field(e.get('verified_facts'), [])),
                              reverse=True)[:max_entities]

    total_generated = 0
    for entity in entities_sorted:
        verified_facts = parse_json_field(entity.get('verified_facts'), [])
        related = entity.get('related_entities', [])

        # Generate insights using LLM
        # You'll need to wire the LLM calling function here based on how it's done elsewhere
        # Look at how rag_service.py calls the LLM and use the same pattern
        new_insights = await insights_service.generate_entity_insights(
            entity_data=entity,
            verified_facts=verified_facts,
            related_entities=related,
            llm_call_fn=... # wire your existing LLM call pattern
        )

        if new_insights:
            await neo4j_service.save_entity_insights(entity['key'], case_id, new_insights)
            total_generated += len(new_insights)

    return {
        "success": True,
        "entities_processed": len(entities_sorted),
        "insights_generated": total_generated
    }

@router.delete("/node/{node_key}/insights/{insight_index}")
async def reject_insight(
    node_key: str,
    insight_index: int,
    case_id: str,
    # ... auth params
):
    success = await neo4j_service.reject_entity_insight(node_key, case_id, insight_index)
    if not success:
        raise HTTPException(status_code=404, detail="Insight or entity not found")
    return {"success": True}

@router.get("/cases/{case_id}/insights")
async def get_case_insights(
    case_id: str,
    # ... auth params
):
    insights = await neo4j_service.get_all_pending_insights(case_id)
    return {"insights": insights, "total": len(insights)}
```

FRONTEND CHANGES:

### 4. CREATE /frontend/src/components/workspace/InsightsPanel.jsx:

Build a panel showing all pending insights with accept/reject actions.

Features:
- Loading state while generating
- "Generate Insights" button (calls POST /api/graph/cases/{caseId}/generate-insights)
- Shows progress: "Processing 10 entities..."
- Groups insights by entity
- Each insight card shows:
  - Entity name + type badge
  - Insight text
  - Confidence badge (color coded: high=green, medium=amber, low=red)
  - Reasoning (collapsible)
  - Category badge (inconsistency | connection | pattern | defense_opportunity | disclosure_concern)
  - ✅ Accept (calls existing verify-insight endpoint) | ❌ Reject (calls new reject endpoint)
- Bulk actions: "Accept All High Confidence" | "Reject All Low Confidence"
- Empty state: "No pending insights. Click Generate to analyze your case."
- After accepting: insight moves out of pending, appears in entity's verified facts

Key API calls to wire up:
- GET /api/graph/cases/{caseId}/insights — fetch all pending insights
- POST /api/graph/cases/{caseId}/generate-insights — generate new ones
- POST /api/graph/node/{entityKey}/verify-insight — accept (existing endpoint)
- DELETE /api/graph/node/{entityKey}/insights/{insightIndex} — reject (new endpoint)

### 5. CaseOverviewView.jsx — add Insights section:

Import InsightsPanel and add it as a section in the dashboard.
Add a count badge: if there are pending insights, show a yellow dot indicator.

ACCEPTANCE CRITERIA:
- "Generate Insights" button triggers LLM analysis of top entities
- After generation: insights appear as cards grouped by entity
- Each insight shows confidence level, category, and reasoning
- Accept button: insight disappears from pending, appears in entity's verified facts
- Reject button: insight is permanently removed
- "Accept All High Confidence" processes all high-confidence insights at once
- Insights persist between sessions (stored in Neo4j)
- Empty state shown when no insights pending
- Generating insights for a 10-entity case completes in under 60 seconds

DO NOT:
- Change how verified facts are stored or displayed elsewhere
- Remove the existing verify_insight endpoint
- Generate insights automatically on document upload (only on demand)
```

---

## Quick Reference — Prompt to Feature Map

| Sprint | Prompt | Feature | Effort |
|---|---|---|---|
| 1 | 1.1 | Fix document viewer z-index in merge modal | 0.5 day |
| 1 | 1.2 | Reduce AI entity extraction noise | 1 day |
| 1 | 1.3 | Save AI chat response as case note | 0.5 day |
| 1 | 1.4 | Bulk categorization UI in financial table | 1 day |
| 1 | 1.5 | Map: right-click to edit/remove location pins | 1.5 days |
| 2 | 2.1 | Edit transaction amounts with audit trail | 2 days |
| 2 | 2.2 | Entity summary panel on case dashboard | 2 days |
| 2 | 2.3 | AI chat: raise document analysis limit | 0.5–1 day |
| 2 | 2.4 | Clarify "Case Files" vs "All Evidence" labels | 0.5 day |
| 2 | 2.5 | Export financial transactions to PDF | 1.5 days |
| 3 | 3.1 | Sub-transaction grouping (full system) | 5–7 days |
| 3 | 3.2 | Table view: virtualization + bulk edit | 5–7 days |
| 3 | 3.3 | Insights: generate, review, accept/reject | 4–5 days |

**Total estimated effort:** ~27–34 development days

---

*All prompts reference exact file paths, existing function names, and established codebase patterns.
Each prompt is self-contained and can be handed to an agent without additional context.*
