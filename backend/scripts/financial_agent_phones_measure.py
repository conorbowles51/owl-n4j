"""agent-phones D: on every case holding phones, approach 1 (money on the phones) computed in a READ ONLY
transaction (nothing is written): money readings bound, ambiguous and unbound to a ledger account, how they compare
with the ledger, and the leads; plus, where a completed run is stored, what the agent's tools read from it. The gate
of 05 4.7 needs at least 20 bound readings on a case with financial records.

Usage (from backend/, via live-run.sh): financial_agent_phones_measure.py [--json out.json]
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json')
    a = ap.parse_args()
    from services.agent import phone_cross_tools as X
    from services.phone_analysis import approaches
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
            if not k.phones:
                continue
            t0 = time.time()
            from services.phone_analysis import framework as F
            results, counts = MS.analyse(c, k.id, F.validate_parameters(MS, {}))
            readings = [r for r in results if r["kind"] == "money_reading"]
            leads = [r for r in results if r["kind"] == "account_lead"]
            binding = Counter(r["measures"]["binding"]["outcome"] for r in readings)
            outcome = Counter(r["measures"]["outcome"] for r in readings)
            status = Counter(r["measures"]["status"] for r in leads)
            row = {"case": str(k.id)[:8], "title": k.title, "phones": k.phones, "ledger_rows": k.rows,
                   "readings": len(readings), "bound": binding.get("bound", 0),
                   "ambiguous": binding.get("ambiguous", 0),
                   "unbound": len(readings) - binding.get("bound", 0) - binding.get("ambiguous", 0),
                   "binding": dict(binding), "outcome": dict(outcome), "leads": len(leads),
                   "lead_status": dict(status), "gate_20_bound": binding.get("bound", 0) >= 20,
                   "seconds": round(time.time() - t0, 1)}
            m = X.money_signal_matches(c, k.id)
            ld = X.money_signal_leads(c, k.id)
            row["stored_run"] = m.get("run_id")
            row["tool_matches"] = m["total_matching"]
            row["tool_leads"] = ld["total_matching"]
            row["tool_leads_by_ledger"] = ld.get("by_ledger")
            out.append(row)
            print(json.dumps(row), flush=True)
        c.rollback()
    if a.json:
        json.dump(out, open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
