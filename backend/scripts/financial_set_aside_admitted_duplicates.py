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

A copy equal in everything but its ledger account (another reader filed it
under another bank wording or product type) is listed under "split across
accounts" with the account merge it needs and what blocks that merge. It is
set aside only with ``--apply --across-accounts`` and only when its files are
one document (identical bytes or stored identical page images); the accounts
are never merged by this command. ``--render-pages`` (dry run only) renders the
files of saved copies that share a period, read only, so the report shows which
pairs are one document before any page identity is stored; nothing is stored.

The report holds counts and opaque ids only (file sha256 prefixes, document
ids). From ``backend/`` with the service environment loaded:

    python3 scripts/financial_set_aside_admitted_duplicates.py                 # dry run, all cases
    python3 scripts/financial_set_aside_admitted_duplicates.py --case <uuid>   # dry run, one case
    python3 scripts/financial_set_aside_admitted_duplicates.py --case <uuid> --render-pages   # dry run, pages rendered
    python3 scripts/financial_set_aside_admitted_duplicates.py --case <uuid> --apply
    python3 scripts/financial_set_aside_admitted_duplicates.py --case <uuid> --apply --across-accounts
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
    split = [dict(set_aside_file=_prefix(e['file_sha256']), retained_file=_prefix(e['retained_file_sha256']),
                  transactions=e['transactions'], basis=e['basis'], automatic=e['automatic'],
                  merge_blockers=e['account_merge']['blockers'],
                  other_saved_periods_in_copy_account=e['account_merge']['other_saved_periods_in_copy_account'])
             for e in plan.get('split_across_accounts', [])]
    return dict(case_id=plan['case_id'], saved_copies=plan['saved_copies'],
        set_aside_periods=len(plan['set_aside']),
        transactions_leaving_totals=sum(e['transactions'] for e in plan['set_aside']),
        set_aside_by_basis=dict(Counter(e.get('basis') for e in plan['set_aside'])), rendered_files=plan.get('rendered_files', 0),
        split_across_accounts=split,
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
        for pair in item['split_across_accounts']:
            total.update(split=1, split_transactions=pair['transactions'], split_automatic=int(pair['automatic']))
            lines.append(f"  split across accounts d{pair['set_aside_file']} -> retained d{pair['retained_file']}: "
                         f"{pair['transactions']} payments counted twice; proof {pair['basis']}; "
                         f"{'set aside with --across-accounts' if pair['automatic'] else 'not one document: set aside by a person'}; "
                         f"account merge blocked by {pair['merge_blockers'] or 'nothing'}; "
                         f"other saved periods in the copy's account {pair['other_saved_periods_in_copy_account']}")
    lines.append(f"TOTAL: {total['periods']} periods set aside, {total['transactions']} payments leave totals, "
                 f"{total['held']} held, {total['already']} already set aside; split across accounts "
                 f"{total['split']} periods ({total['split_transactions']} payments counted twice, "
                 f"{total['split_automatic']} one document)")
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


def rendered_identities(session, case_id, resolve_path=None):
    """Page identities of the files of saved copies sharing a period, rendered now. Stores nothing.

    Files that already carry a comparable stored identity are not rendered.
    Evidence files are only opened for reading.
    """
    from services.financial import admitted_statement_duplicates as admitted, page_identity
    from scripts.financial_reader_recovery_estimate import _resolver
    resolve_path = resolve_path or _resolver()
    buckets = defaultdict(list)
    for copy in admitted._load(session, case_id):
        if copy.document.status == 'admitted' and copy.scope and copy.file is not None:
            buckets[(copy.scope['currency'], copy.scope['start'], copy.scope['end'])].append(copy.file)
    identities = {}
    for files in buckets.values():
        if len({f.id for f in files}) < 2:
            continue
        for file in files:
            key = str(file.id)
            if key in identities or page_identity.stored(file) or not file.stored_path:
                continue
            path = resolve_path(file.stored_path)
            value = page_identity.identity_of_path(path, file.sha256) if path else None
            if value:
                identities[key] = value
    return identities


def dry_run(factory, requested, *, render_pages=False):
    from scripts.financial_reader_recovery_estimate import read_only
    from services.financial.admitted_statement_duplicates import find_admitted_duplicates
    with factory() as session:
        read_only(session)
        try:
            plans = []
            for case_id in _cases(session, requested):
                identities = rendered_identities(session, case_id) if render_pages else None
                plan = find_admitted_duplicates(session, case_id, identities=identities)
                plan['rendered_files'] = len(identities or {})
                plans.append(plan)
        finally:
            session.rollback()
    return plans


def apply(factory, requested, *, across_accounts=False):
    from services.financial.admitted_statement_duplicates import set_aside_admitted_duplicates
    plans, applied, refused = [], [], []
    with factory() as session:
        cases = _cases(session, requested)
        session.rollback()
        for case_id in cases:
            result = set_aside_admitted_duplicates(session, case_id, across_accounts=across_accounts)
            plans.append(result['plan'])
            applied += result['applied']
            refused += result['refused']
    return plans, applied, refused


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--case', type=uuid.UUID, action='append', help='case id (repeatable); default every case for a dry run')
    parser.add_argument('--all-cases', action='store_true', help='required with --apply when no --case is given')
    parser.add_argument('--apply', action='store_true', help='perform the set-aside (writes); default is a read-only dry run')
    parser.add_argument('--across-accounts', action='store_true',
                        help='with --apply: also set aside copies split across two ledger accounts whose files are one document')
    parser.add_argument('--render-pages', action='store_true',
                        help='dry run: render files of copies sharing a period (read only) to find page-identical pairs')
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
        if args.render_pages:
            parser.error('--render-pages is for the dry run; --apply uses stored page identities only')
        plans, done, refused = apply(factory, args.case, across_accounts=args.across_accounts)
        applied = dict(applied=len(done), refused=len(refused))
    else:
        if args.across_accounts:
            parser.error('--across-accounts needs --apply')
        plans = dry_run(factory, args.case, render_pages=args.render_pages)
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
