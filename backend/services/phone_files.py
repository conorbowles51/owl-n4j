"""Phone files as evidence rows, only on demand (07 section 6.4 item 4).

A file from a phone becomes an evidence row only when a person adds it as dossier media or interview evidence:
one file at a time, idempotent per phone file id, never in bulk. The row has `source_type = phone_file` and is
shown in Evidence as "Phone file used in a dossier", linked back to its phone record.

Such a row is kept out of processing jobs (and so out of embedding, which processing does), and out of Workspace
AI source collection, unless the case's external-processing decision allows it (plan standing decision 8; the
decision is `allow_phone_external_processing`, 02 section 8.8, recorded by the phone build). Until the phone build
registers its check, the answer is "not allowed".
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from postgres import link_types
from postgres.models.evidence import EvidenceFile
from postgres.models.user import User

SOURCE_TYPE = "phone_file"
EVIDENCE_LABEL = "Phone file used in a dossier"
REQUIRED_FILE_FACTS = ("original_filename", "stored_path", "size", "sha256")

# check(db, case_id, evidence_file) -> bool: whether the case's external-processing decision covers this file.
ExternalProcessingCheck = Callable[[Session, uuid.UUID, EvidenceFile], bool]
_external_processing_check: ExternalProcessingCheck | None = None


MEMBER_PREFIX = "phone-file:"


def member_locator(file_uid) -> str:
    """The ``stored_path`` of a phone file kept inside an uploaded archive: not a path on disk. Its bytes are read
    through ``services.phone.media.content`` (cb-media item F)."""
    return MEMBER_PREFIX + str(file_uid)


def is_member_locator(stored_path) -> bool:
    return str(stored_path or "").startswith(MEMBER_PREFIX)


def register_external_processing_check(check: ExternalProcessingCheck | None) -> None:
    global _external_processing_check
    _external_processing_check = check


def external_processing_check_registered() -> bool:
    return _external_processing_check is not None


def external_processing_allowed(db: Session, file: EvidenceFile) -> bool:
    """True for every file that is not a phone file; for a phone file, only when the case's decision allows it."""
    if getattr(file, "source_type", None) != SOURCE_TYPE:
        return True
    if _external_processing_check is None:
        return False
    return bool(_external_processing_check(db, file.case_id, file))


def ensure_phone_file_evidence(
    db: Session, *, case_id: uuid.UUID, phone_file_id: str, user: User,
) -> tuple[EvidenceFile, bool]:
    """The evidence row for one phone file, created on first use. Returns (row, created).

    The phone file is checked against the case through the registered `phone_file` resolver, whose metadata must
    give the file's name, stored path, size and sha256. The caller commits.
    """
    phone_file_id = str(phone_file_id or "").strip()
    if not phone_file_id:
        raise ValueError("A phone file id is required")
    existing = _existing(db, case_id, phone_file_id)
    if existing is not None:
        return existing, False
    target = link_types.resolve_phone_target(db, case_id, "phone_file", phone_file_id)
    facts: dict[str, Any] = dict(target.metadata or {})
    missing = [name for name in REQUIRED_FILE_FACTS if facts.get(name) in (None, "")]
    if missing:
        raise ValueError(f"The phone file {phone_file_id} cannot be used as evidence: its {', '.join(missing)} is unknown")
    row = EvidenceFile(
        id=uuid.uuid4(),
        case_id=case_id,
        original_filename=str(facts["original_filename"])[:512],
        stored_path=str(facts["stored_path"]),
        size=int(facts["size"]),
        sha256=str(facts["sha256"]),
        status="unprocessed",
        created_by_id=user.id,
        source_type=SOURCE_TYPE,
        source_ref=phone_file_id,
        metadata_={
            "origin_label": EVIDENCE_LABEL,
            "phone_file_id": phone_file_id,
            "phone_record_id": facts.get("phone_record_id"),
            "extraction_id": facts.get("extraction_id"),
            "mapping_versions": dict(target.mapping_versions),
        },
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        # Another request registered the same file first; use its row.
        existing = _existing(db, case_id, phone_file_id)
        if existing is None:
            raise
        return existing, False
    return row, True


def _existing(db: Session, case_id: uuid.UUID, phone_file_id: str) -> EvidenceFile | None:
    return db.scalar(select(EvidenceFile).where(
        EvidenceFile.case_id == case_id,
        EvidenceFile.source_type == SOURCE_TYPE,
        EvidenceFile.source_ref == phone_file_id,
    ))
