# LLM Configuration Guide

The system has **TWO separate LLM configurations** for different purposes:

## 1. Ingestion Pipeline Configuration (Document Processing)

**Location:** `ingestion/scripts/config.py` or `.env` file

**For Document Ingestion:**
- Set `OLLAMA_MODEL` in your `.env` file:
  ```env
  OLLAMA_MODEL=qwen2.5:14b-instruct
  ```

- OR edit `ingestion/scripts/config.py` line 35:
  ```python
  OLLAMA_MODEL = os.getenv("OLLAMA_MODEL") or "qwen2.5:14b-instruct"
  ```

**Used for:**
- Entity extraction from documents
- Entity disambiguation
- Summary generation
- Relationship extraction

## 2. Backend LLM Service Configuration (Chat/Assistant)

**Location:** `.env` file OR UI settings

**For Chat/AI Assistant:**

**Option A: Via `.env` file**
```env
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:14b-instruct
```

**Option B: Via UI (Recommended)**
1. Open the AI Assistant
2. Click the settings icon (⚙️) in the header
3. Select provider (Ollama/OpenAI)
4. Select model from dropdown
5. Click "Apply"

**Used for:**
- Chat/AI assistant queries
- RAG (Retrieval Augmented Generation)
- Question answering
- Cypher query generation

## Important Notes

- **These are SEPARATE configurations** - changing one doesn't affect the other
- For ingestion, use `OLLAMA_MODEL` in `.env` or edit `ingestion/scripts/config.py`
- For chat/assistant, use `LLM_PROVIDER` and `LLM_MODEL` in `.env` OR the UI
- The UI settings for chat/assistant override the `.env` file for that session
- You can use different models for ingestion vs chat if desired

## Current Defaults

**Ingestion:** `qwen2.5:14b-instruct` (in `ingestion/scripts/config.py`)
**Chat/Assistant:** `openai` → `gpt-4o` (in `backend/config.py`, or set via UI)
