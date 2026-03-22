# Changelog

## What is the Evidence Engine?

The evidence engine is a ground-up replacement of our old document ingestion system. It's a separate FastAPI microservice (`evidence-engine/`) with its own async worker queue, replacing the old approach where ingestion ran as synchronous Python scripts inside the main backend process.

### Why we replaced the old system

The old ingestion pipeline (`ingestion/scripts/`) worked, but had real limitations that were starting to hurt:

- **Entity deduplication was shallow.** It matched entities by normalised name strings and Neo4j fuzzy search. If two documents referred to the same person differently ("John Smith" vs "J. Smith, Director"), the old system would often create two separate nodes. You'd end up manually merging duplicates after every upload.

- **No relationship deduplication at all.** Every chunk that mentioned a connection between two entities created a new relationship. Upload three documents about the same case and you'd get redundant, overlapping relationships cluttering the graph.

- **Cross-document matching was weak.** The old system only checked existing Neo4j nodes via Cypher queries when looking for duplicates. It couldn't do semantic similarity — it had no concept of "these two entities are probably the same even though the names don't exactly match."

- **It blocked the backend.** Ingestion ran in the same Python process as the API server using `ThreadPoolExecutor`. A large document upload could starve other API requests. There was no proper job queue, and progress tracking relied on 3-second polling from the frontend.

### How the evidence engine is better

**Three-phase entity resolution.** Instead of just string matching, the engine uses a blocking → embedding → LLM pipeline:
1. **Blocking** — fast candidate generation via token overlap, alias matching, and exact name matches. Prunes the search space before doing anything expensive.
2. **Embedding similarity** — generates vector embeddings for each entity and finds semantically similar pairs (cosine distance < 0.15) using ChromaDB. This catches "John Smith" vs "J. Smith" matches that string matching would miss.
3. **LLM confirmation** — candidate pairs from both phases are sent to GPT-4o-mini in batches of 20 for a final MERGE/KEEP_SEPARATE decision. Only confirmed matches are merged.

**Cross-document deduplication.** When a new file is processed, its entities are compared against the ChromaDB `entities` collection from all previously-processed files in that case. So the second, third, and tenth document you upload all benefit from what was already extracted — entities converge instead of multiplying.

**Relationship deduplication and type normalisation.** Duplicate relationships on the same entity pair are merged. When two relationships between the same entities have different type labels (e.g. "WORKS_FOR" and "EMPLOYED_BY"), an LLM decides whether to merge them into a canonical type.

**Structured ontology.** The old system let the LLM pick any entity type it wanted, which led to inconsistent categorisation. The evidence engine enforces 10 fixed categories (Person, Organization, Location, Event, Transaction, Communication, Account, Document, PhysicalEvidence, Other) with a freeform `specific_type` field for detail. This means the graph is consistently structured across all cases.

**Proper async architecture.** File processing runs on an arq worker backed by Redis, completely decoupled from the API server. The backend submits jobs via HTTP, and progress streams to the frontend via WebSocket over Redis pub/sub — no more polling.

**Entity summaries.** A dedicated pipeline stage generates a concise LLM summary for every entity, giving investigators a quick overview without needing to read all the source quotes.

### Pipeline stages at a glance

| Stage | What it does |
|-------|-------------|
| 1. Extract text | PDF/Word/Excel/HTML/audio → raw text + tables |
| 2. Chunk & embed | Split into ~6000-char chunks, embed with OpenAI, store in ChromaDB |
| 3. Extract entities & relationships | Two-pass LLM extraction (entities first, then relationships between them) |
| 4. Resolve entities | Three-phase dedup: blocking → embedding similarity → LLM confirmation |
| 5. Resolve relationships | Exact dedup + LLM-driven type normalisation |
| 6. Generate summaries | LLM summary per entity |
| 7. Write to Neo4j | Batched MERGE writes + embed final entities for future cross-job dedup |

---

## [Unreleased] — Evidence Engine Migration Branch

### Sender/Receiver Auto-Linking
- **Transaction parties now auto-link to graph entities during ingestion.** Previously, the evidence engine extracted `sender` and `receiver` as flat text strings on transaction nodes, but never connected them to the actual Person/Organization entities in the graph — even though those entities existed. A new `link_transaction_parties` pipeline step matches sender/receiver names against resolved entities and creates proper `SENT_PAYMENT`/`RECEIVED_PAYMENT` relationships. This means the financial table shows linked, clickable sender/receiver entities out of the box, instead of requiring manual assignment for every transaction.
- **String property fallback for sender/receiver.** If no graph relationship or manual override exists, the financial query now falls back to reading the raw `sender`/`receiver` text properties from the transaction node. This ensures something always shows in the UI, even for transactions where the sender entity wasn't extracted or matched.

### Financial Table UI — "Sender / Receiver" Terminology
- Renamed "From / To" labels to "Sender / Receiver" across both frontends (`frontend/` and `frontend_v2/`). Column headers, batch action buttons, and entity edit dialogs all use the new terminology. This aligns the UI with the evidence engine's extraction vocabulary and is clearer for investigators — "sender" and "receiver" are more precise than the generic "from" and "to".

### Root Directory Cleanup
- Archived ~40 loose documentation files, scripts, and PDFs from the project root into `archived_docs/`. The root was cluttered with old planning docs, test reports, timesheets, and one-off scripts that made it hard to see the actual project structure. The code and configs are unchanged — just the noise is removed.

---

## Evidence Engine Integration

### Monorepo Consolidation
- **Moved evidence-engine into the main repository.** Previously lived in a sibling directory with its own git history, meaning changes across the two services couldn't be reviewed or deployed together. Now it's `owl-n4j/evidence-engine/` — single git history, single PR workflow, single deployment. Docker-compose build paths updated accordingly.

### Evidence Engine Services in Docker Compose
- **Added Redis** as a shared job queue and progress pub/sub broker. Replaces the old polling pattern for tracking ingestion progress.
- **Added evidence-engine API** (port 8001) and **background worker** (arq) as docker-compose services. Both share the existing Neo4j instance.
- **Added ChromaDB as a dedicated service** (port 8100). Previously, ChromaDB was embedded directly in the evidence engine process, which meant it couldn't be shared across services and would lose data on restarts. Running it as a standalone Docker service gives it persistent storage, independent scaling, and makes it accessible to both the evidence engine (for entity embeddings and RAG) and potentially the main backend.
- **Added a second PostgreSQL instance** for evidence-engine job tracking, keeping ingestion metadata separate from the main application database.

### Backend Integration Layer
- **HTTP client** (`evidence_engine_client.py`) for upload, job status, and health checks against the evidence-engine microservice.
- **WebSocket proxy** (`evidence_ws.py`) at `/api/evidence/ws/jobs/{job_id}` that subscribes to Redis pub/sub and streams real-time job progress to the frontend. This replaces the old 3-second polling pattern — progress updates are now instant and don't waste network round-trips.
- **Health check integration** — the main backend's health endpoint now includes evidence-engine status.

### Graph Integration Fixes
- Fixed entity writing to include `key` property and `case_id` on relationships, so the main backend's graph service can actually find and display evidence-engine entities.
- Fixed activity feed duplication caused by evidence ID vs engine job ID mismatch.
- Added processing log writes so pipeline progress appears in the frontend Activity tab.

---

## Backend Architecture

### Neo4j Service Decomposition
- **Split `neo4j_service.py` (4,265 lines) into 8 focused domain services.** The original file was a god object that handled everything from graph visualization to financial queries to geocoding. Now each domain has its own module:
  - `driver.py` — Connection management, raw Cypher execution
  - `graph_service.py` — Graph visualization, search, AI context
  - `entity_service.py` — Entity CRUD, merge, dedup, recycling bin
  - `financial_service.py` — Transaction queries, categories, sub-transactions
  - `algorithm_service.py` — PageRank, Louvain, betweenness, shortest paths
  - `document_service.py` — Document and folder summaries
  - `geo_service.py` — Location queries and geocoding
  - `timeline_service.py` — Timeline event queries
- **Backward-compatible facade** (`Neo4jServiceFacade`) delegates all 68 methods to the new services, so existing router imports continue to work with zero changes. New code can import directly from the focused modules.

### Workspace Storage — JSON to PostgreSQL
- **Replaced all 7 JSON-on-disk storage operations with PostgreSQL.** Case contexts, witnesses, theories, tasks, notes, pinned items, and deadline configs were previously stored as individual JSON files in `data/`. This caused race conditions under concurrent access — BUG-007 (notes disappearing) and BUG-008 (failed to save notes) were both caused by two requests writing to the same file simultaneously.
- PostgreSQL provides proper transactional safety and concurrent access protection. Uses JSONB columns to preserve the flexible schema while gaining database guarantees.
- **Idempotent migration script** (`scripts/migrate_workspace_to_postgres.py`) safely moves existing JSON data into the new tables. Uses upsert pattern so it's safe to re-run.
- All method signatures are identical — zero router changes needed.

---

## Frontend / Performance

### Graph Performance
- Lightweight graph endpoint to reduce initial payload size.
- LOD (Level of Detail) rendering for large graphs.
- Financial table pagination and chunk cache cleanup.

### Case Management
- Inline file summaries shown in full without truncation.
- Case deadlines feature with full-stack CRUD support.

### Financial Table
- Fixed transaction categories showing as "Unknown".
- Added AI summary toggle per transaction.
- Widened financial table to 80/20 split for better readability.
