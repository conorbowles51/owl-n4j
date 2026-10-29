"""Who did what, from where: query the activity trail from the server.

    cd backend && env PYTHONPATH=. ../.venv/bin/python scripts/activity_query.py \
        [--case <case id or exact title>] [--user <email or name>] [--action financial_send ...] \
        [--since 2026-10-27] [--until 2026-10-28] [--limit 200] [--json]

Read only. Times are UTC. Actions: login_success, login_failure, logout,
evidence_upload, financial_send, financial_auto_add.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _day(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc) if 'T' not in value else datetime.fromisoformat(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--case')
    parser.add_argument('--user')
    parser.add_argument('--action', nargs='*')
    parser.add_argument('--since', help='YYYY-MM-DD (UTC) or ISO time')
    parser.add_argument('--until', help='YYYY-MM-DD (UTC, inclusive day) or ISO time')
    parser.add_argument('--limit', type=int, default=200)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    from sqlalchemy import select
    from postgres.session import _get_session_local
    from postgres.models.case import Case
    from services.activity_trail import list_events
    with _get_session_local()() as db:
        case_id = None
        if args.case:
            try:
                case_id = UUID(args.case)
            except ValueError:
                case_id = db.scalar(select(Case.id).where(Case.title == args.case))
                if case_id is None:
                    parser.error(f'No case titled {args.case}')
        until = _day(args.until) + (timedelta(days=1) if args.until and 'T' not in args.until else timedelta()) if args.until else None
        result = list_events(db, case_id=case_id, user=args.user, action=args.action or None,
                             since=_day(args.since) if args.since else None, until=until, limit=args.limit)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0
    print(f"{result['total']} event(s){' (showing ' + str(len(result['events'])) + ')' if result['total'] > len(result['events']) else ''}")
    for event in result['events']:
        details = event['details']
        files = details.get('files') or []
        extra = []
        if details.get('reason'):
            extra.append(f"reason={details['reason']}")
        if details.get('batch_id'):
            extra.append(f"batch={details['batch_id']}")
        print(f"{event['at']}  {event['action']:<18} {event['user_name'] or event['user_email'] or '-':<24} "
              f"from={event['source_address'] or 'not recorded':<16} via={event['origin_label'] or '-'}  "
              f"case={event['case_id'] or '-'} {' '.join(extra)}")
        if event['user_agent']:
            print(f"    agent: {event['user_agent']}  sign-in: {event['session_ref'] or '-'}")
        for file in files:
            print(f"    {file.get('filename')}  sha256={file.get('sha256')}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
