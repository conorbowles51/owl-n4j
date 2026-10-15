"""Internal PDF readings are versions of evidence, not additional disclosures.

Only explicit, case-scoped, byte-identical lineage is grouped. Equal filenames,
hashes or transaction amounts on independently uploaded evidence are insufficient.
"""
from uuid import UUID
from sqlalchemy import select, exists, cast, String, func
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
