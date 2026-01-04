# Ingestion Flow Documentation

This document describes the two-phase entity-first ingestion pipeline for extracting knowledge from documents.

## Architecture Overview

The ingestion system follows a **two-phase extraction approach** that decouples entity extraction from relationship creation, improving accuracy and allowing the AI complete freedom in choosing entity and relationship types.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DOCUMENT INGESTION                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────┐    ┌──────────┐    ┌─────────────────────────────────────────┐│
│  │ Document│───▶│ Chunking │───▶│              FOR EACH CHUNK              ││
│  └─────────┘    │ (18%     │    │                                          ││
│                 │ overlap) │    │  ┌────────────────────────────────────┐ ││
│                 └──────────┘    │  │  PHASE 1: Entity Extraction        │ ││
│                                 │  │  - system_context (from profile)   │ ││
│                                 │  │  - entity_definitions (hints only) │ ││
│                                 │  │  - resolved entities from earlier  │ ││
│                                 │  │    chunks (co-reference)           │ ││
│                                 │  │  - AI has FULL FREEDOM on types    │ ││
│                                 │  │                                    │ ││
│                                 │  │  Output: entities + candidate_rels │ ││
│                                 │  └─────────────┬──────────────────────┘ ││
│                                 │                │                        ││
│                                 │                ▼                        ││
│                                 │  ┌────────────────────────────────────┐ ││
│                                 │  │  PHASE 2: Entity Resolution        │ ││
│                                 │  │  For each entity:                  │ ││
│                                 │  │  1. normalise_key()                │ ││
│                                 │  │  2. resolve_entity()               │ ││
│                                 │  │     - exact match                  │ ││
│                                 │  │     - fuzzy search                 │ ││
│                                 │  │     - type compatibility check     │ ││
│                                 │  │     - batch LLM disambiguation     │ ││
│                                 │  │  3. create/merge in Neo4j          │ ││
│                                 │  │  4. build key mapping              │ ││
│                                 │  └─────────────┬──────────────────────┘ ││
│                                 │                │                        ││
│                                 │                ▼                        ││
│                                 │  ┌────────────────────────────────────┐ ││
│                                 │  │  PHASE 2b: Relationship Creation   │ ││
│                                 │  │  1. Remap candidate_rel keys using │ ││
│                                 │  │     resolution mapping             │ ││
│                                 │  │  2. Create relationships in Neo4j  │ ││
│                                 │  │  (All entities guaranteed to exist)│ ││
│                                 │  └────────────────────────────────────┘ ││
│                                 └─────────────────────────────────────────┘│
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                    POST-PROCESSING (after all chunks)                   ││
│  │  1. Generate entity summaries (once per entity, all facts available)   ││
│  │  2. Batch geocoding (all locations at once)                            ││
│  │  3. Generate document embedding                                         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. Chunking (`chunking.py`)

Documents are split into overlapping chunks for processing:

- **Chunk Size**: 2500 characters
- **Overlap**: 450 characters (~18%) - increased from 8% for better context continuity
- **Sentence-Aware**: Attempts to break at sentence boundaries
- **Page Tracking**: Maintains page number information for citations
- **Marker Stripping**: Page markers (e.g., `--- Page N ---`) are stripped before LLM processing but retained for metadata

### 2. Entity Extraction (`llm_client.py`)

The `extract_candidate_entities()` function prompts the LLM to extract entities and relationships:

#### Profile Usage

The extraction uses two things from the profile:

1. **`system_context`**: Sets the domain context (e.g., "You are analyzing a fraud investigation...")
2. **`entity_definitions`**: Optional hints for domain-specific entity types the AI might otherwise miss

**Important**: These are **hints only**. The AI has **complete freedom** to choose any entity types and relationship types it deems appropriate.

#### What's NOT Used

- `entity_types` - Not used; AI chooses freely
- `relationship_examples` - Not used; AI chooses freely  
- `relationship_types` - Not used; AI chooses freely

#### Extraction Output

```json
{
  "entities": [
    {
      "key": "john-smith",
      "type": "Person",
      "name": "John Smith",
      "date": "2024-01-15",
      "location": "New York",
      "verified_facts": [
        {
          "text": "John Smith is the CFO of Emerald Imports",
          "quote": "John Smith, serving as CFO of Emerald Imports...",
          "page": 3,
          "importance": 5
        }
      ],
      "ai_insights": [
        {
          "text": "May have knowledge of the fraudulent transactions",
          "confidence": "medium",
          "reasoning": "As CFO, he would oversee financial operations"
        }
      ]
    }
  ],
  "candidate_relationships": [
    {
      "from_key": "john-smith",
      "to_key": "emerald-imports",
      "type": "CFO_OF",
      "notes": "John Smith serves as CFO"
    }
  ]
}
```

### 3. Entity Resolution (`entity_resolution.py`)

Each extracted entity goes through resolution to avoid duplicates:

```
┌─────────────────────────────────────────────────────────────┐
│                    RESOLUTION FLOW                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. EXACT MATCH                                             │
│     └─ Key matches existing entity? → Use existing          │
│                                                             │
│  2. FUZZY SEARCH                                            │
│     └─ Name similarity search in Neo4j                      │
│                                                             │
│  3. TYPE COMPATIBILITY CHECK                                │
│     └─ Filter out incompatible types                        │
│        (e.g., Person won't match Company)                   │
│                                                             │
│  4. BATCH LLM DISAMBIGUATION                                │
│     └─ Send ALL candidates to LLM at once                   │
│     └─ LLM ranks/identifies best match                      │
│     └─ Returns best_match_key or null                       │
│                                                             │
│  Result: (resolved_key, is_existing)                        │
└─────────────────────────────────────────────────────────────┘
```

#### Type Compatibility

The following type pairs are considered **incompatible** (won't be matched):
- Person ↔ Company
- Person ↔ Organisation
- Person ↔ Bank
- Person ↔ Account
- Location ↔ Person
- Location ↔ Company

### 4. Key Mapping & Relationship Remapping

After entity resolution, a key mapping is built:

```python
key_mapping = {
    "j-smith": "john-smith",      # Merged into existing entity
    "john-s": "john-smith",       # Another variation merged
}
```

When creating relationships, candidate keys are remapped:

```python
# Original candidate relationship
{"from_key": "j-smith", "to_key": "emerald-imports", "type": "CFO_OF"}

# After remapping
{"from_key": "john-smith", "to_key": "emerald-imports", "type": "CFO_OF"}
```

This ensures relationships always reference valid, resolved entities.

### 5. Verified Facts & Quote Validation

Each `verified_fact` is validated against the source text:

```python
{
  "text": "John Smith transferred $50,000",
  "quote": "John Smith authorized a transfer of $50,000...",
  "page": 5,
  "importance": 5,
  "quote_validated": true  # Added during ingestion
}
```

If the quote cannot be found in the source text (even with fuzzy matching), `quote_validated` is set to `false` and a warning is logged.

### 6. Post-Processing

After all chunks are processed:

#### Summary Generation

- Summaries are generated **once per entity** at the end
- All verified facts are available, sorted by importance (5 → 1)
- High-importance facts (4-5) are always included
- Related entities provide context

#### Batch Geocoding

- All locations are collected during chunk processing
- Geocoding is done in batch at the end
- Includes retry logic for failed lookups
- Results are stored as `latitude`, `longitude`, `formatted_address`

#### Document Embedding

- Full document text is embedded using the embedding service
- Stored in ChromaDB for semantic search
- Linked to Neo4j Document node via `vector_db_id`

## Error Handling

### LLM Retry Logic

- Max 3 retries with exponential backoff (1s, 2s, 4s)
- Retries on: timeout, rate limits, HTTP errors
- Non-retryable: 404 (model not found)

### JSON Repair

Before failing on JSON parse errors, the system attempts repairs:
- Remove trailing commas
- Balance missing brackets
- Remove control characters

### Chunk Failures

If a chunk fails to process:
- Error is logged
- Processing continues with next chunk
- Zero entities/relationships counted for failed chunk

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PROFILE` | Profile name to load | `generic` |
| `NEO4J_URI` | Neo4j connection URI | - |
| `NEO4J_USER` | Neo4j username | - |
| `NEO4J_PASSWORD` | Neo4j password | - |
| `OLLAMA_BASE_URL` | Ollama API URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama model name | `qwen2.5:14b-instruct` |

### Chunking Config (`config.py`)

```python
CHUNK_SIZE = 2500     # Characters per chunk
CHUNK_OVERLAP = 450   # Overlap between chunks (~18%)
```

## Profile Structure

Profiles are loaded from `profiles/<name>.json`:

```json
{
  "name": "fraud",
  "description": "Analyze fraud cases...",
  "ingestion": {
    "system_context": "You are analyzing a fraud investigation...",
    "entity_definitions": {
      "Person": {
        "color": "#F97316",
        "description": "Individual involved in the case"
      },
      "SuspiciousTransaction": {
        "color": "#EF4444",
        "description": "Transaction flagged for unusual patterns"
      }
    },
    "temperature": 1.0
  }
}
```

**Note**: `entity_types`, `relationship_examples`, and `relationship_types` are present in profiles for backwards compatibility but are **not used** in the new extraction system.

## Usage Example

```python
from ingestion import ingest_document

result = ingest_document(
    text="Document content here...",
    doc_name="financial_report.pdf",
    doc_metadata={"case_id": "CASE-001", "source_type": "pdf"},
    log_callback=lambda msg: print(f"[LOG] {msg}")
)

print(result)
# {
#   "status": "complete",
#   "document": "financial_report.pdf",
#   "chunks": 15,
#   "entities_processed": 42,
#   "relationships_processed": 28,
#   "summaries_generated": 42,
#   "locations_geocoded": 5,
#   "embedding_stored": True
# }
```

## Data Flow Summary

```
Document Text
    │
    ▼
┌─────────────┐
│  Chunking   │ ──► Page markers stripped (retained in metadata)
└─────────────┘
    │
    ▼
┌─────────────┐
│  Phase 1:   │ ──► Entities + Candidate Relationships
│  Extraction │     (AI has full freedom on types)
└─────────────┘
    │
    ▼
┌─────────────┐
│  Phase 2a:  │ ──► Resolved entities, key mapping
│  Resolution │     (exact → fuzzy → type check → batch LLM)
└─────────────┘
    │
    ▼
┌─────────────┐
│  Phase 2b:  │ ──► Relationships with remapped keys
│  Relations  │     (guaranteed valid entity references)
└─────────────┘
    │
    ▼
┌─────────────┐
│  Post-Proc  │ ──► Summaries, geocoding, embeddings
└─────────────┘
    │
    ▼
Neo4j Graph + ChromaDB Vector Store
```
