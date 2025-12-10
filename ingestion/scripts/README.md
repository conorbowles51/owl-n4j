# Fraud Investigation Ingestion Pipeline

A modular pipeline for ingesting documents into a Neo4j knowledge graph with entity learning and resolution.

## Features

- **Entity Learning**: Entities are found, matched, and enriched across documents (not just duplicated)
- **Fuzzy Matching + LLM Disambiguation**: Exact key match first, then fuzzy search with LLM decision
- **Inline Summary Updates**: Summaries regenerate after each entity update
- **Document Chunking**: Full document processing with configurable chunk size and overlap
- **Rich Notes**: Plain text notes accumulate per-document observations

## Module Structure

```
scripts/
├── config.py              # Environment loading, constants, entity/relationship types
├── llm_client.py          # Ollama API: extraction, disambiguation, summary generation
├── neo4j_client.py        # Neo4j driver, queries, upserts
├── entity_resolution.py   # Key normalisation, exact/fuzzy matching, disambiguation
├── chunking.py            # Text chunking with sentence-aware boundaries
├── ingestion.py           # Core orchestration logic
├── text_ingestion.py      # .txt file handling
├── pdf_ingestion.py       # .pdf file handling
├── ingest_data.py         # CLI entry point
└── requirements.txt       # Python dependencies
```

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r scripts/requirements.txt
   ```

2. **Configure `.env`** in your project root:
   ```env
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your_password

   LLM_BASE_URL=http://localhost:11434
   LLM_MODEL=llama3
   ```

3. **Place documents** in `data/` directory (at project root)

## Usage

### Ingest all files in data/
```bash
python scripts/ingest_data.py
```

### Ingest a specific file
```bash
python scripts/ingest_data.py --file path/to/document.pdf
```

### Clear database first
```bash
python scripts/ingest_data.py --clear
```

### Custom data directory
```bash
python scripts/ingest_data.py --data-dir /path/to/documents
```

## Entity Schema

Each entity has:
- **id**: UUID (immutable, internal)
- **key**: Normalised identifier for deduplication (e.g., "john-smith")
- **name**: Human-readable label
- **notes**: Accumulated observations per document:
  ```
  [document1.pdf]
  John appears as director of Emerald Imports Ltd.
  
  [document2.txt]
  John authorises transfer of €50,000 to ACC-003.
  ```
- **summary**: AI-generated current understanding (refreshed inline)

## How Resolution Works

1. **Exact Match**: Check if entity key already exists in graph
2. **Fuzzy Search**: If no exact match, search by name similarity
3. **LLM Disambiguation**: Ask LLM if fuzzy matches are the same entity
4. **Create or Update**: Either enrich existing entity or create new one
5. **Summary Refresh**: Regenerate summary with all accumulated notes

## Chunking Configuration

In `config.py`:
```python
CHUNK_SIZE = 2500    # Characters per chunk
CHUNK_OVERLAP = 200  # Overlap between chunks
```

Adjust based on your Ollama model's context window.

## Extending

- **New file types**: Create a new `*_ingestion.py` module following the pattern of `pdf_ingestion.py`
- **New entity types**: Add to `ENTITY_TYPES` in `config.py`
- **New relationship types**: Add to `RELATIONSHIP_TYPES` in `config.py`
- **Custom prompts**: Modify `llm_client.py` extraction/disambiguation prompts
