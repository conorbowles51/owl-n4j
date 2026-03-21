"""
Evidence DB Storage Service

Postgres-backed storage for evidence files, folders, and ingestion logs.
Replaces the JSON-based evidence_storage.py and evidence_log_storage.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, and_
from sqlalchemy.orm import Session

from postgres.models.evidence import EvidenceFile, EvidenceFolder, IngestionLog


# ---------------------------------------------------------------------------
# Folder operations
# ---------------------------------------------------------------------------

class EvidenceDBStorage:
    """Postgres-backed evidence storage service. All methods require a db session."""

    # --- Folders ---

    @staticmethod
    def create_folder(
        db: Session,
        case_id: uuid.UUID,
        name: str,
        parent_id: Optional[uuid.UUID] = None,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> EvidenceFolder:
        folder = EvidenceFolder(
            case_id=case_id,
            name=name,
            parent_id=parent_id,
            created_by_id=created_by_id,
        )
        db.add(folder)
        db.flush()
        return folder

    @staticmethod
    def list_folders(
        db: Session,
        case_id: uuid.UUID,
        parent_id: Optional[uuid.UUID] = None,
    ) -> List[EvidenceFolder]:
        q = select(EvidenceFolder).where(
            EvidenceFolder.case_id == case_id,
            EvidenceFolder.parent_id == parent_id if parent_id else EvidenceFolder.parent_id.is_(None),
        ).order_by(EvidenceFolder.name)
        return list(db.scalars(q).all())

    @staticmethod
    def get_folder(db: Session, folder_id: uuid.UUID) -> Optional[EvidenceFolder]:
        return db.get(EvidenceFolder, folder_id)

    @staticmethod
    def get_folder_breadcrumbs(db: Session, folder_id: uuid.UUID) -> List[EvidenceFolder]:
        """Walk up from folder_id to root, return list from root → current."""
        breadcrumbs: List[EvidenceFolder] = []
        current = db.get(EvidenceFolder, folder_id)
        while current:
            breadcrumbs.append(current)
            current = db.get(EvidenceFolder, current.parent_id) if current.parent_id else None
        breadcrumbs.reverse()
        return breadcrumbs

    @staticmethod
    def rename_folder(db: Session, folder_id: uuid.UUID, new_name: str) -> EvidenceFolder:
        folder = db.get(EvidenceFolder, folder_id)
        if not folder:
            raise ValueError(f"Folder {folder_id} not found")
        folder.name = new_name
        db.flush()
        return folder

    @staticmethod
    def delete_folder(db: Session, folder_id: uuid.UUID, case_id: uuid.UUID) -> List[str]:
        """
        Delete a folder and collect stored_paths of all files that will be removed.
        Caller must delete physical files BEFORE committing (cascade will remove DB records).
        Returns list of stored_path strings for disk cleanup.
        """
        stored_paths: List[str] = []

        def _collect_paths(fid: uuid.UUID) -> None:
            # Collect files in this folder
            files = db.scalars(
                select(EvidenceFile).where(EvidenceFile.folder_id == fid)
            ).all()
            for f in files:
                stored_paths.append(f.stored_path)

            # Recurse into subfolders
            children = db.scalars(
                select(EvidenceFolder).where(EvidenceFolder.parent_id == fid)
            ).all()
            for child in children:
                _collect_paths(child.id)

        _collect_paths(folder_id)

        folder = db.get(EvidenceFolder, folder_id)
        if folder:
            db.delete(folder)
            db.flush()

        return stored_paths

    @staticmethod
    def move_folder(
        db: Session, folder_id: uuid.UUID, new_parent_id: Optional[uuid.UUID]
    ) -> EvidenceFolder:
        folder = db.get(EvidenceFolder, folder_id)
        if not folder:
            raise ValueError(f"Folder {folder_id} not found")
        folder.parent_id = new_parent_id
        db.flush()
        return folder

    @staticmethod
    def get_or_create_folder_path(
        db: Session,
        case_id: uuid.UUID,
        relative_path: str,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> EvidenceFolder:
        """
        Given a path like "wiretaps/batch-01/subfolder", create the chain of
        folders if they don't exist and return the deepest one.
        """
        parts = PurePosixPath(relative_path).parts
        parent_id: Optional[uuid.UUID] = None
        current_folder: Optional[EvidenceFolder] = None

        for part in parts:
            existing = db.scalars(
                select(EvidenceFolder).where(
                    EvidenceFolder.case_id == case_id,
                    EvidenceFolder.name == part,
                    EvidenceFolder.parent_id == parent_id if parent_id else EvidenceFolder.parent_id.is_(None),
                )
            ).first()

            if existing:
                current_folder = existing
            else:
                current_folder = EvidenceFolder(
                    case_id=case_id,
                    name=part,
                    parent_id=parent_id,
                    created_by_id=created_by_id,
                )
                db.add(current_folder)
                db.flush()

            parent_id = current_folder.id

        if current_folder is None:
            raise ValueError(f"Empty relative_path: {relative_path}")
        return current_folder

    # --- Files ---

    @staticmethod
    def list_files(
        db: Session,
        case_id: uuid.UUID,
        folder_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> List[EvidenceFile]:
        conditions = [EvidenceFile.case_id == case_id]
        if folder_id is not None:
            conditions.append(EvidenceFile.folder_id == folder_id)
        if status:
            conditions.append(EvidenceFile.status == status)
        if owner:
            conditions.append(EvidenceFile.owner == owner)

        q = select(EvidenceFile).where(*conditions).order_by(EvidenceFile.created_at.desc())
        return list(db.scalars(q).all())

    @staticmethod
    def list_contents(
        db: Session,
        case_id: uuid.UUID,
        folder_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Return folders + files at a given level, plus file/subfolder counts."""
        if folder_id:
            folder_cond = EvidenceFolder.parent_id == folder_id
            file_cond = EvidenceFile.folder_id == folder_id
        else:
            folder_cond = EvidenceFolder.parent_id.is_(None)
            file_cond = EvidenceFile.folder_id.is_(None)

        folders = list(db.scalars(
            select(EvidenceFolder).where(
                EvidenceFolder.case_id == case_id,
                folder_cond,
            ).order_by(EvidenceFolder.name)
        ).all())

        files = list(db.scalars(
            select(EvidenceFile).where(
                EvidenceFile.case_id == case_id,
                file_cond,
            ).order_by(EvidenceFile.original_filename)
        ).all())

        # Enrich folders with counts
        folder_dicts = []
        for f in folders:
            file_count = db.scalar(
                select(func.count()).select_from(EvidenceFile).where(EvidenceFile.folder_id == f.id)
            ) or 0
            subfolder_count = db.scalar(
                select(func.count()).select_from(EvidenceFolder).where(EvidenceFolder.parent_id == f.id)
            ) or 0
            folder_dicts.append({
                "id": str(f.id),
                "case_id": str(f.case_id),
                "name": f.name,
                "parent_id": str(f.parent_id) if f.parent_id else None,
                "disk_path": f.disk_path,
                "created_at": f.created_at.isoformat() if f.created_at else None,
                "updated_at": f.updated_at.isoformat() if f.updated_at else None,
                "file_count": file_count,
                "subfolder_count": subfolder_count,
            })

        file_dicts = [EvidenceDBStorage._file_to_dict(ef) for ef in files]

        return {"folders": folder_dicts, "files": file_dicts}

    @staticmethod
    def get(db: Session, file_id: uuid.UUID) -> Optional[EvidenceFile]:
        return db.get(EvidenceFile, file_id)

    @staticmethod
    def get_by_legacy_id(db: Session, legacy_id: str) -> Optional[EvidenceFile]:
        return db.scalars(
            select(EvidenceFile).where(EvidenceFile.legacy_id == legacy_id)
        ).first()

    @staticmethod
    def add_files(
        db: Session,
        case_id: uuid.UUID,
        files_data: List[Dict[str, Any]],
        owner: Optional[str] = None,
        folder_id: Optional[uuid.UUID] = None,
    ) -> List[EvidenceFile]:
        """
        Add file records. Each item in files_data expects:
        {original_filename, stored_path, sha256, size, [is_duplicate, duplicate_of_id, relative_path]}
        """
        created: List[EvidenceFile] = []
        for fd in files_data:
            sha256 = fd["sha256"]

            # Detect duplicates
            is_dup = fd.get("is_duplicate", False)
            dup_of_id = fd.get("duplicate_of_id")
            if not is_dup:
                existing = db.scalars(
                    select(EvidenceFile).where(EvidenceFile.sha256 == sha256).limit(1)
                ).first()
                if existing:
                    is_dup = True
                    dup_of_id = existing.id

            ef = EvidenceFile(
                case_id=case_id,
                folder_id=folder_id,
                original_filename=fd["original_filename"],
                stored_path=str(fd["stored_path"]),
                size=fd.get("size", 0),
                sha256=sha256,
                status="unprocessed",
                is_duplicate=is_dup,
                duplicate_of_id=dup_of_id,
                owner=owner,
                legacy_id=fd.get("legacy_id"),
            )
            db.add(ef)
            created.append(ef)

        db.flush()
        return created

    @staticmethod
    def find_by_hash(db: Session, sha256: str) -> Optional[EvidenceFile]:
        return db.scalars(
            select(EvidenceFile).where(EvidenceFile.sha256 == sha256).limit(1)
        ).first()

    @staticmethod
    def find_all_by_hash(db: Session, sha256: str) -> List[EvidenceFile]:
        return list(db.scalars(
            select(EvidenceFile).where(EvidenceFile.sha256 == sha256)
        ).all())

    @staticmethod
    def delete_record(db: Session, file_id: uuid.UUID) -> Optional[EvidenceFile]:
        ef = db.get(EvidenceFile, file_id)
        if ef:
            db.delete(ef)
            db.flush()
        return ef

    @staticmethod
    def move_file(
        db: Session, file_id: uuid.UUID, new_folder_id: Optional[uuid.UUID]
    ) -> EvidenceFile:
        ef = db.get(EvidenceFile, file_id)
        if not ef:
            raise ValueError(f"Evidence file {file_id} not found")
        ef.folder_id = new_folder_id
        db.flush()
        return ef

    @staticmethod
    def move_files(
        db: Session, file_ids: List[uuid.UUID], new_folder_id: Optional[uuid.UUID]
    ) -> List[EvidenceFile]:
        moved = []
        for fid in file_ids:
            ef = db.get(EvidenceFile, fid)
            if ef:
                ef.folder_id = new_folder_id
                moved.append(ef)
        db.flush()
        return moved

    @staticmethod
    def mark_processing(db: Session, file_ids: List[uuid.UUID]) -> None:
        for fid in file_ids:
            ef = db.get(EvidenceFile, fid)
            if ef and ef.status not in ("processed", "processing"):
                ef.status = "processing"
                ef.last_error = None
                ef.processed_at = None
        db.flush()

    @staticmethod
    def mark_processed(
        db: Session, file_ids: List[uuid.UUID], error: Optional[str] = None
    ) -> None:
        now = datetime.now()
        for fid in file_ids:
            ef = db.get(EvidenceFile, fid)
            if not ef:
                continue
            if error:
                ef.status = "failed"
                ef.last_error = error
            else:
                ef.status = "processed"
                ef.last_error = None
            ef.processed_at = now
        db.flush()

    @staticmethod
    def set_relevance(
        db: Session, file_ids: List[uuid.UUID], is_relevant: bool
    ) -> int:
        updated = 0
        for fid in file_ids:
            ef = db.get(EvidenceFile, fid)
            if ef:
                ef.is_relevant = is_relevant
                updated += 1
        if updated:
            db.flush()
        return updated

    # --- Logs ---

    @staticmethod
    def add_log(
        db: Session,
        case_id: uuid.UUID,
        level: str,
        message: str,
        filename: Optional[str] = None,
        evidence_file_id: Optional[uuid.UUID] = None,
        extra: Optional[Dict] = None,
    ) -> IngestionLog:
        log = IngestionLog(
            case_id=case_id,
            evidence_file_id=evidence_file_id,
            level=level,
            message=message,
            filename=filename,
            extra=extra or {},
        )
        db.add(log)
        db.flush()
        return log

    @staticmethod
    def list_logs(
        db: Session,
        case_id: uuid.UUID,
        limit: int = 100,
    ) -> List[IngestionLog]:
        q = (
            select(IngestionLog)
            .where(IngestionLog.case_id == case_id)
            .order_by(IngestionLog.created_at.desc())
            .limit(limit)
        )
        return list(db.scalars(q).all())

    # --- Helpers ---

    @staticmethod
    def _file_to_dict(ef: EvidenceFile) -> Dict[str, Any]:
        return {
            "id": str(ef.id),
            "case_id": str(ef.case_id),
            "folder_id": str(ef.folder_id) if ef.folder_id else None,
            "original_filename": ef.original_filename,
            "stored_path": ef.stored_path,
            "size": ef.size,
            "sha256": ef.sha256,
            "status": ef.status,
            "is_duplicate": ef.is_duplicate,
            "duplicate_of": str(ef.duplicate_of_id) if ef.duplicate_of_id else None,
            "is_relevant": ef.is_relevant,
            "owner": ef.owner,
            "created_at": ef.created_at.isoformat() if ef.created_at else None,
            "processed_at": ef.processed_at.isoformat() if ef.processed_at else None,
            "last_error": ef.last_error,
            "legacy_id": ef.legacy_id,
        }

    @staticmethod
    def _log_to_dict(log: IngestionLog) -> Dict[str, Any]:
        return {
            "id": str(log.id),
            "case_id": str(log.case_id),
            "evidence_file_id": str(log.evidence_file_id) if log.evidence_file_id else None,
            "level": log.level,
            "message": log.message,
            "filename": log.filename,
            "extra": log.extra,
            "timestamp": log.created_at.isoformat() if log.created_at else None,
        }
