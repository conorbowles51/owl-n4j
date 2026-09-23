"""Opt-in loopback-only synthetic service for investigator browser acceptance.

Run from backend: PYTHON_DOTENV_DISABLED=1 python -m tests.financial_browser_server
No production database, login, provider call or client document is used.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from postgres.base import Base
from postgres.session import get_db
from postgres.models.case_membership import CaseMembership
from postgres.models.enums import CaseMembershipRole
from postgres.models.user import User
from postgres.models.financial import FinancialTransaction
from routers.users import get_current_db_user
from routers import financial_statement_import, financial_ledger, financial_adjudication
from tests.test_financial_statement_import import StatementImportTests


def new_fixture():
    fixture = StatementImportTests(); fixture.setUp()
    Base.metadata.create_all(fixture.engine, tables=[CaseMembership.__table__])
    fixture.db.add(CaseMembership(case_id=fixture.case.id, user_id=fixture.user.id,
        membership_role=CaseMembershipRole.owner, added_by_user_id=fixture.user.id,
        permissions={'case':{'view':True,'edit':True},'evidence':{'upload':True,'view':True}}))
    fixture.db.commit()
    return fixture


def create_app():
    fixture = new_fixture()
    @asynccontextmanager
    async def lifespan(app):
        yield
        fixture.tearDown()
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origin_regex=r'http://(localhost|127\.0\.0\.1)(:[0-9]+)?', allow_methods=['*'], allow_headers=['*'])
    def db_session():
        with fixture.SessionLocal() as db: yield db
    def user(db=Depends(get_db)): return db.get(User, fixture.user.id)
    app.dependency_overrides[get_db] = db_session
    app.dependency_overrides[get_current_db_user] = user
    for router in (financial_statement_import.router, financial_ledger.router, financial_adjudication.router):
        app.include_router(router)
    @app.post('/__fixture/reset')
    def reset():
        nonlocal fixture
        fixture.tearDown(); fixture = new_fixture()
        return {'synthetic':True}
    @app.get('/__fixture')
    def identity():
        return {'synthetic':True,'case_id':str(fixture.case.id),'file_id':str(fixture.file.id)}
    @app.get('/api/evidence')
    def files():
        return {'files':[{'id':str(fixture.file.id),'case_id':str(fixture.case.id),
            'original_filename':fixture.file.original_filename,'status':'processed'}]}
    @app.get('/__fixture/payments')
    def saved(db=Depends(get_db)):
        from services.financial.transaction_query import to_view
        rows = db.scalars(select(FinancialTransaction).where(FinancialTransaction.case_id == fixture.case.id,
            FinancialTransaction.superseded_by_id.is_(None))).all()
        return {'payments':[to_view(row, account=row.account).to_json() for row in rows]}
    return app


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(create_app(), host='127.0.0.1', port=58129, log_level='warning')
