"""Set aside statements already saved twice in a case, as linked duplicates.

DRY RUN BY DEFAULT: opens a READ ONLY transaction (refuses to continue if the
database does not accept it, and refuses any ORM write) and prints what a
set-aside would do, per case and per file pair: periods set aside, payments
leaving totals, which copy is retained, and pairs held because their money
differs. Nothing is written.

The rule and the retained copy are those of
``services.financial.admitted_statement_duplicates`` (the product code; this
command only calls it). ``--apply`` performs the set-aside through the same
functions: each copy becomes a superseded document linked to the retained copy
with an adjudication (actor "system: duplicate set-aside") and a file history
entry; its batch items show "Duplicate - Ignored by system". A second run
changes nothing. ``--restore`` undoes one set-aside; ``--keep`` swaps which
copy is retained. The graph follows through the service's drift check.

The report holds counts and opaque ids only (file sha256 prefixes, document
ids). From ``backend/`` with the service environment loaded:

    python3 scripts/financial_set_aside_admitted_duplicates.py                 # dry run, all cases
    python3 scripts/financial_set_aside_admitted_duplicates.py --case <uuid>   # dry run, one case
    python3 scripts/financial_set_aside_admitted_duplicates.py --case <uuid> --apply
    python3 scripts/financial_set_aside_admitted_duplicates.py --case <uuid> --restore <document uuid>
    python3 scripts/financial_set_aside_admitted_duplicates.py --case <uuid> --keep <document uuid> --reason "..."
"""
import argparse
import json
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def _prefix(value):
    return (value or '?')[:12]


def summarise(plan):
    """Counts per case and per file pair; opaque ids only."""
    pairs = defaultdict(lambda: dict(periods=0, transactions=0, saved_first_rule_differs=0))
    for entry in plan['set_aside']:
        pair = pairs[(_prefix(entry['file_sha256']), _prefix(entry['retained_file_sha256']))]
        pair['periods'] += 1
        pair['transactions'] += entry['transactions']
        pair['saved_first_rule_differs'] += not entry['retained_saved_first']
    held = defaultdict(Counter)
    for entry in plan['held'] + plan['kept'] + plan['restored']:
        held[(_prefix(entry['file_sha256']), _prefix(entry['retained_file_sha256']))][entry['code']] += 1
    return dict(case_id=plan['case_id'], saved_copies=plan['saved_copies'],
        set_aside_periods=len(plan['set_aside']),
        transactions_leaving_totals=sum(e['transactions'] for e in plan['set_aside']),
        held=dict(Counter(e['code'] for e in plan['held'])), kept_by_investigator=len(plan['kept']),
        restored=len(plan['restored']), already_set_aside=len(plan['already_set_aside']),
        not_compared=plan['not_compared'],
        pairs=[dict(set_aside_file=a, retained_file=b, **values) for (a, b), values in sorted(pairs.items())],
        held_pairs=[dict(file=a, retained_file=b, codes=dict(codes)) for (a, b), codes in sorted(held.items())])


def render(summaries, *, applied=None):
    lines = []
    total = Counter()
    for item in summaries:
        total.update(periods=item['set_aside_periods'], transactions=item['transactions_leaving_totals'],
                     held=sum(item['held'].values()), already=item['already_set_aside'])
        lines.append(f"case {item['case_id'][:8]}: saved copies {item['saved_copies']} | set aside "
                     f"{item['set_aside_periods']} periods, {item['transactions_leaving_totals']} payments leave totals | "
                     f"held {item['held'] or 0} | kept by investigator {item['kept_by_investigator']} | "
                     f"restored {item['restored']} | already set aside {item['already_set_aside']} | "
                     f"not compared {item['not_compared'] or 0}")
        for pair in item['pairs']:
            lines.append(f"  pair d{pair['set_aside_file']} -> retained d{pair['retained_file']}: {pair['periods']} periods, "
                         f"{pair['transactions']} payments; retained copy saved later for {pair['saved_first_rule_differs']}")
        for pair in item['held_pairs']:
            lines.append(f"  held d{pair['file']} vs d{pair['retained_file']}: {pair['codes']}")
    lines.append(f"TOTAL: {total['periods']} periods set aside, {total['transactions']} payments leave totals, "
                 f"{total['held']} held, {total['already']} already set aside")
    if applied is not None:
        lines.append(f"APPLIED: {applied['applied']} set aside, {applied['refused']} refused")
    return '\n'.join(lines) + '\n'


def _cases(session, requested):
    from sqlalchemy import select
    from postgres.models.financial import FinancialSourceDocument
    if requested:
        return list(requested)
    return list(session.scalars(select(FinancialSourceDocument.case_id).where(
        FinancialSourceDocument.document_type == 'statement_review').distinct().order_by(FinancialSourceDocument.case_id)))


def dry_run(factory, requested):
    from scripts.financial_reader_recovery_estimate import read_only
    from services.financial.admitted_statement_duplicates import find_admitted_duplicates
    with factory() as session:
        read_only(session)
        try:
            plans = [find_admitted_duplicates(session, case_id) for case_id in _cases(session, requested)]
        finally:
            session.rollback()
    return plans


def apply(factory, requested):
    from services.financial.admitted_statement_duplicates import set_aside_admitted_duplicates
    plans, applied, refused = [], [], []
    with factory() as session:
        cases = _cases(session, requested)
        session.rollback()
        for case_id in cases:
            result = set_aside_admitted_duplicates(session, case_id)
            plans.append(result['plan'])
            applied += result['applied']
            refused += result['refused']
    return plans, applied, refused


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--case', type=uuid.UUID, action='append', help='case id (repeatable); default every case for a dry run')
    parser.add_argument('--all-cases', action='store_true', help='required with --apply when no --case is given')
    parser.add_argument('--apply', action='store_true', help='perform the set-aside (writes); default is a read-only dry run')
    parser.add_argument('--restore', type=uuid.UUID, help='restore one set-aside copy (source document id); needs --case')
    parser.add_argument('--keep', type=uuid.UUID, help='keep this set-aside copy instead of its retained copy; needs --case and --reason')
    parser.add_argument('--reason', default='', help='reason recorded with --restore or --keep')
    parser.add_argument('--out', type=Path, help='directory for report.json (document ids; keep outside git)')
    args = parser.parse_args(argv)
    from postgres.session import _get_session_local
    factory = _get_session_local()
    if args.restore or args.keep:
        if not args.case or len(args.case) != 1 or (args.restore and args.keep):
            parser.error('--restore/--keep need exactly one --case and one document')
        from services.financial import admitted_statement_duplicates as admitted
        with factory() as session:
            if args.restore:
                result = admitted.restore_copy(session, case_id=args.case[0], document_id=args.restore,
                    reason=args.reason.strip() or admitted.RESTORE_REASON)
            else:
                if not args.reason.strip():
                    parser.error('--keep needs --reason')
                result = admitted.keep_copy(session, case_id=args.case[0], document_id=args.keep,
                    actor=admitted.SYSTEM_ACTOR, reason=args.reason.strip())
        print(json.dumps(result, indent=1, sort_keys=True, default=str))
        return
    applied = None
    if args.apply:
        if not args.case and not args.all_cases:
            parser.error('--apply needs --case <id> or --all-cases')
        plans, done, refused = apply(factory, args.case)
        applied = dict(applied=len(done), refused=len(refused))
    else:
        plans = dry_run(factory, args.case)
        refused = []
    summaries = [summarise(plan) for plan in plans]
    text = render(summaries, applied=applied)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'report.json').write_text(json.dumps(dict(summaries=summaries, plans=plans,
            refused=refused, applied=applied), indent=1, sort_keys=True, default=str) + '\n')
        (args.out / 'report.md').write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
