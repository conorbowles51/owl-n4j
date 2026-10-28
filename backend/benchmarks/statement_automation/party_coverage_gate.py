"""Release gate: do stored payments still name the other side? Read-only.

Counts, over every stored payment of every case, how many show a bare "Not
identified" (no name and no stated reason; services.financial.party_coverage)
per bank and per printed layout, with the code being released. The release
fails when a bank's bare share rises above the last released baseline by more
than the tolerance, or when a layout the baseline has not seen lands with more
than half of its payments bare.

The baseline is the last released measure (``--baseline``, written by
``--write-baseline`` after a healthy release); without one, the committed seed
beside this file is used.

From ``backend/`` with the service environment loaded::

    python -m benchmarks.statement_automation.party_coverage_gate --baseline ../deploy/logs/party-coverage-baseline.json \\
        --out /tmp/party-coverage.json

``--rows-json`` measures a saved export (a list of row dicts) instead of the database.
Exit 0: pass. Exit 1: the gate failed (reasons printed). Exit 2: it could not measure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

SEED = os.path.join(os.path.dirname(__file__), 'party_coverage_baseline.json')


def measure(rows_json=None):
    from services.financial.party_coverage import load_rows, tally, matched_ids
    if rows_json:
        with open(rows_json) as handle:
            return tally(json.load(handle))
    from sqlalchemy import text
    from postgres.session import _get_session_local
    with _get_session_local()() as session:
        session.execute(text('SET TRANSACTION READ ONLY'))
        rows = list(load_rows(session))
        return tally(rows, matched_ids(session, {row['case_id'] for row in rows}))


def main(argv=None):
    from services.financial.party_coverage import bare_share, compare
    from services.financial.payment_inference import VERSION
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--baseline', help='last released measure (falls back to the committed seed)')
    parser.add_argument('--rows-json', help='measure a saved export instead of the database')
    parser.add_argument('--out', help='write this measure here (JSON)')
    parser.add_argument('--write-baseline', help='write this measure as the new released baseline, then exit 0')
    args = parser.parse_args(argv)
    try:
        current = measure(args.rows_json)
    except Exception as error:  # noqa: BLE001 - reported, the caller decides
        print(f'party coverage: could not measure: {error}', file=sys.stderr)
        return 2
    current['version'] = VERSION
    total = current['total']
    print(f"party coverage ({VERSION}): {total['rows']} payments; named {total['named']}, unnamed with a reason "
          f"{total['reason']}, bare \"Not identified\" {total['bare']} ({bare_share(total) * 100:.1f}%)")
    for bank, counts in sorted(current['banks'].items(), key=lambda item: -item[1]['rows']):
        print(f"  {bank:14} {counts['rows']:7} payments  bare {counts['bare']:6} ({bare_share(counts) * 100:5.1f}%)  reason {counts['reason']:6}")
    for path in (args.out, args.write_baseline):
        if path:
            with open(path, 'w') as handle:
                json.dump(current, handle, indent=1, sort_keys=True)
    if args.write_baseline:
        return 0
    baseline_path = args.baseline if args.baseline and os.path.exists(args.baseline) else SEED
    with open(baseline_path) as handle:
        baseline = json.load(handle)
    failures = compare(current, baseline)
    if failures:
        print(f'PARTY COVERAGE GATE: FAIL against {baseline_path}')
        for failure in failures:
            print('  ' + failure)
        return 1
    print(f'PARTY COVERAGE GATE: PASS against {baseline_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
