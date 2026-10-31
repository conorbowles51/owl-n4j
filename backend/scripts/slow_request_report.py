"""Read-only: each slow request beside its minute's host load, its worker's event-loop lag and release state.

    python scripts/slow_request_report.py                       # last 24 h, requests over 2 s, people only
    python scripts/slow_request_report.py --hours 6 --all-users --min-seconds 5 --limit 50
    python scripts/slow_request_report.py --summary              # per hour: slow requests, lag, host load, outages

Joins (all by minute, ``at`` is the request's completion time):
  * request_speed_slow (started_at, pid, pg_ms, cache) -> request_speed_loop_lag on (minute, pid);
  * -> host_load_minute on minute (CPU busy, CPU pressure, the fleet's and the backend's cores, swap-in);
  * -> availability_probe failures in that minute; -> releases (lx-release) when that table exists.
A row whose minute has no host or lag record says so ("-") rather than leaving it out.
Uses DATABASE_URL; one read-only transaction; never writes.
"""
import argparse
import os
import re
import sys

JOBS_USER = 'a2fd2e70-'  # the jobs login (prefix of its user id)

ROWS = '''
WITH slow AS (
  SELECT s.*, date_trunc('minute', s.at) AS m FROM request_speed_slow s
  WHERE s.at >= now() - make_interval(hours => %(hours)s) AND s.duration_ms >= %(min_ms)s
    AND (%(all_users)s OR (s.user_id IS NOT NULL AND CAST(s.user_id AS text) NOT LIKE %(jobs)s))
)
SELECT s.at, s.started_at, s.pid, s.method, s.route, left(CAST(s.case_id AS text), 8) AS case8,
       left(CAST(s.user_id AS text), 8) AS user8, s.status, s.duration_ms, s.pg_ms, s.pg_count, s.gzip_ms, s.cache,
       l.max_ms AS lag_max_ms, l.over_100ms, l.samples AS lag_samples,
       h.cpu_busy_cores, h.psi_cpu_some, h.load1, h.swap_in_pages,
       (SELECT sum((v->>'cores')::float) FROM jsonb_each(h.groups) g(k, v)
         WHERE k IN ('fleet.slice', 'system.slice/fin-watchdog.service')) AS fleet_cores,
       (SELECT sum((v->>'cores')::float) FROM jsonb_each(h.groups) g(k, v) WHERE k = 'loupe.slice') AS live_cores,
       (SELECT sum((v->>'cores')::float) FROM jsonb_each(h.groups) g(k, v) WHERE k ~ 'owl-backend-v2') AS backend_cores,
       (SELECT max((v->>'cpu_some')::float) FROM jsonb_each(h.groups) g(k, v) WHERE k ~ 'owl-backend-v2') AS backend_cpu_some,
       (SELECT count(*) FROM availability_probe a WHERE date_trunc('minute', a.at) = s.m
          AND (a.status IS NULL OR a.status >= 500)) AS probe_failures
       {release_columns}
FROM slow s
LEFT JOIN request_speed_loop_lag l ON l.minute = s.m AND l.pid = s.pid
LEFT JOIN host_load_minute h ON h.minute = s.m
ORDER BY s.at DESC LIMIT %(limit)s
'''
RELEASE_COLUMNS = ''',
       (SELECT r.sha FROM releases r WHERE r.started_at <= s.at ORDER BY r.started_at DESC LIMIT 1) AS release_sha,
       (SELECT round(extract(epoch FROM s.at - max(r.started_at))) FROM releases r WHERE r.started_at <= s.at)
         AS seconds_since_release'''

SUMMARY = '''
WITH hours AS (
  SELECT generate_series(date_trunc('hour', now() - make_interval(hours => %(hours)s)), date_trunc('hour', now()),
                         interval '1 hour') AS hour
)
SELECT hour,
  (SELECT count(*) FROM request_speed_slow s WHERE date_trunc('hour', s.at) = hour
     AND (%(all_users)s OR (s.user_id IS NOT NULL AND CAST(s.user_id AS text) NOT LIKE %(jobs)s))) AS slow,
  (SELECT max(max_ms) FROM request_speed_loop_lag l WHERE date_trunc('hour', l.minute) = hour) AS lag_max_ms,
  (SELECT round(100.0 * sum(over_100ms) / nullif(sum(samples), 0), 2) FROM request_speed_loop_lag l
     WHERE date_trunc('hour', l.minute) = hour) AS lag_over_100ms_pct,
  (SELECT round(avg(cpu_busy_cores)::numeric, 2) FROM host_load_minute h WHERE date_trunc('hour', h.minute) = hour) AS cpu_busy,
  (SELECT round(avg(psi_cpu_some)::numeric, 1) FROM host_load_minute h WHERE date_trunc('hour', h.minute) = hour) AS psi_cpu,
  (SELECT count(*) FROM host_load_minute h WHERE date_trunc('hour', h.minute) = hour) AS host_minutes,
  (SELECT count(*) FROM availability_probe a WHERE date_trunc('hour', a.at) = hour) AS probes,
  (SELECT count(*) FROM availability_probe a WHERE date_trunc('hour', a.at) = hour
     AND (a.status IS NULL OR a.status >= 500)) AS probe_failures
FROM hours ORDER BY hour
'''


def _fmt(value, width=7, digits=0):
    if value is None:
        return '-'.rjust(width)
    if isinstance(value, float):
        return f'{value:.{digits}f}'.rjust(width)
    return str(value).rjust(width)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--hours', type=int, default=24)
    parser.add_argument('--min-seconds', type=float, default=2.0)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--all-users', action='store_true', help='include the jobs login and anonymous requests')
    parser.add_argument('--summary', action='store_true')
    args = parser.parse_args(argv)
    import psycopg
    url = re.sub(r'^postgresql\+\w+://', 'postgresql://', os.environ.get('DATABASE_URL') or '')
    params = dict(hours=args.hours, min_ms=args.min_seconds * 1000, all_users=args.all_users, jobs=JOBS_USER + '%',
                  limit=args.limit)
    with psycopg.connect(url, connect_timeout=5, application_name='slow-request-report') as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '30s'")
            if args.summary:
                cur.execute(SUMMARY, params)
                print('hour (UTC)        slow  lagmax  lag>100ms%  cpu_busy  psi_cpu%  host_min  probes  failed')
                for r in cur.fetchall():
                    print(f'{r[0]:%Y-%m-%d %H:00} {_fmt(r[1], 6)} {_fmt(r[2], 7)} {_fmt(r[3], 11)} {_fmt(r[4], 9)} '
                          f'{_fmt(r[5], 9)} {_fmt(r[6], 9)} {_fmt(r[7], 7)} {_fmt(r[8], 7)}')
                return 0
            cur.execute("SELECT to_regclass('releases') IS NOT NULL")
            has_releases = cur.fetchone()[0]
            cur.execute(ROWS.format(release_columns=RELEASE_COLUMNS if has_releases else ''), params)
            names = [d.name for d in cur.description]
            rows = cur.fetchall()
    print(f'{len(rows)} slow requests (>= {args.min_seconds:g} s, last {args.hours} h, '
          f'{"all callers" if args.all_users else "people only"}; newest first'
          f'{"" if has_releases else "; no releases table yet"})')
    print('done (UTC)  start    pid      ms   pg_ms cache  lagmax >100  busy psi%  fleet  bkend bk_psi% down  route'
          '  (fleet: fleet.slice + fin-watchdog cores; bkend: the backend service cores)')
    for r in rows:
        r = dict(zip(names, r))
        print(f'{r["at"]:%m-%d %H:%M:%S} {r["started_at"]:%H:%M:%S} ' if r['started_at'] else f'{r["at"]:%m-%d %H:%M:%S} -        ',
              end='')
        print(f'{_fmt(r["pid"], 7)} {_fmt(r["duration_ms"], 6)} {_fmt(r["pg_ms"], 7)} {(r["cache"] or "-"):>5} '
              f'{_fmt(r["lag_max_ms"], 7)} {_fmt(r["over_100ms"], 4)} {_fmt(r["cpu_busy_cores"], 5, 1)} '
              f'{_fmt(r["psi_cpu_some"], 4)} {_fmt(r["fleet_cores"], 6, 2)} {_fmt(r["backend_cores"], 6, 2)} '
              f'{_fmt(r["backend_cpu_some"], 7, 1)} {_fmt(r["probe_failures"], 4)}  {r["method"]} {r["route"]}'
              + (f'  [release {r["release_sha"][:8]} +{r["seconds_since_release"]}s]' if r.get('release_sha') else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
