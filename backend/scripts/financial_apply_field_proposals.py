"""Fill held statements' missing details that the case establishes exactly (field proposals).

DRY RUN BY DEFAULT: opens a READ ONLY transaction and prints, per case, what the
review queue proposes for statements waiting for a currency, bank, holder or
account number, which proposals are confirmed automatically, how many queue
statements every one of whose problems is filled ("Details filled
automatically"), and the grouped changes a save would make. Nothing is written.

The proposals and their limits are those of ``services.financial.field_proposals``
(the product code; this command only calls it). ``--apply`` saves the CONFIRMED
proposals only, through the existing statement-details save (the same path as
the investigator's "Resolve N together"), with actor "System" and the proposal's
source recorded in each file's account-detail history; mode fill-missing (a
masked account number is replaced by the full one). Saving checks each
statement again: it becomes ready, or stays in the queue with its real problem.
An investigator changes any value in the same dialog. A second run changes
nothing. This is the retroactive path for statements read before deploy; it
never runs by itself.

The report holds counts only. From ``backend/`` with the service environment loaded:

    python3 scripts/financial_apply_field_proposals.py --case <uuid>            # dry run
    python3 scripts/financial_apply_field_proposals.py --case <uuid> --apply
"""
import argparse
import json
import sys
import uuid
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def summarise(queue, report):
    proposals = Counter()
    for entry in queue['items'] + queue.get('filled', []):
        for name, proposal in (entry.get('proposals') or {}).items():
            proposals[f"{name}:{proposal['basis']}:{'confirmed' if proposal['confirmed'] else 'one-click'}"] += 1
    return dict(case_id=queue['case_id'], waiting=queue['counts']['waiting'], filled=queue['counts'].get('filled', 0),
                proposals=dict(sorted(proposals.items())),
                save=dict(statements=report['statements'], saved=report['saved'], failed=report['failed'],
                          groups=[dict(fields=sorted(g['changes']), statements=g['statements'],
                                       would_update=g.get('would_update'), updated=g.get('updated'),
                                       error=g.get('error')) for g in report['groups']]))


def _read_only_session():
    """A session on one connection that refuses writes for every transaction (database and ORM)."""
    from sqlalchemy import event, text
    from sqlalchemy.orm import Session
    from postgres.session import _get_engine
    connection = _get_engine().connect()
    if connection.dialect.name == 'postgresql':
        connection.execute(text('SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY'))
        connection.commit()
    session = Session(bind=connection, autoflush=False)

    @event.listens_for(session, 'before_flush')
    def _refuse(*_args):
        raise RuntimeError('The dry run attempted a write; nothing was written.')
    return session, connection


def run(factory, case_id, apply):
    from services.financial.field_proposals import apply_confirmed_proposals
    from services.financial.review_queue import case_review_queue
    session, connection = (factory(), None) if apply else _read_only_session()
    try:
        queue = case_review_queue(session, case_id=case_id, use_cache=False)
        entries = queue['items'] + queue.get('filled', [])
        report = apply_confirmed_proposals(session, case_id=case_id, entries=entries, apply=apply)
    finally:
        session.rollback()
        session.close()
        if connection is not None:
            connection.invalidate()  # never return a read-only connection to the pool
            connection.close()
    return summarise(queue, report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--case', type=uuid.UUID, action='append', required=True, help='case id (repeatable)')
    parser.add_argument('--apply', action='store_true', help='save confirmed proposals (writes); default is a dry run')
    args = parser.parse_args(argv)
    from postgres.session import _get_session_local
    factory = _get_session_local()
    results = [run(factory, case_id, args.apply) for case_id in args.case]
    print(json.dumps(dict(apply=args.apply, cases=results), indent=1, sort_keys=True))


if __name__ == '__main__':
    main()
