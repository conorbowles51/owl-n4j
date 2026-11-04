"""05 4.3.8 (M-1f): on every case holding phones, approach 1 computed in a READ ONLY transaction (nothing is written):
before, the matches the outcome rule offers (corroborated, near amount, several candidates); after, every candidate
pairing by strength, readings with at least one, rows the search bound left out, and decided pairings.

Usage (from backend/, via live-run.sh): financial_money_pairings_measure.py [--json out.json] [--case <id>]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter

sys.path.insert(0, '.')

from sqlalchemy import text  # noqa: E402

from postgres.session import _get_engine  # noqa: E402

MATCHED = ("corroborated", "near_amount", "several_candidates")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json')
    ap.add_argument('--case')
    a = ap.parse_args()
    from services.phone_analysis import approaches, framework as F
    from services.phone_analysis import money_pairings as MP
    from services.phone_analysis import money_signals as MS
    approaches.install()
    out = []
    with _get_engine().connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        cases = c.execute(text(
            "SELECT k.id, k.title, (SELECT count(*) FROM phone_extractions e WHERE e.case_id = k.id AND e.standing = "
            "'active') AS phones, (SELECT count(*) FROM financial_transactions t WHERE t.case_id = k.id AND "
            "t.ledger_status = 'admitted') AS rows FROM cases k ORDER BY k.title")).fetchall()
        for k in cases:
            if not k.phones or (a.case and str(k.id) != a.case):
                continue
            t0 = time.time()
            results, counts = MS.analyse(c, k.id, F.validate_parameters(MS, {}))
            readings = [r for r in results if r["kind"] == "money_reading"]
            before = Counter(r["measures"]["outcome"] for r in readings if r["measures"]["outcome"] in MATCHED)
            levels, best, left = Counter(), Counter(), Counter()
            with_any = 0
            for r in readings:
                m = r["measures"]
                if m["pairings"]:
                    with_any += 1
                    best[m["pairings"][0]["level"]] += 1
                for p in m["pairings"]:
                    levels[p["level"]] += 1
                for key, v in (m["pairings_left_out"] or {}).items():
                    if isinstance(v, int):
                        left[key] += v
            decided = MP.case_decisions(c, k.id)
            row = {"case": str(k.id), "title": k.title, "phones": k.phones, "ledger_rows": k.rows,
                   "readings": len(readings), "before_offered": sum(before.values()), "before_by_outcome": dict(before),
                   "after_readings_with_a_pairing": with_any,
                   "after_pairings_by_strength": {lv: levels.get(lv, 0) for lv in MP.LEVELS},
                   "after_readings_by_best_strength": {lv: best.get(lv, 0) for lv in MP.LEVELS},
                   "left_out_by_search_bound": dict(left),
                   "decided": Counter(d["state"] for d in decided.values() if d["state"]),
                   "seconds": round(time.time() - t0, 2)}
            out.append(row)
            print(json.dumps(row, default=str))
        c.rollback()
    if a.json:
        with open(a.json, 'w') as f:
            json.dump({"measured": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cases": out}, f, indent=1,
                      default=str)


if __name__ == '__main__':
    main()
