"""Single-statement submissions use the existing durable batch worker."""
from uuid import uuid5
from sqlalchemy import select, text
from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item, FinancialImportOperation as Operation
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.import_operations import operation_view

# A held statement lock (another save or a batch turn on this PDF) must not
# hold the request open past the browser's own timeout. Nothing is written
# while waiting, so a busy answer is definite and the submission can be repeated.
QUEUE_LOCK_TIMEOUT = '5s'
BUSY_MESSAGE = ('Another save is using this statement. Nothing was submitted yet; '
    'the import is retried automatically in a moment.')


def job_id(case_id, file_id, request):
    return uuid5(case_id, 'standalone-import:' + str(file_id) + ':' + _digest(request.model_dump(mode='json')))


def find_operation(session, *, case_id, evidence_file_id, request):
    identifier = job_id(case_id, evidence_file_id, request)
    operation = session.scalar(select(Operation).where(Operation.id == identifier, Operation.case_id == case_id))
    return operation_view(operation) if operation else None


def queue_statement(session, *, case_id, evidence_file_id, request, actor):
    from services.financial import import_batches
    from services.financial.file_visibility import require_financial_file
    from services.financial.statement_import import read_statement_import
    from services.financial.statement_import_receipt import saved_receipt
    identifier = job_id(case_id, evidence_file_id, request)
    # Evidence serializes simultaneous first submissions without taking another
    # worker's batch lock. An existing accepted operation is immutable here.
    postgres = session.get_bind().dialect.name == 'postgresql'
    if postgres:
        session.execute(text(f"SET LOCAL lock_timeout = '{QUEUE_LOCK_TIMEOUT}'"))
    try:
        file = session.scalar(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
            EvidenceFile.id == evidence_file_id).with_for_update().execution_options(populate_existing=True))
    except Exception as error:
        from services.financial.import_batches import _lock_busy_error
        if not _lock_busy_error(error):
            raise
        session.rollback()
        # An earlier identical submission may already be accepted; report it.
        existing = session.get(Operation, identifier)
        return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), receipt=None,
            operation=operation_view(existing) if existing else None,
            busy=existing is None, message=None if existing else BUSY_MESSAGE)
    if postgres:
        # Only the first-submission serialization is bounded; the rest of this
        # transaction keeps the server default.
        session.execute(text('SET LOCAL lock_timeout TO DEFAULT'))
    if file is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    require_financial_file(file)
    existing = session.get(Operation, identifier)
    if existing:
        return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), operation=operation_view(existing))
    current = saved_receipt(session, case_id=case_id, evidence_file_id=evidence_file_id, request=request)
    if current['receipt']:
        return current
    if session.scalar(select(Item.id).where(Item.file_id == evidence_file_id,
            Item.statement_key == (request.statement_id or ''), Item.status == 'pending_import').limit(1)):
        raise PdfMappingError('This statement already has an accepted import. Check its processing batch before submitting again.', 409)
    proposal = read_statement_import(session, case_id=case_id, evidence_file_id=evidence_file_id,
        statement_id=request.statement_id, currency=request.currency, _include_period_checks=False)
    raw = request.model_dump(mode='json')
    _, summary = import_batches.assess(proposal, raw)
    if not summary.get('can_import'):
        raise PdfMappingError(' '.join(p['message'] for p in summary.get('problems', [])[:3]) or
            'This statement needs review before import.', 422)
    actor_data = dict(name=actor.name, email=actor.email, user_id=str(actor.user_id))
    item_id = uuid5(identifier, str(file.id) + ':' + (request.statement_id or ''))
    summary.update(filename=file.original_filename, source_id=str(file.id),
        import_actor=actor_data, import_operation_id=str(identifier))
    # Checked files stop the worker from preparing unrelated periods in this PDF.
    session.add(Batch(id=identifier, case_id=case_id, created_by=actor.user_id,
        status='preparing', actor=actor_data, files=[dict(source_id=str(file.id), file_id=str(file.id),
            filename=file.original_filename, currency=request.currency, status='checked', standalone_import=True, statement_id=request.statement_id)]))
    session.flush()
    session.add(Item(id=item_id, batch_id=identifier, file_id=file.id, statement_key=request.statement_id or '',
        status='pending_import', summary=summary, review_request=raw))
    operation = Operation(id=identifier, case_id=case_id, batch_id=identifier,
        expected_revision=_digest(raw), actor=actor_data,
        outcomes=[dict(item_id=str(item_id), file_id=str(file.id), filename=file.original_filename,
            period_start=request.period_start, period_end=request.period_end, status='queued')])
    session.add(operation)
    session.commit()
    return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), operation=operation_view(operation))
