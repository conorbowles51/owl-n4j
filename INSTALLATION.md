# Installation Instructions

This document provides step-by-step instructions for setting up the Owl Investigation Console with all its dependencies.

## Prerequisites

- Python 3.8 or higher
- Node.js 16 or higher (for frontend)
- Neo4j database (running locally or accessible)
- Ollama (optional, for local LLM support)
- OpenAI API key (optional, for OpenAI models)

## Backend Installation

### 1. Create a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Ollama (Optional - for Local LLM)

If you want to use local LLM models via Ollama:

1. **Download and Install Ollama:**
   - Visit https://ollama.ai/download
   - Download and install Ollama for your operating system
   - Start the Ollama service

2. **Pull Required Models:**
   ```bash
   # Default model (recommended)
   ollama pull qwen2.5:32b-instruct
   
   # Alternative models (optional)
   ollama pull qwen2.5:14b-instruct
   ollama pull qwen2.5:7b-instruct
   ollama pull llama3:70b
   ollama pull llama3:8b
   ```

3. **Verify Ollama is Running:**
   ```bash
   ollama list
   ```

### 4. Configure Environment Variables

Create a `.env` file in the project root with the following variables:

```env
# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# LLM Configuration
LLM_PROVIDER=ollama  # or "openai"
LLM_MODEL=qwen2.5:32b-instruct  # or your preferred model
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:32b-instruct

# OpenAI Configuration (if using OpenAI)
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o  # or gpt-4-turbo, gpt-3.5-turbo

# Embedding Configuration
# Note: If EMBEDDING_PROVIDER is not set, it automatically matches LLM_PROVIDER
# If EMBEDDING_MODEL is not set, defaults are:
#   - OpenAI: text-embedding-3-small
#   - Ollama: nomic-embed-text
EMBEDDING_PROVIDER=openai  # Optional: "openai" or "ollama" (defaults to LLM_PROVIDER)
EMBEDDING_MODEL=text-embedding-3-small  # Optional: defaults based on provider
OPENAI_API_KEY=your_openai_api_key  # Required if using OpenAI (for LLM or embeddings)

# Vector DB Configuration
CHROMADB_PATH=data/chromadb

# RAG Configuration
VECTOR_SEARCH_ENABLED=true
VECTOR_SEARCH_TOP_K=10
HYBRID_FILTERING_ENABLED=true

# Ingestion Configuration
CHUNK_SIZE=2500
CHUNK_OVERLAP=200

# Authentication
AUTH_USERNAME=admin
AUTH_PASSWORD=owlinvestigates
AUTH_SECRET_KEY=supersecretchange
AUTH_ALGORITHM=HS256
AUTH_TOKEN_EXPIRE_MINUTES=1440

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

### 5. Start the Backend Server

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend Installation

### 1. Install Node Dependencies

```bash
cd frontend
npm install
```

### 2. Start the Development Server

```bash
npm run dev
```

The frontend will be available at `http://localhost:5173`

## Database Setup

### Neo4j

1. **Install Neo4j:**
   - Download from https://neo4j.com/download/
   - Or use Docker: `docker run -p 7474:7474 -p 7687:7687 neo4j:latest`

2. **Start Neo4j:**
   - Default web interface: http://localhost:7474
   - Default credentials: neo4j/neo4j (change on first login)

3. **Update `.env`** with your Neo4j credentials

### ChromaDB (Vector Database)

ChromaDB is automatically initialized when the backend starts. The database is stored at `data/chromadb` (or the path specified in `CHROMADB_PATH`).

No additional setup is required - the backend will create the database on first use.

## Verification

### Test Backend

1. Check if the API is running:
   ```bash
   curl http://localhost:8000/api/health
   ```

2. Test Ollama connection (if using Ollama):
   ```bash
   python backend/scripts/test_ollama_simple.py
   ```

### Test Frontend

1. Open http://localhost:5173 in your browser
2. Log in with credentials from `.env`
3. Verify you can access the graph view

## Troubleshooting

### Ollama Connection Issues

- **Error: "Connection refused"**: Make sure Ollama is running (`ollama serve` or start the Ollama application)
- **Error: "Model not found"**: Pull the model first (`ollama pull qwen2.5:32b-instruct`)
- **Error: "Read timeout"**: Large models may take time to load. The timeout has been increased to 10 minutes, but you may need to wait for the model to load into memory on first use.

### Neo4j Connection Issues

- **Error: "Connection refused"**: Ensure Neo4j is running and accessible at the URI in `.env`
- **Error: "Authentication failed"**: Check your `NEO4J_USER` and `NEO4J_PASSWORD` in `.env`

### OpenAI API Issues

- **Error: "Invalid API key"**: Verify your `OPENAI_API_KEY` in `.env` is correct
- **Error: "Rate limit exceeded"**: You may have hit OpenAI's rate limits. Wait a moment and try again.

### Vector DB Issues

- **Error: "ChromaDB not initialized"**: The database will be created automatically on first use. Ensure the `CHROMADB_PATH` directory is writable.

## Model Selection

The system supports both Ollama (local) and OpenAI (remote) models. You can:

1. **Select in UI**: Use the Settings icon in the AI Assistant or Profile Editor to choose your provider and model
2. **Configure in `.env`**: Set `LLM_PROVIDER` and `LLM_MODEL` for default behavior

### Available Models

**Ollama Models:**
- `qwen2.5:32b-instruct` (Default, recommended for best quality)
- `qwen2.5:14b-instruct` (Good balance)
- `qwen2.5:7b-instruct` (Faster, lower resource usage)
- `llama3:70b` (Very large, high quality)
- `llama3:8b` (Efficient)

**OpenAI Models:**
- `gpt-4o` (Latest, best quality)
- `gpt-4-turbo` (High quality)
- `gpt-3.5-turbo` (Cost-effective)

## System Requirements

### Minimum Requirements

- **CPU**: 4 cores
- **RAM**: 16GB (8GB for smaller models, 32GB+ recommended for qwen2.5:32b-instruct)
- **Storage**: 10GB free space
- **Network**: Internet connection (for OpenAI or downloading Ollama models)

### Recommended Requirements

- **CPU**: 8+ cores
- **RAM**: 32GB+ (for large models like qwen2.5:32b-instruct)
- **Storage**: 50GB+ free space (for models and data)
- **GPU**: NVIDIA GPU with CUDA support (optional, but significantly speeds up Ollama models)

## Next Steps

After installation:

1. **Create your first case** in the Evidence Processing view
2. **Upload documents** for processing
3. **Select an LLM profile** that matches your investigation type
4. **Start asking questions** in the AI Assistant
5. **Explore the graph** to visualize relationships

For more information, see the main README.md or USER_GUIDE.md files.

