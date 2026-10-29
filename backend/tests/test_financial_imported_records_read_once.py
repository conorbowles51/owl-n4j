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


def test_source_audit_fields_and_text_check_equal_the_plain_reads():
    """source_audit reads evidence and saved-source fields through the copy, and asks content <> '' instead of length()."""
    from sqlalchemy import Text, cast, String
    from services.financial.source_audit import _present
    schema = 'read_once_audit_' + uuid.uuid4().hex
    admin = create_engine(URL)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        meta = MetaData(schema=schema)
        files = Table('files', meta, Column('id', Integer, primary_key=True), Column('metadata', JSONB))
        texts = Table('texts', meta, Column('id', Integer, primary_key=True), Column('content', Text, nullable=False))
        big = 'y' * 400000
        values = [
            dict(statement_root_evidence_id='r', financial_workspace=dict(schema='s', selected_by='n'), financial_file_visibility=dict(removed=True, revision='2'),
                 financial_review_history=[dict(page=big)], financial_review_progress={}, statement_version_request=None),
            dict(financial_file_visibility={}, financial_import_removal=[], financial_review_history='', padding=big),
            {}, [1], 'text', None, dict(financial_file_visibility=dict(removed='yes'), financial_review_progress=dict(a=1)),
        ]
        contents = ['', 'short', big, 'é' * 200000, ' ']
        with admin.begin() as connection:
            meta.create_all(connection)
            connection.execute(files.insert(), [dict(id=i, metadata=v) for i, v in enumerate(values)])
            connection.execute(texts.insert(), [dict(id=i, content=v) for i, v in enumerate(contents)])
        def fields(m):
            return (m['statement_root_evidence_id'].as_string(), m['financial_workspace']['schema'].as_string(),
                    m['financial_workspace']['selected_by'].as_string(), m['financial_file_visibility']['removed'].as_boolean(),
                    m['financial_file_visibility']['revision'].as_string(), _present(m['financial_file_visibility']),
                    _present(m['financial_import_removal']), _present(m['financial_review_progress']),
                    _present(m['financial_review_history']), _present(m['statement_version_request']))
        with admin.connect() as connection:
            session = SimpleNamespace(get_bind=lambda: connection)
            once_column, once = _read_once(session, files.c.metadata)
            plain = connection.execute(select(files.c.id, *fields(files.c.metadata)).order_by(files.c.id)).all()
            copied = connection.execute(select(files.c.id, *fields(once_column)).select_from(files).join(once, true()).order_by(files.c.id)).all()
            lengths = connection.execute(select(texts.c.id, func.length(texts.c.content)).order_by(texts.c.id)).all()
            nonempty = connection.execute(select(texts.c.id, texts.c.content != '').order_by(texts.c.id)).all()
        assert copied == plain and len(plain) == len(values)
        assert [bool(n) for _, n in lengths] == [bool(n) for _, n in nonempty] == [False, True, True, True, True]
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_source_audit_layout_ids_equal_the_python_reading():
    """Reader names picked out by PostgreSQL equal the ones the audit picks out of the loaded choices."""
    from services.financial.source_audit import _layout_ids
    schema = 'layout_ids_' + uuid.uuid4().hex
    admin = create_engine(URL)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        table = Table('documents', MetaData(schema=schema), Column('id', Integer, primary_key=True), Column('metadata', JSONB))
        big = [dict(layout_id=f'layout-{i}', rows=['z' * 50] * 200) for i in range(300)]
        values = [
            dict(choices=[dict(layout_id='a'), dict(layout_id=7), dict(other='x'), 'layout_id', [dict(layout_id='nested')], None,
                          dict(layout_id='b' * 400), dict(layout_id=None), dict(layout_id=['c']), dict(layout_id='a')]),
            dict(choices=big), dict(choices=[]), dict(choices={}), dict(choices=dict(layout_id='object, not a list')),
            dict(choices='a string'), dict(choices=None), dict(), [1], dict(choices=[dict(layout_id='é ✓')]),
        ]
        with admin.begin() as connection:
            table.create(connection)
            connection.execute(table.insert(), [dict(id=i, metadata=v) for i, v in enumerate(values)])
        def python_reading(choices):
            return {choice['layout_id'][:160] for choice in (choices or []) if isinstance(choice, dict) and isinstance(choice.get('layout_id'), str)}
        with admin.connect() as connection:
            session = SimpleNamespace(get_bind=lambda: connection)
            metadata, once = _read_once(session, table.c.metadata)
            ids, value = _layout_ids(once, metadata['choices'])
            rows = connection.execute(select(table.c.id, table.c.metadata, ids, value).select_from(table).join(once, true()).order_by(table.c.id)).all()
        assert len(rows) == len(values)
        for _, stored, layout_ids, rest in rows:
            choices = stored.get('choices') if isinstance(stored, dict) else None
            found = {layout_id[:160] for layout_id in layout_ids or []} | python_reading(rest)
            assert found == python_reading(choices)
            assert (layout_ids is None) == (not isinstance(choices, list)), 'only arrays are read in the database'
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
