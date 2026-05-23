"""
Evidence Storage Service

Handles persistent storage of uploaded evidence files and their processing status.
"""

import json
import os
import hashlib
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from threading import RLock

from config import BASE_DIR
from services._timeutil import utcnow_iso


# BASE_DIR in config.py already points to the project root (e.g. /.../owl-n4j)
# Store metadata under <project>/data and binary files under <project>/ingestion/data
DATA_DIR = BASE_DIR / "data"
STORAGE_FILE = DATA_DIR / "evidence.json"
LOCK_FILE = DATA_DIR / "evidence.json.lock"

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
    """Service for managing evidence file metadata and status.

    Multi-process safe: every mutation reloads the on-disk JSON under an
    fcntl file lock, applies the change, then atomically saves and refreshes
    the in-memory cache. Without this, uvicorn's multiple worker processes
    each held independent in-memory dicts and any single-record mutation from
    worker A would overwrite the latest disk state written by worker B (which
    held records A had never seen). Observed on case 43f1afb1 2026-05-22:
    a 93k-row C5 upload completed in worker 3, then a single DELETE request
    landed on worker 1 and wiped all 93k rows on save.
    """

    def __init__(self) -> None:
        self._records: Dict[str, dict] = _load_evidence()
        self._lock = RLock()  # Reentrant lock for thread-safe operations
        try:
            self._mtime: float = STORAGE_FILE.stat().st_mtime
        except OSError:
            self._mtime = 0.0
        self._migrate_records()

    def _refresh_if_stale(self) -> None:
        """Reload `self._records` if the on-disk file has been mutated by
        another uvicorn worker since we last cached. The _file_locked
        write path covers writes; this is the corresponding read-side
        guard so READS don't serve stale data from a worker that hasn't
        mutated lately. See background_task_storage._refresh_if_stale —
        same bug pattern: a record created by worker A is invisible to
        reads routed to workers B/C/D until they happen to perform a
        mutation themselves.
        """
        try:
            current_mtime = STORAGE_FILE.stat().st_mtime
        except OSError:
            return
        if current_mtime > self._mtime:
            with self._lock:
                try:
                    current_mtime = STORAGE_FILE.stat().st_mtime
                except OSError:
                    return
                if current_mtime > self._mtime:
                    self._records = _load_evidence()
                    self._mtime = current_mtime

    @contextmanager
    def _file_locked(self):
        """Yield a freshly-loaded records dict that will be atomically
        persisted on successful exit. Holds an exclusive fcntl file lock
        across the entire reload-mutate-save window so writes from other
        worker processes serialize correctly.
        """
        with self._lock:
            ensure_dirs()
            with open(LOCK_FILE, "a") as lf:
                # Keep the lock file world-writable so a root-owned re-create
                # (e.g., a sudo'd maintenance script) cannot lock out the
                # backend user. chmod only succeeds for owner or root; if the
                # current process owns the file every call refreshes mode 666.
                try:
                    os.chmod(LOCK_FILE, 0o666)
                except OSError:
                    pass
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    fresh = _load_evidence()
                    yield fresh
                    _save_evidence(fresh)
                    self._records = fresh
                    try:
                        self._mtime = STORAGE_FILE.stat().st_mtime
                    except OSError:
                        pass
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

    def _migrate_records(self) -> None:
        """Migrate legacy records: separate 'duplicate' status into is_duplicate flag,
        and ensure is_relevant field exists."""
        # Check first against in-memory copy; only take the file lock if a
        # migration is actually needed (avoids contention on every worker boot).
        needs_migration = any(
            ("is_relevant" not in rec) or ("is_duplicate" not in rec)
            for rec in self._records.values()
        )
        if not needs_migration:
            return
        with self._file_locked() as records:
            for rec in records.values():
                if "is_relevant" not in rec:
                    rec["is_relevant"] = False
                if "is_duplicate" not in rec:
                    if rec.get("status") == "duplicate":
                        rec["is_duplicate"] = True
                        rec["status"] = "processed" if rec.get("processed_at") else "unprocessed"
                    else:
                        rec["is_duplicate"] = bool(rec.get("duplicate_of"))

    # ------------- Basic accessors -------------

    def reload(self) -> None:
        """Reload evidence records from disk."""
        with self._lock:
            self._records = _load_evidence()

    def _persist(self) -> None:
        _save_evidence(self._records)

    def get_all(self) -> List[dict]:
        """Return all evidence records as a list."""
        self._refresh_if_stale()
        with self._lock:
            return list(self._records.values())

    def get(self, evidence_id: str) -> Optional[dict]:
        """Get a single evidence record by id."""
        self._refresh_if_stale()
        with self._lock:
            return self._records.get(evidence_id)

    # ------------- Query helpers -------------

    def list_files(  # noqa: D401 — read path; calls _refresh_if_stale below
        self,
        case_id: Optional[str] = None,
        status: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> List[dict]:
        """List evidence files, optionally filtered by case_id, status, and owner."""
        self._refresh_if_stale()
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
        self._refresh_if_stale()
        with self._lock:
            for rec in self._records.values():
                if rec.get("sha256") == sha256:
                    return rec
            return None

    def find_all_by_hash(self, sha256: str) -> List[dict]:
        """Find all records matching a given hash."""
        self._refresh_if_stale()
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
            files: List of dicts. Either:
                {
                  "original_filename": str,
                  "stored_path": Path,
                  "content": bytes,
                  "size": int,
                }
              or (when the file is already on disk and already hashed):
                {
                  "original_filename": str,
                  "stored_path": Path,
                  "sha256": str,
                  "size": int,
                }

        Returns:
            List of evidence records that were created.
        """
        created_records: List[dict] = []
        with self._file_locked() as records:
            now = utcnow_iso()
            for file_info in files:
                original_filename = file_info["original_filename"]
                stored_path: Path = file_info["stored_path"]
                size: int = file_info["size"]
                if "sha256" in file_info:
                    sha256 = file_info["sha256"]
                else:
                    content: bytes = file_info["content"]
                    sha256 = _compute_sha256(content)
                duplicate_rec = None
                for rec in records.values():
                    if rec.get("sha256") == sha256:
                        duplicate_rec = rec
                        break

                evidence_id = f"ev_{sha256[:16]}"
                suffix = 1
                while evidence_id in records:
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
                    "status": "unprocessed",
                    "is_duplicate": is_duplicate,
                    "duplicate_of": duplicate_of,
                    "is_relevant": False,
                    "created_at": now,
                    "processed_at": None,
                    "last_error": None,
                }
                if file_info.get("relative_path") is not None:
                    record["relative_path"] = file_info["relative_path"]

                records[evidence_id] = record
                created_records.append(record)
        return created_records

    def delete_record(self, evidence_id: str) -> Optional[dict]:
        """
        Delete an evidence record by ID. Returns the deleted record or None.
        Does NOT delete the physical file — caller is responsible for that.
        """
        deleted = [None]
        with self._file_locked() as records:
            deleted[0] = records.pop(evidence_id, None)
        return deleted[0]

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
        self._refresh_if_stale()
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
        with self._file_locked() as records:
            for evid in evidence_ids:
                rec = records.get(evid)
                if not rec:
                    continue
                if rec.get("status") in ("processed", "processing"):
                    continue
                rec["status"] = "processing"
                rec["last_error"] = None
                rec["processed_at"] = None

    def mark_processed(
        self,
        evidence_ids: List[str],
        error: Optional[str] = None,
    ) -> None:
        """Mark selected evidence as processed or failed."""
        with self._file_locked() as records:
            now = utcnow_iso()
            for evid in evidence_ids:
                rec = records.get(evid)
                if not rec:
                    continue
                if error:
                    rec["status"] = "failed"
                    rec["last_error"] = error
                else:
                    rec["status"] = "processed"
                    rec["last_error"] = None
                rec["processed_at"] = now

    def set_relevance(self, evidence_ids: List[str], is_relevant: bool) -> int:
        """Mark evidence files as relevant or non-relevant. Returns count updated."""
        updated = 0
        with self._file_locked() as records:
            for evid in evidence_ids:
                rec = records.get(evid)
                if rec:
                    rec["is_relevant"] = is_relevant
                    updated += 1
        return updated

    # ------------------------------------------------------------------
    # Phase 5: Tag and Entity-link helpers
    # ------------------------------------------------------------------

    def add_tags(self, evidence_ids: List[str], tags: List[str]) -> int:
        """Add tags to one or more evidence records."""
        if not tags:
            return 0
        clean = [t.strip() for t in tags if t and t.strip()]
        if not clean:
            return 0
        updated = 0
        with self._file_locked() as records:
            for evid in evidence_ids:
                rec = records.get(evid)
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
        return updated

    def remove_tags(self, evidence_ids: List[str], tags: List[str]) -> int:
        """Remove tags from one or more evidence records."""
        if not tags:
            return 0
        remove = set(t.strip() for t in tags if t and t.strip())
        updated = 0
        with self._file_locked() as records:
            for evid in evidence_ids:
                rec = records.get(evid)
                if rec is None:
                    continue
                existing = set(rec.get("tags") or [])
                if existing & remove:
                    rec["tags"] = sorted(existing - remove)
                    updated += 1
        return updated

    def set_tags(self, evidence_id: str, tags: List[str]) -> bool:
        """Replace the tag list on a single evidence record."""
        clean = sorted({t.strip() for t in (tags or []) if t and t.strip()})
        success = [False]
        with self._file_locked() as records:
            rec = records.get(evidence_id)
            if rec is not None:
                rec["tags"] = clean
                success[0] = True
        return success[0]

    def get_tag_counts(self, case_id: str) -> List[Dict]:
        """Return a case-wide tag cloud sorted by usage."""
        counts: Dict[str, int] = {}
        self._refresh_if_stale()
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
        with self._file_locked() as records:
            for evid in evidence_ids:
                rec = records.get(evid)
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
        return updated

    def unlink_entities(self, evidence_ids: List[str], entity_ids: List[str]) -> int:
        """Remove entity links from evidence records."""
        remove = set(entity_ids or [])
        if not remove:
            return 0
        updated = 0
        with self._file_locked() as records:
            for evid in evidence_ids:
                rec = records.get(evid)
                if rec is None:
                    continue
                existing = set(rec.get("linked_entity_ids") or [])
                if existing & remove:
                    rec["linked_entity_ids"] = sorted(existing - remove)
                    updated += 1
        return updated

    def list_by_entity(self, case_id: str, entity_id: str) -> List[Dict]:
        """All evidence records in a case that are linked to a given entity."""
        out: List[Dict] = []
        self._refresh_if_stale()
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
        with self._file_locked() as records:
            for rec in records.values():
                if rec.get("case_id") != case_id:
                    continue
                linked = set(rec.get("linked_entity_ids") or [])
                if entity_id in linked:
                    linked.discard(entity_id)
                    rec["linked_entity_ids"] = sorted(linked)
                    updated += 1
        return updated


# Singleton instance
evidence_storage = EvidenceStorage()


