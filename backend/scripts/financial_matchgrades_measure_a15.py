"""lx-matchgrades A15: read-only. Pairs of current admitted rows in one account with the same amount, direction and
description: same day or within 3 days (what the repeat rule would flag) vs 4-31 days apart (what it leaves)."""
import sys, json
sys.path.insert(0, '.')
from sqlalchemy import text
from postgres.session import _get_engine
with _get_engine().connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    for r in c.execute(text("""
        WITH t AS (SELECT case_id, account_id, amount_minor, direction, lower(regexp_replace(coalesce(description,''), '\\s+', ' ', 'g')) d,
                   coalesce(transaction_date, posted_date, value_date, effective_date) dy, id
                   FROM financial_transactions WHERE ledger_status = 'admitted' AND superseded_by_id IS NULL)
        SELECT a.case_id, count(*) FILTER (WHERE abs(a.dy - b.dy) <= 3) le3, count(*) FILTER (WHERE abs(a.dy - b.dy) BETWEEN 4 AND 31) d4_31
        FROM t a JOIN t b ON a.case_id = b.case_id AND a.account_id = b.account_id AND a.amount_minor = b.amount_minor
          AND a.direction = b.direction AND a.d = b.d AND a.d <> '' AND a.id < b.id AND abs(a.dy - b.dy) <= 31
        GROUP BY 1""")):
        print(json.dumps(dict(case=str(r[0]), within_3_days=r[1], days_4_to_31=r[2])))
    c.rollback()
