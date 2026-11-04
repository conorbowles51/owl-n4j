"""lx-matchgrades: read-only timing of the Transfers workbench answer on a date scope under 500 rows (3 runs each),
and of the whole-case graded pairs. Usage: <case> <start> <end>"""
import sys, time, json
sys.path.insert(0, '.')
from datetime import date
from postgres.session import _get_engine
from services.financial import ledger_transfers as LT
from services.financial.ledger_snapshot import capture_ledger_scope
print(LT.__file__, file=sys.stderr)
from uuid import UUID
case, start, end = UUID(sys.argv[1]), date.fromisoformat(sys.argv[2]), date.fromisoformat(sys.argv[3])
eng = _get_engine()
cap = capture_ledger_scope(eng, case_id=case, start_date=start, end_date=end)
times = []
for _ in range(3):
    t = time.time(); r = LT.ledger_transfer_candidates(cap); times.append(round(time.time() - t, 3))
print(json.dumps(dict(rows=len(r['rows']), candidates=len(r['candidates']), graded=(r.get('graded') or {}).get('by_level'), seconds=times)))
