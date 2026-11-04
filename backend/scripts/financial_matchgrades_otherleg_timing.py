"""lx-matchgrades: read-only timing of the 'possible other legs' drawer for the payments with the most common amounts."""
import sys, time, json
sys.path.insert(0, '.')
from sqlalchemy import text
from sqlalchemy.orm import Session
from postgres.session import _get_engine
CASES = sys.argv[1:] or ['d5b330d1-b3fe-4b03-8539-98d9cc3115e0', '49494305-dcd5-4821-8937-d99cfec3abd9']
def main():
    from services.financial.payment_party_matches import other_leg_candidates
    with _get_engine().connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        s = Session(bind=c)
        for case in CASES:
            top = s.execute(text("select currency, amount_minor, count(*) n, min(id::text) from financial_transactions "
                                 "where case_id=:c group by 1,2 order by n desc limit 3"), dict(c=case)).all()
            for cur, amt, n, tid in top:
                t = time.time(); r = other_leg_candidates(s, case, tid); dt = time.time() - t
                print(json.dumps(dict(case=case[:8], amount=str(amt), rows=n, candidates=len((r or {}).get('candidates', [])),
                                      sec=round(dt, 2))), flush=True)
main()
