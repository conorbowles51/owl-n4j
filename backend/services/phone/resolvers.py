"""The ``phone_extraction`` and ``phone_file`` link resolvers (07 section 6, lx-collect's registry).

A link to a phone item is stored only after its resolver confirms the item is in the case
(``postgres.link_types.resolve_phone_target``). Both resolvers read the capture tables (01 section 6) and nothing
else; a phone item is never passed unchecked.

``mapping_versions`` is the version set behind the item at collect time. At capture there is no mapping yet
(interpretation is stage C), so the set names the capture code version that wrote the rows; stage C adds its
mapping versions beside it.

A ``phone_file`` id is the file's ``file_uid`` (02 section 1.2). Its metadata gives the facts
``services.phone_files.ensure_phone_file_evidence`` needs. ``stored_path`` is the file's path when it is on disk in
a folder upload. A file inside a zip or UFDR has no path of its own (containers are read in place, 01 D6), so its
``stored_path`` is the locator ``phone-file:<file_uid>`` (``phone_files.member_locator``): its bytes are served from
the archive by the phone file reader (``services.phone.media.content``), never opened as a path (cb-media item F).
A file absent from the production has no ``stored_path`` and is refused as evidence with that reason.
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
        else:
            from services import phone_files
            stored_path = phone_files.member_locator(ident)
    return link_types.PhoneTarget(
        label=name, mapping_versions=_versions(row.capture_code_version),
        metadata={"original_filename": name, "stored_path": stored_path, "size": row.disk_size,
                  "sha256": row.disk_sha256, "outcome": row.outcome, "extraction_id": str(row.extraction_id),
                  "document_index": row.document_index, "ordinal": row.ordinal, "phone_record_id": None})


# ---- stage C: records, threads and identities (02 sections 1.2, 5.7, 8.1) ------------------------------------------
# A record or thread is resolved in the current generation of its phone; ``mapping_versions`` names the mapping set,
# the interpreter version and the generation it was read with, so a later re-reading is visible beside the link.

_STATE = text(
    "SELECT s.mapping_set_id, s.interpreter_version, s.generation, e.capture_code_version, e.standing "
    "FROM phone_interpretation_state s JOIN phone_extractions e ON e.id = s.extraction_id "
    "WHERE s.extraction_id = :ext AND e.case_id = :case")

_RECORD = text(
    "SELECT r.extraction_id, r.document_index, r.ordinal, r.model_type, r.title, r.first_instant, "
    "r.interpretation_level, r.mapping_version_id FROM phone_record_summaries r JOIN phone_interpretation_state s ON "
    "s.extraction_id = r.extraction_id AND s.generation = r.generation WHERE r.record_uid = :id AND r.case_id = :case")

_THREAD = text(
    "SELECT t.extraction_id, t.record_uid, t.app, t.thread_kind, t.title_in_record, t.event_count, t.first_instant, "
    "t.last_instant, t.interpretation_level, t.mapping_version_id FROM phone_threads t JOIN phone_interpretation_state s "
    "ON s.extraction_id = t.extraction_id AND s.generation = t.generation WHERE t.thread_key = :id AND t.case_id = :case")

_IDENTITY = text(
    "SELECT id, identity_key, kind, subkind, value_display, sighting_count, phone_count FROM phone_identities "
    "WHERE identity_key = :id AND case_id = :case AND sighting_count > 0")

_CASE_SETS = text(
    "SELECT DISTINCT s.mapping_set_id::text, s.interpreter_version FROM phone_interpretation_state s JOIN "
    "phone_extractions e ON e.id = s.extraction_id WHERE e.case_id = :case AND e.standing = 'active' ORDER BY 1, 2")

REPLACED = ("This item is on a phone report that was replaced in this case; link it on the report the case stands on")


def _interpreted(db, case, extraction_id, extra=None):
    st = db.execute(_STATE, {"ext": extraction_id, "case": case}).first()
    if st is None:
        return None, None
    versions = {"capture_code_version": st.capture_code_version, "mapping_set_id": str(st.mapping_set_id or ""),
                "interpreter_version": st.interpreter_version, "generation": st.generation}
    versions.update(extra or {})
    return versions, st.standing


def resolve_record(db, case_id, target_id):
    """A ``phone_record`` id is the record's ``record_uid`` (02 section 1.2)."""
    ident, case = _uuid(target_id), _uuid(case_id)
    if ident is None or case is None:
        return None
    row = db.execute(_RECORD, {"id": ident, "case": case}).first()
    if row is None:
        return None
    versions, standing = _interpreted(db, case, row.extraction_id, {
        "interpretation_level": row.interpretation_level,
        "mapping_version_id": str(row.mapping_version_id) if row.mapping_version_id else None})
    if versions is None:
        return None
    if standing != "active":
        raise link_types.LinkTargetError(REPLACED)
    return link_types.PhoneTarget(
        label=row.title or row.model_type, mapping_versions=versions,
        metadata={"extraction_id": str(row.extraction_id), "document_index": row.document_index,
                  "ordinal": row.ordinal, "model_type": row.model_type,
                  "first_instant": row.first_instant.isoformat() if row.first_instant else None})


def resolve_thread(db, case_id, target_id):
    """A ``phone_thread`` id is its thread key (02 decision 45), which holds the extraction id."""
    case = _uuid(case_id)
    if case is None or not isinstance(target_id, str) or not target_id:
        return None
    row = db.execute(_THREAD, {"id": target_id, "case": case}).first()
    if row is None:
        return None
    versions, standing = _interpreted(db, case, row.extraction_id, {
        "interpretation_level": row.interpretation_level,
        "mapping_version_id": str(row.mapping_version_id) if row.mapping_version_id else None})
    if versions is None:
        return None
    if standing != "active":
        raise link_types.LinkTargetError(REPLACED)
    return link_types.PhoneTarget(
        label=row.title_in_record or row.app or row.thread_kind, mapping_versions=versions,
        metadata={"extraction_id": str(row.extraction_id), "thread_kind": row.thread_kind, "app": row.app,
                  "record_uid": str(row.record_uid) if row.record_uid else None, "event_count": row.event_count,
                  "first_instant": row.first_instant.isoformat() if row.first_instant else None,
                  "last_instant": row.last_instant.isoformat() if row.last_instant else None})


def resolve_identity(db, case_id, target_id):
    """A ``phone_identity`` id is its identity key (02 section 8.1), unique within a case; never matched without the
    case. Its versions are the mapping sets of the case's phones it was read from."""
    case = _uuid(case_id)
    if case is None or not isinstance(target_id, str) or not target_id:
        return None
    row = db.execute(_IDENTITY, {"id": target_id, "case": case}).first()
    if row is None:
        return None
    sets = [{"mapping_set_id": m, "interpreter_version": v} for m, v in db.execute(_CASE_SETS, {"case": case})]
    return link_types.PhoneTarget(
        label=row.value_display, mapping_versions={"phones": sets},
        metadata={"identity_id": str(row.id), "identity_key": row.identity_key, "kind": row.kind,
                  "subkind": row.subkind, "sighting_count": row.sighting_count, "phone_count": row.phone_count})


def register() -> None:
    """Called once at backend start."""
    link_types.register_phone_resolver("phone_extraction", resolve_extraction)
    link_types.register_phone_resolver("phone_file", resolve_file)
    link_types.register_phone_resolver("phone_record", resolve_record)
    link_types.register_phone_resolver("phone_thread", resolve_thread)
    link_types.register_phone_resolver("phone_identity", resolve_identity)
    from services.phone import selections
    link_types.register_phone_resolver("phone_selection", selections.resolve)
