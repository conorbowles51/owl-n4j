"""Immutable submitted scope, with durable per-statement execution outcomes."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from postgres.models.financial_import_batches import FinancialImportOperation as Operation
from services.financial.pdf_candidates import PdfMappingError


def operation_view(operation):
    outcomes = operation.outcomes
    pending = sum(row['status'] in ('queued', 'importing') for row in outcomes)
    failed = sum(row['status'] == 'failed' for row in outcomes)
    return dict(id=str(operation.id), case_id=str(operation.case_id), batch_id=str(operation.batch_id),
        created_at=operation.created_at.isoformat(), updated_at=operation.updated_at.isoformat(),
        status='in_progress' if pending else ('needs_review' if failed else 'complete'),
        statement_count=len(outcomes), pending=pending, failed=failed,
        imported=sum(row['status'] == 'imported' for row in outcomes),
        already_present=sum(row['status'] == 'already_present' for row in outcomes),
        transaction_count=sum(row.get('transaction_count', 0) for row in outcomes),
        incomplete_count=sum(row.get('incomplete_count', 0) for row in outcomes), outcomes=outcomes)


def operations_for(session, case_id, batch_id):
    return [operation_view(op) for op in session.scalars(select(Operation).where(
        Operation.case_id == case_id, Operation.batch_id == batch_id)
        .order_by(Operation.created_at.desc(), Operation.id).limit(20))]


def check_operation(session, *, case_id, batch_id, request_id):
    # Validate the batch even when no receipt exists. A request lookup must not
    # expose another case's receipts, nor report an inaccessible batch as empty.
    from services.financial.import_batches import batch_for
    batch_for(session, case_id, batch_id)
    operation = session.scalar(select(Operation).where(
        Operation.id == request_id, Operation.case_id == case_id,
        Operation.batch_id == batch_id))
    return dict(case_id=str(case_id), batch_id=str(batch_id), request_id=str(request_id),
                operation=operation_view(operation) if operation else None)


def record_outcome(session, case_id, item, status, **result):
    identifier = item.summary.get('import_operation_id')
    if not identifier:
        return  # Legacy accepted jobs still finish; their batch retains results.
    operation = session.scalar(select(Operation).where(Operation.id == UUID(identifier),
        Operation.case_id == case_id, Operation.batch_id == item.batch_id).with_for_update())
    if operation is None:
        raise PdfMappingError('The accepted import receipt is unavailable. Refresh this batch.', 409)
    outcomes = deepcopy(operation.outcomes)
    entry = next(row for row in outcomes if row['item_id'] == str(item.id))
    entry.update(status=status, **result, updated_at=datetime.now(timezone.utc).isoformat())
    operation.outcomes = outcomes
