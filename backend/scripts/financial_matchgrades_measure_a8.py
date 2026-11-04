"""lx-matchgrades E A8: read-only live distribution of number-switching pairs that share >= 1 counterpart."""
import sys, json, time
sys.path.insert(0, '.')
from collections import Counter
from sqlalchemy import text
from postgres.session import _get_engine
from services.phone_analysis import number_switching as NS
PHONES = ['d9945277-6c80-4a39-82c7-93a95d420384', '4aa79795-1076-4c75-985f-784936abb71f', '574a9752-7d19-4f42-8f98-2112615f4a48',
          '88e01b57-d472-452a-b103-b694292ed012', '7006c0ab-9c93-473a-900a-76d06d9d0603']
with _get_engine().connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    for case in PHONES:
        t = time.time()
        base, _ = NS.analyse(c, case, dict(gap_days=14, window_days=90, threshold=0.5, min_shared=5))
        res, k = NS.analyse(c, case, dict(gap_days=14, window_days=90, threshold=0.0, min_shared=1))
        buckets = Counter()
        for r in res:
            m = r['measures']
            buckets[('sh>=5' if m['shared'] >= 5 else 'sh2-4' if m['shared'] >= 2 else 'sh1',
                     'j>=.5' if m['similarity'] >= .5 else 'j.25-.5' if m['similarity'] >= .25 else 'j<.25',
                     'mk' if m['markers'] else '-')] += 1
        print(json.dumps(dict(case=case[:8], default=len(base), shared1=len(res), counts=k, sec=round(time.time()-t, 1),
                              buckets={'|'.join(b): n for b, n in sorted(buckets.items())})), flush=True)
    c.rollback()
