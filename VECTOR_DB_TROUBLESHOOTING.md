# Vector Database Troubleshooting Guide

## Issue: "Vector search unavailable" after deployment

If you see "Vector search unavailable" when using the AI assistant, but ingestion appears to embed documents successfully, this guide will help you diagnose and fix the issue.

## Root Cause

The backend service uses a global `embedding_service` singleton that initializes when the backend starts. If this initialization fails, the vector search will be disabled even though ingestion (which creates its own EmbeddingService instance) works.

## Diagnostic Steps

### 1. Check Backend Startup Logs

Look for these messages in your backend startup logs:

```
[Embedding] Warning: Could not initialize embedding service: <error>
[Embedding] Vector search will be disabled until configuration is fixed
```

The error message will tell you what's wrong.

### 2. Common Issues and Fixes

#### Issue: Missing OPENAI_API_KEY (if using OpenAI embeddings)

**Symptoms:**
- Error: "OPENAI_API_KEY not set in environment variables"
- Ingestion might work if you provide API key later, but backend won't

**Fix:**
```bash
export OPENAI_API_KEY="your-api-key-here"
# Or add to .env file:
echo "OPENAI_API_KEY=your-api-key-here" >> .env
```

**Then restart the backend server.**

#### Issue: Wrong Embedding Provider Configuration

**Symptoms:**
- Error about unsupported provider or model not found
- Ingestion uses profile config, backend uses global config

**Fix:**
Check your `.env` file or environment variables:
```bash
# If using OpenAI:
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

# If using Ollama:
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=qwen3-embedding:4b  # or another Ollama embedding model
```

**Then restart the backend server.**

#### Issue: Ollama Not Running (if using Ollama embeddings)

**Symptoms:**
- Error about connection refused or Ollama not available
- Ingestion might work if Ollama is running when ingestion runs

**Fix:**
```bash
# Start Ollama (if using Docker):
docker run -d -p 11434:11434 --name ollama ollama/ollama

# Or if installed locally, ensure it's running:
ollama serve
```

**Then restart the backend server.**

#### Issue: Embedding Dimension Mismatch

**Symptoms:**
- Error: "Embedding dimension X does not match collection dimensionality Y"
- Documents were embedded with one model, backend uses different model

**Fix:**
1. Check which embedding model was used during ingestion (check ingestion logs)
2. Ensure backend uses the same model:
   ```bash
   EMBEDDING_PROVIDER=openai  # or ollama
   EMBEDDING_MODEL=text-embedding-3-small  # match ingestion model
   ```
3. If models must differ, delete ChromaDB and re-embed:
   ```bash
   rm -rf data/chromadb
   # Then re-run ingestion
   ```

**Then restart the backend server.**

### 3. Verify Configuration

Check that your environment variables are set correctly:

```bash
# For OpenAI:
echo $OPENAI_API_KEY  # Should not be empty
echo $EMBEDDING_PROVIDER  # Should be "openai"
echo $EMBEDDING_MODEL  # Should be "text-embedding-3-small" or similar

# For Ollama:
echo $EMBEDDING_PROVIDER  # Should be "ollama"
echo $EMBEDDING_MODEL  # Should match an available Ollama model
curl http://localhost:11434/api/tags  # Should return list of available models
```

### 4. Verify Backend Can Access Vector DB

After fixing configuration and restarting, check backend logs for:

```
[Embedding] Using OpenAI model: text-embedding-3-small
# OR
[Embedding] Using Ollama model: qwen3-embedding:4b
```

If you don't see this, the embedding service still isn't initializing correctly.

### 5. Test Vector Search

1. Ensure documents have been ingested and embedded
2. Try using the AI assistant
3. Check backend logs for:
   ```
   [RAG] Vector DB contains X documents
   [RAG] Generated query embedding with Y dimensions
   [RAG] Vector search returned Z documents
   ```

If you see "Vector database not available" or "Vector search unavailable", the embedding service is still not initialized.

## Why Ingestion Works But Backend Doesn't

- **Ingestion** creates a new `EmbeddingService` instance dynamically using the profile's LLM configuration
- **Backend** uses a global singleton `embedding_service` that initializes at startup using global configuration

If the global configuration is wrong or missing API keys at startup, the singleton will be `None`, disabling vector search in the backend even though ingestion works.

## Quick Fix Checklist

1. ✅ Check backend startup logs for embedding service initialization errors
2. ✅ Ensure `OPENAI_API_KEY` is set (if using OpenAI)
3. ✅ Ensure `EMBEDDING_PROVIDER` matches your setup (openai or ollama)
4. ✅ Ensure `EMBEDDING_MODEL` is correct and available
5. ✅ Ensure Ollama is running (if using Ollama)
6. ✅ Ensure embedding model matches between ingestion and backend
7. ✅ Restart the backend server after fixing configuration
8. ✅ Verify backend logs show embedding service initialized successfully

## Still Having Issues?

1. Check backend logs for the exact error message
2. Verify your `.env` file is in the correct location (`backend/.env` or project root)
3. Ensure environment variables are exported before starting the backend
4. Check that the embedding model exists and is accessible
5. Verify ChromaDB data directory permissions (`data/chromadb`)
