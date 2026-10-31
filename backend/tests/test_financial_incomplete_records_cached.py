"""The statement files' incomplete-records list is a cached view: d5b330d1 measured 1.8-3.7 s per call (every
statement's saved metadata read for each request, 0 records to show) and a 1.86 s GIL stall in a web worker. It reads
only database rows of its case (traced on 49494305: no clock, files or graph). Equality with the uncached function
was checked on six cases (computed, memory hit, and a new process from the saved copy): 24 of 24 byte-identical."""
from routers import financial_statement_import


def test_the_incomplete_records_list_is_served_by_the_view_cache():
    route = financial_statement_import.incomplete_records
    assert route.__code__.co_filename.endswith('services/financial/view_cache.py')
    assert route.__wrapped__.__code__.co_filename.endswith('routers/financial_statement_import.py')


def test_the_incomplete_records_list_is_registered_cached_at_its_path():
    endpoints = {route.path: route.endpoint for route in financial_statement_import.router.routes
                 if 'GET' in getattr(route, 'methods', ())}
    path = next(path for path in endpoints if path.endswith('/incomplete-records'))
    assert endpoints[path] is financial_statement_import.incomplete_records
    assert hasattr(endpoints[path], '__wrapped__')


import os
import uuid

import pytest

URL = os.environ.get('FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL')
needs_pg = pytest.mark.skipif(not URL, reason='Requires an explicit local PostgreSQL test connection')


@pytest.fixture
def statement(tmp_path, monkeypatch):
    """A disposable schema with the real tables: one case, one admitted statement holding one incomplete record."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from postgres.base import Base
    from tests.test_financial_duplicates import TABLES
    from postgres.models.case import Case
    from postgres.models.user import User
    from postgres.models.enums import GlobalRole, ExtractionLayer, ProofClass
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial import FinancialSourceDocument
    from services.financial import view_cache
    from services.financial.runs import open_ingestion_run
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    admin = create_engine(URL)
    schema = 'incomplete_records_cached_' + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(URL, connect_args={'options': f'-csearch_path={schema}'})
    view_cache.clear(); view_cache._tables_cache.clear()
    try:
        Base.metadata.create_all(engine, tables=TABLES)
        Session = sessionmaker(bind=engine)
        with Session() as db:
            user = User(id=uuid.uuid4(), email='i@example.test', name='I', password_hash='-', global_role=GlobalRole.user, is_active=True)
            case = Case(id=uuid.uuid4(), title='Matter', created_by_user_id=user.id, owner_user_id=user.id)
            db.add_all([user, case]); db.commit()
            run = open_ingestion_run(case_id=case.id, actor=user, session_factory=Session)
            evidence = EvidenceFile(id=uuid.uuid4(), case_id=case.id, original_filename='statement.pdf', stored_path='/e/s.pdf', sha256='1' * 64)
            db.add(evidence); db.commit()
            document = FinancialSourceDocument(id=uuid.uuid4(), evidence_file_id=evidence.id, sha256_at_ingestion='1' * 64,
                document_type='bank_statement', proof_class=ProofClass.p2.value, extraction_layer=ExtractionLayer.structural.value,
                parser_name='statement_pdf', parser_version='1.4.0', status='admitted',
                metadata_=dict(statement_import_request=dict(currency='GBP'), statement_incomplete_records=[record('r1', 'Rent')]))
            db.add(run.stamp(document)); db.commit()
            yield dict(engine=engine, Session=Session, case_id=case.id, document_id=document.id)
    finally:
        view_cache.clear(); view_cache._tables_cache.clear()
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def record(id, description):
    fields = dict(date='2026-01-02', description=description, amount=None)
    return dict(id=id, fields=fields, original=dict(kind='printed', page_number=1, source_cells=[]), missing_fields=['amount'], version=0)


def call(statement, **filters):
    from routers.financial_statement_import import incomplete_records
    params = dict(account_ids=None, account_holders=None, account_id=None, source_document_id=None, evidence_file_id=None,
                  start_date=None, end_date=None, offset=0, limit=50)
    params.update(filters)
    with statement['Session']() as db:
        return incomplete_records(case_id=statement['case_id'], db=db, **params)


def counting(monkeypatch):
    from services.financial import imported_records as module
    calls = []
    real = module.imported_records
    def counted(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)
    monkeypatch.setattr(module, 'imported_records', counted)
    return calls


def body(result):
    import json
    from fastapi.encoders import jsonable_encoder
    return json.loads(result.body) if hasattr(result, 'body') else jsonable_encoder(result)


@needs_pg
def test_the_saved_copy_is_reused_until_its_records_change(statement, monkeypatch):
    from datetime import date
    from postgres.models.financial import FinancialSourceDocument
    from sqlalchemy import update
    calls = counting(monkeypatch)
    first = body(call(statement))
    assert [item['fields']['description'] for item in first['records']] == ['Rent'] and len(calls) == 1
    assert body(call(statement)) == first and len(calls) == 1, 'unchanged rows: the saved copy answers'
    # Another filter is another copy, never this one.
    assert body(call(statement, start_date=date(2026, 2, 1)))['total'] == 0 and len(calls) == 2
    # A completed or added record is shown at once.
    with statement['Session']() as db:
        db.execute(update(FinancialSourceDocument).where(FinancialSourceDocument.id == statement['document_id']).values(
            metadata_=dict(statement_import_request=dict(currency='GBP'),
                           statement_incomplete_records=[record('r1', 'Rent'), record('r2', 'Rates')])))
        db.commit()
    after = body(call(statement))
    assert len(calls) == 3 and [item['fields']['description'] for item in after['records']] == ['Rent', 'Rates']


@needs_pg
def test_a_refused_date_range_is_never_kept(statement, monkeypatch):
    from datetime import date
    from fastapi import HTTPException
    for _ in range(2):
        with pytest.raises(HTTPException) as refused:
            call(statement, start_date=date(2026, 2, 1), end_date=date(2026, 1, 1))
        assert refused.value.status_code == 422
    from services.financial import view_cache
    assert not [key for key in view_cache._entries if key[0] == 'incomplete-records']
