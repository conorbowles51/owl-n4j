"""Close a forgotten import batch without withdrawing anything it imported.

A forgotten batch is a run nobody is working on (for example the October runs of case 49494305 that releases kept
resuming). ``import_removal.remove_imports`` is the wrong tool for it: it withdraws by PDF hash, including later
re-imports of the same statements. Closing as forgotten only retires the batch:

- status 'removed', worker token and lease cleared, ``actor.closed_as_forgotten`` records whose decision it was,
  when, why and the previous status;
- no transaction, statement, document or batch item is changed or deleted. Unimported ready/attention items stay
  as history of a removed batch and are never worked again;
- the batch's investigator decisions (a period skipped, a duplicate ignored) keep protecting their statements:
  recovery reads them from batches closed as forgotten (``decision_items``).

Dry run by default:
    python -m services.financial.forgotten_batches <case_id> <batch_id> [...] --decision "<who, date: why>"
    ... --apply
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select

from postgres.models.financial_import_batches import (FinancialImportBatch as Batch,
    FinancialImportBatchItem as Item, FinancialImportOperation as Operation)
from services.financial.pdf_candidates import PdfMappingError

# Investigator decisions a closed batch keeps carrying for its statements.
CARRIED_DECISIONS = ('skipped', 'duplicate_ignored')
DONE_BY = 'services.financial.forgotten_batches.close_forgotten_batch'


def closed_as_forgotten(batch):
    return batch.status == 'removed' and bool((batch.actor or {}).get('closed_as_forgotten'))


def forgotten_batch_ids(session, case_id):
    return [batch.id for batch in session.scalars(select(Batch).where(Batch.case_id == case_id,
        Batch.status == 'removed')) if closed_as_forgotten(batch)]


def decision_items(session, case_id, file_ids):
    """Decision items (CARRIED_DECISIONS) of batches closed as forgotten, for these files."""
    ids = forgotten_batch_ids(session, case_id)
    if not ids or not file_ids:
        return []
    return list(session.scalars(select(Item).where(Item.batch_id.in_(ids), Item.file_id.in_(list(file_ids)),
        Item.status.in_(CARRIED_DECISIONS))))


def preview(session, *, case_id, batch_id):
    batch = session.scalar(select(Batch).where(Batch.id == batch_id, Batch.case_id == case_id))
    if batch is None:
        raise PdfMappingError('Batch not found in this case.', 404)
    counts = dict(session.execute(select(Item.status, func.count()).where(Item.batch_id == batch.id)
        .group_by(Item.status)).all())
    decisions = list(session.execute(select(Item.file_id, Item.status).where(Item.batch_id == batch.id,
        Item.status.in_(CARRIED_DECISIONS)).distinct()).all())
    only_here = 0
    for file_id, status in decisions:
        elsewhere = session.scalar(select(Item.id).join(Batch, Item.batch_id == Batch.id).where(
            Batch.case_id == case_id, Batch.id != batch.id, Batch.status != 'removed', Item.file_id == file_id,
            Item.status == status).limit(1))
        only_here += elsewhere is None
    operations = session.scalar(select(func.count()).select_from(Operation).where(Operation.batch_id == batch.id))
    return dict(case_id=str(case_id), batch_id=str(batch.id), status=batch.status,
        already_closed=closed_as_forgotten(batch), items=counts,
        left_unimported={key: counts.get(key, 0) for key in ('ready', 'attention')},
        decisions_carried=len(decisions), decisions_only_in_this_batch=only_here, import_operations=operations,
        transactions_withdrawn=0, statements_withdrawn=0, items_changed=0)


def close_forgotten_batch(session, *, case_id, batch_id, decision, apply=False, now=None):
    """Preview (and with ``apply`` commit) closing one batch as forgotten. ``decision`` names the person and the
    reason, e.g. 'Neil Byrne, 2026-11-01: forgotten October run, redundant'. Refuses a batch a worker still
    holds (pause it and wait for Paused), and a batch removed some other way."""
    if not (decision or '').strip():
        raise PdfMappingError('Record whose decision this is and why.', 400)
    now = now or datetime.now(timezone.utc)
    batch = session.scalar(select(Batch).where(Batch.id == batch_id, Batch.case_id == case_id).with_for_update())
    if batch is None:
        raise PdfMappingError('Batch not found in this case.', 404)
    out = preview(session, case_id=case_id, batch_id=batch_id)
    if out['already_closed']:
        session.rollback()
        return {**out, 'applied': False}
    if batch.status == 'removed':
        raise PdfMappingError('This batch was removed with its imports; it cannot be closed as forgotten.', 409)
    held = bool(batch.worker_token and batch.lease_until and batch.lease_until.replace(tzinfo=timezone.utc) > now)
    if held:
        raise PdfMappingError('A worker is still preparing this batch. Pause it and wait until it shows Paused.', 409)
    if not apply:
        session.rollback()
        return {**out, 'applied': False}
    actor = {key: value for key, value in (batch.actor or {}).items() if key != 'release_pause'}
    actor['closed_as_forgotten'] = dict(at=now.isoformat(), decision=decision.strip(), done_by=DONE_BY,
        previous_status=batch.status, left_unimported=out['left_unimported'],
        decisions_carried=out['decisions_carried'])
    batch.actor = actor
    batch.status = 'removed'
    batch.worker_token = None
    batch.lease_until = None
    session.commit()
    return {**out, 'status': 'removed', 'applied': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('case_id', type=UUID)
    parser.add_argument('batch_ids', type=UUID, nargs='+')
    parser.add_argument('--decision', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    from postgres.session import _get_session_local
    factory = _get_session_local()
    for batch_id in args.batch_ids:
        with factory() as session:
            try:
                print(json.dumps(close_forgotten_batch(session, case_id=args.case_id, batch_id=batch_id,
                    decision=args.decision, apply=args.apply), default=str))
            except PdfMappingError as exc:
                print(json.dumps(dict(batch_id=str(batch_id), refused=str(exc))))


if __name__ == '__main__':
    main()
