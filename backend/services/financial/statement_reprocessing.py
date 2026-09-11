"""Prepare a new statement version without replacing old source text or reviews."""
import hashlib
import os
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile
from services.financial.pdf_candidates import PdfMappingError


def create_statement_version(session, *, case_id, evidence_file_id, request_id, actor, resolve_path):
    from postgres.models.case import Case
    session.execute(select(Case.id).where(Case.id == case_id).with_for_update()).all()
    original = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
        EvidenceFile.case_id == case_id).with_for_update())
    if original is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    if not original.original_filename.lower().endswith('.pdf'):
        raise PdfMappingError('Statement reprocessing requires a PDF.', 422)
    existing = session.scalar(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
        EvidenceFile.metadata_['statement_version_request'].as_string() == str(request_id)))
    if existing is not None:
        if (existing.metadata_ or {}).get('statement_parent_evidence_id') != str(evidence_file_id):
            raise PdfMappingError('This reprocessing request belongs to another statement.', 409)
        return existing
    source = resolve_path(original.stored_path)
    if source is None or not source.is_file() or source.stat().st_size > 256 * 1024 * 1024:
        raise PdfMappingError('The original PDF is unavailable or exceeds the supported size.', 409)
    version_id = uuid4()
    target = source.parent / (str(version_id) + '.pdf')
    digest, count = hashlib.sha256(), 0
    created = False
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(descriptor, 'wb') as outgoing, source.open('rb') as incoming:
            for chunk in iter(lambda: incoming.read(1024 * 1024), b''):
                count += len(chunk)
                if count > 256 * 1024 * 1024:
                    raise PdfMappingError('The PDF changed or exceeds the supported size.', 409)
                outgoing.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != original.sha256:
            raise PdfMappingError('The source bytes no longer match the evidence record.', 409)
        version = EvidenceFile(id=version_id, case_id=case_id, folder_id=original.folder_id,
            original_filename=original.original_filename, stored_path=str(target), size=count,
            sha256=original.sha256, status='unprocessed', source_type=original.source_type,
            metadata_=dict(statement_root_evidence_id=(original.metadata_ or {}).get('statement_root_evidence_id', str(evidence_file_id)), statement_parent_evidence_id=str(evidence_file_id), statement_version_request=str(request_id),
                statement_version_actor=dict(user_id=str(actor.user_id), name=actor.name, email=actor.email)))
        session.add(version)
        session.commit()
        return version
    except Exception:
        session.rollback()
        if created:
            target.unlink(missing_ok=True)
        raise
