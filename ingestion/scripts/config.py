"""
Configuration module - loads environment variables and defines constants.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    load_dotenv()

# ---------------------------------------------------------------------------
# Neo4j Configuration
# ---------------------------------------------------------------------------

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# ---------------------------------------------------------------------------
# LLM Configuration (OpenAI)
# ---------------------------------------------------------------------------

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL") or "qwen2.5:7b"
# ---------------------------------------------------------------------------
# Parallel Processing Configuration
# ---------------------------------------------------------------------------

# Maximum number of files to process in parallel during ingestion
MAX_INGESTION_WORKERS = int(os.getenv("MAX_INGESTION_WORKERS", "4"))

# ---------------------------------------------------------------------------
# Image Processing Configuration
# ---------------------------------------------------------------------------

# Provider for image analysis: "tesseract" (local OCR) or "openai" (GPT-4 Vision)
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "tesseract")

# Tesseract OCR language(s) - e.g. "eng", "eng+spa"
TESSERACT_LANG = os.getenv("TESSERACT_LANG", "eng")

# OpenAI Vision model for image/video frame analysis
OPENAI_VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")

# ---------------------------------------------------------------------------
# Video Processing Configuration
# ---------------------------------------------------------------------------

# FFmpeg binary paths (must be installed system-wide)
FFMPEG_CMD = os.getenv("FFMPEG_CMD", "ffmpeg")
FFPROBE_CMD = os.getenv("FFPROBE_CMD", "ffprobe")

# Key frame extraction interval in seconds
VIDEO_FRAME_INTERVAL = int(os.getenv("VIDEO_FRAME_INTERVAL", "30"))

# Maximum number of frames to extract per video
VIDEO_MAX_FRAMES = int(os.getenv("VIDEO_MAX_FRAMES", "50"))

# ---------------------------------------------------------------------------
# Audio Standalone Processing Configuration
# ---------------------------------------------------------------------------

# Whisper model size for standalone audio transcription (tiny, base, small, medium, large)
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")

# Language for audio transcription (None = auto-detect)
AUDIO_LANGUAGE = os.getenv("AUDIO_LANGUAGE", None)

# ---------------------------------------------------------------------------
# Chunking Configuration
# ---------------------------------------------------------------------------

# Characters per chunk (optimized for faster ingestion with larger context windows)
CHUNK_SIZE = 8000

# Overlap between chunks to maintain context continuity
CHUNK_OVERLAP = 1600

# ---------------------------------------------------------------------------
# Entity Types (from schema)
# ---------------------------------------------------------------------------

ENTITY_TYPES = [
    # Core entity types
    "Person",
    "Company",
    "Account",
    "Organisation",
    "Bank",
    "Location",
    # Event/temporal types
    "Transaction",
    "Payment",
    "Communication",
    "Email",
    "PhoneCall",
    "Meeting",
    "Login",
    "Withdrawal",
    "Deposit",
    "Transfer",
    "Alert",
    "Contract",
    "Invoice",
    "AccountOpening",
    "AccountClosure",
    "Investigation",
    "Warrant",
    "Subpoena",
    "CourtFiling",
    "PropertyTransaction",
    "TravelEvent",
    "CompanyRegistration",
    "LicenseIssuance",
    "Audit",
    # Fallback
    "Other",
]

# ---------------------------------------------------------------------------
# Relationship Types (from schema)
# ---------------------------------------------------------------------------

RELATIONSHIP_TYPES = [
    "OWNS_ACCOUNT",
    "OWNS_COMPANY",
    "TRANSFERRED_TO",
    "MENTIONED_IN",
    "ASSOCIATED_WITH",
    "RELATED_TO",
    "PART_OF_CASE",
    "CALLED",
    "EMAILED",
    "MET_WITH",
    "ATTENDED",
    "SIGNED",
    "TRIGGERED",
    "ISSUED_TO",
    "RECEIVED_FROM",
    "WORKS_FOR",
    "DIRECTOR_OF",
    "SHAREHOLDER_OF",
]
