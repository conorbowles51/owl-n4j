# Ingestion Process Map (Starting at `ingest_data.py`)

This document maps the ingestion pipeline in this repo from the CLI entrypoint through chunking, LLM extraction, entity resolution, and Neo4j persistence.

## High-level flow

```mermaid
flowchart TD
    A[CLI: scripts/ingest_data.py] --> B{Choose input}

    B -->|--file PATH| C[ingest_file(path)]
    B -->|no args| D[find_data_dir() -> ingestion/data]
    D --> E[ingest_all_in_data(data_dir)
    scans *.txt + *.pdf]
    E --> C

    C -->|.txt| T[text_ingestion.ingest_text_file]
    C -->|.pdf| P[pdf_ingestion.ingest_pdf_file]
    C -->|other| SKIP[skip unsupported]

    T --> I[ingestion.ingest_document(text, doc_name, metadata)]
    P --> PX[pdf_ingestion.extract_text_from_pdf
    inserts --- Page N --- markers]
    PX --> I

    I --> DOC[Neo4j: ensure_document(:Document {key})]
    I --> KEYS[Neo4j: get_all_entity_keys()
    context for LLM]
    I --> CH[chunking.chunk_document
    -> chunks with page_start/page_end]

    I --> EST[llm_client.get_processing_estimate
    optional, non-fatal]
    I --> TIMER[Timer thread: every 10s
    llm_client.get_processing_progress_update
    optional, non-fatal]

    CH --> LOOP{{for each chunk}}
    LOOP --> PC[process_chunk(...)]

    PC --> EX[llm_client.extract_entities_and_relationships
    returns entities + relationships JSON]

    EX --> ENTLOOP{{for each entity}}
    ENTLOOP --> NK[entity_resolution.normalise_key]
    NK --> RES[entity_resolution.resolve_entity
    exact -> fuzzy -> LLM disambiguation]

    RES -->|existing| UPD[Neo4j: find_entity_by_key
    merge facts/insights + notes
    generate_entity_summary
    update_entity]
    RES -->|new| NEW[Neo4j: create_entity
    generate_entity_summary]

    UPD --> GEO1{location present
    & no coords yet?}
    GEO1 -->|yes| GEO[geocoding.get_location_properties
    (cached Nominatim)]
    GEO1 -->|no| NO1[skip geocoding]
    GEO --> UPD

    NEW --> GEO2{location present?}
    GEO2 -->|yes| GEO
    GEO2 -->|no| NO2[skip geocoding]

    UPD --> LINK[Neo4j: link_entity_to_document
    (e)-[:MENTIONED_IN]->(d:Document)]
    NEW --> LINK

    EX --> RELLOOP{{for each relationship}}
    RELLOOP --> CR[Neo4j: create_relationship
    MERGE (from)-[TYPE]->(to)]

    PC --> NEXT[chunk processed]
    NEXT --> LOOP

    I --> DONE[returns summary counts]

    A -->|--clear| CLR[Neo4j: clear_database()
    MATCH (n) DETACH DELETE n]
```

## Call graph (from `ingest_data.py`)

- `scripts/ingest_data.py`
  - `main()` parses args: `--file`, `--data-dir`, `--clear`
  - `--clear` → `clear_database()` → `Neo4jClient.clear_database()`
  - file routing:
    - `.txt` → `text_ingestion.ingest_text_file(path)`
    - `.pdf` → `pdf_ingestion.ingest_pdf_file(path)`
- `scripts/text_ingestion.py`
  - reads file as UTF-8 (fallback latin-1)
  - builds `doc_metadata` (`source_type: text`, filename, full_path)
  - calls `ingestion.ingest_document(text, doc_name, doc_metadata)`
- `scripts/pdf_ingestion.py`
  - extracts text via `pypdf.PdfReader` page-by-page
  - inserts `--- Page N ---` markers to preserve page context
  - builds `doc_metadata` (`source_type: pdf`, filename, full_path, page_count)
  - calls `ingestion.ingest_document(text, doc_name, doc_metadata)`
- `scripts/ingestion.py`
  - `ingest_document(...)` is the main orchestrator:
    - ensures a `:Document` node exists in Neo4j (`ensure_document`)
    - fetches existing entity keys for LLM context (`get_all_entity_keys`)
    - chunks the doc with page ranges (`chunk_document`)
    - (optional) asks the LLM for an initial time estimate
    - starts a timer thread that periodically asks the LLM for a “progress update”
    - loops chunks → `process_chunk(...)`
  - `process_chunk(...)`:
    - calls LLM extraction (`extract_entities_and_relationships`)
    - entity loop: resolve & upsert nodes (+ summaries + optional geocoding)
    - relationship loop: create `(:Entity)-[:TYPE]->(:Entity)` edges

## What each module is responsible for

### LLM-facing

- `scripts/llm_client.py`
  - `extract_entities_and_relationships(...)`
    - prompts LLM to output JSON for:
      - `entities[]` with `verified_facts[]` and optional `ai_insights[]`
      - `relationships[]` with `from_key`, `to_key`, `type`, `notes`
    - passes `existing_entity_keys` sample into the prompt to encourage reuse
    - includes page context (`page_start/page_end`) in the prompt
  - `disambiguate_entity(...)`
    - asked during fuzzy matching to decide if candidate == existing entity
  - `generate_entity_summary(...)`
    - summary is generated from **verified facts** when available (fallback to notes)
  - progress helpers (best-effort, ingestion continues on failure):
    - `get_processing_estimate(...)`
    - `get_processing_progress_update(...)`

### Chunking / citations

- `scripts/chunking.py`
  - `chunk_document(text, doc_name, ...)` → list of chunk dicts containing:
    - `text`, `chunk_index`, `total_chunks`
    - `page_start`, `page_end` (derived from `--- Page N ---` markers)

### Entity resolution

- `scripts/entity_resolution.py`
  - `normalise_key(raw)` → stable lowercase “slug key” used for dedupe
  - `resolve_entity(...)` strategy:
    1. exact match: `Neo4jClient.find_entity_by_key(candidate_key)`
    2. fuzzy candidates: `Neo4jClient.fuzzy_search_entities(name, type)`
    3. LLM disambiguation: `llm_client.disambiguate_entity(...)`

### Neo4j persistence

- `scripts/neo4j_client.py`
  - `ensure_document(doc_key, doc_name, metadata)`
    - `MERGE (d:Document {key})` and sets metadata
  - entity upserts:
    - `create_entity(...)` (label is the sanitized entity type)
    - `update_entity(...)` (notes/summary + extra properties)
  - graph links:
    - `link_entity_to_document(entity_key, doc_key)` creates `[:MENTIONED_IN]`
    - `create_relationship(from_key, to_key, rel_type, doc_name, notes)`
      - sanitizes relationship type into a Cypher-safe name
      - `MERGE` to avoid duplicates
      - appends per-document notes into `r.doc_refs` when provided
  - maintenance:
    - `clear_database()` deletes all nodes and relationships

### Geocoding enrichment

- `scripts/geocoding.py`
  - `get_location_properties(location)`
    - uses OpenStreetMap Nominatim (rate-limited)
    - caches results in `ingestion/data/geocoding_cache.json`
    - returns Neo4j-ready properties (`latitude`, `longitude`, etc.)

## Data written to the graph (at a glance)

- Document nodes
  - label: `Document`
  - key: `normalise_key(doc_name)`
  - metadata includes `source_type`, `filename`, `full_path`, optionally `page_count`

- Entity nodes
  - label: sanitized LLM `type` (fallback `Other`)
  - key: `normalise_key(entity.key or entity.name)`
  - properties include:
    - `name`, `notes`, `summary`
    - `verified_facts` (JSON string)
    - `ai_insights` (JSON string)
    - optional geocoding fields (`latitude`, `longitude`, ...)

- Relationships
  - `(:Entity)-[:MENTIONED_IN]->(:Document)`
  - `(:Entity)-[:<REL_TYPE>]->(:Entity)` for extracted relationships

## Configuration / assumptions

- Environment variables are loaded by `scripts/config.py` from repo root `.env` when present.
  - `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
  - `OPENAI_MODEL` (defaults to `gpt-5`)
- `ingestion/docker-compose.yml` sets Neo4j auth to `neo4j/testpassword`; your `.env` must match if you use that compose file.

## Quick “where do I start?”

- To understand the CLI behavior: start in `scripts/ingest_data.py`.
- To understand the real ingestion logic: jump to `scripts/ingestion.py`.
- To understand what the LLM is asked to return: read `scripts/llm_client.py`.
- To understand how keys merge across docs: read `scripts/entity_resolution.py`.
