"""The ``phone_extraction`` and ``phone_file`` link resolvers (07 section 6, lx-collect's registry).

A link to a phone item is stored only after its resolver confirms the item is in the case
(``postgres.link_types.resolve_phone_target``). Both resolvers read the capture tables (01 section 6) and nothing
else; a phone item is never passed unchecked.

``mapping_versions`` is the version set behind the item at collect time. At capture there is no mapping yet
(interpretation is stage C), so the set names the capture code version that wrote the rows; stage C adds its
mapping versions beside it.

A ``phone_file`` id is the file's ``file_uid`` (02 section 1.2). Its metadata gives the facts
``services.phone_files.ensure_phone_file_evidence`` needs. ``stored_path`` is given only when the file is on disk in
a folder upload; a file inside a zip or UFDR has no path of its own (containers are read in place, 01 D6), so
``stored_path`` is None and registering it as evidence is refused with that reason.
"""
from __future__ import annotations

import posixpath
import uuid
from pathlib import Path

from sqlalchemy import text

from postgres import link_types

_EXTRACTION = text(
    "SELECT e.id, e.standing, e.capture_state, e.capture_code_version, c.original_name "
    "FROM phone_extractions e JOIN phone_extraction_containers c ON c.id = e.first_container_id "
    "WHERE e.id = :id AND e.case_id = :case")

_FILE = text(
    "SELECT f.extraction_id, f.document_index, f.ordinal, f.local_path, f.source_file_id, f.disk_relpath, "
    "f.disk_size, f.disk_sha256, f.outcome, e.capture_code_version "
    "FROM phone_files f JOIN phone_extractions e ON e.id = f.extraction_id "
    "WHERE f.file_uid = :id AND e.case_id = :case")

_FOLDER_ROOT = text(
    "SELECT c.stored_path, l.root_path FROM phone_extraction_container_links l "
    "JOIN phone_extraction_containers c ON c.id = l.container_id "
    "WHERE l.extraction_id = :ext AND c.container_kind = 'folder' ORDER BY l.linked_at LIMIT 1")


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _versions(capture_code_version):
    return {"capture_code_version": capture_code_version}


def resolve_extraction(db, case_id, target_id):
    ident = _uuid(target_id)
    if ident is None:
        return None
    row = db.execute(_EXTRACTION, {"id": ident, "case": _uuid(case_id)}).first()
    if row is None:
        return None
    return link_types.PhoneTarget(
        label=row.original_name, mapping_versions=_versions(row.capture_code_version),
        metadata={"extraction_id": str(row.id), "standing": str(row.standing),
                  "capture_state": str(row.capture_state)})


def _data_root():
    from config import EVIDENCE_DATA_ROOT
    return Path(EVIDENCE_DATA_ROOT)


def resolve_file(db, case_id, target_id):
    ident = _uuid(target_id)
    if ident is None:
        return None
    case = _uuid(case_id)
    row = db.execute(_FILE, {"id": ident, "case": case}).first()
    if row is None:
        return None
    name = posixpath.basename((row.local_path or "").replace("\\", "/")) or row.source_file_id or str(ident)
    stored_path = None
    if row.disk_relpath is not None:
        folder = db.execute(_FOLDER_ROOT, {"ext": row.extraction_id}).first()
        if folder is not None:
            stored_path = str(_data_root() / str(case) / folder.stored_path / folder.root_path / row.disk_relpath)
    return link_types.PhoneTarget(
        label=name, mapping_versions=_versions(row.capture_code_version),
        metadata={"original_filename": name, "stored_path": stored_path, "size": row.disk_size,
                  "sha256": row.disk_sha256, "outcome": row.outcome, "extraction_id": str(row.extraction_id),
                  "document_index": row.document_index, "ordinal": row.ordinal, "phone_record_id": None})


def register() -> None:
    """Called once at backend start."""
    link_types.register_phone_resolver("phone_extraction", resolve_extraction)
    link_types.register_phone_resolver("phone_file", resolve_file)
