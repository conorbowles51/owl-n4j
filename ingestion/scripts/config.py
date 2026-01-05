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
# Chunking Configuration
# ---------------------------------------------------------------------------

# Characters per chunk (suitable for local Ollama with ~8K context)
CHUNK_SIZE = 1000

# Overlap between chunks to maintain context continuity
CHUNK_OVERLAP = 200

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
