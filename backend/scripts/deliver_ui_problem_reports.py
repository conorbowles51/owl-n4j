"""Tell the coordinator about new Report a problem reports: ids, kinds, counts and the build id only.

Run as the fleet user (it calls headless/tell.sh). Each undelivered report becomes one FYI line in the
coordinator's inbox, built by services.ui_problem_reports.jobs_message, then delivered_at is set. Reports from
the jobs login or the verification case are test reports: skipped unless --include-test. --dry-run prints the
count only. Never prints a report's text.

    set -a; . <app>/.env; PYTHONPATH=. python scripts/deliver_ui_problem_reports.py [--dry-run] [--include-test]
"""
import argparse
import subprocess
import sys
from datetime import datetime, timezone

TELL = '/mnt/owl-data/fin-wt/headless/tell.sh'


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--include-test', action='store_true')
    args = ap.parse_args(argv)
    from postgres.session import _get_session_local
    from services import ui_problem_reports as reports
    sent = 0
    with _get_session_local()() as db:
        rows = reports.undelivered(db, include_test=args.include_test)
        if args.dry_run:
            print(f'undelivered={len(rows)}')
            return 0
        for row in rows:
            result = subprocess.run([TELL, 'fyi', 'coordinator', 'ui-problem-report', reports.jobs_message(row)],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                print(f'tell failed for {reports.reference(row)}: exit {result.returncode}', file=sys.stderr)
                break
            row.delivered_at = datetime.now(timezone.utc)
            db.commit()
            sent += 1
    print(f'delivered={sent}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
