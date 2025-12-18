"""
Evidence Storage Service

Handles persistent storage of uploaded evidence files and their processing status.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from config import BASE_DIR


# BASE_DIR in config.py already points to the project root (e.g. /.../owl-n4j)
# Store metadata under <project>/data and binary files under <project>/ingestion/data
DATA_DIR = BASE_DIR / "data"
STORAGE_FILE = DATA_DIR / "evidence.json"

# Physical file storage root – reuse ingestion data directory so ingest_data.py can read files
EVIDENCE_ROOT_DIR = BASE_DIR / "ingestion" / "data"


def ensure_dirs():
    """Ensure all storage directories exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_ROOT_DIR.mkdir(parents=True, exist_ok=True)


def _load_evidence() -> Dict[str, dict]:
    """Load evidence records from JSON file."""
    ensure_dirs()
    if not STORAGE_FILE.exists():
        return {}
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error loading evidence storage: {e}")
        return {}


def _save_evidence(records: Dict[str, dict]) -> None:
    """Persist evidence records to JSON file (atomic write)."""
    ensure_dirs()
    tmp = STORAGE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    tmp.replace(STORAGE_FILE)


def _compute_sha256(data: bytes) -> str:
    """Compute SHA256 hash of given bytes."""
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


class EvidenceStorage:
    """Service for managing evidence file metadata and status."""

    def __init__(self) -> None:
        self._records: Dict[str, dict] = _load_evidence()

    # ------------- Basic accessors -------------

    def reload(self) -> None:
        """Reload evidence records from disk."""
        self._records = _load_evidence()

    def _persist(self) -> None:
        _save_evidence(self._records)

    def get_all(self) -> List[dict]:
        """Return all evidence records as a list."""
        return list(self._records.values())

    def get(self, evidence_id: str) -> Optional[dict]:
        """Get a single evidence record by id."""
        return self._records.get(evidence_id)

    # ------------- Query helpers -------------

    def list_files(
        self,
        case_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[dict]:
        """List evidence files, optionally filtered by case_id and status."""
        results = []
        for rec in self._records.values():
            if case_id and rec.get("case_id") != case_id:
                continue
            if status and rec.get("status") != status:
                continue
            results.append(rec)
        # Sort newest first
        results.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return results

    def find_by_hash(self, sha256: str) -> Optional[dict]:
        """Find first record matching a given hash."""
        for rec in self._records.values():
            if rec.get("sha256") == sha256:
                return rec
        return None

    # ------------- Mutating operations -------------

    def add_files(
        self,
        case_id: str,
        files: List[dict],
    ) -> List[dict]:
        """
        Add one or more uploaded files.

        Args:
            case_id: Associated case ID
            files: List of dicts:
                {
                  "original_filename": str,
                  "stored_path": Path,
                  "content": bytes,
                  "size": int,
                }

        Returns:
            List of evidence records that were created.
        """
        ensure_dirs()
        created_records: List[dict] = []
        now = datetime.now().isoformat()

        for file_info in files:
            original_filename = file_info["original_filename"]
            stored_path: Path = file_info["stored_path"]
            content: bytes = file_info["content"]
            size: int = file_info["size"]

            sha256 = _compute_sha256(content)
            duplicate_rec = self.find_by_hash(sha256)

            evidence_id = f"ev_{sha256[:16]}"
            # Ensure uniqueness even if same hash used for id in multiple cases
            suffix = 1
            while evidence_id in self._records:
                evidence_id = f"ev_{sha256[:12]}_{suffix}"
                suffix += 1

            status = "unprocessed"
            duplicate_of = None
            if duplicate_rec:
                status = "duplicate"
                duplicate_of = duplicate_rec.get("id")

            record = {
                "id": evidence_id,
                "case_id": case_id,
                "original_filename": original_filename,
                "stored_path": str(stored_path),
                "size": size,
                "sha256": sha256,
                "status": status,  # unprocessed | processing | processed | duplicate | failed
                "duplicate_of": duplicate_of,
                "created_at": now,
                "processed_at": None,
                "last_error": None,
            }

            self._records[evidence_id] = record
            created_records.append(record)

        self._persist()
        return created_records

    def mark_processing(self, evidence_ids: List[str]) -> None:
        """Mark selected evidence as 'processing'."""
        now = datetime.now().isoformat()
        for evid in evidence_ids:
            rec = self._records.get(evid)
            if not rec:
                continue
            if rec.get("status") in ("processed", "processing"):
                continue
            rec["status"] = "processing"
            rec["last_error"] = None
            rec["processed_at"] = None
        self._persist()

    def mark_processed(
        self,
        evidence_ids: List[str],
        error: Optional[str] = None,
    ) -> None:
        """Mark selected evidence as processed or failed."""
        now = datetime.now().isoformat()
        for evid in evidence_ids:
            rec = self._records.get(evid)
            if not rec:
                continue
            if error:
                rec["status"] = "failed"
                rec["last_error"] = error
            else:
                # Preserve 'duplicate' label for duplicate records so the UI
                # continues to show them as duplicates even after processing.
                # Non-duplicate records are marked as 'processed'.
                if rec.get("status") != "duplicate":
                    rec["status"] = "processed"
                rec["last_error"] = None
            rec["processed_at"] = now
        self._persist()


# Singleton instance
evidence_storage = EvidenceStorage()


