# OWL Investigation Platform — Testing Playbooks

> **Purpose:** Comprehensive testing playbooks covering the entire OWL investigation platform. Each playbook is a self-contained test plan that an agent (Claude Code) or manual tester can follow step-by-step to validate a logical section of the application.
>
> **Test Case:** "Operation Silver Bridge" (Case ID: `60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`) — a financial crime investigation with **171 entities** and **411 relationships** extracted from **10 ingested documents**.
>
> **Platform URLs:**
> - Frontend: `http://localhost:5173`
> - Backend API: `http://localhost:8000`
>
> **Auth Credentials:**
> - Email: `neil.byrne@gmail.com`
> - Password: `OwlAdmin123!`

---

## Table of Contents

- [Playbook 0: Case Creation & Evidence Ingestion (Reference)](#playbook-0-case-creation--evidence-ingestion-reference)
- [Playbook 1: Knowledge Graph — Viewing, Navigation & Search](#playbook-1-knowledge-graph--viewing-navigation--search)
- [Playbook 2: Knowledge Graph — CRUD Operations](#playbook-2-knowledge-graph--crud-operations)
- [Playbook 3: Entity Resolution & Merging](#playbook-3-entity-resolution--merging)
- [Playbook 4: Graph Analysis Tools (Spotlight Graph)](#playbook-4-graph-analysis-tools-spotlight-graph)
- [Playbook 5: Table View](#playbook-5-table-view)
- [Playbook 6: Timeline View](#playbook-6-timeline-view)
- [Playbook 7: Map View](#playbook-7-map-view)
- [Playbook 8: Financial Dashboard](#playbook-8-financial-dashboard)
- [Playbook 9: AI Assistant](#playbook-9-ai-assistant)
- [Playbook 10: Insights System](#playbook-10-insights-system)
- [Playbook 11: Workspace & Collaboration Features](#playbook-11-workspace--collaboration-features)
- [Playbook 12: Evidence & File Management](#playbook-12-evidence--file-management)
- [Playbook 13: Case Backup, Restore & Snapshots](#playbook-13-case-backup-restore--snapshots)
- [Playbook 14: User Management & Authentication](#playbook-14-user-management--authentication)
- [Playbook 15: Cost Tracking & System Monitoring](#playbook-15-cost-tracking--system-monitoring)
- [Playbook 16: LLM Configuration & Extraction Profiles](#playbook-16-llm-configuration--extraction-profiles)
- [Playbook 17: Database Management & Backfill](#playbook-17-database-management--backfill)
- [Playbook 18: Edge Cases & Error Handling](#playbook-18-edge-cases--error-handling)

---

## Playbook 0: Case Creation & Evidence Ingestion (Reference)

**Description:** This playbook documents the already-completed setup of the "Operation Silver Bridge" test case. It serves as a reference for the baseline state that all other playbooks depend on.

**Status:** ALREADY COMPLETED

### What Was Done

1. **Case Created:** "Operation Silver Bridge" was created via the Case Management view with case ID `60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
2. **Evidence Uploaded:** 10 evidence files were uploaded to the case (mix of PDF, CSV, TXT, and XLSX formats) covering financial records, corporate filings, communications, and transaction logs related to a money laundering investigation.
3. **Evidence Processed:** All 10 files were processed using the "fraud" extraction profile, which extracted entities and relationships using GPT-4o.
4. **Result:** The knowledge graph now contains **171 entities** and **411 relationships** spanning entity types including Person, Company, Account, Bank, Transaction, Location, Organisation, Document, and others.

### Key Entities for Testing

The following entities are known to exist in the case and are referenced throughout the playbooks:

- **People:** Marco Delgado, Elena Cruz, Roberto Salazar, Victor Mendoza
- **Companies:** Solaris Property Group, Cruz & Partners, Silver Bridge Capital
- **Locations:** New York City, Miami, Cayman Islands
- **Banks/Accounts:** Various financial institutions and account numbers
- **Transactions:** Wire transfers, cash deposits, and other financial movements

### Baseline State

- All 10 documents show "processed" status in Evidence Processing view
- The knowledge graph is fully populated and queryable
- The case is owned by user "Neil Byrne" (neil.byrne@gmail.com)

---

## Playbook 1: Knowledge Graph — Viewing, Navigation & Search

**Description:** Validate that the knowledge graph renders correctly, entity counts are accurate, search works, entity type filtering works, node details are accessible, context menus function, and the Spotlight Graph breadcrumb navigation operates properly.

**Prerequisites:**
- Operation Silver Bridge case is loaded (case ID: `60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`)
- User is authenticated as `neil.byrne@gmail.com`
- Backend and frontend servers are running

### Steps

**Step 1: Authenticate and navigate to Case Management**

- **Action:** Call `POST /api/auth/login` with `{"username": "neil.byrne@gmail.com", "password": "OwlAdmin123!"}`.
- **Expected:** Response returns a JWT token and user info with `name` containing "Neil" or "Byrne".
- **Pass:** HTTP 200 with valid token.
- **Fail:** Any error response or missing token.

**Step 2: Load the case graph data**

- **Action:** Call `GET /api/graph?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb` with the auth token.
- **Expected:** Response contains `nodes` array and `links` array. The nodes array should contain approximately 171 items. The links array should contain approximately 411 items.
- **Pass:** Response contains `nodes` with length >= 150 and `links` with length >= 350 (allowing for slight variations from merges/edits).
- **Fail:** Empty response, error, or drastically different counts.

**Step 3: Verify entity types are returned**

- **Action:** Call `GET /api/graph/entity-types?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response returns an array of entity type objects, each with a `type` and `count`. Common types expected: Person, Company, Account, Transaction, Location, Bank, Organisation.
- **Pass:** At least 5 distinct entity types returned, each with count > 0.
- **Fail:** Empty array or fewer than 3 entity types.

**Step 4: Search for a known entity — "Marco Delgado"**

- **Action:** Call `GET /api/graph/search?q=Marco+Delgado&limit=20&case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response contains at least one result with `name` matching "Marco Delgado" (case-insensitive partial match). The result should include `key`, `name`, `type`, and optionally `summary`.
- **Pass:** At least 1 result with name containing "Marco" or "Delgado".
- **Fail:** Empty results or error.

**Step 5: Search for a company entity — "Solaris"**

- **Action:** Call `GET /api/graph/search?q=Solaris&limit=20&case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** At least one result with name containing "Solaris" (e.g., "Solaris Property Group" or similar).
- **Pass:** At least 1 result returned with "Solaris" in the name.
- **Fail:** No results.

**Step 6: Get node details for a specific entity**

- **Action:** From Step 4 results, take the `key` of the Marco Delgado entity. Call `GET /api/graph/node/{key}?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response includes detailed node information: `name`, `type`, `summary`, `properties` object, `verified_facts` array (may be empty), `ai_insights` array (may be empty), `relationships` array listing connected entities.
- **Pass:** Response contains `name`, `type`, and `relationships` array with at least 1 relationship.
- **Fail:** Missing core fields or empty relationships for a central entity.

**Step 7: Get node neighbours**

- **Action:** Using the Marco Delgado `key`, call `GET /api/graph/node/{key}/neighbours?depth=1&case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response contains `nodes` and `links` arrays representing the 1-hop neighbourhood of Marco Delgado. Should include directly connected entities (companies, accounts, other people).
- **Pass:** `nodes` array has length >= 2 (Marco Delgado + at least 1 neighbour). `links` has length >= 1.
- **Fail:** Only the queried node returned, or error.

**Step 8: Get graph summary**

- **Action:** Call `GET /api/graph/summary?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response includes summary statistics such as `node_count`, `link_count` (or `relationship_count`), and possibly entity type breakdown.
- **Pass:** Summary contains node_count >= 150 and link/relationship count >= 350.
- **Fail:** Missing counts or zero values.

**Step 9: Filter graph by entity type (via frontend behavior)**

- **Action:** Call `GET /api/graph?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`. From the full graph data, filter nodes client-side to only show nodes where `type` === "Person".
- **Expected:** The filtered set should contain multiple Person entities including Marco Delgado, Elena Cruz, etc.
- **Pass:** At least 5 Person-type entities exist in the graph data.
- **Fail:** No Person entities found.

**Step 10: Verify pane view modes exist (frontend UI check)**

- **Action:** In the browser at `http://localhost:5173`, after loading the case into graph view, verify the layout controls are present. Look for the split-pane toggle button (the button with Layout/Maximize icon that toggles between single, split, minimized, and full pane modes).
- **Expected:** The graph view displays with a main graph panel and optionally a Spotlight Graph panel. Toggle buttons exist for switching pane layouts.
- **Pass:** Graph renders with visible pane controls.
- **Fail:** Graph does not render or pane controls are missing.

### Pass Criteria

All 10 steps pass. The knowledge graph loads with correct entity/relationship counts, search returns relevant results, node details contain expected fields (properties, relationships, verified facts, AI insights), entity types are correctly categorized, and graph summary statistics are accurate.

### Notes

- Entity and relationship counts may vary slightly if previous test runs have added or removed entities. The baseline is approximately 171 entities and 411 relationships.
- Search is case-insensitive and supports partial matching.
- The Spotlight Graph (subgraph) panel and breadcrumb navigation are tested more thoroughly in Playbook 4.

---

## Playbook 2: Knowledge Graph — CRUD Operations

**Description:** Validate creating, reading, updating, and deleting nodes and relationships in the knowledge graph. Also test pinning facts and batch updates.

**Prerequisites:**
- Authenticated as `neil.byrne@gmail.com` with valid token
- Operation Silver Bridge case loaded (case ID: `60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`)

### Steps

**Step 1: Create a new node — "Angela Torres" (Person)**

- **Action:** Call `POST /api/graph/create-node` with body:
  ```json
  {
    "name": "Angela Torres",
    "type": "Person",
    "description": "A potential witness in the Silver Bridge money laundering case",
    "summary": "Angela Torres is a former accountant at Cruz & Partners who may have knowledge of fraudulent transactions",
    "properties": {
      "role": "Witness",
      "occupation": "Accountant",
      "location": "Miami, FL"
    },
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb"
  }
  ```
- **Expected:** Response confirms node creation with a generated `key` for the new entity. Response should include the node's `name`, `type`, and `key`.
- **Pass:** HTTP 200/201 with a valid `key` returned and `name` === "Angela Torres".
- **Fail:** Error response or missing key.

**Step 2: Verify the new node exists via search**

- **Action:** Call `GET /api/graph/search?q=Angela+Torres&limit=5&case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** At least 1 result with name "Angela Torres".
- **Pass:** Search returns the newly created entity.
- **Fail:** Entity not found in search results.

**Step 3: Get details of the new node**

- **Action:** Call `GET /api/graph/node/{angela_key}?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb` using the key from Step 1.
- **Expected:** Response includes `name: "Angela Torres"`, `type: "Person"`, `summary` containing "former accountant", and `properties` containing `role`, `occupation`, `location`.
- **Pass:** All fields match what was submitted in Step 1.
- **Fail:** Missing or incorrect fields.

**Step 4: Edit the node — update properties**

- **Action:** Call `PUT /api/graph/node/{angela_key}` with body:
  ```json
  {
    "summary": "Angela Torres is a former senior accountant at Cruz & Partners. She resigned in 2024 and may be willing to cooperate with investigators.",
    "notes": "Initial contact made via attorney. Willing to meet under immunity agreement.",
    "properties": {
      "role": "Cooperating Witness",
      "occupation": "Former Senior Accountant",
      "location": "Miami, FL",
      "phone": "305-555-0142"
    }
  }
  ```
- **Expected:** Response confirms update. The summary, notes, and properties should be updated.
- **Pass:** HTTP 200 with updated values reflected.
- **Fail:** Error response or values not updated.

**Step 5: Verify edit persists — re-fetch node details**

- **Action:** Call `GET /api/graph/node/{angela_key}?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Summary now includes "senior accountant" and "resigned in 2024". Notes field is populated. Properties include `phone`.
- **Pass:** Updated values are present.
- **Fail:** Old values still shown.

**Step 6: Create a relationship between Angela Torres and Elena Cruz**

- **Action:** First, search for Elena Cruz: `GET /api/graph/search?q=Elena+Cruz&limit=5&case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`. Get her key. Then call `POST /api/graph/relationships` with body:
  ```json
  {
    "relationships": [
      {
        "source_key": "{angela_key}",
        "target_key": "{elena_key}",
        "type": "WORKED_WITH",
        "properties": {
          "context": "Both employed at Cruz & Partners from 2020-2024",
          "confidence": "high"
        }
      }
    ],
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb"
  }
  ```
- **Expected:** Response confirms relationship creation.
- **Pass:** HTTP 200 with confirmation of 1 relationship created.
- **Fail:** Error response.

**Step 7: Verify relationship exists in node neighbours**

- **Action:** Call `GET /api/graph/node/{angela_key}/neighbours?depth=1&case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Elena Cruz appears as a neighbour of Angela Torres with relationship type "WORKED_WITH".
- **Pass:** Elena Cruz's key appears in the neighbours' nodes array.
- **Fail:** Elena Cruz not found in neighbours.

**Step 8: Pin a fact on an existing node**

- **Action:** Get node details for a well-populated entity (e.g., Marco Delgado). If `verified_facts` array has at least 1 item, call `PUT /api/graph/node/{marco_key}/pin-fact?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "fact_index": 0,
    "pinned": true
  }
  ```
- **Expected:** Response confirms the fact has been pinned.
- **Pass:** HTTP 200 and the fact at index 0 now has `pinned: true`.
- **Fail:** Error response or fact not pinned. If no verified facts exist, skip this step (not a failure).

**Step 9: Batch update multiple nodes**

- **Action:** Call `PUT /api/graph/batch-update` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "updates": [
      {
        "node_key": "{angela_key}",
        "properties": { "status": "Active Witness" }
      }
    ]
  }
  ```
- **Expected:** Response confirms batch update was successful.
- **Pass:** HTTP 200 with success confirmation.
- **Fail:** Error response.

**Step 10: Delete the test node — Angela Torres**

- **Action:** Call `DELETE /api/graph/node/{angela_key}?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response confirms deletion (HTTP 200 or 204). The node and its relationships (including the WORKED_WITH relationship) should be removed.
- **Pass:** HTTP 200/204.
- **Fail:** Error response.

**Step 11: Verify deletion — search should not find the node**

- **Action:** Call `GET /api/graph/search?q=Angela+Torres&limit=5&case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** No results for "Angela Torres".
- **Pass:** Empty results or no matching entities.
- **Fail:** Deleted entity still appears.

**Step 12: Verify graph count is restored**

- **Action:** Call `GET /api/graph/summary?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Node count is back to the original value (approximately 171), confirming the test node was properly cleaned up.
- **Pass:** Node count matches pre-test baseline (within +/- 2).
- **Fail:** Count is significantly different from baseline.

### Pass Criteria

All 12 steps pass. Nodes can be created with full metadata, searched, edited, connected via relationships, facts can be pinned, batch updates work, and deletion properly removes nodes and their relationships.

### Notes

- This playbook creates and then deletes a test entity to avoid polluting the test dataset.
- If the pin-fact step is skipped (no verified facts available), note this in the test report.
- The relationship creation between Angela Torres and Elena Cruz is automatically cleaned up when Angela Torres is deleted.

---

## Playbook 3: Entity Resolution & Merging

**Description:** Validate the entity resolution workflow: finding similar entities, reviewing comparison pairs, merging duplicates, and rejecting false positives.

**Prerequisites:**
- Authenticated with valid token
- Operation Silver Bridge case loaded (case ID: `60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`)

### Steps

**Step 1: Find similar entities (non-streaming)**

- **Action:** Call `POST /api/graph/find-similar-entities` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "entity_types": null,
    "name_similarity_threshold": 0.7,
    "max_results": 50
  }
  ```
- **Expected:** Response contains an array of similar entity pairs. Each pair includes two entities with their names, keys, types, and a similarity score.
- **Pass:** Response is valid JSON. If similar entities exist, each pair has `entity1`, `entity2`, and `similarity` fields. If no similar entities are found, an empty array is acceptable.
- **Fail:** Error response or malformed data.

**Step 2: Find similar entities filtered by type**

- **Action:** Call `POST /api/graph/find-similar-entities` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "entity_types": ["Person"],
    "name_similarity_threshold": 0.6,
    "max_results": 50
  }
  ```
- **Expected:** Response contains only pairs where both entities are of type "Person". The lower threshold (0.6) may surface more potential matches.
- **Pass:** All returned pairs have entities with type "Person" (or empty array if no matches).
- **Fail:** Non-Person entities in results, or error.

**Step 3: Find similar entities via streaming endpoint**

- **Action:** Call `GET /api/graph/find-similar-entities/stream?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb&name_similarity_threshold=0.7&max_results=50`.
- **Expected:** Response is a Server-Sent Events (SSE) stream. Events should include `start`, optionally `type_start`, `progress`, `type_complete`, and finally `complete`. The `complete` event contains the full results.
- **Pass:** Stream opens successfully and eventually emits a `complete` event with results (or empty results). No `error` event emitted.
- **Fail:** Stream fails to open, emits `error` event, or never completes.

**Step 4: Create two test entities with similar names for merge testing**

- **Action:** Create two entities:
  - Entity A: `POST /api/graph/create-node` with `{"name": "John R. Mercer", "type": "Person", "summary": "Test entity for merge", "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb"}`
  - Entity B: `POST /api/graph/create-node` with `{"name": "John Robert Mercer", "type": "Person", "summary": "Test entity for merge - duplicate", "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb"}`
- **Expected:** Both entities created successfully with unique keys.
- **Pass:** Two valid keys returned.
- **Fail:** Either creation fails.

**Step 5: Verify similar entities scan detects the test pair**

- **Action:** Call `POST /api/graph/find-similar-entities` with `entity_types: ["Person"]` and `name_similarity_threshold: 0.5`.
- **Expected:** The pair (John R. Mercer, John Robert Mercer) should appear in results with a high similarity score (likely > 0.7).
- **Pass:** The test pair appears in results.
- **Fail:** Test pair not detected (may indicate threshold issue — note the threshold used).

**Step 6: Merge the two test entities**

- **Action:** Call `POST /api/graph/merge-entities` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "source_key": "{entity_a_key}",
    "target_key": "{entity_b_key}",
    "merged_data": {
      "name": "John Robert Mercer",
      "type": "Person",
      "summary": "Merged entity - John R. Mercer / John Robert Mercer",
      "notes": "Merged during entity resolution testing"
    }
  }
  ```
- **Expected:** Response confirms merge. One entity should remain (the target), and the source entity should be removed. All relationships from both entities should be preserved on the merged entity.
- **Pass:** HTTP 200 with merge confirmation. Searching for the merged name returns exactly 1 result.
- **Fail:** Error or both entities still exist.

**Step 7: Verify merge result**

- **Action:** Search for "John Robert Mercer" and verify only 1 entity exists. Then search for "John R. Mercer" and verify the old entity is gone.
- **Expected:** Only the merged entity remains.
- **Pass:** Exactly 1 entity with name "John Robert Mercer". No entity with exact name "John R. Mercer".
- **Fail:** Duplicate still exists.

**Step 8: Create another test pair for rejection testing**

- **Action:** Create two entities:
  - Entity C: `POST /api/graph/create-node` with `{"name": "James Wilson", "type": "Person", "summary": "Test entity for reject", "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb"}`
  - Entity D: `POST /api/graph/create-node` with `{"name": "James B. Wilson", "type": "Person", "summary": "Different person with similar name", "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb"}`
- **Expected:** Both entities created.
- **Pass:** Two valid keys returned.
- **Fail:** Either creation fails.

**Step 9: Reject the pair as a false positive**

- **Action:** Call `POST /api/graph/reject-merge` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "entity_key_1": "{entity_c_key}",
    "entity_key_2": "{entity_d_key}"
  }
  ```
- **Expected:** Response confirms rejection.
- **Pass:** HTTP 200 with rejection confirmation.
- **Fail:** Error response.

**Step 10: Verify rejected pair is stored**

- **Action:** Call `GET /api/graph/rejected-merges?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response includes the rejected pair (entity_c_key, entity_d_key) in the `rejected_pairs` array.
- **Pass:** The pair appears in rejected merges list.
- **Fail:** Pair not found in rejected list.

**Step 11: Undo the rejection**

- **Action:** From Step 10, get the `rejection_id` of the test pair. Call `DELETE /api/graph/rejected-merges/{rejection_id}`.
- **Expected:** Rejection is removed.
- **Pass:** HTTP 200/204. The pair no longer appears in rejected merges.
- **Fail:** Error or pair still in rejected list.

**Step 12: Clean up test entities**

- **Action:** Delete the merged entity (John Robert Mercer), James Wilson, and James B. Wilson using `DELETE /api/graph/node/{key}?case_id=...`.
- **Expected:** All test entities removed.
- **Pass:** All deletions return HTTP 200/204.
- **Fail:** Any deletion fails.

### Pass Criteria

All 12 steps pass. The similar entity detection finds near-duplicates, merging consolidates two entities into one while preserving relationships, rejection marks pairs as false positives, and undo-rejection reverses that decision. All test entities are cleaned up.

### Notes

- The streaming endpoint (Step 3) uses SSE and may require special handling in automated tests.
- Similarity thresholds can be adjusted. A threshold of 0.7 is the default. Lower thresholds (0.5-0.6) may be needed to catch the test pair depending on the fuzzy matching algorithm.
- Entity merge preserves all relationships from both source and target entities.

---

## Playbook 4: Graph Analysis Tools (Spotlight Graph)

**Description:** Validate the graph analysis algorithms (Shortest Paths, PageRank, Louvain Community Detection, Betweenness Centrality) and the Spotlight Graph subgraph functionality.

**Prerequisites:**
- Authenticated with valid token
- Operation Silver Bridge case loaded (case ID: `60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`)
- At least 2 entity keys known (obtained via search in Playbook 1)

### Steps

**Step 1: Search for two entities to use in analysis**

- **Action:** Search for "Marco Delgado" and "Cayman Islands" (or another Location entity). Record both keys.
  - `GET /api/graph/search?q=Marco+Delgado&limit=5&case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`
  - `GET /api/graph/search?q=Cayman&limit=5&case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`
- **Expected:** Both searches return results. Record the `key` for each.
- **Pass:** Both entities found with valid keys.
- **Fail:** Either entity not found (substitute another known entity if needed).

**Step 2: Run Shortest Paths between two entities**

- **Action:** Call `POST /api/graph/shortest-paths` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "node_keys": ["{marco_key}", "{cayman_key}"],
    "max_depth": 10
  }
  ```
- **Expected:** Response contains `nodes` and `links` arrays representing the shortest path(s) between the two entities. The path should include intermediate entities (e.g., companies, accounts, transactions that connect Marco Delgado to Cayman Islands).
- **Pass:** `nodes` array has length >= 2 (at least the two queried nodes). `links` array has length >= 1. A path exists between the entities.
- **Fail:** Empty results (no path found) or error. If no path exists, this is informational — the entities may not be connected.

**Step 3: Run PageRank to identify influential nodes**

- **Action:** Call `POST /api/graph/pagerank` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "node_keys": null,
    "top_n": 20,
    "iterations": 20,
    "damping_factor": 0.85
  }
  ```
- **Expected:** Response contains an array of nodes ranked by PageRank score. Top nodes should be central entities in the investigation (likely key people, companies, or accounts with many connections).
- **Pass:** Response contains at least 10 ranked nodes, each with a `score` field > 0. The top-ranked nodes should be recognizable case entities.
- **Fail:** Empty results or error.

**Step 4: Run Louvain Community Detection**

- **Action:** Call `POST /api/graph/louvain` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "node_keys": null,
    "resolution": 1.0,
    "max_iterations": 10
  }
  ```
- **Expected:** Response contains community assignments for nodes. Each node should have a `community` ID. Multiple communities should be detected (at least 2-3 groups of related entities).
- **Pass:** Response contains community data with at least 2 distinct communities. Nodes are assigned to communities.
- **Fail:** All nodes in same community (no clustering detected) or error.

**Step 5: Run Betweenness Centrality**

- **Action:** Call `POST /api/graph/betweenness-centrality` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "node_keys": null,
    "top_n": 20,
    "normalized": true
  }
  ```
- **Expected:** Response contains nodes ranked by betweenness centrality score. Bridge nodes (entities that connect different groups) should rank highest.
- **Pass:** Response contains at least 10 ranked nodes with `score` field. Top nodes should be different from PageRank results (though overlap is acceptable).
- **Fail:** Empty results or error.

**Step 6: Expand a node to see its neighbours**

- **Action:** Call `POST /api/graph/expand-nodes` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "node_keys": ["{marco_key}"],
    "depth": 1
  }
  ```
- **Expected:** Response contains `nodes` and `links` arrays for the expanded neighbourhood. Should include Marco Delgado plus all directly connected entities and their mutual relationships.
- **Pass:** `nodes` array has length >= 3 (Marco + at least 2 neighbours). `links` array populated.
- **Fail:** Only the queried node returned, or error.

**Step 7: Expand with depth 2**

- **Action:** Call `POST /api/graph/expand-nodes` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "node_keys": ["{marco_key}"],
    "depth": 2
  }
  ```
- **Expected:** Response contains a larger neighbourhood than Step 6, including 2-hop connections. More nodes and links should be returned.
- **Pass:** `nodes` count > Step 6 `nodes` count. `links` count > Step 6 `links` count.
- **Fail:** Same or fewer results than depth 1.

**Step 8: Run Shortest Paths with multiple source nodes (subgraph creation)**

- **Action:** Search for a third entity (e.g., "Elena Cruz"). Call `POST /api/graph/shortest-paths` with 3 node keys:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "node_keys": ["{marco_key}", "{elena_key}", "{cayman_key}"],
    "max_depth": 10
  }
  ```
- **Expected:** Response contains shortest paths between all pairs of the 3 entities, forming a subgraph that connects them.
- **Pass:** Results contain paths connecting at least 2 of the 3 entities.
- **Fail:** No paths found between any pair, or error.

### Pass Criteria

All 8 steps pass. The graph analysis algorithms (Shortest Paths, PageRank, Louvain, Betweenness Centrality) return meaningful results. Node expansion works at different depths. The Spotlight Graph can be built from shortest paths between multiple entities.

### Notes

- PageRank and Betweenness Centrality may highlight different entities. PageRank favors well-connected nodes; Betweenness Centrality favors bridge nodes.
- Louvain community detection with `resolution: 1.0` is the default. Higher resolution values produce more, smaller communities.
- If Shortest Paths returns no path, the two entities may not be connected in the graph. Try different entity pairs.
- The Spotlight Graph breadcrumb navigation is a frontend feature that tracks subgraph history. Each shortest path or expand operation creates a new breadcrumb entry that can be navigated back to.

---

## Playbook 5: Table View

**Description:** Validate the Table view of entities including pagination, sorting, filtering, bulk operations (merge, delete, edit), and the Add Node functionality.

**Prerequisites:**
- Authenticated with valid token
- Operation Silver Bridge case loaded
- Full graph data available

### Steps

**Step 1: Load all entities for table display**

- **Action:** Call `GET /api/graph?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb` to get all nodes.
- **Expected:** Response contains `nodes` array with approximately 171 entities.
- **Pass:** `nodes` array has length >= 150.
- **Fail:** Empty or significantly reduced node count.

**Step 2: Verify entity data has table-compatible fields**

- **Action:** Inspect the first 5 nodes from Step 1. Each node should have at minimum: `key`, `name`, `type`.
- **Expected:** All nodes have `key`, `name`, and `type` fields. Most have additional fields like `summary`, `notes`, and type-specific `properties`.
- **Pass:** All inspected nodes have the required fields.
- **Fail:** Any node missing `key`, `name`, or `type`.

**Step 3: Test entity type filtering (client-side)**

- **Action:** From the full graph data, filter to show only "Company" type entities.
- **Expected:** Filtered list contains only Company entities (e.g., Solaris Property Group, Cruz & Partners, Silver Bridge Capital).
- **Pass:** All entities in filtered set have `type === "Company"`. At least 3 Company entities exist.
- **Fail:** Non-Company entities in filtered set, or no Company entities.

**Step 4: Test sorting by name (client-side)**

- **Action:** Sort all nodes alphabetically by `name` (A-Z).
- **Expected:** First entity alphabetically should start with a letter early in the alphabet. Last entity should start with a letter late in the alphabet.
- **Pass:** Sort order is correct (each name >= previous name in alphabetical order).
- **Fail:** Sort order is incorrect.

**Step 5: Test pagination (client-side)**

- **Action:** With page size 50, verify that page 1 shows entities 1-50, page 2 shows entities 51-100, etc.
- **Expected:** With ~171 entities and page size 50, there should be 4 pages (50+50+50+21). Page size options available are: 50, 100, 250, 500, 1000, All.
- **Pass:** Correct number of pages calculated. Each page shows the correct slice of data.
- **Fail:** Pagination math is incorrect.

**Step 6: Create a node from table view (via API)**

- **Action:** Call `POST /api/graph/create-node` with:
  ```json
  {
    "name": "Table Test Entity",
    "type": "Document",
    "summary": "Created from table view test",
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb"
  }
  ```
- **Expected:** Node created successfully. Record the key.
- **Pass:** HTTP 200 with valid key.
- **Fail:** Error response.

**Step 7: Verify new entity appears in graph data**

- **Action:** Re-fetch graph data and verify "Table Test Entity" is present.
- **Expected:** Entity appears in the nodes array.
- **Pass:** Entity found with correct name and type.
- **Fail:** Entity not found.

**Step 8: Bulk update test — update entity via batch endpoint**

- **Action:** Call `PUT /api/graph/batch-update` with:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "updates": [
      {
        "node_key": "{table_test_key}",
        "properties": { "status": "reviewed", "priority": "low" }
      }
    ]
  }
  ```
- **Expected:** Batch update succeeds.
- **Pass:** HTTP 200 with success confirmation.
- **Fail:** Error response.

**Step 9: Verify batch update**

- **Action:** Call `GET /api/graph/node/{table_test_key}?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Node properties include `status: "reviewed"` and `priority: "low"`.
- **Pass:** Properties updated correctly.
- **Fail:** Properties not updated.

**Step 10: Delete test entity (simulating bulk delete)**

- **Action:** Call `DELETE /api/graph/node/{table_test_key}?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Entity deleted.
- **Pass:** HTTP 200/204.
- **Fail:** Error response.

**Step 11: Verify deletion**

- **Action:** Search for "Table Test Entity".
- **Expected:** No results.
- **Pass:** Entity not found.
- **Fail:** Entity still exists.

### Pass Criteria

All 11 steps pass. Graph data loads with correct entity structure for table display. Client-side filtering, sorting, and pagination work correctly. CRUD operations from the table context (add, edit via batch, delete) function properly.

### Notes

- The Table View in the frontend (GraphTableView component) supports dynamic columns based on entity properties.
- Page size options are: 50, 100, 250, 500, 1000, All.
- Bulk merge in the table view uses the same merge API tested in Playbook 3.
- The table supports multi-select via checkboxes for bulk operations.
- Column filtering uses unique value extraction from the current dataset.

---

## Playbook 6: Timeline View

**Description:** Validate the Timeline view which displays temporal events extracted from the case entities.

**Prerequisites:**
- Authenticated with valid token
- Operation Silver Bridge case loaded (case ID: `60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`)
- Entities with date/time properties exist in the graph

### Steps

**Step 1: Fetch timeline events**

- **Action:** Call `GET /api/timeline?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response contains `events` array and `total` count. Each event should have at minimum: `date`, `name` or `description`, `type`, and `entity_key`.
- **Pass:** `events` array has length >= 1 and `total` > 0.
- **Fail:** Empty events array. Note: If no timeline data exists, this is expected for cases where entities lack temporal data. Record as "N/A — no timeline data".

**Step 2: Fetch available event types**

- **Action:** Call `GET /api/timeline/types`.
- **Expected:** Response contains an array of distinct event types found in the data.
- **Pass:** At least 1 event type returned.
- **Fail:** Empty array (may be acceptable if no timeline events exist).

**Step 3: Filter timeline by event type**

- **Action:** If event types were returned in Step 2, pick the first type. Call `GET /api/timeline?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb&types={first_type}`.
- **Expected:** Response contains only events of the specified type.
- **Pass:** All returned events match the filtered type.
- **Fail:** Events of other types present in filtered results.

**Step 4: Filter timeline by date range**

- **Action:** Call `GET /api/timeline?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb&start_date=2023-01-01&end_date=2024-12-31`.
- **Expected:** Response contains only events within the specified date range.
- **Pass:** All returned events have dates between 2023-01-01 and 2024-12-31 (inclusive).
- **Fail:** Events outside the date range present.

**Step 5: Verify timeline data can be converted from graph nodes (frontend logic)**

- **Action:** Fetch full graph data via `GET /api/graph?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`. Inspect nodes for date-related properties (e.g., `date`, `transaction_date`, `created_date`).
- **Expected:** Some nodes have temporal properties that can be displayed on a timeline.
- **Pass:** At least 5 nodes have date-related properties.
- **Fail:** No nodes have date properties (timeline view would show "no data").

**Step 6: Verify event details link back to entities**

- **Action:** If events were returned in Step 1, pick one event and verify it has an `entity_key` field. Use that key to fetch node details: `GET /api/graph/node/{entity_key}?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** The node exists and its properties correspond to the timeline event data.
- **Pass:** Node found and relevant properties match the event.
- **Fail:** Node not found or data mismatch.

### Pass Criteria

Steps 1 and 2 must pass (API endpoints respond correctly). Steps 3-6 pass if timeline data exists. If no timeline data is present, steps 3-6 are recorded as "N/A — no timeline data" and this is not considered a failure.

### Notes

- The Timeline View (TimelineView component) displays events on a vertical timeline with swim lanes organized by entity.
- Timeline events are derived from entities that have temporal properties (dates, timestamps).
- The frontend uses `convertGraphNodesToTimelineEvents` utility to transform graph data into timeline events.
- The view includes zoom controls (ZoomControls component) and a date range filter (DateRangeFilter component).
- The swim lane layout (SwimLaneColumn component) organizes events by entity for visual grouping.

---

## Playbook 7: Map View

**Description:** Validate the Map view which displays geocoded entities as location pins on an interactive map.

**Prerequisites:**
- Authenticated with valid token
- Operation Silver Bridge case loaded (case ID: `60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`)
- Some entities have geocoded locations (latitude/longitude)

### Steps

**Step 1: Fetch entities with locations**

- **Action:** Call `GET /api/graph/locations?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response contains an array of entities that have latitude and longitude coordinates. Expected locations include New York City, Miami, and Cayman Islands.
- **Pass:** At least 1 entity returned with `latitude` and `longitude` fields.
- **Fail:** Empty response. If no geocoded entities exist, record as "N/A — no geocoded entities" and proceed to Step 5.

**Step 2: Verify expected locations are present**

- **Action:** Inspect the locations from Step 1 for known case locations.
- **Expected:** At least some of these locations should be present:
  - New York City (Solaris Property Group office) — approximately lat 40.7, lon -74.0
  - Miami (Silver Bridge Club, Cruz & Partners) — approximately lat 25.8, lon -80.2
  - Cayman Islands — approximately lat 19.3, lon -81.4
- **Pass:** At least 1 of the expected locations is found (within reasonable coordinate ranges).
- **Fail:** None of the expected locations found.

**Step 3: Verify location entities have required fields**

- **Action:** For each location entity, check for: `key`, `name`, `type`, `latitude`, `longitude`, and optionally `location_name`.
- **Expected:** All location entities have valid numeric coordinates and a name.
- **Pass:** All entities have `latitude` (number between -90 and 90) and `longitude` (number between -180 and 180).
- **Fail:** Missing or invalid coordinates.

**Step 4: Update a location on an entity**

- **Action:** Pick a location entity from Step 1. Call `PUT /api/graph/node/{key}/location` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "location_name": "Updated Test Location",
    "latitude": 40.7128,
    "longitude": -74.0060
  }
  ```
- **Expected:** Location updated successfully.
- **Pass:** HTTP 200 with confirmation.
- **Fail:** Error response.

**Step 5: Add location to an entity that lacks one**

- **Action:** Search for an entity without coordinates (e.g., a Person entity). Call `PUT /api/graph/node/{person_key}/location` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "location_name": "Test Location - Will Remove",
    "latitude": 25.7617,
    "longitude": -80.1918
  }
  ```
- **Expected:** Location added to the entity.
- **Pass:** HTTP 200. Entity now appears in locations endpoint.
- **Fail:** Error response.

**Step 6: Verify new location appears**

- **Action:** Call `GET /api/graph/locations?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** The entity from Step 5 now appears in the locations list.
- **Pass:** Entity found with correct coordinates.
- **Fail:** Entity not in locations list.

**Step 7: Remove location from entity**

- **Action:** Call `DELETE /api/graph/node/{person_key}/location?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Location removed from the entity.
- **Pass:** HTTP 200/204.
- **Fail:** Error response.

**Step 8: Verify location removed**

- **Action:** Call `GET /api/graph/locations?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** The entity from Step 5 no longer appears in locations list (unless it originally had coordinates).
- **Pass:** Entity not in locations list (or back to original state).
- **Fail:** Entity still shows test location.

**Step 9: Restore original location (if modified in Step 4)**

- **Action:** If Step 4 modified an existing location, restore it to its original coordinates using the same PUT endpoint.
- **Expected:** Location restored.
- **Pass:** HTTP 200.
- **Fail:** Error response.

### Pass Criteria

Steps 1-3 must pass if geocoded entities exist. Steps 4-9 test CRUD operations on locations and must all pass. If no geocoded entities exist initially, Steps 1-3 are "N/A" but Steps 5-8 should still pass (adding/removing a test location).

### Notes

- The Map View (MapView component) uses an interactive map library to display location pins.
- The map supports additional features: HeatmapLayer, HotspotPanel, MovementTrails, ProximityAnalysis, RouteAnalysis, and TimeControl components.
- Location coordinates should be valid WGS84 (latitude: -90 to 90, longitude: -180 to 180).
- The map view uses `convertGraphNodesToMapLocations` utility to transform graph data for display.
- Right-clicking a pin in the frontend provides options to edit or remove the location.

---

## Playbook 8: Financial Dashboard

**Description:** Validate the Financial Dashboard view including transaction loading, filtering, categorization, amount editing, sub-transactions, PDF export, and chart data.

**Prerequisites:**
- Authenticated with valid token
- Operation Silver Bridge case loaded (case ID: `60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`)
- Financial transaction entities exist in the graph

### Steps

**Step 1: Fetch financial transactions**

- **Action:** Call `GET /api/financial?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response contains `transactions` array with financial entities. Each transaction should have: `key`, `name`, `type`, `amount` (or equivalent), and optionally `date`, `from_entity`, `to_entity`, `category`.
- **Pass:** `transactions` array has length >= 1.
- **Fail:** Empty transactions array. Note: If no financial transactions exist, record as "N/A — no financial data" for subsequent steps.

**Step 2: Fetch financial summary**

- **Action:** Call `GET /api/financial/summary?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response contains summary statistics: `total_amount`, `transaction_count`, and possibly breakdowns by type or category.
- **Pass:** Summary contains `transaction_count` matching Step 1's array length.
- **Fail:** Missing or inconsistent summary data.

**Step 3: Fetch transaction volume over time**

- **Action:** Call `GET /api/financial/volume?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response contains `data` array with time-series volume data (date + amount pairs for charting).
- **Pass:** `data` array has length >= 0 (may be empty if no dated transactions).
- **Fail:** Error response.

**Step 4: Fetch available categories**

- **Action:** Call `GET /api/financial/categories?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response contains `categories` array with objects having `name`, `color`, and `builtin` fields.
- **Pass:** At least 1 category returned.
- **Fail:** Empty categories (predefined categories should always exist).

**Step 5: Filter transactions by type**

- **Action:** From Step 1, identify distinct transaction types. Call `GET /api/financial?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb&types={first_type}`.
- **Expected:** Only transactions of the specified type are returned.
- **Pass:** All returned transactions have the filtered type.
- **Fail:** Transactions of other types present.

**Step 6: Filter transactions by date range**

- **Action:** Call `GET /api/financial?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb&start_date=2023-01-01&end_date=2024-12-31`.
- **Expected:** Only transactions within the date range are returned.
- **Pass:** All returned transactions have dates within range.
- **Fail:** Transactions outside range present.

**Step 7: Categorize a transaction**

- **Action:** Pick a transaction key from Step 1 and a category from Step 4. Call `PUT /api/financial/categorize/{node_key}` with body:
  ```json
  {
    "category": "{category_name}",
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb"
  }
  ```
- **Expected:** Transaction categorized successfully.
- **Pass:** HTTP 200 with confirmation.
- **Fail:** Error response.

**Step 8: Batch categorize multiple transactions**

- **Action:** Pick 2 transaction keys. Call `PUT /api/financial/batch-categorize` with body:
  ```json
  {
    "node_keys": ["{key1}", "{key2}"],
    "category": "{category_name}",
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb"
  }
  ```
- **Expected:** Both transactions categorized.
- **Pass:** HTTP 200.
- **Fail:** Error response.

**Step 9: Edit a transaction amount**

- **Action:** Pick a transaction key. Call `PUT /api/financial/transactions/{node_key}/amount` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "new_amount": 99999.99,
    "correction_reason": "Test correction — will revert"
  }
  ```
- **Expected:** Amount updated with correction logged.
- **Pass:** HTTP 200.
- **Fail:** Error response.

**Step 10: Verify amount update and revert**

- **Action:** Re-fetch the transaction data. Verify the amount changed to 99999.99. Then revert it using the same endpoint with the original amount and reason "Reverting test correction".
- **Expected:** Amount is updated, then restored.
- **Pass:** Both updates succeed.
- **Fail:** Amount not updated or revert fails.

**Step 11: Update transaction details (purpose, notes)**

- **Action:** Call `PUT /api/financial/details/{node_key}` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "purpose": "Test purpose update",
    "notes": "Test notes — will revert"
  }
  ```
- **Expected:** Details updated.
- **Pass:** HTTP 200.
- **Fail:** Error response.

**Step 12: Link a sub-transaction**

- **Action:** Pick two transaction keys (parent and child). Call `POST /api/financial/transactions/{parent_key}/sub-transactions` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "child_key": "{child_key}"
  }
  ```
- **Expected:** Sub-transaction linked.
- **Pass:** HTTP 200.
- **Fail:** Error response.

**Step 13: Get sub-transactions**

- **Action:** Call `GET /api/financial/transactions/{parent_key}/sub-transactions?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response includes the child transaction linked in Step 12.
- **Pass:** Child transaction appears in sub-transactions list.
- **Fail:** Child not found.

**Step 14: Unlink sub-transaction**

- **Action:** Call `DELETE /api/financial/transactions/{child_key}/parent?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Sub-transaction unlinked.
- **Pass:** HTTP 200/204.
- **Fail:** Error response.

**Step 15: Verify PDF export endpoint**

- **Action:** Call `GET /api/financial/export/pdf?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response returns a PDF file (Content-Type: application/pdf) or a redirect to PDF generation.
- **Pass:** HTTP 200 with PDF content or valid response.
- **Fail:** Error response or non-PDF content.

### Pass Criteria

Steps 1-4 must pass (basic data loading). Steps 5-14 must pass if financial transactions exist. Step 15 must return a valid response. If no financial data exists, Steps 5-14 are "N/A".

### Notes

- The Financial View (FinancialView component) includes: FinancialSummaryCards, FinancialCharts, FinancialTable, and FinancialFilterPanel.
- Transaction types may include: wire_transfer, cash_deposit, check, ACH, etc.
- Categories have associated colors for visual grouping.
- The SubTransactionModal component handles creating parent-child transaction hierarchies.
- PDF export opens in a new browser tab via `/api/financial/export/pdf`.

---

## Playbook 9: AI Assistant

**Description:** Validate the AI chat assistant including asking questions about the case, verifying the hybrid retrieval pipeline (vector + graph), checking pipeline traces, and saving responses as notes.

**Prerequisites:**
- Authenticated with valid token
- Operation Silver Bridge case loaded (case ID: `60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`)
- LLM service is configured and accessible (OpenAI API key set)

### Steps

**Step 1: Get current LLM configuration**

- **Action:** Call `GET /api/llm-config/current`.
- **Expected:** Response shows the active LLM model and provider (e.g., provider: "openai", model: "gpt-4o").
- **Pass:** Valid provider and model returned.
- **Fail:** No configuration or error.

**Step 2: Ask a question about the case**

- **Action:** Call `POST /api/chat` with body:
  ```json
  {
    "question": "Who is the ringleader of the money laundering operation in this case?",
    "model": null,
    "provider": null
  }
  ```
  Note: The chat endpoint uses the currently loaded case context.
- **Expected:** Response contains an `answer` field with a coherent response referencing case entities. The response should mention key figures like Marco Delgado or other central characters. Response may also include `pipeline_trace` with retrieval details.
- **Pass:** `answer` field is non-empty and references at least one case entity by name.
- **Fail:** Empty answer, generic response with no case-specific content, or error. Note: LLM API errors (rate limits, key issues) should be recorded but may not indicate a platform bug.

**Step 3: Verify pipeline trace in response**

- **Action:** Inspect the response from Step 2 for `pipeline_trace` or similar field.
- **Expected:** The pipeline trace should include:
  - Text passages retrieved from the vector database (document chunks)
  - Graph entities retrieved from Neo4j
  - The retrieval method used (hybrid: vector + graph)
  - Confidence scores or relevance scores for retrieved passages
- **Pass:** Pipeline trace contains both text passages and graph entities.
- **Fail:** Pipeline trace missing or contains only one retrieval type.

**Step 4: Ask a financial question**

- **Action:** Call `POST /api/chat` with body:
  ```json
  {
    "question": "What was the total amount of money transferred to accounts in the Cayman Islands?"
  }
  ```
- **Expected:** Response references financial transactions and Cayman Islands entities. Should include specific amounts if available in the data.
- **Pass:** Answer mentions Cayman Islands and references financial data.
- **Fail:** No case-specific financial information in response.

**Step 5: Extract entity keys from an answer**

- **Action:** Using the answer from Step 2, call `POST /api/chat/extract-nodes` with body:
  ```json
  {
    "answer": "{answer_text_from_step_2}"
  }
  ```
- **Expected:** Response contains an array of entity keys mentioned in the answer.
- **Pass:** At least 1 entity key extracted from the answer.
- **Fail:** Empty array (the answer should reference entities).

**Step 6: Get suggested questions**

- **Action:** Call `POST /api/chat/suggestions` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "selected_keys": null
  }
  ```
- **Expected:** Response contains an array of suggested questions relevant to the case.
- **Pass:** At least 1 suggested question returned.
- **Fail:** Empty suggestions or error.

**Step 7: Test chat history — create a chat history entry**

- **Action:** Call `POST /api/chat-history` with body:
  ```json
  {
    "messages": [
      {"role": "user", "content": "Who is Marco Delgado?"},
      {"role": "assistant", "content": "Test response for chat history testing"}
    ],
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "title": "Test Chat History"
  }
  ```
- **Expected:** Chat history entry created with an `id`.
- **Pass:** HTTP 200/201 with valid `id`.
- **Fail:** Error response.

**Step 8: List chat histories**

- **Action:** Call `GET /api/chat-history`.
- **Expected:** Response includes the chat history created in Step 7.
- **Pass:** At least 1 chat history returned, including the test entry.
- **Fail:** Empty list.

**Step 9: Get specific chat history**

- **Action:** Call `GET /api/chat-history/{chat_id}` using the ID from Step 7.
- **Expected:** Response contains the full chat history with messages array.
- **Pass:** Messages array contains the user and assistant messages from Step 7.
- **Fail:** Missing or incorrect messages.

**Step 10: Delete test chat history**

- **Action:** Call `DELETE /api/chat-history/{chat_id}`.
- **Expected:** Chat history deleted.
- **Pass:** HTTP 200/204.
- **Fail:** Error response.

### Pass Criteria

Steps 1, 6-10 must pass (LLM config, suggestions, chat history CRUD). Steps 2-5 should pass but may fail due to external LLM API issues (rate limits, API key problems), which should be noted separately from platform bugs.

### Notes

- The AI Assistant (ChatPanel component) uses a hybrid retrieval pipeline combining vector search (ChromaDB) and graph search (Neo4j).
- The pipeline trace provides transparency into what data was retrieved and used to generate the answer.
- Chat histories are auto-saved and can be loaded later via the ChatHistoryList component.
- The `extract-nodes` endpoint uses LLM to identify entity references in AI responses.
- Timeout for chat queries is 10 minutes (600000ms) due to potential LLM latency.

---

## Playbook 10: Insights System

**Description:** Validate the AI-powered insights system including generation, review, acceptance, rejection, and retrieval of insights across case entities.

**Prerequisites:**
- Authenticated with valid token
- Operation Silver Bridge case loaded (case ID: `60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`)
- LLM service configured

### Steps

**Step 1: Get existing case insights**

- **Action:** Call `GET /api/graph/cases/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/insights`.
- **Expected:** Response contains an array of insights. Each insight should have: `text`, `confidence` (high/medium/low), `category` (inconsistency/connection/defense_opportunity/brady_giglio/pattern), `entity_key`, and optionally `reasoning`.
- **Pass:** Response is valid (array, possibly empty if no insights generated yet).
- **Fail:** Error response.

**Step 2: Generate new insights**

- **Action:** Call `POST /api/graph/cases/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/generate-insights?max_entities=5`.
- **Expected:** Response confirms insight generation has started or completed. Should include generated insights for up to 5 entities.
- **Pass:** Response indicates insights were generated (count > 0) or the process started.
- **Fail:** Error response. Note: This uses the LLM API and may fail due to external API issues.

**Step 3: Verify insights were generated**

- **Action:** Call `GET /api/graph/cases/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/insights`.
- **Expected:** Response now contains insights (more than before Step 2, if Step 2 generated new ones).
- **Pass:** At least 1 insight exists with valid `text`, `confidence`, and `category`.
- **Fail:** No insights found after generation.

**Step 4: Verify insight categories**

- **Action:** Inspect the insights from Step 3. Check that each insight has a valid category.
- **Expected:** Categories should be one of: `inconsistency`, `connection`, `defense_opportunity`, `brady_giglio`, `pattern`.
- **Pass:** All insights have a valid category from the expected set.
- **Fail:** Unknown or missing categories.

**Step 5: Verify confidence levels**

- **Action:** Inspect insights for confidence levels.
- **Expected:** Confidence values should be one of: `high`, `medium`, `low`.
- **Pass:** All insights have a valid confidence level.
- **Fail:** Unknown or missing confidence levels.

**Step 6: Accept a high-confidence insight**

- **Action:** Find an insight with `confidence: "high"`. Get its `entity_key` and `insight_index`. The insight index is its position (0-based) in the entity's `ai_insights` array. First, get the entity's details to find the insight index, then call `POST /api/graph/node/{entity_key}/verify-insight?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "insight_index": 0,
    "username": "neil.byrne@gmail.com"
  }
  ```
- **Expected:** Insight is converted to a verified fact on the entity.
- **Pass:** HTTP 200 with confirmation. The entity's `verified_facts` array now includes the insight text.
- **Fail:** Error response or insight not converted.

**Step 7: Reject a low-confidence insight**

- **Action:** Find an insight with `confidence: "low"`. Call `DELETE /api/graph/node/{entity_key}/insights/{insight_index}?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Insight is removed from the entity.
- **Pass:** HTTP 200/204.
- **Fail:** Error response.

**Step 8: Verify rejection**

- **Action:** Re-fetch the entity's details. Verify the rejected insight no longer appears in `ai_insights`.
- **Expected:** The insight at the rejected index is gone.
- **Pass:** Insight removed from entity's `ai_insights` array.
- **Fail:** Insight still present.

**Step 9: Verify accepted insight in verified facts**

- **Action:** Re-fetch the entity details from Step 6. Check the `verified_facts` array.
- **Expected:** The accepted insight now appears as a verified fact with the verifying username.
- **Pass:** Verified fact found with matching text content.
- **Fail:** Verified fact not found.

### Pass Criteria

Steps 1, 3-5, 7-9 must pass. Step 2 (generation) and Step 6 (acceptance) may fail due to LLM API issues — record these separately. At minimum, the insight retrieval, validation, and rejection APIs must work correctly.

### Notes

- The Insights Panel (InsightsPanel component) is accessible from the left toolbar in the frontend.
- Insight categories map to investigation-specific analysis types:
  - `inconsistency`: Conflicting information across entities
  - `connection`: Hidden or indirect connections between entities
  - `defense_opportunity`: Potential defense arguments
  - `brady_giglio`: Exculpatory evidence (legal requirement to disclose)
  - `pattern`: Behavioral or transactional patterns
- The "Accept" action converts an AI insight into a verified fact, which carries investigator attribution.
- Bulk accept/reject is handled in the frontend by iterating over insights.

---

## Playbook 11: Workspace & Collaboration Features

**Description:** Validate the Workspace features including case context, investigative notes, tasks, witnesses, theories, pinned items, and investigation timeline.

**Prerequisites:**
- Authenticated with valid token
- Operation Silver Bridge case loaded (case ID: `60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`)

### Steps

**Step 1: Get case context**

- **Action:** Call `GET /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/context`.
- **Expected:** Response contains case context information such as overview, key facts, or investigative focus areas.
- **Pass:** Valid response (may be empty if no context has been set).
- **Fail:** Error response.

**Step 2: Get entity summary for workspace dashboard**

- **Action:** Call `GET /api/graph/cases/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/entity-summary`.
- **Expected:** Response contains entity count breakdown by type (e.g., Person: X, Company: Y, Account: Z).
- **Pass:** At least 3 entity types with counts > 0.
- **Fail:** Empty or error.

**Step 3: Create an investigative note**

- **Action:** Call `POST /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/notes` with body:
  ```json
  {
    "title": "Test Investigative Note",
    "content": "This is a test note created during testing. Marco Delgado appears to be coordinating wire transfers through Solaris Property Group.",
    "category": "financial_analysis"
  }
  ```
- **Expected:** Note created with an `id`.
- **Pass:** HTTP 200/201 with valid `id`.
- **Fail:** Error response.

**Step 4: List notes**

- **Action:** Call `GET /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/notes`.
- **Expected:** Response includes the note created in Step 3.
- **Pass:** At least 1 note returned.
- **Fail:** Empty list.

**Step 5: Update the note**

- **Action:** Call `PUT /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/notes/{note_id}` with body:
  ```json
  {
    "title": "Test Investigative Note — Updated",
    "content": "Updated content: Additional evidence suggests Elena Cruz is also involved in the wire transfer scheme."
  }
  ```
- **Expected:** Note updated.
- **Pass:** HTTP 200.
- **Fail:** Error response.

**Step 6: Create a task**

- **Action:** Call `POST /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/tasks` with body:
  ```json
  {
    "title": "Review Solaris Property Group financial records",
    "description": "Cross-reference the wire transfers from Q3 2024 with the account statements",
    "status": "pending",
    "priority": "high",
    "due_date": "2026-03-15"
  }
  ```
- **Expected:** Task created with an `id`.
- **Pass:** HTTP 200/201 with valid `id`.
- **Fail:** Error response.

**Step 7: List tasks**

- **Action:** Call `GET /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/tasks`.
- **Expected:** Response includes the task from Step 6.
- **Pass:** At least 1 task returned.
- **Fail:** Empty list.

**Step 8: Mark task as complete**

- **Action:** Call `PUT /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/tasks/{task_id}` with body:
  ```json
  {
    "status": "completed"
  }
  ```
- **Expected:** Task status updated to completed.
- **Pass:** HTTP 200.
- **Fail:** Error response.

**Step 9: Create a witness record**

- **Action:** Call `POST /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/witnesses` with body:
  ```json
  {
    "name": "Test Witness — Sarah Kim",
    "role": "Informant",
    "contact_info": "Through legal counsel only",
    "notes": "Former employee at Solaris Property Group. Willing to provide testimony under immunity.",
    "reliability": "high"
  }
  ```
- **Expected:** Witness record created with an `id`.
- **Pass:** HTTP 200/201 with valid `id`.
- **Fail:** Error response.

**Step 10: List witnesses**

- **Action:** Call `GET /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/witnesses`.
- **Expected:** Response includes the witness from Step 9.
- **Pass:** At least 1 witness returned.
- **Fail:** Empty list.

**Step 11: Create a case theory**

- **Action:** Call `POST /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/theories` with body:
  ```json
  {
    "title": "Layered Money Laundering via Real Estate",
    "description": "Theory: Marco Delgado uses Solaris Property Group as a front to layer illicit funds through real estate transactions, with Cruz & Partners providing legal cover for the purchases.",
    "status": "active",
    "confidence": "medium"
  }
  ```
- **Expected:** Theory created with an `id`.
- **Pass:** HTTP 200/201 with valid `id`.
- **Fail:** Error response.

**Step 12: List theories**

- **Action:** Call `GET /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/theories`.
- **Expected:** Response includes the theory from Step 11.
- **Pass:** At least 1 theory returned.
- **Fail:** Empty list.

**Step 13: Build theory graph**

- **Action:** Call `POST /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/theories/{theory_id}/build-graph` with body:
  ```json
  {
    "include_related_entities": true
  }
  ```
- **Expected:** Response contains a graph structure (nodes and links) representing the theory.
- **Pass:** Response contains graph data (may be empty if no entities linked yet).
- **Fail:** Error response.

**Step 14: Pin an evidence item**

- **Action:** Call `POST /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/pinned?item_type=entity&item_id={some_entity_key}`.
- **Expected:** Item pinned successfully.
- **Pass:** HTTP 200/201 with pin `id`.
- **Fail:** Error response.

**Step 15: Get pinned items**

- **Action:** Call `GET /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/pinned`.
- **Expected:** Response includes the pinned item from Step 14.
- **Pass:** At least 1 pinned item.
- **Fail:** Empty list.

**Step 16: Unpin the item**

- **Action:** Call `DELETE /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/pinned/{pin_id}`.
- **Expected:** Item unpinned.
- **Pass:** HTTP 200/204.
- **Fail:** Error response.

**Step 17: Get investigation timeline**

- **Action:** Call `GET /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/investigation-timeline`.
- **Expected:** Response contains a timeline of investigation activities (note creation, task updates, etc.).
- **Pass:** Valid response (may be empty or contain entries from this test session).
- **Fail:** Error response.

**Step 18: Clean up test data**

- **Action:** Delete the test note, task, witness, and theory:
  - `DELETE /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/notes/{note_id}`
  - `DELETE /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/tasks/{task_id}`
  - `DELETE /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/witnesses/{witness_id}`
  - `DELETE /api/workspace/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/theories/{theory_id}`
- **Expected:** All test items deleted.
- **Pass:** All deletions return HTTP 200/204.
- **Fail:** Any deletion fails.

### Pass Criteria

All 18 steps pass. All workspace CRUD operations (notes, tasks, witnesses, theories, pinned items) work correctly. Investigation timeline returns valid data.

### Notes

- The Workspace View (WorkspaceView + CaseOverviewView components) is a comprehensive case management dashboard.
- The workspace includes sections: EntitySummarySection, InvestigativeNotesSection, TasksSection, WitnessMatrixSection, TheoriesSection, PinnedEvidenceSection, InvestigationTimelineSection.
- Theory graphs are built using AI to identify relevant entities from the theory description.
- The investigation timeline tracks all investigative activities for audit purposes.
- Deadlines can also be managed via the workspace (CaseDeadlinesSection component).

---

## Playbook 12: Evidence & File Management

**Description:** Validate the evidence processing view, file listing, document preview, file summaries, and filtering capabilities.

**Prerequisites:**
- Authenticated with valid token
- Operation Silver Bridge case loaded (case ID: `60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`)
- 10 evidence files have been uploaded and processed

### Steps

**Step 1: List all evidence files for the case**

- **Action:** Call `GET /api/evidence?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response contains an array of evidence files. Each file should have: `id`, `filename`, `status` (processed/unprocessed), `file_type`, `file_size`, `case_id`, and timestamps.
- **Pass:** Array contains 10 files, all with `status` indicating "processed" (or equivalent).
- **Fail:** Fewer than 10 files, or files with unexpected statuses.

**Step 2: Filter evidence by status — processed**

- **Action:** Call `GET /api/evidence?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb&status=processed`.
- **Expected:** Only processed files returned.
- **Pass:** All 10 files returned (all should be processed).
- **Fail:** Fewer than 10 files.

**Step 3: Filter evidence by status — unprocessed**

- **Action:** Call `GET /api/evidence?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb&status=unprocessed`.
- **Expected:** No unprocessed files returned (all have been processed).
- **Pass:** Empty array.
- **Fail:** Unprocessed files found (unexpected).

**Step 4: Get summary for a specific document**

- **Action:** Pick a filename from Step 1. Call `GET /api/evidence/summary/{filename}?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response contains an AI-generated summary of the document content.
- **Pass:** Non-empty summary text returned.
- **Fail:** Empty summary or error. Note: Summary may not exist if backfill hasn't been run.

**Step 5: List files in case directory**

- **Action:** Call `GET /api/filesystem/list?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response contains `items` array listing files and subdirectories in the case's file storage.
- **Pass:** `items` array has length >= 1.
- **Fail:** Empty items or error.

**Step 6: Read a text file**

- **Action:** From Step 5, find a text file (`.txt` extension). Call `GET /api/filesystem/read?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb&path={file_path}`.
- **Expected:** Response contains `content` field with the text file's contents.
- **Pass:** Non-empty content returned.
- **Fail:** Error or empty content. If no .txt files exist, skip and note "N/A".

**Step 7: Get file URL for document preview**

- **Action:** Pick an evidence file ID from Step 1. Construct the URL: `/api/evidence/{evidence_id}/file`.
- **Expected:** This URL should serve the actual file content when requested with authentication.
- **Pass:** URL can be constructed. (Full download test may require browser context with auth headers.)
- **Fail:** Evidence ID not available.

**Step 8: Check evidence ingestion logs**

- **Action:** Call `GET /api/evidence/logs?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb&limit=50`.
- **Expected:** Response contains recent ingestion log entries showing processing status for the 10 files.
- **Pass:** At least 1 log entry returned.
- **Fail:** Empty logs.

**Step 9: Find evidence by filename**

- **Action:** Pick a known filename from Step 1. Call `GET /api/evidence/by-filename/{filename}?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Response contains the evidence record matching the filename.
- **Pass:** Evidence record found with matching filename.
- **Fail:** Not found.

**Step 10: Verify file type distribution**

- **Action:** From Step 1, count files by type (csv, pdf, txt, xlsx).
- **Expected:** At least 2 different file types present among the 10 files.
- **Pass:** Multiple file types present.
- **Fail:** All files are the same type.

### Pass Criteria

Steps 1-3, 5, 7-10 must pass. Steps 4 and 6 may be "N/A" depending on data availability.

### Notes

- The Evidence Processing View (EvidenceProcessingView component) shows uploaded files with processing status.
- The File Navigator (FileNavigator component) provides a file tree view for browsing case files.
- The Document Viewer (DocumentViewer component) supports previewing PDF, text, and CSV files.
- File preview (FilePreview component) handles different file type rendering.
- Evidence upload supports both individual files and folders (with webkitdirectory for folder structure preservation).

---

## Playbook 13: Case Backup, Restore & Snapshots

**Description:** Validate the snapshot system for saving and restoring graph states, and the case backup/restore functionality.

**Prerequisites:**
- Authenticated with valid token
- Operation Silver Bridge case loaded (case ID: `60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`)

### Steps

**Step 1: List existing snapshots**

- **Action:** Call `GET /api/snapshots`.
- **Expected:** Response contains an array of snapshots (may be empty if none created yet).
- **Pass:** Valid response (array).
- **Fail:** Error response.

**Step 2: Create a named snapshot**

- **Action:** First, get the current graph data: `GET /api/graph?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`. Then call `POST /api/snapshots` with body:
  ```json
  {
    "name": "Test Snapshot — Pre-Change Baseline",
    "notes": "Created during testing to verify snapshot/restore functionality",
    "subgraph": {
      "nodes": ["{nodes_from_graph}"],
      "links": ["{links_from_graph}"]
    },
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "case_name": "Operation Silver Bridge"
  }
  ```
  (The nodes and links arrays come from the graph data fetched above.)
- **Expected:** Snapshot created with an `id`, `name`, and `timestamp`.
- **Pass:** HTTP 200/201 with valid snapshot `id`.
- **Fail:** Error response (may fail if data is too large — the API supports chunked upload for large snapshots).

**Step 3: Verify snapshot appears in list**

- **Action:** Call `GET /api/snapshots`.
- **Expected:** The snapshot from Step 2 appears in the list with correct name and node/link counts.
- **Pass:** Snapshot found with name "Test Snapshot — Pre-Change Baseline".
- **Fail:** Snapshot not in list.

**Step 4: Get the snapshot details**

- **Action:** Call `GET /api/snapshots/{snapshot_id}`.
- **Expected:** Full snapshot data returned including `subgraph` with `nodes` and `links` arrays.
- **Pass:** Snapshot data contains nodes and links matching what was saved.
- **Fail:** Missing or incomplete data.

**Step 5: Make a change to the graph — add a test node**

- **Action:** Call `POST /api/graph/create-node` with:
  ```json
  {
    "name": "Snapshot Test Node — Should Be Removed After Restore",
    "type": "Document",
    "summary": "Test node for snapshot restore verification",
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb"
  }
  ```
- **Expected:** Node created. Record the key.
- **Pass:** HTTP 200 with valid key.
- **Fail:** Error.

**Step 6: Verify the change exists**

- **Action:** Search for the test node.
- **Expected:** Node found.
- **Pass:** Search returns the test node.
- **Fail:** Node not found.

**Step 7: Restore the snapshot**

- **Action:** Call `POST /api/snapshots/restore` with the snapshot data from Step 4 (the full snapshot object).
- **Expected:** Graph is restored to the snapshot state. The test node from Step 5 should be gone after restore (if the restore performs a full graph replacement for the case).
- **Pass:** HTTP 200 with restore confirmation.
- **Fail:** Error response.

**Step 8: Verify restoration**

- **Action:** Search for the test node ("Snapshot Test Node — Should Be Removed After Restore").
- **Expected:** If the snapshot restore performs a full graph replacement, the test node should be gone. If it is an additive restore (overlay), the test node may still exist.
- **Pass:** Snapshot restore completed successfully. Note whether the test node was removed (full restore) or persists (additive restore).
- **Fail:** Restore did not complete.

**Step 9: Clean up — delete test node if it persists**

- **Action:** If the test node from Step 5 still exists, delete it: `DELETE /api/graph/node/{test_key}?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Node deleted (or already gone from restore).
- **Pass:** Clean state restored.
- **Fail:** Unable to delete.

**Step 10: Delete the test snapshot**

- **Action:** Call `DELETE /api/snapshots/{snapshot_id}`.
- **Expected:** Snapshot deleted.
- **Pass:** HTTP 200/204.
- **Fail:** Error response.

**Step 11: Verify snapshot deletion**

- **Action:** Call `GET /api/snapshots`.
- **Expected:** The test snapshot no longer appears in the list.
- **Pass:** Snapshot not in list.
- **Fail:** Snapshot still present.

### Pass Criteria

Steps 1-6, 10-11 must pass. Steps 7-9 should pass but the behavior of restore (full vs. additive) should be documented.

### Notes

- The Snapshot system (SnapshotList, SnapshotModal, SaveSnapshotProgressDialog, LoadSnapshotProgressDialog components) provides versioned graph states.
- Large snapshots are handled via chunked upload (the frontend's snapshotsAPI.create handles this automatically).
- The snapshot stores: graph nodes/links, timeline data, chat history, AI overview, and case metadata.
- Case backup (casesAPI.backup) provides a full case export as a ZIP file including files.
- Case restore (casesAPI.restore) imports from a backup ZIP file.

---

## Playbook 14: User Management & Authentication

**Description:** Validate authentication flows, user profile information, role-based access, and case collaboration membership.

**Prerequisites:**
- Backend and frontend servers running
- User `neil.byrne@gmail.com` exists with password `OwlAdmin123!`

### Steps

**Step 1: Login with valid credentials**

- **Action:** Call `POST /api/auth/login` with body:
  ```json
  {
    "username": "neil.byrne@gmail.com",
    "password": "OwlAdmin123!"
  }
  ```
- **Expected:** Response contains `access_token` (JWT), `token_type: "bearer"`, and user information including `name`, `email`, `role`.
- **Pass:** HTTP 200 with valid `access_token`.
- **Fail:** Authentication error.

**Step 2: Verify current user (me endpoint)**

- **Action:** Call `GET /api/auth/me` with the JWT token from Step 1 in the Authorization header.
- **Expected:** Response contains user profile: `email: "neil.byrne@gmail.com"`, `name` (containing "Neil" or "Byrne"), and `role` (should be "super_admin" or "admin").
- **Pass:** Email matches and role is admin-level.
- **Fail:** Wrong user info or error.

**Step 3: Login with invalid password**

- **Action:** Call `POST /api/auth/login` with body:
  ```json
  {
    "username": "neil.byrne@gmail.com",
    "password": "WrongPassword123!"
  }
  ```
- **Expected:** HTTP 401 Unauthorized with error message.
- **Pass:** HTTP 401 returned.
- **Fail:** Login succeeds with wrong password (security issue).

**Step 4: Login with non-existent user**

- **Action:** Call `POST /api/auth/login` with body:
  ```json
  {
    "username": "nonexistent@example.com",
    "password": "AnyPassword123!"
  }
  ```
- **Expected:** HTTP 401 Unauthorized.
- **Pass:** HTTP 401 returned.
- **Fail:** Any other response.

**Step 5: Access protected endpoint without token**

- **Action:** Call `GET /api/auth/me` WITHOUT the Authorization header.
- **Expected:** HTTP 401 or 403 Unauthorized/Forbidden.
- **Pass:** Request is rejected.
- **Fail:** Request succeeds without authentication.

**Step 6: List all users (admin function)**

- **Action:** Call `GET /api/users` with valid token.
- **Expected:** Response contains array of users. At least 1 user (the current user).
- **Pass:** User list returned with at least 1 user.
- **Fail:** Error or empty list.

**Step 7: Get case members for Operation Silver Bridge**

- **Action:** Call `GET /api/cases/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/members`.
- **Expected:** Response contains array of case members. Current user should be listed as "owner" (or equivalent role).
- **Pass:** At least 1 member listed. Current user has owner/admin permissions.
- **Fail:** No members or current user not listed.

**Step 8: Get current user's membership for the case**

- **Action:** Call `GET /api/cases/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/members/me`.
- **Expected:** Response shows current user's role and permissions for this case.
- **Pass:** Response includes permission flags (e.g., `can_edit`, `can_delete`, `can_invite`).
- **Fail:** Error or missing permissions.

**Step 9: Logout**

- **Action:** Call `POST /api/auth/logout`.
- **Expected:** Logout successful.
- **Pass:** HTTP 200.
- **Fail:** Error response.

**Step 10: Verify token is invalidated after logout**

- **Action:** Call `GET /api/auth/me` with the token from Step 1 (after logout).
- **Expected:** HTTP 401 (token should be invalidated). Note: Some JWT implementations may not invalidate tokens server-side; the token may still work until expiry.
- **Pass:** HTTP 401 (preferred) or HTTP 200 (acceptable if JWT is stateless).
- **Fail:** Error other than 401.

**Step 11: Re-login to restore session**

- **Action:** Call `POST /api/auth/login` with valid credentials again.
- **Expected:** New token issued.
- **Pass:** HTTP 200 with new access_token.
- **Fail:** Cannot re-login.

### Pass Criteria

Steps 1-9, 11 must pass. Step 10 is informational (documents token invalidation behavior).

### Notes

- The LoginPanel component handles the frontend authentication flow.
- The CollaboratorModal component manages case members and invitations.
- Permission presets are: `owner`, `editor`, `viewer`.
- The platform uses JWT tokens with Bearer authentication.
- Super admin users can see all cases; regular users see only cases they are members of.
- The CreateUserModal component allows admin users to create new user accounts.

---

## Playbook 15: Cost Tracking & System Monitoring

**Description:** Validate the cost ledger for tracking LLM usage costs and the system logging infrastructure.

**Prerequisites:**
- Authenticated with valid token
- At least one ingestion or AI query has been performed (costs should be recorded)

### Steps

**Step 1: Get cost ledger records**

- **Action:** Call `GET /api/cost-ledger`.
- **Expected:** Response contains an array of cost records. Each record should include: `timestamp`, `amount` (or `cost`), `activity_type` (e.g., "ingestion", "chat", "insights"), `model` used, and optionally `case_id`.
- **Pass:** At least 1 cost record returned (from previous ingestion/AI operations).
- **Fail:** Empty array (may indicate cost tracking is not enabled — record as informational).

**Step 2: Get cost summary**

- **Action:** Call `GET /api/cost-ledger/summary`.
- **Expected:** Response contains aggregated cost data: total cost, breakdown by activity type, and possibly by model.
- **Pass:** Summary contains total cost value >= 0.
- **Fail:** Error response.

**Step 3: Filter costs by case**

- **Action:** Call `GET /api/cost-ledger?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** Only cost records associated with the Silver Bridge case are returned.
- **Pass:** All returned records have the correct `case_id` (or empty array if costs are not tagged by case).
- **Fail:** Records from other cases present.

**Step 4: Filter costs by activity type**

- **Action:** Call `GET /api/cost-ledger?activity_type=ingestion`.
- **Expected:** Only ingestion-related cost records returned.
- **Pass:** All returned records have `activity_type` === "ingestion" (or empty if none).
- **Fail:** Other activity types present.

**Step 5: Get system logs**

- **Action:** Call `GET /api/system-logs?limit=50`.
- **Expected:** Response contains system log entries. Each entry should have: `timestamp`, `log_type`, `origin`, `message`, and optionally `user`, `success`.
- **Pass:** At least 1 log entry returned.
- **Fail:** Empty logs (may indicate logging is not active).

**Step 6: Get system log statistics**

- **Action:** Call `GET /api/system-logs/statistics`.
- **Expected:** Response contains log statistics: counts by type, counts by origin, total count.
- **Pass:** Valid statistics returned with total count >= 0.
- **Fail:** Error response.

**Step 7: Filter system logs by type**

- **Action:** Call `GET /api/system-logs?log_type=INFO&limit=20`.
- **Expected:** Only INFO-type logs returned.
- **Pass:** All returned logs have the filtered type.
- **Fail:** Logs of other types present.

**Step 8: Filter system logs by user**

- **Action:** Call `GET /api/system-logs?user=neil.byrne@gmail.com&limit=20`.
- **Expected:** Only logs attributed to the specified user returned.
- **Pass:** All returned logs are for the correct user.
- **Fail:** Logs from other users present.

**Step 9: List background tasks**

- **Action:** Call `GET /api/background-tasks?limit=20`.
- **Expected:** Response contains array of background tasks. Each task should have: `id`, `status` (pending/running/completed/failed), `type`, and `created_at`.
- **Pass:** Valid response (may be empty if no background tasks have been run).
- **Fail:** Error response.

**Step 10: Filter background tasks by case**

- **Action:** Call `GET /api/background-tasks?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb&limit=20`.
- **Expected:** Only tasks for the Silver Bridge case returned.
- **Pass:** All returned tasks have the correct `case_id`.
- **Fail:** Tasks from other cases present.

### Pass Criteria

Steps 1, 2, 5, 6, 9 must return valid responses (even if empty). Steps 3, 4, 7, 8, 10 test filtering and should pass if data exists.

### Notes

- The CostLedgerPanel component displays cost data in the frontend.
- The SystemLogsPanel component shows system activity logs.
- The BackgroundTasksPanel component tracks long-running operations (file processing, backfill operations).
- Cost tracking records LLM token usage and associated costs for each API call to OpenAI.
- System logs capture: authentication events, file processing, AI queries, graph modifications, and errors.

---

## Playbook 16: LLM Configuration & Extraction Profiles

**Description:** Validate viewing and switching LLM configurations, and managing extraction profiles for entity extraction.

**Prerequisites:**
- Authenticated with valid token
- LLM service configured (OpenAI API key set)

### Steps

**Step 1: Get current LLM configuration**

- **Action:** Call `GET /api/llm-config/current`.
- **Expected:** Response shows active model configuration: `provider` (e.g., "openai"), `model_id` (e.g., "gpt-4o"), and possibly additional settings.
- **Pass:** Valid provider and model_id returned.
- **Fail:** No configuration or error.

**Step 2: List available LLM models**

- **Action:** Call `GET /api/llm-config/models`.
- **Expected:** Response contains array of available models from all providers. Each model should have `id`, `name`, and `provider`.
- **Pass:** At least 1 model listed.
- **Fail:** Empty list or error.

**Step 3: List available models filtered by provider**

- **Action:** Call `GET /api/llm-config/models?provider=openai`.
- **Expected:** Only OpenAI models returned.
- **Pass:** All returned models have `provider: "openai"`.
- **Fail:** Models from other providers present.

**Step 4: Get confidence threshold**

- **Action:** Call `GET /api/llm-config/confidence-threshold`.
- **Expected:** Response contains current confidence threshold value (between 0.0 and 1.0).
- **Pass:** Valid threshold value returned.
- **Fail:** Error or invalid value.

**Step 5: Set confidence threshold**

- **Action:** Call `POST /api/llm-config/confidence-threshold` with body: `{"threshold": 0.5}`.
- **Expected:** Threshold updated to 0.5.
- **Pass:** HTTP 200 with confirmation.
- **Fail:** Error response.

**Step 6: Verify threshold change**

- **Action:** Call `GET /api/llm-config/confidence-threshold`.
- **Expected:** Threshold value is 0.5.
- **Pass:** Value matches what was set.
- **Fail:** Different value.

**Step 7: Restore original threshold**

- **Action:** Call `POST /api/llm-config/confidence-threshold` with body: `{"threshold": 0.7}` (or the original value from Step 4).
- **Expected:** Threshold restored.
- **Pass:** HTTP 200.
- **Fail:** Error.

**Step 8: List extraction profiles**

- **Action:** Call `GET /api/profiles`.
- **Expected:** Response contains array of extraction profiles. Should include at least a "fraud" profile (used for the Silver Bridge case). Each profile should have `name` and configuration details.
- **Pass:** At least 1 profile returned (e.g., "fraud").
- **Fail:** Empty list.

**Step 9: Get specific profile details — "fraud"**

- **Action:** Call `GET /api/profiles/fraud`.
- **Expected:** Response contains the fraud profile configuration including entity types to extract, relationship types, extraction prompts, and model settings.
- **Pass:** Profile found with configuration details.
- **Fail:** Profile not found or error.

**Step 10: Create a test extraction profile**

- **Action:** Call `POST /api/profiles` with body:
  ```json
  {
    "name": "test_profile",
    "description": "Test profile for playbook testing",
    "entity_types": ["Person", "Company", "Location"],
    "relationship_types": ["WORKS_FOR", "LOCATED_IN"]
  }
  ```
- **Expected:** Profile created.
- **Pass:** HTTP 200/201 with confirmation.
- **Fail:** Error response.

**Step 11: Verify test profile exists**

- **Action:** Call `GET /api/profiles/test_profile`.
- **Expected:** Profile found with matching configuration.
- **Pass:** Profile details match what was submitted.
- **Fail:** Profile not found.

**Step 12: Delete the test profile**

- **Action:** Call `DELETE /api/profiles/test_profile`.
- **Expected:** Profile deleted.
- **Pass:** HTTP 200/204.
- **Fail:** Error response.

**Step 13: Verify test profile deleted**

- **Action:** Call `GET /api/profiles/test_profile`.
- **Expected:** HTTP 404 Not Found.
- **Pass:** HTTP 404.
- **Fail:** Profile still exists.

### Pass Criteria

All 13 steps pass. LLM configuration can be viewed and modified. Extraction profiles can be listed, inspected, created, and deleted.

### Notes

- The ProfileEditor component in the frontend allows creating and editing extraction profiles.
- The fraud profile is the primary profile used for Operation Silver Bridge.
- A "generic" profile may also be available for non-specialized extraction.
- LLM configuration changes affect all subsequent AI operations (chat, insights, extraction).
- The confidence threshold controls the minimum similarity score for vector search results.

---

## Playbook 17: Database Management & Backfill

**Description:** Validate the database management endpoints for vector database status, document indices, entity indices, and backfill operations.

**Prerequisites:**
- Authenticated with valid token
- Operation Silver Bridge case has processed documents in the vector database

### Steps

**Step 1: Get backfill status**

- **Action:** Call `GET /api/backfill/status`.
- **Expected:** Response contains counts of items needing backfill: documents without embeddings, entities without embeddings, documents without summaries, etc.
- **Pass:** Valid status response with counts >= 0.
- **Fail:** Error response.

**Step 2: List documents in vector database**

- **Action:** Call `GET /api/database/documents`.
- **Expected:** Response contains array of documents stored in ChromaDB with their IDs and metadata.
- **Pass:** At least 1 document listed (from the 10 processed evidence files).
- **Fail:** Empty list or error.

**Step 3: List documents with backfill status**

- **Action:** Call `GET /api/database/documents/status`.
- **Expected:** Response shows each document with its embedding and summary backfill status.
- **Pass:** Status information returned for at least 1 document.
- **Fail:** Error response.

**Step 4: Get a specific document from vector database**

- **Action:** Pick a document ID from Step 2. Call `GET /api/database/documents/{doc_id}`.
- **Expected:** Response contains the document's content, metadata, and embedding status.
- **Pass:** Document data returned.
- **Fail:** Document not found or error.

**Step 5: List entities in vector database**

- **Action:** Call `GET /api/database/entities`.
- **Expected:** Response contains array of entity embeddings stored in ChromaDB.
- **Pass:** At least 1 entity listed.
- **Fail:** Empty list or error.

**Step 6: List entities with embedding status**

- **Action:** Call `GET /api/database/entities/status`.
- **Expected:** Response shows each entity with its embedding status.
- **Pass:** Status information returned.
- **Fail:** Error response.

**Step 7: Run backfill dry run — document summaries**

- **Action:** Call `POST /api/backfill/document-summaries` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "skip_existing": true,
    "dry_run": true
  }
  ```
- **Expected:** Response reports what would be done without actually making changes. Should indicate how many documents need summaries.
- **Pass:** Valid dry run report with counts.
- **Fail:** Error response.

**Step 8: Run backfill dry run — case IDs**

- **Action:** Call `POST /api/backfill/case-ids` with body:
  ```json
  {
    "include_entities": true,
    "include_vector_db": true,
    "dry_run": true
  }
  ```
- **Expected:** Response reports what case_id backfilling would be done.
- **Pass:** Valid dry run report.
- **Fail:** Error response.

**Step 9: Run backfill dry run — chunk embeddings**

- **Action:** Call `POST /api/backfill/chunks` with body:
  ```json
  {
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb",
    "skip_existing": true,
    "dry_run": true
  }
  ```
- **Expected:** Response reports chunk embedding backfill status.
- **Pass:** Valid dry run report.
- **Fail:** Error response.

**Step 10: Run backfill dry run — entity metadata**

- **Action:** Call `POST /api/backfill/entity-metadata` with body:
  ```json
  {
    "dry_run": true
  }
  ```
- **Expected:** Response reports entity metadata (case_id) backfill status in ChromaDB.
- **Pass:** Valid dry run report.
- **Fail:** Error response.

### Pass Criteria

All 10 steps pass. Database status endpoints return valid data. Dry run backfills report expected results without making changes.

### Notes

- The DatabaseModal component in the frontend provides the UI for database management.
- Backfill operations can be long-running (up to 10 minutes timeout).
- Dry runs are safe — they only report what would be done.
- Actual backfills (non-dry-run) should only be run intentionally, as they may incur LLM costs (for summary generation) and processing time.
- The vector database (ChromaDB) stores document embeddings, chunk embeddings, and entity embeddings used for semantic search.

---

## Playbook 18: Edge Cases & Error Handling

**Description:** Validate error handling, empty state handling, input validation, and boundary conditions across the platform.

**Prerequisites:**
- Authenticated with valid token

### Steps

**Step 1: Create an empty case**

- **Action:** Call `POST /api/cases` with body:
  ```json
  {
    "title": "Empty Test Case",
    "description": "Case created for edge case testing — no entities"
  }
  ```
- **Expected:** Case created with a valid `id`.
- **Pass:** HTTP 200/201 with case `id`.
- **Fail:** Error response.

**Step 2: Load graph for empty case**

- **Action:** Call `GET /api/graph?case_id={empty_case_id}`.
- **Expected:** Response contains empty `nodes` and `links` arrays (not an error).
- **Pass:** Response has `nodes: []` and `links: []`.
- **Fail:** Error response instead of empty data.

**Step 3: Get entity types for empty case**

- **Action:** Call `GET /api/graph/entity-types?case_id={empty_case_id}`.
- **Expected:** Empty array of entity types.
- **Pass:** Empty array returned.
- **Fail:** Error response.

**Step 4: Search in empty case**

- **Action:** Call `GET /api/graph/search?q=anything&limit=10&case_id={empty_case_id}`.
- **Expected:** Empty results array.
- **Pass:** Empty results.
- **Fail:** Error response.

**Step 5: Get graph summary for empty case**

- **Action:** Call `GET /api/graph/summary?case_id={empty_case_id}`.
- **Expected:** Summary with `node_count: 0` and `link_count: 0` (or equivalent zero values).
- **Pass:** Zero counts returned.
- **Fail:** Error response.

**Step 6: Get timeline for empty case**

- **Action:** Call `GET /api/timeline?case_id={empty_case_id}`.
- **Expected:** Empty events array.
- **Pass:** `events: []`.
- **Fail:** Error response.

**Step 7: Get financial transactions for empty case**

- **Action:** Call `GET /api/financial?case_id={empty_case_id}`.
- **Expected:** Empty transactions array.
- **Pass:** `transactions: []`.
- **Fail:** Error response.

**Step 8: Get locations for empty case**

- **Action:** Call `GET /api/graph/locations?case_id={empty_case_id}`.
- **Expected:** Empty locations array.
- **Pass:** Empty array.
- **Fail:** Error response.

**Step 9: Try to create a node with empty name**

- **Action:** Call `POST /api/graph/create-node` with body:
  ```json
  {
    "name": "",
    "type": "Person",
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb"
  }
  ```
- **Expected:** HTTP 400 or 422 validation error. The API should reject nodes with empty names.
- **Pass:** Error response indicating name is required.
- **Fail:** Node created with empty name (validation missing).

**Step 10: Try to create a node without a type**

- **Action:** Call `POST /api/graph/create-node` with body:
  ```json
  {
    "name": "No Type Node",
    "type": "",
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb"
  }
  ```
- **Expected:** HTTP 400 or 422, or the API assigns a default type.
- **Pass:** Either error response OR node created with a default type.
- **Fail:** Node created with empty/null type and no default.

**Step 11: Try to create a relationship with invalid keys**

- **Action:** Call `POST /api/graph/relationships` with body:
  ```json
  {
    "relationships": [
      {
        "source_key": "nonexistent_key_12345",
        "target_key": "also_nonexistent_67890",
        "type": "KNOWS"
      }
    ],
    "case_id": "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb"
  }
  ```
- **Expected:** Error response or graceful handling (relationship not created since source/target do not exist).
- **Pass:** Error response or empty/zero result (no relationship created).
- **Fail:** Relationship created despite invalid keys.

**Step 12: Try to get details for non-existent node**

- **Action:** Call `GET /api/graph/node/nonexistent_key_12345?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** HTTP 404 Not Found.
- **Pass:** HTTP 404.
- **Fail:** HTTP 200 with empty/null data.

**Step 13: Try to delete a non-existent node**

- **Action:** Call `DELETE /api/graph/node/nonexistent_key_12345?case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** HTTP 404 or graceful handling (nothing to delete).
- **Pass:** HTTP 404 or HTTP 200/204 with indication nothing was deleted.
- **Fail:** HTTP 500 internal error.

**Step 14: Access case without membership**

- **Action:** If possible, try to access the empty test case's data using a different user's token (or skip if only one user exists). Alternatively, test accessing a non-existent case: `GET /api/graph?case_id=00000000-0000-0000-0000-000000000000`.
- **Expected:** Error response (404 for non-existent case, or 403 for unauthorized access).
- **Pass:** Appropriate error response.
- **Fail:** Data returned for non-existent case.

**Step 15: Test invalid case ID format**

- **Action:** Call `GET /api/graph?case_id=not-a-valid-uuid`.
- **Expected:** HTTP 400 or 422 validation error (invalid UUID format), or empty results if the API accepts string IDs.
- **Pass:** Error response or empty results (no crash).
- **Fail:** HTTP 500 internal server error.

**Step 16: Test very long search query**

- **Action:** Call `GET /api/graph/search?q={1000_character_string}&limit=10&case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb` with a 1000-character search string.
- **Expected:** Empty results or graceful truncation. No server crash.
- **Pass:** Valid response (empty results expected).
- **Fail:** HTTP 500 or server timeout.

**Step 17: Test negative limit parameter**

- **Action:** Call `GET /api/graph/search?q=test&limit=-1&case_id=60b9367c-ec0a-4619-b3ba-eb18ddb91bfb`.
- **Expected:** HTTP 400/422 validation error or the API treats it as 0/default.
- **Pass:** No server crash. Either error or empty results.
- **Fail:** HTTP 500.

**Step 18: Clean up — delete empty test case**

- **Action:** Call `DELETE /api/cases/{empty_case_id}`.
- **Expected:** Case deleted.
- **Pass:** HTTP 200/204.
- **Fail:** Error (may indicate the case has dependent data that prevents deletion).

### Pass Criteria

Steps 1-8 must pass (empty state handling). Steps 9-17 should not cause HTTP 500 errors — they should return appropriate 4xx status codes or handle the edge case gracefully. Step 18 must pass (cleanup).

### Notes

- Good empty state handling is critical for user experience when a case is newly created before any evidence is uploaded.
- Input validation should happen at both the API layer (Pydantic models in FastAPI) and the frontend (form validation).
- The API should never return HTTP 500 for client-side input errors — these should always be 4xx.
- Browser back/forward navigation and page refresh are frontend-specific tests that require manual browser testing or Playwright/Cypress testing.
- Permission denied scenarios require multiple user accounts with different role assignments.

---

## Test Execution Summary Template

When running these playbooks, use the following template to record results:

```
## Test Run: [Date]
### Environment
- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- User: neil.byrne@gmail.com
- Case: Operation Silver Bridge (60b9367c-ec0a-4619-b3ba-eb18ddb91bfb)

### Results

| Playbook | Steps Passed | Steps Failed | Steps N/A | Overall |
|----------|-------------|-------------|-----------|---------|
| PB-0     | N/A         | N/A         | N/A       | DONE    |
| PB-1     | X/10        | X/10        | X/10      | PASS/FAIL |
| PB-2     | X/12        | X/12        | X/12      | PASS/FAIL |
| PB-3     | X/12        | X/12        | X/12      | PASS/FAIL |
| PB-4     | X/8         | X/8         | X/8       | PASS/FAIL |
| PB-5     | X/11        | X/11        | X/11      | PASS/FAIL |
| PB-6     | X/6         | X/6         | X/6       | PASS/FAIL |
| PB-7     | X/9         | X/9         | X/9       | PASS/FAIL |
| PB-8     | X/15        | X/15        | X/15      | PASS/FAIL |
| PB-9     | X/10        | X/10        | X/10      | PASS/FAIL |
| PB-10    | X/9         | X/9         | X/9       | PASS/FAIL |
| PB-11    | X/18        | X/18        | X/18      | PASS/FAIL |
| PB-12    | X/10        | X/10        | X/10      | PASS/FAIL |
| PB-13    | X/11        | X/11        | X/11      | PASS/FAIL |
| PB-14    | X/11        | X/11        | X/11      | PASS/FAIL |
| PB-15    | X/10        | X/10        | X/10      | PASS/FAIL |
| PB-16    | X/13        | X/13        | X/13      | PASS/FAIL |
| PB-17    | X/10        | X/10        | X/10      | PASS/FAIL |
| PB-18    | X/18        | X/18        | X/18      | PASS/FAIL |

### Total: X/185 steps passed
```

---

*Document generated for OWL Investigation Platform testing. Last updated: 2026-02-20.*
