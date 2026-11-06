"""Tell the coordinator about AI spending at 80 % and at a limit: one FYI line per crossing, once.

Run as the fleet user each watchdog cycle. Notes crossings the evidence engine made too, since spend is read from the
cost records. With no limit saved it reads nothing else and sends nothing. --dry-run prints the count only.

    set -a; . <app>/.env; PYTHONPATH=. python scripts/deliver_ai_budget_alerts.py [--dry-run]
"""
import argparse
import subprocess
import sys

TELL = '/mnt/owl-data/fin-wt/headless/tell.sh'


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    from postgres.models.case import Case
    from postgres.session import _get_session_local
    from services import ai_budget
    sent = 0
    with _get_session_local()() as db:
        ai_budget.record_alerts(db)
        waiting = ai_budget.undelivered_alerts(db)
        if args.dry_run:
            print(f'undelivered={len(waiting)}')
            return 0
        for alert in waiting:
            case = db.get(Case, ai_budget._uuid(alert.get('case_id'))) if alert.get('case_id') else None
            result = subprocess.run([TELL, 'fyi', 'coordinator', 'ai-budget',
                                     ai_budget.alert_sentence(alert, case.title if case else None)],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                print(f'tell failed: exit {result.returncode}', file=sys.stderr)
                break
            ai_budget.mark_delivered(db, [alert['key']])
            sent += 1
    print(f'delivered={sent}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
