"""Read the trades and holdings of every brokerage and investment-fund statement already in a case (lx-brokerage C).

Runs ``services.financial.brokerage_ledger.sync_document``, the same function every writer of a statement's cash rows
calls, over each admitted statement of a brokerage account, and ``sync_fund_statement`` (what the fund-statement
set-aside calls) over each file whose text names an investment-fund statement. It writes only ``financial_security_rows``; no cash row
is read for writing. Dry run (default): every statement is read and the counts printed, then rolled back.
``--apply`` commits, one statement per transaction.

    python -m scripts.financial_brokerage_rows [--case <id> ...] [--apply]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def brokerage_documents(session, cases=None):
    from sqlalchemy import select
    from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod
    from services.financial.brokerage_ledger import brokerage_institutions
    query = select(FinancialSourceDocument.id).join(
        FinancialStatementPeriod, FinancialStatementPeriod.source_document_id == FinancialSourceDocument.id).join(
        FinancialAccount, FinancialAccount.id == FinancialStatementPeriod.account_id).where(
        FinancialAccount.institution_name.in_(sorted(brokerage_institutions())))
    if cases:
        query = query.where(FinancialSourceDocument.case_id.in_(cases))
    return sorted(set(session.scalars(query)), key=str)


def fund_statement_files(session, cases=None):
    """Files whose text names an investment-fund statement (the cheap pre-check ``not_payment_statements`` uses)."""
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
    query = select(EvidenceFile.id).join(EvidenceDocumentText, EvidenceDocumentText.evidence_file_id == EvidenceFile.id
        ).where(EvidenceDocumentText.content.ilike('%FONDOS DE INVERSI%'))
    if cases:
        query = query.where(EvidenceFile.case_id.in_(cases))
    return sorted(set(session.scalars(query)), key=str)


def run_funds(factory, cases=None, *, apply=False):
    from services.financial.brokerage_ledger import sync_fund_statement
    totals = dict(files=0, fund_statements=0, copies=0, trades=0, holdings=0, lines_not_read=0, added=0, superseded=0,
                  unchanged=0)
    per_file = []
    with factory() as session:
        ids = fund_statement_files(session, cases)
    for file_id in ids:
        with factory() as session:
            out = sync_fund_statement(session, file_id, force=True)
            session.commit() if apply else session.rollback()
        per_file.append(out)
        totals['files'] += 1
        totals['fund_statements'] += bool(out['fund_statement'])
        totals['copies'] += bool(out['copy'])
        for key in ('trades', 'holdings', 'lines_not_read', 'added', 'superseded', 'unchanged'):
            totals[key] += out[key]
    return totals, per_file


def run(factory, cases=None, *, apply=False):
    from services.financial.brokerage_ledger import sync_document
    totals = dict(documents=0, admitted_documents=0, trades=0, holdings=0, lines_not_read=0, added=0, superseded=0,
                  unchanged=0, carried_corrections=0, dropped_corrections=0)
    per_document = []
    with factory() as session:
        ids = brokerage_documents(session, cases)
    for document_id in ids:
        with factory() as session:
            out = sync_document(session, document_id, force=True)
            if apply:
                session.commit()
            else:
                session.rollback()
        per_document.append(out)
        totals['documents'] += 1
        totals['admitted_documents'] += 1 if out['trades'] or out['holdings'] else 0
        for key in ('trades', 'holdings', 'lines_not_read', 'added', 'superseded', 'unchanged', 'carried_corrections',
                    'dropped_corrections'):
            totals[key] += out[key]
    return totals, per_document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--case', action='append', help='case id (repeat); default every case')
    parser.add_argument('--apply', action='store_true', help='commit (default: dry run, rolled back)')
    parser.add_argument('--out', type=Path, help='write the per-statement counts here (JSON, outside git)')
    args = parser.parse_args(argv)
    import uuid
    from postgres.session import _get_session_local
    cases = [uuid.UUID(c) for c in args.case] if args.case else None
    factory = _get_session_local()
    totals, per_document = run(factory, cases, apply=args.apply)
    funds, per_file = run_funds(factory, cases, apply=args.apply)
    print(json.dumps(dict(mode='apply' if args.apply else 'dry-run', brokerage_statements=totals,
                          fund_statements=funds), indent=2))
    if args.out:
        args.out.write_text(json.dumps(dict(brokerage=per_document, funds=per_file), indent=2, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
