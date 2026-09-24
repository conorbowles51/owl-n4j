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
from postgres.models.evidence import IngestionLog
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialStatementReviewDraft
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from routers.users import get_current_db_user
from routers import evidence, evidence_folders, financial_statement_import, financial_ledger, financial_adjudication
from tests.test_financial_statement_import import StatementImportTests


def new_fixture():
    fixture = StatementImportTests(); fixture.setUp()
    Base.metadata.create_all(fixture.engine, tables=[CaseMembership.__table__, IngestionLog.__table__,
        FinancialCandidateMapping.__table__, FinancialStatementReviewDraft.__table__,
        WorkspaceEntry.__table__, WorkspaceEntryLink.__table__])
    from services.financial.file_scope import mark_financial_workspace
    mark_financial_workspace(fixture.file, user_id=fixture.user.id)
    fixture.file.status = 'processed'
    for name in ('Interview transcript.pdf', 'Unsent statement.pdf'):
        ordinary = fixture.evidence(('b' if name.startswith('Interview') else 'c') * 64)
        ordinary.original_filename = name
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
    app.dependency_overrides[evidence.get_current_user] = lambda: {'username': fixture.user.email}
    for router in (evidence.router, evidence_folders.router, financial_statement_import.router, financial_ledger.router, financial_adjudication.router):
        app.include_router(router)
    @app.post('/__fixture/reset')
    def reset():
        nonlocal fixture
        fixture.tearDown(); fixture = new_fixture()
        return {'synthetic':True}
    @app.get('/__fixture')
    def identity():
        return {'synthetic':True,'case_id':str(fixture.case.id),'file_id':str(fixture.file.id)}
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
