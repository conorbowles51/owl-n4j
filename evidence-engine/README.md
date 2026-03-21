# Evidence Engine

The Evidence Engine is a Python/FastAPI microservice responsible for all evidence handling within the OWL Investigation Platform. It receives investigative files (PDFs, Word documents, spreadsheets, images, audio, video), extracts structured intelligence from them using LLM-powered analysis, and writes the results into a Neo4j knowledge graph that powers the platform's graph, timeline, map, and financial views.

---

## Table of Contents

- [Why a Microservice](#why-a-microservice)
- [How It Fits Into the Platform](#how-it-fits-into-the-platform)
- [What the Evidence Engine Does](#what-the-evidence-engine-does)
- [Architecture Overview](#architecture-overview)
- [The Ingestion Pipeline](#the-ingestion-pipeline)
  - [Stage 1: Text Extraction](#stage-1-text-extraction)
  - [Stage 2: Chunking & Embedding](#stage-2-chunking--embedding)
  - [Stage 3: Entity & Relationship Extraction](#stage-3-entity--relationship-extraction)
  - [Stage 4: Entity Resolution (Deduplication)](#stage-4-entity-resolution-deduplication)
  - [Stage 5: Relationship Resolution](#stage-5-relationship-resolution)
  - [Stage 6: Summary Generation](#stage-6-summary-generation)
  - [Stage 7: Graph Writing](#stage-7-graph-writing)
- [The Ontology](#the-ontology)
  - [Entity Categories](#entity-categories)
  - [Relationship Types](#relationship-types)
  - [Disambiguation Rules](#disambiguation-rules)
  - [Frontend View Configuration](#frontend-view-configuration)
- [API Reference](#api-reference)
- [Real-Time Progress](#real-time-progress)
- [Job Lifecycle](#job-lifecycle)
- [Multi-File & Cross-Job Deduplication](#multi-file--cross-job-deduplication)
- [Services & Dependencies](#services--dependencies)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Why This Is Better Than the Old System](#why-this-is-better-than-the-old-system)
- [Development](#development)

---

## Why a Microservice

Evidence ingestion is the most resource-intensive operation in the platform. A single document can trigger hundreds of LLM calls, embedding computations, OCR passes, and graph writes that take 5–20 minutes. Running this inside the main backend meant that:

- Long-running ingestion blocked API request threads.
- A crash during ingestion could take down the entire backend.
- There was no way to scale ingestion independently of the API.
- Progress tracking was crude — the frontend had to poll JSON files.

The Evidence Engine solves all of this by running as a separate service with its own database, worker pool, and job queue.

---

## How It Fits Into the Platform

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────────────────────┐
│  Frontend    │────▶│  Main Backend    │────▶│  Evidence Engine (this service)  │
│  (React)     │     │  (FastAPI)       │     │  ┌──────────┐  ┌─────────────┐  │
│              │◀─ws─│                  │     │  │ API      │  │ Worker Pool │  │
└─────────────┘     └──────────────────┘     │  │ (FastAPI)│  │ (arq/Redis) │  │
                                              │  └──────────┘  └──────┬──────┘  │
                                              └────────────────────────┼─────────┘
                                                                       │
                                              ┌────────────────────────┼─────────┐
                                              │         Pipeline       │         │
                                              │  ┌─────────┐  ┌───────▼──────┐  │
                                              │  │ Neo4j   │  │ ChromaDB     │  │
                                              │  │ (graph) │  │ (vectors)    │  │
                                              │  └─────────┘  └──────────────┘  │
                                              └──────────────────────────────────┘
```

1. **User uploads a file** via the frontend.
2. **Main backend** proxies the upload to the Evidence Engine's API (`POST /cases/{case_id}/files`).
3. **Evidence Engine API** saves the file to disk, creates a job record, and enqueues it to the Redis job queue.
4. **Worker** picks up the job and runs it through the 7-stage ingestion pipeline.
5. **Progress updates** are published via Redis pub/sub and forwarded to the frontend over WebSocket.
6. **Results** are written to Neo4j (knowledge graph) and ChromaDB (vector embeddings), where the main backend and frontend can query them.

---

## What the Evidence Engine Does

| Responsibility | Description |
|---|---|
| **File Intake** | Accepts file uploads via REST API, stores originals on disk organized by case and job |
| **Text Extraction** | Extracts text from PDFs, Word, Excel, CSV, HTML, Markdown, images (OCR), audio (transcription), and video (frame analysis + audio transcription) |
| **Intelligent Chunking** | Splits extracted text into overlapping chunks optimized for LLM context windows |
| **Entity Extraction** | Uses LLM (GPT-4o-mini) to identify people, organizations, locations, transactions, and 20 other entity categories from text |
| **Relationship Extraction** | Identifies and types relationships between entities (WORKS_FOR, SENT_PAYMENT, LOCATED_AT, etc.) |
| **Entity Resolution** | Deduplicates entities within a file and across all files in a case using a three-phase approach (blocking, embedding similarity, LLM confirmation) |
| **Relationship Resolution** | Deduplicates relationships and normalizes relationship types |
| **Summary Generation** | Generates narrative summaries for every entity using GPT-4o |
| **Graph Writing** | Writes all entities and relationships to Neo4j with proper labels, properties, and indexes |
| **Geocoding** | Geocodes Location entities via Google Maps API so they appear on the map view |
| **RAG Embedding** | Embeds entities and document chunks in ChromaDB for semantic search and future deduplication |
| **Job Tracking** | Tracks job status and progress in its own PostgreSQL database |
| **Real-Time Progress** | Streams progress updates via Redis pub/sub to WebSocket clients |
| **File Serving** | Provides stored evidence files back to the frontend when needed |

---

## Architecture Overview

### Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| API Server | Python 3.12 + FastAPI | REST endpoints + WebSocket |
| Task Queue | Redis + arq | Async background job processing |
| Job Database | PostgreSQL 16 | Job tracking (separate from main DB) |
| Graph Database | Neo4j 5 | Knowledge graph (shared with platform) |
| Vector Database | ChromaDB | Document chunks + entity embeddings |
| LLM (extraction) | GPT-4o-mini | Entity/relationship extraction, dedup confirmation |
| LLM (summaries) | GPT-4o | High-quality narrative summaries |
| Embeddings | text-embedding-3-small | Vector embeddings for RAG and dedup |
| Audio Transcription | OpenAI Whisper | Audio/video transcription |
| OCR | Tesseract / OpenAI Vision | Image text extraction (configurable) |
| Video Processing | FFmpeg | Frame extraction, audio splitting |
| Geocoding | Google Maps API | Location coordinate resolution |

### Design Principles

- **Async throughout** — FastAPI, async SQLAlchemy, aiohttp, asyncio semaphores
- **Idempotent writes** — Neo4j MERGE (not CREATE) keyed on entity UUID, safe to re-run
- **Case isolation** — All data partitioned by `case_id` (separate ChromaDB collections, Neo4j node properties)
- **Structured LLM output** — All extraction uses OpenAI's JSON schema response format, no fragile parsing
- **Bounded concurrency** — Semaphore limits (10 concurrent OpenAI calls, 2 concurrent jobs) prevent overload

---

## The Ingestion Pipeline

The pipeline is orchestrated by `app/pipeline/orchestrator.py` and runs **sequentially** through 7 stages per file. Each stage updates the job's status and progress in the database and publishes updates via Redis.

### Stage 1: Text Extraction

**File:** `app/pipeline/extract_text.py`

Converts the uploaded file into raw text, handling each format appropriately:

| Format | Method |
|---|---|
| PDF | PyMuPDF — extracts text page by page |
| DOCX | python-docx — preserves structure, extracts tables separately |
| XLSX/CSV | openpyxl — each sheet as a separate table chunk |
| HTML/Markdown | BeautifulSoup/Markdown — strips markup |
| Images (JPG, PNG) | Tesseract OCR (default) or OpenAI Vision, plus EXIF metadata extraction |
| Audio (MP3, WAV) | OpenAI Whisper API, with FFmpeg chunking for files >25MB |
| Video (MP4, AVI) | FFmpeg key frame extraction → Vision API scene descriptions + audio track transcription |

**Output:** `ExtractedDocument(text, tables, metadata)` — tables are kept separate from body text because table-aware extraction prompts yield better results for financial data and structured records.

### Stage 2: Chunking & Embedding

**File:** `app/pipeline/chunk_embed.py`

Splits the extracted text into overlapping chunks and embeds them in ChromaDB for RAG (retrieval-augmented generation).

**Chunking strategy:**
- **Chunk size:** ~6,000 characters (~1,500 tokens)
- **Overlap:** 800 characters (~200 tokens)
- **Split hierarchy:** Paragraph breaks (`\n\n`) → line breaks (`\n`) → sentence boundaries (`. `) → word boundaries (` `)
- **Tables** are chunked independently with an `is_table` flag so the extraction prompt can adjust its approach

**Embedding:**
- Model: `text-embedding-3-small` (1,536 dimensions)
- Batched: 100 texts per API call
- Stored in ChromaDB collection `case_{case_id}_documents`
- Each chunk ID: `{job_id}_chunk_{index}`
- Metadata: file name, chunk index, table flag, sheet name (for Excel)

### Stage 3: Entity & Relationship Extraction

**File:** `app/pipeline/extract_entities.py`

This is the core intelligence stage. It uses a **two-pass design**:

**Pass 1 — Entity Extraction (parallel across chunks):**
- Each chunk is sent to GPT-4o-mini with:
  - The chunk text
  - The file name (for context)
  - The case's LLM profile (investigator-provided context about the case)
  - Whether this is a table chunk
  - The full ontology schema (entity categories, properties, disambiguation rules)
- The LLM returns structured JSON: an array of `RawEntity` objects
- Each entity has: `temp_id`, `category`, `specific_type`, `name`, `properties`, `source_quote`, `confidence`
- Chunks are processed in parallel, bounded by a semaphore (max 10 concurrent OpenAI calls)

**Pass 2 — Relationship Extraction (parallel across chunks):**
- Each chunk is sent again with the **entities extracted from that chunk** included as context
- The LLM identifies relationships between entities, returning `RawRelationship` objects
- Each relationship has: `source_entity_id`, `target_entity_id`, `type`, `detail`, `properties`, `confidence`
- The relationship type is guided by the ontology's 40+ preferred types but custom types are allowed

**Why two passes?** Relationships depend on knowing which entities exist. Extracting both simultaneously produced lower-quality relationships because the LLM had to do too much in a single call.

### Stage 4: Entity Resolution (Deduplication)

**File:** `app/pipeline/resolve_entities.py`

The same person, organization, or location often appears across multiple chunks (or across multiple files in a case). This stage merges duplicates using a **three-phase approach**:

**Phase 1 — Blocking (fast, deterministic):**
- Groups entities by category (Person with Person, Location with Location, etc.)
- Finds candidate pairs via:
  - Exact normalized-name matches
  - Token overlap ≥ 50% between names
  - Alias-to-name matches (e.g., "J. Smith" alias matches "John Smith" name)
- This phase is cheap and reduces the search space dramatically

**Phase 2 — Embedding Similarity:**
- Creates embeddings for all entities within each category
- Finds additional candidate pairs where cosine distance < 0.15
- Uses a temporary ChromaDB collection (cleaned up after)
- Catches fuzzy matches that blocking missed (e.g., "IBM" and "International Business Machines")

**Phase 3 — LLM Confirmation:**
- All candidate pairs from phases 1 and 2 are sent to GPT-4o-mini in batches of 20
- The LLM decides: **MERGE** or **KEEP_SEPARATE** for each pair
- A UnionFind data structure groups transitive merges (if A=B and B=C, then A=B=C)

**Merge execution:**
- The primary entity in each group is the one with the highest confidence and most properties
- The merged entity gets: a new UUID, all aliases combined, all source quotes combined, all source files tracked
- An ID mapping is produced so relationships can be remapped

**Cross-job deduplication** (when other files in the case have already been processed):
- Queries the existing `case_{case_id}_entities` ChromaDB collection
- Runs embedding similarity + LLM confirmation against previously ingested entities
- Marks matches as `is_existing=True` (these won't be re-embedded, just updated)

**Confidence filtering:**
- Entities below 0.4 confidence are dropped
- Relationships below 0.3 confidence are dropped
- Relationships pointing to dropped entities are also removed

### Stage 5: Relationship Resolution

**File:** `app/pipeline/resolve_relationships.py`

Deduplicates and normalizes relationships in two tiers:

**Tier 1 — Exact grouping:**
- Relationships with the same `(source_id, target_id, normalized_type)` are merged
- The merged relationship keeps: the longest detail text, the maximum confidence, all unique source quotes

**Tier 2 — Type normalization:**
- Finds relationships between the same entity pair but with different types
- Sends these to GPT-4o-mini in batches of 20
- The LLM decides: **MERGE** (choosing the canonical type) or **KEEP_SEPARATE**
- Example: "WORKS_FOR" and "EMPLOYED_BY" between the same two entities would be merged

### Stage 6: Summary Generation

**File:** `app/pipeline/generate_summaries.py`

Generates human-readable narrative summaries for every entity:

- **Model:** GPT-4o (the quality model — summaries are user-facing, so quality matters)
- **Input per entity:** Name, category, all properties, all source quotes, list of related entities
- **Batch size:** 5 entities per LLM call
- **Output:** 2–4 sentence narrative summary describing who/what the entity is and why it matters
- **Applied to all entities**, including `is_existing` ones (re-summarized with new context from the latest file)

### Stage 7: Graph Writing

**File:** `app/pipeline/write_graph.py`

The final stage writes everything to Neo4j and prepares data for RAG:

**Geocoding (Location entities only):**
- Constructs an address string from the entity's `address`, `city`, `region`, `country` properties
- Calls Google Maps Geocoding API to get `(latitude, longitude)`
- Results are cached in memory to avoid duplicate API calls
- Locations without coordinates won't appear on the map view

**Entity writes to Neo4j:**
- Batched in groups of 500 using `UNWIND ... MERGE` queries
- One batch per entity category (each category is a separate Neo4j label)
- Properties are flattened (no nested objects; lists are allowed)
- `MERGE` keyed on entity `id` makes writes idempotent — re-running a job won't create duplicates

**Relationship writes to Neo4j:**
- Batched in groups of 500
- Relationship type is sanitized to alphanumeric + underscores (Neo4j requirement)
- `MERGE` on `(source)-[type]->(target)` with property updates

**Entity embedding for RAG:**
- New entities (not `is_existing`) are embedded as: `"{category}: {name} — {description} (aliases: {aliases})"`
- Stored in ChromaDB collection `case_{case_id}_entities`
- Used for: (1) future cross-job deduplication, (2) semantic entity search in the frontend, (3) RAG context for the AI chat feature

---

## The Ontology

The ontology defines what the Evidence Engine can "see" in documents. It lives in `app/ontology/schema.yaml` and is loaded at startup. The ontology follows a **guided open** design: there are fixed categories with defined properties, but the LLM can assign a free-form `specific_type` for finer granularity (e.g., category "Person" with specific_type "Suspect" or "Informant").

### Entity Categories

The ontology defines **24 entity categories**, each becoming a Neo4j node label:

#### People & Organizations
| Category | Description | Key Properties |
|---|---|---|
| **Person** | A named individual | aliases, role, nationality, date_of_birth, description |
| **Organization** | A formal legal entity (company, agency, bank, NGO) | aliases, org_type, jurisdiction, description |
| **Group** | An informal association (gang, cell, network, syndicate) | aliases, group_type (enum), estimated_size, description |

#### Places & Events
| Category | Description | Key Properties |
|---|---|---|
| **Location** | A geographic location specific enough to map | address, city, region, country, coordinates_hint, specificity (enum) |
| **Event** | A meaningful discrete occurrence | date, date_precision (enum), event_type, significance, description |

#### Financial
| Category | Description | Key Properties |
|---|---|---|
| **Transaction** | An actual financial transfer with identifiable parties | amount, currency, date, sender, receiver, method, reference |
| **Account** | A financial account at an institution | account_number, institution, holder, account_type, currency |
| **FinancialInstrument** | A bearer instrument (credit card, check, crypto wallet) | instrument_type (enum), number, issuer, expiry |

#### Communications & Documents
| Category | Description | Key Properties |
|---|---|---|
| **Communication** | A specific communication (call, email, meeting) | comm_type, date, participants (list), duration, summary |
| **Document** | A text-based document referenced in evidence | doc_type, date, reference_number, author |
| **Media** | Audio/visual evidence (CCTV, photos, recordings) | media_type (enum), date, duration, source_device |

#### Physical Evidence
| Category | Description | Key Properties |
|---|---|---|
| **Vehicle** | Cars, boats, aircraft, motorcycles | vehicle_type (enum), make, model, year, color, registration_plate, VIN |
| **Weapon** | Firearms, blades, explosives | weapon_type (enum), make, model, serial_number, caliber |
| **Drug** | Controlled substances and precursors | substance_name, drug_type (enum), quantity, unit, estimated_value, form (enum) |
| **Device** | Physical electronic devices | device_type (enum), make, model, serial_number, IMEI, MAC address |
| **PhysicalEvidence** | Fallback for items that don't fit above categories | evidence_type, description |

#### Digital
| Category | Description | Key Properties |
|---|---|---|
| **CyberIdentity** | Digital identifiers (email, phone, username, IP, wallet) | identity_type (enum), platform, handle, associated_name |

#### Legal & Intelligence
| Category | Description | Key Properties |
|---|---|---|
| **LegalAction** | Formal legal proceedings (arrest, charge, conviction) | action_type (enum), case_number, jurisdiction, date, outcome |
| **Intelligence** | Intelligence products (tips, intercepts, surveillance) | intel_type (enum), date, source_reliability (NATO A–F), information_credibility (NATO 1–6) |

#### Catch-all
| Category | Description | Key Properties |
|---|---|---|
| **Other** | Entities that don't fit any category (must justify) | other_type, description |

### Relationship Types

The ontology defines **40+ relationship types** organized by domain. The LLM prefers these types but may create custom types when none fit.

**General:** `ASSOCIATED_WITH`, `RELATED_TO` (familial/personal)

**Employment & Membership:** `WORKS_FOR`, `SUPERVISED_BY`, `MEMBER_OF`, `AFFILIATED_WITH`, `CONTROLLED_BY`, `SUBSIDIARY_OF`, `KNOWN_ASSOCIATE_OF`

**Location & Movement:** `LOCATED_AT`, `TRAVELED_TO`, `RESIDED_AT`, `OPERATED_FROM`

**Financial:** `SENT_PAYMENT`, `RECEIVED_PAYMENT`, `VIA_ACCOUNT`, `HELD_BY`, `FINANCED_BY`, `BENEFICIAL_OWNER_OF`, `TRANSFERRED_TO`

**Communication & Identity:** `COMMUNICATED_WITH`, `ALIAS_OF`

**Legal:** `ARRESTED_FOR`, `CHARGED_WITH`, `CONVICTED_OF`, `SUSPECT_IN`, `VICTIM_OF`, `WITNESS_TO`

**Evidence & Ownership:** `OWNS`, `SEIZED_FROM`, `FOUND_AT`, `REGISTERED_TO`

**Document & Reference:** `MENTIONED_IN`

**Digital:** `ACCESSED_FROM`

**Event Participation:** `PARTICIPATED_IN`

Each relationship type specifies typical source/target categories and available properties (e.g., `WORKS_FOR` has `role`, `date_from`, `date_to`).

### Disambiguation Rules

The ontology includes explicit disambiguation rules injected into extraction prompts:

- **Device vs CyberIdentity:** Device = the physical object (a phone). CyberIdentity = the digital identifier (the phone number). Extract both when the text mentions a device and its identifiers.
- **Account vs FinancialInstrument:** Account = held at an institution. FinancialInstrument = bearer instrument (credit card, check).
- **Organization vs Group:** Organization = formal legal entity. Group = informal association.
- **Document vs Media:** Document = text-based. Media = audio/visual.
- **Event vs LegalAction:** Event = real-world occurrence. LegalAction = formal legal proceeding.
- **PhysicalEvidence:** Always prefer the specific category (Vehicle, Weapon, Drug, Device) if applicable.

### Frontend View Configuration

The ontology configures which entity categories power each frontend view:

| View | Categories | Required Fields |
|---|---|---|
| **Timeline** | Event, LegalAction, Media, Intelligence, Transaction, Communication | `date` |
| **Map** | Location | `latitude`, `longitude` |
| **Financial** | Transaction | `amount`, `currency` |
| **Graph** | All categories | — |

---

## API Reference

**Base URL:** `http://evidence-engine:8000` (internal) or `http://localhost:8001` (dev)

### Upload File

```
POST /cases/{case_id}/files
Content-Type: multipart/form-data

Parameters:
  file: UploadFile (required)
  llm_profile: string (optional) — case context provided by the investigator

Response 201:
{
  "id": "uuid",
  "case_id": "string",
  "file_name": "string",
  "status": "pending",
  "progress": 0.0,
  "entity_count": 0,
  "relationship_count": 0,
  "created_at": "ISO timestamp"
}
```

### Get Job Status

```
GET /jobs/{job_id}

Response 200:
{
  "id": "uuid",
  "case_id": "string",
  "file_name": "string",
  "status": "extracting_entities",
  "progress": 0.45,
  "entity_count": 23,
  "relationship_count": 15,
  "error_message": null,
  "created_at": "ISO timestamp",
  "updated_at": "ISO timestamp"
}
```

### List Jobs for Case

```
GET /cases/{case_id}/jobs

Response 200: [ { ...job }, ... ]
```

### Health Check

```
GET /health

Response 200:
{
  "status": "ok",
  "checks": {
    "postgres": true,
    "neo4j": true,
    "chromadb": true,
    "redis": true
  }
}
```

---

## Real-Time Progress

The Evidence Engine provides real-time progress updates via WebSocket:

```
WS /ws/jobs/{job_id}

Messages (JSON):
{
  "job_id": "uuid",
  "status": "extracting_entities",
  "progress": 0.45,
  "message": "Extracting entities from chunk 12/27…"
}
```

**How it works:**
1. The pipeline publishes status updates to a Redis pub/sub channel (`job:{job_id}:progress`)
2. The WebSocket endpoint subscribes to this channel and forwards messages to connected clients
3. The connection closes automatically when the job reaches `completed` or `failed`

This decoupled design means the worker doesn't need to know about WebSocket connections, and multiple clients can watch the same job.

---

## Job Lifecycle

```
PENDING ──▶ EXTRACTING_TEXT ──▶ CHUNKING ──▶ EXTRACTING_ENTITIES
                                                     │
                                                     ▼
COMPLETED ◀── WRITING_GRAPH ◀── GENERATING_SUMMARIES ◀── RESOLVING_RELATIONSHIPS ◀── RESOLVING_ENTITIES
    │
    ▼
  (or FAILED at any stage)
```

**Worker configuration:**
- Max concurrent jobs: **2** (prevents OpenAI rate limiting)
- Job timeout: **1 hour**
- Retry on failure: **3 attempts**

**Failure behavior:** If any stage fails, the entire job is marked `FAILED` with the error message stored in the database. Because Neo4j writes use `MERGE`, a failed job can be safely re-run without creating duplicates.

---

## Multi-File & Cross-Job Deduplication

When an investigator uploads multiple files to the same case, the Evidence Engine ensures entities are deduplicated across all files:

1. **File A** is uploaded and processed. Its entities are written to Neo4j and embedded in ChromaDB collection `case_{case_id}_entities`.

2. **File B** is uploaded. During entity resolution (Stage 4), the pipeline:
   - Queries the existing `case_{case_id}_entities` collection for similar entities
   - Runs embedding similarity + LLM confirmation against previously ingested entities
   - Marks matching entities as `is_existing=True`
   - Remaps relationships to point to the existing entity IDs

3. **The result:** The Neo4j graph contains a unified, deduplicated view across all files in the case. "John Smith" mentioned in File A and "J. Smith" in File B become the same node with merged properties and combined source quotes.

---

## Services & Dependencies

The Evidence Engine connects to four external services via thin async wrapper clients:

| Service | Client | Purpose |
|---|---|---|
| **Neo4j** | `app/services/neo4j_client.py` | Read/write knowledge graph. Singleton async driver with connection pooling. |
| **ChromaDB** | `app/services/chroma_client.py` | Vector storage for document chunks and entity embeddings. HTTP client. Collections per case. |
| **OpenAI** | `app/services/openai_client.py` | LLM calls (extraction, dedup, summaries) and embeddings. Semaphore-bounded to 10 concurrent calls. |
| **Redis** | `app/services/redis_client.py` | Job queue (arq) and progress pub/sub. Singleton aioredis connection. |

---

## Configuration

All configuration is via environment variables, loaded by Pydantic Settings in `app/config.py`:

```bash
# PostgreSQL (evidence-engine job tracking — separate from main DB)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@evidence-postgres:5432/ingestion

# Neo4j (shared with main platform)
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# ChromaDB (shared with main platform)
CHROMA_HOST=chromadb
CHROMA_PORT=8000

# Redis (shared — job queue + pub/sub)
REDIS_URL=redis://redis:6379

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini                    # Extraction & dedup
OPENAI_QUALITY_MODEL=gpt-4o                 # Summaries
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# Quality thresholds
ENTITY_CONFIDENCE_THRESHOLD=0.4             # Drop entities below this
RELATIONSHIP_CONFIDENCE_THRESHOLD=0.3       # Drop relationships below this

# File storage
STORAGE_PATH=/data/files                    # Where uploaded files are saved

# Image processing
IMAGE_PROVIDER=tesseract                    # Or "openai" for Vision API OCR
TESSERACT_LANG=eng

# Video processing
VIDEO_FRAME_INTERVAL=30                     # Seconds between key frames
VIDEO_MAX_FRAMES=50

# Geocoding (optional — needed for map view)
GOOGLE_MAPS_API_KEY=...
```

---

## Project Structure

```
evidence-engine/
├── app/
│   ├── main.py                    # FastAPI app + lifespan (service init/shutdown)
│   ├── config.py                  # Pydantic Settings (all env vars)
│   ├── dependencies.py            # SQLAlchemy async session factory
│   ├── worker.py                  # arq worker entry point + settings
│   ├── models/
│   │   └── job.py                 # SQLAlchemy Job model
│   ├── schemas/
│   │   └── job.py                 # Pydantic request/response schemas
│   ├── api/
│   │   ├── routes/
│   │   │   ├── upload.py          # POST /cases/{case_id}/files
│   │   │   ├── jobs.py            # GET /jobs, GET /cases/{case_id}/jobs
│   │   │   └── health.py         # GET /health
│   │   └── websocket.py          # WS /ws/jobs/{job_id}
│   ├── pipeline/                  # === THE INGESTION PIPELINE ===
│   │   ├── orchestrator.py        # Chains all stages, updates status
│   │   ├── extract_text.py        # Stage 1: file → text
│   │   ├── chunk_embed.py         # Stage 2: text → chunks in ChromaDB
│   │   ├── extract_entities.py    # Stage 3: chunks → entities + relationships
│   │   ├── resolve_entities.py    # Stage 4: entity deduplication
│   │   ├── resolve_relationships.py # Stage 5: relationship deduplication
│   │   ├── generate_summaries.py  # Stage 6: entity narrative summaries
│   │   └── write_graph.py         # Stage 7: Neo4j + geocoding + RAG
│   ├── services/                  # Thin async wrappers
│   │   ├── neo4j_client.py
│   │   ├── chroma_client.py
│   │   ├── openai_client.py
│   │   └── redis_client.py
│   ├── ontology/                  # === THE KNOWLEDGE SCHEMA ===
│   │   ├── schema.yaml            # 24 entity categories, 40+ relationship types
│   │   ├── loader.py              # YAML → typed dataclasses
│   │   ├── schema_builder.py      # Generates OpenAI JSON schemas from ontology
│   │   └── prompt_builder.py      # Builds extraction prompts from ontology
│   └── prompts/                   # LLM prompt templates
│       ├── entity_resolution.txt
│       ├── entity_summary.txt
│       └── relationship_resolution.txt
├── alembic/                       # Database migrations
│   ├── env.py
│   └── versions/
│       ├── 001_create_jobs_table.py
│       └── 002_add_pipeline_status_values.py
├── tests/
├── Dockerfile                     # Python 3.12 + FFmpeg + Tesseract
├── pyproject.toml                 # Dependencies
└── alembic.ini
```

---

## Why This Is Better Than the Old System

The Evidence Engine replaces an older evidence handling system that was built directly into the main backend. Here's why the new architecture is a significant improvement:

### Old System: How It Worked

- **JSON file storage:** Evidence metadata lived in `data/evidence.json` and logs in `data/evidence_logs.json` — flat JSON files on disk.
- **In-process ingestion:** Document processing ran synchronously inside the main backend's request threads, blocking the API for 5–20 minutes per file.
- **Flat file structure:** No folder organization — all files dumped into a flat directory per case.
- **Progress tracking:** The frontend polled JSON log files for status updates — no real-time feedback.
- **No isolation:** A crash or memory spike during ingestion could bring down the entire backend, including the API, chat, and graph queries.
- **Single-threaded scaling:** Processing was limited to Python's ThreadPoolExecutor within the main backend process.

### New System: What Changed

| Dimension | Old System | Evidence Engine |
|---|---|---|
| **Metadata storage** | JSON files on disk | PostgreSQL with indexes, constraints, JSONB |
| **Processing model** | Synchronous, blocks API threads | Async background workers via Redis + arq |
| **Failure isolation** | Crash takes down entire backend | Crash only affects evidence worker; API stays up |
| **Scalability** | Single process, ThreadPoolExecutor | Independent worker pool, can scale horizontally |
| **Progress tracking** | Poll JSON files | Real-time WebSocket via Redis pub/sub |
| **File organization** | Flat directory per case | Hierarchical folders with breadcrumbs |
| **Deduplication** | SHA256 hash lookup in JSON | SHA256 index in PostgreSQL + three-phase entity dedup |
| **Data integrity** | No transactions, no constraints | PostgreSQL transactions, foreign keys, cascade deletes |
| **Querying** | Load and scan entire JSON file | SQL queries with indexes |
| **API integration** | Direct function imports (tight coupling) | HTTP client (loose coupling, independently deployable) |
| **Concurrency control** | None | Semaphore-bounded OpenAI calls, configurable worker pool |
| **Retry logic** | None — failed jobs stayed failed | Automatic retry (3 attempts) via arq |

### Key Improvements in Practice

1. **The backend never blocks.** Users can continue using the graph, chat, and financial views while files process in the background.

2. **Real-time progress.** Investigators see exactly what stage their file is at ("Extracting entities from chunk 12/27...") instead of a spinning loader.

3. **Crash resilience.** If the evidence worker hits an out-of-memory error processing a 500-page PDF, the main backend keeps running. The job is automatically retried.

4. **Folder management.** Investigators can organize evidence into hierarchical folders with drag-and-drop, breadcrumb navigation, and cascade deletes — replacing the old flat file dump.

5. **Better deduplication.** The old system only detected duplicate files (by SHA256 hash). The new system deduplicates entities across files using embedding similarity and LLM confirmation, producing a cleaner knowledge graph.

6. **Independent deployment.** The evidence engine can be updated, restarted, or scaled without touching the main backend. In production, you can run more workers during a bulk upload without affecting API performance.

7. **Proper database.** Moving from JSON files to PostgreSQL means ACID transactions, proper indexing, concurrent access safety, and the ability to query evidence metadata efficiently (e.g., "show me all failed jobs in the last hour").

---

## Development

### Running Locally

```bash
# Start infrastructure services
docker compose up neo4j postgres redis chromadb evidence-postgres -d

# Run database migrations
alembic upgrade head

# Start the API server (hot-reload)
uvicorn app.main:app --reload --port 8000

# Start the background worker (separate terminal)
arq app.worker.WorkerSettings
```

### Running with Docker

```bash
# Start everything including evidence-engine
docker compose up

# Services:
#   evidence-engine-api    → localhost:8001
#   evidence-engine-worker → (background, no port)
#   evidence-postgres      → localhost:5433
#   neo4j                  → localhost:7687
#   chromadb               → localhost:8100
#   redis                  → localhost:6379
```

### Running Tests

```bash
pytest
```

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```
