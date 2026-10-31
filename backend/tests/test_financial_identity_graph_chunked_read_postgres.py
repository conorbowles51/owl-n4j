"""Opt-in real PostgreSQL: the identity plan's payment read streams through a server-side cursor
(yield_per) while resolved_link looks accounts up on the same session. The plan must equal an unchunked
read's, the lookups inside the open stream must work (review follow-up to 45787abf), and only rows that carry a
link reach Python."""

import os
import unittest
from uuid import uuid4

from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from postgres.base import Base
from postgres.models.financial import FinancialAccount, FinancialTransaction
from services.financial import identity_graph
from tests.test_financial_duplicates import DuplicateTestCase


@unittest.skipUnless(os.getenv('LOUPE_TEST_LOCAL_POSTGRES') == '1', 'Requires isolated local PostgreSQL')
class ChunkedPaymentReadPostgresTests(DuplicateTestCase):
    def test_lookups_inside_the_streamed_read_give_the_unchunked_plan(self):
        self.make_copy(rows=tuple((n * 100, f"{n:02x}") for n in range(1, 8)))
        rows = list(self.db.query(FinancialTransaction).filter_by(case_id=self.case.id).order_by(FinancialTransaction.id))
        # Two rows carry no link; the read leaves them in the database.
        for row in rows[:5]:
            row.metadata_ = {**(row.metadata_ or {}),
                             'investigation_labels': {'counterparty_link': {'kind': 'account', 'id': str(self.account.id)}}}
            flag_modified(row, 'metadata_')
        self.db.commit()

        url = make_url(os.environ['LOUPE_TEST_LOCAL_POSTGRES_URL'])
        self.assertEqual((url.host, url.port, url.database), ('127.0.0.1', 55434, 'loupe_local'))
        schema = 'identity_chunked_read_' + uuid4().hex
        admin = create_engine(url, connect_args={'connect_timeout': 2})
        engine = create_engine(url, connect_args={'connect_timeout': 2, 'options': '-csearch_path=' + schema})
        names = set(inspect(self.engine).get_table_names())
        tables = [table for table in Base.metadata.sorted_tables if table.name in names]
        try:
            with admin.begin() as db:
                db.execute(text('CREATE SCHEMA ' + schema))
            Base.metadata.create_all(engine, tables=tables)
            with self.engine.connect() as source, engine.begin() as target:
                for table in tables:
                    copied = [dict(row) for row in source.execute(select(table)).mappings()]
                    if copied:
                        target.execute(table.insert(), copied)
            SessionLocal = sessionmaker(bind=engine, autoflush=False)

            def plan(chunk):
                statements = []
                def capture(conn, cursor, statement, parameters, context, executemany):
                    statements.append((statement, bool(context.execution_options.get('yield_per'))))
                event.listen(engine, 'before_cursor_execute', capture)
                original = identity_graph.PAYMENT_LINK_CHUNK
                identity_graph.PAYMENT_LINK_CHUNK = chunk
                try:
                    with SessionLocal() as db:
                        return identity_graph.identity_graph_plan(db, self.case.id), statements
                finally:
                    identity_graph.PAYMENT_LINK_CHUNK = original
                    event.remove(engine, 'before_cursor_execute', capture)

            # The case's accounts are loaded before the payment read, so resolved_link answers from the session and
            # valid data issues no SQL mid-stream. Make every lookup a real query on the same session to prove that
            # SQL while the server-side cursor is open works and changes nothing.
            from services.financial import payment_counterparty_link
            resolved = payment_counterparty_link.resolved_link
            read = []
            stored = payment_counterparty_link.stored_link
            payment_counterparty_link.stored_link = lambda labels, reviewed: read.append(1) or stored(labels, reviewed)
            def resolved_with_a_query(db, case_id, link):
                db.execute(select(FinancialAccount.id).where(FinancialAccount.case_id == case_id)).all()
                return resolved(db, case_id, link)
            whole, _ = plan(100_000)
            payment_counterparty_link.resolved_link = resolved_with_a_query
            try:
                chunked, statements = plan(2)
            finally:
                payment_counterparty_link.resolved_link = resolved
                payment_counterparty_link.stored_link = stored
            self.assertEqual(chunked, whole)
            self.assertEqual(len(chunked['payment_links']), 5)
            self.assertEqual(len(read), 2 * 5)
            streamed = [i for i, (statement, streaming) in enumerate(statements) if streaming]
            self.assertEqual(len(streamed), 1)
            # Queries ran on the same session while the stream was open.
            self.assertTrue(any('FROM financial_accounts' in statement for statement, _ in statements[streamed[0] + 1:]))
        finally:
            engine.dispose()
            with admin.begin() as db:
                db.execute(text('DROP SCHEMA IF EXISTS ' + schema + ' CASCADE'))
            admin.dispose()
