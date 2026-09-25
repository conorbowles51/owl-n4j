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
from postgres.models.financial_money_trails import FinancialMoneyTrail
from postgres.models.financial_recovery import FinancialRecoveryRelease, FinancialRecoveryRun, FinancialRecoveryItem
from postgres.models.evidence import IngestionLog
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialStatementReviewDraft
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from routers.users import get_current_db_user
from routers import evidence, evidence_folders, financial_statement_import, financial_ledger, financial_adjudication
from tests.test_financial_statement_import import StatementImportTests


def new_fixture():
    fixture = StatementImportTests(); fixture.setUp()
    Base.metadata.create_all(fixture.engine, tables=[CaseMembership.__table__, IngestionLog.__table__, FinancialMoneyTrail.__table__,
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
    app.add_middleware(CORSMiddleware, allow_origin_regex=r'http://(localhost|127\.0\.0\.1)(:[0-9]+)?', allow_methods=['*'], allow_headers=['*'], allow_credentials=True)
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
    @app.post('/__fixture/reconciled')
    def reconciled(quiet: bool = False):
        from tests.financial_reconciled_fixture import install_reconciled_source
        install_reconciled_source(fixture, quiet=quiet)
        # A real selectable PDF supports source-view browser acceptance. All
        # contents are synthetic and the artifact stays in the temporary fixture.
        import fitz
        import hashlib
        pdf=fitz.open(); page=pdf.new_page()
        page.insert_text((60,60), 'Synthetic Company - TEST123\nSynthetic statement source text\nOpening balance EUR 12,450\nClosing balance EUR ' + ('12,450' if quiet else '47,450'))
        pdf.save(str(fixture.path));pdf.close()
        fixture.file.sha256=hashlib.sha256(fixture.path.read_bytes()).hexdigest()
        fixture.db.commit()
        return {'synthetic': True}
    @app.post('/__fixture/currency-batch')
    async def currency_batch():
        import json
        from pathlib import Path
        from uuid import uuid4
        from unittest.mock import AsyncMock
        from services.financial import import_batches
        from postgres.models.evidence import EvidenceTableGeometry, EvidenceDocumentText
        with fixture.SessionLocal() as db:
            geometry=db.get(EvidenceTableGeometry,(fixture.file.id,1))
            geometry.payload=json.loads(json.dumps(geometry.payload,ensure_ascii=False).replace('€',''))
            text=db.get(EvidenceDocumentText,fixture.file.id)
            text.content=text.content.replace('Currency: EUR','Currency: USD')
            from hashlib import sha256
            text.content_sha256=sha256(text.content.encode()).hexdigest();text.character_count=len(text.content)
            db.commit()
            identifier=import_batches.create_batch(db,case_id=fixture.case.id,request_id=uuid4(),file_ids=[fixture.file.id],folder_ids=[],actor=fixture.actor)
        await import_batches.advance_batch(fixture.SessionLocal,identifier,Path,AsyncMock(side_effect=AssertionError('Retained reading expected')))
        return {'batch_id':str(identifier)}
    @app.post('/__fixture/printed-total-corrections')
    def printed_total_corrections():
        """A real synthetic PDF with two deliberately incorrect OCR controls."""
        from copy import deepcopy
        from hashlib import sha256
        import fitz
        from postgres.models.evidence import EvidenceTableGeometry
        from tests.financial_reconciled_fixture import install_reconciled_source
        from tests.test_financial_pdf_geometry_candidates import rectangle
        install_reconciled_source(fixture)
        geometry = fixture.db.get(EvidenceTableGeometry, (fixture.file.id, 1))
        payload = deepcopy(geometry.payload)
        cells = payload[0]['table']['values']
        first = max(cell['row'] for cell in cells) + 1
        printed = {}
        for offset, (label, column, actual) in enumerate((
                ('Total credits', 2, '1,035,000.00'), ('Total debits', 3, '1,000,000.00'))):
            for col, value in ((1, label), (column, '0.00')):
                cells.append(dict(row=first + offset, column=col, text=value,
                    locator=rectangle(440 + offset * 20, x=20 + col * 100, width=90, height=15)))
            printed[(first + offset, column)] = actual
        geometry.payload = payload
        # Keep the real PDF accurate while the retained reading models an OCR
        # error. No parser/assessment/writer is mocked in the browser journey.
        pdf = fitz.open()
        page = pdf.new_page(width=600, height=800)
        page.insert_text((20, 15), 'Synthetic Company - TEST123 - EUR - January to December 2023', fontsize=9)
        for cell in cells:
            x, y, _, _ = cell['locator']['rect']
            value = printed.get((cell['row'], cell['column']), cell['text']).replace('€', '')
            page.insert_text((x / 1000 + 1, y / 1000 + 10), value, fontsize=8)
        pdf.save(str(fixture.path))
        pdf.close()
        fixture.file.sha256 = sha256(fixture.path.read_bytes()).hexdigest()
        fixture.db.commit()
        controls = {row['fields']['total_direction']: row['id'] for row in fixture.preview()['rows']
            if row['kind'] == 'statement_total'}
        return dict(synthetic=True, credit_row_id=controls['credit'], debit_row_id=controls['debit'],
            credit_minor='103500000', debit_minor='100000000', currency='EUR', transaction_count=12)
    @app.post('/__fixture/account-history')
    def history_fixture():
        from copy import deepcopy
        from hashlib import sha256
        from uuid import UUID, uuid4
        from datetime import date
        from postgres.models.financial import FinancialSourceDocument, FinancialStatementPeriod, FinancialAccount
        from services.financial.account_history import record_admission_snapshot
        from tests.financial_reconciled_fixture import install_reconciled_source
        from services.financial.import_batches import initial_request
        from services.financial.statement_import import StatementImportRequest
        from services.financial.statement_admission import assess_admission
        install_reconciled_source(fixture,quiet=True)
        raw=initial_request(fixture.preview());assessment=assess_admission(fixture.preview(),StatementImportRequest.model_validate(raw))
        raw.update(no_activity_confirmed=True,no_activity_revision=assessment['revision'])
        receipt=fixture.confirm(raw)
        with fixture.SessionLocal() as db:
            source=db.get(FinancialSourceDocument,UUID(receipt['source_document_id']))
            period=db.get(FinancialStatementPeriod,UUID(receipt['period_id'])) if receipt.get('period_id') else db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id==source.id))
            period.period_start=date(2023,1,1);period.period_end=date(2023,1,31)
            record_admission_snapshot(db,source,period)
            account=db.get(FinancialAccount,period.account_id)
            def copy_row(row):return {c.key:deepcopy(getattr(row,c.key)) for c in row.__mapper__.column_attrs if c.key not in ('id','created_at','updated_at')}
            ids=[str(account.id)]
            for label,currency,liability in [('Second synthetic account','EUR',False),('Synthetic dollars','USD',False),('Synthetic card','USD',True)]:
                values=copy_row(account);values.update(identity_key='synthetic-history-'+str(uuid4()),holder_name=label,identifier_as_printed='HIST'+str(len(ids)),currency=currency,account_type='credit_card' if liability else account.account_type)
                other=FinancialAccount(id=uuid4(),**values);db.add(other);db.flush();ids.append(str(other.id))
                from postgres.models.evidence import EvidenceFile
                file_values=copy_row(fixture.file);file_values['original_filename']=label+'.pdf'
                other_file=EvidenceFile(id=uuid4(),**file_values);db.add(other_file);db.flush()
                values=copy_row(source);values['metadata_']=deepcopy(source.metadata_);values['evidence_file_id']=other_file.id
                if liability:values['metadata_']['statement_import_original']['metadata']['balance_convention']='liability_owed'
                other_source=FinancialSourceDocument(id=uuid4(),**values);db.add(other_source);db.flush()
                values=copy_row(period);values.update(account_id=other.id,source_document_id=other_source.id,currency=currency,
                    opening_balance_minor=-1245000 if liability else 1245000,closing_balance_minor=-1245000 if liability else 1245000)
                other_period=FinancialStatementPeriod(id=uuid4(),**values);db.add(other_period);db.flush()
                record_admission_snapshot(db,other_source,other_period)
            db.commit()
        return {'account_ids':ids}
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
