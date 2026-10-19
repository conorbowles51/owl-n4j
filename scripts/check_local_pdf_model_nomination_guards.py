"""Verify nomination database guards inside a rollback-only local transaction."""
import sys
from pathlib import Path
from uuid import UUID, uuid4
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from postgres.models.financial_pdf_nominations import FinancialPdfNomination
from services.financial.pdf_candidates import _digest

engine = create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
case = UUID('e9cafc92-85a7-497c-aec8-049157e823d0')
file = UUID('582d271e-c6ee-4eb1-9441-f632794e1664')
checks = []
with engine.connect() as connection:
    transaction = connection.begin()
    try:
        request = {'case_id': str(case), 'evidence_file_id': str(file), 'execution_mode': 'simulated_test'}
        values = dict(id=uuid4(), case_id=case, evidence_file_id=file, status='pending', request=request, request_sha256=_digest(request), actor={'name':'Synthetic guard check'})
        table = FinancialPdfNomination.__table__
        def refuse(label, statement):
            try:
                with connection.begin_nested(): connection.execute(statement)
            except DBAPIError: checks.append(label)
            else: raise AssertionError(label)
        refuse('source case mismatch', table.insert().values(**{**values, 'request': {**request, 'case_id': str(uuid4())}}))
        refuse('precompleted insert', table.insert().values(**{**values, 'status':'completed','result':{},'outcome_actor':{},'completed_at':datetime.now(timezone.utc)}))
        connection.execute(table.insert().values(**values))
        where = table.update().where(table.c.id==values['id'])
        refuse('input rewrite', where.values(request_sha256='b'*64))
        refuse('incomplete terminal outcome', where.values(status='failed'))
        connection.execute(where.values(status='failed', error_code='user_abandoned', outcome_actor={'name':'Synthetic guard check'}, completed_at=datetime.now(timezone.utc)))
        refuse('terminal rewrite', where.values(error_code='provider_failed'))
        refuse('terminal reopen', where.values(status='pending',error_code=None,outcome_actor=None,completed_at=None))
        print('PASS: ' + '; '.join(checks))
    finally: transaction.rollback()
engine.dispose()
print('All guard writes rolled back; no provider called.')
