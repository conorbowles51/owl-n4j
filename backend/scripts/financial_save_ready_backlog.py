"""Save the backlog of fully reconciled statements (statements read before automatic save existed).

Automatic save (``services.financial.queue_save.AUTO_SAVE_READY``) only fires
when a file's preparation ends, so statements prepared before deploy stay
ready in the review queue. This command is the explicit, audited way to save
that backlog with the same rule:

* a statement is saved only when today's admission (the batch save's own
  projection, ``validate_reviews=True, reading='all'``) says it is ready AND it
  has no check at all AND no investigator edit or draft;
* it is claimed with actor "System" under an ordinary import receipt, and the
  batch worker imports it (case lock, bounded retry), so it is reversible with
  the existing import removal;
* a second run saves nothing new (saved statements are no longer ready).

DRY RUN BY DEFAULT: a READ ONLY transaction; counts per case from the stored
queue (ready, of which without stored checks or edits). ``--check`` also runs
the full admission read-only for the candidates (slow: about 2.5 s per
statement) and counts what ``--apply`` would claim. ``--apply`` writes.

Counts and opaque case-id prefixes only. From ``backend/`` with the service
environment loaded:

    python3 scripts/financial_save_ready_backlog.py                      # dry run, every case
    python3 scripts/financial_save_ready_backlog.py --case <uuid> --check
    python3 scripts/financial_save_ready_backlog.py --case <uuid> --apply
"""
import argparse
import json
import sys
import uuid
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
CHUNK = 10


def _cases(session, requested):
    from sqlalchemy import select
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch
    if requested:
        return list(requested)
    return list(session.scalars(select(Batch.case_id).where(Batch.status != 'removed').distinct()
                                .order_by(Batch.case_id)))


def candidates(session, case_id):
    """(ready entries, candidate item ids): ready in the stored queue, no stored check, no edit or draft."""
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    from services.financial.review_queue import case_review_queue
    from services.financial.statement_progress import review_progress
    queue = case_review_queue(session, case_id=case_id, use_cache=False)
    ids = [uuid.UUID(entry['id']) for entry in queue['ready']]
    items = list(session.scalars(select(Item).where(Item.id.in_(ids)))) if ids else []
    files = {f.id: f for f in session.scalars(select(EvidenceFile).where(
             EvidenceFile.id.in_({i.file_id for i in items})))} if items else {}
    chosen = [i.id for i in items if not i.review_request and not (i.summary or {}).get('problems')
              and not (i.summary or {}).get('problem_count')
              and not (i.file_id in files and review_progress(files[i.file_id], i.statement_key))]
    return queue['counts'], chosen


def dry_run(factory, requested, check):
    from scripts.financial_reader_recovery_estimate import read_only
    rows = []
    with factory() as session:
        read_only(session)
        try:
            for case_id in _cases(session, requested):
                counts, chosen = candidates(session, case_id)
                row = dict(case=str(case_id)[:8], ready=counts['ready'], candidates=len(chosen))
                if check and chosen:
                    row.update(_check(session, case_id, chosen))
                rows.append(row)
        finally:
            session.rollback()
    return rows


def _check(session, case_id, ids):
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    from services.financial.import_batches import checked_batch_items, import_available
    from services.financial.queue_save import fully_reconciled
    items = list(session.scalars(select(Item).where(Item.id.in_(ids))))
    files = {f.id: f for f in session.scalars(select(EvidenceFile).where(
             EvidenceFile.id.in_({i.file_id for i in items})))}
    would, held = 0, 0
    for start in range(0, len(items), 50):
        part = items[start:start + 50]
        checked = {p.id: p for p in checked_batch_items(session, case_id, part, validate_reviews=True, reading='all')}
        for item in part:
            projection = checked[item.id]
            if import_available(projection) and fully_reconciled(item, projection, files.get(item.file_id)):
                would += 1
            else:
                held += 1
    return dict(would_save=would, would_hold=held)


def apply(factory, requested):
    from services.financial.queue_save import SYSTEM_ACTOR, save_statements
    rows = []
    with factory() as session:
        cases = _cases(session, requested)
        session.rollback()
    for case_id in cases:
        with factory() as session:
            counts, chosen = candidates(session, case_id)
            session.rollback()
        queued, held = 0, Counter()
        for start in range(0, len(chosen), CHUNK):
            with factory() as session:
                result = save_statements(session, case_id=case_id, item_ids=chosen[start:start + CHUNK],
                                         actor=SYSTEM_ACTOR, only_reconciled=True)
            queued += result['queued']
            held.update(entry['reason'] for entry in result['held'])
        rows.append(dict(case=str(case_id)[:8], ready=counts['ready'], candidates=len(chosen), queued=queued,
                         held=dict(held)))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--case', type=uuid.UUID, action='append', help='case id (repeatable); default every case for a dry run')
    parser.add_argument('--all-cases', action='store_true', help='required with --apply when no --case is given')
    parser.add_argument('--check', action='store_true', help='dry run: also run the full admission (read only, slow)')
    parser.add_argument('--apply', action='store_true', help='claim the statements for import as System (writes)')
    args = parser.parse_args(argv)
    from postgres.session import _get_session_local
    factory = _get_session_local()
    if args.apply:
        if not args.case and not args.all_cases:
            parser.error('--apply needs --case <id> or --all-cases')
        rows = apply(factory, args.case)
    else:
        rows = dry_run(factory, args.case, args.check)
    for row in rows:
        print(json.dumps(row, sort_keys=True))
    print(('APPLIED' if args.apply else 'DRY RUN') + ': ' + json.dumps(dict(
        ready=sum(r['ready'] for r in rows), candidates=sum(r['candidates'] for r in rows),
        **({'queued': sum(r['queued'] for r in rows)} if args.apply else
           {'would_save': sum(r.get('would_save', 0) for r in rows)} if args.check else {})), sort_keys=True))


if __name__ == '__main__':
    main()
