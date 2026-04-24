"""
Evidence Storage Service

Handles persistent storage of uploaded evidence files and their processing status.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from threading import RLock

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
    """Service for managing evidence file metadata and status. Thread-safe."""

    def __init__(self) -> None:
        self._records: Dict[str, dict] = _load_evidence()
        self._lock = RLock()  # Reentrant lock for thread-safe operations
        self._migrate_records()

    def _migrate_records(self) -> None:
        """Migrate legacy records: separate 'duplicate' status into is_duplicate flag,
        and ensure is_relevant field exists."""
        changed = False
        with self._lock:
            for rec in self._records.values():
                if "is_relevant" not in rec:
                    rec["is_relevant"] = False
                    changed = True
                if "is_duplicate" not in rec:
                    if rec.get("status") == "duplicate":
                        rec["is_duplicate"] = True
                        rec["status"] = "processed" if rec.get("processed_at") else "unprocessed"
                    else:
                        rec["is_duplicate"] = bool(rec.get("duplicate_of"))
                    changed = True
            if changed:
                self._persist()

    # ------------- Basic accessors -------------

    def reload(self) -> None:
        """Reload evidence records from disk."""
        with self._lock:
            self._records = _load_evidence()

    def _persist(self) -> None:
        _save_evidence(self._records)

    def get_all(self) -> List[dict]:
        """Return all evidence records as a list."""
        with self._lock:
            return list(self._records.values())

    def get(self, evidence_id: str) -> Optional[dict]:
        """Get a single evidence record by id."""
        with self._lock:
            return self._records.get(evidence_id)

    # ------------- Query helpers -------------

    def list_files(
        self,
        case_id: Optional[str] = None,
        status: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> List[dict]:
        """List evidence files, optionally filtered by case_id, status, and owner."""
        with self._lock:
            results = []
            for rec in self._records.values():
                if case_id and rec.get("case_id") != case_id:
                    continue
                if status and rec.get("status") != status:
                    continue
                if owner and rec.get("owner") != owner:
                    continue
                results.append(rec)
            # Sort newest first
            results.sort(key=lambda r: r.get("created_at", ""), reverse=True)
            return results

    def find_by_hash(self, sha256: str) -> Optional[dict]:
        """Find first record matching a given hash."""
        with self._lock:
            for rec in self._records.values():
                if rec.get("sha256") == sha256:
                    return rec
            return None

    def find_all_by_hash(self, sha256: str) -> List[dict]:
        """Find all records matching a given hash."""
        with self._lock:
            results = []
            for rec in self._records.values():
                if rec.get("sha256") == sha256:
                    results.append(rec)
            return results

    # ------------- Mutating operations -------------

    def add_files(
        self,
        case_id: str,
        files: List[dict],
        owner: Optional[str] = None,
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
        with self._lock:
            ensure_dirs()
            created_records: List[dict] = []
            now = datetime.now().isoformat()

            for file_info in files:
                original_filename = file_info["original_filename"]
                stored_path: Path = file_info["stored_path"]
                content: bytes = file_info["content"]
                size: int = file_info["size"]

                sha256 = _compute_sha256(content)
                # Find duplicate directly to avoid double-locking
                duplicate_rec = None
                for rec in self._records.values():
                    if rec.get("sha256") == sha256:
                        duplicate_rec = rec
                        break

                evidence_id = f"ev_{sha256[:16]}"
                # Ensure uniqueness even if same hash used for id in multiple cases
                suffix = 1
                while evidence_id in self._records:
                    evidence_id = f"ev_{sha256[:12]}_{suffix}"
                    suffix += 1

                duplicate_of = None
                is_duplicate = False
                if duplicate_rec:
                    is_duplicate = True
                    duplicate_of = duplicate_rec.get("id")

                record = {
                    "id": evidence_id,
                    "case_id": case_id,
                    "owner": owner,
                    "original_filename": original_filename,
                    "stored_path": str(stored_path),
                    "size": size,
                    "sha256": sha256,
                    "status": "unprocessed",  # unprocessed | processing | processed | failed
                    "is_duplicate": is_duplicate,
                    "duplicate_of": duplicate_of,
                    "is_relevant": False,
                    "created_at": now,
                    "processed_at": None,
                    "last_error": None,
                }
                if file_info.get("relative_path") is not None:
                    record["relative_path"] = file_info["relative_path"]

                self._records[evidence_id] = record
                created_records.append(record)

            self._persist()
            return created_records

    def delete_record(self, evidence_id: str) -> Optional[dict]:
        """
        Delete an evidence record by ID. Returns the deleted record or None.
        Does NOT delete the physical file — caller is responsible for that.
        """
        with self._lock:
            rec = self._records.pop(evidence_id, None)
            if rec:
                self._persist()
            return rec

    def get_by_cellebrite_file_ids(
        self, case_id: str, file_ids: List[str]
    ) -> Dict[str, dict]:
        """
        Bulk resolve Cellebrite UFED file UUIDs to evidence records.
        Returns a dict: file_id -> evidence record. Missing file_ids are omitted.
        """
        if not file_ids:
            return {}
        wanted = set(file_ids)
        out: Dict[str, dict] = {}
        with self._lock:
            for rec in self._records.values():
                if rec.get("case_id") != case_id:
                    continue
                fid = rec.get("cellebrite_file_id")
                if not fid or fid not in wanted:
                    continue
                # Prefer non-duplicate originals over duplicates
                existing = out.get(fid)
                if existing is None or (existing.get("is_duplicate") and not rec.get("is_duplicate")):
                    out[fid] = rec
        return out

    def mark_processing(self, evidence_ids: List[str]) -> None:
        """Mark selected evidence as 'processing'."""
        with self._lock:
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
        with self._lock:
            now = datetime.now().isoformat()
            for evid in evidence_ids:
                rec = self._records.get(evid)
                if not rec:
                    continue
                if error:
                    rec["status"] = "failed"
                    rec["last_error"] = error
                else:
                    rec["status"] = "processed"
                    rec["last_error"] = None
                rec["processed_at"] = now
            self._persist()

    def set_relevance(self, evidence_ids: List[str], is_relevant: bool) -> int:
        """Mark evidence files as relevant or non-relevant. Returns count updated."""
        updated = 0
        with self._lock:
            for evid in evidence_ids:
                rec = self._records.get(evid)
                if rec:
                    rec["is_relevant"] = is_relevant
                    updated += 1
            if updated:
                self._persist()
        return updated

    # ------------------------------------------------------------------
    # Phase 5: Tag and Entity-link helpers
    # ------------------------------------------------------------------

    def add_tags(self, evidence_ids: List[str], tags: List[str]) -> int:
        """Add tags to one or more evidence records. Bulk-safe (one persist)."""
        if not tags:
            return 0
        clean = [t.strip() for t in tags if t and t.strip()]
        if not clean:
            return 0
        updated = 0
        with self._lock:
            for evid in evidence_ids:
                rec = self._records.get(evid)
                if rec is None:
                    continue
                existing = set(rec.get("tags") or [])
                before = len(existing)
                existing.update(clean)
                if len(existing) != before:
                    rec["tags"] = sorted(existing)
                    updated += 1
                elif "tags" not in rec:
                    rec["tags"] = sorted(existing)
            if updated:
                self._persist()
        return updated

    def remove_tags(self, evidence_ids: List[str], tags: List[str]) -> int:
        """Remove tags from one or more evidence records."""
        if not tags:
            return 0
        remove = set(t.strip() for t in tags if t and t.strip())
        updated = 0
        with self._lock:
            for evid in evidence_ids:
                rec = self._records.get(evid)
                if rec is None:
                    continue
                existing = set(rec.get("tags") or [])
                if existing & remove:
                    rec["tags"] = sorted(existing - remove)
                    updated += 1
            if updated:
                self._persist()
        return updated

    def set_tags(self, evidence_id: str, tags: List[str]) -> bool:
        """Replace the tag list on a single evidence record."""
        clean = sorted({t.strip() for t in (tags or []) if t and t.strip()})
        with self._lock:
            rec = self._records.get(evidence_id)
            if rec is None:
                return False
            rec["tags"] = clean
            self._persist()
            return True

    def get_tag_counts(self, case_id: str) -> List[Dict]:
        """Return a case-wide tag cloud sorted by usage."""
        counts: Dict[str, int] = {}
        with self._lock:
            for rec in self._records.values():
                if rec.get("case_id") != case_id:
                    continue
                for t in rec.get("tags") or []:
                    counts[t] = counts.get(t, 0) + 1
        return [
            {"tag": t, "count": c}
            for t, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

    def link_entities(self, evidence_ids: List[str], entity_ids: List[str]) -> int:
        """Link one or more evidence records to one or more entity IDs."""
        if not entity_ids:
            return 0
        to_add = [e for e in entity_ids if e]
        if not to_add:
            return 0
        updated = 0
        with self._lock:
            for evid in evidence_ids:
                rec = self._records.get(evid)
                if rec is None:
                    continue
                existing = set(rec.get("linked_entity_ids") or [])
                before = len(existing)
                existing.update(to_add)
                if len(existing) != before:
                    rec["linked_entity_ids"] = sorted(existing)
                    updated += 1
                elif "linked_entity_ids" not in rec:
                    rec["linked_entity_ids"] = sorted(existing)
            if updated:
                self._persist()
        return updated

    def unlink_entities(self, evidence_ids: List[str], entity_ids: List[str]) -> int:
        """Remove entity links from evidence records."""
        remove = set(entity_ids or [])
        if not remove:
            return 0
        updated = 0
        with self._lock:
            for evid in evidence_ids:
                rec = self._records.get(evid)
                if rec is None:
                    continue
                existing = set(rec.get("linked_entity_ids") or [])
                if existing & remove:
                    rec["linked_entity_ids"] = sorted(existing - remove)
                    updated += 1
            if updated:
                self._persist()
        return updated

    def list_by_entity(self, case_id: str, entity_id: str) -> List[Dict]:
        """All evidence records in a case that are linked to a given entity."""
        out: List[Dict] = []
        with self._lock:
            for rec in self._records.values():
                if rec.get("case_id") != case_id:
                    continue
                linked = rec.get("linked_entity_ids") or []
                if entity_id in linked:
                    out.append(rec)
        return out

    def unlink_entities_from_all(self, case_id: str, entity_id: str) -> int:
        """Used when a CaseEntity is deleted — remove its link from every record in the case."""
        updated = 0
        with self._lock:
            for rec in self._records.values():
                if rec.get("case_id") != case_id:
                    continue
                linked = set(rec.get("linked_entity_ids") or [])
                if entity_id in linked:
                    linked.discard(entity_id)
                    rec["linked_entity_ids"] = sorted(linked)
                    updated += 1
            if updated:
                self._persist()
        return updated


# Singleton instance
evidence_storage = EvidenceStorage()


