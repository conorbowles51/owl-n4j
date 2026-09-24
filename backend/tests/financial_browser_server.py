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
from postgres.models.financial_recovery import FinancialRecoveryRelease, FinancialRecoveryRun, FinancialRecoveryItem
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
        WorkspaceEntry.__table__, WorkspaceEntryLink.__table__, FinancialRecoveryRelease.__table__, FinancialRecoveryRun.__table__, FinancialRecoveryItem.__table__])
    from services.financial.file_scope import mark_financial_workspace
    mark_financial_workspace(fixture.file, user_id=fixture.user.id)
    fixture.file.status = 'processed'
    for name in ('Interview transcript.pdf', 'Unsent statement.pdf', 'Payments.csv', 'Accounts.xlsx', 'Invoice.docx', 'Receipt.png', 'Legacy.xls'):
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
    @app.post('/__fixture/mixed-statements')
    def mixed_statements():
        from tests.test_financial_statement_import_credit_one import install_collection
        install_collection(fixture)
        return {'synthetic': True}
    @app.post('/__fixture/duplicate-statements')
    def duplicate_statements():
        from hashlib import sha256
        from postgres.models.evidence import EvidenceDocumentText
        from tests.test_financial_statement_overlap import StatementOverlapTests
        from services.financial.file_scope import mark_financial_workspace
        text = fixture.db.get(EvidenceDocumentText, fixture.file.id)
        text.content += 'Bank: Synthetic Bank\nStatement Period: January 1, 2023 - December 31, 2023\n'
        text.content_sha256 = sha256(text.content.encode()).hexdigest()
        text.character_count = len(text.content)
        fixture.db.commit()
        helper = StatementOverlapTests()
        helper.f, helper.primary = fixture, fixture.file
        other = helper.copy_file()
        mark_financial_workspace(other, user_id=fixture.user.id)
        fixture.db.commit()
        return {'synthetic': True, 'other_file_id': str(other.id)}
    @app.post('/__fixture/recovery')
    def recover_fixture():
        from tests.test_financial_deployment_recovery import partial_import, snapshot
        document = partial_import(fixture)
        item = snapshot(fixture)
        return {'item_id': str(item), 'source_document_id': str(document)}
    @app.post('/__fixture/recover-next')
    def recover_next():
        from pathlib import Path
        from services.financial.deployment_recovery import recover_one
        with fixture.SessionLocal() as db:
            identifier = db.scalar(select(FinancialRecoveryItem.id).where(FinancialRecoveryItem.file_id == fixture.file.id))
        recover_one(fixture.SessionLocal, identifier, Path)
        return {'synthetic': True}
    @app.post('/__fixture/missing-reading-batch')
    async def missing_reading_batch():
        from pathlib import Path
        from uuid import uuid4
        from unittest.mock import AsyncMock
        from services.financial import import_batches
        from postgres.models.financial_import_batches import FinancialImportBatch
        with fixture.SessionLocal() as db:
            identifier = import_batches.create_batch(db, case_id=fixture.case.id, request_id=uuid4(),
                file_ids=[fixture.file.id], folder_ids=[], actor=fixture.actor)
        await import_batches.advance_batch(fixture.SessionLocal, identifier, Path, AsyncMock(side_effect=AssertionError('Retained reading expected')))
        with fixture.SessionLocal() as db:
            batch = db.get(FinancialImportBatch, identifier)
            batch.files = [{**batch.files[0], 'file_id': str(uuid4()), 'status': 'checked'}]
            db.commit()
        return {'batch_id': str(identifier)}
    @app.post('/__fixture/review-reasons-batch')
    async def review_reasons_batch():
        from pathlib import Path
        from uuid import uuid4
        from hashlib import sha256
        from unittest.mock import AsyncMock
        from services.financial import import_batches
        from postgres.models.evidence import EvidenceDocumentText
        with fixture.SessionLocal() as db:
            text = db.get(EvidenceDocumentText, fixture.file.id)
            text.content = text.content.replace('Account Name: Test Company\n', '')
            text.content_sha256 = sha256(text.content.encode()).hexdigest()
            text.character_count = len(text.content)
            text.source_locations = [{**loc, 'end_char': len(text.content)} for loc in text.source_locations]
            db.commit()
            identifier = import_batches.create_batch(db, case_id=fixture.case.id, request_id=uuid4(),
                file_ids=[fixture.file.id], folder_ids=[], actor=fixture.actor)
        await import_batches.advance_batch(fixture.SessionLocal, identifier, Path, AsyncMock(side_effect=AssertionError('Retained reading expected')))
        return {'batch_id': str(identifier)}
    @app.post('/__fixture/advance-batch/{batch_id}')
    async def advance_fixture_batch(batch_id: str):
        from pathlib import Path
        from uuid import UUID
        from unittest.mock import AsyncMock
        from services.financial.import_batches import advance_batch
        await advance_batch(fixture.SessionLocal, UUID(batch_id), Path, AsyncMock(side_effect=AssertionError('Retained reading expected')))
        return {'synthetic': True}
    return app


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(create_app(), host='127.0.0.1', port=58129, log_level='warning')
