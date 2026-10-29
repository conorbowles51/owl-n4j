"""Opt-in PostgreSQL check: saved metadata read once per row gives the same fields as reading the column.

Set FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL to a local test PostgreSQL connection; a disposable schema is used.
"""
import os
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, func, select, text, true
from sqlalchemy.dialects.postgresql import JSONB

from services.financial.imported_records import _read_once

URL = os.environ.get('FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires an explicit local PostgreSQL test connection')


def test_fields_read_once_equal_the_stored_column():
    schema = 'read_once_test_' + uuid.uuid4().hex
    admin = create_engine(URL)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        table = Table('documents', MetaData(schema=schema), Column('id', Integer, primary_key=True), Column('metadata', JSONB))
        big = 'x' * 300000  # stored compressed / out of line, as large saved readings are
        values = [
            dict(statement_account_id='a1', statement_incomplete_records=[dict(fields=dict(date='2021-01-02'))],
                 statement_details_review=dict(currency='USD'), statement_import_request=dict(currency='GBP', period_start='2021-01-01', rows=big)),
            dict(statement_import_request=dict(currency='EUR', period_end='2021-02-28'), statement_admission=dict(blockers=[dict(message='m')]), padding=big),
            {}, [1, 'statement_account_id'], 'text', 7, None, dict(statement_account_id=None, statement_details_review=[]),
        ]
        with admin.begin() as connection:
            table.create(connection)
            connection.execute(table.insert(), [dict(id=index, metadata=value) for index, value in enumerate(values)])
        def fields(metadata):
            return (metadata['statement_account_id'].as_string(), metadata['statement_incomplete_records'],
                    func.coalesce(metadata['statement_details_review']['currency'].as_string(), metadata['statement_import_request']['currency'].as_string()),
                    metadata['statement_admission']['blockers'], metadata['statement_import_request']['period_start'].as_string(),
                    metadata['statement_import_request']['period_end'].as_string())
        with admin.connect() as connection:
            session = SimpleNamespace(get_bind=lambda: connection)
            once_column, once = _read_once(session, table.c.metadata)
            assert once is not None
            plain = connection.execute(select(table.c.id, *fields(table.c.metadata)).order_by(table.c.id)).all()
            read_once = connection.execute(select(table.c.id, *fields(once_column)).select_from(table).join(once, true()).order_by(table.c.id)).all()
            whole = connection.execute(select(table.c.id, once_column).select_from(table).join(once, true()).order_by(table.c.id)).all()
        assert read_once == plain and len(plain) == len(values)
        assert [row[1] for row in whole] == values, 'the copy is the stored value itself'
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_other_databases_read_the_column_as_before():
    column = object()
    session = SimpleNamespace(get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name='sqlite')))
    assert _read_once(session, column) == (column, None)
