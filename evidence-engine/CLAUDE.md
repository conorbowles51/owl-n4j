# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **ingestion service** — a Python/FastAPI microservice that is part of a larger **investigations console** application. Investigators create cases, upload files (PDFs, audio, Word docs, Excel, etc.), and this service processes them into a structured knowledge graph.

The application is **single-tenant** — each customer gets their own server running the full stack via Docker Compose.

## Common Commands

```bash
# Start all services (API, worker, Postgres, Neo4j, ChromaDB, Redis)
docker compose up

# Run DB migrations
alembic upgrade head

# Start API server (dev, outside Docker)
uvicorn app.main:app --reload

# Start arq worker (dev, outside Docker)
arq app.worker.WorkerSettings

# Run tests
pytest
```

## Project Structure

```
app/
├── main.py              # FastAPI app factory + lifespan
├── config.py            # Pydantic Settings (all env vars)
├── dependencies.py      # SQLAlchemy async session factory
├── worker.py            # arq worker entry point
├── models/job.py        # SQLAlchemy Job model (PostgreSQL)
├── schemas/job.py       # Pydantic request/response schemas
├── api/
│   ├── routes/          # upload.py, jobs.py, health.py
│   └── websocket.py     # WS /ws/jobs/{job_id} progress stream
├── pipeline/            # Core processing stages (run sequentially by orchestrator)
│   ├── orchestrator.py  # Chains stages, updates job status
│   ├── extract_text.py  # Stage 1: file → ExtractedDocument
│   ├── chunk_embed.py   # Stage 2: text → TextChunks in ChromaDB
│   ├── extract_entities.py  # Stage 3: two-pass entity+relationship extraction
│   ├── resolve_entities.py  # Stage 4: block → embed → LLM confirm dedup
│   └── write_graph.py   # Stage 5: Neo4j + geocoding + RAG embeddings
├── services/            # Thin async wrappers: openai, neo4j, chroma, redis
└── prompts/             # LLM prompt templates (.txt files with {placeholders})
```

## Pipeline Architecture

The pipeline runs **sequentially** per file, orchestrated by `pipeline/orchestrator.py`:

1. **extract_text** → `ExtractedDocument(text, tables, metadata)` — tables kept separate for table-aware extraction
2. **chunk_embed** → `list[TextChunk]` stored in ChromaDB `case_{id}_documents`
3. **extract_entities** → Two-pass: entities from chunks (parallel), then relationships using known entities (parallel). Uses `asyncio.gather` bounded by a semaphore (10 concurrent OpenAI calls)
4. **resolve_entities** → Three-phase dedup: blocking (name/alias matching) → embedding similarity (cosine > 0.85) → LLM confirmation (batches of 20). Uses UnionFind for merge groups. Cross-job dedup against existing `case_{id}_entities` ChromaDB collection
5. **write_graph** → MERGE with UNWIND (batches of 500) into Neo4j. Geocodes locations. Embeds entities into ChromaDB for RAG

## Key Design Decisions

- **Guided open ontology**: 10 fixed categories (Person, Organization, Location, Event, Transaction, Communication, Account, Document, PhysicalEvidence, Other) + AI-chosen `specific_type`. Dual-labeled in Neo4j
- **Task queue**: arq (async-native, Redis-based) — not Celery
- **Chunking**: Custom recursive splitter (~6000 chars, 800 overlap) — no langchain dependency
- **Extraction model**: GPT-4o-mini via `response_format={"type": "json_object"}`
- **ChromaDB collections**: One per case (`case_{id}_documents`, `case_{id}_entities`) for natural isolation
- **Neo4j writes**: Always MERGE (not CREATE) keyed on entity `id` — idempotent for re-runs
- **Progress**: Redis pub/sub → WebSocket forwarding
- **File storage**: Disk at `{STORAGE_PATH}/{case_id}/{job_id}/{filename}`

## Tech Stack

- **Backend**: Python 3.12 + FastAPI
- **Graph DB**: Neo4j 5 (entities and relationships)
- **Relational DB**: PostgreSQL 16 (job tracking via SQLAlchemy async + Alembic)
- **Vector DB**: ChromaDB (document chunks + entity embeddings for RAG and dedup)
- **LLM**: OpenAI API — GPT-4o-mini for extraction/dedup, text-embedding-3-small for embeddings
- **Audio transcription**: OpenAI Whisper API (ffmpeg for chunking files >25MB)
- **Image OCR**: Tesseract or OpenAI Vision (configurable via `IMAGE_PROVIDER`)
- **Video processing**: FFmpeg frame extraction + Vision API descriptions + audio transcription
- **Queue**: Redis + arq
- **Infrastructure**: Google Cloud, single instance, Docker Compose

## Frontend Views (data requirements)

The React frontend (separate repo) consumes the graph through four views. When modifying extraction or graph writing, ensure data supports all four:

- **Graph view** — All entities and relationships, fulltext search on name/description
- **Timeline view** — Event nodes with `date` + `date_precision` properties
- **Map view** — Location nodes with `latitude`/`longitude` (geocoded via Google Maps API)
- **Financial view** — Transaction nodes with `amount`, `currency`, `date`, `sender`, `receiver`, `method`

## Key Design Challenges

- **Entity deduplication at scale**: Cases can have 10K+ entities. Three-phase approach: blocking → embedding similarity → LLM confirmation. Cross-job dedup is built in (queries existing entity embeddings)
- **Extraction noise**: Prompts enforce selective extraction with explicit inclusion/exclusion rules per category. Every entity requires `source_quote` and `confidence`
- **Location specificity**: Only locations specific enough to geocode. Prompt explicitly excludes vague regions
- **Transaction modeling**: Only actual financial transactions with identifiable parties. Prompt excludes incidental monetary references
- **Timeline relevance**: Only meaningful discrete events. Prompt excludes vague temporal references
