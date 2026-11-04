"""lx-matchgrades E A16: read-only live effect of phone-analysis pairing defaults at their widest allowed values."""
import sys, json, time
sys.path.insert(0, '.')
from collections import Counter
from sqlalchemy import text
from postgres.session import _get_engine
from services.phone_analysis import framework as F, extraction_comparison as EC, reparse_comparison as RC, device_users as DU
PHONES = ['d9945277-6c80-4a39-82c7-93a95d420384', '4aa79795-1076-4c75-985f-784936abb71f', '574a9752-7d19-4f42-8f98-2112615f4a48',
          '88e01b57-d472-452a-b103-b694292ed012', '7006c0ab-9c93-473a-900a-76d06d9d0603']
WIDE = {EC: {"app_jaccard": 0.1}, RC: {"time_window_hours": 48}, DU: {"min_days": 1}}
class Ctx:
    def progress(self, *a, **k): pass
    def cancelled(self): return False
def kinds(m, c, case, p):
    p = F.validate_parameters(m, p)
    out = m.analyse(c, case, p) if hasattr(m, 'analyse') else m.run(c, case, p, Ctx())
    res = out[0] if isinstance(out, tuple) else out
    return dict(Counter(r.get('kind') for r in res))
with _get_engine().connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    for case in PHONES:
        out = dict(case=case[:8])
        for m, p in WIDE.items():
            name = m.__name__.rsplit('.', 1)[-1]
            try:
                t = time.time()
                out[name] = dict(default=kinds(m, c, case, {}), wide=kinds(m, c, case, p), sec=round(time.time() - t, 1))
            except Exception as e:
                out[name] = repr(e)[:200]
                c.rollback(); c.execute(text("SET TRANSACTION READ ONLY"))
        print(json.dumps(out, default=str), flush=True)
    c.rollback()
