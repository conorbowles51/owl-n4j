"""lx-matchgrades E A14: read-only live counts of receipt items still in the queue and receipts settled."""
import sys, json
sys.path.insert(0, '.')
from sqlalchemy import text
from postgres.session import _get_engine
with _get_engine().connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    rows = c.execute(text("""
      SELECT b.case_id::text, i.status,
             count(*) FILTER (WHERE i.summary::text LIKE '%Open its document review%') AS receipt_like,
             count(*) FILTER (WHERE i.summary ? 'receipt_settlement') AS settled
      FROM financial_import_batch_items i JOIN financial_import_batches b ON b.id = i.batch_id
      GROUP BY 1, 2 HAVING count(*) FILTER (WHERE i.summary::text LIKE '%Open its document review%') > 0
          OR count(*) FILTER (WHERE i.summary ? 'receipt_settlement') > 0 ORDER BY 1, 2""")).fetchall()
    for r in rows:
        print(json.dumps(dict(case=r[0][:8], status=r[1], receipt_like=r[2], settled=r[3])), flush=True)
    c.rollback()
