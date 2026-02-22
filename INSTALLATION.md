# Owl Investigation Console — Installation Guide

Complete setup instructions for deploying the Owl Investigation Console with all services and dependencies.

---

## Architecture Overview

```
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│   Frontend     │    │   Backend      │    │   Databases    │
│   React/Vite   │───▶│   FastAPI      │───▶│   Neo4j 5      │
│   Port 5173    │    │   Port 8000    │    │   Port 7687    │
└────────────────┘    │                │    ├────────────────┤
                      │                │───▶│   PostgreSQL   │
                      │                │    │   Port 5432    │
                      │                │    ├────────────────┤
                      │                │───▶│   ChromaDB     │
                      │                │    │   (embedded)   │
                      └───────┬────────┘    └────────────────┘
                              │
                      ┌───────┴────────┐
                      │   LLM Layer    │
                      │   OpenAI API   │
                      │   — or —       │
                      │   Ollama local │
                      └────────────────┘
```

---

## Prerequisites

| Requirement         | Minimum        | Recommended     |
|---------------------|----------------|-----------------|
| Python              | 3.11+          | 3.13            |
| Node.js             | 18+            | 20 LTS          |
| RAM                 | 16 GB          | 32 GB+          |
| CPU                 | 4 cores        | 8+ cores        |
| Disk                | 10 GB free     | 50 GB+          |
| GPU (Ollama only)   | —              | NVIDIA w/ CUDA  |

---

## 1. Clone & Environment Setup

```bash
git clone <repo-url> owl-n4j
cd owl-n4j

# Create Python virtual environment
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
```

---

## 2. Database Services

### Option A — Docker Compose (recommended)

Start Neo4j and PostgreSQL with a single command:

```bash
docker compose up -d
```

This launches:

| Service    | Container   | Port(s)            | Credentials              |
|------------|-------------|--------------------|--------------------------|
| Neo4j 5    | `owl-n4j`   | 7474 (HTTP), 7687 (Bolt) | `neo4j` / `testpassword` |
| PostgreSQL | `owl-pg`    | 5432               | `owl_us` / `owl_pw` / DB: `owl_db` |

### Option B — Manual Installation

**Neo4j:**
- Download from https://neo4j.com/download/ (Community Edition v5+)
- Enable APOC plugin: set `NEO4J_PLUGINS=["apoc"]`
- Start and change default password at http://localhost:7474

**PostgreSQL:**
- Install PostgreSQL 16+ via your package manager
- Create database: `createdb owl_db`

### ChromaDB

No setup required — ChromaDB runs embedded within the backend process. Data is stored at `data/chromadb/` by default.

---

## 3. Environment Configuration

Copy the example and fill in your values:

```bash
cp .env.example .env
```

Edit `.env` with the full configuration:

```env
# ─── Database ─────────────────────────────────────────────
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=testpassword

DATABASE_URL=postgresql://owl_us:owl_pw@localhost:5432/owl_db

# ─── LLM Provider ────────────────────────────────────────
# Choose "openai" or "ollama"
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o

# OpenAI (required if LLM_PROVIDER=openai or for geo rescan/insights)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Ollama (required if LLM_PROVIDER=ollama)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:32b-instruct

# ─── Embeddings ───────────────────────────────────────────
# Defaults to same provider as LLM_PROVIDER if not set
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

# ─── Vector DB / RAG ─────────────────────────────────────
CHROMADB_PATH=data/chromadb
VECTOR_SEARCH_ENABLED=true
VECTOR_SEARCH_TOP_K=50
HYBRID_FILTERING_ENABLED=true
CHUNK_SEARCH_ENABLED=true
CHUNK_SEARCH_TOP_K=50
ENTITY_SEARCH_ENABLED=true
ENTITY_SEARCH_TOP_K=50
CONTEXT_TOKEN_BUDGET=80000

# ─── Chunking ────────────────────────────────────────────
CHUNK_SIZE=8000
CHUNK_OVERLAP=1600

# ─── Ingestion ───────────────────────────────────────────
MAX_INGESTION_WORKERS=4

# ─── Media Processing (optional) ─────────────────────────
IMAGE_PROVIDER=tesseract          # "tesseract" (local OCR) or "openai" (GPT-4 Vision)
TESSERACT_LANG=eng                # OCR language(s), e.g. "eng+spa"
OPENAI_VISION_MODEL=gpt-4o       # Model for image/video frame analysis
VIDEO_FRAME_INTERVAL=30           # Seconds between extracted frames
VIDEO_MAX_FRAMES=50               # Max frames per video
WHISPER_MODEL_SIZE=base           # tiny, base, small, medium, large
AUDIO_LANGUAGE=                   # Blank = auto-detect

# ─── Authentication ──────────────────────────────────────
AUTH_USERNAME=admin
AUTH_PASSWORD=owlinvestigates
AUTH_SECRET_KEY=change-this-to-a-random-secret
AUTH_ALGORITHM=HS256
AUTH_TOKEN_EXPIRE_MINUTES=1440

# ─── API ─────────────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

> **Note for Ollama users:** If running Ollama with models that have smaller context windows (< 32K), reduce `VECTOR_SEARCH_TOP_K`, `CHUNK_SEARCH_TOP_K`, `ENTITY_SEARCH_TOP_K` to `15` and `CONTEXT_TOKEN_BUDGET` to `15000`.

---

## 4. Backend Installation

```bash
# Install Python dependencies
pip install -r backend/requirements.txt
```

### System-Level Dependencies

Some features require native libraries installed on the host OS:

#### WeasyPrint (financial PDF export)

```bash
# macOS
brew install pango libffi

# Ubuntu / Debian
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 libffi-dev libgobject-2.0-0

# Fedora / RHEL
sudo dnf install -y pango gdk-pixbuf2 libffi-devel
```

#### Tesseract OCR (image text extraction — optional)

Only needed if `IMAGE_PROVIDER=tesseract`.

```bash
# macOS
brew install tesseract

# Ubuntu / Debian
sudo apt-get install -y tesseract-ocr

# Fedora / RHEL
sudo dnf install -y tesseract
```

#### FFmpeg (video processing — optional)

Only needed if ingesting video files.

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt-get install -y ffmpeg

# Fedora / RHEL
sudo dnf install -y ffmpeg
```

### Run Database Migrations

```bash
cd backend
alembic upgrade head
```

### Start the Backend

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 5. Frontend Installation

```bash
cd frontend
npm install
npm run dev
```

The app will be available at **http://localhost:5173**.

For a production build:

```bash
npm run build
npm run preview
```

---

## 6. Ollama Setup (Optional — Local LLM)

If you prefer local models instead of OpenAI:

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull models
ollama pull qwen2.5:32b-instruct    # Recommended
ollama pull qwen3-embedding:4b      # For local embeddings

# Verify
ollama list
```

Then set in `.env`:

```env
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:32b-instruct
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=qwen3-embedding:4b
```

---

## 7. Verification

### Backend Health Check

```bash
curl http://localhost:8000/api/health
```

### Full Stack Checklist

| Check | How |
|-------|-----|
| Backend API | `curl http://localhost:8000/api/health` returns `200` |
| Neo4j connected | No connection errors in backend logs |
| PostgreSQL connected | Backend starts without DB errors |
| Frontend loads | Open http://localhost:5173 in browser |
| Login works | Use credentials from `AUTH_USERNAME` / `AUTH_PASSWORD` |
| LLM responds | Open AI Chat panel and send a test message |
| Graph view | Navigate to Graph tab — should render (empty if no data) |
| Financial view | Navigate to Financial tab — table and charts render |
| Map view | Navigate to Map tab — Leaflet map renders |

---

## 8. Docker Deployment (Full Stack)

If deploying everything via Docker, update `backend/Dockerfile` to include system dependencies:

```dockerfile
FROM python:3.11-slim

# System dependencies for WeasyPrint, Tesseract, FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf2.0-0 \
    libffi-dev libgobject-2.0-0 \
    tesseract-ocr \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Then build and run:

```bash
docker compose up -d --build
```

---

## 9. Feature-Specific Notes

### AI Geo Rescan (Map View)

- Requires `OPENAI_API_KEY` — uses GPT-5.2 for location extraction
- Geocoding uses OpenStreetMap Nominatim (free, rate-limited to 1 req/sec)
- Access via the "AI Rescan Locations" button in the Map view

### Financial Sub-Transactions

- Access via the **⋯** (three-dot) menu on any transaction row
- "Group Sub-Transactions" opens a modal to link child transactions
- Parent rows show a ▶/▼ expand toggle to reveal children

### AI Insights

- Access via the Insights panel in the workspace
- Generates LLM-powered insights for top entities in a case
- Requires `OPENAI_API_KEY`

### Media Ingestion

- **Images:** Set `IMAGE_PROVIDER=tesseract` for local OCR or `IMAGE_PROVIDER=openai` for GPT-4 Vision
- **Video:** Requires FFmpeg installed. Extracts frames at configurable intervals
- **Audio:** Requires `openai-whisper` Python package. Transcribes audio files via Whisper

---

## 10. Troubleshooting

### Connection Errors

| Error | Fix |
|-------|-----|
| Neo4j "Connection refused" | Ensure Neo4j is running: `docker compose ps` or check service status |
| Neo4j "Authentication failed" | Verify `NEO4J_USER` / `NEO4J_PASSWORD` in `.env` match the database |
| PostgreSQL "Connection refused" | Ensure Postgres is running and `DATABASE_URL` is correct |
| "ChromaDB not initialized" | Ensure `CHROMADB_PATH` directory is writable; it auto-creates on first use |

### LLM Errors

| Error | Fix |
|-------|-----|
| "Invalid API key" | Check `OPENAI_API_KEY` in `.env` |
| "Rate limit exceeded" | Wait and retry, or reduce `MAX_INGESTION_WORKERS` |
| Ollama "Connection refused" | Start Ollama: `ollama serve` |
| Ollama "Model not found" | Pull the model: `ollama pull <model-name>` |
| Ollama read timeout | Large models take time to load on first use — wait and retry |

### WeasyPrint / PDF Errors

| Error | Fix |
|-------|-----|
| "cannot load library libgobject" | Install system libs: `brew install pango` (macOS) or `apt-get install libgobject-2.0-0` (Linux) |
| PDF export returns 500 | Check backend logs for missing native library details |

### Media Processing Errors

| Error | Fix |
|-------|-----|
| "tesseract not found" | Install Tesseract: `brew install tesseract` or `apt-get install tesseract-ocr` |
| "ffmpeg not found" | Install FFmpeg: `brew install ffmpeg` or `apt-get install ffmpeg` |
| "whisper not installed" | `pip install openai-whisper` (requires ~1 GB download for model weights) |

---

## 11. Updating

To update to the latest version:

```bash
git pull origin main

# Backend
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && alembic upgrade head && cd ..

# Frontend
cd frontend && npm install && npm run build && cd ..

# Restart services
# (restart your backend process / Docker containers)
```
