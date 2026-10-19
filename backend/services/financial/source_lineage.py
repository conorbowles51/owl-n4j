"""Internal PDF readings are versions of evidence, not additional disclosures.

Only explicit, case-scoped, byte-identical lineage is grouped. Equal filenames,
hashes or transaction amounts on independently uploaded evidence are insufficient.
"""
from collections import OrderedDict
from threading import Lock
from uuid import UUID
from sqlalchemy import select, exists, cast, String, func, literal_column
from sqlalchemy.orm import aliased
from postgres.models.evidence import EvidenceFile
from services.financial.file_visibility import financial_file_visibility


def lineage_groups(files):
    by_id = {str(file.id): file for file in files}
    groups = {}
    for file in files:
        root = str((file.metadata_ or {}).get('statement_root_evidence_id') or file.id)
        original = by_id.get(root)
        if original is None or original.case_id != file.case_id or original.sha256 != file.sha256:
            root = str(file.id)
        groups.setdefault(root, []).append(file)
    return groups


def current_version(versions):
    # Keep removed readings in history; a removed family is still reachable in
    # the removed-files view. Selecting it never silently restores its imports.
    active = [f for f in versions if not financial_file_visibility(f)['financial_removed']]
    by_id = {str(f.id): f for f in versions}
    def depth(file):
        seen = set()
        while (parent := (file.metadata_ or {}).get('statement_parent_evidence_id')) in by_id and parent not in seen:
            seen.add(parent)
            file = by_id[parent]
        return len(seen)
    return max(active or versions, key=lambda f: (
        '' if active else (financial_file_visibility(f)['financial_visibility_changed_at'] or ''),
        f.created_at.isoformat() if f.created_at else '', depth(f), str(f.id)))


# Columns no lineage, comparison or review reads, deferred on case-wide loads:
# the processing snapshot alone was 12 MB of 19 MB per load on a 5,482-file
# case. A deferred column still loads on first access, so results are unchanged.
CASE_WIDE_DEFERRED = (EvidenceFile.last_processed_profile_snapshot, EvidenceFile.summary, EvidenceFile.transcription,
                      EvidenceFile.transcription_segments, EvidenceFile.transcription_speakers,
                      EvidenceFile.transcription_speaker_merges, EvidenceFile.tags, EvidenceFile.linked_entity_ids)


def case_wide_files():
    """select(EvidenceFile) for loading many of a case's files at once."""
    from sqlalchemy.orm import defer
    return select(EvidenceFile).options(*(defer(column) for column in CASE_WIDE_DEFERRED))


class CaseFile:
    """A read-only copy of an evidence row, for comparisons that never write.

    Only the fields lineage, visibility, review progress and duplicate guards
    read are kept. Anything else raises AttributeError rather than guessing.
    """
    __slots__ = ('id', 'case_id', 'sha256', 'status', 'engine_job_id', 'original_filename', 'created_at', 'metadata_')

    def __init__(self, file):
        for name in self.__slots__:
            object.__setattr__(self, name, getattr(file, name))

    def __setattr__(self, name, value):
        raise AttributeError('CaseFile is a read-only copy; load the EvidenceFile to change it.')


# Per process: case id -> {file id: (row version, CaseFile)}. A row is reused
# only while PostgreSQL reports the same row version (xmin), which every
# committed update, including one to its metadata, changes. Decoding a large
# case's metadata was about 1.2 s of every statement open and queue rebuild.
_CASE_FILES = OrderedDict()
_CASE_FILES_LOCK = Lock()
CASE_FILES_KEPT = 2  # About 90 MB per worker for a 5,500-file case.


def _row_version(session):
    """SQL for a row's version, or None where the database has none (SQLite)."""
    if session.get_bind().dialect.name != 'postgresql':
        return None
    return literal_column('evidence_files.xmin::text')


def _cacheable(session):
    # Unflushed edits live only in this session's identity map. A database
    # copy would not show them, so such a session reads its own objects.
    return not any(isinstance(obj, EvidenceFile) for obj in (*session.new, *session.dirty, *session.deleted))


def case_files(session, case_id, ids=None):
    """{file id: file} for a case, or the given ids of it, for read-only comparison.

    Rows whose version is unchanged since this process last read them are
    returned as the same CaseFile copies; changed and new rows are loaded.
    Without row versions, or with unflushed evidence edits, the session's own
    EvidenceFile objects are returned instead.
    """
    version = _row_version(session)
    condition = [EvidenceFile.case_id == case_id] + ([EvidenceFile.id.in_(set(ids))] if ids is not None else [])
    if version is None or not _cacheable(session):
        return {file.id: file for file in session.scalars(case_wide_files().where(*condition))}
    current = dict(session.execute(select(EvidenceFile.id, version).where(*condition)).all())
    key = str(case_id)
    with _CASE_FILES_LOCK:
        known = _CASE_FILES.get(key, {})
        if key in _CASE_FILES:
            _CASE_FILES.move_to_end(key)
    stale = [file_id for file_id, row_version in current.items()
             if (known.get(file_id) or (None,))[0] != row_version]
    loaded = {}
    for start in range(0, len(stale), 1000):
        # Plain columns, not ORM objects: an object this session already holds
        # would be returned as it was first loaded, not as this row version.
        for row in session.execute(select(*(getattr(EvidenceFile, name).label(name) for name in CaseFile.__slots__),
                version.label('row_version')).where(EvidenceFile.case_id == case_id,
                EvidenceFile.id.in_(stale[start:start + 1000]))):
            loaded[row.id] = (row.row_version, CaseFile(row))
    # A row changed between the two reads is stored under its newer version
    # only; the next read compares that version again.
    # A row deleted between the two reads is left out, as a fresh load would.
    result = {file_id: loaded[file_id][1] if file_id in loaded else known[file_id][1] for file_id in current
              if file_id in loaded or (file_id in known and known[file_id][0] == current[file_id])}
    if loaded or (ids is None and len(known) != len(current)):
        with _CASE_FILES_LOCK:
            entries = dict(_CASE_FILES.get(key, {}))
            entries.update(loaded)
            if ids is None:
                entries = {file_id: entry for file_id, entry in entries.items() if file_id in current}
            _CASE_FILES[key] = entries
            _CASE_FILES.move_to_end(key)
            while len(_CASE_FILES) > CASE_FILES_KEPT:
                _CASE_FILES.popitem(last=False)
    return result


def comparison_lineage(session, case_id):
    """case_lineage for read-only comparison, from case_files."""
    return lineage_groups(list(case_files(session, case_id).values()))


def case_lineage(session, case_id):
    return lineage_groups(list(session.scalars(case_wide_files().where(EvidenceFile.case_id == case_id))))


def select_current_files(session, case_id, selected):
    identifiers = {str(f.id) for f in selected}
    return [current_version(versions) for versions in case_lineage(session, case_id).values()
            if any(str(f.id) in identifiers for f in versions)]


def lineage_id(file):
    try:
        return str(UUID(str((file.metadata_ or {}).get('statement_root_evidence_id') or file.id)))
    except (ValueError, TypeError):
        return str(file.id)


def visible_evidence_condition():
    """Hide only proven internal copies, before pagination and counting."""
    original = aliased(EvidenceFile)
    return ~exists(select(original.id).where(
        original.case_id == EvidenceFile.case_id, original.sha256 == EvidenceFile.sha256,
        original.id != EvidenceFile.id,
        func.replace(cast(original.id, String), '-', '') == func.replace(
            EvidenceFile.metadata_['statement_root_evidence_id'].as_string(), '-', ''),
    ).correlate(EvidenceFile))


def reading_history(session, files):
    """Small batch lookup for Evidence listings; original ids/citations stay put."""
    if not files:
        return {}
    originals = {str(file.id): file for file in files}
    copies = session.scalars(select(EvidenceFile).where(
        EvidenceFile.case_id.in_({file.case_id for file in files}),
        EvidenceFile.metadata_['statement_root_evidence_id'].as_string().in_(originals),
    ).order_by(EvidenceFile.created_at, EvidenceFile.id))
    result = {}
    for copy in copies:
        original = originals.get(lineage_id(copy))
        if not original or original.id == copy.id or original.case_id != copy.case_id or original.sha256 != copy.sha256:
            continue
        result.setdefault(str(original.id), []).append(dict(id=str(copy.id), status=copy.status,
            created_at=copy.created_at.isoformat() if copy.created_at else None,
            reading_mode=(copy.metadata_ or {}).get('statement_pdf_reading_mode', 'automatic')))
    return result
