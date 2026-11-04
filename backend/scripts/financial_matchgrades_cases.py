import sys; sys.path.insert(0, '.')
from sqlalchemy import text
from postgres.session import _get_engine
with _get_engine().connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    for r in c.execute(text("SELECT k.id, k.title, (SELECT count(*) FROM financial_transactions t WHERE t.case_id=k.id AND t.ledger_status='admitted' AND t.superseded_by_id IS NULL) n, (SELECT count(*) FROM phone_extractions e WHERE e.case_id=k.id) p FROM cases k ORDER BY 3 DESC")):
        if r.n or r.p: print(r.id, r.n, r.p, r.title)
