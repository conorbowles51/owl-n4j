"""Case-scoped recorded processing history; never inferred historical versions."""
from uuid import UUID
from services.financial.custody import source_custody
from sqlalchemy import select
from postgres.models.financial import FinancialSourceDocument, FinancialIngestionRun
from postgres.models.evidence import EvidenceFile
from services.financial.ledger_summary import LedgerSummaryError


def capture_processing_provenance(session, *, case_id, readings):
    document_ids={UUID(r['source']['id']) for r in readings}
    run_ids={UUID(r['row']['ingestion_run_id']) for r in readings}
    documents=list(session.scalars(select(FinancialSourceDocument).where(
        FinancialSourceDocument.case_id==case_id,FinancialSourceDocument.id.in_(document_ids)))) if document_ids else []
    if {d.id for d in documents}!=document_ids:
        raise LedgerSummaryError('Captured processing source scope is incomplete.')
    run_ids.update(d.ingestion_run_id for d in documents)
    runs=list(session.scalars(select(FinancialIngestionRun).where(
        FinancialIngestionRun.case_id==case_id,FinancialIngestionRun.id.in_(run_ids)))) if run_ids else []
    if {r.id for r in runs}!=run_ids:
        raise LedgerSummaryError('Captured processing run scope is incomplete.')
    file_ids={d.evidence_file_id for d in documents if d.evidence_file_id}
    files=list(session.scalars(select(EvidenceFile).where(EvidenceFile.case_id==case_id,EvidenceFile.id.in_(file_ids)))) if file_ids else []
    if {f.id for f in files}!=file_ids:
        raise LedgerSummaryError('Captured evidence registration scope is incomplete.')
    def value(v):return v.isoformat() if hasattr(v,'isoformat') else str(v) if isinstance(v,UUID) else v
    def record(row,fields):return {name:value(getattr(row,name)) for name in fields}
    from services.financial.pdf_candidates import _digest
    imports = []
    for document in sorted(documents, key=lambda item: str(item.id)):
        metadata = document.metadata_ or {}
        if 'statement_import_original' not in metadata:
            continue
        if _digest(metadata['statement_import_request']) != metadata.get('statement_import_request_sha256'):
            raise LedgerSummaryError('Stored statement confirmation does not match its recorded digest.')
        digest = metadata.get('statement_import_original_sha256')
        if digest and _digest(metadata['statement_import_original']) != digest:
            raise LedgerSummaryError('Stored statement review does not match its recorded digest.')
        imports.append(dict(source_document_id=str(document.id), evidence_file_id=str(document.evidence_file_id),
            original=metadata['statement_import_original'], original_sha256=digest,
            confirmation=metadata['statement_import_request'], confirmation_sha256=metadata['statement_import_request_sha256']))
    return dict(schema_version='loupe.financial.processing_provenance/1',case_id=str(case_id),
        statement_import_history=imports,
        source_documents=[record(d,('id','evidence_file_id','ingestion_run_id','sha256_at_ingestion','document_type','extraction_layer','parser_name','parser_version')) for d in sorted(documents,key=lambda d:str(d.id))],
        runs=[record(r,('id','code_version','ruleset_version','started_by_user_id','started_by_email','started_at','completed_at')) for r in sorted(runs,key=lambda r:str(r.id))],
        custody_reports=[source_custody(session, case_id=case_id, file_id=f.id) for f in sorted(files,key=lambda f:str(f.id))],
        evidence_registrations=[record(f,('id','original_filename','size','source_type','sha256','created_at','created_by_id','processed_at')) for f in sorted(files,key=lambda f:str(f.id))],
        limitation='Recorded database registration and financial processing metadata for captured sources only. Null versions/times are unknown. These records do not establish all custody transfers or the versions of every upstream component. Stored file hashes are not fresh byte checks.')
