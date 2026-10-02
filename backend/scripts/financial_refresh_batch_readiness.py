"""Backfill stored batch readiness, using the same code path as the worker.

Batch list reads no longer re-read statement PDFs. Items prepared before the
readiness record existed (older summaries without bank/product identity, or
whose assessment needs a re-reading) are shown as "Readiness being updated"
until the write side refreshes them. The background sweep in the batch worker
does this within a bounded time per minute; this command does the same work
for chosen cases at once.

From `backend/`, with the service environment loaded:

    python3 scripts/financial_refresh_batch_readiness.py --all --dry-run
    python3 scripts/financial_refresh_batch_readiness.py --case <case-uuid>

`--dry-run` reports counts inside a read-only transaction and writes nothing.
Output is counts and case ids only, never financial values.
"""
import argparse
import os
import sys
import time
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--case', type=UUID, action='append', help='case id (repeatable)')
    target.add_argument('--all', action='store_true', help='every case with active batch items')
    parser.add_argument('--dry-run', action='store_true', help='count the backlog only; write nothing')
    parser.add_argument('--budget', type=float, default=None, help='seconds per case (default: until done)')
    args = parser.parse_args()

    from sqlalchemy import select, text
    from postgres.session import _get_session_local
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    from services.financial import import_batches

    factory = _get_session_local()
    with factory() as db:
        cases = args.case or list(db.scalars(select(Batch.case_id).join(Item, Item.batch_id == Batch.id).where(
            Batch.status != 'removed', Item.status.in_(import_batches.PROJECTED_STATUSES)).distinct()))
    for case_id in cases:
        started = time.monotonic()
        with factory() as db:
            if args.dry_run:
                if db.get_bind().dialect.name == 'postgresql':
                    db.execute(text('SET TRANSACTION READ ONLY'))
                from services.financial.statement_import_overlap import needs_hydration
                items = list(db.scalars(select(Item).join(Batch, Batch.id == Item.batch_id).where(
                    Batch.case_id == case_id, Batch.status != 'removed',
                    Item.status.in_(('ready', 'attention', 'pending_import')))))
                stale, unhydrated = import_batches.readiness_backlog(db, case_id)
                print(f'{case_id}: identity_missing={sum(needs_hydration(i) for i in items)} '
                      f'held_for_readiness={len(stale)} comparison_waiting_on={len(unhydrated)} '
                      f'({time.monotonic() - started:.1f}s)', flush=True)
                db.rollback()
            else:
                outcome = import_batches.refresh_case_readiness(db, case_id=case_id, budget_seconds=args.budget)
                print(f'{case_id}: {outcome} ({time.monotonic() - started:.1f}s)', flush=True)


if __name__ == '__main__':
    main()
