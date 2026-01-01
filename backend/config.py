"""
Configuration for the Investigation Console backend.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    load_dotenv()

print ("openai key", os.getenv("OPENAI_API_KEY"))
# Neo4j Configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# LLM / Ollama / OpenAI Configuration
OPENAI_MODEL = os.getenv("OPENAI_MODEL")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL") or "qwen2.5:32b-instruct"

# Embedding Configuration
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai").lower()  # "openai" or "ollama"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")  # OpenAI model or Ollama model name
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Required if using OpenAI

# Vector DB Configuration
CHROMADB_PATH = os.getenv("CHROMADB_PATH", "data/chromadb")  # Relative to project root

# RAG Configuration
VECTOR_SEARCH_ENABLED = os.getenv("VECTOR_SEARCH_ENABLED", "true").lower() == "true"
VECTOR_SEARCH_TOP_K = int(os.getenv("VECTOR_SEARCH_TOP_K", "10"))  # Number of documents to retrieve
HYBRID_FILTERING_ENABLED = os.getenv("HYBRID_FILTERING_ENABLED", "true").lower() == "true"

# Ingestion chunking configuration
# Keep these in sync with ingestion/scripts/config.py so the ingestion
# pipeline can safely import them from the shared `config` module.
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "2500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

# Authentication configuration
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "owlinvestigates")
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "supersecretchange")
AUTH_ALGORITHM = os.getenv("AUTH_ALGORITHM", "HS256")
AUTH_TOKEN_EXPIRE_MINUTES = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours default

# API Configuration
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
