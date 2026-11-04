"""lx-matchgrades E A6: read-only live effect of the message-copy time tolerance (tau 120 s) and offset window (24 h)."""
import sys, json, time
sys.path.insert(0, '.')
from collections import Counter
from sqlalchemy import text
from postgres.session import _get_engine
from services.phone_analysis import message_reconciliation as MR, framework as F
PHONES = ['d9945277-6c80-4a39-82c7-93a95d420384', '4aa79795-1076-4c75-985f-784936abb71f', '574a9752-7d19-4f42-8f98-2112615f4a48',
          '88e01b57-d472-452a-b103-b694292ed012', '7006c0ab-9c93-473a-900a-76d06d9d0603']
with _get_engine().connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    for case in PHONES:
        t = time.time(); out = dict(case=case[:8])
        for name, p in (("default", {}), ("tau3600_window72", {"tau_s": 3600, "offset_window_h": 72})):
            res, _ = MR.analyse(c, case, F.validate_parameters(MR, p))
            out[name] = dict(Counter(r['kind'] for r in res))
        out['sec'] = round(time.time() - t, 1)
        print(json.dumps(out), flush=True)
    c.rollback()
