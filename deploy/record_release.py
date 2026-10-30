"""One row per release attempt in Postgres table ``releases`` (deploy.sh and deploy-now.sh call this at the end).

    python deploy/record_release.py <backend_dir> key=value ...

Columns: sha, live_before, source (deploy.sh / deploy-now), outcome, plan (what ran and what was skipped),
frontend_build (the build id served afterwards), started_at, finished_at, backend_restart_at, frontend_switch_at,
healthy_at (epoch seconds in, timestamptz stored), log_file. The table is created here when missing, so recording
never depends on a migration having run; the jobs measuring availability (lx-measure) read it. A failure to record is
printed and never fails a release.
"""
import sys
from datetime import datetime, timezone

DDL = """
CREATE TABLE IF NOT EXISTS releases (
    id bigserial PRIMARY KEY,
    sha text,
    live_before text,
    source text,
    outcome text,
    plan text,
    frontend_build text,
    started_at timestamptz,
    finished_at timestamptz,
    backend_restart_at timestamptz,
    frontend_switch_at timestamptz,
    healthy_at timestamptz,
    log_file text,
    recorded_at timestamptz NOT NULL DEFAULT now()
)
"""
COLUMNS = ('sha', 'live_before', 'source', 'outcome', 'plan', 'frontend_build', 'started_at', 'finished_at',
           'backend_restart_at', 'frontend_switch_at', 'healthy_at', 'log_file')
TIMES = {'started_at', 'finished_at', 'backend_restart_at', 'frontend_switch_at', 'healthy_at'}


def parse(args):
    values = {}
    for arg in args:
        key, _, value = arg.partition('=')
        if key not in COLUMNS:
            raise SystemExit('unknown column %s' % key)
        if value == '':
            values[key] = None
        elif key in TIMES:
            values[key] = datetime.fromtimestamp(int(value), tz=timezone.utc)
        else:
            values[key] = value
    return values


def main(argv):
    backend_dir, values = argv[1], parse(argv[2:])
    sys.path.insert(0, backend_dir)
    try:
        from sqlalchemy import create_engine, text
        from config import DATABASE_URL
        engine = create_engine(DATABASE_URL, pool_pre_ping=False)
        with engine.begin() as conn:
            conn.execute(text(DDL))
            names = sorted(values)
            conn.execute(text('INSERT INTO releases (%s) VALUES (%s)' % (
                ', '.join(names), ', '.join(':' + name for name in names))), values)
        engine.dispose()
        print('release recorded: %s %s' % ((values.get('sha') or '')[:8], values.get('outcome')))
    except Exception as exc:  # recording never fails a release
        print('release not recorded: %s' % exc)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
