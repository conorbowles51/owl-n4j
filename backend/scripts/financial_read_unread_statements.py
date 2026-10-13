"""Read statement files that are in Financial but were never read or prepared.

DRY RUN BY DEFAULT: opens a READ ONLY transaction (refuses to continue if the
database does not accept it, and refuses any ORM write) and prints, per case,
how many statement files the "Read N unread statement files" action would add
to the case's automatic batch: never read, read but never prepared, and exact
copies of files already in Financial (recorded as copies, not read).

``--apply`` performs the same action the queue button performs
(``services.financial.auto_read.read_unread``): the files join the case's
automatic batch (actor System) and the batch worker reads and prepares them
with bounded concurrency. Nothing is saved or admitted. A second run adds
nothing. Reverse: pause or remove the automatic batch in Financial.

Counts and opaque ids only. From ``backend/`` with the service environment loaded:

    python3 scripts/financial_read_unread_statements.py                 # dry run, all cases
    python3 scripts/financial_read_unread_statements.py --case <uuid>   # dry run, one case
    python3 scripts/financial_read_unread_statements.py --case <uuid> --apply
    python3 scripts/financial_read_unread_statements.py --case <uuid> --evidence           # also PDFs only in Evidence
    python3 scripts/financial_read_unread_statements.py --case <uuid> --evidence --apply

``--evidence`` also checks the case's Evidence PDFs that were never sent to
Financial (uploaded before automatic reading existed) with the statement
detector (first pages' text layer only), and reports those it recognises; with
``--apply`` they are marked for the automatic batch, which the worker sweep adds
and reads with the same bounded concurrency. Exact copies are recorded, not read.
"""
import argparse
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def financial_cases(session):
    from sqlalchemy import select, union
    from postgres.models.financial import FinancialSourceDocument
    from postgres.models.financial_import_batches import FinancialImportBatch
    from postgres.models.evidence import EvidenceFile
    rows = session.execute(union(select(FinancialImportBatch.case_id), select(FinancialSourceDocument.case_id),
        select(EvidenceFile.case_id).where(EvidenceFile.metadata_['financial_workspace'].is_not(None)))).all()
    return sorted({row[0] for row in rows}, key=str)


def plan(session, case_id):
    from services.financial.auto_read import plan_unread
    kept, copies = plan_unread(session, case_id=case_id)
    never_read = sum(f.status != 'processed' for f in kept)
    return dict(case_id=str(case_id), unread=len(kept) + len(copies), never_read=never_read,
                read_not_prepared=len(kept) - never_read, copies=len(copies), sample=[str(f.id)[:8] for f in kept[:5]])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--case', type=uuid.UUID, action='append', help='case id (repeatable); default all cases')
    parser.add_argument('--apply', action='store_true', help='add the files to the automatic batch')
    parser.add_argument('--evidence', action='store_true', help='also check Evidence PDFs never sent to Financial')
    args = parser.parse_args(argv)
    from postgres.session import _get_session_local
    from scripts.financial_reader_recovery_estimate import read_only
    factory = _get_session_local()
    with factory() as session:
        read_only(session)
        cases = args.case or financial_cases(session)
        plans = [plan(session, case_id) for case_id in cases]
        evidence = {}
        if args.evidence:
            from routers.evidence import _resolve_stored_path
            from services.financial.auto_read import evidence_statements
            for case_id in cases:
                keep, copies, checked = evidence_statements(session, case_id=case_id, resolve_path=_resolve_stored_path)
                evidence[case_id] = ([f.id for f in keep], [(f.id, r.id) for f, r in copies])
                print(f"case {str(case_id)[:8]}: Evidence PDFs checked {checked} | recognised statements to read {len(keep)} | "
                      f"exact copies of files in Financial {len(copies)}")
    total = 0
    for item in plans:
        total += item['unread']
        print(f"case {item['case_id'][:8]}: unread statement files {item['unread']} | never read {item['never_read']} | "
              f"read, never prepared {item['read_not_prepared']} | exact copies (not read) {item['copies']}"
              + (f" | e.g. {', '.join(item['sample'])}" if item['sample'] else ''))
    print(f'TOTAL unread statement files: {total}')
    if not args.apply:
        print('Dry run: nothing was written. Re-run with --apply (and --case) to read them.')
        return 0
    from services.financial.auto_read import read_unread, accept_evidence_statements
    from postgres.models.evidence import EvidenceFile
    for case_id, (keep, copies) in evidence.items():
        with factory() as session:
            files = [session.get(EvidenceFile, i) for i in keep]
            pairs = [(session.get(EvidenceFile, a), session.get(EvidenceFile, b)) for a, b in copies]
            accept_evidence_statements(session, case_id=case_id, files=files, copies=pairs)
        print(f"case {str(case_id)[:8]}: {len(keep)} Evidence statements marked for automatic reading, {len(copies)} copies recorded")
    for item in plans:
        if not item['unread']:
            continue
        with factory() as session:
            result = read_unread(session, case_id=uuid.UUID(item['case_id']))
        print(f"case {item['case_id'][:8]}: added {result['added']} to automatic batch "
              f"{(result['batch_id'] or '-')[:8]}, copies recorded {result['copies']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
