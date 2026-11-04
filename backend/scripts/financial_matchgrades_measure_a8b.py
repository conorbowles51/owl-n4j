"""lx-matchgrades E A8 after: read-only live counts of the graded number-switching results at the defaults."""
import sys, json, time
sys.path.insert(0, '.')
from collections import Counter
from sqlalchemy import text
from postgres.session import _get_engine
from services.phone_analysis import number_switching as NS, framework as F
PHONES = ['d9945277-6c80-4a39-82c7-93a95d420384', '4aa79795-1076-4c75-985f-784936abb71f', '574a9752-7d19-4f42-8f98-2112615f4a48',
          '88e01b57-d472-452a-b103-b694292ed012', '7006c0ab-9c93-473a-900a-76d06d9d0603']
print(NS.__file__, NS.VERSION, flush=True)
with _get_engine().connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    for case in PHONES:
        t = time.time()
        res, k = NS.analyse(c, case, F.validate_parameters(NS, {}))
        print(json.dumps(dict(case=case[:8], results=len(res), kinds=dict(Counter(r['kind'] for r in res)),
                              levels=dict(Counter(r['measures']['level'] for r in res)), counts=k,
                              words=NS.counts_words(k), sec=round(time.time() - t, 1))), flush=True)
    c.rollback()
