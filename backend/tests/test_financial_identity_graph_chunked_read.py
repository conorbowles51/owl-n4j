"""The identity sweep reads a case's payments in chunks: fetched in one go, d5b330d1's 27,673 rows held the
interpreter lock for 489 ms in the driver, inside a web worker. The plan must be the same as an unchunked read."""

from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified

from postgres.models.financial import FinancialTransaction
from services.financial import identity_graph
from tests.test_financial_duplicates import DuplicateTestCase


class ChunkedPaymentReadTests(DuplicateTestCase):
    def test_payments_are_read_in_chunks_and_the_plan_is_unchanged(self):
        self.make_copy(rows=tuple((n * 100, f"{n:02x}") for n in range(1, 8)))
        rows = list(self.db.query(FinancialTransaction).filter_by(case_id=self.case.id).order_by(FinancialTransaction.id))
        self.assertGreaterEqual(len(rows), 7)
        for row in rows[::2]:
            row.metadata_ = {**(row.metadata_ or {}),
                             'investigation_labels': {'counterparty_link': {'kind': 'account', 'id': str(self.account.id)}}}
            flag_modified(row, 'metadata_')
        self.db.commit()

        def plan(chunk):
            options = []
            def capture(conn, cursor, statement, parameters, context, executemany):
                if 'financial_transactions.ref_id' in statement:
                    options.append(context.execution_options.get('yield_per'))
            event.listen(self.engine, 'before_cursor_execute', capture)
            original = identity_graph.PAYMENT_LINK_CHUNK
            identity_graph.PAYMENT_LINK_CHUNK = chunk
            try:
                with self.SessionLocal() as db:
                    return identity_graph.identity_graph_plan(db, self.case.id), options
            finally:
                identity_graph.PAYMENT_LINK_CHUNK = original
                event.remove(self.engine, 'before_cursor_execute', capture)

        chunked, options = plan(2)
        whole, _ = plan(10_000)
        self.assertEqual(options, [2])
        self.assertEqual(len(chunked['payment_links']), len(rows[::2]))
        self.assertEqual(chunked, whole)
