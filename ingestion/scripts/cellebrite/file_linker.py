"""
File linker for Cellebrite UFED report ingestion.

Maps XML file UUIDs (from <taggedFiles>) to physical files on disk,
normalizes Windows backslash paths, validates file existence, and
registers key media files as evidence records for optional Tier 2
LLM processing (image OCR, audio transcription, video analysis).

Each registered evidence record carries a `cellebrite_model_id` so
processed results can be linked back to the parent Neo4j entity.
"""

import hashlib
import uuid as uuid_mod
from pathlib import Path
from typing import Dict, List, Optional, Callable, Set

from .models import TaggedFile, ParsedModel


# File categories inferred from the taggedFiles Local Path prefix
# (Cellebrite organises extracted files into folders by type)
MEDIA_CATEGORIES = {
    "Image": {"extensions": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".heif", ".tif", ".tiff"},
              "evidence_type": "image"},
    "Audio": {"extensions": {".ogg", ".opus", ".mp3", ".m4a", ".aac", ".wav", ".amr", ".3gp"},
              "evidence_type": "audio"},
    "Video": {"extensions": {".mp4", ".3gp", ".avi", ".mov", ".mkv", ".webm"},
              "evidence_type": "video"},
    "Text":  {"extensions": {".txt", ".html", ".htm", ".xml", ".json", ".csv", ".pdf"},
              "evidence_type": "document"},
}


def _normalise_path(windows_path: str) -> str:
    """Convert Windows backslash path to forward slashes."""
    return windows_path.replace("\\", "/")


def _detect_category(local_path: str) -> Optional[str]:
    """Detect file category from the taggedFiles local path prefix or extension."""
    normalised = _normalise_path(local_path)

    # Check path prefix (Cellebrite convention)
    parts = normalised.split("/")
    if len(parts) >= 2:
        folder = parts[0]
        if folder in MEDIA_CATEGORIES:
            return folder

    # Fallback: check extension
    ext = Path(normalised).suffix.lower()
    for category, info in MEDIA_CATEGORIES.items():
        if ext in info["extensions"]:
            return category

    return None


def _compute_sha256_file(file_path: Path) -> Optional[str]:
    """Compute SHA256 hash of a file on disk (chunked for large files)."""
    try:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, IOError):
        return None


class CellebriteFileLinker:
    """
    Links Cellebrite tagged file UUIDs to physical files on disk
    and registers media files as evidence records.
    """

    def __init__(
        self,
        report_dir: Path,
        tagged_files: List[TaggedFile],
        case_id: str,
        report_key: str,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        self.report_dir = report_dir
        self.case_id = case_id
        self.report_key = report_key
        self.log_callback = log_callback

        # Build UUID -> TaggedFile index
        self._file_index: Dict[str, TaggedFile] = {}
        # Build UUID -> resolved physical Path
        self._resolved_paths: Dict[str, Path] = {}

        self._build_index(tagged_files)

    def _log(self, msg: str):
        if self.log_callback:
            self.log_callback(msg)

    def _build_index(self, tagged_files: List[TaggedFile]):
        """Build UUID-to-path index with validation."""
        resolved = 0
        missing = 0

        for tf in tagged_files:
            if not tf.file_id or not tf.local_path:
                continue

            self._file_index[tf.file_id] = tf

            # Normalise and resolve path
            rel_path = _normalise_path(tf.local_path)
            full_path = self.report_dir / rel_path

            # Security: ensure resolved path is within report directory
            try:
                resolved_path = full_path.resolve()
                report_resolved = self.report_dir.resolve()
                if not str(resolved_path).startswith(str(report_resolved)):
                    self._log(f"WARNING: Path traversal blocked: {rel_path}")
                    continue
            except (OSError, ValueError):
                continue

            if resolved_path.exists():
                self._resolved_paths[tf.file_id] = resolved_path
                resolved += 1
            else:
                missing += 1

        self._log(
            f"File index: {len(self._file_index)} entries, "
            f"{resolved} resolved, {missing} missing on disk"
        )

    def get_path(self, file_id: str) -> Optional[Path]:
        """Get resolved physical path for a file UUID."""
        return self._resolved_paths.get(file_id)

    def get_tagged_file(self, file_id: str) -> Optional[TaggedFile]:
        """Get TaggedFile metadata for a file UUID."""
        return self._file_index.get(file_id)

    def register_media_files(
        self,
        evidence_storage,
        owner: Optional[str] = None,
        model_file_map: Optional[Dict[str, List[str]]] = None,
    ) -> int:
        """
        Register media files as evidence records for Tier 2 LLM processing.

        Args:
            evidence_storage: EvidenceStorage instance
            owner: Username for ownership attribution
            model_file_map: Optional mapping of model_id -> [file_id, ...] from jump_targets

        Returns:
            Number of evidence records created
        """
        # Build reverse map: file_id -> model_id (for back-linking)
        file_to_model: Dict[str, str] = {}
        if model_file_map:
            for model_id, file_ids in model_file_map.items():
                for fid in file_ids:
                    file_to_model[fid] = model_id

        files_to_register: List[dict] = []
        seen_hashes: Set[str] = set()

        for file_id, resolved_path in self._resolved_paths.items():
            tf = self._file_index.get(file_id)
            if not tf:
                continue

            # Only register media files (Image, Audio, Video, Text)
            category = _detect_category(tf.local_path)
            if not category:
                continue

            # Use existing hash from XML if available, otherwise compute
            sha256 = tf.sha256
            if not sha256:
                sha256 = _compute_sha256_file(resolved_path)
            if not sha256:
                continue

            # Skip if we've already registered this exact file
            if sha256 in seen_hashes:
                continue
            seen_hashes.add(sha256)

            # Build evidence record data
            file_info = {
                "original_filename": resolved_path.name,
                "stored_path": resolved_path,
                "content": b"",  # We don't need content for hash — provide SHA directly
                "size": tf.size or 0,
            }

            # We'll create the record with extra metadata below
            files_to_register.append({
                "file_info": file_info,
                "file_id": file_id,
                "category": category,
                "sha256": sha256,
                "model_id": file_to_model.get(file_id),
                "resolved_path": resolved_path,
            })

        if not files_to_register:
            self._log("No media files to register")
            return 0

        # Register in batches to avoid holding the lock too long
        batch_size = 500
        total_created = 0

        for i in range(0, len(files_to_register), batch_size):
            batch = files_to_register[i:i + batch_size]
            records = self._register_batch(batch, evidence_storage, owner)
            total_created += len(records)

            if (i + batch_size) % 2000 == 0 or i + batch_size >= len(files_to_register):
                self._log(
                    f"Registered {total_created}/{len(files_to_register)} media files"
                )

        self._log(f"Registered {total_created} media files as evidence records")
        return total_created

    def _register_batch(
        self,
        batch: List[dict],
        evidence_storage,
        owner: Optional[str],
    ) -> List[dict]:
        """Register a batch of files as evidence records."""
        from datetime import datetime

        records = []
        now = datetime.now().isoformat()

        with evidence_storage._lock:
            for item in batch:
                sha256 = item["sha256"]
                resolved_path = item["resolved_path"]
                category = item["category"]
                model_id = item.get("model_id")

                evidence_id = f"ev_{sha256[:16]}"
                # Ensure uniqueness
                suffix = 1
                while evidence_id in evidence_storage._records:
                    evidence_id = f"ev_{sha256[:12]}_{suffix}"
                    suffix += 1

                # Check for duplicates
                duplicate_of = None
                is_duplicate = False
                for rec in evidence_storage._records.values():
                    if rec.get("sha256") == sha256:
                        is_duplicate = True
                        duplicate_of = rec.get("id")
                        break

                record = {
                    "id": evidence_id,
                    "case_id": self.case_id,
                    "owner": owner,
                    "original_filename": resolved_path.name,
                    "stored_path": str(resolved_path),
                    "size": item["file_info"]["size"],
                    "sha256": sha256,
                    "status": "unprocessed",
                    "is_duplicate": is_duplicate,
                    "duplicate_of": duplicate_of,
                    "is_relevant": False,
                    "created_at": now,
                    "processed_at": None,
                    "last_error": None,
                    # Cellebrite-specific metadata
                    "cellebrite_report_key": self.report_key,
                    "cellebrite_file_id": item["file_id"],
                    "cellebrite_model_id": model_id,
                    "cellebrite_category": category,
                    "source_type": "cellebrite",
                }

                evidence_storage._records[evidence_id] = record
                records.append(record)

            evidence_storage._persist()

        return records

    def build_model_file_map(self, models: List[ParsedModel]) -> Dict[str, List[str]]:
        """
        Build a mapping of model_id -> [file_id, ...] from jump_targets.

        Only includes file references (ismodel=False) that exist in the file index.
        """
        model_file_map: Dict[str, List[str]] = {}

        for model in models:
            self._collect_file_refs(model, model_file_map)

        return model_file_map

    def _collect_file_refs(self, model: ParsedModel, result: Dict[str, List[str]]):
        """Recursively collect file references from a model and its children."""
        file_refs = []

        for i, target_id in enumerate(model.jump_targets):
            is_model = model.jump_target_is_model[i] if i < len(model.jump_target_is_model) else False
            if not is_model and target_id in self._file_index:
                file_refs.append(target_id)

        if file_refs:
            result[model.model_id] = file_refs

        # Recurse into nested models
        for nested in model.model_fields.values():
            self._collect_file_refs(nested, result)
        for nested_list in model.multi_model_fields.values():
            for nested in nested_list:
                self._collect_file_refs(nested, result)

    @property
    def resolved_count(self) -> int:
        return len(self._resolved_paths)

    @property
    def total_count(self) -> int:
        return len(self._file_index)
