import sys, json, time, bisect
sys.path.insert(0, '.')
from collections import Counter
from sqlalchemy import text
from sqlalchemy.orm import Session
from postgres.session import _get_engine
CASES = sys.argv[1:]
def main():
    from services.financial import payment_party_matches as P
    from services.phone_analysis.money_pairings import _tolerance_minor
    with _get_engine().connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY")); s = Session(bind=c)
        for case in CASES:
            t0 = time.time(); rows = [r for r in P.case_rows(s, case) if r['ordering_date']]
            cre = sorted([r for r in rows if r['direction'] == 'credit'], key=lambda r: (r['currency'], abs(int(r['amount_minor']))))
            keys = [(r['currency'], abs(int(r['amount_minor']))) for r in cre]
            cnt = Counter()
            for d in (r for r in rows if r['direction'] == 'debit'):
                a = abs(int(d['amount_minor'])); cur = d['currency']
                for bp, name in ((100, '1pct'), (1000, 'tol10pct')):
                    tol = max(a * bp // 10000, 100) if name == '1pct' else _tolerance_minor(a, cur)
                    lo = bisect.bisect_left(keys, (cur, a - tol)); hi = bisect.bisect_right(keys, (cur, a + tol))
                    for cr in cre[lo:hi]:
                        if cr['account_id'] == d['account_id'] or abs(int(cr['amount_minor'])) == a: continue
                        g = abs((cr['ordering_date'] - d['ordering_date']).days)
                        cnt[name + ('_le31' if g <= 31 else ('_le365' if g <= 365 else '_gt365'))] += 1
            print(json.dumps(dict(case=case, near_amount_pairs=dict(cnt), sec=round(time.time() - t0, 1))), flush=True)
        c.rollback()
main()
