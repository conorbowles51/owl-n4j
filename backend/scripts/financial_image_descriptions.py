"""Complete the descriptions of saved payments read from page images. Dry run by default.

The page-image reader read each payment's first printed line only; the counterparty is often on the lines under it.
This command (product code: ``services.financial.vision_descriptions`` and
``saved_reading_replacement.refresh_descriptions(from_images=True)``) works per saved statement:

DRY RUN (default): a READ ONLY transaction. Lists each saved statement in scope that holds payments read from page
images: how many, how many not yet read for their description lines, and what applying the lines already read would
change (assess_image_descriptions). Sends nothing.

--read: reads the description lines of the payments not yet read (one request per page, by the page-image reader
chain, within the case's reading budget; this costs) and stores that reading on the saved statement. Nothing is
applied by it.

--apply: each payment whose stored lines complete its description is superseded by the same payment with the
completed description, through the correction chain (names, category, link and notes go with it; the earlier row is
kept, linked; amount, direction, date and balance unchanged), one transaction per statement.

The same reading gives each payment's first line as the page prints it; where every read agrees on a first line that
differs from the saved one by a few characters, it is stored as a proposed correction (the dry run lists them).
--first-lines --for-name <person> --for-email <address> [--for-user-id <uuid>]: applies those corrections after any
--apply (only the payments named by --payment, when given), through the same correction chain, as the reading model's work for that person, shown as the model's reading
and not confirmed (saved_reading_replacement.correct_first_lines).

From ``backend/`` with the service environment loaded:

    python3 scripts/financial_image_descriptions.py --case <case uuid>               # dry run
    python3 scripts/financial_image_descriptions.py --document <source document uuid> --read
    python3 scripts/financial_image_descriptions.py --document <source document uuid> --apply
    python3 scripts/financial_image_descriptions.py --case <case uuid> --first-lines --for-name "Neil Byrne" \\
        --for-email neil@owlconsultancygroup.com --for-user-id <uuid>
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from uuid import UUID

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def documents(session, case_ids, document_ids):
    """Saved statements in scope that hold payments saved as read from page images."""
    from sqlalchemy import select
    from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
    query = (select(FinancialTransaction.source_document_id).distinct()
             .where(FinancialTransaction.ledger_status == 'admitted', FinancialTransaction.superseded_by_id.is_(None),
                    FinancialTransaction.source_document_id.is_not(None)))
    if case_ids:
        query = query.where(FinancialTransaction.case_id.in_([UUID(c) for c in case_ids]))
    if document_ids:
        query = query.where(FinancialTransaction.source_document_id.in_([UUID(d) for d in document_ids]))
    found = []
    for document_id in session.scalars(query):
        document = session.get(FinancialSourceDocument, document_id)
        if document is not None and document.status == 'admitted':
            found.append(document)
    return found


def survey(factory, case_ids, document_ids):
    from scripts.financial_reader_recovery_estimate import read_only
    from services.financial import vision_descriptions
    from services.financial.saved_reading_replacement import assess_first_line_fixes, assess_image_descriptions
    results = []
    with factory() as session:
        read_only(session)
        for document in documents(session, case_ids, document_ids):
            pairs = vision_descriptions.first_line_rows(session, document)
            if not pairs:
                continue
            stored = (document.metadata_ or {}).get(vision_descriptions.METADATA_KEY) or {}
            verdict = assess_image_descriptions(session, document)
            results.append(dict(verdict, page_image_payments=len(pairs),
                                not_read=len(vision_descriptions.not_looked(stored, pairs, session)),
                                kept_by_reading=dict(Counter(stored.get('kept', {}).values())),
                                first_lines=assess_first_line_fixes(session, document)))
        session.rollback()
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--case', action='append', default=[])
    parser.add_argument('--document', action='append', default=[])
    parser.add_argument('--read', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--first-lines', action='store_true')
    parser.add_argument('--for-name')
    parser.add_argument('--for-email')
    parser.add_argument('--for-user-id')
    parser.add_argument('--payment', action='append', default=[],
                        help='with --first-lines: correct only these payments (repeatable); the others stay proposed')
    parser.add_argument('--json', help='write the per-statement results to this file')
    args = parser.parse_args(argv)
    if not (args.case or args.document):
        parser.error('name --case or --document')
    if args.first_lines and not (args.for_name and args.for_email):
        parser.error('--first-lines needs --for-name and --for-email: the model reads for a person, never as them')
    from postgres.session import _get_session_local
    factory = _get_session_local()
    results = survey(factory, args.case, args.document)
    if args.read:
        from scripts.financial_reader_recovery_estimate import _resolver
        from services.financial.vision_descriptions import read_saved_lines
        resolve_path = _resolver()
        for entry in results:
            if not entry['not_read']:
                continue
            record = read_saved_lines(factory, entry['document_id'], resolve_path)
            print(f"  read document {entry['document_id']}: {record.get('status')} {record.get('reason') or ''} "
                  f"{record.get('completed', 0)} of {record.get('rows', 0)} completed, kept "
                  f"{dict(Counter((record.get('kept') or {}).values()))}, errors {len(record.get('errors') or [])}, "
                  f"${record.get('cost_usd') or 0:.4f}", flush=True)
        results = survey(factory, args.case, args.document)
    outcomes = Counter((r['outcome'], r.get('code')) for r in results)
    print(f'saved statements with page-image payments: {len(results)} ({sum(r["page_image_payments"] for r in results)} '
          f'payments, {sum(r["not_read"] for r in results)} not yet read for their description lines and printed first line)')
    for (outcome, code), count in sorted(outcomes.items(), key=lambda item: (item[0][0], str(item[0][1]))):
        print(f'  {outcome}{" (" + code + ")" if code and outcome != "same" else ""}: {count}')
    for r in results:
        if r['outcome'] == 'describe':
            print(f"  DESCRIBE document {r['document_id']}: {len(r['changes'])} of {r['page_image_payments']} "
                  f"payment descriptions gain printed lines; money untouched")
    for r in results:
        for change in (r.get('first_lines') or {}).get('changes') or []:
            print(f"  FIRST LINE document {r['document_id']} page {change['page']} payment "
                  f"{change['transaction_id']}: {change['first_line_before']!r} -> {change['first_line_after']!r} "
                  f"(read by {(change.get('read_by') or {}).get('model')})")
    if args.apply:
        from services.financial.saved_reading_replacement import refresh_descriptions
        applied = []
        for entry in [r for r in results if r['outcome'] == 'describe']:
            try:
                outcome = refresh_descriptions(session_factory=factory, case_id=entry['case_id'],
                                               document_id=entry['document_id'], from_images=True)
            except Exception as error:  # Reported per statement; nothing of that statement was written.
                outcome = dict(entry, applied=False, refusal=str(error)[:300])
            print(f"  {'APPLIED' if outcome.get('applied') else 'NOT APPLIED'} document {entry['document_id']}: "
                  + (f"{outcome.get('payments')} payment descriptions completed" if outcome.get('applied')
                     else (outcome.get('refusal') or outcome.get('code') or '')), flush=True)
            applied.append(outcome)
        results = applied + [r for r in results if r['outcome'] != 'describe']
    if args.first_lines:
        from services.financial.saved_reading_replacement import correct_first_lines
        scope = survey(factory, args.case, args.document) if args.apply else results
        if args.payment:
            proposed = {c['transaction_id'] for r in scope for c in (r.get('first_lines') or {}).get('changes') or []}
            for payment in sorted(set(args.payment) - proposed):
                print(f'  NO PROPOSAL for payment {payment}: not a current payment with a proposed first line (a '
                      f'payment corrected since has a new id; the dry run lists the current ones)')
        for entry in scope:
            if (entry.get('first_lines') or {}).get('outcome') != 'describe':
                continue
            try:
                outcome = correct_first_lines(session_factory=factory, case_id=entry['case_id'],
                                              document_id=entry['document_id'], for_name=args.for_name,
                                              for_email=args.for_email, for_user_id=args.for_user_id,
                                              only=set(args.payment) or None)
            except Exception as error:  # Reported per statement; nothing of that statement was written.
                outcome = dict(applied=False, refusal=str(error)[:300])
            print(f"  {'APPLIED' if outcome.get('applied') else 'NOT APPLIED'} first lines, document "
                  f"{entry['document_id']}: " + (f"{outcome.get('payments')} corrected (the model's reading, not "
                  f"confirmed)" if outcome.get('applied') else (outcome.get('refusal') or outcome.get('code') or '')),
                  flush=True)
            results.append(dict(document_id=entry['document_id'], first_lines_applied=outcome))
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
