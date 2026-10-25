"""Replace saved statement periods that the current reader proves wrong. Dry run by default.

The rule is ``services.financial.saved_reading_replacement`` (product code; this
command only calls it): a saved period is replaced, per period and never per
file, only when nobody typed or corrected its payments, exactly one statement
of the file's current reading is that period (same currency, printed dates,
account reference and ledger account), that reading proves under every
admission check exactly as a fresh untouched statement would, and its money
differs from what is saved.

DRY RUN (default): a READ ONLY transaction (refused if the database does not
accept it; any ORM write raises). Prints counts only: per outcome and reason,
and per period that would be replaced, saved and fresh payment counts and what
differs.

--apply: each period that would be replaced is imported through the strict
import writer as a replacement of its saved copy, proved again under the
writer's locks, in one transaction per period: the new reading is admitted and
the saved copy set aside, linked and restorable (actor "system: reader
replacement", adjudication and file history entry). Switch
LOUPE_FINANCIAL_REPLACE_SAVED_READING=0 refuses it.

--restore <source document id>: undoes one replacement exactly (either copy of
the pair may be named): the earlier copy counts again and the replacing reading
is set aside, linked. One transaction. Already restored: nothing changes. A restored period is never replaced
again automatically.

From ``backend/`` with the service environment loaded:

    python3 scripts/financial_replace_saved_reading.py --period <statement period uuid> ...
    python3 scripts/financial_replace_saved_reading.py --document <source document uuid> ... --apply
    python3 scripts/financial_replace_saved_reading.py --case <case uuid>      # every saved period of a case
    python3 scripts/financial_replace_saved_reading.py --all                    # every case (dry run)
    python3 scripts/financial_replace_saved_reading.py --restore <source document uuid>
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from uuid import UUID

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def _documents_for_periods(session, period_ids):
    from sqlalchemy import select
    from postgres.models.financial import FinancialStatementPeriod
    found = dict(session.execute(select(FinancialStatementPeriod.id, FinancialStatementPeriod.source_document_id)
                                 .where(FinancialStatementPeriod.id.in_([UUID(p) for p in period_ids]))).all())
    missing = [p for p in period_ids if UUID(p) not in found]
    if missing:
        raise SystemExit(f'Statement periods not found: {len(missing)}')
    return [str(found[UUID(p)]) for p in period_ids]


def dry_run(factory, *, case_ids=None, document_ids=None, period_ids=None):
    from scripts.financial_reader_recovery_estimate import read_only
    from services.financial.saved_reading_replacement import plan
    with factory() as session:
        read_only(session)
        if period_ids:
            document_ids = (document_ids or []) + _documents_for_periods(session, period_ids)
        results = plan(session, case_ids=case_ids, document_ids=document_ids)
        session.rollback()
    return results


def report(results):
    outcomes = Counter((r['outcome'], r.get('code')) for r in results)
    lines = [f'saved periods assessed: {len(results)}']
    for (outcome, code), count in sorted(outcomes.items(), key=lambda item: (item[0][0], str(item[0][1]))):
        lines.append(f'  {outcome}{" (" + code + ")" if code and outcome != "same" else ""}: {count}')
    for r in results:
        if r['outcome'] == 'replace':
            lines.append(f"  REPLACE period {r.get('period_id')} (document {r['document_id']}): saved payments "
                         f"{r.get('saved_payments')}, fresh payments {r.get('fresh_payments')}, differs "
                         f"{'+'.join(r.get('differs') or [])}, missing {r.get('missing_payments')}, extra "
                         f"{r.get('extra_payments')}, investigator work {'yes' if r.get('investigator_work') else 'no'}")
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--case', action='append', default=[])
    parser.add_argument('--document', action='append', default=[])
    parser.add_argument('--period', action='append', default=[])
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--restore')
    parser.add_argument('--json', help='write the per-period results (ids and counts only) to this file')
    args = parser.parse_args(argv)
    from postgres.session import _get_session_local
    factory = _get_session_local()
    if args.restore:
        if args.apply or args.case or args.document or args.period or args.all:
            parser.error('--restore takes one source document and nothing else')
        from sqlalchemy import select
        from postgres.models.financial import FinancialSourceDocument
        from services.financial.saved_reading_replacement import replacement_pair, restore_replacement
        with factory() as session:
            document = session.get(FinancialSourceDocument, UUID(args.restore))
            pair = replacement_pair(session, document) if document is not None else None
            # Either copy may be named; restore always brings the earlier saved copy back.
            case_id, replacing = (document.case_id, pair[0].id) if pair else (None, None)
            session.rollback()
        if document is None:
            raise SystemExit('Source document not found.')
        if pair is None:
            raise SystemExit('This statement was not replaced by a reading.')
        print(json.dumps(restore_replacement(session_factory=factory, case_id=case_id, document_id=replacing)))
        return 0
    if not (args.case or args.document or args.period or args.all):
        parser.error('name --case, --document, --period or --all')
    if args.all and args.apply:
        parser.error('--apply needs explicit --document or --period ids (or --case)')
    results = dry_run(factory, case_ids=args.case or None,
                      document_ids=args.document or None if (args.document or args.period) else None,
                      period_ids=args.period or None)
    print(report(results))
    if args.apply:
        from scripts.financial_reader_recovery_estimate import _resolver
        from services.financial.saved_reading_replacement import replace_document
        resolve_path = _resolver()
        applied = []
        for entry in [r for r in results if r['outcome'] == 'replace']:
            try:
                outcome = replace_document(session_factory=factory, case_id=entry['case_id'],
                                           document_id=entry['document_id'], resolve_path=resolve_path)
            except Exception as error:  # Reported per period; nothing of that period was written.
                outcome = {**{k: v for k, v in entry.items() if k != 'request'}, 'applied': False,
                           'refusal': str(error)[:300]}
            receipt = outcome.get('receipt') or {}
            print(f"  {'APPLIED' if outcome.get('applied') else 'NOT APPLIED'} period {entry.get('period_id')}: "
                  + (f"new document {receipt.get('source_document_id')}, payments {receipt.get('transaction_count')}"
                     if outcome.get('applied') else (outcome.get('refusal') or outcome.get('code') or '')))
            applied.append(outcome)
        results = applied + [r for r in results if r['outcome'] != 'replace']
    if args.json:
        Path(args.json).write_text(json.dumps([{k: v for k, v in r.items() if k != 'request'} for r in results],
                                              indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
