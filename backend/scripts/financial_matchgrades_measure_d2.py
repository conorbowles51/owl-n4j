"""lx-matchgrades D: read-only. Before: open suggestions stored (score >= 0.5). After: every candidate by strength."""
import sys, json, time
sys.path.insert(0, '.')
from collections import Counter
from sqlalchemy import text
from postgres.session import _get_engine
from services.phone import identity_decisions as idd
print(idd.__file__, file=sys.stderr)
CASES = ['d9945277-6c80-4a39-82c7-93a95d420384', '4aa79795-1076-4c75-985f-784936abb71f', '574a9752-7d19-4f42-8f98-2112615f4a48',
         '88e01b57-d472-452a-b103-b694292ed012', '7006c0ab-9c93-473a-900a-76d06d9d0603']
with _get_engine().connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    for case in CASES:
        before = c.execute(text("SELECT count(*) FROM phone_identity_suggestions WHERE case_id=:c AND state='open'"), {"c": case}).scalar()
        t0 = time.time(); rows = idd.candidate_rows(c, case)
        lv = Counter(idd.strength(r["score"], r["reasons"])[0] for r in rows)
        kinds = Counter("+".join(sorted({x["reason"] for x in r["reasons"]})) for r in rows)
        print(json.dumps(dict(case=case, before_open=before, after_total=len(rows), after_by_level=dict(lv), by_reasons=dict(kinds), sec=round(time.time()-t0, 2))), flush=True)
    c.rollback()
