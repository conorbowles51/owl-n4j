import sys; sys.path.insert(0, '.')
from sqlalchemy import text
from postgres.session import _get_engine
with _get_engine().connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    for r in c.execute(text("SELECT date_trunc('month', ordering_date)::date m, count(*) FROM financial_transactions WHERE case_id=:c AND ledger_status='admitted' AND superseded_by_id IS NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 3"), {"c": sys.argv[1]}): print(r)
