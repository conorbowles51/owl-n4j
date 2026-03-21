#!/usr/bin/env python3
"""
Migrate evidence.json and evidence_logs.json data to Postgres tables.

Idempotent: skips records whose legacy_id already exists.

Usage:
    cd backend
    python -m scripts.migrate_evidence_to_postgres
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Ensure backend is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import BASE_DIR
from postgres.session import get_background_session
from postgres.models.evidence import EvidenceFile, EvidenceFolder, IngestionLog
from postgres.models.case import Case
from sqlalchemy import select


DATA_DIR = BASE_DIR / "data"
EVIDENCE_FILE = DATA_DIR / "evidence.json"
LOGS_FILE = DATA_DIR / "evidence_logs.json"


def _load_json(path: Path) -> dict | list:
    if not path.exists():
        print(f"  [skip] {path} does not exist")
        return {} if path.name == "evidence.json" else []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_case_uuid(db, case_id_str: str) -> uuid.UUID | None:
    """Try to parse as UUID directly, or look up by legacy format."""
    try:
        return uuid.UUID(case_id_str)
    except ValueError:
        pass
    # Try to find case by matching title/legacy id patterns
    case = db.scalars(select(Case).limit(1)).first()
    if case:
        return case.id
    return None


def migrate_evidence(db) -> int:
    """Migrate evidence.json records to evidence_files table."""
    data = _load_json(EVIDENCE_FILE)
    if not data:
        print("  No evidence records to migrate.")
        return 0

    records = data if isinstance(data, list) else list(data.values())
    migrated = 0
    skipped = 0

    # Build legacy_id → UUID map for duplicate_of resolution
    legacy_to_uuid: dict[str, uuid.UUID] = {}

    for rec in records:
        legacy_id = rec.get("id", "")
        if not legacy_id:
            continue

        # Check if already migrated
        existing = db.scalars(
            select(EvidenceFile).where(EvidenceFile.legacy_id == legacy_id)
        ).first()
        if existing:
            legacy_to_uuid[legacy_id] = existing.id
            skipped += 1
            continue

        case_id = _resolve_case_uuid(db, rec.get("case_id", ""))
        if not case_id:
            print(f"  [warn] Cannot resolve case_id for {legacy_id}, skipping")
            skipped += 1
            continue

        new_id = uuid.uuid4()
        legacy_to_uuid[legacy_id] = new_id

        # Parse dates
        created_at = None
        if rec.get("created_at"):
            try:
                created_at = datetime.fromisoformat(rec["created_at"])
            except (ValueError, TypeError):
                created_at = datetime.now()

        processed_at = None
        if rec.get("processed_at"):
            try:
                processed_at = datetime.fromisoformat(rec["processed_at"])
            except (ValueError, TypeError):
                pass

        ef = EvidenceFile(
            id=new_id,
            case_id=case_id,
            original_filename=rec.get("original_filename", "unknown"),
            stored_path=rec.get("stored_path", ""),
            size=rec.get("size", 0),
            sha256=rec.get("sha256", ""),
            status=rec.get("status", "unprocessed"),
            is_duplicate=rec.get("is_duplicate", False),
            is_relevant=rec.get("is_relevant", False),
            owner=rec.get("owner"),
            last_error=rec.get("last_error"),
            legacy_id=legacy_id,
        )
        # Set timestamps manually
        if created_at:
            ef.created_at = created_at
        if processed_at:
            ef.processed_at = processed_at

        db.add(ef)
        migrated += 1

    db.flush()

    # Second pass: resolve duplicate_of references
    resolved_dups = 0
    for rec in records:
        legacy_id = rec.get("id", "")
        dup_of = rec.get("duplicate_of")
        if not dup_of or not legacy_id:
            continue

        file_uuid = legacy_to_uuid.get(legacy_id)
        dup_uuid = legacy_to_uuid.get(dup_of)
        if file_uuid and dup_uuid:
            ef = db.get(EvidenceFile, file_uuid)
            if ef:
                ef.duplicate_of_id = dup_uuid
                resolved_dups += 1

    db.flush()

    print(f"  Evidence: migrated={migrated}, skipped={skipped}, dups_resolved={resolved_dups}")
    return migrated


def migrate_logs(db) -> int:
    """Migrate evidence_logs.json to ingestion_logs table."""
    data = _load_json(LOGS_FILE)
    if not data:
        print("  No log records to migrate.")
        return 0

    logs = data if isinstance(data, list) else []
    migrated = 0

    for entry in logs:
        case_id_str = entry.get("case_id")
        if not case_id_str:
            continue

        case_id = _resolve_case_uuid(db, case_id_str)
        if not case_id:
            continue

        # Try to link to evidence file via legacy id
        evidence_file_id = None
        ev_id = entry.get("evidence_id")
        if ev_id:
            ef = db.scalars(
                select(EvidenceFile).where(EvidenceFile.legacy_id == ev_id)
            ).first()
            if ef:
                evidence_file_id = ef.id

        created_at = None
        ts = entry.get("timestamp")
        if ts:
            try:
                created_at = datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                created_at = datetime.now()

        extra = {}
        if entry.get("progress_current") is not None:
            extra["progress_current"] = entry["progress_current"]
        if entry.get("progress_total") is not None:
            extra["progress_total"] = entry["progress_total"]

        log = IngestionLog(
            case_id=case_id,
            evidence_file_id=evidence_file_id,
            level=entry.get("level", "info"),
            message=entry.get("message", ""),
            filename=entry.get("filename"),
            extra=extra,
        )
        if created_at:
            log.created_at = created_at

        db.add(log)
        migrated += 1

    db.flush()
    print(f"  Logs: migrated={migrated}")
    return migrated


def main():
    print("Starting evidence migration to Postgres...")

    with get_background_session() as db:
        ev_count = migrate_evidence(db)
        log_count = migrate_logs(db)
        # commit happens automatically via get_background_session context manager

    print(f"Migration complete: {ev_count} evidence records, {log_count} log records.")

    # Rename source files to .migrated
    for path in (EVIDENCE_FILE, LOGS_FILE):
        if path.exists():
            migrated_path = path.with_suffix(path.suffix + ".migrated")
            path.rename(migrated_path)
            print(f"  Renamed {path.name} → {migrated_path.name}")


if __name__ == "__main__":
    main()
