"""Which batches are superseded: every statement they hold is in a newer batch or already saved.

Read only; nothing is deleted or changed. The batch list hides superseded
batches by default ("Show N older batches") so the investigator is not asked
to choose between near-identical runs over the same files. A statement is its
file's bytes (sha256) and its statement key, as in the review queue, so a
second upload of the same PDF prepared in a newer batch also counts.

A batch is never superseded while it is preparing, pausing or saving, while it
holds no statement, or while one of its files has no statement anywhere newer
(a failed file is only covered when a newer batch holds the same bytes).
"""
from sqlalchemy import select

from postgres.models.evidence import EvidenceFile

ACTIVE = ('preparing', 'pausing')
IGNORED = ('removed', 'superseded_reading')


def superseded_batches(session, case_id, batches, items):
    """{batch id: True} for superseded batches. `items` are the batches' (unprojected) items."""
    from services.financial.review_queue import _saved_scopes
    file_ids = {item.file_id for item in items}
    for batch in batches:
        for file in batch.files or []:
            for key in ('file_id', 'source_id'):
                if file.get(key):
                    file_ids.add(file[key])
    file_ids = {_uuid(value) for value in file_ids} - {None}
    shas = dict(session.execute(select(EvidenceFile.id, EvidenceFile.sha256).where(
        EvidenceFile.case_id == case_id, EvidenceFile.id.in_(file_ids))).all()) if file_ids else {}
    saved, _ = _saved_scopes(session, case_id)
    by_batch = {}
    for item in items:
        if item.status not in IGNORED:
            by_batch.setdefault(item.batch_id, []).append(item)
    order = sorted(batches, key=lambda b: (b.created_at, str(b.id)))
    newer_statements, newer_files, result = set(), set(), {}
    # Walk from the newest: what any newer batch holds is known when a batch is judged.
    for batch in reversed(order):
        own = by_batch.get(batch.id, [])
        statements = {(shas.get(item.file_id), item.statement_key or '') for item in own}
        files = {shas.get(_uuid(file.get('file_id'))) or shas.get(_uuid(file.get('source_id')))
                 for file in batch.files or []}
        covered = bool(own) and batch.status not in ACTIVE and not any(i.status == 'pending_import' for i in own)
        if covered:
            covered = all(item.status == 'imported' or scope in saved or scope in newer_statements
                          for item in own for scope in [(shas.get(item.file_id), item.statement_key or '')])
        if covered:
            held_files = {shas.get(item.file_id) for item in own}
            covered = all(sha in held_files or sha in newer_files for sha in files) and None not in files
        if covered:
            result[batch.id] = True
        newer_statements |= statements
        newer_files |= {sha for sha in files if sha}
    return result


def _uuid(value):
    from uuid import UUID
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None
