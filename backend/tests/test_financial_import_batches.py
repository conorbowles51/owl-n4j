import asyncio
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import AsyncMock
from uuid import uuid4, UUID
from sqlalchemy import select
from postgres.base import Base
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from postgres.models.evidence import EvidenceFolder, IngestionLog
from services.financial import import_batches as service
from services.financial.statement_import import StatementImportRequest, StatementReviewDraft
from services.financial.pdf_candidates import PdfMappingError
from tests.test_financial_statement_import import StatementImportTests as Fixture


class BatchImportTests(TestCase):
    def test_saved_holder_correction_clears_the_batch_warning_for_balance_only_statement(self):
        batch = self.create(); self.advance(batch)
        item = self.status(batch)['items'][0]
        raw = service.initial_request(self.f.preview())
        for row in raw['rows']:
            row['excluded'] = True
        raw['holder'] = ''
        with self.f.SessionLocal() as db:
            first = service.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(item['id']),
                request=StatementReviewDraft.model_validate(raw), expected_review_revision=service._digest({}))
            self.assertTrue(any(p.get('field') == 'holder' for p in self.status(batch)['items'][0]['problems']))
            raw['holder'] = 'Manually confirmed holder'
            service.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(item['id']),
                request=StatementReviewDraft.model_validate(raw), expected_review_revision=first['review_revision'])
        saved = self.status(batch)['items'][0]
        self.assertEqual(saved['holder'], raw['holder'])
        self.assertFalse(any(p.get('field') == 'holder' for p in saved['problems']))
        self.assertTrue(saved['can_import'])
        self.assertEqual(saved['transaction_count'], 0)

    def test_bulk_currency_uses_refreshed_reading_for_unreviewed_legacy_batch(self):
        from types import SimpleNamespace
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            item.summary = {**item.summary, 'revision': 'f'*64, 'review_model': 'older'}
            db.commit()
            current = service.batch_status(db, case_id=self.f.case.id, batch_id=batch)['items'][0]
            self.assertNotEqual(current['revision'], 'f'*64)
            service.set_selected_currency(db, case_id=self.f.case.id, batch_id=batch,
                selections=[SimpleNamespace(id=item.id, revision=current['currency_revision'])], currency='USD', actor=self.f.actor)
            self.assertEqual(db.get(Item, item.id).review_request['currency'], 'USD')

    def test_bulk_currency_keeps_corrections_reopens_and_imports_in_selected_currency(self):
        from types import SimpleNamespace
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            proposal = self.f.preview()
            raw = service.initial_request(proposal)
            raw['account_number'] = '00123456789'
            raw['holder'] = 'Manually checked holder'
            next(r for r in raw['rows'] if not r['excluded'])['description'] = 'Saved wording'
            item.review_request = raw
            db.commit()
            selection = SimpleNamespace(id=item.id, revision=service.currency_revision(item))
            result = service.set_selected_currency(db, case_id=self.f.case.id, batch_id=batch,
                selections=[selection], currency='MXN', actor=self.f.actor)
            self.assertEqual(result['updated'], 1)
            db.refresh(item)
            self.assertEqual(item.review_request['currency'], 'MXN')
            self.assertEqual(item.review_request['holder'], raw['holder'])
            self.assertEqual(item.review_request['account_number'], '00123456789')
            self.assertEqual(next(r for r in item.review_request['rows'] if not r['excluded'])['description'], 'Saved wording')
            self.assertEqual([r['amount_minor'] for r in item.review_request['rows']], [r['amount_minor'] for r in raw['rows']])
            with self.assertRaisesRegex(PdfMappingError, 'changed'):
                service.set_selected_currency(db, case_id=self.f.case.id, batch_id=batch,
                    selections=[selection], currency='USD', actor=self.f.actor)
        self.assertEqual(self.f.preview()['currency'], 'MXN')
        status = self.status(batch)
        with self.f.SessionLocal() as db:
            service.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                expected_revision=status['ready_revision'], actor=self.f.actor)
        self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['imported'], 1)
        with self.f.SessionLocal() as db:
            self.assertEqual({r.currency for r in db.scalars(select(FinancialTransaction))}, {'MXN'})

    def test_bulk_currency_cannot_touch_imported_or_cross_case_items(self):
        from types import SimpleNamespace
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            selection = SimpleNamespace(id=item.id, revision=service.currency_revision(item))
            with self.assertRaises(PdfMappingError):
                service.set_selected_currency(db, case_id=uuid4(), batch_id=batch, selections=[selection], currency='USD', actor=self.f.actor)
            item.status = 'pending_import'; db.commit()
            with self.assertRaisesRegex(PdfMappingError, 'changed'):
                service.set_selected_currency(db, case_id=self.f.case.id, batch_id=batch, selections=[selection], currency='USD', actor=self.f.actor)
            self.assertEqual(db.get(Item, item.id).summary['currency'], 'EUR')

    def test_bulk_currency_rolls_back_prior_items_if_a_later_period_is_unavailable(self):
        from types import SimpleNamespace
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            first = db.scalar(select(Item).where(Item.batch_id == batch))
            last = Item(id=UUID(int=2**128-1), batch_id=batch, file_id=first.file_id,
                statement_key='unavailable-period', status='attention', summary=deepcopy(first.summary))
            db.add(last); db.commit()
            selections = [SimpleNamespace(id=item.id, revision=service.currency_revision(item)) for item in (first, last)]
            with self.assertRaises(PdfMappingError):
                service.set_selected_currency(db, case_id=self.f.case.id, batch_id=batch,
                    selections=selections, currency='USD', actor=self.f.actor)
            db.refresh(first)
            self.assertEqual(first.summary['currency'], 'EUR')
            self.assertIsNone(first.review_request)
        self.assertEqual(self.f.preview()['currency'], 'EUR')

    def setUp(self):
        self.f = Fixture('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        self.f.file.status="processed"
        Base.metadata.create_all(self.f.db.connection(), tables=[Batch.__table__, Item.__table__, IngestionLog.__table__])
        self.f.db.commit()

    def tearDown(self):
        self.f.tearDown()

    def create(self, folder_ids=None, request_id=None):
        f=self.f
        with f.SessionLocal() as db:
            return service.create_batch(db,case_id=f.case.id,request_id=request_id or uuid4(),
                file_ids=[] if folder_ids else [f.file.id],folder_ids=folder_ids or [],actor=f.actor)

    def status(self,batch,**kwargs):
        with self.f.SessionLocal() as db:
            return service.batch_status(db,case_id=self.f.case.id,batch_id=batch,**kwargs)

    def advance(self,batch):
        process=AsyncMock(side_effect=AssertionError('Existing geometry must be reused'))
        asyncio.run(service.advance_batch(self.f.SessionLocal,batch,Path,process))
        process.assert_not_awaited()

    def test_folder_preparation_bulk_confirmation_and_repeat_do_not_duplicate(self):
        f=self.f
        folder=EvidenceFolder(id=uuid4(),case_id=f.case.id,name='Financial batch fixture')
        f.db.add(folder);f.db.flush();f.file.folder_id=folder.id;f.db.commit()
        batch=self.create([folder.id])
        self.advance(batch)
        before=self.status(batch)
        self.assertEqual(before['status'],'review')
        self.assertEqual(before['counts']['ready'],1,before)
        self.assertEqual(before['ready_transactions'],12)
        with f.SessionLocal() as db:
            service.queue_import(db,case_id=f.case.id,batch_id=batch,expected_revision=before['ready_revision'],actor=f.actor)
        self.advance(batch)
        after=self.status(batch)
        self.assertEqual(after['counts']['imported'],1,after)
        self.assertEqual(after['items'][0]['transaction_count'],12)
        self.advance(batch)
        # A second folder batch recognises the existing import too.
        second=self.create([folder.id]);self.advance(second)
        self.assertEqual(self.status(second)['counts']['imported'],1)
        with f.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))),12)

    def test_bulk_import_saves_balance_only_statement_and_file_status_without_payments(self):
        from services.financial.statement_file_status import statement_file_status
        from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
        Base.metadata.create_all(self.f.db.connection(), tables=[WorkspaceEntry.__table__, WorkspaceEntryLink.__table__])
        self.f.db.commit()
        self.f.standalone_balance_request([['Saldo final', '0,00 EUR']])
        batch = self.create()
        self.advance(batch)
        before = self.status(batch)
        self.assertEqual(before['ready_transactions'], 0)
        self.assertTrue(before['items'][0]['can_import'])
        with self.f.SessionLocal() as db:
            queued = service.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                expected_revision=before['ready_revision'], actor=self.f.actor)
        self.assertEqual(queued['queued'], 1)
        self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['imported'], 1)
        with self.f.SessionLocal() as db:
            status = statement_file_status(db, case_id=self.f.case.id)
            self.assertEqual(status['files'][0]['current_transactions'], 0)
            self.assertEqual(len(status['files'][0]['periods']), 1)
            self.assertEqual(list(db.scalars(select(FinancialTransaction))), [])
        repeated = self.create()
        self.advance(repeated)
        self.assertEqual(self.status(repeated)['counts']['imported'], 1)

    def test_readiness_separates_flagged_rows_and_balance_differences(self):
        proposal=self.f.preview()
        status,clean=service.assess(proposal)
        self.assertEqual(status,'ready',clean)
        changed=deepcopy(proposal)
        payment=next(r for r in changed['rows'] if not r['excluded'])
        payment['issues']=['Check the date against the PDF.']
        status,summary=service.assess(changed)
        self.assertEqual(status,'attention')
        self.assertIn(payment['id'],[p['row_id'] for p in summary['problems']])
        self.assertFalse(any(p['row_id'] is None for p in summary['problems']))
        self.assertEqual(summary['problems'][0]['page'], payment['page_number'])
        raw=service.initial_request(changed)
        next(r for r in raw['rows'] if r['id']==payment['id'])['reason']='Checked against the PDF.'
        self.assertEqual(service.assess(changed,raw)[0],'ready')
        edited=service.initial_request(proposal)
        next(r for r in edited['rows'] if r['id']==payment['id'])['description']='Corrected description'
        status,summary=service.assess(proposal,edited)
        self.assertEqual(status,'ready')
        self.assertTrue(summary['can_import'])
        self.assertEqual(summary['problems'], [])
        # An arithmetical mismatch never joins ready statements.
        changed=deepcopy(proposal)
        changed['rows'].append(dict(id='end',kind='balance',excluded=True,issues=[],page_number=1,fields=dict(description='Closing balance',balance='1')))
        self.assertEqual(service.assess(changed)[0],'attention')

    def test_bulk_worker_imports_undated_interest_with_its_period_and_no_printed_date(self):
        self.f.card_balance_request()
        import hashlib
        from postgres.models.evidence import EvidenceDocumentText
        text = self.f.db.get(EvidenceDocumentText, self.f.file.id)
        text.content = text.content.replace('Currency: EUR', 'Currency: USD')
        text.content_sha256 = hashlib.sha256(text.content.encode()).hexdigest()
        self.f.db.commit()
        batch = self.create()
        self.advance(batch)
        before = self.status(batch)
        self.assertEqual(before['counts']['ready'], 1, before)
        with self.f.SessionLocal() as db:
            service.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                                 expected_revision=before['ready_revision'], actor=self.f.actor)
        self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['imported'], 1)
        with self.f.SessionLocal() as db:
            rows = list(db.scalars(select(FinancialTransaction)))
            self.assertEqual(len(rows), 3)
            charge = next(r for r in rows if r.description == 'Interest Charge on Purchases')
            self.assertIsNone(charge.transaction_date)
            self.assertEqual(charge.provenance['date_basis'], 'statement_end_ordering_only')

    def test_confirmation_only_queues_the_ready_snapshot_and_cases_are_isolated(self):
        f=self.f;batch=self.create();self.advance(batch)
        before=self.status(batch)
        with f.SessionLocal() as db:
            original=db.scalar(select(Item).where(Item.batch_id==batch))
            flagged=Item(id=uuid4(),batch_id=batch,file_id=f.file.id,statement_key='other-period',status='attention',summary={**original.summary,'period_start':'2024-01-01','period_end':'2024-12-31','can_import':False,'problems':[{'message':'Check an amount.','row_id':'1:0:1'}]})
            db.add(flagged);db.commit()
            # An unrelated attention item does not alter the approved ready list.
            service.queue_import(db,case_id=f.case.id,batch_id=batch,expected_revision=before['ready_revision'],actor=f.actor)
            self.assertEqual(flagged.status,'attention')
        with f.SessionLocal() as db:
            with self.assertRaisesRegex(PdfMappingError,'ready statements changed'):
                service.queue_import(db,case_id=f.case.id,batch_id=batch,expected_revision=before['ready_revision'],actor=f.actor)
            with self.assertRaisesRegex(PdfMappingError,'not found'):
                service.batch_status(db,case_id=uuid4(),batch_id=batch)
        self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['attention'],1)
        self.assertEqual(self.status(batch)['counts']['imported'],1)
        self.assertEqual(self.status(batch,only_problems=True)['total'],1)

    def test_saved_corrections_are_used_by_background_import(self):
        f=self.f;batch=self.create();self.advance(batch)
        item=self.status(batch)['items'][0]
        raw=service.initial_request(f.preview())
        payment=next(r for r in raw['rows'] if not r['excluded'])
        payment['description']='Corrected fixture payment'
        payment['reason']='Compared with the synthetic statement.'
        with f.SessionLocal() as db:
            result=service.save_review(db,case_id=f.case.id,batch_id=batch,item_id=UUID(item['id']),request=StatementImportRequest.model_validate(raw),expected_review_revision=service._digest({}))
            self.assertEqual(result['status'],'ready')
            with self.assertRaisesRegex(PdfMappingError,'Another user saved'):
                service.save_review(db,case_id=f.case.id,batch_id=batch,item_id=UUID(item['id']),request=StatementImportRequest.model_validate(raw),expected_review_revision=service._digest({}))
        ready=self.status(batch)
        with f.SessionLocal() as db:
            service.queue_import(db,case_id=f.case.id,batch_id=batch,expected_revision=ready['ready_revision'],actor=f.actor)
        self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['imported'],1)
        with f.SessionLocal() as db:
            rows=list(db.scalars(select(FinancialTransaction)))
            self.assertIn('Corrected fixture payment',[r.description for r in rows])

    def test_individual_saved_progress_is_retained_when_added_to_a_batch(self):
        from services.financial.statement_progress import save_progress
        f=self.f
        raw=service.initial_request(f.preview())
        payment=next(row for row in raw['rows'] if not row['excluded'])
        payment.update(date='', reason='Date correction is not finished')
        with f.SessionLocal() as db:
            save_progress(db,case_id=f.case.id,evidence_file_id=f.file.id,
                request=StatementReviewDraft.model_validate(raw),expected_review_revision='initial',actor=f.actor)
        batch=self.create(); self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['attention'],1)
        with f.SessionLocal() as db:
            item=db.scalar(select(Item).where(Item.batch_id==batch))
            self.assertEqual(next(row for row in item.review_request['rows'] if row['id']==payment['id'])['date'],'')

    def test_incomplete_progress_can_be_bulk_imported_with_missing_values_retained(self):
        f=self.f; batch=self.create(); self.advance(batch)
        item=self.status(batch)['items'][0]
        raw=service.initial_request(f.preview())
        payment=next(r for r in raw['rows'] if not r['excluded'])
        payment['amount_minor']=''
        raw['holder']=''
        with f.SessionLocal() as db:
            result=service.save_review(db, case_id=f.case.id, batch_id=batch, item_id=UUID(item['id']),
                request=StatementReviewDraft.model_validate(raw), expected_review_revision=service._digest({}))
            self.assertEqual(result['status'], 'attention')
            saved=db.get(Item, UUID(item['id']))
            self.assertEqual(saved.review_request['holder'], '')
            self.assertEqual(result['review_revision'], service._digest(saved.review_request))
            self.assertTrue(saved.summary['can_import'])
            service.queue_import(db, case_id=f.case.id, batch_id=batch,
                expected_revision=service.ready_revision([saved]), actor=f.actor)
        self.advance(batch)
        after = self.status(batch)
        self.assertEqual(after['counts']['imported'], 1)
        from postgres.models.financial import FinancialSourceDocument
        with f.SessionLocal() as db:
            source = db.scalar(select(FinancialSourceDocument).where(FinancialSourceDocument.evidence_file_id == f.file.id))
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 11)
            self.assertEqual(source.metadata_['statement_incomplete_records'][0]['fields']['amount_minor'], '')
            self.assertEqual(source.metadata_['statement_import_request']['holder'], '')

    def test_next_problem_crosses_list_pages_and_never_crosses_cases(self):
        f=self.f; batch=self.create(); self.advance(batch)
        original=self.status(batch)['items'][0]
        target=None
        with f.SessionLocal() as db:
            for n in range(130):
                identity=uuid4()
                if n == 128: target=identity
                db.add(Item(id=identity, batch_id=batch, file_id=f.file.id, statement_key=f'synthetic-{n}',
                    status='attention' if n == 128 else 'ready',
                    summary={**original, 'filename':f'Z synthetic {n:03d}', 'account':f'TEST{n+1000}', 'problems':[dict(row_id='3:0:4', message='Check date')] if n == 128 else []}))
            db.commit()
            result=service.next_problem(db, case_id=f.case.id, batch_id=batch, item_id=UUID(original['id']))
            self.assertEqual(result['item_id'], str(target))
            self.assertEqual(result['row_id'], '3:0:4')
            self.assertEqual(service.next_problem(db, case_id=f.case.id, batch_id=batch, item_id=target)['item_id'], None)
            with self.assertRaises(PdfMappingError):
                service.next_problem(db, case_id=uuid4(), batch_id=batch, item_id=target)

    def test_start_is_idempotent_and_worker_recovers_after_recorded_import(self):
        f=self.f;request=uuid4();batch=self.create(request_id=request)
        self.assertEqual(self.create(request_id=request),batch)
        self.advance(batch)
        ready=self.status(batch)
        with f.SessionLocal() as db:
            service.queue_import(db,case_id=f.case.id,batch_id=batch,expected_revision=ready['ready_revision'],actor=f.actor)
        self.advance(batch)
        # Simulate a process exit after the writer commits, before the batch receipt.
        with f.SessionLocal() as db:
            item=db.scalar(select(Item).where(Item.batch_id==batch));item.status='pending_import'
            db.get(Batch,batch).status='preparing';db.commit()
        self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['imported'],1)
        with f.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))),12)

    def test_each_recognised_period_is_checked_separately_and_unknown_currency_stays_out(self):
        from unittest.mock import patch
        f=self.f;batch=self.create();base=f.preview()
        choices=[dict(id='a'*64),dict(id='b'*64)]
        calls=[]
        def reading(*args,**kwargs):
            calls.append(kwargs)
            result=deepcopy(base);result['statement_choices']=choices
            result['statement_id']=kwargs.get('statement_id')
            if result['statement_id']=='b'*64:
                next(row for row in result['rows'] if not row['excluded'])['issues']=['Check the date.']
            return result
        with f.SessionLocal() as db, patch.object(service,'read_statement_import',side_effect=reading):
            owner=db.get(Batch,batch)
            service.prepare_reviews(db,owner,owner.files[0])
        status=self.status(batch)
        self.assertEqual(status['counts']['ready'],1)
        self.assertEqual(status['counts']['attention'],1)
        self.assertEqual({i['statement_id'] for i in status['items']},{'a'*64,'b'*64})
        self.assertIs(calls[0]['_cache'],calls[1]['_cache'])
        unknown=deepcopy(base);unknown['currency']=''
        self.assertEqual(service.assess(unknown)[0],'attention')

    def test_newly_ready_statement_requires_a_new_confirmation(self):
        f=self.f;batch=self.create();self.advance(batch);before=self.status(batch)
        with f.SessionLocal() as db:
            original=db.scalar(select(Item).where(Item.batch_id==batch))
            db.add(Item(id=uuid4(),batch_id=batch,file_id=f.file.id,statement_key='late-period',status='ready',summary=deepcopy(original.summary)))
            db.commit()
            with self.assertRaisesRegex(PdfMappingError,'ready statements changed'):
                service.queue_import(db,case_id=f.case.id,batch_id=batch,expected_revision=before['ready_revision'],actor=f.actor)
            self.assertFalse(list(db.scalars(select(Item).where(Item.status=='pending_import'))))
