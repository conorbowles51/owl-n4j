# Owl Platform — Cursor Opus Master Orchestration Prompt

Paste the entire block below into Cursor with Claude Opus 4.5 / claude-4-opus.

---

```
You are a senior full-stack engineer working on the Owl Investigation Platform.

Owl is a React 18 + FastAPI + Neo4j legal investigation tool used by defense attorneys to
analyze large volumes of prosecution discovery documents. It extracts entities and relationships
from documents into a knowledge graph and lets attorneys query the graph with natural language.

Project root: /Users/neilbyrne/Documents/Owl/owl-n4j
Frontend: /frontend/src (React 18, Tailwind CSS, Vite)
Backend: /backend (FastAPI, Python, async/await throughout)
Graph DB: Neo4j (queries via neo4j_service.py using Cypher)
Vector DB: ChromaDB (in vector_db_service.py)
LLM: OpenAI or Ollama (switchable per profile)

Your job is to set up and execute the following 13 build tasks across 3 sprints.
Read the full task list carefully first. Then begin executing Sprint 1 tasks in parallel
where possible, followed by Sprint 2, then Sprint 3.

For each task:
1. Read ALL referenced files completely before writing any code
2. Follow existing patterns exactly — naming conventions, async patterns, Tailwind classes,
   Pydantic models, error handling — match what is already in the codebase
3. Never rebuild something that already exists — check first
4. After completing each task, confirm what was changed and why

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPRINT 1 — QUICK WINS (start these in parallel)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

──────────────────────────────────────────────
TASK 1.1 — Fix: Document Viewer Opens Behind Modal
FILES: /frontend/src/components/DocumentViewer.jsx,
       /frontend/src/components/MergeEntitiesModal.jsx,
       /frontend/src/components/MapView.jsx
──────────────────────────────────────────────
PROBLEM: When a user opens a source document from inside the MergeEntitiesModal,
the DocumentViewer renders behind the modal. Same bug on MapView popups.

FIX:
- In DocumentViewer.jsx: wrap the entire return in ReactDOM.createPortal(..., document.body)
  Add: import ReactDOM from 'react-dom'
  Set the overlay div to: className includes "fixed inset-0 z-[9999]"
- In MergeEntitiesModal.jsx: ensure no parent div has overflow:hidden that clips the portal
- In MapView.jsx: apply same portal fix to any detail panels opened from markers

DONE WHEN: User opens merge modal → clicks source doc → doc appears ON TOP of modal →
closes doc → merge modal still open with state intact. No console errors.

──────────────────────────────────────────────
TASK 1.2 — Reduce AI Entity Extraction Noise
FILES: /backend/ingestion/scripts/llm_client.py,
       /backend/ingestion/scripts/entity_resolution.py,
       /profiles/*.json
──────────────────────────────────────────────
PROBLEM: The LLM extracts too many low-quality entities — every table row becomes an entity,
minor mentions become entities. Target: 30-50% reduction in entity count, zero loss of
significant entities.

FIX:
- In llm_client.py, find the entity extraction system prompt (~lines 477-535).
  Add these rules immediately before the JSON format instruction:

  ENTITY QUALITY RULES — FOLLOW STRICTLY:
  1. SIGNIFICANCE THRESHOLD: Only extract entities that play an active, named role in events.
     Skip passing mentions, generic job titles without names, background references.
  2. TABLES: Do NOT create one entity per row. Identify the 2-3 key parties in the table,
     create entities only for them, summarize the table in their verified_facts.
  3. IMPORTANCE: Before extracting, ask "Would an attorney need to click on this entity?"
     If no, skip it.
  4. DEDUPLICATION: Same person with slightly different names = ONE entity with aliases in
     verified_facts. Do not create separate entities.
  5. MINIMUM: Entity must be a named party to a transaction, agreement, communication, or
     legal proceeding. Generic references do not qualify.

- In entity_resolution.py: find the fuzzy match similarity threshold and raise it to 0.88
- In profiles/*.json: add "max_entities_per_chunk": 25 to ingestion settings if that field exists

Add comment above changes: # QUALITY FILTER — Feb 2026

DONE WHEN: Test prompt with a sample document. Entity count is noticeably lower. Key named
parties are all still present. No significant entities missing.

──────────────────────────────────────────────
TASK 1.3 — Save AI Chat Response as Case Note
FILES: /frontend/src/components/ChatPanel.jsx,
       /frontend/src/services/api.js
──────────────────────────────────────────────
PROBLEM: Attorneys find useful answers in AI chat but can't save them. Notes API already
exists — this is a frontend-only wiring task.

EXISTING INFRASTRUCTURE (do not rebuild):
- Notes API: api.workspace.createNote(caseId, {content, tags}) — already in api.js ~line 1858
- Backend: POST /api/workspace/{case_id}/notes — fully working

FIX in ChatPanel.jsx:
- Find assistant message rendering (~lines 775-805)
- Add a bookmark icon button (BookmarkPlus from lucide-react) below each assistant message
- On click: show small modal pre-filled with:
    title: first 60 chars of the user question that preceded this response
    content: full AI response text (editable)
- On Save: call api.workspace.createNote(caseId, {content, tags: ['ai-chat']})
- Show success toast using existing toast pattern in the file
- On Cancel: close modal, nothing saved

DONE WHEN: Hover AI message → bookmark icon visible → click → modal opens pre-filled →
Save → success toast → open Notes panel → note appears with 'ai-chat' tag.

──────────────────────────────────────────────
TASK 1.4 — Bulk Categorization UI in Financial Table
FILES: /frontend/src/components/financial/FinancialTable.jsx,
       /frontend/src/components/financial/FinancialView.jsx
──────────────────────────────────────────────
PROBLEM: The batch categorize API endpoint already exists (PUT /api/financial/batch-categorize)
and the frontend has selectedKeys state, but there is no UI to actually apply a category
to selected rows.

EXISTING (do not rebuild):
- PUT /api/financial/batch-categorize — works, takes {node_keys, category, case_id}
- api.financial.batchCategorize(nodeKeys, category, caseId) — in api.js ~line 794
- FinancialTable already has: selectedKeys prop, onSelectionChange prop, onBatchCategorize prop
- Checkboxes and selection logic may already be partially built — READ THE FILE FIRST

FIX:
READ FinancialTable.jsx completely first. Then:
- Confirm checkboxes exist on rows; if missing, add them
- In the batch action toolbar (lines 345-379), confirm or ADD:
    A category <select> dropdown populated from the categories prop
    An "Apply Category" button that calls onBatchCategorize(selectedKeys, selectedCategory)
- In FinancialView.jsx, confirm handleBatchCategorize calls the API and refreshes the table

DONE WHEN: Select multiple rows → category dropdown appears in toolbar → select category →
click Apply → all selected transactions update → table refreshes → selection cleared.

──────────────────────────────────────────────
TASK 1.5 — Map: Edit and Remove Location Pins
FILES: /backend/services/neo4j_service.py,
       /backend/routers/graph.py,
       /frontend/src/components/MapView.jsx
──────────────────────────────────────────────
PROBLEM: Location pins on the map cannot be edited or removed. Bad AI-extracted locations
pollute the map with no way to fix them.

FIX:
BACKEND — add to neo4j_service.py (match existing async session pattern):
  async def update_entity_location(self, node_key, case_id, location_name, latitude, longitude)
    → SET n.location_name, n.latitude, n.longitude
  async def remove_entity_location(self, node_key, case_id)
    → REMOVE n.latitude, n.longitude, n.location_name (node stays in graph)

BACKEND — add to graph.py (match existing endpoint patterns for auth + error handling):
  PUT /graph/node/{node_key}/location — body: {case_id, location_name, latitude, longitude}
  DELETE /graph/node/{node_key}/location — query param: case_id

FRONTEND — in MapView.jsx:
  Add right-click handler to each Leaflet <Marker>:
    Show context menu: "Edit Location" | "Remove from Map"
  "Edit Location": open modal with fields for location_name, latitude, longitude (pre-filled)
    → on Save: call PUT endpoint → update marker in local state immediately
  "Remove from Map": call DELETE endpoint → remove marker from local state immediately
  Context menu: fixed-position div, z-[9999], dismisses on mouse-leave

DONE WHEN: Right-click map marker → context menu appears → Edit → modal opens pre-filled →
Save → marker moves. Remove → marker disappears. Entity still exists in graph view.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPRINT 2 — MEDIUM FEATURES (after Sprint 1 complete)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

──────────────────────────────────────────────
TASK 2.1 — Financial Dashboard: Edit Transaction Amounts
FILES: /backend/services/neo4j_service.py,
       /backend/routers/financial.py,
       /frontend/src/services/api.js,
       /frontend/src/components/financial/FinancialTable.jsx
──────────────────────────────────────────────
PROBLEM: Transaction amounts extracted by AI may be wrong. Attorneys need to correct them.
CRITICAL: Must preserve original AI-extracted amount as audit trail — never destroy it.

FIX:
BACKEND — neo4j_service.py, add method (follow existing update_transaction_details pattern):
  async def update_transaction_amount(self, node_key, case_id, new_amount, correction_reason)
  Logic:
    1. Fetch current amount
    2. If node.original_amount is null: SET node.original_amount = current amount (preserve first value)
    3. SET node.amount = new_amount
    4. SET node.amount_corrected = true
    5. SET node.correction_reason = correction_reason

BACKEND — financial.py router, add endpoint (follow existing details endpoint pattern):
  PUT /api/financial/transactions/{node_key}/amount
  Body: UpdateAmountRequest {case_id, new_amount: float, correction_reason: str}
  Validate: new_amount > 0

FRONTEND — api.js: add api.financial.updateAmount(nodeKey, {caseId, newAmount, correctionReason})

FRONTEND — FinancialTable.jsx: make amount cell inline-editable
  Click amount → becomes input field with current value
  Enter/✓ to save → calls updateAmount API → updates local state
  Escape → cancel, restore original display
  If transaction.amount_corrected: show amber ✎ indicator next to amount
  Hover ✎: tooltip shows "Original: $X — {correction_reason}"

DONE WHEN: Click amount → edit → Enter → saves → ✎ indicator appears → hover shows original.
Refresh page → corrected amount persists. Original never lost from database.

──────────────────────────────────────────────
TASK 2.2 — Entity Summary Panel on Case Dashboard
FILES: /backend/services/neo4j_service.py,
       /backend/routers/graph.py,
       /frontend/src/components/workspace/CaseOverviewView.jsx,
       CREATE: /frontend/src/components/workspace/EntitySummarySection.jsx
──────────────────────────────────────────────
PROBLEM: The case dashboard has no structured list of entities. Attorneys can't quickly see
who/what is in the case without navigating to the graph.

FIX:
BACKEND — neo4j_service.py, add method:
  async def get_case_entity_summary(self, case_id) → list
  Cypher:
    MATCH (n {case_id: $case_id})
    WHERE n:Person OR n:Company OR n:Organisation OR n:Bank OR n:BankAccount
    AND n.name IS NOT NULL
    RETURN n.key, n.name, labels(n)[0] as type, n.summary,
           size(COALESCE(n.verified_facts, [])) as facts_count,
           size(COALESCE(n.ai_insights, [])) as insights_count
    ORDER BY type, n.name
  Note: verified_facts/ai_insights may be stored as JSON strings — use parse_json_field()
  if that helper exists in the file, otherwise handle both list and string cases.

BACKEND — graph.py router, add:
  GET /api/graph/cases/{case_id}/entity-summary
  Returns: {entities: [...], total: count}

FRONTEND — create EntitySummarySection.jsx:
  Tabs: All | People | Companies | Organisations | Banks | Accounts (with count badges)
  Search input: filter entities by name in real-time
  Sort dropdown: Name | Type | Most Facts | Most Insights
  Entity rows: type icon | name | summary (truncated, 1 line) | facts count | insights count
  Hover → cursor pointer (onClick → onEntityClick prop if wired)
  Max height: overflow-y-auto so it doesn't push other sections off screen
  Loading + empty states

FRONTEND — CaseOverviewView.jsx:
  Import and add <EntitySummarySection caseId={caseId} /> in the scrollable content area
  Place it after the client profile / case summary section

DONE WHEN: Case dashboard shows entity list. Tabs filter by type. Search filters by name.
Counts show correctly. Scrollable if many entities.

──────────────────────────────────────────────
TASK 2.3 — AI Chat: Raise Document Analysis Limit
FILES: /backend/services/rag_service.py,
       /backend/services/vector_db_service.py,
       /frontend/src/components/ChatPanel.jsx
──────────────────────────────────────────────
PROBLEM: AI chat is limited to ~10 documents. Attorneys have cases with 50-200 documents
and need to analyze across all of them.

FIX:
FIRST: Search these files for: n_results, top_k, limit=, [:10], CHUNK_SEARCH_TOP_K,
VECTOR_SEARCH_TOP_K, ENTITY_SEARCH_TOP_K, max_docs. Report what you find before changing.

In vector_db_service.py:
  search(top_k=10) → raise default to 50
  search_entities(top_k=10) → raise default to 50
  search_chunks(top_k=15) → raise default to 50

In rag_service.py:
  Any TOP_K constants → raise to 50
  verified_facts[:10] → change to [:25]
  Any results slicing like filtered[:10] in retrieval logic → raise or remove cap
  CONTEXT_TOKEN_BUDGET → if set low, raise to 80000 (GPT-4 supports 128K)
  Add code comment: # Raised from 10→50 for full case analysis. For Ollama <32K context, reduce to 15.

In ChatPanel.jsx:
  If document selector list is capped visually or programmatically at 10:
    Remove cap
    Add "Select All Documents" toggle at top of list

DONE WHEN: Can select all documents in a case. AI chat response draws from all selected docs.
No timeout for normal use (up to 50 docs). Context limit errors handled gracefully with
a clear user message rather than a crash.

──────────────────────────────────────────────
TASK 2.4 — Clarify "Case Files" vs "All Evidence" on Dashboard
FILES: /frontend/src/components/workspace/CaseOverviewView.jsx,
       /frontend/src/components/workspace/DocumentsSection.jsx,
       /frontend/src/components/workspace/AllEvidenceSection.jsx
──────────────────────────────────────────────
PROBLEM: Users don't understand the difference between "Case Files" and "All Evidence".
The naming is confusing — attorneys think both show the same thing.

FIX (UI labels and ordering only — no backend changes, no functionality changes):

FIRST: Read all three files. Understand exactly what each section displays.
Then apply:

1. Rename "Case Files" section heading → "Uploaded Documents"
   Add subtitle (text-sm text-gray-500): "Files you have added to this case and processed for analysis"

2. Rename "All Evidence" heading based on what it actually shows:
   If it shows extracted entities/relationships → "Extracted Evidence"
   Add subtitle: "Entities and relationships automatically identified from your uploaded documents"
   If it shows something different → rename to accurately reflect actual content

3. If both sections show essentially the same data from different angles:
   Merge them into one "Documents" section with a summary line:
   "X documents uploaded · Y entities extracted"

4. Reorder sections in CaseOverviewView for logical attorney flow:
   1st: Case Summary / Client Profile
   2nd: Uploaded Documents
   3rd: Key Entities (Task 2.2 section, if built)
   4th: Notes / Tasks / Working materials

5. Add a (?) help icon tooltip to any section title that might still be ambiguous.

DONE WHEN: A non-technical attorney reading the dashboard immediately understands
what each section shows. No section uses the word "Evidence" to mean "uploaded files".
All existing buttons and export checkboxes still work.

──────────────────────────────────────────────
TASK 2.5 — Export Financial Transactions to PDF
FILES: CREATE: /backend/services/financial_export_service.py,
       /backend/routers/financial.py,
       /frontend/src/components/financial/FinancialView.jsx,
       /frontend/src/services/api.js
──────────────────────────────────────────────
PROBLEM: Attorneys need to export transaction reports to PDF for client meetings, court
filings, and sharing with co-counsel.

EXISTING: WeasyPrint is already installed. Follow the HTML→PDF pattern.

FIX:
CREATE /backend/services/financial_export_service.py:
  Function: generate_financial_pdf(transactions, case_name, filters_description) → bytes
  Build HTML with:
    Header: dark navy gradient, case name, generation date, "Attorney-Client Privileged"
    Summary box: total transactions, total value, category breakdown, active filters
    Table (A4 landscape): Date | From | To | Amount | Category | Notes/Purpose
    Corrected amounts: show ✎ marker, footnote: "† Manually corrected. Original on file."
    Sub-transactions (if any): indented rows with ↳ prefix under their parent
  Convert to PDF: weasyprint.HTML(string=html).write_pdf()
  Return bytes

BACKEND — financial.py router, add:
  GET /api/financial/export/pdf
  Query params: case_id (required), case_name, categories, start_date, end_date
  Fetches transactions via existing neo4j_service method
  Builds filter description string from active params
  Returns Response(content=pdf_bytes, media_type="application/pdf",
                   headers={"Content-Disposition": f'attachment; filename="..."'})

FRONTEND — FinancialView.jsx:
  Add "Export PDF" button in toolbar (Download icon from lucide-react)
  Handler builds URL with current active filters (match what's on screen)
  Uses window.open(url, '_blank') to trigger download

FRONTEND — api.js: not required if using window.open directly

DONE WHEN: Click Export PDF → file downloads → PDF shows correct transactions matching
current filter state → corrected amounts marked → "Attorney-Client Privileged" in footer →
works with 0 to 500+ transactions without error.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPRINT 3 — COMPLEX NEW SYSTEMS (after Sprint 2 complete)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

──────────────────────────────────────────────
TASK 3.1 — Sub-Transaction Grouping
FILES: /backend/services/neo4j_service.py,
       /backend/routers/financial.py,
       /frontend/src/services/api.js,
       /frontend/src/components/financial/FinancialTable.jsx,
       CREATE: /frontend/src/components/financial/SubTransactionModal.jsx
──────────────────────────────────────────────
PROBLEM: A $1.3M house purchase is shown as one transaction, but it's composed of a $900K
bank loan + $200K gift + $200K in fees. Attorneys need to group related transactions to
show how a total is composed.

DATA MODEL: Use a property on child nodes (parent_transaction_key: string) and a Neo4j
relationship: (child)-[:PART_OF]->(parent). Both nodes remain in graph. No data deleted.

FIX:
BACKEND — neo4j_service.py, add 3 methods (follow existing async session pattern):

  link_sub_transaction(parent_key, child_key, case_id):
    Validate both nodes exist and belong to case_id
    MERGE (child)-[:PART_OF]->(parent)
    SET child.parent_transaction_key = parent_key
    SET parent.is_parent = true

  unlink_sub_transaction(child_key, case_id):
    DELETE the :PART_OF relationship
    REMOVE child.parent_transaction_key
    Check if parent has remaining children; if none, SET parent.is_parent = false

  get_transaction_children(parent_key, case_id):
    MATCH (child)-[:PART_OF]->(parent {key: parent_key, case_id: case_id})
    RETURN child properties ORDER BY child.date

  Also: update get_financial_transactions() RETURN clause to include is_parent and
  parent_transaction_key so frontend knows the hierarchy.

BACKEND — financial.py router, add 3 endpoints (follow existing endpoint patterns):
  POST /api/financial/transactions/{parent_key}/sub-transactions
    Body: {case_id, child_key}. Reject if parent_key == child_key.
  DELETE /api/financial/transactions/{child_key}/parent
    Query param: case_id
  GET /api/financial/transactions/{parent_key}/sub-transactions
    Query param: case_id. Returns: {children: [...], count: N}

FRONTEND — api.js: add linkSubTransaction, unlinkSubTransaction, getSubTransactions

FRONTEND — FinancialTable.jsx:
  Rows where is_parent=true: show ▶/▼ expand toggle
  On expand: fetch children → show indented rows with ↳ prefix below parent
  Parent row amount is the total; show warning if children don't sum to parent
  Add "Group as Sub-Transaction" to row action menu (opens SubTransactionModal)
  Child rows: show "Remove from group" action → calls unlinkSubTransaction

CREATE SubTransactionModal.jsx:
  Props: isOpen, onClose, parentTransaction, allTransactions, caseId, onSave
  Shows parent at top with its amount
  Checkbox list of all OTHER transactions (excluding current children of other parents)
  Running total of selected children vs parent amount
  Warning (not blocking) if totals don't match
  Save: calls linkSubTransaction for each selected child → refreshes table

DONE WHEN:
  Can group transactions under a parent. Parent row shows ▶ expand.
  Click ▶: children show indented with ↳. Children sum displays vs parent total.
  Ungroup works. PDF export shows sub-transactions indented. No data deleted.

──────────────────────────────────────────────
TASK 3.2 — Table View: Performance + Bulk Edit
FILES: /frontend/src/components/GraphTableView.jsx (READ ENTIRELY — 97KB),
       /backend/services/neo4j_service.py,
       /backend/routers/graph.py
──────────────────────────────────────────────
PROBLEM: GraphTableView.jsx renders all entities at once. With large cases (500-2000+ entities)
this causes freezes. Also no bulk edit capability.

WARNING: This file is ~97KB. READ IT COMPLETELY before making any changes.
Understand: how rows render, existing selection state, sort/filter logic, what must be preserved.

FIX — PERFORMANCE:
Option A (preferred if >200 rows common): Install react-window, use FixedSizeList for row rendering.
  Each row as React.memo(TableRow) to prevent unnecessary re-renders.
  Wrap list in fixed-height container: calc(100vh - Xpx) based on existing layout.
Option B (simpler): Add pagination — show 100 rows/page, add page controls below table.
  Show: "Showing 1–100 of 847 entities"
Choose whichever fits better with the existing component structure.
Add useMemo() for sort and filter computations.

FIX — BULK SELECTION:
Read existing selection state. Add or enhance:
  Checkbox column as first column
  "Select All" checkbox in header (selects all visible/filtered rows)
  "{N} entities selected" indicator
  Shift+click for range selection

FIX — BULK ACTION TOOLBAR (appears when 2+ rows selected):
  "Merge 2 Entities" button (only when exactly 2 selected) → opens existing MergeEntitiesModal
  "Edit Property" button → opens BulkEditModal
  "Clear" button

FIX — BULK EDIT MODAL:
  Dropdown: which property to edit (name, summary, notes, type)
  Input: new value
  Preview: "Will update {N} entities"
  Apply → calls PUT /api/graph/batch-update

BACKEND — neo4j_service.py, add:
  batch_update_entities(updates: list[{key, property, value}], case_id) → int
  Use UNWIND + APOC if available, otherwise standard SET with property map

BACKEND — graph.py router, add:
  PUT /api/graph/batch-update
  Body: BatchUpdateRequest {case_id, updates: [{key, property, value}]}
  Whitelist allowed properties: {name, summary, notes, type, description}
  Limit: max 500 updates per call

DONE WHEN:
  Table with 1000 entities renders without browser freeze. (<500ms render)
  Checkboxes work, Select All works.
  2 selected → Merge opens MergeEntitiesModal with both entities pre-loaded.
  N selected → Edit Property → bulk update persists. Table refreshes.
  All existing sort, filter, individual edit still works.

──────────────────────────────────────────────
TASK 3.3 — Insights: Generate, Review, Accept/Reject
FILES: /backend/services/neo4j_service.py,
       /backend/routers/graph.py,
       CREATE: /backend/services/insights_service.py,
       CREATE: /frontend/src/components/workspace/InsightsPanel.jsx,
       /frontend/src/components/workspace/CaseOverviewView.jsx
──────────────────────────────────────────────
PROBLEM: Entities have ai_insights stored but there's no way to generate new ones on demand,
or to review and accept/reject them from the dashboard.

EXISTING (do not rebuild):
  - ai_insights stored as JSON array on entity nodes
  - POST /api/graph/node/{key}/verify-insight → converts insight → verified fact (KEEP THIS)
  - verify_insight() in neo4j_service.py

FIX:
READ FIRST: Look at how LLM calls are made in rag_service.py or any llm_service.py file.
Use the EXACT same calling pattern for insight generation.

CREATE /backend/services/insights_service.py:
  Function: generate_entity_insights(entity_data, verified_facts, related_entities, llm_call_fn) → list
  LLM prompt instructs: generate 3-5 investigative insights for a defense attorney, including:
    - Inconsistencies or gaps in evidence
    - Significant connections to other entities
    - Defense opportunities (alibi, alternative explanations)
    - Brady/Giglio concerns (evidence favorable to defense)
  Each insight: {text, confidence: high|medium|low, reasoning, category, status: "pending"}
  Parse JSON response, validate, return list

BACKEND — neo4j_service.py, add 4 methods:
  get_entities_for_insights(case_id) → entities with verified_facts and related entities
  save_entity_insights(node_key, case_id, new_insights) → append to ai_insights array
  reject_entity_insight(node_key, case_id, insight_index) → remove from ai_insights array
  get_all_pending_insights(case_id) → all pending insights across all entities, with entity info

BACKEND — graph.py router, add 3 endpoints:
  POST /api/graph/cases/{case_id}/generate-insights
    Query param: max_entities=10 (limit to prevent very long ops)
    Fetches top entities by verified_facts count, generates + saves insights
    Returns: {entities_processed, insights_generated}
  DELETE /api/graph/node/{node_key}/insights/{insight_index}?case_id=...
    Calls reject_entity_insight → removes from array
  GET /api/graph/cases/{case_id}/insights
    Returns all pending insights across case

CREATE /frontend/src/components/workspace/InsightsPanel.jsx:
  "Generate Insights" button → POST to generate endpoint → show progress
  List of insight cards grouped by entity, showing:
    Entity name + type badge
    Insight text
    Confidence badge (green=high, amber=medium, red=low)
    Category badge
    Reasoning (collapsed by default, expandable)
    ✅ Accept button → calls existing POST verify-insight endpoint
    ❌ Reject button → calls new DELETE endpoint
  Bulk actions: "Accept All High Confidence" | "Reject All Low Confidence"
  Empty state: "No pending insights. Click Generate to analyze your case."

CaseOverviewView.jsx:
  Import and add <InsightsPanel caseId={caseId} authUsername={authUsername} />
  Add count badge if pending insights exist

DONE WHEN:
  Click Generate → LLM analyzes entities → insight cards appear.
  Accept → insight moves to verified facts. Reject → insight removed.
  Bulk accept/reject works. Insights persist between sessions.
  Generate for 10-entity case completes in under 90 seconds.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXECUTION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. READ before writing. Read every file you will touch before changing it.

2. Match patterns. Follow the exact async/await, Pydantic, Tailwind, and naming patterns
   already in the codebase. Do not introduce new libraries without checking they're needed.

3. Check before building. Never rebuild something that already exists. Verify the file first.

4. No silent failures. Every API call in the frontend must have error handling and show the
   user a meaningful message if something goes wrong.

5. Preserve data. Never delete records from Neo4j. Store original values before overwriting.

6. Sprint order matters. Complete Sprint 1 fully before starting Sprint 2.
   Sprint 2 fully before Sprint 3. Within each sprint, tasks can run in parallel.

7. After each task: briefly state what files were changed, what was added, and confirm
   the acceptance criteria are met.

Begin with Sprint 1. Start with tasks 1.1, 1.3, and 1.4 simultaneously (frontend-only,
no conflicts). Then 1.2 (backend/prompts) and 1.5 (full stack) in parallel.
```
