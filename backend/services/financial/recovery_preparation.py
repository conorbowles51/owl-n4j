"""Prepare retained readings without holding the investigator's case lock.

The final writer compares these stored inputs again under its normal locks.
SQL fingerprints follow the existing pending-duplicate projection pattern:
large JSON values stay in PostgreSQL; the synthetic SQLite path hashes values.
No prepared result or token grants ledger admission.
"""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import JSON, String, Text, cast, func, select
from sqlalchemy.exc import DBAPIError

from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import (
    AdjudicationEvent, FinancialAccount, FinancialSourceDocument,
    FinancialStatementPeriod, FinancialTransaction,
)
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as BatchItem
from postgres.models.financial_recovery import FinancialRecoveryItem as Item, FinancialRecoveryRun as Run
from services.financial.pdf_candidates import PdfMappingError, _digest


def _normal(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    return value


def _rows(session, model, condition, *, names=None):
    """A scalar content revision, independent of timestamps or ORM caches."""
    columns = [column for column in model.__table__.columns if names is None or column.name in names]
    postgres = session.get_bind().dialect.name == 'postgresql'
    hashed = [isinstance(column.type, (JSON, Text)) for column in columns]
    query = select(*(func.md5(cast(column, String)) if postgres and hashed[index] else column
                     for index, column in enumerate(columns))).where(condition)
    query = query.order_by(*model.__table__.primary_key.columns)
    return [[value if postgres and hashed[index] else _digest(value) if hashed[index] else _normal(value)
             for index, value in enumerate(row)] for row in session.execute(query)]


def input_revision(session, case_id, item, *, include_scope=False):
    """Bind the actual reading, saved-review and coverage inputs.

    Coverage considers all registered periods and pending reviews in this case.
    Only readings that those reviews can parse (plus this source's history and
    explicitly retained duplicate targets) need text/geometry fingerprints.
    Payment revisions are limited to sources those readings can match by bytes.
    """
    files = list(session.execute(select(EvidenceFile.id, EvidenceFile.sha256,
        EvidenceFile.metadata_['statement_parent_evidence_id'].as_string(),
        EvidenceFile.metadata_['financial_duplicate_dispositions']).where(EvidenceFile.case_id == case_id)))
    by_id = {str(row[0]): row for row in files}
    reading_ids = {str(item.file_id), *item.result.get('lineage_ids', [])}
    if item.result.get('reading_file_id'):
        reading_ids.add(item.result['reading_file_id'])
    reading_ids.update(str(value) for value in session.scalars(select(BatchItem.file_id)
        .join(Batch, Batch.id == BatchItem.batch_id).where(Batch.case_id == case_id,
            Batch.status != 'removed', BatchItem.status.in_(('ready', 'attention', 'pending_import')))))
    batch_ids = [UUID(value['batch_id']) for value in item.result.get('failed_batches', [])]
    for entries in session.scalars(select(Batch.files).where(Batch.case_id == case_id, Batch.id.in_(batch_ids))):
        reading_ids.update(entry[key] for entry in entries for key in ('file_id', 'source_id') if entry.get(key))
    while True:
        previous = set(reading_ids)
        for identifier in previous:
            row = by_id.get(identifier)
            if not row:
                continue
            if row[2]:
                reading_ids.add(row[2])
            for decision in (row[3] or {}).values():
                retained = (decision.get('retained') or {}).get('evidence_file_id')
                if retained:
                    reading_ids.add(retained)
        if previous == reading_ids:
            break
    ids = [by_id[value][0] for value in sorted(reading_ids) if value in by_id]
    hashes = {by_id[value][1] for value in reading_ids if value in by_id}
    source_ids = list(session.scalars(select(FinancialSourceDocument.id).where(
        FinancialSourceDocument.case_id == case_id,
        FinancialSourceDocument.sha256_at_ingestion.in_(hashes))))
    values = dict(
        item=[str(item.id), item.status, item.result],
        files=_rows(session, EvidenceFile, EvidenceFile.case_id == case_id,
            names={'id', 'case_id', 'original_filename', 'stored_path', 'sha256', 'status', 'engine_job_id', 'metadata', 'created_at'}),
        text=_rows(session, EvidenceDocumentText, EvidenceDocumentText.evidence_file_id.in_(ids)),
        geometry=_rows(session, EvidenceTableGeometry, EvidenceTableGeometry.evidence_file_id.in_(ids)),
        sources=_rows(session, FinancialSourceDocument, FinancialSourceDocument.case_id == case_id),
        accounts=_rows(session, FinancialAccount, FinancialAccount.case_id == case_id),
        periods=_rows(session, FinancialStatementPeriod, FinancialStatementPeriod.case_id == case_id),
        payments=_rows(session, FinancialTransaction, (FinancialTransaction.case_id == case_id)
            & FinancialTransaction.source_document_id.in_(source_ids)),
        decisions=_rows(session, AdjudicationEvent, (AdjudicationEvent.case_id == case_id)
            & AdjudicationEvent.subject_id.in_(source_ids)),
        batches=_rows(session, Batch, Batch.case_id == case_id, names={'id', 'case_id', 'status', 'files'}),
        reviews=_rows(session, BatchItem, BatchItem.batch_id.in_(select(Batch.id).where(Batch.case_id == case_id)),
            names={'id', 'batch_id', 'file_id', 'statement_key', 'status', 'summary', 'review_request'}),
    )
    revision = _digest(values)
    return (revision, ids, source_ids) if include_scope else revision


def lock_inputs(session, case_id, prepared):
    """Freeze the compared inputs briefly, or yield to the current owner.

    The case lock prevents new case-owned records; existing records also need
    locks because extraction and legacy duplicate writers do not take Case.
    NOWAIT avoids holding Case while waiting for any of those operations.
    """
    owned_files = select(EvidenceFile.id).where(EvidenceFile.case_id == case_id)
    readings = owned_files.where(EvidenceFile.id.in_(prepared['reading_ids']))
    owned_batches = select(Batch.id).where(Batch.case_id == case_id)
    queries = (
        (EvidenceFile, EvidenceFile.case_id == case_id),
        (EvidenceDocumentText, EvidenceDocumentText.evidence_file_id.in_(readings)),
        (EvidenceTableGeometry, EvidenceTableGeometry.evidence_file_id.in_(readings)),
        (FinancialSourceDocument, FinancialSourceDocument.case_id == case_id),
        (FinancialAccount, FinancialAccount.case_id == case_id),
        (FinancialStatementPeriod, FinancialStatementPeriod.case_id == case_id),
        (Batch, Batch.case_id == case_id),
        (BatchItem, BatchItem.batch_id.in_(owned_batches)),
    )
    try:
        for model, condition in queries:
            keys = tuple(model.__table__.primary_key.columns)
            session.execute(select(*keys).where(condition).order_by(*keys).with_for_update(nowait=True)).all()
        from services.financial.account_consolidation import expand_account_ids
        accounts = set(session.scalars(select(FinancialStatementPeriod.account_id).where(
            FinancialStatementPeriod.case_id == case_id,
            FinancialStatementPeriod.source_document_id.in_(prepared['source_ids']))))
        accounts.update(session.scalars(select(FinancialTransaction.account_id).where(
            FinancialTransaction.case_id == case_id,
            FinancialTransaction.source_document_id.in_(prepared['source_ids']))))
        for identifier in session.scalars(select(FinancialSourceDocument.metadata_['statement_account_id'].as_string())
                .where(FinancialSourceDocument.case_id == case_id,
                    FinancialSourceDocument.id.in_(prepared['source_ids']))):
            if identifier:
                try:
                    accounts.add(UUID(identifier))
                except ValueError:
                    pass  # The strict saved-statement writer rejects invalid metadata.
        accounts = expand_account_ids(session, case_id, list(accounts)) if accounts else []
        session.execute(select(FinancialTransaction.id).where(FinancialTransaction.case_id == case_id,
            FinancialTransaction.source_document_id.in_(prepared['source_ids']) |
            FinancialTransaction.account_id.in_(accounts)).order_by(FinancialTransaction.id)
            .with_for_update(nowait=True)).all()
    except DBAPIError as error:
        if (getattr(error.orig, 'sqlstate', None) or getattr(error.orig, 'pgcode', None)) != '55P03':
            raise
        session.rollback()
        return False
    return True


def prepare_readings(factory, item_id, resolve_path):
    from services.financial.deployment_recovery import PENDING, _verify_bytes
    from services.financial.evidence_intake import has_financial_reading
    from services.financial.reading_recovery import inspect_completed_reading
    from services.financial.statement_import import read_statement_import
    from services.financial.statement_import_overlap import comparison_sources

    def active():
        # Cooperative boundaries only: never cancel the parser thread. The
        # current catalog/period finishes, but Pause prevents the next one.
        with factory() as current:
            state = current.execute(select(Run.status, Item.status).join(Item, Item.run_id == Run.id)
                .where(Item.id == item_id)).first()
            return bool(state and state[0] == 'running' and state[1] in PENDING)

    with factory() as session:
        item = session.get(Item, item_id)
        run = session.get(Run, item.run_id) if item else None
        if not run or run.status != 'running' or item.status not in PENDING:
            return None
        file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == item.file_id, EvidenceFile.case_id == run.case_id))
        if file is None:
            return None
        revision, reading_ids, source_ids = input_revision(session, run.case_id, item, include_scope=True)
        prepared = dict(revision=revision, reading_ids=reading_ids, source_ids=source_ids,
            proposals=None, error=None, diagnoses={}, coverage=None)
        # Batch Retry needs its existing diagnosis, but must not reconstruct a
        # large statement while the final worker holds Case/Run locks.
        for reference in item.result.get('failed_batches', []):
            if not active():
                return None
            batch = session.scalar(select(Batch).where(Batch.id == UUID(reference['batch_id']), Batch.case_id == run.case_id))
            entry = next((entry for entry in batch.files if entry.get('source_id') == reference['source_id']), None) if batch else None
            if not entry or entry.get('status') != 'error' or not entry.get('file_id'):
                continue
            reading = session.scalar(select(EvidenceFile).where(EvidenceFile.id == UUID(entry['file_id']), EvidenceFile.case_id == run.case_id))
            key = (entry['file_id'], entry.get('currency'))
            if reading and reading.status == 'processed' and key not in prepared['diagnoses']:
                diagnosis = inspect_completed_reading(session, case_id=run.case_id,
                    file=reading, currency=entry.get('currency'), _continue=active)
                if diagnosis is None:
                    return None
                prepared['diagnoses'][key] = diagnosis
        target_id = UUID(item.result['reading_file_id']) if item.result.get('reading_file_id') else file.id
        target = session.scalar(select(EvidenceFile).where(EvidenceFile.id == target_id, EvidenceFile.case_id == run.case_id))
        if target and target.status != 'processing' and has_financial_reading(session, target):
            try:
                if not active():
                    return None
                _verify_bytes(target, resolve_path)
                if not active():
                    return None
                cache = {}
                first = read_statement_import(session, case_id=run.case_id, evidence_file_id=target.id, _cache=cache)
                choices = first.get('statement_choices') or []
                proposals = []
                for choice in choices:
                    if not active():
                        return None
                    proposals.append(read_statement_import(session, case_id=run.case_id,
                        evidence_file_id=target.id, statement_id=choice['id'], _cache=cache))
                prepared['proposals'] = proposals or [first]
                if not active():
                    return None
                prepared['coverage'] = comparison_sources(session, run.case_id)[0]
            except (PdfMappingError, ValueError) as error:
                prepared['error'] = str(error) if isinstance(error, PdfMappingError) else 'The new reading has incomplete or invalid statement fields. Open the source to review them.'
        # Drop ORM cached state before comparing the content loaded at the start.
        # No locks or writes are made by preparation, even on parser failure.
        session.expire_all()
        current = session.get(Item, item_id)
        if current is None or input_revision(session, run.case_id, current) != revision:
            return None
        return prepared
